import datetime
import logging
import random
from collections.abc import Iterable, Mapping
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.utils import timezone
from django.utils.formats import number_format

from djtools.utils.calendario import somar_dias_uteis

from comum.models import Vinculo

from rsc_tae.enums import AreaCorrecao, SituacaoAvaliacaoItem, SituacaoDocumentoPreliminar, SituacaoProcesso, TipoDocumentoPreliminar
from rsc_tae.models import (
    ApontamentoCorrecaoRSCTae,
    AvaliacaoAnexoRSCTae,
    AvaliacaoProcessoRSCTae,
    DeliberacaoItemCRSCRSCTae,
    DocumentoPreliminarRSCTae,
    OrigemTransicao,
    ProcessoRSCTae,
    RolSaberCompetencia,
    RolSaberCompetenciaAnexo,
    RolSaberCompetenciaPreenchimento,
)
from rsc_tae.models.anexo import (
    meses_para_anos_pontuaveis,
    pontos_anexo,
    pontos_item_anexos,
    taxa_por_papel,
    unidades_pontuaveis,
    unidades_pontuaveis_anexos,
)

logger = logging.getLogger(__name__)


def codigos_situacao_exercicio_externo(configuracao=None) -> list[str]:
    """Códigos SIAPE das situações configuradas como exercício fora do órgão.

    Lista vazia (nenhuma situação marcada ou configuração inexistente) significa que
    nenhum processo é sinalizado — a política é decisão da CRSC, não do código.

    ``Situacao.codigo`` é nullable: situação sem código fica de fora, porque um ``None``
    na lista viraria ``IN (NULL)`` e nunca casaria — a situação ficaria configurada e sem
    efeito, calada. Aceita a configuração já carregada (o admin a cacheia na request).
    """
    from rsc_tae.models import ConfiguracaoRSCTae

    config = configuracao or ConfiguracaoRSCTae.objects.first()
    if not config:
        return []
    return list(config.situacoes_exercicio_externo.exclude(codigo__isnull=True).values_list('codigo', flat=True))


def _ids_servidores_indisponiveis(data=None):
    """Retorna conjunto de IDs de Servidor afastados ou de férias na data informada (padrão: hoje).

    Usa queries em lote — adequado para filtrar querysets de Vinculo sem N+1.
    """
    from rh.models import ServidorAfastamento

    data = data or datetime.date.today()

    # Servidores com afastamento ativo na data (exceto afastamentos PGD configurados)
    indisponiveis = set(
        ServidorAfastamento.objects.exclude_afastamentos_pgd()
        .filter(data_inicio__lte=data, data_termino__gte=data, cancelado=False)
        .values_list('servidor_id', flat=True)
    )

    # Servidores de férias na data (app férias é opcional)
    if 'ferias' in settings.INSTALLED_APPS:
        try:
            from ferias.models import ParcelaFerias

            ids_ferias = set(
                ParcelaFerias.objects.filter(
                    data_inicio__lte=data,
                    data_fim__gte=data,
                ).values_list('ferias__servidor_id', flat=True)
            )
            indisponiveis |= ids_ferias
        except Exception:
            pass

    return indisponiveis


def _calcular_data_limite_avaliacao(data_inicio=None):
    """Retorna a data-limite para avaliação somando dias úteis configurados a partir de data_inicio."""
    from rsc_tae.models import ConfiguracaoRSCTae

    config = ConfiguracaoRSCTae.objects.first()
    dias = config.dias_uteis_prazo_avaliador if config else 10
    inicio = data_inicio or datetime.date.today()
    return somar_dias_uteis(inicio, dias)


def _verificar_prazos_expirados(processo):
    """Substitui avaliadores com prazo de avaliação vencido por novo sorteio.

    Deve ser chamado antes de montar o contexto nas views visualizar() e avaliar().
    Opera dentro de transaction.atomic() para garantir consistência.
    """
    if processo.situacao != SituacaoProcesso.EM_ANALISE:
        return

    hoje = datetime.date.today()
    expiradas = list(
        AvaliacaoProcessoRSCTae.objects.filter(
            processo=processo,
            substituido=False,
            finalizada=False,
            data_limite_avaliacao__lt=hoje,
        ).select_related('avaliador_vinculo')
    )

    for ap in expiradas:
        try:
            _substituir_avaliador(
                processo=processo,
                avaliador_out=ap.avaliador_vinculo,
                motivo=4,  # MOTIVO_SUBSTITUICAO_PRAZO
                justificativa=f'Prazo expirado em {ap.data_limite_avaliacao:%d/%m/%Y}.',
                realizado_por_vinculo=None,
            )
        except Exception:
            logger.exception(
                'Erro ao substituir avaliador %s com prazo expirado no processo %s',
                ap.avaliador_vinculo,
                processo.pk,
            )


def _motivo_indisponibilidade_vinculo(vinculo, data=None):
    """Retorna string descritiva do motivo de indisponibilidade do vínculo, ou '' se disponível.

    Usa os métodos do Servidor para verificação individual (adequado para exibição por membro).
    """
    if not vinculo:
        return ''
    try:
        servidor = vinculo.relacionamento
        if not hasattr(servidor, 'estah_afastado_ateh'):
            return ''  # Não é servidor — considera disponível
        data = data or datetime.date.today()
        afastamento = servidor.estah_afastado_ateh(data)
        if afastamento:
            termino = afastamento.data_termino.strftime('%d/%m/%Y')
            sigla = getattr(getattr(afastamento, 'afastamento', None), 'sigla', '') or ''
            descricao = f' ({sigla})' if sigla else ''
            return f'Afastado até {termino}{descricao}'
        ferias = servidor.estah_de_ferias_ateh(data)
        if ferias:
            fim = ferias.data_fim.strftime('%d/%m/%Y')
            return f'Férias até {fim}'
    except Exception:
        pass
    return ''


def _sortear_avaliadores(processo, quantidade=None, realizado_por_vinculo=None):
    """Sorteia aleatoriamente `quantidade` avaliadores aptos para o processo (por padrão, ProcessoRSCTae.QUANTIDADE_AVALIADORES).

    Critérios de aptidão:
    - Membro ativo do banco AvaliadorAuxiliarRSCTae (data_inativacao nula, ativo=True)
    - Não está afastado nem de férias hoje
    - Não é o dono do processo

    Executa dentro de transaction.atomic():
    - Define processo.avaliadores (M2M)
    - Cria AvaliacaoProcessoRSCTae com prazo para cada sorteado
    - Registra SorteioAvaliadorRSCTae para auditoria
    - Transiciona processo para EM_ANALISE

    Levanta ValueError se não houver avaliadores suficientes.
    Retorna lista de Vinculo sorteados.
    """
    from rsc_tae.models import AvaliadorAuxiliarRSCTae, SorteioAvaliadorRSCTae

    quantidade = ProcessoRSCTae.QUANTIDADE_AVALIADORES if quantidade is None else quantidade
    ids_indisponiveis = _ids_servidores_indisponiveis()

    candidatos_qs = AvaliadorAuxiliarRSCTae.aptos_para_sorteio(excluir_vinculo_ids=[processo.vinculo_id])
    if ids_indisponiveis:
        candidatos_qs = candidatos_qs.exclude(
            vinculo__tipo_relacionamento__model='servidor',
            vinculo__id_relacionamento__in=ids_indisponiveis,
        )

    candidatos_ids = list(candidatos_qs.values_list('vinculo_id', flat=True))

    if len(candidatos_ids) < quantidade:
        raise ValueError(
            f'O regulamento exige {quantidade} avaliadores auxiliares; '
            f'apenas {len(candidatos_ids)} disponíveis no banco. '
            'Verifique o banco de avaliadores auxiliares.'
        )

    sorteados_ids = random.sample(candidatos_ids, quantidade)
    sorteados = list(Vinculo.objects.filter(id__in=sorteados_ids).select_related('pessoa'))

    agora = timezone.now()
    data_limite = _calcular_data_limite_avaliacao()

    with transaction.atomic():
        processo_ref = ProcessoRSCTae.objects.select_for_update().get(pk=processo.pk)

        # Limpa avaliadores anteriores e avaliações pendentes
        avaliadores_anteriores_ids = set(processo_ref.avaliadores.values_list('id', flat=True))
        if avaliadores_anteriores_ids:
            AvaliacaoProcessoRSCTae.objects.filter(
                processo=processo_ref,
                avaliador_vinculo_id__in=avaliadores_anteriores_ids,
                finalizada=False,
            ).delete()
            AvaliacaoAnexoRSCTae.objects.filter(
                anexo__processo=processo_ref,
                avaliador_vinculo_id__in=avaliadores_anteriores_ids,
            ).delete()

        processo_ref.avaliadores.set(sorteados)

        for av in sorteados:
            # Reativa a avaliação existente se o sorteado já participou do processo (limpa `substituido`)
            AvaliacaoProcessoRSCTae.reativar_ou_criar(processo_ref, av, data_limite, agora=agora)
            SorteioAvaliadorRSCTae.objects.create(
                processo=processo_ref,
                avaliador_sorteado=av,
                motivo=SorteioAvaliadorRSCTae.MOTIVO_INICIAL,
                realizado_por_vinculo=realizado_por_vinculo,
            )

        processo_ref.transicionar(
            SituacaoProcesso.EM_ANALISE,
            motivo='Avaliadores sorteados automaticamente — processo encaminhado para análise.',
            por_vinculo=realizado_por_vinculo,
            origem=OrigemTransicao.AUTOMATICO,
            campos_extras={'avaliador_atual': None},
        )

    logger.info(
        'Sorteio RSC-TAE: processo #%s — %s avaliadores sorteados: %s',
        processo.pk,
        quantidade,
        ', '.join(str(v) for v in sorteados),
    )
    return sorteados


