"""Fluxo: as listagens de editais de extensão e quem enxerga o quê (feature 001, parte de leitura).

São as portas de entrada do módulo: "Editais" (todos), "Submeter Projetos" (inscrição aberta),
"Indicar Avaliador" (editais em avaliação) e o filtro por ano. A regressão que interessa aqui é
de ESCOPO: cada lista é um queryset por fase do edital e, na de avaliação, por campus do
usuário — um edital na fase errada ou de outro escopo aparecendo (ou sumindo) é o defeito. Por
isso cada teste afirma um edital que tem de estar e outro, na mesma página, que não pode.

Também aqui a matriz de permissão das rotas da fatia, por status HTTP.
"""

import pytest
from playwright.sync_api import Locator, expect

from djtools.e2e_ui import Tela

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

EDITAIS = '/projetos/editais/'
EDITAIS_ABERTOS = '/projetos/editais_abertos/'
EDITAIS_PARA_AVALIACAO = '/projetos/editais_para_avaliacao/'
FILTRAR_POR_ANO = '/projetos/filtrar_editais_por_ano/'
CLASSIFICACAO = '/projetos/classificacao_projetos/'
AUTORIZAR = '/projetos/autorizar_edital/{}/{}/'


def titulo_do_cartao(tela: Tela, titulo: str) -> Locator:
    """O título (``h4``) do cartão do edital. A mesma sonda serve à presença e à ausência."""
    return tela.loc(f'//h4[strong[normalize-space(.)="{titulo}"]]')


@pytest.mark.parametrize(
    ('periodo', 'esperado', 'ausente', 'queryset'),
    [
        ('Em Inscrição', 'inscricao', 'divulgado', 'em_inscricao'),
        # "Em Execução" é o edital divulgado com projeto aprovado ainda não concluído — e por isso
        # mesmo ele NÃO é "Concluído" (`EditalQueryset.concluidos` exclui os em execução).
        ('Em Execução', 'divulgado', 'inscricao', 'em_execucao'),
    ],
)
def test_servidor_filtra_os_editais_por_periodo(logado_projetos, projetos_seed, periodo, esperado, ausente, queryset):
    from projetos.models import Edital

    edital, outro = projetos_seed.editais[esperado], projetos_seed.editais[ausente]
    tela = Tela(logado_projetos('coordenador_projeto')).ir(EDITAIS)
    tela.ver_titulo('Todos os editais')

    tela.ir(f'{EDITAIS}?ano={edital.inicio_inscricoes.year}&periodo={periodo}')
    expect(titulo_do_cartao(tela, edital.titulo)).to_have_count(1)
    assert not titulo_do_cartao(tela, outro.titulo).count(), f'o filtro "{periodo}" listou edital de outra fase'
    assert getattr(Edital.objects, queryset)().filter(pk=edital.pk).exists(), f'a tela listou em "{periodo}" um edital que o ORM não põe lá'


def test_servidor_ve_so_os_editais_com_inscricao_aberta_para_submeter(logado_projetos, projetos_seed):
    em_inscricao, divulgado = projetos_seed.editais['inscricao'], projetos_seed.editais['divulgado']
    tela = Tela(logado_projetos('coordenador_projeto')).ir(EDITAIS_ABERTOS)

    tela.cartao(em_inscricao.titulo).ver_botao('Adicionar Projeto')
    expect(titulo_do_cartao(tela, em_inscricao.titulo)).to_have_count(1)
    assert not titulo_do_cartao(tela, divulgado.titulo).count(), 'edital já divulgado oferecido para submissão'


@pytest.mark.parametrize(
    ('papel', 've_edital_geral'),
    [
        ('gerente', True),
        # Sem `pode_gerenciar_edital`, a lista se restringe aos editais DE CAMPUS com oferta na UO
        # do usuário (`views.editais_para_avaliacao`): o geral em avaliação some.
        ('coordenador_extensao', False),
    ],
)
def test_editais_para_indicar_avaliador_por_escopo(logado_projetos, projetos_seed, papel, ve_edital_geral):
    de_campus, geral = projetos_seed.editais['inscricao'], projetos_seed.editais['resultado_parcial']
    assert de_campus.campus_especifico, 'o seed perdeu a premissa do teste'
    assert not geral.campus_especifico, 'o seed perdeu a premissa do teste'

    tela = Tela(logado_projetos(papel)).ir(EDITAIS_PARA_AVALIACAO)
    tela.ver_titulo('Editais em Avaliação')
    expect(tela.loc(f'//td[normalize-space(.)="{de_campus.titulo}"]')).to_have_count(1)
    assert tela.loc(f'//td[normalize-space(.)="{geral.titulo}"]').count() == int(ve_edital_geral)


def test_filtro_de_editais_por_ano_responde_json(logado_projetos, projetos_seed):
    """O endpoint que alimenta o select de edital nos filtros por ano (AJAX)."""
    edital = projetos_seed.editais['inscricao']
    resposta = Tela(logado_projetos('coordenador_projeto')).buscar(f'{FILTRAR_POR_ANO}?ano={edital.inicio_inscricoes.year}')

    assert resposta.status == 200, resposta.text()
    titulos = {registro['fields']['titulo'] for registro in resposta.json()}
    assert edital.titulo in titulos, f'o edital do ano não veio no JSON: {sorted(titulos)}'


def test_filtro_de_editais_por_ano_sem_edital_responde_lista_vazia(logado_projetos, projetos_seed):
    resposta = Tela(logado_projetos('coordenador_projeto')).buscar(f'{FILTRAR_POR_ANO}?ano=1900')
    assert resposta.status == 200
    assert resposta.json() == []


# Matriz medida no navegador, só de papéis que NÃO podem (o acesso permitido de cada rota já é
# exercitado pelos fluxos da fatia).
NEGADOS = [
    ('coordenador_extensao', CLASSIFICACAO),
    ('avaliador', CLASSIFICACAO),
    ('coordenador_projeto', EDITAIS_PARA_AVALIACAO),
    ('aluno', EDITAIS_ABERTOS),
]


@pytest.mark.parametrize(('papel', 'rota'), NEGADOS)
def test_papel_sem_permissao_recebe_403(logado_projetos, papel, rota):
    assert Tela(logado_projetos(papel)).buscar(rota).status == 403


def test_coordenador_de_extensao_nao_autoriza_edital(logado_projetos, edital_novo):
    from projetos.models import Edital

    edital = edital_novo(autorizado=None, autorizado_em=None)
    assert Tela(logado_projetos('coordenador_extensao')).buscar(AUTORIZAR.format(edital.pk, 1)).status == 403
    assert Edital.objects.get(pk=edital.pk).autorizado is None, 'o 403 veio, mas o edital foi autorizado mesmo assim'
