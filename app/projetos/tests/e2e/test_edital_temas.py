"""Fluxo: temas do edital e áreas temáticas de interesse do avaliador.

Os dois lados do mesmo filtro: o edital declara os temas aceitos (aba "Temas", quando o edital
exige tema) e o servidor declara as áreas temáticas em que quer avaliar ("Tornar-se Avaliador")
— a indicação de avaliador só oferece quem tem interesse na área do projeto. Pega a regressão do
ciclo dos temas (filtrar por área, marcar e salvar, remover pela aba), do salvar sem nenhum tema
marcado, e da gravação das áreas de interesse pelo widget de escolha em popup.
"""

import pytest
from playwright.sync_api import expect

from djtools.e2e_ui import Tela
from projetos.tests.e2e.conftest import clicar_em

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

EDITAL = '/projetos/edital/{}/'
ADICIONAR_TEMA = '/projetos/adicionar_tema_edital/{}/'
SALVAR_TEMAS = '/projetos/salvar_temas_edital/{}/'
REMOVER_TEMA = '/projetos/remover_tema_edital/{}/{}/'
AREAS_DE_INTERESSE = '/projetos/indicar_areas_tematicas_de_interesse/'


def test_temas_do_edital_adicionar_e_remover(logado_projetos, edital_novo, catalogo_do_edital):
    """Filtrar por área → marcar um tema → salvar; depois remover pela aba "Temas" do edital."""
    edital = edital_novo()
    tema, outro = catalogo_do_edital.temas
    tela = Tela(logado_projetos('gerente')).ir(EDITAL.format(edital.pk))

    tela.clicar_aba('Temas').ver_texto('Nenhum tema cadastrado.')
    clicar_em(tela, ADICIONAR_TEMA.format(edital.pk))
    tela.ver_titulo('Adicionar Tema').preencher('Filtrar por Área Temática', 'lista', 'Cultura').clicar_botao('Enviar')
    expect(tela.loc(f'//form[@action="{SALVAR_TEMAS.format(edital.pk)}"]')).to_be_visible()  # o "Salvar" posta para outra rota
    tela.selecionar_item(tema.descricao).clicar_botao('Salvar')

    tela.esperar().sucesso('Temas adicionados com sucesso.')
    assert list(edital.temas.all()) == [tema], f'temas gravados: {list(edital.temas.all())} (o {outro} não foi marcado)'

    tela.ir(EDITAL.format(edital.pk)).clicar_aba('Temas')
    # O ícone leva `?origem=1` (volta para o edital, não para a tela de adicionar): a rota pura fica na constante.
    clicar_em(tela, REMOVER_TEMA.format(edital.pk, tema.pk) + '?origem=1')
    tela.esperar().sucesso('Tema removido com sucesso.')
    assert not edital.temas.exists(), 'a UI disse que removeu, mas o tema continua no edital'


def test_salvar_temas_sem_nenhum_marcado_e_recusado(logado_projetos, edital_novo, catalogo_do_edital):
    edital = edital_novo()
    tela = Tela(logado_projetos('gerente')).ir(ADICIONAR_TEMA.format(edital.pk))

    tela.ver_texto(catalogo_do_edital.temas[0].descricao).clicar_botao('Salvar')
    tela.esperar().erro('Nenhum tema selecionado.')
    assert ADICIONAR_TEMA.format(edital.pk).rstrip('/') in tela.pagina.url, f'não voltou à tela de temas: {tela.pagina.url}'
    assert not edital.temas.exists(), 'a UI recusou, mas gravou tema no edital'


def test_servidor_indica_areas_tematicas_de_interesse(logado_projetos, areas_tematicas_do):
    """O ``Servidor`` (``pode_se_tornar_avaliador``) marca "Cultura" e passa a constar como interessado nela."""
    from projetos.models import AreaTematica

    servidor = areas_tematicas_do('coordenador_projeto')
    AreaTematica.objects.get(descricao='Cultura').vinculo.remove(servidor)  # parte de "sem interesse", o teste prova a gravação
    tela = Tela(logado_projetos('coordenador_projeto')).ir(AREAS_DE_INTERESSE)

    tela.ver_titulo('Tornar-se Avaliador: Indique as Áreas Temáticas de seu Interesse')
    tela.preencher('Áreas Temáticas', 'checkbox popup', 'Cultura').clicar_botao('Enviar')

    tela.esperar().sucesso('Área de conhecimento cadastrada com sucesso.')
    tela.quadro('Áreas Temáticas do Servidor').ver_texto('Cultura')
    assert AreaTematica.objects.filter(descricao='Cultura', vinculo=servidor).exists(), 'a UI disse que salvou, mas não persistiu'