def _substituir_avaliador(processo, avaliador_out, motivo, justificativa, realizado_por_vinculo):
    """Substitui um avaliador por um novo sorteado do banco de avaliadores auxiliares.

    1. Marca a AvaliacaoProcessoRSCTae do avaliador_out como substituido=True
    2. Remove avaliador_out do M2M processo.avaliadores
    3. Apaga AvaliacaoAnexoRSCTae pendentes do avaliador_out
    4. Sorteia 1 substituto do banco AvaliadorAuxiliarRSCTae
    5. Cria AvaliacaoProcessoRSCTae + SorteioAvaliadorRSCTae para o substituto
    6. Permanece em EM_ANALISE (não altera situação do processo)
    """
    from rsc_tae.models import AvaliadorAuxiliarRSCTae, SorteioAvaliadorRSCTae

    with transaction.atomic():
        processo_ref = ProcessoRSCTae.objects.select_for_update().get(pk=processo.pk)

        # IDs de todos que já foram sorteados neste processo (incluindo substituídos)
        ids_ja_sorteados = list(AvaliacaoProcessoRSCTae.objects.filter(processo=processo_ref).values_list('avaliador_vinculo_id', flat=True))

        # Marca como substituído
        AvaliacaoProcessoRSCTae.objects.filter(
            processo=processo_ref,
            avaliador_vinculo=avaliador_out,
        ).update(substituido=True)

        # Remove do M2M
        processo_ref.avaliadores.remove(avaliador_out)

        # Remove avaliações de anexo pendentes
        AvaliacaoAnexoRSCTae.objects.filter(
            anexo__processo=processo_ref,
            avaliador_vinculo=avaliador_out,
        ).delete()

        # Sorteia substituto do banco de avaliadores auxiliares
        ids_excluidos = list({*ids_ja_sorteados, processo_ref.vinculo_id})
        candidatos = list(AvaliadorAuxiliarRSCTae.aptos_para_sorteio(excluir_vinculo_ids=ids_excluidos))
        ids_indisponiveis = _ids_servidores_indisponiveis()
        if ids_indisponiveis:
            candidatos = [
                c
                for c in candidatos
                if not (
                    getattr(c.vinculo, 'tipo_relacionamento', None)
                    and getattr(c.vinculo, 'tipo_relacionamento', None).model == 'servidor'
                    and c.vinculo.id_relacionamento in ids_indisponiveis
                )
            ]

        if not candidatos:
            raise ValueError(f'Não há avaliadores aptos no banco para substituir {avaliador_out}. Verifique o banco de avaliadores auxiliares.')

        substituto_aux = random.choice(candidatos)
        substituto = substituto_aux.vinculo

        # Adiciona ao M2M e (re)ativa a avaliação — embora o sorteio exclua quem já participou,
        # o caminho único de criação garante que `substituido` nunca fique órfão
        processo_ref.avaliadores.add(substituto)
        data_limite = _calcular_data_limite_avaliacao()
        agora = timezone.now()
        AvaliacaoProcessoRSCTae.reativar_ou_criar(processo_ref, substituto, data_limite, agora=agora)

        # Registra no histórico de sorteios
        SorteioAvaliadorRSCTae.objects.create(
            processo=processo_ref,
            avaliador_sorteado=substituto,
            avaliador_substituido=avaliador_out,
            motivo=motivo,
            justificativa=justificativa,
            realizado_por_vinculo=realizado_por_vinculo,
        )

    logger.info(
        'Substituição RSC-TAE: processo #%s — %s substituído por %s (motivo=%s)',
        processo.pk,
        avaliador_out,
        substituto,
        motivo,
    )
    return substituto


def _listar_candidatos_avaliadores(lista_excessao_ids=None):
    qs = Vinculo.objects.filter(ativo=True).select_related('user', 'pessoa').order_by('pessoa__nome', 'user__username')
    if lista_excessao_ids:
        qs = qs.exclude(id__in=lista_excessao_ids)
    return qs


def _get_vinculo_do_usuario(request):
    servidor = request.user.get_relacionamento()
    return servidor.get_vinculo()


def _rh_sistemico(user) -> bool:
    return bool(getattr(user, 'has_perm', lambda *_: False)('rh.eh_rh_sistemico'))


def _rh_campus(user) -> bool:
    return bool(getattr(user, 'has_perm', lambda *_: False)('rh.eh_rh_campus'))


def _mesmo_campus(vinculo_a, vinculo_b) -> bool:
    """True se os dois vínculos estão lotados em setores do mesmo campus (UO).

    Vínculo sem setor é situação esperada (ex.: sem lotação ativa) e resulta em False,
    sem registrar exceção.
    """
    setor_a = getattr(vinculo_a, 'setor', None)
    setor_b = getattr(vinculo_b, 'setor', None)
    if setor_a is None or setor_b is None:
        return False
    return setor_a.uo_id == setor_b.uo_id


def _contexto_acesso_processo(request, processo: ProcessoRSCTae) -> dict:
    try:
        vinculo_usuario = _get_vinculo_do_usuario(request)
    except Exception:
        logger.exception('Não foi possível obter o vínculo do usuário %s', request.user)
        vinculo_usuario = None

    eh_dono = bool(vinculo_usuario and processo.vinculo_id == vinculo_usuario.id)
    eh_rh_sistemico = _rh_sistemico(request.user)
    eh_rh_campus = _rh_campus(request.user)
    eh_mesmo_campus = bool(eh_rh_campus and vinculo_usuario and _mesmo_campus(vinculo_usuario, processo.vinculo))

    return {
        'vinculo_usuario': vinculo_usuario,
        'eh_dono': eh_dono,
        'eh_rh_sistemico': eh_rh_sistemico,
        'eh_rh_campus': eh_rh_campus,
        'eh_mesmo_campus': eh_mesmo_campus,
    }


def _validar_acesso_processo(request, processo: ProcessoRSCTae):
    ctx = _contexto_acesso_processo(request, processo)
    if not ctx['eh_dono']:
        raise PermissionDenied('Permissão negada.')
    return ctx['vinculo_usuario']


def _validar_acesso_processo_leitura(request, processo: ProcessoRSCTae) -> dict:
    ctx = _contexto_acesso_processo(request, processo)
    if ctx['eh_dono'] or ctx['eh_rh_sistemico']:
        return ctx

    # Avaliador designado com permissão de avaliar pode visualizar o processo (leitura).
    if request.user.has_perm('rsc_tae.avaliar_processorsctae') and ctx['vinculo_usuario']:
        try:
            eh_avaliador = processo.avaliadores.filter(id=ctx['vinculo_usuario'].id).exists()
        except Exception:
            logger.exception('Erro ao verificar avaliadores do processo %s para o usuário %s', processo.pk, request.user)
            eh_avaliador = False
        if not eh_avaliador:
            eh_avaliador = int(getattr(processo, 'avaliador_atual_id', 0) or 0) == int(ctx['vinculo_usuario'].id)
        if eh_avaliador:
            return ctx

    raise PermissionDenied('Permissão negada.')


def _validar_acesso_avaliacao(request, processo: ProcessoRSCTae) -> dict:
    if not request.user.has_perm('rsc_tae.avaliar_processorsctae'):
        raise PermissionDenied('Permissão negada.')

    try:
        vinculo_usuario = _get_vinculo_do_usuario(request)
    except Exception:
        logger.exception('Não foi possível obter o vínculo do usuário %s', request.user)
        vinculo_usuario = None

    if vinculo_usuario and processo.vinculo_id == vinculo_usuario.id:
        raise PermissionDenied('Você não pode avaliar seu próprio processo.')

    if processo.situacao not in SituacaoProcesso.AVALIAVEIS:
        raise PermissionDenied('Este processo não está com situação "Em Análise".')

    if not vinculo_usuario:
        raise PermissionDenied('Vínculo do usuário não encontrado.')

    # Novo fluxo: múltiplos avaliadores designados
    try:
        if processo.avaliadores.filter(id=vinculo_usuario.id).exists():
            return _contexto_acesso_processo(request, processo)
    except PermissionDenied:
        raise
    except Exception:
        logger.exception('Erro ao verificar avaliadores do processo %s para o usuário %s', processo.pk, request.user)

    # Fallback para processos antigos (avaliador único)
    avaliador_atual_id = getattr(processo, 'avaliador_atual_id', None)
    if not avaliador_atual_id:
        raise PermissionDenied('Avaliador não definido para este processo.')

    if int(avaliador_atual_id) != int(getattr(vinculo_usuario, 'id', 0) or 0):
        raise PermissionDenied('Este processo está atribuído a outro avaliador.')

    return _contexto_acesso_processo(request, processo)


def _formatar_avaliador_para_exibicao(user) -> str:
    if not user:
        return '-'

    try:
        relacionamento = user.get_relacionamento()
    except Exception:
        relacionamento = None

    if relacionamento:
        try:
            vinculo = relacionamento.get_vinculo()
        except Exception:
            vinculo = None
        return str(vinculo or relacionamento)

    try:
        nome = (user.get_full_name() or '').strip()
    except Exception:
        nome = ''
    return nome or str(user)


def _agrupar_por_requisito(linhas):
    """Agrupa linhas por requisito, retornando lista de dicts com label e linhas."""
    grupos = {}
    for ln in linhas:
        req = getattr(ln.get('item'), 'requisito', None)
        req_key = getattr(req, 'pk', None)
        if req_key not in grupos:
            label = getattr(req, 'descricao_curta', '') or ''
            grupos[req_key] = {'requisito': req, 'label': label, 'linhas': [], 'subtotal_pontos': Decimal('0'), 'subtotal_itens': 0}
        grupos[req_key]['linhas'].append(ln)
        pontos = ln.get('pontuacao_total') or ln.get('total_pontos_requeridos_item') or Decimal('0')
        if pontos > 0:
            grupos[req_key]['subtotal_pontos'] += pontos
            grupos[req_key]['subtotal_itens'] += 1
    return [grupos[k] for k in sorted(grupos.keys(), key=lambda x: (x is None, x))]


def _requisitos_obrigatorios_do_nivel(nivel) -> list:
    """Requisitos obrigatórios (RN04) configurados no nível, ordenados por número ([] se não houver)."""
    try:
        return list(nivel.requisitos_obrigatorios.order_by('numero'))
    except Exception:
        logger.exception('Erro ao obter requisitos obrigatórios do nível %s', nivel)
        return []


def atende_requisitos_obrigatorios(nivel, ids_itens_pontuados, requisitos_obrigatorios=None) -> bool:
    """True se ao menos um item pontuado pertence aos requisitos obrigatórios do nível (RN04).

    Níveis sem requisito obrigatório configurado (I, II e III) sempre atendem. ``requisitos_obrigatorios``
    pode ser passado já resolvido para evitar rebuscá-los quando o chamador já os tem em mãos.
    """
    if requisitos_obrigatorios is None:
        requisitos_obrigatorios = _requisitos_obrigatorios_do_nivel(nivel)
    if not requisitos_obrigatorios:
        return True
    numeros_obrigatorios = {r.numero for r in requisitos_obrigatorios}
    return RolSaberCompetencia.objects.filter(
        id__in=list(ids_itens_pontuados),
        grupo__requisito__numero__in=numeros_obrigatorios,
    ).exists()


def _erro_requisitos_obrigatorios(processo: ProcessoRSCTae, itens_com_pontuacao_ids) -> str | None:
    """Mensagem de erro se os requisitos obrigatórios do nível (RN04) não forem atendidos, senão None.

    Para níveis IV, V e VI, ao menos um critério preenchido deve pertencer aos
    requisitos obrigatórios configurados no nível.
    """
    nivel = processo.nivel_requisitado
    requisitos_obrigatorios = _requisitos_obrigatorios_do_nivel(nivel)
    if not requisitos_obrigatorios:
        return None  # Nível sem requisito obrigatório (I, II, III)
    if atende_requisitos_obrigatorios(nivel, itens_com_pontuacao_ids):
        return None
    nomes = ', '.join(r.descricao_curta for r in requisitos_obrigatorios)
    return f'Para o nível {nivel.ordem_romana}, ao menos um critério deve pertencer a: {nomes}.'


