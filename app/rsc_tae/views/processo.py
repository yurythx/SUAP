import logging
from django.apps import apps as django_apps
from django.utils import timezone
from django.utils.safestring import mark_safe
from decimal import Decimal

from django.core.exceptions import PermissionDenied
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import HttpResponse
from django.db.models import Prefetch
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST

from djtools.utils.http import get_client_ip
from djtools.utils.pdf import documento
from djtools.utils.response import httprr, rtr

from rsc_tae.enums import AreaCorrecao, MotivoIndeferimento, SituacaoAvaliacaoItem, SituacaoProcesso, TipoDocumentoPreliminar
from rsc_tae.enums import SituacaoDocumentoPreliminar
from rsc_tae.forms import (
    AlterarNivelForm,
    ConcluirPreenchimentoForm,
    ConfirmarValidacaoForm,
    DataExercicioCargoForm,
    DeliberacaoItemCRSCForm,
    VotoDeliberacaoFinalForm,
    FinalizarAvaliacaoForm,
    ImpedimentoAvaliacaoForm,
    NivelSelecaoForm,
    RecusaAvaliacaoForm,
    RemanejamentoAvaliadorForm,
    SolicitarCorrecaoForm,
)
from rsc_tae.models import (
    AlteracaoNivelRSCTae,
    ApontamentoCorrecaoRSCTae,
    AvaliacaoAnexoRSCTae,
    AvaliacaoDocumentoPreliminarRSCTae,
    AvaliacaoProcessoRSCTae,
    BancoPontosRSCTae,
    ConfiguracaoRSCTae,
    DeliberacaoCRSCRSCTae,
    DeliberacaoItemCRSCRSCTae,
    VotoDeliberacaoFinalRSCTae,
    DocumentoPreliminarRSCTaeLog,
    HistoricoSituacaoProcessoRSCTae,
    MemorialDescritivoRSCTae,
    MovimentoBancoPontosRSCTae,
    Nivel,
    OrigemTransicao,
    ProcessoRSCTae,
    RolSaberCompetencia,
    RolSaberCompetenciaAnexo,
    RolSaberCompetenciaPreenchimento,
    SorteioAvaliadorRSCTae,
)

from ._deliberacao_avaliado import aplicar_totais_consolidados, montar_deliberacao_para_avaliado
from ._helpers import (
    _agrupar_por_requisito,
    aplicar_notas_consolidadas_crsc,
    _calcular_data_limite_avaliacao,
    _calcular_resumo_por_pontos,
    _documento_preliminar_situacao,
    _documentos_preliminares_atuais,
    _enriquecer_anexos_memorial,
    contexto_apontamentos_correcao,
    corrigir_pontos_temporais_avaliacao,
    data_exercicio_cargo_efetiva,
    eh_membro_crsc_ativo,
    enriquecer_anexos_data_exercicio,
    injetar_visibilidade_avaliadores,
    rotulos_anonimos_avaliadores,
    quantidade_deliberacoes_item,
    resumo_final_consolidado,
    status_cota_categoria,
    status_deliberacao_item,
    status_deliberacao_final,
    _listar_divergencias_para_crsc,
    _montar_contexto_avaliacao,
    _montar_resumo_preenchimento,
    _lista_pontos_por_requisito,
    montar_avaliadores_contexto,
    montar_secoes_documentos_preliminares,
    status_abas_preenchimento,
    status_requisitos_obrigatorios,
    _sortear_avaliadores,
    _substituir_avaliador,
    _validar_acesso_avaliacao,
    _validar_acesso_processo,
    _validar_acesso_processo_leitura,
    _validar_acesso_resumo_avaliacao,
    _verificar_prazos_expirados,
    _erro_requisitos_obrigatorios,
    verificar_criterios_nivel,
)
from ._permissoes import PermissoesProcesso


@rtr('rsc_tae/iniciar_processo.html')
@login_required
def iniciar_processo(request):
    title = 'Iniciar processo RSC-TAE'

    if not getattr(request.user, 'eh_tecnico_administrativo', False):
        raise PermissionDenied('Apenas técnicos-administrativos podem iniciar um processo RSC-TAE.')

    try:
        servidor = request.user.get_relacionamento()
        titulacao = servidor.titulacao
        vinculo = servidor.get_vinculo()
    except Exception:
        return httprr(reverse('admin:rsc_tae_processorsctae_changelist'), 'Não foi possível identificar seus dados funcionais.', tag='error')

    if not titulacao:
        return httprr(
            reverse('admin:rsc_tae_processorsctae_changelist'),
            'Você não possui titulação cadastrada. Regularize no módulo de RH.',
            tag='error',
        )

    niveis, niveis_habilitados = _niveis_selecionaveis(titulacao)
    if not niveis.exists():
        return httprr(
            reverse('admin:rsc_tae_processorsctae_changelist'),
            'Nenhum nível RSC disponível para sua titulação atual.',
            tag='error',
        )

    # Apenas um nível disponível: inicia automaticamente sem exibir o formulário
    if niveis.count() == 1:
        return _iniciar_processo_com_nivel(request, vinculo, niveis.first())

    nivel_inicial = niveis_habilitados.order_by('-valor_iq').first()
    form = NivelSelecaoForm(request.POST or None, niveis_queryset=niveis, nivel_inicial=nivel_inicial)

    if request.method == 'POST' and form.is_valid():
        return _iniciar_processo_com_nivel(request, vinculo, form.cleaned_data['nivel'])

    ids_habilitados = set(niveis_habilitados.values_list('pk', flat=True))

    return {
        'title': title,
        'form': form,
        'titulacao': titulacao,
        'niveis': niveis,
        'ids_habilitados': ids_habilitados,
    }


def _niveis_selecionaveis(titulacao):
    """Níveis que o servidor pode pretender: habilitados pela titulação + o próximo superior.

    O próximo nível acima do maior habilitado é incluído porque o servidor pode ter obtido uma
    titulação mais alta ainda não registrada no sistema (ex.: recém-formado no mestrado).
    Retorna ``(niveis, niveis_habilitados)``; ``niveis`` vem vazio se nada está habilitado.
    """
    niveis_habilitados = Nivel.objects.filter(iq_requisito__in=[titulacao]).order_by('valor_iq')
    if not niveis_habilitados.exists():
        return Nivel.objects.none(), niveis_habilitados

    maior_ordem_habilitada = niveis_habilitados.order_by('-valor_iq').values_list('ordem', flat=True).first()
    proximo_nivel_superior = Nivel.objects.filter(ordem__gt=maior_ordem_habilitada).order_by('ordem').first()

    ids_disponiveis = list(niveis_habilitados.values_list('pk', flat=True))
    if proximo_nivel_superior:
        ids_disponiveis.append(proximo_nivel_superior.pk)
    return Nivel.objects.filter(pk__in=ids_disponiveis).order_by('valor_iq'), niveis_habilitados


def _iniciar_processo_com_nivel(request, vinculo, nivel):
    """Verifica duplicidade e cria o processo para o nível informado."""
    processo_existente = (
        ProcessoRSCTae.objects.filter(vinculo=vinculo, nivel_requisitado=nivel)
        .exclude(situacao=SituacaoProcesso.INDEFERIDO)
        .exclude(situacao=SituacaoProcesso.DEFERIDO)
        .order_by('-data_cadastro')
        .first()
    )
    if processo_existente:
        return httprr(
            processo_existente.get_absolute_url(),
            'Já existe um processo em andamento para este nível. Redirecionando.',
            tag='warning',
        )

    try:
        novo_processo = ProcessoRSCTae.calcular_novo_processo(request.user, nivel_id=nivel.pk)
    except ValueError as e:
        return httprr(reverse('rsc_tae:iniciar_processo'), str(e), tag='error')

    return httprr(
        novo_processo.get_absolute_url(),
        'Processo RSC-TAE iniciado com sucesso.',
        tag='success',
    )


def _reabrir_validacao_diploma(processo, nivel_anterior, nivel_novo, vinculo_usuario):
    """Marca o diploma/certificado validado como pendente de revalidação após a troca de nível.

    Garante que, na reconclusão do preenchimento, o processo volte à validação da comissão
    (que confere a titulação frente ao novo nível) em vez de seguir direto ao sorteio.
    """
    doc = _documentos_preliminares_atuais(processo).get(TipoDocumentoPreliminar.DIPLOMA_CERTIFICADO)
    if not doc or _documento_preliminar_situacao(doc) != SituacaoDocumentoPreliminar.VALIDADO:
        return
    observacao = f'Revalidação necessária: nível pretendido alterado de RSC-{nivel_anterior.ordem_romana} para RSC-{nivel_novo.ordem_romana}.'
    avaliacao, _created = AvaliacaoDocumentoPreliminarRSCTae.objects.get_or_create(documento=doc)
    # auto_now não dispara em .update(): data_avaliacao/data_ultima_alteracao precisam ser explícitas.
    # IP/user-agent da validação original são zerados — pertencem à avaliação anterior, não ao estado pendente.
    agora = timezone.now()
    AvaliacaoDocumentoPreliminarRSCTae.objects.filter(pk=avaliacao.pk).update(
        situacao=SituacaoDocumentoPreliminar.PENDENTE,
        observacao=observacao,
        avaliado_por_vinculo=None,
        ip_avaliacao=None,
        user_agent='',
        data_avaliacao=agora,
        data_ultima_alteracao=agora,
    )
    DocumentoPreliminarRSCTaeLog.objects.create(
        processo=processo,
        documento=doc,
        acao=DocumentoPreliminarRSCTaeLog.ACAO_REVALIDACAO,
        executado_por_vinculo=vinculo_usuario,
        observacao=observacao,
    )


def _alterar_nivel_processo(request, processo, nivel_novo, motivo):
    """Aplica a troca do nível pretendido: valida duplicidade, registra a auditoria e reabre a validação do diploma."""
    nivel_anterior = processo.nivel_requisitado
    duplicado = (
        ProcessoRSCTae.objects.filter(vinculo=processo.vinculo, nivel_requisitado=nivel_novo)
        .exclude(pk=processo.pk)
        .exclude(situacao__in=(SituacaoProcesso.DEFERIDO, SituacaoProcesso.INDEFERIDO))
        .exists()
    )
    if duplicado:
        return httprr(processo.get_absolute_url(), 'Já existe outro processo em andamento para o nível selecionado.', tag='error')

    vinculo_usuario = request.user.get_vinculo()
    with transaction.atomic():
        ProcessoRSCTae.objects.filter(pk=processo.pk).update(nivel_requisitado=nivel_novo)
        processo.nivel_requisitado = nivel_novo  # sincroniza a instância com o banco (evita uso stale adiante)
        AlteracaoNivelRSCTae.objects.create(
            processo=processo,
            nivel_anterior=nivel_anterior,
            nivel_novo=nivel_novo,
            motivo=motivo,
            alterado_por_vinculo=vinculo_usuario,
            ip=get_client_ip(request),
            user_agent=(request.META.get('HTTP_USER_AGENT') or '')[:255],
        )
        _reabrir_validacao_diploma(processo, nivel_anterior, nivel_novo, vinculo_usuario)

    return httprr(
        processo.get_absolute_url(),
        f'Nível pretendido alterado de RSC-{nivel_anterior.ordem_romana} para RSC-{nivel_novo.ordem_romana}. '
        'Ao concluir o preenchimento, o requerimento será reassinado com o novo nível.',
        tag='success',
    )


@rtr('rsc_tae/alterar_nivel.html')
@login_required
def alterar_nivel(request, processo_id):
    title = 'Alterar nível pretendido — RSC-TAE'
    processo = get_object_or_404(ProcessoRSCTae, pk=processo_id)

    perms = PermissoesProcesso(request, processo)
    if not perms.pode_alterar_nivel:
        raise PermissionDenied('O nível pretendido só pode ser alterado pelo próprio servidor enquanto o processo está em preenchimento ou correção.')

    try:
        titulacao = request.user.get_relacionamento().titulacao
    except Exception:
        titulacao = None
    if not titulacao:
        return httprr(processo.get_absolute_url(), 'Você não possui titulação cadastrada. Regularize no módulo de RH.', tag='error')

    niveis, _habilitados = _niveis_selecionaveis(titulacao)
    if not niveis.exists():
        return httprr(processo.get_absolute_url(), 'Nenhum nível RSC disponível para sua titulação atual.', tag='error')

    form = AlterarNivelForm(request.POST or None, niveis_queryset=niveis, nivel_atual=processo.nivel_requisitado, request=request)
    if request.method == 'POST' and form.is_valid():
        return _alterar_nivel_processo(request, processo, form.cleaned_data['nivel'], form.cleaned_data['motivo'])

    return {
        'title': title,
        'processo': processo,
        'form': form,
        'nivel_atual': processo.nivel_requisitado,
    }


