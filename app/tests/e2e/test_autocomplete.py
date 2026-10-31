"""Fluxo: autocomplete do SUAP ponta a ponta (widget select2 → ``/json/<app>/<model>/``).

Por que este fluxo: o endpoint ``/json/`` (``suap/urls.py`` → ``djtools.views.json_view``)
é atravessado por quase toda tela de cadastro do SUAP e já teve regressão real de
performance (DISTINCT incondicional + índice ausente em ``pessoa.nome``). Um teste que
digita no widget cobre, de uma vez, o JS do widget, a autenticação do endpoint, a função
``buscar_json`` do model e a renderização dos resultados — coisa que teste de unidade no
endpoint isolado não pega.

Tela usada: ``/djtools/give_permission/`` (``AtribuirPermissaoForm``), que tem dois
autocompletes múltiplos sobre ``auth.Group`` e ``auth.Permission`` — dados garantidos pelo
``sync_permissions`` do seed, sem setup nenhum.
"""

import pytest
from playwright.sync_api import expect

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

URL = '/djtools/give_permission/'


def _abrir_autocomplete(page, nome_do_campo):
    """Clica no widget select2 que substitui ``select[name=<nome_do_campo>]``.

    O ``id`` do select é aleatório a cada render (ex. ``grupos_xFR8sn48vF``), então
    ancorar por ``name`` é o único caminho estável. O select2 insere seu ``span`` como
    irmão imediato do select original.
    """
    widget = page.locator(f'select[name="{nome_do_campo}"] + span.select2')
    expect(widget).to_be_visible()
    widget.click()


def test_autocomplete_de_grupos_consulta_o_endpoint_json(logado):
    page = logado('admin')
    chamadas_json = []
    page.on('request', lambda req: chamadas_json.append(req.url) if '/json/' in req.url else None)

    page.goto(URL)
    _abrir_autocomplete(page, 'grupos')
    page.keyboard.type('Aud')

    # O resultado só aparece depois do XHR: esperar pelo item é o que sincroniza.
    expect(page.locator('.select2-results__option', has_text='Auditor').first).to_be_visible()
    assert any('/json/auth/group/' in url for url in chamadas_json), f'o widget deveria consultar /json/auth/group/; chamadas vistas: {chamadas_json}'


def test_autocomplete_seleciona_e_mantem_o_item_escolhido(logado):
    page = logado('admin')
    page.goto(URL)
    _abrir_autocomplete(page, 'grupos')
    page.keyboard.type('Auditor Sistêmico')
    page.locator('.select2-results__option', has_text='Auditor Sistêmico').first.click()

    # Item escolhido fica visível no widget e o select original passa a ter a opção.
    expect(page.locator('.select2-selection__choice', has_text='Auditor Sistêmico')).to_be_visible()
    assert page.locator('select[name="grupos"] option').count() >= 1


def test_autocomplete_exige_autenticacao(new_context):
    """``json_view`` devolve 401 para anônimo em model sem ``PUBLIC_SEARCH``.

    Contexto próprio, sem ``storage_state``: este teste precisa ser anônimo.
    """
    page = new_context().new_page()
    resposta = page.request.get('/json/auth/group/?q=Aud')
    assert resposta.status == 401, f'esperado 401 para anônimo, veio {resposta.status}'
