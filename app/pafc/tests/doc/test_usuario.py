"""Roteiro navegado das tarefas do ``pafc`` — a fonte de ``pafc/docs/usuario.md``.

Um teste por tarefa da doc, na ordem em que a doc as apresenta. As asserções são as mesmas
dos e2e (título, botão, mensagem de sucesso) e existem para a rodada falhar alto quando a
tela mudou de forma: doc que descreve um passo que não existe mais é pior que doc velha.

Marcado ``e2e`` além de ``doc`` de propósito — o ``-m "not e2e"`` do ``suap_check`` precisa
excluir esta suíte, que exige o banco ``*_e2e`` e um browser.

O módulo não tem ``features/``: os estados de domínio (PAFC em elaboração, PAFC nos
conselhos, modelo) são semeados por ORM no ``doc_seed`` e os passos documentados são
navegados de verdade.
"""

from __future__ import annotations

import sys

import pytest

from djtools.e2e_ui import Tela

pytestmark = [pytest.mark.doc, pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

PAFCS = '/admin/pafc/pafc/'
SOLICITACOES_AD_REFERENDUM = '/admin/pafc/solicitacaotramitacaoadreferendumpafc/'
MODELOS = '/admin/pafc/modelopafc/'


def _anotar(titulo: str, tela: Tela) -> None:
    """Despeja cabeçalhos, botões e rótulos da tela para a redação da doc (não é asserção)."""
    cabecalhos = tela.pagina.get_by_role('heading').all_inner_texts()
    main = ' '.join(tela.pagina.locator('//main').all_inner_texts())[:800]
    sys.stderr.write(
        f'\n[doc:{titulo}] url={tela.pagina.url}'
        f'\n  cabeçalhos: {[c.strip() for c in cabecalhos if c.strip()]}'
        f'\n  botões: {tela.botoes_na_tela()}'
        f'\n  rótulos: {tela.rotulos_na_tela()}'
        f'\n  erros: {tela.erros_na_tela()}'
        f'\n  main: {main!r}\n'
    )


def test_acompanhar_pafc(logado_doc, doc_seed, capturar):
    """Tarefa 1 — a listagem e a página do PAFC em elaboração."""
    pafc = doc_seed['pafc_elaboracao']

    tela = Tela(logado_doc('servidor')).ir(PAFCS)
    assert 'at /' not in tela.pagina.title(), f'pafcs respondeu página de erro: {tela.pagina.title()}'
    _anotar('pafc-listagem', tela)
    capturar(tela.pagina, 'pafc-listagem')
    # O PAFC do conselho tem o mesmo nome de curso (o `save` copia do PPC) — a linha
    # desejada é a que NÃO traz o sufixo "(Conselho)".
    tela.pagina.locator(
        '//tr[contains(., "Curso de Exemplo da Doc") and not(contains(., "Conselho"))]//a[contains(@class, "icon-view")]'
    ).first.click()

    tela.ver_titulo(f'PAFC: {pafc}')
    _anotar('pafc-tela', tela)
    capturar(tela.pagina, 'pafc-tela')


def test_solicitar_tramitacao_ad_referendum(logado_doc, doc_seed, capturar):
    """Tarefa 2 — solicitar a tramitação ad referendum e acompanhar a solicitação."""
    from pafc.models import SolicitacaoTramitacaoAdReferendumPAFC

    pafc = doc_seed['pafc_conselho']

    # A tela do PAFC nos conselhos traz o botão de solicitação.
    tela = Tela(logado_doc('servidor')).ir(f'/pafc/pafc/{pafc.pk}/')
    tela.ver_titulo(f'PAFC: {pafc}')
    tela.ver_botao('Solicitar tramitação Ad Referendum')
    _anotar('pafc-conselho', tela)
    capturar(tela.pagina, 'pafc-conselho')
    tela.clicar_botao('Solicitar tramitação Ad Referendum')

    popup = tela.popup()
    _anotar('ad-referendum-formulario', popup)
    capturar(tela.pagina, 'ad-referendum-formulario')
    popup.preencher('Justificativa', 'textarea', 'Necessário tramitar antes da reunião do conselho.')
    popup.salvar_no_popup('Salvar')

    tela.sucesso('Solicitação registrada com sucesso.')
    solicitacao = SolicitacaoTramitacaoAdReferendumPAFC.objects.filter(pafc=pafc).order_by('-id').first()
    assert solicitacao is not None, 'a UI disse que solicitou, mas não persistiu'
    assert solicitacao.deferida is None, 'a solicitação nasceu com decisão; a doc afirma que fica pendente'

    # Do outro lado do balcão: a solicitação fica na listagem de tramitações ad referendum.
    gestao = Tela(logado_doc('admin_pafc')).ir(SOLICITACOES_AD_REFERENDUM)
    assert 'at /' not in gestao.pagina.title(), f'solicitações ad referendum respondeu página de erro: {gestao.pagina.title()}'
    _anotar('ad-referendum-listagem', gestao)
    capturar(gestao.pagina, 'ad-referendum-listagem')
    gestao.linha('Curso de Exemplo da Doc (Conselho)').clicar_icone('exibição')
    gestao.ver_titulo(str(solicitacao))
    _anotar('ad-referendum-visualizar', gestao)
    capturar(gestao.pagina, 'ad-referendum-visualizar')


def test_modelo_pafc(logado_doc, doc_seed, capturar):
    """Tarefa 3 — o modelo de PAFC e suas seções (Administrador de PAFC)."""
    modelo = doc_seed['modelo_pafc']

    tela = Tela(logado_doc('admin_pafc')).ir(MODELOS)
    assert 'at /' not in tela.pagina.title(), f'modelos respondeu página de erro: {tela.pagina.title()}'
    _anotar('modelos-pafc-listagem', tela)
    capturar(tela.pagina, 'modelos-pafc-listagem')
    tela.linha(modelo.descricao).clicar_icone('exibição')

    tela.ver_titulo(f'Modelo {modelo.descricao}')
    _anotar('modelo-pafc-tela', tela)
    capturar(tela.pagina, 'modelo-pafc-tela')