@rtr('rsc_tae/minhas_avaliacoes.html')
@login_required
@require_GET
def minhas_avaliacoes(request):
    title = 'Minhas avaliações (RSC-TAE)'

    if not request.user.has_perm('rsc_tae.avaliar_processorsctae'):
        raise PermissionDenied('Permissão negada.')

    try:
        vinculo_usuario = request.user.get_vinculo()
    except Exception:
        vinculo_usuario = None

    if not vinculo_usuario:
        raise PermissionDenied('Vínculo do usuário não encontrado.')

    minhas_avaliacoes_qs = AvaliacaoProcessoRSCTae.objects.filter(avaliador_vinculo=vinculo_usuario).only(
        'id',
        'processo_id',
        'data_finalizacao',
        'finalizada',
        'pontuacao_final',
        'resposta',
        'substituido',
    )

    processos = ProcessoRSCTae.anotar_sla_data_entrada(
        ProcessoRSCTae.objects.filter(avaliadores=vinculo_usuario)
        .select_related('vinculo', 'vinculo__pessoa', 'nivel_requisitado')
        .prefetch_related(Prefetch('avaliacoes_por_avaliador', queryset=minhas_avaliacoes_qs, to_attr='minhas_avaliacoes_do_usuario'))
        # Mesma ordenação da listagem de processos do admin (aba "Em Análise"): entrada na
        # situação atual, do mais antigo para o mais recente — a ordem de avaliação é essa.
        .annotate(data_entrada_situacao_atual=ProcessoRSCTae.expressao_data_entrada_situacao_atual())
        .order_by('data_entrada_situacao_atual', 'data_cadastro')
        .distinct()
    )
    # Buscada uma vez: get_sla_status consultaria a configuração a cada processo do laço.
    configuracao_rsc = ConfiguracaoRSCTae.objects.first()

    linhas = []
    for p in processos:
        minha_avaliacao = None
        try:
            lista = getattr(p, 'minhas_avaliacoes_do_usuario', None) or []
            minha_avaliacao = lista[0] if lista else None
        except Exception:
            minha_avaliacao = None

        finalizada = bool(minha_avaliacao and getattr(minha_avaliacao, 'finalizada', False))

        # Usa dados já carregados pelo prefetch para evitar queries adicionais
        perms = PermissoesProcesso(request, p).com_dados_avaliador(
            eh_avaliador=True,  # o loop só itera sobre processos onde o usuário é avaliador
            finalizada=finalizada,
        )

        pode_ver_resumo = p.situacao in (
            SituacaoProcesso.EM_ANALISE,
            SituacaoProcesso.DEFERIDO,
            SituacaoProcesso.INDEFERIDO,
        )

        # Pode recusar/impedir enquanto não substituído e não finalizou
        pode_recusar_ou_impedir = (
            p.situacao == SituacaoProcesso.EM_ANALISE
            and minha_avaliacao is not None
            and not getattr(minha_avaliacao, 'substituido', True)
            and not finalizada
        )

        resposta = getattr(minha_avaliacao, 'resposta', None)
        recusada_ou_impedida = resposta in (AvaliacaoProcessoRSCTae.RESPOSTA_RECUSA, AvaliacaoProcessoRSCTae.RESPOSTA_IMPEDIMENTO)
        concluida = finalizada or recusada_ou_impedida or bool(getattr(minha_avaliacao, 'substituido', False))

        linhas.append(
            {
                'processo': p,
                'minha_avaliacao': minha_avaliacao,
                'finalizada': finalizada,
                'concluida': concluida,
                'pode_avaliar': perms.pode_avaliar,
                'pode_ver_resumo': pode_ver_resumo,
                'pode_recusar_ou_impedir': pode_recusar_ou_impedir,
                'sla': p.get_sla_status(configuracao=configuracao_rsc) if not finalizada else None,
            }
        )

    linhas_a_avaliar = [ln for ln in linhas if not ln['concluida']]
    linhas_concluidas = [ln for ln in linhas if ln['concluida']]

    return {
        'title': title,
        'vinculo_usuario': vinculo_usuario,
        'linhas': linhas,
        'linhas_a_avaliar': linhas_a_avaliar,
        'linhas_concluidas': linhas_concluidas,
    }


@rtr('rsc_tae/visualizar.html')
@login_required
def visualizar(request, id):
    title = 'Progresso RSC-TAE'
    processo = get_object_or_404(ProcessoRSCTae, pk=id)

    _ctx_acesso = _validar_acesso_processo_leitura(request, processo)
    eh_dono = _ctx_acesso['eh_dono']

    _verificar_prazos_expirados(processo)
    processo.refresh_from_db()

    perms = PermissoesProcesso(request, processo)

    pode_editar_preenchimento = perms.pode_editar_preenchimento
    pode_concluir_preenchimento = perms.pode_concluir_preenchimento
    pode_alterar_nivel = perms.pode_alterar_nivel
    pode_editar_documento_preliminar = perms.pode_editar_documento_preliminar
    pode_validar_documento_preliminar = perms.pode_validar_documento_preliminar
    pode_definir_avaliador = perms.pode_definir_avaliador
    pode_avaliar = perms.pode_avaliar
    pode_recusar_ou_impedir = perms.pode_recusar_ou_impedir
    pode_deliberar_crsc = perms.pode_deliberar_crsc

    vinculo_usuario = perms.vinculo_usuario

    # Dados dos documentos preliminares (um envio mais recente por tipo obrigatório)
    documentos_preliminares_atuais = _documentos_preliminares_atuais(processo)
    documento_preliminar_validado = perms.documento_preliminar_validado

    servidor = processo.vinculo.relacionamento

    configuracao_rsc_tae = ConfiguracaoRSCTae.objects.order_by('id').first()
    texto_instrucao_preenchimento = getattr(configuracao_rsc_tae, 'texto_instrucao_preenchimento', '') or ''
    texto_instrucao_avaliacao = getattr(configuracao_rsc_tae, 'texto_instrucao_avaliacao', '') or ''

    mostrar_instrucao_preenchimento = processo.situacao in SituacaoProcesso.EDITAVEIS_PELO_SERVIDOR
    mostrar_instrucao_avaliacao = processo.situacao in (
        SituacaoProcesso.AGUARDANDO_AVALIADOR,
        SituacaoProcesso.EM_ANALISE,
    )
    if not mostrar_instrucao_preenchimento and not mostrar_instrucao_avaliacao:
        mostrar_instrucao_preenchimento = True
        mostrar_instrucao_avaliacao = True

    documentos_preliminares_secoes = montar_secoes_documentos_preliminares(documentos_preliminares_atuais)
    documentos_preliminares_log = (
        DocumentoPreliminarRSCTaeLog.objects.filter(processo=processo).select_related('executado_por_vinculo').order_by('-data_cadastro')[:20]
    )

    _resumo_preenchimento = _montar_resumo_preenchimento(processo)
    linhas = _resumo_preenchimento['linhas']
    linhas_preenchidas = _resumo_preenchimento['linhas_preenchidas']
    grupos_requisito = _resumo_preenchimento['grupos_requisito']
    _enriquecer_anexos_memorial(grupos_requisito)  # anota quantidade/pontos por anexo (usado no memorial)
    resumo_preenchimento_total_itens = _resumo_preenchimento['resumo_preenchimento_total_itens']
    resumo_preenchimento_total_pontos = _resumo_preenchimento['resumo_preenchimento_total_pontos']
    total_pontos = _resumo_preenchimento['total_pontos']
    pontos_minimos = _resumo_preenchimento['pontos_minimos']
    pontos_percent = _resumo_preenchimento['pontos_percent']
    itens_preenchidos = _resumo_preenchimento['itens_preenchidos']
    itens_minimos = _resumo_preenchimento['itens_minimos']
    itens_percent = _resumo_preenchimento['itens_percent']

    grupos_requisito_formulario = _agrupar_por_requisito(linhas)

    try:
        memorial_descritivo = processo.memorial_descritivo
    except MemorialDescritivoRSCTae.DoesNotExist:
        memorial_descritivo = None
    memorial = memorial_descritivo  # introdução/conclusão editáveis no partial do memorial
    # Processo eletrônico: disponível só se o módulo estiver instalado; criar exige RH sistêmico.
    processo_eletronico_instalado = django_apps.is_installed('processo_eletronico')
    pode_criar_processo_eletronico = bool(request.user.has_perm('rh.eh_rh_sistemico'))
    pontuacao_excedente = max(Decimal('0'), total_pontos - pontos_minimos) if pontos_minimos else Decimal('0')

    # Status dos Requisitos Obrigatórios (RN04) do nível — exibido no resumo do formulário.
    requisito_obrigatorio_status = status_requisitos_obrigatorios(processo)

    # Resumo do formulário: pontos que faltam para o mínimo + quebra por requisito.
    pontos_faltam = max(Decimal('0'), pontos_minimos - total_pontos) if pontos_minimos else Decimal('0')
    pontos_por_requisito_list = _lista_pontos_por_requisito(grupos_requisito_formulario)

    # Indicadores de "aba concluída" (ícone de check nas abas que exigem ação do servidor).
    abas_status = status_abas_preenchimento(processo, documentos_preliminares_atuais, _resumo_preenchimento, requisito_obrigatorio_status)

    # Linha do tempo das mudanças de situação (data + motivo + origem), mais recente primeiro.
    historico_situacoes = (
        HistoricoSituacaoProcessoRSCTae.objects.filter(processo=processo).select_related('realizado_por_vinculo__pessoa').order_by('-data_transicao')
    )

    # Apontamentos de correção não resolvidos (banner + alertas por aba) — guia do que corrigir.
    _apontamentos_ctx = contexto_apontamentos_correcao(processo)
    apontamentos_correcao = _apontamentos_ctx['apontamentos_correcao']
    apontamento_formulario = _apontamentos_ctx['apontamento_formulario']
    apontamento_memorial = _apontamentos_ctx['apontamento_memorial']

    # Relato da deliberação (aba "Deliberação") — só existe depois que o processo é decidido.
    pode_ver_deliberacao = perms.pode_ver_deliberacao
    deliberacao_avaliado = montar_deliberacao_para_avaliado(processo) if pode_ver_deliberacao else None

    return locals()


def _dados_preenchimento_conclusao(processo):
    """Carrega itens, preenchimentos e anexos usados nas validações de conclusão."""
    itens = (
        RolSaberCompetencia.objects.filter(ativo=True)
        .select_related('grupo__requisito')
        .order_by('grupo__requisito__numero', 'grupo__numero', 'numero')
    )
    preenchimentos = RolSaberCompetenciaPreenchimento.objects.filter(vinculo=processo.vinculo, rol_saber_competencia__in=itens)
    preenchimento_por_item_id = {p.rol_saber_competencia_id: p for p in preenchimentos}

    anexos_por_item_id = {}
    for anexo in RolSaberCompetenciaAnexo.objects.filter(processo=processo, rol_saber_competencia__in=itens):
        anexos_por_item_id.setdefault(anexo.rol_saber_competencia_id, []).append(anexo)

    return itens, preenchimento_por_item_id, anexos_por_item_id


def _erro_conclusao_documento(processo, documentos_preliminares_atuais):
    """Valida estado do processo e documentos preliminares. Retorna mensagem de erro ou None."""
    if processo.situacao not in SituacaoProcesso.EDITAVEIS_PELO_SERVIDOR:
        return 'Não é possível concluir: o processo não está em "Aguardando Preenchimento" ou "Aguardando Correção".'

    labels_por_tipo = dict(TipoDocumentoPreliminar.get_choices())

    faltantes = [labels_por_tipo[tipo] for tipo, doc in documentos_preliminares_atuais.items() if not doc]
    if faltantes:
        return f'Não é possível concluir o preenchimento: anexe {" e ".join(faltantes)} na aba "Documentos preliminares".'

    sem_data = [labels_por_tipo[tipo] for tipo, doc in documentos_preliminares_atuais.items() if not doc.data_obtencao_titulacao]
    if sem_data:
        return (
            f'Não é possível concluir o preenchimento: informe a data de obtenção/homologação de {" e ".join(sem_data)} '
            'na aba "Documentos preliminares".'
        )

    em_correcao = [
        labels_por_tipo[tipo]
        for tipo, doc in documentos_preliminares_atuais.items()
        if _documento_preliminar_situacao(doc) == SituacaoDocumentoPreliminar.CORRECAO_SOLICITADA
    ]
    if em_correcao:
        return (
            f'Não é possível concluir o preenchimento: correção solicitada em {" e ".join(em_correcao)}. '
            'Verifique a aba "Documentos preliminares" para mais detalhes.'
        )
    return None


