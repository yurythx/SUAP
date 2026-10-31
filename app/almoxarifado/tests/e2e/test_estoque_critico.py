"""Fluxo: controle de estoque crítico (``/almoxarifado/situacao_estoque/``).

Não tinha cenário no behave, apesar de estar no menu e de ser o que avisa o
almoxarifado antes de faltar material. Duas propriedades importam: a tela é **escopada pelo
campus do usuário** (o título traz a sigla) e é restrita a coordenação/auditoria.
"""

import pytest
from playwright.sync_api import expect

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

URL = '/almoxarifado/situacao_estoque/'
CONFIGURACAO = '/almoxarifado/configuracao_estoque/'
IMPORTAR_CSV = '/almoxarifado/importar_estoque_csv/'


def test_situacao_do_estoque_e_escopada_pelo_campus_do_usuario(logado_almox, servidores_almox):
    """O h2 traz a sigla do campus: é assim que se vê que a tela não vaza outro campus."""
    sigla = servidores_almox['CoordDeAlmoxSiste'].setor.sigla
    page = logado_almox('CoordDeAlmoxSiste')
    page.goto(URL)

    expect(page.get_by_role('heading', name=f'Situação do Estoque {sigla}')).to_be_visible()


def test_permite_declarar_material_controlado(logado_almox):
    """Sem material controlado a tela não tem o que monitorar — o botão é o começo do fluxo."""
    page = logado_almox('CoordDeAlmoxSiste')
    page.goto(URL)
    expect(page.get_by_role('link', name='Adicionar Material Controlado')).to_be_visible()


def test_operador_nao_ve_estoque_critico(logado_almox):
    """``menu.yaml`` restringe a tela a coordenação e auditoria — Operador fica fora."""
    page = logado_almox('OperadDeAlmoxa')
    assert page.goto(URL).status == 403


def test_configuracao_de_estoque_define_os_parametros_de_controle(logado_almox):
    """É onde se declara tempo e intervalo de aquisição — o que alimenta o estoque crítico.

    Sem esses parâmetros a tela de situação do estoque não tem como classificar nada como
    crítico, então esta tela é pré-requisito daquela.
    """
    page = logado_almox('CoordDeAlmoxSiste')
    page.goto(CONFIGURACAO)

    expect(page.get_by_role('heading', name='Controle de Estoque de Materiais')).to_be_visible()
    expect(page.locator('input[name=tempo_aquisicao]')).to_be_visible()
    expect(page.locator('input[name=intervalo_aquisicao]')).to_be_visible()


def test_importacao_de_estoque_por_csv_e_restrita(logado_almox):
    """Carga em massa de estoque não é do coordenador sistêmico — nem dele.

    A tela está no menu raiz do Almoxarifado com um único grupo exigido; travar o 403 aqui
    evita que uma frouxidão de permissão abra carga em massa de saldo para quem opera o dia
    a dia.
    """
    page = logado_almox('CoordDeAlmoxSiste')
    assert page.goto(IMPORTAR_CSV).status == 403