def verificar_criterios_nivel(processo: ProcessoRSCTae, pontos_por_item: Mapping[int, Decimal]) -> dict:
    """Verifica os critérios do nível pretendido sobre os pontos POR ITEM já apurados.

    Fonte única dos critérios de deferimento nas fases de avaliação e deliberação:
    - pontuação mínima do nível, somando o saldo de concessão anterior (RN07);
    - número mínimo de itens com pontos > 0;
    - requisito obrigatório do nível (RN04) sobre os itens efetivamente pontuados.

    ``pontos_por_item``: {item_id: pontos validados/consolidados} — itens temporais já
    convertidos em anos pontuáveis por quem apurou os pontos.
    """
    nivel = processo.nivel_requisitado
    saldo_anterior = processo.saldo_pontuacao_anterior or Decimal('0')
    total_pontos_itens = sum(pontos_por_item.values(), Decimal('0'))
    total_pontos = total_pontos_itens + saldo_anterior

    ids_itens_pontuados = [item_id for item_id, pontos in pontos_por_item.items() if pontos > 0]
    itens_validados = len(ids_itens_pontuados)

    pontos_minimos = nivel.pontuacao_minima or Decimal('0')
    itens_minimos = int(nivel.numero_minimo_itens or 0)

    requisitos_obrigatorios = _requisitos_obrigatorios_do_nivel(nivel)
    atingiu_pontos = pontos_minimos <= 0 or total_pontos >= pontos_minimos
    atingiu_itens = itens_minimos <= 0 or itens_validados >= itens_minimos
    atingiu_requisito_obrigatorio = atende_requisitos_obrigatorios(nivel, ids_itens_pontuados, requisitos_obrigatorios)

    pontos_percent = 100.0
    if pontos_minimos > 0:
        pontos_percent = float(min(total_pontos / pontos_minimos, Decimal('1')) * Decimal('100'))

    return {
        'total_pontos': total_pontos,
        'total_pontos_itens': total_pontos_itens,
        'saldo_anterior': saldo_anterior,
        'itens_validados': itens_validados,
        'pontos_minimos': pontos_minimos,
        'itens_minimos': itens_minimos,
        'atingiu_pontos': atingiu_pontos,
        'atingiu_itens': atingiu_itens,
        'atingiu_requisito_obrigatorio': atingiu_requisito_obrigatorio,
        'labels_requisitos_obrigatorios': [r.descricao_curta for r in requisitos_obrigatorios],
        'requisito_obrigatorio_aplicavel': bool(requisitos_obrigatorios),
        'atende_todos': bool(atingiu_pontos and atingiu_itens and atingiu_requisito_obrigatorio),
        'pontos_percent': pontos_percent,
    }


def anexos_por_item(processo: ProcessoRSCTae, itens: Iterable[RolSaberCompetencia]) -> dict:
    """{item_id: [anexos do processo para o item]} para o resumo por pontos.

    Traz os objetos anexo (não só as unidades) porque a pontuação por papel
    (titular/substituto) depende de ``anexo.papel``.
    """
    resultado: dict = {}
    anexos = RolSaberCompetenciaAnexo.objects.filter(processo=processo, rol_saber_competencia__in=itens)
    for anexo in anexos:
        resultado.setdefault(anexo.rol_saber_competencia_id, []).append(anexo)
    return resultado


def _calcular_resumo_por_pontos(processo: ProcessoRSCTae, itens, preenchimento_por_item_id, anexos_por_item_id):
    """*anexos_por_item_id*: {item_id: [anexos do item]} — os pontos são somados por anexo,
    aplicando a taxa do papel (titular/substituto) e a conversão temporal em ``pontos_item_anexos``."""
    total_pontos_itens = Decimal('0')
    itens_preenchidos = 0
    for item in itens:
        anexos_do_item = anexos_por_item_id.get(item.id) or []
        soma_unidades_anexos = sum((getattr(a, 'pontuacao', None) or Decimal('0') for a in anexos_do_item), Decimal('0'))
        if soma_unidades_anexos > 0:
            pontos_item = pontos_item_anexos(item, anexos_do_item)
        else:
            quantidade = preenchimento_por_item_id.get(item.id).quantidade if item.id in preenchimento_por_item_id else 0
            pontos_item = (item.pontuacao_unidade or Decimal('0')) * Decimal(quantidade)

        if pontos_item > 0:
            itens_preenchidos += 1
        total_pontos_itens += pontos_item

    # RN07: saldo excedente de concessão anterior (Art. 3º, §2º) é somado à pontuação atual
    saldo_anterior = processo.saldo_pontuacao_anterior or Decimal('0')
    total_pontos = total_pontos_itens + saldo_anterior

    pontos_minimos = processo.nivel_requisitado.pontuacao_minima or Decimal('0')
    itens_minimos = processo.nivel_requisitado.numero_minimo_itens or 0

    if pontos_minimos and pontos_minimos > 0:
        pontos_percent = float(min(total_pontos / pontos_minimos, Decimal('1')) * Decimal('100'))
    else:
        pontos_percent = 0.0

    if itens_minimos and itens_minimos > 0:
        itens_percent = float(min(Decimal(itens_preenchidos) / Decimal(itens_minimos), Decimal('1')) * Decimal('100'))
    else:
        itens_percent = 0.0

    return {
        'total_pontos': total_pontos,
        'total_pontos_itens': total_pontos_itens,
        'saldo_anterior': saldo_anterior,
        'pontos_minimos': pontos_minimos,
        'pontos_percent': pontos_percent,
        'itens_preenchidos': itens_preenchidos,
        'itens_minimos': itens_minimos,
        'itens_percent': itens_percent,
    }


def _anexos_tem_problema(anexos_do_item) -> bool:
    """True se algum anexo do item está sem pontuação (0) ou sem descrição."""
    return any((getattr(a, 'pontuacao', None) or Decimal('0')) == 0 or not (getattr(a, 'descricao', '') or '').strip() for a in anexos_do_item)


def _montar_resumo_preenchimento(processo: ProcessoRSCTae):
    # Ordena por requisito e, dentro dele, pela numeração do item (Nº exibido).
    # O grupo é apenas categorização interna e não define a ordem de exibição.
    itens = RolSaberCompetencia.objects.filter(ativo=True).select_related('grupo__requisito').order_by('grupo__requisito__numero', 'numero')

    preenchimentos = RolSaberCompetenciaPreenchimento.objects.filter(
        vinculo=processo.vinculo,
        rol_saber_competencia__in=itens,
    )
    preenchimento_por_item_id = {p.rol_saber_competencia_id: p for p in preenchimentos}

    anexos = RolSaberCompetenciaAnexo.objects.filter(processo=processo, rol_saber_competencia__in=itens)
    anexos_por_item_id = {}
    for a in anexos:
        anexos_por_item_id.setdefault(a.rol_saber_competencia_id, []).append(a)

    unidades_anexos_por_item_id = {}
    for item_id, anexos_do_item in anexos_por_item_id.items():
        unidades_anexos_por_item_id[item_id] = [(getattr(a, 'pontuacao', None) or Decimal('0')) for a in anexos_do_item]

    linhas = []
    problema_preenchimento_geral = False
    for item in itens:
        quantidade = preenchimento_por_item_id.get(item.id).quantidade if item.id in preenchimento_por_item_id else 0
        unidades_anexos = unidades_anexos_por_item_id.get(item.id) or []
        soma_unidades_anexos = sum(unidades_anexos, Decimal('0'))
        pontuacao_total = (
            pontos_item_anexos(item, anexos_por_item_id.get(item.id, []))
            if soma_unidades_anexos > 0
            else (item.pontuacao_unidade or Decimal('0')) * Decimal(quantidade)
        )

        anexos_do_item = anexos_por_item_id.get(item.id, [])
        tem_anexos = len(anexos_do_item) > 0
        tem_pontuacao = pontuacao_total > 0
        # Para item temporal, um anexo com período válido pode arredondar para 0 ano pontuável
        # ('ano ou fração > 6 meses') e ainda estar completo. Usa as unidades declaradas nos
        # anexos (meses/quantidade), não o total já arredondado, para detectar arquivo sem dados.
        anexos_com_unidades = soma_unidades_anexos > 0
        mismatch = (tem_pontuacao and not tem_anexos) or (tem_anexos and not anexos_com_unidades)

        # Item com problema no resumo: anexo sem pontuação OU sem descrição.
        problema_preenchimento = tem_anexos and _anexos_tem_problema(anexos_do_item)
        if mismatch or problema_preenchimento:
            problema_preenchimento_geral = True

        quantidade_efetiva = unidades_pontuaveis_anexos(item, unidades_anexos) if soma_unidades_anexos > 0 else Decimal(quantidade)

        linhas.append(
            {
                'item': item,
                'quantidade': quantidade,
                'quantidade_efetiva': quantidade_efetiva,
                'pontuacao_total': pontuacao_total,
                'anexos': anexos_do_item,
                'problema_preenchimento': problema_preenchimento,
            }
        )

    linhas_preenchidas = [ln for ln in linhas if ln.get('quantidade') or ln.get('anexos')]
    resumo_preenchimento_total_itens = len(linhas_preenchidas)
    resumo_preenchimento_total_pontos = sum((ln.get('pontuacao_total') or Decimal('0')) for ln in linhas_preenchidas)

    grupos_requisito = _agrupar_por_requisito(linhas_preenchidas)

    resumo_pontos = _calcular_resumo_por_pontos(processo, itens, preenchimento_por_item_id, anexos_por_item_id)

    return {
        'linhas': linhas,
        'linhas_preenchidas': linhas_preenchidas,
        'grupos_requisito': grupos_requisito,
        'resumo_preenchimento_total_itens': resumo_preenchimento_total_itens,
        'resumo_preenchimento_total_pontos': resumo_preenchimento_total_pontos,
        'problema_preenchimento_geral': problema_preenchimento_geral,
        **resumo_pontos,
    }


def _validar_acesso_resumo_avaliacao(request, processo: ProcessoRSCTae):
    user = request.user

    try:
        vinculo_usuario = user.get_vinculo()
    except Exception:
        logger.exception('Não foi possível obter o vínculo do usuário %s', user)
        vinculo_usuario = None

    # O dono do processo pode visualizar o resumo da própria avaliação.
    if vinculo_usuario and getattr(processo, 'vinculo_id', None) == getattr(vinculo_usuario, 'id', None):
        return

    if user.has_perm('rh.eh_rh_sistemico'):
        return

    if not user.has_perm('rsc_tae.avaliar_processorsctae'):
        raise PermissionDenied('Permissão negada.')

    if not vinculo_usuario:
        raise PermissionDenied('Permissão negada.')

    # Novo fluxo: qualquer avaliador designado pode visualizar
    try:
        if processo.avaliadores.filter(id=vinculo_usuario.id).exists():
            return
    except Exception:
        logger.exception('Erro ao verificar avaliadores do processo %s para o usuário %s', processo.pk, user)

    # Fallback para processos antigos
    avaliador_atual = getattr(processo, 'avaliador_atual', None)
    if not avaliador_atual or int(getattr(avaliador_atual, 'id', 0) or 0) != int(getattr(vinculo_usuario, 'id', 0) or 0):
        raise PermissionDenied('Apenas o avaliador atual pode visualizar o resumo da avaliação.')


