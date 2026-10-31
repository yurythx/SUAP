"""Ciclo de deliberação LAI: fila de análise, prévia dos dados e transições rastreadas.

Toda mudança de ``PDABaseDados.situacao_lai`` do módulo passa por ``aplicar_evento`` — é o que
mantém a linha do tempo (``DeliberacaoLAI``) sem buracos. Alterar a situação com ``.update()``
cru em qualquer outro ponto reintroduz o problema que este módulo existe para resolver.
"""

import datetime
import logging
from dataclasses import dataclass

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Count, Q
from django.utils.translation import gettext as _

from dados_abertos.enums import FormatoRecurso, SituacaoLAI, TipoEventoLAI
from dados_abertos.models import DeliberacaoLAI, PDABaseDados, PlanoDadosAbertos
from dados_abertos.services.coleta import ler_tabular

logger = logging.getLogger(__name__)

PREVIEW_MAX_REGISTROS = 5
PREVIEW_MAX_COLUNAS = 20

#: Teto de leitura da prévia de CSV. A prévia mostra 5 linhas; ler o arquivo inteiro (dados abertos
#: costumam ter centenas de milhares de registros) só para descartá-lo é desperdício de memória.
#: Vale só para formatos orientados a linha, onde cortar no fim de uma linha preserva o sentido.
PREVIEW_MAX_BYTES = 256 * 1024

#: Teto para JSON, que precisa ser lido inteiro para ser parseado. Acima disso a prévia se recusa,
#: em vez de cortar o documento e reportar como se o arquivo estivesse corrompido.
PREVIEW_MAX_BYTES_JSON = 10 * 1024 * 1024

#: A decisão que chega do formulário é a situação-alvo; o tipo do evento é derivado daqui.
#: Mapa explícito de propósito: antes o código atribuía a decisão direto em ``situacao_lai``,
#: apoiado em os dois enums terem por acaso os mesmos valores.
TIPO_POR_DECISAO = {
    SituacaoLAI.LIBERADO: TipoEventoLAI.LIBERACAO,
    SituacaoLAI.DEVOLVIDO: TipoEventoLAI.DEVOLUCAO,
}


@dataclass(frozen=True)
class DetalheDeliberacao:
    """Tudo que o card de um dataset precisa: prévias, linha do tempo e a última rodada."""

    relacao: PDABaseDados
    recursos: list
    eventos: list
    ultimo_parecer: DeliberacaoLAI | None
    ultima_resposta: DeliberacaoLAI | None


# --------------------------------------------------------------------- prévia dos dados


def _ler_arquivo(recurso, limite: int | None) -> bytes | None:
    """Lê o recurso (todo, se ``limite`` for ``None``) ou ``None`` se o arquivo não estiver acessível."""
    try:
        recurso.arquivo.open('rb')
        try:
            return recurso.arquivo.read(limite) if limite is not None else recurso.arquivo.read()
        finally:
            recurso.arquivo.close()
    except FileNotFoundError, OSError, ValueError:
        return None


def _ler_inicio_do_arquivo(recurso) -> bytes | None:
    """Primeiros ``PREVIEW_MAX_BYTES`` do recurso, para formatos orientados a linha (CSV).

    Quando o corte acontece no meio de uma linha, a última é descartada — meia linha vira coluna
    fantasma na prévia. Não serve para JSON: ver ``_ler_json_inteiro``.
    """
    conteudo = _ler_arquivo(recurso, PREVIEW_MAX_BYTES)
    if conteudo is None:
        return None
    if len(conteudo) == PREVIEW_MAX_BYTES and b'\n' in conteudo:
        conteudo = conteudo.rsplit(b'\n', 1)[0]
    return conteudo


def _tamanho(recurso) -> int | None:
    try:
        return recurso.arquivo.size
    except FileNotFoundError, OSError, ValueError:
        return None