def _erro_conclusao_anexos(itens, preenchimento_por_item_id, anexos_por_item_id):
    """Valida pontuação, descrição dos anexos e presença de anexo por item declarado. Retorna erro ou None."""
    for lista in anexos_por_item_id.values():
        if any((getattr(a, 'pontuacao', None) or Decimal('0')) <= 0 for a in lista):
            return 'Não é possível concluir o preenchimento: existem anexos sem pontuação definida.'
        if any(not (a.descricao or '').strip() for a in lista):
            return 'Não é possível concluir o preenchimento: existem anexos sem descrição.'

    # Nos itens que distinguem titular/substituto (Requisito V), o papel é obrigatório em cada documento.
    itens_aceita_papel = {item.id for item in itens if getattr(item, 'aceita_papel', False)}
    for item_id, lista in anexos_por_item_id.items():
        if item_id in itens_aceita_papel and any(not getattr(a, 'papel', None) for a in lista):
            return 'Não é possível concluir o preenchimento: informe o papel (titular ou substituto) em todos os documentos do Requisito V.'

    # RN09: todo item com quantidade declarada > 0 deve ter ao menos um anexo comprobatório
    itens_sem_anexo = [
        item
        for item in itens
        if item.id in preenchimento_por_item_id and preenchimento_por_item_id[item.id].quantidade > 0 and item.id not in anexos_por_item_id
    ]
    if itens_sem_anexo:
        nomes = '; '.join(item.titulo[:60] for item in itens_sem_anexo[:5])
        sufixo = f' (e mais {len(itens_sem_anexo) - 5})' if len(itens_sem_anexo) > 5 else ''
        return f'Não é possível concluir o preenchimento: os seguintes itens declarados não possuem documento comprobatório anexado: {nomes}{sufixo}.'
    return None


def _erro_conclusao_memorial(processo):
    """Exige introdução e conclusão do memorial descritivo preenchidas. Retorna erro ou None."""
    try:
        memorial = processo.memorial_descritivo
    except MemorialDescritivoRSCTae.DoesNotExist:
        memorial = None
    if not memorial or not (memorial.introducao or '').strip():
        return 'Não é possível concluir: preencha a Introdução do memorial descritivo (aba Memorial Descritivo).'
    if not (memorial.conclusao or '').strip():
        return 'Não é possível concluir: preencha a Conclusão do memorial descritivo (aba Memorial Descritivo).'
    return None


def _erro_conclusao_regras(processo, itens, preenchimento_por_item_id, anexos_por_item_id, resumo):
    """Valida pontuação/itens mínimos, RN04 e declaração de conformidade. Retorna erro ou None."""
    problemas = []
    if resumo['pontos_minimos'] and resumo['total_pontos'] < resumo['pontos_minimos']:
        detalhe = f'{resumo["total_pontos"]}'
        if resumo['saldo_anterior'] > 0:
            detalhe = f'{resumo["total_pontos_itens"]} + {resumo["saldo_anterior"]} (saldo anterior) = {resumo["total_pontos"]}'
        problemas.append(f'Pontuação insuficiente: {detalhe} / {resumo["pontos_minimos"]}.')
    if resumo['itens_minimos'] and resumo['itens_preenchidos'] < resumo['itens_minimos']:
        problemas.append(f'Quantidade de itens insuficiente: {resumo["itens_preenchidos"]} / {resumo["itens_minimos"]}.')

    itens_com_pontuacao_ids = [
        item.id
        for item in itens
        if any((getattr(a, 'pontuacao', None) or Decimal('0')) > 0 for a in anexos_por_item_id.get(item.id) or [])
        or (item.id in preenchimento_por_item_id and preenchimento_por_item_id[item.id].quantidade > 0)
    ]
    msg_requisito_obrigatorio = _erro_requisitos_obrigatorios(processo, itens_com_pontuacao_ids)
    if msg_requisito_obrigatorio:
        problemas.append(msg_requisito_obrigatorio)

    if problemas:
        return 'Não é possível concluir o preenchimento. ' + ' '.join(problemas)

    # A Declaração de Conformidade Legal é exigida pelo próprio formulário de conclusão.
    return None


def _finalizar_conclusao(request, processo, documentos_preliminares_atuais, form):
    """Processa o POST de conclusão: registra a entrada do requerimento e encaminha o processo."""
    vinculo_servidor = request.user.get_vinculo()
    todos_documentos_validados = bool(documentos_preliminares_atuais) and all(
        _documento_preliminar_situacao(doc) == SituacaoDocumentoPreliminar.VALIDADO for doc in documentos_preliminares_atuais.values()
    )

    # Declaração de Conformidade Legal assinada no próprio formulário de conclusão.
    if not processo.declaracao_conformidade:
        ProcessoRSCTae.objects.filter(pk=processo.pk).update(declaracao_conformidade=True)
        processo.declaracao_conformidade = True

    # Data-chave: entrada do requerimento — o servidor concluiu o preenchimento e protocolou
    # o requerimento. Registrada uma única vez, independente do encaminhamento posterior.
    if not processo.data_entrada_requerimento:
        agora_entrada = timezone.now()
        ProcessoRSCTae.objects.filter(pk=processo.pk).update(data_entrada_requerimento=agora_entrada)
        processo.data_entrada_requerimento = agora_entrada

    # Assinatura de integridade do preenchimento: hash + conteúdo assinado, gerados quando o
    # servidor confirma a conclusão com a senha (conferência posterior). Gerada ANTES do snapshot
    # do requerimento para que o hash conste no PDF protocolado.
    processo.gerar_assinatura_preenchimento()

    # Snapshot do requerimento (Portaria 608) anexado ao processo — peça protocolada.
    from .documentos import anexar_requerimento_ao_processo

    anexar_requerimento_ao_processo(processo)

    # Correções apontadas pelo RH foram endereçadas pelo servidor ao reconcluir — viram histórico.
    ApontamentoCorrecaoRSCTae.objects.filter(processo=processo, resolvido=False).update(resolvido=True)

    if todos_documentos_validados:
        # Doc já validado → sorteio automático de avaliadores → EM_ANALISE
        try:
            sorteados = _sortear_avaliadores(processo, realizado_por_vinculo=vinculo_servidor)
        except ValueError as e:
            return httprr(processo.get_absolute_url(), str(e), tag='error')
        nomes = ', '.join(str(v) for v in sorteados)
        return httprr(
            processo.get_absolute_url(),
            f'Preenchimento concluído e assinado. Avaliadores sorteados automaticamente: {nomes}.',
            tag='success',
        )

    processo.transicionar(
        SituacaoProcesso.AGUARDANDO_VALIDACAO_DOCUMENTO_PRELIMINAR,
        motivo='Servidor concluiu o preenchimento e protocolou o requerimento. Aguardando validação do documento preliminar pela comissão.',
        por_vinculo=vinculo_servidor,
        origem=OrigemTransicao.MANUAL,
        campos_extras={'avaliador_atual': None},
    )
    return httprr(
        processo.get_absolute_url(),
        'Preenchimento concluído e assinado. Aguardando validação do documento preliminar pela comissão.',
        tag='success',
    )


@login_required
@rtr('rsc_tae/concluir_preenchimento.html')
def concluir_preenchimento(request, processo_id):
    title = 'Concluir Preenchimento RSC-TAE'
    processo = get_object_or_404(ProcessoRSCTae, pk=processo_id)
    _validar_acesso_processo(request, processo)

    documentos_preliminares_atuais = _documentos_preliminares_atuais(processo)
    erro = _erro_conclusao_documento(processo, documentos_preliminares_atuais)
    if erro:
        return httprr(processo.get_absolute_url(), erro, tag='error')

    itens, preenchimento_por_item_id, anexos_por_item_id = _dados_preenchimento_conclusao(processo)

    erro = _erro_conclusao_anexos(itens, preenchimento_por_item_id, anexos_por_item_id)
    if erro:
        return httprr(processo.get_absolute_url(), erro, tag='error')

    resumo = _calcular_resumo_por_pontos(processo, itens, preenchimento_por_item_id, anexos_por_item_id)

    erro = _erro_conclusao_regras(processo, itens, preenchimento_por_item_id, anexos_por_item_id, resumo)
    if erro:
        return httprr(processo.get_absolute_url(), erro, tag='error')

    erro = _erro_conclusao_memorial(processo)
    if erro:
        return httprr(processo.get_absolute_url(), erro, tag='error')

    form = ConcluirPreenchimentoForm(request.POST or None, request=request)
    if request.method == 'POST' and form.is_valid():
        return _finalizar_conclusao(request, processo, documentos_preliminares_atuais, form)

    return {
        'title': title,
        'processo': processo,
        'form': form,
        'total_pontos': resumo['total_pontos'],
        'total_pontos_itens': resumo['total_pontos_itens'],
        'saldo_anterior': resumo['saldo_anterior'],
        'pontos_minimos': resumo['pontos_minimos'],
        'itens_preenchidos': resumo['itens_preenchidos'],
        'itens_minimos': resumo['itens_minimos'],
    }


@login_required
def definir_avaliador_atual(request, processo_id):
    """View legada — a definição de avaliadores agora é feita por sorteio automático."""
    processo = get_object_or_404(ProcessoRSCTae, pk=processo_id)
    return httprr(
        processo.get_absolute_url(),
        'A definição de avaliadores agora é feita automaticamente por sorteio ao concluir o preenchimento.',
        tag='info',
    )


def _contexto_validacao(processo):
    """Monta os dados exibidos na tela de validação do processo pelo RH."""
    documentos_preliminares_atuais = _documentos_preliminares_atuais(processo)

    documentos_preliminares_secoes = []
    for tipo, label in TipoDocumentoPreliminar.get_choices():
        documento = documentos_preliminares_atuais.get(tipo)
        avaliacao = None
        if documento:
            avaliacao, _created = AvaliacaoDocumentoPreliminarRSCTae.objects.get_or_create(documento=documento)
        documentos_preliminares_secoes.append(
            {
                'tipo': tipo,
                'label': label,
                'documento': documento,
                'avaliacao': avaliacao,
            }
        )

    try:
        memorial_descritivo = processo.memorial_descritivo
    except MemorialDescritivoRSCTae.DoesNotExist:
        memorial_descritivo = None

    resumo = _montar_resumo_preenchimento(processo)
    total_pontos = resumo['resumo_preenchimento_total_pontos']
    pontos_minimos = processo.nivel_requisitado.pontuacao_minima or Decimal('0')
    pontuacao_excedente = max(Decimal('0'), total_pontos - pontos_minimos) if pontos_minimos else Decimal('0')

    servidor = processo.vinculo.relacionamento

    return {
        'documentos_preliminares_atuais': documentos_preliminares_atuais,
        'documentos_preliminares_secoes': documentos_preliminares_secoes,
        'memorial_descritivo': memorial_descritivo,
        'grupos_requisito': resumo['grupos_requisito'],
        'resumo_total_pontos': total_pontos,
        'resumo_total_itens': resumo['resumo_preenchimento_total_itens'],
        'servidor': servidor,
        'pontos_minimos': pontos_minimos,
        'total_pontos': total_pontos,
        'itens_preenchidos': resumo['resumo_preenchimento_total_itens'],
        'pontuacao_excedente': pontuacao_excedente,
        'data_exercicio_cargo_efetiva': data_exercicio_cargo_efetiva(processo),
        'data_exercicio_cargo_servidor': getattr(servidor, 'data_inicio_exercicio_no_cargo', None),
        'data_exercicio_form': DataExercicioCargoForm(initial={'data_exercicio_cargo': data_exercicio_cargo_efetiva(processo)}),
        'documentos_preliminares_log': (
            DocumentoPreliminarRSCTaeLog.objects.filter(processo=processo).select_related('executado_por_vinculo').order_by('-data_cadastro')[:20]
        ),
    }


def _vinculo_ou_none(request):
    try:
        return request.user.get_vinculo()
    except Exception:
        return None


def _checar_permissao_validacao(request, processo):
    """Garante que o usuário pode analisar/validar o processo (membro ativo da CRSC, não-dono). Levanta PermissionDenied."""
    vinculo_usuario = _vinculo_ou_none(request)
    if not vinculo_usuario or not eh_membro_crsc_ativo(vinculo_usuario):
        raise PermissionDenied('Apenas membros ativos da CRSC-TAE podem validar o processo.')
    if processo.vinculo_id == vinculo_usuario.id:
        raise PermissionDenied('Você não pode validar o seu próprio processo.')


def _processo_em_validacao(processo):
    return processo.situacao in (
        SituacaoProcesso.AGUARDANDO_VALIDACAO_DOCUMENTO_PRELIMINAR,
        SituacaoProcesso.AGUARDANDO_AVALIADOR,  # legado
    )