def _montar_contexto_avaliacao(request, processo: ProcessoRSCTae, title: str):
    try:
        vinculo_usuario = request.user.get_vinculo()
    except Exception:
        logger.exception('Não foi possível obter o vínculo do usuário %s', request.user)
        vinculo_usuario = None
    eh_dono = bool(vinculo_usuario and getattr(processo, 'vinculo_id', None) == getattr(vinculo_usuario, 'id', None))

    # Identifica qual avaliação (de qual avaliador) será exibida neste contexto.
    avaliador_contexto = None
    if (
        vinculo_usuario
        and request.user.has_perm('rsc_tae.avaliar_processorsctae')
        and getattr(processo, 'situacao', None) in SituacaoProcesso.AVALIAVEIS
    ):
        try:
            if processo.avaliadores.filter(id=vinculo_usuario.id).exists():
                avaliador_contexto = vinculo_usuario
        except Exception:
            logger.exception('Erro ao verificar avaliadores do processo %s', processo.pk)
            avaliador_contexto = None

        if not avaliador_contexto:
            # Fallback: processo antigo
            if int(getattr(processo, 'avaliador_atual_id', 0) or 0) == int(getattr(vinculo_usuario, 'id', 0) or 0):
                avaliador_contexto = vinculo_usuario

    if not avaliador_contexto:
        # Para dono/RH, exibe a primeira avaliação disponível (se houver)
        try:
            avaliador_contexto = processo.avaliadores.all().order_by('pessoa__nome').first()
        except Exception:
            logger.exception('Erro ao buscar avaliadores do processo %s', processo.pk)
            avaliador_contexto = None
        if not avaliador_contexto:
            avaliador_contexto = getattr(processo, 'avaliador_atual', None)

    avaliacao_processo = None
    avaliacao_finalizada = False
    if avaliador_contexto:
        try:
            avaliacao_processo, _ = AvaliacaoProcessoRSCTae.objects.get_or_create(processo=processo, avaliador_vinculo=avaliador_contexto)
            avaliacao_finalizada = bool(getattr(avaliacao_processo, 'finalizada', False))
        except Exception:
            logger.exception('Erro ao obter/criar AvaliacaoProcessoRSCTae para o processo %s e avaliador %s', processo.pk, avaliador_contexto)
            avaliacao_processo = None
            avaliacao_finalizada = False

    situacao_permite_avaliar = getattr(processo, 'situacao', None) == SituacaoProcesso.EM_ANALISE

    pode_avaliar_anexos = bool(
        (not eh_dono)
        and request.user.has_perm('rsc_tae.avaliar_processorsctae')
        and situacao_permite_avaliar
        and avaliador_contexto
        and vinculo_usuario
        and int(getattr(avaliador_contexto, 'id', 0) or 0) == int(getattr(vinculo_usuario, 'id', 0) or 0)
        and (not avaliacao_finalizada)
    )

    ctx = _montar_resumo_preenchimento(processo)
    linhas_preenchidas = ctx['linhas_preenchidas']

    avaliacoes_anexo_qs = AvaliacaoAnexoRSCTae.objects.filter(anexo__processo=processo)
    if avaliador_contexto:
        avaliacoes_anexo_qs = avaliacoes_anexo_qs.filter(avaliador_vinculo=avaliador_contexto)
    else:
        avaliacoes_anexo_qs = avaliacoes_anexo_qs.none()

    avaliacoes_anexo = avaliacoes_anexo_qs.select_related('anexo', 'avaliado_por', 'avaliador_vinculo')
    avaliacao_anexo_por_id = {a.anexo_id: a for a in avaliacoes_anexo}

    # Determina se todas as avaliações são visíveis a todos (sem filtro por avaliador)
    processo_finalizado = processo.situacao in (*SituacaoProcesso.FINAIS, SituacaoProcesso.AGUARDANDO_CRSC)

    # Busca avaliações para o detalhamento multi-avaliador.
    # Se o processo NÃO está finalizado, avaliador só vê a própria avaliação.
    todas_avaliacoes_anexo_qs = (
        AvaliacaoAnexoRSCTae.objects.filter(anexo__processo=processo)
        .select_related('anexo', 'avaliado_por', 'avaliador_vinculo', 'avaliador_vinculo__pessoa')
        .order_by('avaliador_vinculo__pessoa__nome')
    )
    if not processo_finalizado and vinculo_usuario and not eh_dono:
        # Avaliador em análise: só vê a própria
        eh_avaliador = False
        try:
            eh_avaliador = processo.avaliadores.filter(id=vinculo_usuario.id).exists()
        except Exception:
            logger.exception('Erro ao verificar avaliadores do processo %s', processo.pk)
        if not eh_avaliador:
            eh_avaliador = int(getattr(processo, 'avaliador_atual_id', 0) or 0) == int(getattr(vinculo_usuario, 'id', 0) or 0)
        if eh_avaliador:
            todas_avaliacoes_anexo_qs = todas_avaliacoes_anexo_qs.filter(avaliador_vinculo=vinculo_usuario)

    todas_avaliacoes_por_anexo_id = {}
    for av in todas_avaliacoes_anexo_qs:
        todas_avaliacoes_por_anexo_id.setdefault(av.anexo_id, []).append(av)

    avaliadores = []
    try:
        avaliadores_vinculos = list(processo.avaliadores.all().select_related('pessoa').order_by('pessoa__nome'))
    except Exception:
        logger.exception('Erro ao listar avaliadores do processo %s', processo.pk)
        avaliadores_vinculos = []
    if not avaliadores_vinculos:
        av_atual = getattr(processo, 'avaliador_atual', None)
        if av_atual:
            avaliadores_vinculos = [av_atual]
    avaliadores = [str(v) for v in avaliadores_vinculos]
    tem_multiplos_avaliadores = len(avaliadores_vinculos) > 1

    for ln in linhas_preenchidas:
        for anexo in ln.get('anexos') or []:
            avaliacao_anexo = avaliacao_anexo_por_id.get(anexo.id)
            anexo.avaliacao_anexo = avaliacao_anexo
            anexo.ja_avaliado = bool(
                avaliacao_anexo and avaliacao_anexo.situacao in (SituacaoAvaliacaoItem.DEFERIDO, SituacaoAvaliacaoItem.INDEFERIDO)
            )

            # Taxa por papel do próprio anexo (titular/substituto); itens sem papel usam a taxa única.
            taxa = taxa_por_papel(ln.get('item'), getattr(anexo, 'papel', None))
            unidades_requeridas = getattr(anexo, 'pontuacao', None) or Decimal('0')
            if avaliacao_anexo and avaliacao_anexo.situacao == SituacaoAvaliacaoItem.DEFERIDO:
                unidades_validadas = avaliacao_anexo.pontuacao_validada or Decimal('0')
            else:
                unidades_validadas = Decimal('0')

            anexo.pontos_requeridos = taxa * unidades_requeridas
            anexo.pontos_validados = taxa * unidades_validadas

            # Avaliações de todos os avaliadores para este anexo
            avaliacoes_do_anexo = todas_avaliacoes_por_anexo_id.get(anexo.id, [])
            for av_todos in avaliacoes_do_anexo:
                av_todos.pontos_requeridos_calc = taxa * unidades_requeridas
                if av_todos.situacao == SituacaoAvaliacaoItem.DEFERIDO:
                    av_todos.pontos_validados_calc = taxa * (av_todos.pontuacao_validada or Decimal('0'))
                else:
                    av_todos.pontos_validados_calc = Decimal('0')
            anexo.avaliacoes_todos = avaliacoes_do_anexo

    linhas_avaliacao = []
    for ln in linhas_preenchidas:
        anexos_do_item = ln.get('anexos') or []
        pontuacao_unidade = getattr(ln.get('item'), 'pontuacao_unidade', None) or Decimal('0')
        total_pontos_requeridos_item = sum((getattr(a, 'pontos_requeridos', None) or Decimal('0')) for a in anexos_do_item)
        total_pontos_validados_item = sum((getattr(a, 'pontos_validados', None) or Decimal('0')) for a in anexos_do_item)
        linhas_avaliacao.append(
            {
                **ln,
                'pontuacao_unidade': pontuacao_unidade,
                'total_pontos_requeridos_item': total_pontos_requeridos_item,
                'total_pontos_validados_item': total_pontos_validados_item,
            }
        )
    total_pontos_validados = sum((_ln.get('total_pontos_validados_item') or Decimal('0')) for _ln in linhas_avaliacao)

    itens_requeridos = int(getattr(processo.nivel_requisitado, 'numero_minimo_itens', 0) or 0)
    itens_validados = sum(1 for _ln in linhas_avaliacao if (_ln.get('total_pontos_validados_item') or Decimal('0')) > 0)

    pontos_requeridos_nivel = getattr(processo.nivel_requisitado, 'pontuacao_minima', None) or Decimal('0')

    anexos_total = 0
    anexos_deferidos = 0
    anexos_indeferidos = 0
    anexos_pendentes = 0
    itens_pendentes_lista = []
    for ln in linhas_avaliacao:
        anexos_do_item = ln.get('anexos') or []
        anexos_total += len(anexos_do_item)

        item_tem_pendente = False
        pendentes_no_item = 0
        for a in anexos_do_item:
            av = getattr(a, 'avaliacao_anexo', None)
            if av and av.situacao == SituacaoAvaliacaoItem.DEFERIDO:
                anexos_deferidos += 1
            elif av and av.situacao == SituacaoAvaliacaoItem.INDEFERIDO:
                anexos_indeferidos += 1
            else:
                anexos_pendentes += 1
                item_tem_pendente = True
                pendentes_no_item += 1

        if item_tem_pendente and anexos_do_item:
            try:
                item_label = str(getattr(ln.get('item'), 'titulo', None) or ln.get('item'))
            except Exception:
                item_label = 'Item'
            itens_pendentes_lista.append({'item': ln.get('item'), 'label': item_label, 'pendentes': pendentes_no_item})

    atingiu_pontos = (not pontos_requeridos_nivel or pontos_requeridos_nivel <= 0) or (total_pontos_validados >= pontos_requeridos_nivel)
    atingiu_itens = (not itens_requeridos or itens_requeridos <= 0) or (itens_validados >= itens_requeridos)
    resultado_parcial_deferido = bool(atingiu_pontos and atingiu_itens)

    if pontos_requeridos_nivel and pontos_requeridos_nivel > 0:
        pontos_percent = float(min(total_pontos_validados / pontos_requeridos_nivel, Decimal('1')) * Decimal('100'))
    else:
        pontos_percent = 0.0
    if itens_requeridos and itens_requeridos > 0:
        itens_percent = float(min(Decimal(itens_validados) / Decimal(itens_requeridos), Decimal('1')) * Decimal('100'))
    else:
        itens_percent = 0.0

    grupos_requisito_avaliacao = _agrupar_por_requisito(linhas_avaliacao)

    # Detalhamento por avaliador: todos os registros (ativos + histórico)
    todas_avaliacoes_proc_qs = (
        AvaliacaoProcessoRSCTae.objects.filter(processo=processo)
        .select_related('avaliador_vinculo', 'avaliador_vinculo__pessoa')
        .order_by('substituido', 'avaliador_vinculo__pessoa__nome')
    )
    # Se o processo NÃO está finalizado, avaliador só vê o próprio resultado
    if not processo_finalizado and vinculo_usuario and not eh_dono:
        eh_avaliador_proc = False
        try:
            eh_avaliador_proc = processo.avaliadores.filter(id=vinculo_usuario.id).exists()
        except Exception:
            logger.exception('Erro ao verificar avaliadores do processo %s', processo.pk)
        if not eh_avaliador_proc:
            eh_avaliador_proc = int(getattr(processo, 'avaliador_atual_id', 0) or 0) == int(getattr(vinculo_usuario, 'id', 0) or 0)
        if eh_avaliador_proc:
            todas_avaliacoes_proc_qs = todas_avaliacoes_proc_qs.filter(avaliador_vinculo=vinculo_usuario)

    todas_avaliacoes_proc = list(todas_avaliacoes_proc_qs)

    # Avaliadores que contam para o resultado: não substituídos
    avaliacoes_ativas = [a for a in todas_avaliacoes_proc if not a.substituido]
    # Histórico auditável: substituídos (recusaram, declararam impedimento ou foram remanejados)
    avaliacoes_substituidas = [a for a in todas_avaliacoes_proc if a.substituido]

    # Cálculo de deferimento: APENAS avaliadores ativos (não substituídos)
    total_avaliacoes_finalizadas = sum(1 for a in avaliacoes_ativas if a.finalizada)
    total_deferidos = sum(1 for a in avaliacoes_ativas if a.finalizada and a.resultado == SituacaoProcesso.DEFERIDO)
    total_indeferidos = total_avaliacoes_finalizadas - total_deferidos
    resultado_processo_por_maioria = None
    if total_avaliacoes_finalizadas > 0:
        resultado_processo_por_maioria = bool(total_deferidos * 2 >= total_avaliacoes_finalizadas)

    return {
        'title': title,
        'processo': processo,
        'avaliadores': avaliadores,
        'avaliador_contexto': avaliador_contexto,
        'avaliacao_finalizada': avaliacao_finalizada,
        'pode_avaliar_anexos': pode_avaliar_anexos,
        'linhas_avaliacao': linhas_avaliacao,
        'grupos_requisito_avaliacao': grupos_requisito_avaliacao,
        'total_pontos_validados': total_pontos_validados,
        'pontos_requeridos_nivel': pontos_requeridos_nivel,
        'itens_requeridos': itens_requeridos,
        'itens_validados': itens_validados,
        'pontos_percent': pontos_percent,
        'itens_percent': itens_percent,
        'anexos_total': anexos_total,
        'anexos_deferidos': anexos_deferidos,
        'anexos_indeferidos': anexos_indeferidos,
        'anexos_pendentes': anexos_pendentes,
        'itens_pendentes_lista': itens_pendentes_lista,
        'resultado_parcial_deferido': resultado_parcial_deferido,
        'avaliacoes_ativas': avaliacoes_ativas,
        'avaliacoes_substituidas': avaliacoes_substituidas,
        'total_avaliacoes_finalizadas': total_avaliacoes_finalizadas,
        'total_deferidos': total_deferidos,
        'total_indeferidos': total_indeferidos,
        'resultado_processo_por_maioria': resultado_processo_por_maioria,
        'tem_multiplos_avaliadores': tem_multiplos_avaliadores,
        'RESPOSTA_ACEITE': AvaliacaoProcessoRSCTae.RESPOSTA_ACEITE,
        'RESPOSTA_RECUSA': AvaliacaoProcessoRSCTae.RESPOSTA_RECUSA,
        'RESPOSTA_IMPEDIMENTO': AvaliacaoProcessoRSCTae.RESPOSTA_IMPEDIMENTO,
    }