def _parece_json(recurso) -> bool:
    """Decide o formato pelo campo declarado ou pelo primeiro caractere do arquivo.

    A checagem é feita ANTES de ler, porque cada formato exige uma estratégia de leitura
    diferente — e olhar o conteúdo já lido levaria de volta ao JSON truncado.
    """
    if (getattr(recurso, 'formato', '') or '').upper() == 'JSON':
        return True
    inicio = _ler_arquivo(recurso, 64)
    return bool(inicio) and inicio.lstrip()[:1] in (b'[', b'{')


def _recortar(tabular) -> dict:
    """Converte a leitura tabular no formato da prévia, recortando as colunas.

    O corte é da exibição, não da leitura: o esquema do recurso é a lista completa de colunas.
    """
    return {
        'colunas': tabular.colunas[:PREVIEW_MAX_COLUNAS],
        'linhas': [linha[:PREVIEW_MAX_COLUNAS] for linha in tabular.linhas],
        'erro': tabular.erro,
    }


def preview_recurso(recurso, n: int = PREVIEW_MAX_REGISTROS) -> dict:
    """Colunas e primeiros ``n`` registros do recurso, para prévia na tela de deliberação.

    Retorna ``{'colunas': list, 'linhas': list[list], 'erro': str | None}``. Nunca lança:
    arquivo ausente no storage (ex.: réplica de produção sem a mídia) vira um ``erro`` amigável.
    """
    if not getattr(recurso, 'arquivo', None):
        return {'colunas': [], 'linhas': [], 'erro': 'Recurso sem arquivo anexado.'}
    if _parece_json(recurso):
        return _preview_json_do_arquivo(recurso, n)
    conteudo = _ler_inicio_do_arquivo(recurso)
    if conteudo is None:
        return {'colunas': [], 'linhas': [], 'erro': 'Arquivo indisponível para prévia neste ambiente.'}
    return _recortar(ler_tabular(conteudo.decode('utf-8', 'replace'), getattr(recurso, 'formato', '') or '', limite=n))


def _preview_json_do_arquivo(recurso, n: int) -> dict:
    """Prévia de JSON, que só pode ser lido por inteiro — documento cortado não é documento.

    O teto vira recusa explícita em vez de leitura parcial: truncar produziria um "JSON inválido"
    que culpa o arquivo por um limite nosso.
    """
    tamanho = _tamanho(recurso)
    if tamanho is not None and tamanho > PREVIEW_MAX_BYTES_JSON:
        limite_mb = PREVIEW_MAX_BYTES_JSON / (1024 * 1024)
        return {
            'colunas': [],
            'linhas': [],
            'erro': f'Arquivo JSON grande demais para prévia automática (acima de {limite_mb:.0f} MB). Baixe o recurso para conferir o conteúdo.',
        }
    conteudo = _ler_arquivo(recurso, None)
    if conteudo is None:
        return {'colunas': [], 'linhas': [], 'erro': 'Arquivo indisponível para prévia neste ambiente.'}
    return _recortar(ler_tabular(conteudo.decode('utf-8', 'replace'), FormatoRecurso.JSON, limite=n))


# ------------------------------------------------------------------ fila e detalhe da tela


def montar_fila(pda: PlanoDadosAbertos | None) -> list:
    """Datasets aguardando análise no PDA — consulta leve, sem abrir arquivo algum.

    Só entram datasets com ao menos um recurso: sem recurso não há prévia do conteúdo a ser
    publicado, e não há o que o Responsável LAI avaliar (regra de negócio).
    """
    if not pda:
        return []
    return list(
        PDABaseDados.objects.filter(pda=pda, situacao_lai=SituacaoLAI.EM_ANALISE, base_dados__recursos__isnull=False)
        .select_related('base_dados', 'base_dados__organizacao')
        .annotate(
            qtd_recursos=Count('base_dados__recursos', distinct=True),
            devolucoes=Count('eventos_lai', filter=Q(eventos_lai__tipo=TipoEventoLAI.DEVOLUCAO), distinct=True),
        )
        .distinct()
        .order_by('base_dados__titulo')
    )