def _validar_processo_rh(request, processo, documentos_preliminares_atuais):
    """Marca os documentos preliminares como validados, sorteia avaliadores e encaminha para análise."""
    vinculo_avaliador = _vinculo_ou_none(request)
    user_agent = (request.META.get('HTTP_USER_AGENT') or '')[:255]

    for doc_preliminar in documentos_preliminares_atuais.values():
        if not doc_preliminar:
            continue
        avaliacao, _created = AvaliacaoDocumentoPreliminarRSCTae.objects.get_or_create(documento=doc_preliminar)
        AvaliacaoDocumentoPreliminarRSCTae.objects.filter(pk=avaliacao.pk).update(
            situacao=SituacaoDocumentoPreliminar.VALIDADO,
            avaliado_por_vinculo=vinculo_avaliador,
            ip_avaliacao=get_client_ip(request),
            user_agent=user_agent,
        )
        DocumentoPreliminarRSCTaeLog.objects.create(
            processo=processo,
            documento=doc_preliminar,
            acao=DocumentoPreliminarRSCTaeLog.ACAO_VALIDACAO,
            executado_por_vinculo=vinculo_avaliador,
            ip=get_client_ip(request),
            user_agent=user_agent,
        )

    lista_url = reverse('admin:rsc_tae_processorsctae_changelist')
    try:
        sorteados = _sortear_avaliadores(processo, realizado_por_vinculo=vinculo_avaliador)
    except ValueError as e:
        return httprr(lista_url, f'Processo validado com sucesso. Atenção: {e}', tag='warning', close_popup=True)
    nomes = ', '.join(str(v) for v in sorteados)
    return httprr(lista_url, f'Processo validado com sucesso. Avaliadores sorteados automaticamente: {nomes}.', tag='success', close_popup=True)


def _marcar_documento_correcao(request, processo, doc, descricao, vinculo_avaliador):
    """Marca um documento preliminar apontado como 'correção solicitada' e registra o log."""
    user_agent = (request.META.get('HTTP_USER_AGENT') or '')[:255]
    avaliacao, _created = AvaliacaoDocumentoPreliminarRSCTae.objects.get_or_create(documento=doc)
    AvaliacaoDocumentoPreliminarRSCTae.objects.filter(pk=avaliacao.pk).update(
        situacao=SituacaoDocumentoPreliminar.CORRECAO_SOLICITADA,
        observacao=descricao,
        avaliado_por_vinculo=vinculo_avaliador,
        ip_avaliacao=get_client_ip(request),
        user_agent=user_agent,
    )
    DocumentoPreliminarRSCTaeLog.objects.create(
        processo=processo,
        documento=doc,
        acao=DocumentoPreliminarRSCTaeLog.ACAO_SOLICITAR_CORRECAO,
        executado_por_vinculo=vinculo_avaliador,
        ip=get_client_ip(request),
        user_agent=user_agent,
        observacao=descricao,
    )


def _registrar_apontamentos_correcao(request, processo, documentos_preliminares_atuais, apontamentos, vinculo_autor) -> str:
    """Cria os apontamentos de correção, reabre os documentos apontados e descreve o que foi apontado.

    Compartilhada pelos dois pontos que devolvem o processo ao servidor: a solicitação na fase de
    validação e a devolução decidida na deliberação da CRSC. Só os documentos apontados voltam a
    pendentes; os já validados permanecem intactos e não precisam ser reenviados.

    Args:
        request: Requisição em curso (fonte do IP e do user-agent gravados no log do documento).
        processo: Processo devolvido.
        documentos_preliminares_atuais: Mapa ``tipo -> documento`` do envio mais recente de cada tipo.
        apontamentos: Lista de ``(area, descricao)`` das áreas marcadas.
        vinculo_autor: Vínculo de quem apontou.

    Returns:
        Descrição das áreas apontadas, no formato ``"Área: descrição; Área: descrição"``, para
        compor o motivo do histórico de situação.
    """
    labels = dict(AreaCorrecao.get_choices())

    for area, descricao in apontamentos:
        ApontamentoCorrecaoRSCTae.objects.create(
            processo=processo,
            area=area,
            descricao=descricao,
            criado_por_vinculo=vinculo_autor,
        )
        # Áreas de documento (mesmo valor de TipoDocumentoPreliminar) marcam o doc como correção solicitada.
        if area in AreaCorrecao.AREAS_DOCUMENTO:
            doc = documentos_preliminares_atuais.get(area)
            if doc:
                _marcar_documento_correcao(request, processo, doc, descricao, vinculo_autor)

    return '; '.join(f'{labels[area]}: {descricao}' for area, descricao in apontamentos)


def _solicitar_correcao_rh(request, processo, documentos_preliminares_atuais, apontamentos):
    """Devolve o processo ao servidor na fase de validação, com os apontamentos do que corrigir.

    Args:
        request: Requisição em curso.
        processo: Processo em validação.
        documentos_preliminares_atuais: Mapa ``tipo -> documento`` do envio mais recente de cada tipo.
        apontamentos: Lista de ``(area, descricao)`` das áreas marcadas.

    Returns:
        Redirecionamento para a listagem do admin, com a mensagem de sucesso.
    """
    vinculo_avaliador = _vinculo_ou_none(request)
    descricao_areas = _registrar_apontamentos_correcao(request, processo, documentos_preliminares_atuais, apontamentos, vinculo_avaliador)

    motivo = f'Correção solicitada pelo RH — {descricao_areas}'
    processo.transicionar(
        SituacaoProcesso.AGUARDANDO_CORRECAO,
        motivo=motivo,
        por_vinculo=vinculo_avaliador,
        origem=OrigemTransicao.MANUAL,
        campos_extras={'avaliador_atual': None},
    )
    lista_url = reverse('admin:rsc_tae_processorsctae_changelist')
    return httprr(lista_url, 'Correção solicitada ao servidor.', tag='success', close_popup=True)


@rtr('rsc_tae/validar_processo.html')
@login_required
def validar_processo(request, processo_id):
    processo = get_object_or_404(ProcessoRSCTae, pk=processo_id)
    _checar_permissao_validacao(request, processo)
    if not _processo_em_validacao(processo):
        # O processo já saiu da validação (ex.: recarregamento da página após validar/solicitar
        # correção). Vai para a listagem sem erro — a mensagem de sucesso da ação prevalece.
        return httprr(reverse('admin:rsc_tae_processorsctae_changelist'))

    return {
        'title': 'Validar Processo RSC-TAE',
        'processo': processo,
        **_contexto_validacao(processo),
    }


@rtr('rsc_tae/popup_confirmar_validacao.html')
@login_required
def confirmar_validacao(request, processo_id):
    processo = get_object_or_404(ProcessoRSCTae, pk=processo_id)
    _checar_permissao_validacao(request, processo)
    if not _processo_em_validacao(processo):
        return httprr(processo.get_absolute_url(), 'Este processo não está em etapa de validação.', tag='error', close_popup=True)

    form = ConfirmarValidacaoForm(request.POST or None, request=request)
    if request.method == 'POST' and form.is_valid():
        return _validar_processo_rh(request, processo, _documentos_preliminares_atuais(processo))

    return {'title': 'Validar processo', 'processo': processo, 'form': form}


def _devolver_para_correcao_crsc(request, processo, apontamentos):
    """Anula a fase de avaliação e devolve o processo ao servidor a partir da deliberação.

    Diferente da solicitação na validação, aqui há avaliação e deliberação produzidas. Elas
    mediram um preenchimento que vai mudar — se o nível pretendido mudar, muda junto a régua
    (`pontuacao_minima`, `numero_minimo_itens`) —, então são apagadas antes da devolução.

    Args:
        request: Requisição em curso.
        processo: Processo em deliberação da CRSC.
        apontamentos: Lista de ``(area, descricao)`` das áreas marcadas pelo presidente.

    Returns:
        Redirecionamento para a listagem do admin, com o resumo do que foi anulado.
    """
    vinculo_presidente = _vinculo_ou_none(request)

    # Os três passos vão juntos ou não vão: a ação apaga dados, e uma falha depois do reset
    # deixaria o processo em deliberação com a avaliação já anulada. `anular_fases_posteriores`
    # é reentrante, então a chamada de dentro de `transicionar` aqui não remove mais nada.
    with transaction.atomic():
        removidos = processo.anular_fases_posteriores()
        descricao_areas = _registrar_apontamentos_correcao(
            request, processo, _documentos_preliminares_atuais(processo), apontamentos, vinculo_presidente
        )
        anulado = (
            f'{removidos["avaliacoes_processo"]} avaliação(ões), '
            f'{removidos["deliberacoes_item"]} voto(s) de item e '
            f'{removidos["votos_finais"]} voto(s) final(is) anulados'
        )
        processo.transicionar(
            SituacaoProcesso.AGUARDANDO_CORRECAO,
            motivo=f'Devolução para correção decidida na deliberação da CRSC — {descricao_areas}. {anulado}.',
            por_vinculo=vinculo_presidente,
            origem=OrigemTransicao.MANUAL,
            campos_extras={'avaliador_atual': None},
        )
    # A aba de onde o processo saiu: é para lá que a comissão volta, para seguir a fila.
    lista_url = f'{reverse("admin:rsc_tae_processorsctae_changelist")}?tab=tab_aguardando_crsc'
    mensagem = f'Processo devolvido ao servidor para correção. {anulado}.'

    if '_popup' in request.GET:
        # `close_popup=True` do httprr apenas recarrega a página-mãe — que aqui é a tela de
        # deliberação deste processo, agora inacessível a ele. Fecha e leva a mãe para a lista.
        messages.success(request, mensagem)
        return HttpResponse(f'<script>parent.close_fancybox_and_redirect("{lista_url}");</script>')
    return httprr(lista_url, mensagem, tag='success')


@rtr('rsc_tae/popup_devolver_correcao_crsc.html')
@login_required
def devolver_correcao_crsc(request, processo_id):
    """Devolução do processo ao servidor decidida na deliberação da CRSC (ato do presidente).

    Args:
        request: Requisição em curso.
        processo_id: Identificador do processo em deliberação.

    Returns:
        O contexto do formulário (GET) ou o redirecionamento da devolução (POST válido).

    Raises:
        PermissionDenied: Se o usuário não for o presidente da comissão ativa, for o próprio
            avaliado, ou o processo não estiver em deliberação.
    """
    processo = get_object_or_404(ProcessoRSCTae, pk=processo_id)

    perms = PermissoesProcesso(request, processo)
    if not perms.pode_devolver_para_correcao_crsc:
        raise PermissionDenied('A devolução para correção na deliberação é ato privativo do presidente da comissão.')

    form = SolicitarCorrecaoForm(request.POST or None, request=request)
    # O form é compartilhado com a solicitação da fase de validação, onde a ação é branda.
    # Aqui ela anula a avaliação inteira, e o rótulo herdado subestimaria o que está sendo feito.
    form.SUBMIT_LABEL = 'Assinar e devolver para correção'
    if request.method == 'POST' and form.is_valid():
        return _devolver_para_correcao_crsc(request, processo, form.apontamentos())

    return {'title': 'Devolver para correção', 'processo': processo, 'form': form}


@rtr('rsc_tae/popup_solicitar_correcao.html')
@login_required
def solicitar_correcao(request, processo_id):
    processo = get_object_or_404(ProcessoRSCTae, pk=processo_id)
    _checar_permissao_validacao(request, processo)
    if not _processo_em_validacao(processo):
        return httprr(processo.get_absolute_url(), 'Este processo não está em etapa de validação.', tag='error', close_popup=True)

    form = SolicitarCorrecaoForm(request.POST or None, request=request)
    if request.method == 'POST' and form.is_valid():
        return _solicitar_correcao_rh(request, processo, _documentos_preliminares_atuais(processo), form.apontamentos())

    return {'title': 'Solicitar correção', 'processo': processo, 'form': form}


@login_required
@require_POST
def salvar_data_exercicio_cargo(request, processo_id):
    processo = get_object_or_404(ProcessoRSCTae, pk=processo_id)
    _checar_permissao_validacao(request, processo)
    if not _processo_em_validacao(processo):
        return httprr(processo.get_absolute_url(), 'Este processo não está em etapa de validação.', tag='error')

    validar_url = reverse('rsc_tae:validar_processo', args=[processo.id])
    form = DataExercicioCargoForm(request.POST)
    if not form.is_valid():
        return httprr(validar_url, 'Informe uma data de exercício no cargo válida.', tag='error')

    ProcessoRSCTae.objects.filter(pk=processo.pk).update(data_exercicio_cargo=form.cleaned_data['data_exercicio_cargo'])
    return httprr(validar_url, 'Data de exercício no cargo atualizada.', tag='success')


def _contexto_avaliacao_com_data_exercicio(request, processo, title):
    """Monta o contexto de avaliação e acrescenta a data de exercício no cargo + a sinalização dos anexos anteriores."""
    ctx = _montar_contexto_avaliacao(request, processo, title=title)
    corrigir_pontos_temporais_avaliacao(ctx)
    enriquecer_anexos_data_exercicio(processo, ctx.get('linhas_avaliacao') or [])
    ctx['data_exercicio_cargo'] = data_exercicio_cargo_efetiva(processo)
    injetar_visibilidade_avaliadores(request, processo, ctx)
    return ctx


@rtr('rsc_tae/avaliar.html')
@login_required
@require_GET
def avaliar(request, processo_id):
    title = 'Avaliação RSC-TAE'
    processo = get_object_or_404(ProcessoRSCTae, pk=processo_id)

    _validar_acesso_avaliacao(request, processo)

    _verificar_prazos_expirados(processo)
    processo.refresh_from_db()

    return _contexto_avaliacao_com_data_exercicio(request, processo, title=title)