def quantidade_deliberacoes_item() -> int:
    """Quantidade de deliberações de membros necessárias para consolidar um item (config; default 4)."""
    from rsc_tae.models import ConfiguracaoRSCTae

    config = ConfiguracaoRSCTae.objects.first()
    return int(getattr(config, 'quantidade_deliberacoes_item', 0) or 4)


# Cota de deliberações por categoria da comissão (regra interna do IFRN). O limite é configurado na
# tela Configurações > Rsc_tae — o NOME do campo em `rsc_tae.forms._ConfiguracaoRSCTaeBase` é esta
# chave, então renomear um dos dois órfã a configuração gravada.
CHAVE_LIMITE_POR_CATEGORIA = 'limite_deliberacoes_por_categoria'
LIMITE_POR_CATEGORIA_PADRAO = 2


def limite_deliberacoes_por_categoria() -> int:
    """Máximo de deliberações que uma categoria da comissão gasta em cada escopo de votação.

    Lido da tela de Configurações do SUAP (``comum.Configuracao``, app ``rsc_tae``). Em branco,
    não numérico ou menor que 1 vale o padrão — zero pararia a comissão inteira.

    Returns:
        O limite por categoria, nunca menor que 1.
    """
    from comum.models import Configuracao

    valor = (Configuracao.get_valor_por_chave('rsc_tae', CHAVE_LIMITE_POR_CATEGORIA) or '').strip()
    try:
        limite = int(valor)
    except ValueError:
        return LIMITE_POR_CATEGORIA_PADRAO
    return limite if limite >= 1 else LIMITE_POR_CATEGORIA_PADRAO


def categoria_por_vinculo() -> dict[int, int | None]:
    """``{vinculo_id: categoria_id}`` dos membros ATIVOS da comissão ATIVA (uma consulta).

    Quem não aparece no mapa não é membro elegível e, por isso, não delibera.
    """
    from rsc_tae.models import MembroComissaoRSCTae

    return dict(MembroComissaoRSCTae.objects.filter(comissao__ativa=True, ativo=True).values_list('vinculo_id', 'categoria_id'))


def votos_que_consomem_cota(votos, vinculo_id: int | None, categoria_id: int, categorias: dict[int, int | None]) -> list:
    """Votos do escopo que gastam a cota da categoria, na ótica de ``vinculo_id``.

    Ficam de fora o voto de desempate (prerrogativa do presidente) e o voto do próprio membro, que
    segue podendo revisá-lo. É a regra de contagem usada tanto pela trava quanto pelo painel de
    pendências — uma só, para os dois não divergirem.

    Args:
        votos: Votos já registrados no escopo.
        vinculo_id: Vínculo de quem quer votar (o próprio voto não conta).
        categoria_id: Categoria desse vínculo na comissão ativa.
        categorias: Mapa ``{vinculo_id: categoria_id}`` de ``categoria_por_vinculo``.

    Returns:
        Os votos que consomem a cota.
    """
    return [
        voto
        for voto in votos
        if not getattr(voto, 'desempate', False)
        and voto.deliberado_por_vinculo_id != vinculo_id
        and categorias.get(voto.deliberado_por_vinculo_id) == categoria_id
    ]


def _nome_do_votante(voto) -> str:
    """Nome de quem assinou o voto, para explicar ao bloqueado quem gastou a cota."""
    pessoa = getattr(voto.deliberado_por_vinculo, 'pessoa', None)
    return str(getattr(pessoa, 'nome', '') or voto.deliberado_por_vinculo)


def status_cota_categoria(votos, vinculo, limite: int | None = None) -> dict:
    """Situação da cota da categoria de ``vinculo`` dentro de UM escopo de votação.

    O escopo é definido por quem chama, passando a lista de votos correspondente: os votos de um
    anexo divergente, ou os votos da deliberação final. Os contadores são independentes — estourar
    a cota num item não impede a categoria de votar na deliberação final.

    Não consomem cota: o voto de desempate do presidente (prerrogativa do cargo, e contá-lo
    deixaria empate sem saída) e o voto do próprio ``vinculo`` (que segue podendo revisá-lo).

    Args:
        votos: Votos já registrados no escopo (``DeliberacaoItemCRSCRSCTae`` ou ``VotoDeliberacaoFinalRSCTae``).
        vinculo: Vínculo do membro que quer votar.
        limite: Limite por categoria; ``None`` lê da configuração.

    Returns:
        ``{'categoria', 'usados', 'limite', 'bloqueado', 'motivo', 'nomes_que_usaram'}``.
    """
    from rsc_tae.models import CategoriaMembroComissaoRSCTae

    limite = limite_deliberacoes_por_categoria() if limite is None else limite
    categorias = categoria_por_vinculo()
    vinculo_id = getattr(vinculo, 'id', None)
    categoria_id = categorias.get(vinculo_id)

    if not categoria_id:
        return {
            'categoria': None,
            'usados': 0,
            'limite': limite,
            'bloqueado': True,
            'motivo': 'Seu cadastro na comissão está sem categoria — o RH precisa definir a categoria antes de você deliberar.',
            'nomes_que_usaram': [],
        }

    da_categoria = votos_que_consomem_cota(votos, vinculo_id, categoria_id, categorias)
    nomes = [_nome_do_votante(voto) for voto in da_categoria]
    categoria = CategoriaMembroComissaoRSCTae.objects.filter(pk=categoria_id).first()
    usados = len(da_categoria)
    bloqueado = usados >= limite
    motivo = ''
    if bloqueado:
        motivo = f'A categoria {categoria} já utilizou as {limite} deliberações a que tem direito aqui ({", ".join(sorted(nomes))}).'

    return {
        'categoria': categoria,
        'usados': usados,
        'limite': limite,
        'bloqueado': bloqueado,
        'motivo': motivo,
        'nomes_que_usaram': nomes,
    }


def consolidar_pontuacao_votos(votos):
    """Nota consolidada pela maioria: pontuação mais votada (moda); em caso de empate, a maior. None se sem votos.

    Usada na deliberação FINAL, onde a pontuação é secundária ao resultado (deferido/indeferido).
    """
    from collections import Counter

    if not votos:
        return None
    contagem = Counter(v.pontuacao_efetiva for v in votos)
    maior_freq = max(contagem.values())
    candidatos = [pontuacao for pontuacao, freq in contagem.items() if freq == maior_freq]
    return max(candidatos)


def consolidar_nota_item(votos):
    """(nota, empatado) do item: pontuação mais votada (moda) e se a moda empata (mais de um valor).

    Diferente de ``consolidar_pontuacao_votos``, NÃO resolve empate pela maior — sinaliza para
    exigir o voto de desempate do presidente. Retorna ``(None, False)`` quando não há votos.
    """
    from collections import Counter

    if not votos:
        return None, False
    contagem = Counter(v.pontuacao_efetiva for v in votos)
    maior_freq = max(contagem.values())
    candidatos = [pontuacao for pontuacao, freq in contagem.items() if freq == maior_freq]
    if len(candidatos) > 1:
        return None, True
    return candidatos[0], False


def eh_presidente(vinculo) -> bool:
    """True se o vínculo é presidente da comissão ativa (membro ativo com ``presidente=True``)."""
    if not vinculo:
        return False
    from rsc_tae.models import MembroComissaoRSCTae

    return MembroComissaoRSCTae.objects.filter(comissao__ativa=True, ativo=True, presidente=True, vinculo=vinculo).exists()


def eh_membro_crsc_ativo(vinculo) -> bool:
    """True se o vínculo é membro ATIVO da comissão ATIVA (elegível a ações/privilégios da CRSC).

    Um membro inativo (ou de comissão inativa) fica impedido de qualquer ação da comissão, mesmo
    mantendo a permissão de grupo ``comum.is_membro_crsc_tae`` (concedida a quem tem registro).
    """
    if not vinculo:
        return False
    from rsc_tae.models import MembroComissaoRSCTae

    return MembroComissaoRSCTae.objects.filter(comissao__ativa=True, ativo=True, vinculo=vinculo).exists()


def status_deliberacao_item(votos, quantidade_necessaria) -> dict:
    """Resumo da votação de um item, contando quórum/maioria só com votos normais.

    Ao atingir o quórum: se a moda for única, fecha com ela; se empatar, usa o voto de desempate
    do presidente (se houver), senão fica ``aguardando_desempate`` e NÃO fecha.
    """
    normais = [v for v in votos if not getattr(v, 'desempate', False)]
    desempates = [v for v in votos if getattr(v, 'desempate', False)]
    voto_desempate = desempates[-1] if desempates else None

    total = len(normais)
    quorum = total >= quantidade_necessaria
    nota_maioria, empatado = consolidar_nota_item(normais)

    fechado = False
    nota = None
    aguardando_desempate = False
    if quorum and not empatado:
        fechado, nota = True, nota_maioria
    elif quorum and voto_desempate is not None:
        fechado, nota = True, voto_desempate.pontuacao_efetiva
    elif quorum:
        aguardando_desempate = True

    return {
        'total': total,
        'quantidade_necessaria': quantidade_necessaria,
        'quorum': quorum,
        'fechado': fechado,
        'empatado': empatado,
        'aguardando_desempate': aguardando_desempate,
        'nota_consolidada': nota,
        'voto_desempate': voto_desempate,
    }