def montar_detalhe(relacao: PDABaseDados) -> DetalheDeliberacao:
    """Prévias e linha do tempo de UM dataset — a parte cara, feita só para o item em foco."""
    recursos = list(relacao.base_dados.recursos.all())
    for recurso in recursos:
        recurso.preview = preview_recurso(recurso)
    eventos = list(relacao.eventos_lai.select_related('autor__pessoa').order_by('data', 'id'))
    return DetalheDeliberacao(
        relacao=relacao,
        recursos=recursos,
        eventos=eventos,
        ultimo_parecer=_ultimo(eventos, TipoEventoLAI.DEVOLUCAO),
        ultima_resposta=_ultimo(eventos, TipoEventoLAI.REENVIO),
    )


def _ultimo(eventos: list, tipo: int) -> DeliberacaoLAI | None:
    return next((e for e in reversed(eventos) if e.tipo == tipo), None)


def progresso_pda(pda: PlanoDadosAbertos | None) -> dict:
    """Progresso real do PDA: bases liberadas sobre bases que podem ser analisadas.

    Denominador estável de propósito — a fila encolhe a cada deliberação, então medir progresso
    por ela faria a barra andar para trás.
    """
    if not pda:
        return {'liberadas': 0, 'total': 0, 'percentual': 0}
    analisaveis = PDABaseDados.objects.filter(pda=pda, base_dados__recursos__isnull=False).distinct()
    total = analisaveis.count()
    liberadas = analisaveis.filter(situacao_lai=SituacaoLAI.LIBERADO).count()
    percentual = round(liberadas * 100 / total) if total else 0
    return {'liberadas': liberadas, 'total': total, 'percentual': percentual}


# ------------------------------------------------------------------------- transições


def aplicar_evento(
    relacao: PDABaseDados,
    tipo: int,
    nova_situacao: int,
    texto: str = '',
    autor=None,
    ip: str | None = None,
    user_agent: str = '',
    motivo_reabertura: str = '',
) -> DeliberacaoLAI:
    """Grava o evento e move a situação da relação. Porta única de transição do ciclo LAI.

    Deve ser chamada dentro de uma transação: o evento e a nova situação precisam entrar ou
    falhar juntos, sob pena de a linha do tempo divergir do estado.
    """
    evento = DeliberacaoLAI(
        pda_base_dados=relacao,
        tipo=tipo,
        texto=(texto or '').strip(),
        autor=autor,
        ip=ip or None,
        user_agent=(user_agent or '')[:500],
    )
    evento.full_clean()
    evento.save()
    relacao.situacao_lai = nova_situacao
    relacao.motivo_reabertura = motivo_reabertura
    # `data_atualizacao` é `auto_now`, e o Django só o grava quando ele entra em `update_fields`.
    # A transição muda a relação, então a "Data de Atualização" do admin tem de acompanhar —
    # é a mesma convenção já usada em matriz_priorizacao_service e acoes_automaticas_service.
    relacao.save(update_fields=['situacao_lai', 'motivo_reabertura', 'data_atualizacao'])
    return evento


def registrar_deliberacao(relacao_id: int, decisao: int, parecer: str, vinculo, ip: str | None, user_agent: str) -> PDABaseDados:
    """Registra a decisão do Responsável LAI (liberar ou devolver) sobre um dataset em análise."""
    tipo = TIPO_POR_DECISAO.get(decisao)
    if tipo is None:
        raise ValidationError({'__all__': [_('Decisão inválida.')]})
    with transaction.atomic():
        relacao = PDABaseDados.objects.select_for_update().get(pk=relacao_id, situacao_lai=SituacaoLAI.EM_ANALISE)
        aplicar_evento(relacao, tipo, nova_situacao=decisao, texto=parecer, autor=vinculo, ip=ip, user_agent=user_agent)
    return relacao