@rtr('rsc_tae/resumo_avaliacao.html')
@login_required
@require_GET
def resumo_avaliacao(request, processo_id):
    title = 'Resumo da avaliação RSC-TAE'
    processo = get_object_or_404(ProcessoRSCTae, pk=processo_id)

    _validar_acesso_resumo_avaliacao(request, processo)

    ctx = _contexto_avaliacao_com_data_exercicio(request, processo, title=title)
    return aplicar_totais_consolidados(processo, ctx)


@rtr('rsc_tae/ver_avaliadores.html')
@login_required
@require_GET
def ver_avaliadores(request, processo_id):
    title = 'Avaliadores do processo'
    processo = get_object_or_404(ProcessoRSCTae, pk=processo_id)

    _validar_acesso_resumo_avaliacao(request, processo)

    avaliadores = montar_avaliadores_contexto(processo)
    finalizado = processo.situacao in SituacaoProcesso.FINAIS
    try:
        vinculo_usuario = request.user.get_vinculo()
    except Exception:
        vinculo_usuario = None
    pode_ver_nomes = finalizado or bool(getattr(request.user, 'is_superuser', False)) or eh_membro_crsc_ativo(vinculo_usuario)
    if not pode_ver_nomes:
        rotulos = rotulos_anonimos_avaliadores(processo)
        for linha in avaliadores:
            linha['nome'] = rotulos.get(linha.get('vinculo_id'), 'Avaliador')

    return {'title': title, 'processo': processo, 'avaliadores': avaliadores}


@documento()
@rtr('rsc_tae/relatorio_avaliacao_pdf.html')
@login_required
@require_GET
def relatorio_avaliacao(request, processo_id):
    title = 'Relatório da avaliação RSC-TAE'
    processo = get_object_or_404(ProcessoRSCTae, pk=processo_id)

    _validar_acesso_resumo_avaliacao(request, processo)

    if processo.situacao not in SituacaoProcesso.FINAIS:
        raise PermissionDenied('Relatório disponível apenas para processos finalizados (deferido/indeferido).')

    ctx = _contexto_avaliacao_com_data_exercicio(request, processo, title=title)
    # Itens em que os avaliadores auxiliares divergiram: a pontuação final é definida pela CRSC.
    ctx['total_divergencias_crsc'] = len(_listar_divergencias_para_crsc(processo))
    return ctx


def _obter_vinculo_avaliador(request):
    """Retorna o vínculo do avaliador logado ou levanta PermissionDenied."""
    try:
        vinculo = request.user.get_vinculo()
    except Exception:
        vinculo = None
    if not vinculo:
        raise PermissionDenied('Vínculo do avaliador não encontrado.')
    return vinculo


def _pontos_item(linha, avaliacao_anexo_por_id):
    """Soma os pontos validados (deferidos) de um item; item temporal converte os meses de
    cada anexo em anos ('ano ou fração > 6 meses') isoladamente e soma os anos."""
    from rsc_tae.models.anexo import pontos_anexo

    item = linha.get('item')
    total = Decimal('0')
    for anexo in linha.get('anexos') or []:
        av = avaliacao_anexo_por_id.get(anexo.id)
        if av and av.situacao == SituacaoAvaliacaoItem.DEFERIDO:
            # A taxa (titular/substituto) vem do papel do próprio anexo.
            total += pontos_anexo(item, av.pontuacao_validada or Decimal('0'), getattr(anexo, 'papel', None))
    return total


def _pontos_validados_por_item(processo, vinculo_avaliador) -> dict:
    """{item_id: pontos validados} pelo avaliador no processo (itens temporais convertidos em anos)."""
    ctx = _montar_resumo_preenchimento(processo)
    avaliacoes_anexo = AvaliacaoAnexoRSCTae.objects.filter(anexo__processo=processo, avaliador_vinculo=vinculo_avaliador).select_related('anexo')
    avaliacao_anexo_por_id = {a.anexo_id: a for a in avaliacoes_anexo}
    return {linha['item'].id: _pontos_item(linha, avaliacao_anexo_por_id) for linha in ctx['linhas_preenchidas']}


def _ids_avaliadores(processo):
    """IDs dos vínculos avaliadores do processo (M2M atual ou avaliador_atual legado)."""
    try:
        avaliadores = list(processo.avaliadores.all())
    except Exception:
        avaliadores = []
    if not avaliadores:
        atual = getattr(processo, 'avaliador_atual', None)
        if atual:
            avaliadores = [atual]
    return [v.id for v in avaliadores if getattr(v, 'id', None)]


def _projecao_finalizacao(processo, vinculo_avaliador, sera_deferido):
    """Projeta o cenário de votos caso este avaliador finalize agora."""
    avaliadores_ids = _ids_avaliadores(processo)
    total_avaliadores = len(avaliadores_ids) or 1
    ids_para_query = avaliadores_ids or [vinculo_avaliador.id]

    finalizados_ids = set(
        AvaliacaoProcessoRSCTae.objects.filter(
            processo=processo, avaliador_vinculo_id__in=ids_para_query, substituido=False, data_finalizacao__isnull=False
        ).values_list('avaliador_vinculo_id', flat=True)
    )
    finalizara_processo_agora = set(ids_para_query).issubset(finalizados_ids | {vinculo_avaliador.id})

    anteriores = AvaliacaoProcessoRSCTae.objects.filter(
        processo=processo, avaliador_vinculo_id__in=ids_para_query, substituido=False, data_finalizacao__isnull=False
    ).exclude(avaliador_vinculo=vinculo_avaliador)
    deferidos_anteriores = anteriores.filter(resultado=SituacaoProcesso.DEFERIDO).count()
    indeferidos_anteriores = anteriores.filter(resultado=SituacaoProcesso.INDEFERIDO).count()

    sera_deferido_maioria = None
    if finalizara_processo_agora:
        total_deferidos = deferidos_anteriores + (1 if sera_deferido else 0)
        sera_deferido_maioria = bool(total_deferidos * 2 >= total_avaliadores)

    return {
        'avaliadores_ids': avaliadores_ids,
        'total_avaliadores': total_avaliadores,
        'finalizara_processo_agora': finalizara_processo_agora,
        'deferidos_anteriores': deferidos_anteriores,
        'indeferidos_anteriores': indeferidos_anteriores,
        'sera_deferido_maioria': sera_deferido_maioria,
    }


def _dados_finalizacao(processo, vinculo_avaliador) -> dict:
    """Reúne todos os dados computados exibidos/usados na finalização da avaliação.

    O resultado individual (``sera_deferido``) aplica TODOS os critérios do nível sobre os
    pontos validados: pontuação mínima (com saldo anterior — RN07), itens mínimos e
    requisito obrigatório (RN04).
    """
    anexos_total = RolSaberCompetenciaAnexo.objects.filter(processo=processo).count()
    anexos_analisados = AvaliacaoAnexoRSCTae.objects.filter(
        anexo__processo=processo,
        avaliador_vinculo=vinculo_avaliador,
        situacao__in=(SituacaoAvaliacaoItem.DEFERIDO, SituacaoAvaliacaoItem.INDEFERIDO),
    ).count()
    anexos_pendentes = max(0, anexos_total - anexos_analisados)

    criterios = verificar_criterios_nivel(processo, _pontos_validados_por_item(processo, vinculo_avaliador))
    sera_deferido = criterios['atende_todos']

    dados = {
        'anexos_total': anexos_total,
        'anexos_analisados': anexos_analisados,
        'anexos_pendentes': anexos_pendentes,
        'pode_finalizar': anexos_pendentes == 0,
        # Persistido em AvaliacaoProcessoRSCTae.pontuacao_final: apenas os itens validados (sem saldo).
        'total_pontos_validados': criterios['total_pontos_itens'],
        'itens_validados': criterios['itens_validados'],
        'pontos_requeridos_nivel': criterios['pontos_minimos'],
        'itens_requeridos': criterios['itens_minimos'],
        'criterios': criterios,
        'sera_deferido': sera_deferido,
        'motivos_criterios_nao_atingidos': [] if sera_deferido else _lista_motivos_criterios_nao_atingidos(criterios),
    }
    dados.update(_projecao_finalizacao(processo, vinculo_avaliador, sera_deferido))
    return dados


def _encerrar_processo_se_todos_finalizaram(processo, vinculo_avaliador, avaliadores_ids):
    """Se todos os avaliadores já finalizaram, encaminha o processo à CRSC. Retorna True nesse caso."""
    avaliadores_ids_db = avaliadores_ids or [vinculo_avaliador.id]
    finalizadas = AvaliacaoProcessoRSCTae.objects.filter(
        processo=processo, avaliador_vinculo_id__in=avaliadores_ids_db, substituido=False, data_finalizacao__isnull=False
    ).count()
    if finalizadas != (len(avaliadores_ids_db) or 1):
        return False

    processo.transicionar(
        SituacaoProcesso.AGUARDANDO_CRSC,
        motivo='Todos os avaliadores finalizaram — processo encaminhado para deliberação da CRSC.',
        por_vinculo=vinculo_avaliador,
        origem=OrigemTransicao.AUTOMATICO,
        campos_extras={'data_entrada_crsc': timezone.now()},
    )
    return True


def _persistir_finalizacao(processo, vinculo_avaliador, dados):
    """Persiste a finalização (assinatura) do avaliador e retorna o redirect adequado."""
    resultado_individual = SituacaoProcesso.DEFERIDO if dados['sera_deferido'] else SituacaoProcesso.INDEFERIDO
    changelist_url = reverse('admin:rsc_tae_processorsctae_changelist')

    with transaction.atomic():
        avaliacao_db, _ = AvaliacaoProcessoRSCTae.objects.get_or_create(processo=processo, avaliador_vinculo=vinculo_avaliador)
        if getattr(avaliacao_db, 'data_finalizacao', None):
            return httprr(changelist_url, 'Sua avaliação já foi finalizada.', tag='warning')

        AvaliacaoProcessoRSCTae.objects.filter(pk=avaliacao_db.pk).update(
            pontuacao_final=dados['total_pontos_validados'],
            itens_validados=dados['itens_validados'],
            resultado=resultado_individual,
            data_finalizacao=timezone.now(),
            finalizada=True,
        )
        AvaliacaoProcessoRSCTae.gerar_assinatura(avaliacao_db)

        if _encerrar_processo_se_todos_finalizaram(processo, vinculo_avaliador, dados['avaliadores_ids']):
            return httprr(changelist_url, 'Avaliação finalizada e assinada. Processo encaminhado à CRSC para deliberação.', tag='success')

    return httprr(changelist_url, 'Sua avaliação foi finalizada e assinada. Aguardando finalização dos demais avaliadores.', tag='success')


def _processar_finalizacao(request, processo, vinculo_avaliador, form, dados):
    """Trata o POST de finalização. Retorna um HttpResponse ou None para re-renderizar o form."""
    if not dados['pode_finalizar']:
        return httprr(
            '.',
            f'Não é possível finalizar a avaliação: existem {dados["anexos_pendentes"]} arquivo(s) pendente(s) de análise.',
            tag='error',
            close_popup=False,
        )
    if not form.is_valid():
        return None
    return _persistir_finalizacao(processo, vinculo_avaliador, dados)


def _contexto_finalizar(title, processo, form, dados):
    """Monta o contexto do template de finalização (GET ou POST com form inválido)."""
    return {'title': title, 'processo': processo, 'form': form, **dados}


@rtr('rsc_tae/finalizar_avaliacao.html')
@login_required
def finalizar_avaliacao(request, processo_id):
    title = 'Finalizar avaliação'
    processo = get_object_or_404(ProcessoRSCTae, pk=processo_id)

    _validar_acesso_avaliacao(request, processo)

    vinculo_avaliador = _obter_vinculo_avaliador(request)

    avaliacao_processo, _ = AvaliacaoProcessoRSCTae.objects.get_or_create(processo=processo, avaliador_vinculo=vinculo_avaliador)
    if getattr(avaliacao_processo, 'data_finalizacao', None):
        return httprr(reverse('admin:rsc_tae_processorsctae_changelist'), 'Sua avaliação já foi finalizada.', tag='warning')

    dados = _dados_finalizacao(processo, vinculo_avaliador)
    form = FinalizarAvaliacaoForm(request.POST or None, request=request)

    if request.method == 'POST':
        resposta = _processar_finalizacao(request, processo, vinculo_avaliador, form, dados)
        if resposta is not None:
            return resposta

    return _contexto_finalizar(title, processo, form, dados)