def _resolver_resultado_final(quorum, deferidos, indeferidos, voto_desempate):
    """(resultado, decidido_por_desempate, aguardando_desempate) da deliberação final por maioria simples."""
    if not quorum:
        return None, False, False
    if deferidos > indeferidos:
        return SituacaoProcesso.DEFERIDO, False, False
    if indeferidos > deferidos:
        return SituacaoProcesso.INDEFERIDO, False, False
    if voto_desempate is not None:
        return voto_desempate.resultado, True, False
    return None, False, True


def status_deliberacao_final(votos, quantidade_necessaria) -> dict:
    """Placar da deliberação final, contando quórum/maioria só com votos normais.

    Maioria simples decide; em empate usa o voto de desempate do presidente, senão fica
    ``aguardando_desempate`` e NÃO fecha.
    """
    normais = [v for v in votos if not getattr(v, 'desempate', False)]
    desempates = [v for v in votos if getattr(v, 'desempate', False)]
    voto_desempate = desempates[-1] if desempates else None

    total = len(normais)
    deferidos = sum(1 for v in normais if v.resultado == SituacaoProcesso.DEFERIDO)
    indeferidos = total - deferidos
    quorum = total >= quantidade_necessaria

    resultado, decidido_por_desempate, aguardando_desempate = _resolver_resultado_final(quorum, deferidos, indeferidos, voto_desempate)
    fechado = resultado is not None

    if not fechado:
        pontuacao = None
    elif decidido_por_desempate:
        pontuacao = voto_desempate.pontuacao_efetiva
    else:
        pontuacao = consolidar_pontuacao_votos(normais)

    return {
        'total': total,
        'quantidade_necessaria': quantidade_necessaria,
        'deferidos': deferidos,
        'indeferidos': indeferidos,
        'quorum': quorum,
        'fechado': fechado,
        'resultado': resultado,
        'empate': aguardando_desempate,
        'aguardando_desempate': aguardando_desempate,
        'decidido_por_desempate': decidido_por_desempate,
        'pontuacao_consolidada': pontuacao,
        'voto_desempate': voto_desempate,
    }


def aplicar_notas_consolidadas_crsc(ctx_avaliacao, divergencias) -> None:
    """Substitui, no contexto de avaliação, os pontos validados dos anexos já consolidados pela CRSC e recalcula o total.

    A nota consolidada (unidades, pela maioria) passa a valer no total exibido na deliberação.
    """
    nota_por_anexo = {
        d['anexo'].id: d['status_deliberacao']['nota_consolidada']
        for d in divergencias
        if d['status_deliberacao']['fechado'] and d['status_deliberacao']['nota_consolidada'] is not None
    }
    if not nota_por_anexo:
        return

    linhas = ctx_avaliacao.get('linhas_avaliacao') or []
    for ln in linhas:
        item = ln.get('item')
        for anexo in ln.get('anexos') or []:
            if anexo.id in nota_por_anexo:
                taxa = taxa_por_papel(item, getattr(anexo, 'papel', None))
                anexo.pontos_validados = (nota_por_anexo[anexo.id] or Decimal('0')) * taxa
                anexo.consolidado_crsc = True
        ln['total_pontos_validados_item'] = sum((getattr(a, 'pontos_validados', None) or Decimal('0')) for a in (ln.get('anexos') or []))
    ctx_avaliacao['total_pontos_validados'] = sum((ln.get('total_pontos_validados_item') or Decimal('0')) for ln in linhas)


def _pontos_finais_por_item(processo: ProcessoRSCTae, consolidado_por_anexo: dict) -> dict:
    """Soma, por item, os pontos finais do processo na visão da CRSC.

    Reúne as UNIDADES de cada anexo (declaradas em ``anexo.pontuacao``, ou a nota consolidada
    pela comissão nos anexos divergentes já fechados) e converte em pontos via
    ``unidades_pontuaveis_anexos`` — que, para item temporal, faz meses->anos ('ano ou fração
    > 6 meses') POR PERÍODO antes de somar. Assim o total bate com o resumo da avaliação.
    """
    from collections import defaultdict

    # {item_id: [(unidades, papel), ...]} — o papel do anexo define a taxa (titular/substituto).
    unidades_por_item: dict = defaultdict(list)
    item_por_id: dict = {}
    anexos = RolSaberCompetenciaAnexo.objects.filter(processo=processo).select_related('rol_saber_competencia')
    for anexo in anexos:
        item = anexo.rol_saber_competencia
        item_por_id[item.id] = item
        if anexo.id in consolidado_por_anexo:
            unidades = consolidado_por_anexo[anexo.id] or Decimal('0')
        else:
            unidades = getattr(anexo, 'pontuacao', None) or Decimal('0')
        unidades_por_item[item.id].append((unidades, getattr(anexo, 'papel', None)))

    pontos_por_item: dict = {}
    for item_id, unidades_papeis in unidades_por_item.items():
        item = item_por_id[item_id]
        pontos_por_item[item_id] = sum((pontos_anexo(item, unidades, papel) for unidades, papel in unidades_papeis), Decimal('0'))
    return pontos_por_item


def resumo_final_consolidado(processo: ProcessoRSCTae, divergencias) -> dict:
    """Nota final do processo já com as notas consolidadas das deliberações de item aplicadas.

    Calcula direto dos anexos do processo (independente de avaliador logado): itens sem divergência
    contam com a pontuação declarada (já validada por padrão) e itens divergentes consolidados usam
    a nota da comissão. Aplica os critérios do nível via ``verificar_criterios_nivel`` — pontuação
    mínima com saldo anterior (RN07), itens mínimos e requisito obrigatório (RN04). Serve para
    nortear a decisão dos membros na deliberação final e trava o voto de deferimento quando
    ``deferido`` é False.
    """
    consolidado_por_anexo = {
        d['anexo'].id: d['status_deliberacao']['nota_consolidada']
        for d in divergencias
        if d['status_deliberacao']['fechado'] and d['status_deliberacao']['nota_consolidada'] is not None
    }

    pontos_por_item = _pontos_finais_por_item(processo, consolidado_por_anexo)
    criterios = verificar_criterios_nivel(processo, pontos_por_item)

    # Solicitado = pontuação declarada pelo servidor (sem aplicar nenhuma consolidação), para comparar.
    total_solicitado = sum(_pontos_finais_por_item(processo, {}).values(), Decimal('0'))

    return {
        **criterios,
        'pontos_requeridos': criterios['pontos_minimos'],
        'itens_requeridos': criterios['itens_minimos'],
        'total_solicitado': total_solicitado,
        'deferido': criterios['atende_todos'],
        'itens_consolidados': len(consolidado_por_anexo),
        'total_divergencias': len(divergencias),
    }


def _listar_divergencias_para_crsc(processo: ProcessoRSCTae) -> list[dict]:
    """Retorna lista de divergências entre o declarado pelo avaliado e o verificado pelos avaliadores.

    Uma divergência existe quando, para um dado anexo do processo:
    - Ao menos um avaliador o indeferiu, OU
    - Ao menos um avaliador alterou a pontuação validada (pontuacao_validada ≠ pontuacao), OU
    - Os avaliadores discordam entre si (um defere, outro indefere).

    Cada item retornado é um dict com:
        'item'            - RolSaberCompetencia
        'requisito'       - Requisito
        'anexo'           - RolSaberCompetenciaAnexo (com .pontuacao declarada)
        'avaliacoes'      - lista de AvaliacaoAnexoRSCTae (todos os avaliadores)
        'tem_indeferido'  - bool: algum avaliador indeferiu
        'tem_deferido'    - bool: algum avaliador deferiu
        'pontuacao_alterada' - bool: algum avaliador mudou a pontuação validada
        'desacordo_avaliadores' - bool: avaliadores discordam entre si
        'deliberacao_crsc' - DeliberacaoItemCRSCRSCTae ou None (decisão já registrada pela CRSC)
    """

    anexos = (
        RolSaberCompetenciaAnexo.objects.filter(processo=processo)
        .select_related('rol_saber_competencia__grupo__requisito')
        .order_by('rol_saber_competencia__grupo__requisito__numero', 'rol_saber_competencia__grupo__numero', 'rol_saber_competencia__numero', 'id')
    )

    avaliacoes_qs = (
        AvaliacaoAnexoRSCTae.objects.filter(
            anexo__processo=processo,
            avaliador_vinculo__isnull=False,
        )
        .select_related('avaliador_vinculo__pessoa')
        .order_by('avaliador_vinculo__pessoa__nome')
    )
    avaliacoes_por_anexo: dict[int, list] = {}
    for av in avaliacoes_qs:
        avaliacoes_por_anexo.setdefault(av.anexo_id, []).append(av)

    deliberacoes_qs = (
        DeliberacaoItemCRSCRSCTae.objects.filter(processo=processo).select_related('deliberado_por_vinculo__pessoa').order_by('data_deliberacao')
    )
    votos_por_anexo: dict[int, list] = {}
    for d in deliberacoes_qs:
        votos_por_anexo.setdefault(d.anexo_id, []).append(d)
    quantidade_necessaria = quantidade_deliberacoes_item()

    divergencias = []
    for anexo in anexos:
        avaliacoes = avaliacoes_por_anexo.get(anexo.id, [])

        situacoes = {av.situacao for av in avaliacoes}
        tem_indeferido = SituacaoAvaliacaoItem.INDEFERIDO in situacoes
        tem_deferido = SituacaoAvaliacaoItem.DEFERIDO in situacoes
        pontuacao_alterada = any(
            av.situacao == SituacaoAvaliacaoItem.DEFERIDO and av.pontuacao_validada is not None and av.pontuacao_validada != anexo.pontuacao
            for av in avaliacoes
        )
        desacordo_avaliadores = tem_indeferido and tem_deferido

        if not (tem_indeferido or pontuacao_alterada):
            continue  # Sem divergência — todos deferidos com pontuação correta

        votos = votos_por_anexo.get(anexo.id, [])
        divergencias.append(
            {
                'item': anexo.rol_saber_competencia,
                'requisito': getattr(anexo.rol_saber_competencia, 'requisito', None),
                'anexo': anexo,
                'avaliacoes': avaliacoes,
                'tem_indeferido': tem_indeferido,
                'tem_deferido': tem_deferido,
                'pontuacao_alterada': pontuacao_alterada,
                'desacordo_avaliadores': desacordo_avaliadores,
                'votos': votos,
                'status_deliberacao': status_deliberacao_item(votos, quantidade_necessaria),
            }
        )

    return divergencias


def _contar_anexos_avaliados_por_avaliador(processo):
    """Conta, por avaliador, quantos anexos do processo já foram avaliados."""
    contagem = {}
    anexos = RolSaberCompetenciaAnexo.objects.filter(processo=processo).prefetch_related('avaliacoes')
    for anexo in anexos:
        for avaliacao in anexo.avaliacoes.all():
            if avaliacao.avaliador_vinculo_id:
                contagem[avaliacao.avaliador_vinculo_id] = contagem.get(avaliacao.avaliador_vinculo_id, 0) + 1
    return contagem