def registrar_reenvio(relacao_id: int, texto: str, vinculo, ip: str | None, user_agent: str) -> PDABaseDados:
    """Devolve ao LAI um dataset devolvido para ajustes, com a resposta do gestor.

    Levanta ``PDABaseDados.DoesNotExist`` quando o dataset não está devolvido — reenviar o que
    está em análise ou já liberado reabriria uma deliberação concluída.
    """
    with transaction.atomic():
        relacao = PDABaseDados.objects.select_for_update().get(pk=relacao_id, situacao_lai=SituacaoLAI.DEVOLVIDO)
        if not relacao.base_dados.recursos.exists():
            raise ValidationError({'__all__': [_('Anexe ao menos um recurso: sem prévia dos dados não há o que o Responsável LAI avaliar.')]})
        aplicar_evento(
            relacao,
            TipoEventoLAI.REENVIO,
            nova_situacao=SituacaoLAI.EM_ANALISE,
            texto=texto,
            autor=vinculo,
            ip=ip,
            user_agent=user_agent,
        )
    return relacao


def _ids_enviaveis(relacoes) -> list[int]:
    """Ids das relações pendentes/devolvidas que têm ao menos um recurso."""
    return list(
        relacoes.filter(situacao_lai__in=(SituacaoLAI.PENDENTE, SituacaoLAI.DEVOLVIDO))
        .annotate(_qtd_recursos=Count('base_dados__recursos'))
        .filter(_qtd_recursos__gt=0)
        .values_list('id', flat=True)
    )


def enviar_para_analise(relacoes, autor=None, ip: str | None = None, user_agent: str = '') -> int:
    """Envia datasets à análise do LAI em lote e retorna quantos foram enviados.

    Quem nunca foi analisado entra como ``ENVIO``; quem estava devolvido entra como ``REENVIO``,
    para a linha do tempo distinguir a primeira submissão das seguintes. Datasets sem recurso são
    ignorados — cabe a quem chamou avisar sobre eles.
    """
    ids = _ids_enviaveis(relacoes)
    if not ids:
        return 0
    with transaction.atomic():
        itens = list(PDABaseDados.objects.select_for_update().filter(id__in=ids))
        DeliberacaoLAI.objects.bulk_create(
            [
                DeliberacaoLAI(
                    pda_base_dados=relacao,
                    tipo=TipoEventoLAI.REENVIO if relacao.situacao_lai == SituacaoLAI.DEVOLVIDO else TipoEventoLAI.ENVIO,
                    texto=_texto_envio_em_lote(relacao),
                    autor=autor,
                    ip=ip or None,
                    user_agent=(user_agent or '')[:500],
                )
                for relacao in itens
            ]
        )
        PDABaseDados.objects.filter(id__in=ids).update(situacao_lai=SituacaoLAI.EM_ANALISE, motivo_reabertura='')
    return len(itens)


def _texto_envio_em_lote(relacao: PDABaseDados) -> str:
    if relacao.situacao_lai == SituacaoLAI.DEVOLVIDO:
        return _('Reenviado em lote, sem descrição dos ajustes.')
    return _('Enviado para análise do Responsável LAI.')


def reabrir_por_edicao(base) -> None:
    """Reverte para EM_ANALISE as relações LIBERADO da base (invalidação por edição de conteúdo).

    Deixa evento em cada relação afetada: ``motivo_reabertura`` é apenas o estado corrente e é
    limpo na deliberação seguinte, então sozinho ele não preserva o histórico.
    """
    liberadas = list(base.relacoes_pda.filter(situacao_lai=SituacaoLAI.LIBERADO))
    if not liberadas:
        return
    hoje = datetime.date.today().strftime('%d/%m/%Y')
    motivo = _('Reaberto por edição do conteúdo em %(data)s.') % {'data': hoje}
    with transaction.atomic():
        DeliberacaoLAI.objects.bulk_create(
            [DeliberacaoLAI(pda_base_dados=relacao, tipo=TipoEventoLAI.REABERTURA_POR_EDICAO, texto=motivo) for relacao in liberadas]
        )
        base.relacoes_pda.filter(id__in=[relacao.id for relacao in liberadas]).update(situacao_lai=SituacaoLAI.EM_ANALISE, motivo_reabertura=motivo)
    logger.info('LAI: base %s reaberta para análise por edição de conteúdo.', base.pk)