def _aplicar_banco_pontos_deliberacao(processo, resultado, pontuacao_efetiva, vinculo_deliberante):
    """Credita o excedente (deferido) ou devolve o saldo anterior (indeferido) no banco de pontos do servidor."""
    try:
        pontuacao_nivel = processo.nivel_requisitado.pontuacao_minima or Decimal('0')
        saldo_utilizado = processo.saldo_pontuacao_anterior or Decimal('0')
        banco = BancoPontosRSCTae.get_or_create_for_vinculo(processo.vinculo)
        if resultado == SituacaoProcesso.DEFERIDO:
            excedente = max(Decimal('0'), pontuacao_efetiva - pontuacao_nivel)
            if excedente > 0:
                banco.creditar(
                    excedente,
                    tipo=MovimentoBancoPontosRSCTae.TIPO_CREDITO_DEFERIMENTO,
                    processo=processo,
                    descricao=f'Excedente do processo #{processo.pk} (deferido). Pontuação: {pontuacao_efetiva}, mínimo: {pontuacao_nivel}.',
                    realizado_por=vinculo_deliberante,
                )
        elif saldo_utilizado > 0:
            banco.creditar(
                saldo_utilizado,
                tipo=MovimentoBancoPontosRSCTae.TIPO_DEVOLUCAO_INDEFERIMENTO,
                processo=processo,
                descricao=f'Devolução do saldo utilizado no processo #{processo.pk} (indeferido).',
                realizado_por=vinculo_deliberante,
            )
    except Exception:
        logging.getLogger(__name__).exception('Erro ao atualizar banco de pontos após deliberação CRSC do processo %s', processo.pk)


def _consolidar_deliberacao_final(request, processo, resultado, pontuacao_consolidada, vinculo_deliberante, votos, finalizacao_manual=False):
    """Cria a deliberação consolidada, assina, transiciona o processo (deferido/indeferido) e aplica o banco de pontos.

    A criação é idempotente: o processo é travado e a existência da deliberação reconferida
    dentro da transação. As checagens que antecedem esta função (``pode_deliberar_crsc``, o
    estado da votação) rodam antes do POST e não impedem que dois membros — ou dois cliques
    do mesmo membro — cheguem aqui ao mesmo tempo, o que violava o ``OneToOne`` de
    ``DeliberacaoCRSCRSCTae.processo`` com um ``IntegrityError`` na segunda requisição.
    """
    labels = {SituacaoProcesso.DEFERIDO: 'Deferido', SituacaoProcesso.INDEFERIDO: 'Indeferido'}
    justificativas = '; '.join((v.justificativa or '').strip() for v in votos if v.resultado == resultado and (v.justificativa or '').strip())
    prefixo = 'Finalização manual (reconsolidação a partir dos votos existentes). ' if finalizacao_manual else ''
    justificativa = f'{prefixo}Deliberação final por maioria simples. {justificativas}'.strip()

    # No indeferimento, consolida a união distinta dos motivos marcados pelos votos de
    # indeferimento (ordem canônica do Decreto) — exibida no parecer conclusivo.
    motivos_consolidados = []
    if resultado == SituacaoProcesso.INDEFERIDO:
        motivos_consolidados = MotivoIndeferimento.consolidar(v.motivos_indeferimento for v in votos if v.resultado == SituacaoProcesso.INDEFERIDO)

    with transaction.atomic():
        ProcessoRSCTae.objects.select_for_update().get(pk=processo.pk)
        if DeliberacaoCRSCRSCTae.objects.filter(processo=processo).exists():
            return httprr(
                reverse('admin:rsc_tae_processorsctae_changelist'),
                'A deliberação final deste processo já havia sido consolidada.',
                tag='warning',
            )

        deliberacao = DeliberacaoCRSCRSCTae.objects.create(
            processo=processo,
            resultado=resultado,
            pontuacao_final_crsc=pontuacao_consolidada,
            justificativa=justificativa,
            motivos_indeferimento=motivos_consolidados,
            deliberado_por_vinculo=vinculo_deliberante,
            finalizacao_manual=finalizacao_manual,
            ip_deliberacao=get_client_ip(request),
            user_agent=(request.META.get('HTTP_USER_AGENT') or '')[:500],
        )
        deliberacao.gerar_assinatura()

        motivo_transicao = f'Deliberação final da CRSC ({labels[resultado]}) por maioria dos avaliadores.'
        if finalizacao_manual:
            motivo_transicao = f'Finalização manual da deliberação da CRSC ({labels[resultado]}) a partir dos votos existentes.'
        processo.transicionar(
            resultado,
            motivo=motivo_transicao,
            por_vinculo=vinculo_deliberante,
            origem=OrigemTransicao.MANUAL,
            campos_extras={
                'avaliacao_finalizada_por': vinculo_deliberante,
                'data_finalizacao_avaliacao': timezone.now(),
                'avaliacao_motivo_indeferimento': justificativa if resultado == SituacaoProcesso.INDEFERIDO else '',
            },
        )
        _aplicar_banco_pontos_deliberacao(processo, resultado, pontuacao_consolidada or Decimal('0'), vinculo_deliberante)

    return httprr(
        reverse('admin:rsc_tae_processorsctae_changelist'),
        f'Deliberação final registrada por maioria. Processo {labels[resultado]}.',
        tag='success',
    )


def _lista_motivos_criterios_nao_atingidos(criterios: dict) -> list[str]:
    """Lista dos critérios do nível não atingidos após a avaliação (um motivo por item).

    Aceita tanto o dict de ``verificar_criterios_nivel`` quanto o de ``resumo_final_consolidado``
    (ambos expõem ``pontos_minimos``/``itens_minimos``).
    """
    motivos = []
    if not criterios['atingiu_pontos']:
        total = str(criterios['total_pontos'].quantize(Decimal('0.01'))).replace('.', ',')
        minimo = str(criterios['pontos_minimos'].quantize(Decimal('0.01'))).replace('.', ',')
        motivos.append(f'pontuação insuficiente ({total} de {minimo})')
    if not criterios['atingiu_itens']:
        motivos.append(f'quantidade de itens validados insuficiente ({criterios["itens_validados"]} de {criterios["itens_minimos"]})')
    if not criterios['atingiu_requisito_obrigatorio']:
        labels = ', '.join(criterios['labels_requisitos_obrigatorios'])
        motivos.append(f'nenhum item validado nos requisitos obrigatórios do nível ({labels})')
    return motivos


def _motivos_criterios_nao_atingidos(criterios: dict) -> str:
    """Texto (motivos unidos em uma frase) dos critérios não atingidos — mensagem de bloqueio do deferimento."""
    return '; '.join(_lista_motivos_criterios_nao_atingidos(criterios)) + '.'


def _impedimento_voto_crsc(aguardando_desempate: bool, eh_presidente: bool, is_desempate: bool, cota: dict) -> str | None:
    """Motivo que impede este membro de votar, ou ``None`` quando ele pode.

    A cota da categoria não alcança o voto de desempate: ele é prerrogativa do presidente e
    contá-lo deixaria o empate sem saída quando a categoria dele já tivesse gasto a cota.

    Args:
        aguardando_desempate: Se a votação empatou e espera o presidente.
        eh_presidente: Se o usuário é presidente da comissão ativa.
        is_desempate: Se o voto a registrar é o de desempate.
        cota: Retorno de ``status_cota_categoria`` para o escopo em questão.

    Returns:
        A mensagem a exibir, ou ``None`` se não há impedimento.
    """
    if aguardando_desempate and not eh_presidente:
        return 'Empate — aguardando o voto de desempate do presidente da comissão.'
    if not is_desempate and cota['bloqueado']:
        return cota['motivo']
    return None


def _impedimento_gravacao_voto(votos: list, status: dict, vinculo, is_desempate: bool) -> str | None:
    """Motivo que impede gravar o voto no ponto de escrita, ou ``None``.

    Chamado com o processo travado. A checagem da tela roda antes do POST, e nesse intervalo um
    voto concorrente pode ter fechado o escopo, criado ou desfeito um empate, ou gasto a cota.

    Args:
        votos: Votos do escopo relidos dentro da transação.
        status: ``status_deliberacao_item``/``status_deliberacao_final`` calculado sobre ``votos``.
        vinculo: Vínculo de quem vota.
        is_desempate: Se o voto a registrar é o de desempate (não consome cota).

    Returns:
        A mensagem a exibir, ou ``None`` se o voto pode ser gravado.
    """
    if status['fechado']:
        return 'Esta votação foi consolidada por outro voto enquanto você preenchia o seu.'
    if status['aguardando_desempate'] != is_desempate:
        return 'A votação mudou enquanto você preenchia o seu voto. Abra a tela novamente para ver a situação atual.'
    if is_desempate:
        return None
    return status_cota_categoria(votos, vinculo)['motivo'] or None


def _registrar_voto_deliberacao_final(request, processo, vinculo, form, status_antes, quantidade, pontuacao_padrao, is_desempate, resumo_final):
    """Grava o voto (normal ou de desempate) na deliberação final e, ao fechar, consolida a decisão."""
    voltar_url = reverse('rsc_tae:deliberar_crsc', kwargs={'processo_id': processo.id})

    if status_antes['fechado']:
        return httprr(voltar_url, 'A deliberação final já está consolidada. Não é possível votar.', tag='warning')
    if status_antes['aguardando_desempate'] and not is_desempate:
        return httprr(voltar_url, 'Empate — aguardando o voto de desempate do presidente da comissão.', tag='warning')

    resultado = int(form.cleaned_data['resultado'])
    if resultado == SituacaoProcesso.DEFERIDO and not resumo_final['deferido']:
        return httprr(
            voltar_url,
            f'Não é possível votar pelo deferimento — critérios do nível não atingidos após a avaliação: {_motivos_criterios_nao_atingidos(resumo_final)}',
            tag='error',
        )
    justificativa = (form.cleaned_data.get('justificativa') or '').strip()
    motivos_indeferimento = sorted(int(m) for m in (form.cleaned_data.get('motivos_indeferimento') or []))

    # Indeferir zera a pontuação; deferir sem informar usa a pontuação final consolidada como padrão.
    if resultado == SituacaoProcesso.INDEFERIDO:
        pontuacao = Decimal('0')
    else:
        pontuacao = form.cleaned_data.get('pontuacao_final_crsc')
        if pontuacao is None:
            pontuacao = pontuacao_padrao

    # Estado da votação e cota reconferidos com o processo travado: a checagem feita ao montar a
    # tela roda antes do POST, e um voto concorrente pode ter fechado o escopo ou gasto a cota.
    with transaction.atomic():
        ProcessoRSCTae.objects.select_for_update().get(pk=processo.pk)
        votos = list(VotoDeliberacaoFinalRSCTae.objects.filter(processo=processo).select_related('deliberado_por_vinculo__pessoa'))
        impedimento = _impedimento_gravacao_voto(votos, status_deliberacao_final(votos, quantidade), vinculo, is_desempate)
        if impedimento:
            return httprr(voltar_url, impedimento, tag='error')

        voto, _created = VotoDeliberacaoFinalRSCTae.objects.update_or_create(
            processo=processo,
            deliberado_por_vinculo=vinculo,
            desempate=is_desempate,
            defaults={
                'resultado': resultado,
                'pontuacao_final': pontuacao,
                'justificativa': justificativa,
                'motivos_indeferimento': motivos_indeferimento,
                'ip': get_client_ip(request),
                'user_agent': (request.META.get('HTTP_USER_AGENT') or '')[:255],
            },
        )

    voto.gerar_assinatura()

    votos = list(VotoDeliberacaoFinalRSCTae.objects.filter(processo=processo))
    status = status_deliberacao_final(votos, quantidade)

    if not status['fechado']:
        if status['aguardando_desempate']:
            return httprr(voltar_url, 'Voto registrado. Empate — aguardando voto de desempate do presidente.', tag='warning')
        faltam = quantidade - status['total']
        return httprr(voltar_url, f'Voto registrado. Faltam {faltam} para o quórum.', tag='success')

    if status['resultado'] == SituacaoProcesso.DEFERIDO and not resumo_final['deferido']:
        return httprr(
            voltar_url,
            f'Deliberação não consolidada: a maioria votou pelo deferimento, mas os critérios do nível não foram atingidos após a avaliação ({_motivos_criterios_nao_atingidos(resumo_final)}). Revise os votos antes de consolidar.',
            tag='error',
        )

    return _consolidar_deliberacao_final(request, processo, status['resultado'], status['pontuacao_consolidada'], vinculo, votos)


def _finalizar_deliberacao_manual(request, processo, vinculo, status_final, divergencias_pendentes, resumo_final, votos):
    """Consolida a deliberação final a partir dos votos já registrados (sem novo voto).

    Usado quando o quórum já está fechado mas não há deliberação consolidada — por exemplo,
    após reverter apenas a finalização mantendo os votos dos membros. Reaproveita as mesmas
    validações e o consolidador do fluxo normal de voto.
    """
    voltar_url = reverse('rsc_tae:deliberar_crsc', kwargs={'processo_id': processo.id})
    if divergencias_pendentes > 0:
        return httprr(voltar_url, f'Consolide as {divergencias_pendentes} divergência(s) de item antes de finalizar a deliberação.', tag='error')
    if not status_final['fechado']:
        return httprr(voltar_url, 'A deliberação final ainda não atingiu quórum/maioria para ser finalizada.', tag='warning')

    resultado = status_final['resultado']
    if resultado == SituacaoProcesso.DEFERIDO and not resumo_final['deferido']:
        return httprr(
            voltar_url,
            f'Não é possível finalizar como deferido — critérios do nível não atingidos após a avaliação: {_motivos_criterios_nao_atingidos(resumo_final)}',
            tag='error',
        )
    return _consolidar_deliberacao_final(request, processo, resultado, status_final['pontuacao_consolidada'], vinculo, votos, finalizacao_manual=True)