def _linha_avaliador(vinculo, avaliacao_processo, avaliados, total_anexos):
    """Monta os dados de exibição (nome + progresso/resultado) de um avaliador."""
    finalizada = bool(avaliacao_processo and getattr(avaliacao_processo, 'finalizada', False))
    if not finalizada:
        pct = int(avaliados * 100 / total_anexos) if total_anexos > 0 else 0
        return {
            'nome': str(vinculo),
            'vinculo_id': getattr(vinculo, 'id', None),
            'finalizada': False,
            'variante': 'info',
            'pct': pct,
            'avaliados': avaliados,
            'total': total_anexos,
        }

    deferido = avaliacao_processo.resultado == SituacaoProcesso.DEFERIDO
    pontuacao = avaliacao_processo.pontuacao_final
    return {
        'nome': str(vinculo),
        'vinculo_id': getattr(vinculo, 'id', None),
        'finalizada': True,
        'variante': 'success' if deferido else 'error',
        'resultado_txt': 'Deferido' if deferido else 'Indeferido',
        'pontuacao': number_format(pontuacao, decimal_pos=2) if pontuacao is not None else '—',
    }


def montar_avaliadores_contexto(processo):
    """Lista os avaliadores do processo com status/progresso, para exibição em modal."""
    avaliadores = list(processo.avaliadores.all())
    if not avaliadores:
        return []

    avaliacao_por_avaliador = {ap.avaliador_vinculo_id: ap for ap in processo.avaliacoes_por_avaliador.all()}
    total_anexos = RolSaberCompetenciaAnexo.objects.filter(processo=processo).count()
    avaliados_por_avaliador = _contar_anexos_avaliados_por_avaliador(processo)

    return [
        _linha_avaliador(vinculo, avaliacao_por_avaliador.get(vinculo.id), avaliados_por_avaliador.get(vinculo.id, 0), total_anexos)
        for vinculo in avaliadores
    ]


def rotulos_anonimos_avaliadores(processo) -> dict:
    """Mapa vinculo_id -> 'Avaliador N' para todos os avaliadores do processo (ordem estável por id).

    Usado para anonimizar os nomes quando o usuário não é membro da CRSC-TAE.
    """
    ids = set()
    try:
        ids.update(v.id for v in processo.avaliadores.all())
    except Exception:
        logger.exception('Erro ao listar avaliadores do processo %s', getattr(processo, 'pk', None))
    ids.update(
        AvaliacaoProcessoRSCTae.objects.filter(processo=processo, avaliador_vinculo__isnull=False).values_list('avaliador_vinculo_id', flat=True)
    )
    return {vid: f'Avaliador {i}' for i, vid in enumerate(sorted(ids), start=1)}


def injetar_visibilidade_avaliadores(request, processo, ctx) -> dict:
    """Injeta no contexto o flag/mapa que controlam a exibição dos nomes de avaliadores.

    Veem nomes: membros da CRSC-TAE (``comum.is_membro_crsc_tae``) ou qualquer um quando o processo
    já está finalizado (a coação só é risco durante o andamento). Os demais recebem rótulos anônimos.
    Também anonimiza a lista simples ``avaliadores`` (strings) quando presente.
    """
    if not isinstance(ctx, dict):
        return ctx
    finalizado = processo.situacao in SituacaoProcesso.FINAIS
    try:
        vinculo = request.user.get_vinculo()
    except Exception:
        vinculo = None
    pode = finalizado or bool(getattr(request.user, 'is_superuser', False)) or eh_membro_crsc_ativo(vinculo)
    rotulos = {} if pode else rotulos_anonimos_avaliadores(processo)
    ctx['pode_ver_nomes_avaliadores'] = pode
    ctx['rotulos_avaliadores'] = rotulos
    if not pode and ctx.get('avaliadores'):
        ctx['avaliadores'] = list(rotulos.values())
    return ctx


def _ids_itens_com_pontuacao(processo):
    """IDs de itens 'pontuados': têm anexo com pontuação > 0 OU preenchimento com quantidade > 0."""
    ids_anexo = set(RolSaberCompetenciaAnexo.objects.filter(processo=processo, pontuacao__gt=0).values_list('rol_saber_competencia_id', flat=True))
    ids_preenchimento = set(
        RolSaberCompetenciaPreenchimento.objects.filter(vinculo=processo.vinculo, quantidade__gt=0).values_list('rol_saber_competencia_id', flat=True)
    )
    return ids_anexo | ids_preenchimento


def status_requisitos_obrigatorios(processo):
    """Status dos Requisitos Obrigatórios (RN04) do nível pretendido, para exibição no resumo do formulário.

    Retorna dict: ``aplicavel`` (o nível exige), ``alcancado`` (≥1 requisito obrigatório pontuado)
    e ``labels`` (descrições curtas dos requisitos obrigatórios).
    """
    obrigatorios = _requisitos_obrigatorios_do_nivel(processo.nivel_requisitado)
    if not obrigatorios:
        return {'aplicavel': False, 'alcancado': False, 'labels': []}
    alcancado = atende_requisitos_obrigatorios(processo.nivel_requisitado, _ids_itens_com_pontuacao(processo))
    return {'aplicavel': True, 'alcancado': alcancado, 'labels': [r.descricao_curta for r in obrigatorios]}


def _documentos_preliminares_atuais(processo) -> dict:
    """Retorna, para cada tipo obrigatório de documento preliminar, o envio mais recente do processo (ou None)."""
    return {
        tipo: (DocumentoPreliminarRSCTae.objects.filter(processo=processo, tipo=tipo).select_related('avaliacao').order_by('-data_cadastro').first())
        for tipo, _label in TipoDocumentoPreliminar.get_choices()
    }


def _documento_preliminar_situacao(documento) -> int:
    return getattr(getattr(documento, 'avaliacao', None), 'situacao', None) or SituacaoDocumentoPreliminar.PENDENTE


def data_exercicio_cargo_efetiva(processo):
    """Data de exercício no cargo em vigor: a confirmada pela comissão ou, se vazia, a cadastrada do servidor."""
    if processo.data_exercicio_cargo:
        return processo.data_exercicio_cargo
    servidor = getattr(processo.vinculo, 'relacionamento', None)
    return getattr(servidor, 'data_inicio_exercicio_no_cargo', None)


def anexo_anterior_a_data(anexo, data_exercicio) -> bool:
    """True se o anexo temporal tem período que começa antes da data de exercício no cargo (guia ao avaliador)."""
    if not data_exercicio:
        return False
    data_inicio = getattr(anexo, 'data_inicio', None)
    return bool(data_inicio and data_inicio < data_exercicio)


def enriquecer_anexos_data_exercicio(processo, linhas_avaliacao) -> None:
    """Marca cada anexo com ``anterior_data_exercicio`` (guia ao avaliador), a partir da data efetiva do processo."""
    data_exercicio = data_exercicio_cargo_efetiva(processo)
    for ln in linhas_avaliacao:
        for anexo in ln.get('anexos') or []:
            anexo.anterior_data_exercicio = anexo_anterior_a_data(anexo, data_exercicio)


def _anos_validados(av) -> int:
    """Anos validados de uma avaliação de anexo (0 se não deferida)."""
    if av and av.situacao == SituacaoAvaliacaoItem.DEFERIDO:
        return meses_para_anos_pontuaveis(av.pontuacao_validada or Decimal('0'))
    return 0


def _corrigir_anexo_temporal(anexo, item) -> None:
    """Converte, para exibição na avaliação, as unidades/pontos de um anexo temporal de meses para anos.

    A taxa é a do papel do próprio anexo (titular/substituto); itens sem papel usam a taxa única.
    """
    unidade = taxa_por_papel(item, getattr(anexo, 'papel', None))
    anos_decl = meses_para_anos_pontuaveis(getattr(anexo, 'pontuacao', None) or Decimal('0'))
    anexo.unid_informadas_aval = anos_decl
    anexo.pontos_requeridos = unidade * anos_decl

    anos_val_ctx = _anos_validados(getattr(anexo, 'avaliacao_anexo', None))
    anexo.unid_validadas_aval = anos_val_ctx
    anexo.pontos_validados = unidade * anos_val_ctx

    for av in getattr(anexo, 'avaliacoes_todos', None) or []:
        anos_val = _anos_validados(av)
        av.unid_validadas_aval = anos_val
        av.pontos_requeridos_calc = unidade * anos_decl
        av.pontos_validados_calc = unidade * anos_val


def corrigir_pontos_temporais_avaliacao(ctx) -> None:
    """Recalcula os pontos da avaliação para itens temporais (converte meses em anos POR PERÍODO).

    O contexto legado multiplica ``pontuacao_unidade`` pelos MESES por anexo; para item temporal o
    correto é converter cada período em anos ('ano ou fração > 6 meses') isoladamente e somar os
    anos — o total do item é a soma dos anos de cada documento. Ajusta os totais do item, a
    exibição por anexo e o total validado do resumo.
    """
    linhas = ctx.get('linhas_avaliacao') or []
    for ln in linhas:
        item = ln.get('item')
        if not getattr(item, 'item_temporal', False):
            continue
        anexos = ln.get('anexos') or []
        for anexo in anexos:
            _corrigir_anexo_temporal(anexo, item)
        # Totais do item = soma dos pontos por anexo (cada um já na taxa do seu papel).
        ln['total_pontos_requeridos_item'] = sum((getattr(a, 'pontos_requeridos', None) or Decimal('0')) for a in anexos)
        ln['total_pontos_validados_item'] = sum((getattr(a, 'pontos_validados', None) or Decimal('0')) for a in anexos)

    _recalcular_totais_avaliacao(ctx)


def _recalcular_totais_avaliacao(ctx) -> None:
    """Recompõe total validado, solicitado, itens validados, resultado parcial e percentual após ajuste temporal."""
    linhas = ctx.get('linhas_avaliacao') or []
    total_val = sum((ln.get('total_pontos_validados_item') or Decimal('0')) for ln in linhas)
    total_solic = sum((ln.get('total_pontos_requeridos_item') or Decimal('0')) for ln in linhas)
    itens_val = sum(1 for ln in linhas if (ln.get('total_pontos_validados_item') or Decimal('0')) > 0)
    pontos_min = ctx.get('pontos_requeridos_nivel') or Decimal('0')
    itens_min = int(ctx.get('itens_requeridos') or 0)

    ctx['total_pontos_validados'] = total_val
    ctx['total_pontos_solicitados'] = total_solic
    ctx['itens_validados'] = itens_val
    atingiu_pontos = (not pontos_min or pontos_min <= 0) or (total_val >= pontos_min)
    atingiu_itens = (not itens_min or itens_min <= 0) or (itens_val >= itens_min)
    ctx['resultado_parcial_deferido'] = bool(atingiu_pontos and atingiu_itens)
    if pontos_min and pontos_min > 0:
        ctx['pontos_percent'] = float(min(total_val / pontos_min, Decimal('1')) * Decimal('100'))


def contexto_apontamentos_correcao(processo) -> dict:
    """Apontamentos de correção não resolvidos, para o servidor ver o que corrigir.

    Retorna a lista geral (banner) e, separadamente, os apontamentos de formulário e memorial
    (usados como alerta no topo das abas correspondentes).
    """
    apontamentos = list(
        ApontamentoCorrecaoRSCTae.objects.filter(processo=processo, resolvido=False)
        .select_related('criado_por_vinculo')
        .order_by('area', 'data_criacao')
    )
    por_area = {a.area: a for a in apontamentos}
    return {
        'apontamentos_correcao': apontamentos,
        'apontamento_formulario': por_area.get(AreaCorrecao.FORMULARIO),
        'apontamento_memorial': por_area.get(AreaCorrecao.MEMORIAL),
    }


