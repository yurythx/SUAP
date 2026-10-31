"""Fluxo: matriz de grupo x tela — o contrato de acesso do módulo.

O almoxarifado é governado por grupo (16 em ``permissions.yaml``, e o ``menu.yaml`` usa
``groups_required`` na maioria das telas). Regressão aqui é silenciosa: a tela simplesmente
passa a abrir para quem não devia, ou fecha para quem precisa, e nenhum teste de model pega.

A matriz abaixo foi **medida** no navegador, não deduzida do YAML, e é estável entre
execuções. Serve de documentação executável: mudar `permissions.yaml` sem atualizar aqui
quebra o teste, que é o ponto.
"""

import pytest

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

PLANO_CONTAS = '/admin/almoxarifado/planocontasalmox/add/'
ELEMENTO_DESPESA = '/admin/almoxarifado/categoriamaterialconsumo/add/'
MATERIAL_CONSUMO = '/admin/almoxarifado/materialconsumo/'
CATMAT = '/admin/almoxarifado/catmat/'
EMPENHOS = '/almoxarifado/empenhos/'
ESTOQUE_CRITICO = '/almoxarifado/situacao_estoque/'
BALANCETE = '/almoxarifado/balancete_ed_detalhado/'

# (matrícula, url, status esperado)
MATRIZ = [
    # Coordenador de Almoxarifado Sistêmico: opera o módulo, mas NÃO mexe em contabilidade.
    ('CoordDeAlmoxSiste', MATERIAL_CONSUMO, 200),
    ('CoordDeAlmoxSiste', CATMAT, 200),
    ('CoordDeAlmoxSiste', EMPENHOS, 200),
    ('CoordDeAlmoxSiste', ESTOQUE_CRITICO, 200),
    ('CoordDeAlmoxSiste', BALANCETE, 200),
    ('CoordDeAlmoxSiste', PLANO_CONTAS, 403),
    ('CoordDeAlmoxSiste', ELEMENTO_DESPESA, 403),
    # Operador: opera empenho e lê balancete, mas não vê estoque crítico nem cadastros.
    ('OperadDeAlmoxa', EMPENHOS, 200),
    ('OperadDeAlmoxa', BALANCETE, 200),
    ('OperadDeAlmoxa', ESTOQUE_CRITICO, 403),
    ('OperadDeAlmoxa', PLANO_CONTAS, 403),
    # Contador Administrador: é o inverso do coordenador — contabilidade sim, operação não.
    ('ContadorAdministra', PLANO_CONTAS, 200),
    ('ContadorAdministra', ELEMENTO_DESPESA, 200),
    ('ContadorAdministra', EMPENHOS, 403),
    ('ContadorAdministra', ESTOQUE_CRITICO, 403),
    ('ContadorAdministra', BALANCETE, 403),
    # Auditor: leitura de conferência (empenho, estoque, balancete), nenhum cadastro.
    ('AuditorAlmox', EMPENHOS, 200),
    ('AuditorAlmox', ESTOQUE_CRITICO, 200),
    ('AuditorAlmox', BALANCETE, 200),
    ('AuditorAlmox', PLANO_CONTAS, 403),
    ('AuditorAlmox', ELEMENTO_DESPESA, 403),
]


@pytest.mark.parametrize(('matricula', 'url', 'esperado'), MATRIZ, ids=lambda v: str(v).replace('/', '_'))
def test_matriz_de_acesso(logado_almox, matricula, url, esperado):
    page = logado_almox(matricula)
    obtido = page.goto(url).status
    assert obtido == esperado, f'{matricula} em {url}: esperado {esperado}, obtido {obtido}'


def test_gerenciador_de_catalogo_nao_tem_acesso_administrativo(logado_almox):
    """Achado a confirmar com o negócio, travado como está hoje.

    "Gerenciador do Catálogo de Materiais" sugere poder sobre o catálogo, mas no conjunto de
    permissões atual o grupo não abre nem ``materialconsumo`` nem ``catmat``. Se isso for
    engano de ``permissions.yaml``, este teste é o lugar de registrar a correção.
    """
    page = logado_almox('GereDoCataDeMate')
    assert page.goto(MATERIAL_CONSUMO).status == 403
    assert page.goto(CATMAT).status == 403


def test_servidor_sem_grupo_de_almoxarifado_nao_entra(logado_almox):
    """Servidor só com o grupo `Servidor`, nenhum do almoxarifado — a linha de base do módulo."""
    page = logado_almox('ServidorSemGrupo')
    assert page.goto(EMPENHOS).status == 403
    assert page.goto(ESTOQUE_CRITICO).status == 403
