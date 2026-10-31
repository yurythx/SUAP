"""Leitura da deliberação da CRSC na perspectiva do avaliado.

O avaliado enxergava só a camada dos avaliadores auxiliares: a nota que a CRSC consolidou em
cada anexo contestado, a justificativa do colegiado e o motivo do indeferimento existiam
apenas no PDF da deliberação. Este módulo monta essa leitura em tela.

Duas decisões moldam o que sai daqui:

- **Todos os anexos, não só os contestados.** ``_listar_divergencias_para_crsc`` devolve apenas
  o que teve indeferimento ou corte de pontuação; o avaliado precisa ver também os itens que
  ninguém questionou, marcados como aceitos como declarados — senão some do relato metade do
  que ele enviou.
- **Sem voto nominal.** Sai a decisão consolidada, a contagem dos votos e as justificativas do
  colegiado; não sai quem votou o quê. Por isso as avaliações e os votos entram como texto, e
  nunca como objeto: um ``AvaliacaoAnexoRSCTae`` ou ``DeliberacaoItemCRSCRSCTae`` na mão do
  template carrega o vínculo de quem assinou.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from rsc_tae.enums import SituacaoAvaliacaoItem, SituacaoProcesso
from rsc_tae.models import DeliberacaoCRSCRSCTae, DeliberacaoItemCRSCRSCTae, ProcessoRSCTae, RolSaberCompetenciaAnexo
from rsc_tae.views._helpers import _listar_divergencias_para_crsc, aplicar_notas_consolidadas_crsc, resumo_final_consolidado

# Estados possíveis de um anexo no relato final ao avaliado.
ACEITO_COMO_DECLARADO = 'aceito_como_declarado'
CONSOLIDADO = 'consolidado'
EM_DELIBERACAO = 'em_deliberacao'
AVALIADO_PELOS_AUXILIARES = 'avaliado_pelos_auxiliares'


def _textos_distintos(valores) -> list[str]:
    """Textos não vazios, sem repetir, preservando a ordem de entrada."""
    vistos: dict[str, None] = {}
    for valor in valores:
        texto = (valor or '').strip()
        if texto:
            vistos.setdefault(texto, None)
    return list(vistos)


def _nota_dos_auxiliares(avaliacoes) -> Any:
    """Pontuação validada pelos auxiliares, quando eles convergiram num único valor.

    Indeferido vale 0. Havendo mais de um valor distinto não existe nota da avaliação — é
    justamente a divergência que a CRSC resolveria.
    """
    valores = {Decimal('0') if av.situacao == SituacaoAvaliacaoItem.INDEFERIDO else (av.pontuacao_validada or Decimal('0')) for av in avaliacoes}
    return valores.pop() if len(valores) == 1 else None


def _estado_contestado(fechado: bool, houve_deliberacao_crsc: bool) -> str:
    """Estado do anexo contestado.

    Sem deliberação colegiada no processo inteiro, o que vale é a avaliação dos auxiliares —
    é o fluxo anterior à CRSC, e anunciar "sem deliberação concluída" faria um processo já
    decidido parecer aberto.
    """
    if fechado:
        return CONSOLIDADO
    return EM_DELIBERACAO if houve_deliberacao_crsc else AVALIADO_PELOS_AUXILIARES


def _linha_contestada(divergencia: dict, houve_deliberacao_crsc: bool) -> dict[str, Any]:
    """Anexo que os auxiliares contestaram e a CRSC deliberou (ou ainda delibera)."""
    status = divergencia['status_deliberacao']
    votos = divergencia['votos']
    fechado = bool(status['fechado'])
    return {
        'item': divergencia['item'],
        'anexo': divergencia['anexo'],
        'unidades_declaradas': divergencia['anexo'].pontuacao,
        'observacoes_auxiliares': _textos_distintos(av.observacao for av in divergencia['avaliacoes']),
        'estado': _estado_contestado(fechado, houve_deliberacao_crsc),
        'nota_crsc': status['nota_consolidada'] if fechado else None,
        'nota_auxiliares': _nota_dos_auxiliares(divergencia['avaliacoes']),
        'justificativas': _textos_distintos(voto.justificativa for voto in votos),
        'votos_deferir': sum(1 for voto in votos if voto.decisao == DeliberacaoItemCRSCRSCTae.DECISAO_DEFERIR),
        'votos_indeferir': sum(1 for voto in votos if voto.decisao == DeliberacaoItemCRSCRSCTae.DECISAO_INDEFERIR),
    }


def _linha_aceita(anexo: RolSaberCompetenciaAnexo) -> dict[str, Any]:
    """Anexo que ninguém contestou: vale como o avaliado declarou, sem deliberação."""
    return {
        'item': anexo.rol_saber_competencia,
        'anexo': anexo,
        'unidades_declaradas': anexo.pontuacao,
        'observacoes_auxiliares': [],
        'estado': ACEITO_COMO_DECLARADO,
        'nota_crsc': None,
        'nota_auxiliares': None,
        'justificativas': [],
        'votos_deferir': 0,
        'votos_indeferir': 0,
    }


def _anexos_do_processo(processo: ProcessoRSCTae):
    """Anexos na ordem em que o processo os apresenta: requisito, grupo, item."""
    return (
        RolSaberCompetenciaAnexo.objects.filter(processo=processo)
        .select_related('rol_saber_competencia__grupo__requisito')
        .order_by(
            'rol_saber_competencia__grupo__requisito__numero',
            'rol_saber_competencia__grupo__numero',
            'rol_saber_competencia__numero',
            'id',
        )
    )


def _deliberacao_publicada(deliberacao: DeliberacaoCRSCRSCTae | None) -> dict[str, Any] | None:
    """Campos publicáveis da deliberação, sem o model.

    Entregar o ``DeliberacaoCRSCRSCTae`` deixava ``deliberado_por_vinculo`` e
    ``processo.votos_deliberacao_final`` a um passo da resolução de variáveis do template —
    ou seja, o voto nominal que esta tela não divulga a um ajuste de distância. Com um dict
    a garantia é estrutural, e não depende de o template continuar bem-comportado.
    """
    if deliberacao is None:
        return None
    return {
        'resultado': deliberacao.get_resultado_display(),
        'justificativa': deliberacao.justificativa or '',
        'pontuacao_final_crsc': deliberacao.pontuacao_final_crsc,
        'data_deliberacao': deliberacao.data_deliberacao,
    }


def _motivos(processo: ProcessoRSCTae, deliberacao: DeliberacaoCRSCRSCTae | None, resumo: dict) -> list[str]:
    """Constatações do indeferimento com a redação do Decreto — as mesmas do parecer."""
    from rsc_tae.views.documentos import _motivos_indeferimento_parecer

    if deliberacao is None or processo.situacao != SituacaoProcesso.INDEFERIDO:
        return []
    return _motivos_indeferimento_parecer(processo, resumo)


def montar_deliberacao_para_avaliado(processo: ProcessoRSCTae) -> dict[str, Any]:
    """Relato da decisão final: resultado, totais consolidados e o que houve em cada anexo.

    Os totais vêm de ``resumo_final_consolidado`` — a mesma fonte do parecer conclusivo —, para
    que tela e documento não declarem números diferentes.
    """
    from rsc_tae.views.documentos import _membros_crsc_deliberantes

    divergencias = _listar_divergencias_para_crsc(processo)
    contestados = {divergencia['anexo'].pk: divergencia for divergencia in divergencias}
    deliberacao = DeliberacaoCRSCRSCTae.objects.filter(processo=processo).select_related('deliberado_por_vinculo__pessoa').first()
    houve_deliberacao_crsc = deliberacao is not None

    linhas = [
        _linha_contestada(contestados[anexo.pk], houve_deliberacao_crsc) if anexo.pk in contestados else _linha_aceita(anexo)
        for anexo in _anexos_do_processo(processo)
    ]
    resumo = resumo_final_consolidado(processo, divergencias)

    return {
        'deliberacao': _deliberacao_publicada(deliberacao),
        'deferido': processo.situacao == SituacaoProcesso.DEFERIDO,
        'resumo': resumo,
        'motivos': _motivos(processo, deliberacao, resumo),
        'linhas': linhas,
        'membros': _membros_crsc_deliberantes(processo),
        'sem_deliberacao_crsc': not houve_deliberacao_crsc,
    }


def _percentual(alcancado, exigido) -> float:
    """Percentual de progresso, limitado a 100 — o mesmo cálculo do resumo da avaliação."""
    if not exigido:
        return 0.0
    return float(min(Decimal(alcancado) / Decimal(exigido), Decimal('1')) * Decimal('100'))


def aplicar_totais_consolidados(processo: ProcessoRSCTae, contexto: dict[str, Any]) -> dict[str, Any]:
    """Troca os totais brutos dos auxiliares pelos consolidados da CRSC em processo já decidido.

    Enquanto o processo corre, o total dos auxiliares é o único que existe e é o que interessa a
    quem avalia. Decidido o processo, quem lê a tela quer o número que o parecer declara — antes
    disso, resumo e parecer exibiam pontuações diferentes sem nada explicando a diferença.
    """
    if processo.situacao not in SituacaoProcesso.FINAIS:
        return contexto

    divergencias = _listar_divergencias_para_crsc(processo)
    # Aplica a nota da CRSC anexo a anexo ANTES de fixar o cabeçalho: este helper recalcula o
    # total a partir das linhas, e o número que vale é o do parecer (com saldo anterior e a
    # conversão temporal por período, que nenhuma linha isolada carrega).
    aplicar_notas_consolidadas_crsc(contexto, divergencias)
    resumo = resumo_final_consolidado(processo, divergencias)
    return {
        **contexto,
        'total_pontos_validados': resumo['total_pontos'],
        'itens_validados': resumo['itens_validados'],
        'pontos_requeridos_nivel': resumo['pontos_requeridos'],
        'itens_requeridos': resumo['itens_requeridos'],
        'pontos_percent': _percentual(resumo['total_pontos'], resumo['pontos_requeridos']),
        'itens_percent': _percentual(resumo['itens_validados'], resumo['itens_requeridos']),
        'resultado_parcial_deferido': resumo['deferido'],
    }