# Metadados de apresentação por tipo/situação (usados nos cards da aba de documentos preliminares).
_ICONE_POR_TIPO_DOCUMENTO_PRELIMINAR = {
    TipoDocumentoPreliminar.DIPLOMA_CERTIFICADO: 'certificate',
    TipoDocumentoPreliminar.HOMOLOGACAO_ESTAGIO_PROBATORIO: 'clipboard-check',
}

_STATUS_DOCUMENTO_PRELIMINAR = {
    SituacaoDocumentoPreliminar.VALIDADO: ('Validado', 'status-success'),
    SituacaoDocumentoPreliminar.CORRECAO_SOLICITADA: ('Correção solicitada', 'status-error'),
    SituacaoDocumentoPreliminar.PENDENTE: ('Pendente', 'status-alert'),
}


def montar_secoes_documentos_preliminares(documentos_preliminares_atuais) -> list:
    """Monta a lista de seções (uma por tipo) com metadados de apresentação para os cards.

    Cada seção traz o documento atual, o ícone do tipo e o rótulo/classe da situação,
    evitando lógica de apresentação no template.
    """
    secoes = []
    for tipo, label in TipoDocumentoPreliminar.get_choices():
        documento = documentos_preliminares_atuais.get(tipo)
        situacao = _documento_preliminar_situacao(documento)
        situacao_label, situacao_classe = _STATUS_DOCUMENTO_PRELIMINAR[situacao]
        secoes.append(
            {
                'tipo': tipo,
                'label': label,
                'icone': _ICONE_POR_TIPO_DOCUMENTO_PRELIMINAR.get(tipo, 'file'),
                'documento_atual': documento,
                'situacao_label': situacao_label if documento else 'Não enviado',
                'situacao_classe': situacao_classe if documento else 'status-alert',
            }
        )
    return secoes


def _enriquecer_anexos_memorial(grupos) -> None:
    """Anota cada anexo com a quantidade e os pontos calculados conforme a régua do item.

    O campo ``anexo.pontuacao`` guarda a quantidade de unidades declaradas — para item
    temporal, a duração em meses. A quantidade exibida passa por ``unidades_pontuaveis``:
    em item temporal converte meses em anos pontuáveis ('por ano ou fração superior a
    seis meses') antes de multiplicar pela pontuação por unidade; nos demais itens é a
    própria quantidade declarada. A régua oficial converte a SOMA dos períodos do item,
    portanto o subtotal da linha do item continua sendo a referência.
    """
    for grupo in grupos:
        for linha in grupo['linhas']:
            item = linha['item']
            for anexo in linha.get('anexos') or []:
                quantidade = unidades_pontuaveis(item, getattr(anexo, 'pontuacao', None) or Decimal('0'))
                anexo.quantidade_no_item = quantidade
                # Pontos por-anexo na taxa do papel (titular/substituto); item sem papel usa a taxa única.
                anexo.pontos_no_item = quantidade * taxa_por_papel(item, getattr(anexo, 'papel', None))


def montar_contexto_memorial(request, processo) -> dict:
    """Monta o contexto do memorial descritivo (dados dinâmicos derivados do preenchimento).

    Reaproveitado pela view ``visualizar`` (render inicial) e pelo endpoint AJAX de atualização.
    Inclui a introdução/conclusão editáveis (``memorial``) e a permissão de edição.
    """
    from ._permissoes import PermissoesProcesso
    from rsc_tae.models import MemorialDescritivoRSCTae

    resumo = _montar_resumo_preenchimento(processo)
    total_pontos = resumo['total_pontos']
    pontos_minimos = resumo['pontos_minimos']
    pontuacao_excedente = max(Decimal('0'), total_pontos - pontos_minimos) if pontos_minimos else Decimal('0')
    _enriquecer_anexos_memorial(resumo['grupos_requisito'])
    return {
        'processo': processo,
        'servidor': processo.vinculo.relacionamento,
        'grupos_requisito': resumo['grupos_requisito'],
        'total_pontos': total_pontos,
        'total_pontos_itens': resumo['total_pontos_itens'],
        'saldo_anterior': resumo['saldo_anterior'],
        'pontos_minimos': pontos_minimos,
        'itens_preenchidos': resumo['itens_preenchidos'],
        'pontuacao_excedente': pontuacao_excedente,
        'memorial': MemorialDescritivoRSCTae.objects.filter(processo=processo).first(),
        'pode_editar_preenchimento': PermissoesProcesso(request, processo).pode_editar_preenchimento,
    }


def status_abas_preenchimento(processo, documentos_preliminares_atuais, resumo, requisito_obrigatorio):
    """Indica se cada aba que exige ação do servidor está concluída (para o ícone de check na aba).

    Retorna dict com as chaves ``documentos`` e ``formulario`` (bool). A Declaração de Conformidade
    Legal deixou de ter aba própria — passou a ser assinada no formulário de conclusão.
    """
    pontos_ok = not resumo['pontos_minimos'] or resumo['total_pontos'] >= resumo['pontos_minimos']
    itens_ok = not resumo['itens_minimos'] or resumo['itens_preenchidos'] >= resumo['itens_minimos']
    rn04_ok = not requisito_obrigatorio['aplicavel'] or requisito_obrigatorio['alcancado']

    documentos_ok = bool(documentos_preliminares_atuais) and all(
        bool(doc) and _documento_preliminar_situacao(doc) != SituacaoDocumentoPreliminar.CORRECAO_SOLICITADA
        for doc in documentos_preliminares_atuais.values()
    )

    return {
        'documentos': documentos_ok,
        'formulario': pontos_ok and itens_ok and rn04_ok,
    }


def _lista_pontos_por_requisito(grupos):
    """Converte os grupos de `_agrupar_por_requisito` em lista [{'numeral', 'pontos'}] para o resumo."""
    itens = []
    for grupo in grupos:
        requisito = grupo.get('requisito')
        if requisito is None:
            continue
        numeral = getattr(requisito, 'numeral_romano', '') or getattr(requisito, 'descricao_curta', '') or ''
        itens.append({'numeral': numeral, 'pontos': number_format(grupo['subtotal_pontos'], decimal_pos=2)})
    return itens


def pontos_por_requisito(processo):
    """Lista de pontos por requisito do processo (para o resumo do formulário via AJAX)."""
    resumo = _montar_resumo_preenchimento(processo)
    return _lista_pontos_por_requisito(_agrupar_por_requisito(resumo['linhas']))


def _fmt(valor) -> str:
    """Serializa Decimal/None como string com 2 casas (ex.: '52.00'; None -> '0.00')."""
    return str((valor if valor is not None else Decimal('0')).quantize(Decimal('0.01')))


def _dados_identificacao(processo: ProcessoRSCTae) -> dict:
    """Seção 1 da aba Memorial — identificação do servidor.

    Divulgada publicamente no Portal (endpoint ``memoriais-avaliados/``): restrita a
    nome, SIAPE, cargo e lotação — dados como data de ingresso, classificação, função e
    e-mail foram removidos a pedido, por não serem necessários à publicação.
    """
    servidor = processo.vinculo.relacionamento
    return {
        'nome': str(getattr(processo.vinculo.pessoa, 'nome', '') or ''),
        'siape': str(getattr(servidor, 'matricula', '') or ''),
        'cargo': str(getattr(servidor, 'cargo_emprego', '') or ''),
        'lotacao': str(getattr(processo.vinculo, 'setor', '') or ''),
    }


def _dados_requerimento(processo: ProcessoRSCTae) -> dict:
    """Seção 2 da aba Memorial — informações do requerimento.

    Divulgada publicamente no Portal: os campos de pontuação (mínima, total, excedente,
    saldo anterior etc.) foram removidos a pedido — o Portal não deve expor a pontuação
    do requerimento, apenas o nível pretendido e o processo anterior (se houver).
    """
    return {
        'nivel_rsc_pretendido': f'RSC-{processo.nivel_requisitado.ordem_romana}',
        'processo_anterior_id': processo.processo_anterior_id,
    }


def _dados_memorial_requisitos(resumo: dict, introducao: str) -> dict:
    """Seção 3 da aba Memorial — introdução + descrição por requisito.

    Divulgada publicamente no Portal: pontuações (total do memorial, subtotal por
    requisito, quantidade/pontos por documento comprobatório) foram removidas a
    pedido — mantém-se apenas a descrição textual dos requisitos/itens/documentos.
    """
    requisitos = []
    for grupo in resumo['grupos_requisito']:
        itens = []
        for linha in grupo['linhas']:
            item = linha['item']
            documentos = [{'descricao': str(getattr(anexo, 'descricao', '') or '')} for anexo in (linha.get('anexos') or [])]
            itens.append(
                {
                    'numero': item.numero,
                    'titulo': str(item.titulo or ''),
                    'quantidade': _fmt(linha['quantidade_efetiva']),
                    'unidade_medida': str(getattr(item, 'unidade_medida', '') or ''),
                    'pontuacao_unidade': _fmt(item.pontuacao_unidade),
                    'pontuacao_total': _fmt(linha['pontuacao_total']),
                    'documentos': documentos,
                }
            )
        requisitos.append(
            {
                'label': str(grupo.get('label') or ''),
                'descricao': str(getattr(grupo.get('requisito'), 'descricao', '') or ''),
                'itens': itens,
            }
        )
    return {
        'introducao': introducao,
        'requisitos': requisitos,
    }


def _dados_conclusao(processo: ProcessoRSCTae, resumo: dict, conclusao: str) -> dict:
    """Seção 4 da aba Memorial — conclusão do servidor + frase-resumo."""
    total_fmt = str((resumo['total_pontos'] or Decimal('0')).quantize(Decimal('0.01'))).replace('.', ',')
    nivel = f'RSC-{processo.nivel_requisitado.ordem_romana}'
    resumo_frase = (
        f'À vista das informações apresentadas, totalizo {total_fmt} pontos e atendo aos '
        f'critérios legais e regulamentares para o nível {nivel} do RSC-PCCTAE. '
        f'Solicito a análise pela CRSC-PCCTAE.'
    )
    return {'texto': conclusao, 'resumo': resumo_frase}


def montar_dados_memorial(processo: ProcessoRSCTae) -> dict:
    """Monta o dict JSON-ready com as 4 seções da aba Memorial Descritivo.

    Versão request-free de ``montar_contexto_memorial``, para a API pública do Portal.
    """
    from rsc_tae.models import MemorialDescritivoRSCTae

    resumo = _montar_resumo_preenchimento(processo)
    _enriquecer_anexos_memorial(resumo['grupos_requisito'])
    memorial = MemorialDescritivoRSCTae.objects.filter(processo=processo).first()
    introducao = str(getattr(memorial, 'introducao', '') or '')
    conclusao = str(getattr(memorial, 'conclusao', '') or '')

    return {
        'id': processo.pk,
        'identificacao': _dados_identificacao(processo),
        'requerimento': _dados_requerimento(processo),
        'memorial': _dados_memorial_requisitos(resumo, introducao),
        'conclusao': _dados_conclusao(processo, resumo, conclusao),
    }
