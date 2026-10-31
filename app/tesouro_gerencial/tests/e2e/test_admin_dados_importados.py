"""Smoke: as telas de admin dos dados importados — fora do menu, só para superusuário.

Além dos dois cadastros do menu, ``admin.py`` registra 25 models: as tabelas de classificação e os
documentos que a importação grava. Nenhum grupo tem permissão neles (``permissions.yaml``), então só o
superusuário os abre — é por elas que se confere, linha a linha, o que uma importação gravou. Várias
têm código que roda ao listar: colunas calculadas (``get_valor``, ``get_subitem_original``,
``get_documento_empenho_inicial``) e os filtros "(exceto)" (``SimpleListFilterExclude``), que montam
as opções a partir das tabelas de classificação e excluem pelo código escolhido. Erro em qualquer um
deles é 500 numa tela que ninguém abre todo dia — por isso a varredura.

``Tela.buscar`` em lote (GET pela sessão do browser, sem renderizar): o que se afirma é o 200. As
listagens têm linhas para calcular, porque a execução de referência do seed está lá. A falha lista
todas as telas quebradas de uma vez.
"""

import pytest

from djtools.e2e_ui import Tela

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

ADMIN = '/admin/tesouro_gerencial/'

# Os filtros "(exceto)" de documentos e restos a pagar, escolhidos: é o único caminho que executa o
# `queryset` deles (sem valor escolhido, só as opções são montadas).
EXCETO = '?unidade_orcamentaria_exclude=26298&acao_governo_exclude=2004&naturesa_despesa_exclude=339030&fonte_recurso_exclude=8250000000'

LISTAGENS = [
    '/admin/tesouro_gerencial/classificacaoinstitucional/',
    '/admin/tesouro_gerencial/esferaorcamentaria/',
    '/admin/tesouro_gerencial/acaogoverno/',
    '/admin/tesouro_gerencial/programatrabalhoresumido/',
    '/admin/tesouro_gerencial/planointerno/',
    '/admin/tesouro_gerencial/fonterecurso/',
    '/admin/tesouro_gerencial/naturezadespesa/',
    '/admin/tesouro_gerencial/subelementonaturezadespesa/',
    '/admin/tesouro_gerencial/unidadegestora/',
    '/admin/tesouro_gerencial/gru/',
    '/admin/tesouro_gerencial/receitagru/',
    '/admin/tesouro_gerencial/rap/',
    f'/admin/tesouro_gerencial/rap/{EXCETO}',
    '/admin/tesouro_gerencial/rapitem/',
    '/admin/tesouro_gerencial/documentoempenho/',
    f'/admin/tesouro_gerencial/documentoempenho/{EXCETO}',
    '/admin/tesouro_gerencial/documentoempenhoitem/',
    '/admin/tesouro_gerencial/documentoliquidacao/',
    f'/admin/tesouro_gerencial/documentoliquidacao/{EXCETO}',
    '/admin/tesouro_gerencial/documentoliquidacaoitem/',
    '/admin/tesouro_gerencial/documentopagamento/',
    '/admin/tesouro_gerencial/documentopagamentoitem/',
    '/admin/tesouro_gerencial/notacredito/',
    '/admin/tesouro_gerencial/notacreditoitem/',
    '/admin/tesouro_gerencial/notadotacao/',
    '/admin/tesouro_gerencial/notadotacaoitem/',
    '/admin/tesouro_gerencial/historicoimportacao/',
    '/admin/tesouro_gerencial/importacao/',
]


def _quebradas(tela: Tela, urls: list[str]) -> list[str]:
    falhas = []
    for url in urls:
        try:
            status = tela.buscar(url).status
        except Exception as erro:
            falhas.append(f'{url} -> {type(erro).__name__}: {str(erro).splitlines()[0]}')
            continue
        if status != 200:
            falhas.append(f'{url} -> HTTP {status}')
    return falhas


def test_listagens_dos_dados_importados_abrem_para_o_superusuario(logado_tesouro):
    tela = Tela(logado_tesouro('superusuario'))

    falhas = _quebradas(tela, [ADMIN, *LISTAGENS])

    assert not falhas, f'{len(falhas)} de {len(LISTAGENS) + 1} telas não abriram:\n  ' + '\n  '.join(falhas)


@pytest.mark.parametrize(('papel', 'esperado'), [('superusuario', 200), ('gestor', 403)])
def test_dados_importados_nao_sao_tela_do_gestor(logado_tesouro, papel, esperado):
    """O gestor importa e consulta pelas variáveis, mas não navega o documento cru: ``permissions.yaml`` só
    lhe dá os dois cadastros de documento específico."""
    resposta = Tela(logado_tesouro(papel)).buscar('/admin/tesouro_gerencial/documentoempenho/')

    assert resposta.status == esperado, f'{papel} recebeu {resposta.status} na listagem de documentos de empenho (esperado {esperado})'
