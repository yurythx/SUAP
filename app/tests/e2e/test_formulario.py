"""Fluxo: validação de ``FormPlus`` (o ``clean()`` global) numa tela real.

Por que este fluxo: o commit que pôs um ``clean()`` em ``FormPlus``/``ModelFormPlus``
(que dá ``raise`` quando ``self.errors``) mudou o comportamento visível de duas formas —
o resumo de erro virou **plural** ("corrija os erros abaixo") mesmo com um único campo
inválido, e passou a injetar a mensagem "Existem erros no formulário..." como erro de
formulário. Isso é contrato de UI que nenhum teste de unidade de form cobre, e que só
aparece renderizado. As telas do admin (``ModelAdminPlus``) NÃO passam por esse caminho —
por isso o fluxo usa uma tela ``FormPlus`` de verdade, não o admin.

Tela usada: ``/djtools/give_permission/`` (``AtribuirPermissaoForm``), cujo campo
``usuarios`` é obrigatório — submeter vazio é o caminho mais curto para o erro.
"""

import pytest
from playwright.sync_api import expect

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

URL = '/djtools/give_permission/'
SUBMIT = 'input[name=atribuirpermissao_form]'


def test_submit_vazio_mostra_erro_de_campo_obrigatorio(logado):
    page = logado('admin')
    page.goto(URL)
    page.click(SUBMIT)

    expect(page.locator('.errorlist', has_text='Este campo é obrigatório.').first).to_be_visible()
    # Não saiu da tela: erro de validação re-renderiza o próprio formulário.
    expect(page.get_by_role('heading', name='Atribuir Permissão')).to_be_visible()


def test_resumo_de_erro_do_formplus_vem_no_plural(logado):
    """Trava o efeito do ``clean()`` global do ``FormPlus``.

    Um único campo obrigatório vazio ainda produz o resumo no plural, porque o ``clean()``
    global acrescenta o próprio erro de formulário. Se alguém remover ou reverter aquele
    ``clean()``, este teste cai — que é o ponto.
    """
    page = logado('admin')
    page.goto(URL)
    page.click(SUBMIT)

    expect(page.locator('p.errornote')).to_have_text('Por favor, corrija os erros abaixo.')
    expect(page.locator('.errorlist', has_text='Existem erros no formulário').first).to_be_visible()