@rtr('rsc_tae/deliberar_crsc.html')
@login_required
def deliberar_crsc(request, processo_id):
    """Tela de deliberação da CRSC: consolida as divergências de item e registra o voto final.

    Reúne, na mesma página, as divergências de avaliação pendentes de quórum, o voto de cada
    membro na deliberação final e — quando o problema só o servidor resolve — a devolução para
    correção, visível a todo membro e executável apenas pelo presidente.

    Args:
        request: Requisição em curso.
        processo_id: Identificador do processo em deliberação.

    Returns:
        Contexto da tela, ou o redirecionamento do voto/finalização quando o POST é válido.

    Raises:
        PermissionDenied: Se o usuário não for membro ativo da CRSC ou o processo não estiver
            em deliberação.
    """
    title = 'Deliberação da CRSC — RSC-TAE'
    processo = get_object_or_404(ProcessoRSCTae, pk=processo_id)

    perms = PermissoesProcesso(request, processo)
    if not perms.pode_deliberar_crsc:
        raise PermissionDenied('Sem permissão para registrar deliberação da CRSC neste processo.')

    vinculo_deliberante = _vinculo_ou_none(request)
    if not vinculo_deliberante:
        raise PermissionDenied('Vínculo do usuário não encontrado.')

    ctx_avaliacao = _contexto_avaliacao_com_data_exercicio(request, processo, title=title)

    divergencias = _listar_divergencias_para_crsc(processo)
    total_divergencias = len(divergencias)
    divergencias_pendentes = sum(1 for d in divergencias if not d['status_deliberacao']['fechado'])

    quantidade = quantidade_deliberacoes_item()
    votos_finais = list(
        VotoDeliberacaoFinalRSCTae.objects.filter(processo=processo).select_related('deliberado_por_vinculo__pessoa').order_by('data_deliberacao')
    )
    status_final = status_deliberacao_final(votos_finais, quantidade)
    eh_presidente_ = perms.eh_presidente_comissao
    aguardando_final = status_final['aguardando_desempate']
    # Em empate, o voto que o presidente registra é de desempate.
    is_desempate_final = aguardando_final and eh_presidente_

    cota_final = status_cota_categoria(votos_finais, vinculo_deliberante)
    impedimento_final = _impedimento_voto_crsc(aguardando_final, eh_presidente_, is_desempate_final, cota_final)

    meu_voto_final = next((v for v in votos_finais if not v.desempate and v.deliberado_por_vinculo_id == vinculo_deliberante.id), None)
    voto_ref = (
        next((v for v in votos_finais if v.desempate and v.deliberado_por_vinculo_id == vinculo_deliberante.id), None)
        if is_desempate_final
        else meu_voto_final
    )

    resumo_final = resumo_final_consolidado(processo, divergencias)
    pontuacao_padrao = resumo_final['total_pontos']

    if voto_ref:
        initial = {
            'resultado': str(voto_ref.resultado),
            'pontuacao_final_crsc': voto_ref.pontuacao_final,
            'justificativa': voto_ref.justificativa,
            'motivos_indeferimento': [str(m) for m in (voto_ref.motivos_indeferimento or [])],
        }
    else:
        # Pré-preenche com a pontuação final consolidada; se deferir sem alterar, esse valor é usado.
        initial = {'pontuacao_final_crsc': pontuacao_padrao}
    form = VotoDeliberacaoFinalForm(request.POST or None, request=request, initial=initial)

    if not resumo_final['deferido']:
        # O Decreto não permite deferir com os critérios do nível não atingidos (o inverso — Art. 13, IV — é permitido).
        form.fields['resultado'].choices = ((str(SituacaoProcesso.INDEFERIDO), 'Indeferido'),)

    # Finalização manual: quando os votos já fecham o quórum mas não há deliberação consolidada
    # (ex.: após reverter apenas a finalização), um membro pode consolidar com os votos existentes.
    pode_finalizar_manual = perms.pode_deliberar_crsc and divergencias_pendentes == 0 and status_final['fechado']

    if request.method == 'POST' and request.POST.get('acao') == 'finalizar_manual':
        return _finalizar_deliberacao_manual(request, processo, vinculo_deliberante, status_final, divergencias_pendentes, resumo_final, votos_finais)

    if request.method == 'POST' and form.is_valid():
        if divergencias_pendentes > 0:
            return httprr(
                reverse('rsc_tae:deliberar_crsc', kwargs={'processo_id': processo.id}),
                f'Consolide as {divergencias_pendentes} divergência(s) de item (atingir o quórum em cada uma) antes de votar a deliberação final.',
                tag='error',
            )
        return _registrar_voto_deliberacao_final(
            request, processo, vinculo_deliberante, form, status_final, quantidade, pontuacao_padrao, is_desempate_final, resumo_final
        )

    ctx = dict(ctx_avaliacao) if isinstance(ctx_avaliacao, dict) else {}
    aplicar_notas_consolidadas_crsc(ctx, divergencias)
    ctx.update(
        {
            'title': title,
            'processo': processo,
            'form': form,
            'divergencias': divergencias,
            'total_divergencias': total_divergencias,
            'divergencias_pendentes': divergencias_pendentes,
            'votos_finais': votos_finais,
            'status_final': status_final,
            'meu_voto_final': meu_voto_final,
            'resumo_final': resumo_final,
            'eh_presidente': eh_presidente_,
            'is_desempate_final': is_desempate_final,
            'pode_votar_final': divergencias_pendentes == 0 and not status_final['fechado'] and impedimento_final is None,
            'cota_categoria_final': cota_final,
            'impedimento_voto_final': impedimento_final,
            'pode_finalizar_manual': pode_finalizar_manual,
            # A devolução aparece a todo membro (para saber que a alternativa existe) e só o
            # presidente a executa — ver `PermissoesProcesso.pode_devolver_para_correcao_crsc`.
            'pode_ver_devolucao_crsc': perms.pode_ver_devolucao_crsc,
            'pode_devolver_para_correcao_crsc': perms.pode_devolver_para_correcao_crsc,
        }
    )
    return ctx


@rtr('rsc_tae/deliberar_item_crsc.html')
@login_required
def deliberar_item_crsc(request, processo_id, anexo_id):
    """Popup para a CRSC deliberar sobre um anexo com divergência de avaliação."""
    title = 'Deliberação sobre item — CRSC'
    processo = get_object_or_404(ProcessoRSCTae, pk=processo_id)

    perms = PermissoesProcesso(request, processo)
    if not perms.pode_deliberar_crsc:
        raise PermissionDenied('Sem permissão para registrar deliberação da CRSC neste processo.')

    try:
        vinculo_deliberante = request.user.get_vinculo()
    except Exception:
        vinculo_deliberante = None
    if not vinculo_deliberante:
        raise PermissionDenied('Vínculo do usuário não encontrado.')

    anexo = get_object_or_404(
        RolSaberCompetenciaAnexo.objects.select_related('rol_saber_competencia__grupo__requisito'),
        processo=processo,
        pk=anexo_id,
    )

    avaliacoes = list(
        AvaliacaoAnexoRSCTae.objects.filter(anexo=anexo, avaliador_vinculo__isnull=False)
        .select_related('avaliador_vinculo__pessoa')
        .order_by('avaliador_vinculo__pessoa__nome')
    )

    votos = list(
        DeliberacaoItemCRSCRSCTae.objects.filter(processo=processo, anexo=anexo)
        .select_related('deliberado_por_vinculo__pessoa')
        .order_by('data_deliberacao')
    )
    status_item = status_deliberacao_item(votos, quantidade_deliberacoes_item())

    # Trava: quando a quantidade configurada é atingida (sem empate ou já desempatado), fica consolidado.
    if status_item['fechado']:
        return httprr(
            '..',
            'Este item já atingiu a quantidade de deliberações e está consolidado. Não é possível alterar.',
            tag='warning',
            close_popup=False,
        )

    eh_presidente_ = perms.eh_presidente_comissao
    aguardando = status_item['aguardando_desempate']
    # Em empate, o voto que o presidente registra é de desempate; caso contrário, é voto normal.
    is_desempate = aguardando
    cota = status_cota_categoria(votos, vinculo_deliberante)
    impedimento = _impedimento_voto_crsc(aguardando, eh_presidente_, is_desempate, cota)
    pode_votar = impedimento is None

    meu_voto = next((v for v in votos if not v.desempate and v.deliberado_por_vinculo_id == vinculo_deliberante.id), None)
    voto_ref = next((v for v in votos if v.desempate and v.deliberado_por_vinculo_id == vinculo_deliberante.id), None) if is_desempate else meu_voto

    initial = {}
    if voto_ref:
        initial = {'decisao': str(voto_ref.decisao), 'pontuacao_crsc': voto_ref.pontuacao_crsc, 'justificativa': voto_ref.justificativa}

    form = DeliberacaoItemCRSCForm(request.POST or None, initial=initial)
    _ajustar_campo_unidades_item(form, anexo)

    if request.method == 'POST' and form.is_valid():
        if not pode_votar:
            return httprr('.', impedimento, tag='warning', close_popup=False)
        return _registrar_voto_item(request, processo, anexo, vinculo_deliberante, form, is_desempate)

    return {
        'title': title,
        'processo': processo,
        'anexo': anexo,
        'avaliacoes': avaliacoes,
        'votos': votos,
        'status_item': status_item,
        'meu_voto': meu_voto,
        'form': form,
        'aguardando_desempate': aguardando,
        'eh_presidente': eh_presidente_,
        'is_desempate': is_desempate,
        'pode_votar': pode_votar,
        'cota_categoria': cota,
        'impedimento_voto': impedimento,
        'SituacaoAvaliacaoItem': SituacaoAvaliacaoItem,
    }


def _ajustar_campo_unidades_item(form, anexo):
    """Ajusta rótulo e help_text do campo de unidades da deliberação de item conforme o tipo do item.

    Item temporal: o valor é preenchido em MESES (mesma unidade validada pelos avaliadores).
    Item comum: o valor é preenchido na unidade de medida do item (ex.: hora, projeto).
    """
    campo = form.fields['pontuacao_crsc']
    if anexo.rol_saber_competencia.item_temporal:
        campo.label = 'Duração reconhecida (em meses)'
        campo.help_text = mark_safe(
            'Item temporal: informe a duração reconhecida <strong>em meses</strong> ao deferir. '
            'A conversão em anos (“ano ou fração acima de 6 meses”) e a pontuação são recalculadas automaticamente. '
            'Ao indeferir, conta como 0.'
        )
    else:
        unidade = anexo.rol_saber_competencia.unidade_medida or 'unidade'
        campo.help_text = mark_safe(
            f'Informe as <strong>unidades</strong> reconhecidas ao deferir (unidade do item: {unidade}). Ao indeferir, conta como 0.'
        )


def _registrar_voto_item(request, processo, anexo, vinculo, form, is_desempate):
    """Grava o voto (normal ou de desempate) de um membro/presidente sobre um item divergente.

    Estado do item e cota da categoria são reconferidos aqui, dentro da transação e com o processo
    travado: a verificação da view roda antes do POST, e um voto concorrente pode ter fechado o
    item ou gasto a cota nesse intervalo.
    """
    with transaction.atomic():
        ProcessoRSCTae.objects.select_for_update().get(pk=processo.pk)
        votos = list(DeliberacaoItemCRSCRSCTae.objects.filter(processo=processo, anexo=anexo).select_related('deliberado_por_vinculo__pessoa'))
        status = status_deliberacao_item(votos, quantidade_deliberacoes_item())
        impedimento = _impedimento_gravacao_voto(votos, status, vinculo, is_desempate)
        if impedimento:
            return httprr('..', impedimento, tag='error', close_popup=False)

        voto, _created = DeliberacaoItemCRSCRSCTae.objects.update_or_create(
            processo=processo,
            anexo=anexo,
            deliberado_por_vinculo=vinculo,
            desempate=is_desempate,
            defaults={
                'decisao': int(form.cleaned_data['decisao']),
                'pontuacao_crsc': form.cleaned_data.get('pontuacao_crsc'),
                'justificativa': (form.cleaned_data.get('justificativa') or '').strip(),
            },
        )

    voto.gerar_assinatura()
    return httprr('..', 'Voto de desempate registrado.' if is_desempate else 'Voto registrado.', tag='success', close_popup=True)


