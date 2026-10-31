"""Fluxo: empenho (modo 2) — o mais rico do módulo.

Um empenho amarra processo eletrônico, tipo de material, fornecedor e itens; é a porta de
entrada de todo material que chega. São dois formulários encadeados (empenho → item) e
quatro autocompletes, então é onde uma quebra de widget ou de permissão aparece primeiro.
"""

from uuid import uuid4

import pytest
from playwright.sync_api import expect

from djtools.e2e_fixtures import escolher_autocomplete

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

LISTAGEM = '/almoxarifado/empenhos/'
FORM = '/admin/almoxarifado/empenho/add/'


@pytest.fixture
def processo_para_empenho(servidores_almox):
    """Processo eletrônico do solicitante — equivale ao step ``Dado o cadastro de processo``.

    ``get_or_create`` por assunto: a suíte e2e não dá flush, então repetir a run tem de
    reencontrar o processo em vez de criar outro.
    """
    from protocolo.models import Processo

    servidor = servidores_almox['CoordDeAlmoxSiste']
    processo, _ = Processo.objects.get_or_create(
        assunto='Assunto E2E Almoxarifado',
        defaults={'vinculo_cadastro': servidor.get_vinculo(), 'tipo': 1, 'setor_origem': servidor.setor},
    )
    return processo


def test_listagem_de_empenhos_filtra(logado_almox):
    page = logado_almox('CoordDeAlmoxSiste')
    page.goto(LISTAGEM)
    expect(page.get_by_role('heading', name='Empenhos')).to_be_visible()

    # O empenho do seed do módulo (almoxarifado/tests/e2e/seed.py).
    page.fill('input[name=numero_empenho]', '20193012RE')
    page.click('input[name=buscaempenho_form]')
    expect(page.get_by_text('20193012RE').first).to_be_visible()


def test_cadastra_empenho_e_empenha_item(logado_almox, processo_para_empenho):
    """Fluxo completo: cria o empenho, depois empenha um item nele."""
    page = logado_almox('CoordDeAlmoxSiste')
    # O form valida o formato: "9999NE123456" — depois do NE são SEIS DÍGITOS, não hex.
    numero = f'2019NE{uuid4().int % 10**6:06d}'

    page.goto(FORM)
    page.fill('input[name=numero]', numero)
    escolher_autocomplete(page, 'processo', processo_para_empenho.assunto)
    escolher_autocomplete(page, 'tipo_material', 'Consumo')
    escolher_autocomplete(page, 'pessoa_fisica', 'CoordDeAlmoxSiste')
    page.click('input[name=_save]')

    # Pós-save o SUAP vai para a tela do empenho, cujo h2 traz o número.
    expect(page.get_by_role('heading', name=f'Empenho {numero}')).to_be_visible()

    from almoxarifado.models import Empenho

    empenho = Empenho.objects.filter(numero=numero).first()
    assert empenho is not None, 'a UI disse que salvou, mas não persistiu'
    assert empenho.processo_id == processo_para_empenho.pk, 'empenho salvo sem o processo escolhido'

    # "Empenhar novo item" mora dentro de um h2, não é link com nome acessível próprio.
    page.get_by_text('Empenhar novo item').first.click()
    page.wait_for_load_state()

    escolher_autocomplete(page, 'material', 'Material de Consumo')
    page.fill('input[name=qtd_empenhada]', '2')
    page.fill('input[name=valor]', '200')
    page.click('input[name=empenhoconsumo_form]')

    expect(page.get_by_text('Item de Empenho cadastrada com sucesso.')).to_be_visible()

    from almoxarifado.models import EmpenhoConsumo

    assert EmpenhoConsumo.objects.filter(empenho=empenho).exists(), 'item não vinculado ao empenho'


def test_contador_nao_acessa_empenhos(logado_almox):
    """Empenho é do almoxarifado; o Contador Administrador não entra (ver test_permissoes)."""
    page = logado_almox('ContadorAdministra')
    assert page.goto(LISTAGEM).status == 403
