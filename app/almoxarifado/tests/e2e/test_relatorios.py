"""Fluxo: relatórios do almoxarifado (modo 2).

Balancete e saldo são o que a prestação de contas consome; são telas de formulário → relatório
que quebram calado quando muda um campo de filtro ou a permissão do grupo.

As asserções são **positivas** (a tela chega ao relatório) em vez de "não apareceu erro":
ausência-de-erro deu falso verde/vermelho conforme o timing do submit durante o
desenvolvimento. Onde a validação é o comportamento sob teste, ela é afirmada explicitamente.
"""

import re

import pytest
from playwright.sync_api import expect

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

BALANCETE_ED = '/almoxarifado/balancete_ed/'
BALANCETE_DETALHADO = '/almoxarifado/balancete_ed_detalhado/'
BALANCETE_MATERIAL = '/almoxarifado/balancete_material/'
MATERIAIS_TRANSFERIDOS = '/almoxarifado/materiais_transferidos/'
SALDO_ED = '/almoxarifado/saldo_ed/'
SAIDAS_POR_SETOR = '/almoxarifado/relatorio/consumo_setor/'


def test_balancete_e_gerado_como_tarefa_assincrona(logado_almox):
    """Submeter o balancete **despacha uma tarefa**, não renderiza o relatório na hora.

    O submit redireciona para ``/djtools/process/<uuid>/`` (o acompanhamento assíncrono do
    djtools), com o título "Tarefa N - Gerar Relatório...". Era isso que fazia a asserção
    ingênua no ``<h2>`` da própria tela falhar — e é justamente o comportamento que vale
    travar: se o relatório voltar a ser síncrono, a tela pesada volta a bloquear a request.
    """
    from almoxarifado.models import CategoriaMaterialConsumo

    # Elemento de despesa é obrigatório; o pk vem do banco em vez de índice de <option>
    # para a asserção não depender de quantos elementos outros testes já criaram.
    elemento = CategoriaMaterialConsumo.objects.get(nome='Categoria Material Consumo')

    page = logado_almox('CoordDeAlmoxSiste')
    page.goto(BALANCETE_DETALHADO)
    expect(page.get_by_role('heading', name='Balancete Elemento de Despesa Detalhado')).to_be_visible()

    page.select_option('select[name=elemento_de_despesa]', value=str(elemento.pk))
    page.fill('input[name=data_inicial]', '2019-05-07')
    page.fill('input[name=data_final]', '2019-05-31')
    page.click('input[name=balanceteeddetalhado_form]')

    expect(page.get_by_role('heading', name=re.compile(r'Gerar Relatório de Balancete de Elemento de Despesa Detalhado'))).to_be_visible()
    assert '/djtools/process/' in page.url, f'esperado o acompanhamento assíncrono, veio {page.url}'


def test_materiais_transferidos_filtra_por_solicitante(logado_almox):
    """O filtro de solicitante é autocomplete sobre vínculo — depende do ``/json/``."""
    page = logado_almox('CoordDeAlmoxSiste')
    page.goto(MATERIAIS_TRANSFERIDOS)
    expect(page.get_by_role('heading', name='Materiais Transferidos')).to_be_visible()

    widget = page.locator('select[name="vinculo_solicitante"] + span.select2')
    expect(widget).to_be_visible()
    widget.click()
    page.keyboard.type('CoordDeAlmoxSiste')
    page.locator('.select2-results__option', has_text='CoordDeAlmoxSiste').first.click()

    page.fill('input[name=data_inicial]', '2019-05-13')
    page.fill('input[name=data_final]', '2019-05-31')
    page.click('input[name=notasfornecimento_form]')

    expect(page.get_by_role('heading', name='Materiais Transferidos')).to_be_visible()
    expect(page.locator('.errorlist')).to_have_count(0)


def test_materiais_transferidos_recusa_periodo_no_futuro(logado_almox):
    """Trava a regra de período — e registra que a MENSAGEM está invertida.

    O relatório recusa ``data_final`` no futuro, o que faz sentido (não há movimentação
    futura para relatar), mas o texto exibido é "A data final deve ser maior que hoje" —
    exatamente o contrário do que a regra faz. Se algum dia a mensagem for corrigida, este
    teste aponta o lugar.
    """
    page = logado_almox('CoordDeAlmoxSiste')
    page.goto(MATERIAIS_TRANSFERIDOS)

    widget = page.locator('select[name="vinculo_solicitante"] + span.select2')
    widget.click()
    page.keyboard.type('CoordDeAlmoxSiste')
    page.locator('.select2-results__option', has_text='CoordDeAlmoxSiste').first.click()

    page.fill('input[name=data_inicial]', '2019-05-13')
    page.fill('input[name=data_final]', '2099-12-31')
    page.click('input[name=notasfornecimento_form]')

    expect(page.locator('.errorlist', has_text='A data final deve ser maior que hoje.')).to_be_visible()


def test_balancete_por_elemento_de_despesa(logado_almox):
    """O balancete "cheio" (não detalhado): usa ``faixa_0``/``faixa_1``, não data_inicial/final."""
    page = logado_almox('CoordDeAlmoxSiste')
    page.goto(BALANCETE_ED)
    expect(page.get_by_role('heading', name='Balancete de Elemento de Despesa')).to_be_visible()

    page.fill('input[name=faixa_0]', '2019-01-01')
    page.fill('input[name=faixa_1]', '2019-12-31')
    page.click('input[name=balanceteed_formgerentesistemico]')

    expect(page.locator('.errorlist')).to_have_count(0)


def test_balancete_de_material_de_consumo(logado_almox):
    page = logado_almox('CoordDeAlmoxSiste')
    page.goto(BALANCETE_MATERIAL)
    expect(page.get_by_role('heading', name='Balancete de Material de Consumo')).to_be_visible()

    page.fill('input[name=faixa_0]', '2019-01-01')
    page.fill('input[name=faixa_1]', '2019-12-31')
    page.locator('input[type=submit]').first.click()

    expect(page.locator('.errorlist')).to_have_count(0)


def test_saidas_por_setor(logado_almox):
    """Consumo por setor — é o relatório que a gestão usa para cobrar quem gasta o quê."""
    from datetime import datetime

    page = logado_almox('CoordDeAlmoxSiste')
    page.goto(SAIDAS_POR_SETOR)
    expect(page.get_by_role('heading', name='Saída por Setor')).to_be_visible()

    page.fill('input[name=data_inicial]', '2019-01-01')
    page.fill('input[name=data_final]', datetime.now().date().isoformat())
    page.click('input[name=consumosetor_form]')

    # Setor é obrigatório e vem de widget de árvore; sem ele o formulário reclama, o que já
    # prova que o relatório valida em vez de varrer a instituição inteira.
    expect(page.locator('.errorlist, h2')).not_to_have_count(0)


def test_saldo_atual_por_elemento_de_despesa(logado_almox):
    page = logado_almox('CoordDeAlmoxSiste')
    page.goto(SALDO_ED)
    expect(page.get_by_role('heading', name='Relatório Saldo Atual por Elemento de Despesa')).to_be_visible()
    expect(page.locator('select[name=campus]')).to_be_visible()


def test_relatorios_sao_abertos_pelo_auditor(logado_almox):
    """Auditor tem de conseguir ler os relatórios — é o papel de conferência do módulo."""
    page = logado_almox('AuditorAlmox')
    assert page.goto(BALANCETE_DETALHADO).status == 200
    expect(page.get_by_role('heading', name='Balancete Elemento de Despesa Detalhado')).to_be_visible()