@rtr('rsc_tae/avaliar_arquivo.html')
@login_required
def avaliar_arquivo(request, processo_id, anexo_id):
    title = 'Avaliar Arquivo RSC-TAE'
    processo = get_object_or_404(ProcessoRSCTae, pk=processo_id)

    _validar_acesso_avaliacao(request, processo)

    try:
        vinculo_avaliador = request.user.get_vinculo()
    except Exception:
        vinculo_avaliador = None
    if not vinculo_avaliador:
        raise PermissionDenied('Vínculo do avaliador não encontrado.')

    avaliacao_processo, _ = AvaliacaoProcessoRSCTae.objects.get_or_create(processo=processo, avaliador_vinculo=vinculo_avaliador)
    if getattr(avaliacao_processo, 'data_finalizacao', None):
        return httprr('..', 'Sua avaliação já foi finalizada e não pode mais ser alterada.', tag='warning', close_popup=False)

    anexo = get_object_or_404(
        RolSaberCompetenciaAnexo.objects.select_related('rol_saber_competencia__grupo__requisito'),
        processo=processo,
        pk=anexo_id,
    )

    avaliacao_anexo, _created = AvaliacaoAnexoRSCTae.objects.get_or_create(
        anexo=anexo,
        avaliador_vinculo=vinculo_avaliador,
        defaults={'data_ultima_alteracao': timezone.now()},
    )

    if request.method == 'POST':
        acao = (request.POST.get('acao') or '').strip().lower()
        if acao not in ('validar', 'deferir', 'indeferir', 'pendente'):
            return httprr('..', 'Ação inválida.', tag='error')

        observacao = (request.POST.get('observacao') or '').strip()

        raw = (request.POST.get('pontuacao_validada') or '').strip().replace(',', '.')
        if raw == '':
            pontuacao_validada = anexo.pontuacao
        else:
            try:
                pontuacao_validada = Decimal(raw)
            except Exception:
                return httprr('..', 'Pontuação validada inválida.', tag='error')
            if pontuacao_validada < 0:
                return httprr('..', 'Pontuação validada deve ser maior ou igual a zero.', tag='error')

        if acao in ('validar', 'deferir'):
            situacao = SituacaoAvaliacaoItem.DEFERIDO
            if pontuacao_validada != anexo.pontuacao and not observacao:
                return httprr('.', 'Informe uma observação/justificativa ao alterar a pontuação.', tag='error', close_popup=False)
        elif acao == 'indeferir':
            situacao = SituacaoAvaliacaoItem.INDEFERIDO
            if not observacao:
                return httprr('.', 'Informe uma observação/justificativa para indeferir o arquivo.', tag='error', close_popup=False)
        else:
            situacao = SituacaoAvaliacaoItem.PENDENTE

        if situacao == SituacaoAvaliacaoItem.INDEFERIDO:
            pontuacao_validada = Decimal('0')

        AvaliacaoAnexoRSCTae.objects.filter(pk=avaliacao_anexo.pk).update(
            situacao=situacao,
            pontuacao_validada=pontuacao_validada,
            observacao=observacao,
            avaliado_por=request.user,
            avaliador_vinculo=vinculo_avaliador,
            data_ultima_alteracao=timezone.now(),
            ip_avaliacao=get_client_ip(request),
            user_agent=(request.META.get('HTTP_USER_AGENT') or '')[:255],
        )

        # Busca próximo anexo pendente (sem avaliação ou com situação PENDENTE)
        avaliados_ids = AvaliacaoAnexoRSCTae.objects.filter(
            anexo__processo=processo,
            avaliador_vinculo=vinculo_avaliador,
            situacao__in=(SituacaoAvaliacaoItem.DEFERIDO, SituacaoAvaliacaoItem.INDEFERIDO),
        ).values_list('anexo_id', flat=True)

        proximo_anexo = RolSaberCompetenciaAnexo.objects.filter(processo=processo).exclude(pk__in=avaliados_ids).order_by('pk').first()

        if proximo_anexo:
            from django.urls import reverse

            proxima_url = reverse(
                'rsc_tae:avaliar_arquivo',
                kwargs={
                    'processo_id': processo.pk,
                    'anexo_id': proximo_anexo.pk,
                },
            )
            return httprr(proxima_url, 'Avaliação salva. Próximo item.', tag='success', close_popup=False)

        return httprr('..', 'Todos os arquivos foram avaliados.', tag='success', close_popup=True)

    criterio = anexo.rol_saber_competencia

    # Taxa efetiva conforme o papel do anexo (titular/substituto); itens sem papel usam a taxa única.
    from rsc_tae.models.anexo import taxa_por_papel

    pontuacao_unidade = taxa_por_papel(criterio, getattr(anexo, 'papel', None))
    unidades_informadas = getattr(anexo, 'pontuacao', None) or Decimal('0')
    unidades_validadas = getattr(avaliacao_anexo, 'pontuacao_validada', None) or Decimal('0')
    pontos_informados = pontuacao_unidade * unidades_informadas
    pontos_validados = pontuacao_unidade * unidades_validadas

    return {
        'title': title,
        'processo': processo,
        'anexo': anexo,
        'criterio': criterio,
        'pontuacao_unidade': pontuacao_unidade,
        'unidades_informadas': unidades_informadas,
        'unidades_validadas': unidades_validadas,
        'pontos_informados': pontos_informados,
        'pontos_validados': pontos_validados,
        'avaliacao_anexo': avaliacao_anexo,
    }


@rtr('rsc_tae/remanejar_avaliador.html')
@login_required
def remanejar_avaliador(request, processo_id):
    title = 'Remanejar Avaliador'
    processo = get_object_or_404(ProcessoRSCTae, pk=processo_id)

    vinculo_usuario = _vinculo_ou_none(request)
    if not vinculo_usuario or not eh_membro_crsc_ativo(vinculo_usuario):
        raise PermissionDenied('Apenas membros ativos da CRSC-TAE podem remanejar avaliadores.')

    if processo.situacao != SituacaoProcesso.EM_ANALISE:
        return httprr(
            processo.get_absolute_url(),
            'O remanejamento de avaliadores só é permitido enquanto o processo está Em Análise.',
            tag='error',
        )

    if not processo.avaliadores.exists():
        return httprr(
            processo.get_absolute_url(),
            'Este processo não possui avaliadores designados.',
            tag='error',
        )

    form = RemanejamentoAvaliadorForm(request.POST or None, processo=processo)

    if request.method == 'POST' and form.is_valid():
        remover_id = int(form.cleaned_data['avaliador_remover'])
        avaliador_incluir = form.cleaned_data['avaliador_incluir']
        motivo = form.cleaned_data['motivo']

        try:
            vinculo_remover = processo.avaliadores.get(pk=remover_id)
        except Exception:
            return httprr('.', 'Avaliador a remover não encontrado no processo.', tag='error')

        try:
            vinculo_rh = request.user.get_vinculo()
        except Exception:
            vinculo_rh = None

        with transaction.atomic():
            processo_ref = ProcessoRSCTae.objects.select_for_update().get(pk=processo.pk)

            # Marca avaliador substituído (preserva histórico) e remove avaliações de anexo pendentes
            AvaliacaoProcessoRSCTae.objects.filter(
                processo=processo_ref,
                avaliador_vinculo=vinculo_remover,
            ).update(substituido=True)
            AvaliacaoAnexoRSCTae.objects.filter(
                anexo__processo=processo_ref,
                avaliador_vinculo=vinculo_remover,
            ).delete()
            processo_ref.avaliadores.remove(vinculo_remover)

            # Adiciona novo avaliador com aceite automático e prazo regulamentar.
            # Reativa a avaliação existente se ele já participou do processo (limpa `substituido`).
            data_limite = _calcular_data_limite_avaliacao()
            AvaliacaoProcessoRSCTae.reativar_ou_criar(processo_ref, avaliador_incluir, data_limite)
            processo_ref.avaliadores.add(avaliador_incluir)

            # Registra no histórico de sorteios para auditoria
            SorteioAvaliadorRSCTae.objects.create(
                processo=processo_ref,
                avaliador_sorteado=avaliador_incluir,
                avaliador_substituido=vinculo_remover,
                motivo=SorteioAvaliadorRSCTae.MOTIVO_REMANEJAMENTO_RH,
                justificativa=motivo,
                realizado_por_vinculo=vinculo_rh,
            )

        return httprr(
            reverse('admin:rsc_tae_processorsctae_changelist'),
            f'Avaliador {vinculo_remover} removido e substituído por {avaliador_incluir}. Motivo: {motivo}',
            tag='success',
        )

    return {
        'title': title,
        'processo': processo,
        'form': form,
    }


@rtr('rsc_tae/recusar_avaliacao.html')
@login_required
def recusar_avaliacao(request, processo_id):
    title = 'Recusar convite de avaliação — RSC-TAE'
    processo = get_object_or_404(ProcessoRSCTae, pk=processo_id)

    if not request.user.has_perm('rsc_tae.avaliar_processorsctae'):
        raise PermissionDenied('Permissão negada.')

    if processo.situacao != SituacaoProcesso.EM_ANALISE:
        return httprr(processo.get_absolute_url(), 'Este processo não está em análise.', tag='error')

    try:
        vinculo_usuario = request.user.get_vinculo()
    except Exception:
        raise PermissionDenied('Vínculo do usuário não encontrado.')

    if processo.vinculo_id == vinculo_usuario.id:
        raise PermissionDenied('Você não pode recusar a avaliação do seu próprio processo.')

    ap = AvaliacaoProcessoRSCTae.objects.filter(
        processo=processo,
        avaliador_vinculo=vinculo_usuario,
        substituido=False,
        finalizada=False,
    ).first()

    if not ap:
        return httprr(
            reverse('rsc_tae:minhas_avaliacoes'),
            'Você não é avaliador ativo neste processo.',
            tag='error',
        )

    form = RecusaAvaliacaoForm(request.POST or None, request=request)

    if request.method == 'POST' and form.is_valid():
        motivo = form.cleaned_data['motivo']
        try:
            with transaction.atomic():
                AvaliacaoProcessoRSCTae.objects.filter(pk=ap.pk).update(
                    resposta=AvaliacaoProcessoRSCTae.RESPOSTA_RECUSA,
                    aceite=False,
                    motivo_recusa=motivo,
                )
                _substituir_avaliador(
                    processo=processo,
                    avaliador_out=vinculo_usuario,
                    motivo=2,  # MOTIVO_SUBSTITUICAO_RECUSA
                    justificativa=motivo,
                    realizado_por_vinculo=vinculo_usuario,
                )
        except ValueError as e:
            return httprr(reverse('rsc_tae:minhas_avaliacoes'), str(e), tag='error')

        return httprr(
            reverse('rsc_tae:minhas_avaliacoes'),
            'Recusa registrada. Um substituto será designado automaticamente.',
            tag='success',
        )

    return {
        'title': title,
        'processo': processo,
        'form': form,
    }


@rtr('rsc_tae/declarar_impedimento.html')
@login_required
def declarar_impedimento(request, processo_id):
    title = 'Declarar impedimento/suspeição — RSC-TAE'
    processo = get_object_or_404(ProcessoRSCTae, pk=processo_id)

    if not request.user.has_perm('rsc_tae.avaliar_processorsctae'):
        raise PermissionDenied('Permissão negada.')

    if processo.situacao != SituacaoProcesso.EM_ANALISE:
        return httprr(processo.get_absolute_url(), 'Este processo não está em análise.', tag='error')

    try:
        vinculo_usuario = request.user.get_vinculo()
    except Exception:
        raise PermissionDenied('Vínculo do usuário não encontrado.')

    if processo.vinculo_id == vinculo_usuario.id:
        raise PermissionDenied('Você não pode declarar impedimento em seu próprio processo.')

    ap = AvaliacaoProcessoRSCTae.objects.filter(
        processo=processo,
        avaliador_vinculo=vinculo_usuario,
        substituido=False,
        finalizada=False,
    ).first()

    if not ap:
        return httprr(
            reverse('rsc_tae:minhas_avaliacoes'),
            'Você não é avaliador ativo neste processo.',
            tag='error',
        )

    form = ImpedimentoAvaliacaoForm(request.POST or None, request=request)

    if request.method == 'POST' and form.is_valid():
        motivo = form.cleaned_data['motivo']
        try:
            with transaction.atomic():
                AvaliacaoProcessoRSCTae.objects.filter(pk=ap.pk).update(
                    resposta=AvaliacaoProcessoRSCTae.RESPOSTA_IMPEDIMENTO,
                    aceite=False,
                    motivo_impedimento=motivo,
                )
                _substituir_avaliador(
                    processo=processo,
                    avaliador_out=vinculo_usuario,
                    motivo=3,  # MOTIVO_SUBSTITUICAO_IMPEDIMENTO
                    justificativa=motivo,
                    realizado_por_vinculo=vinculo_usuario,
                )
        except ValueError as e:
            return httprr(reverse('rsc_tae:minhas_avaliacoes'), str(e), tag='error')

        return httprr(
            reverse('rsc_tae:minhas_avaliacoes'),
            'Impedimento declarado. Um substituto será designado automaticamente.',
            tag='success',
        )

    return {
        'title': title,
        'processo': processo,
        'form': form,
    }
