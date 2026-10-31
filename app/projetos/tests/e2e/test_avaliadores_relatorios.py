"""Relatórios de avaliadores do Gerente Sistêmico: quem é avaliador cadastrado e quem foi indicado em cada edital.

"Lista de Avaliadores Cadastrados" é quem declarou área temática de interesse (o banco de onde
a indicação escolhe); "Lista de Avaliadores de Projetos" é quem de fato foi indicado, por edital,
com exportação para XLS. A regressão que se pega: o filtro por área/edital deixar de filtrar —
o gestor montaria a comissão com a lista errada.
"""

from __future__ import annotations

import datetime
from typing import TYPE_CHECKING

import pytest
from playwright.sync_api import Locator, expect

from djtools.e2e_ui import Tela
from projetos.tests.e2e.conftest import vinculo

if TYPE_CHECKING:
    from projetos.models import Edital

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

LISTAR_AVALIADORES = '/projetos/listar_avaliadores/'
LISTAR_AVALIADORES_DE_PROJETOS = '/projetos/listar_avaliadores_de_projetos/'


def celula(tela: Tela, texto: str) -> Locator:
    """A célula com exatamente ``texto`` — a mesma sonda serve à presença e à ausência."""
    return tela.loc(f'//td[normalize-space(.)="{texto}"]')


def test_avaliadores_cadastrados_por_area_tematica(logado_projetos, areas_tematicas_do):
    """Filtrado por "Cultura", lista quem tem a área e não quem não tem."""
    from projetos.models import AreaTematica

    cultura = AreaTematica.objects.get(descricao='Cultura')
    cultura.vinculo.add(areas_tematicas_do('avaliador'))
    cultura.vinculo.remove(areas_tematicas_do('segundo_avaliador'))
    AreaTematica.objects.exclude(pk=cultura.pk).first().vinculo.add(vinculo('segundo_avaliador'))
    tela = Tela(logado_projetos('gerente')).ir(LISTAR_AVALIADORES)

    tela.ver_titulo('Lista de Avaliadores Cadastrados').preencher_formulario(
        [('Nome', 'texto', 'Avaliador'), ('Filtrar por Área Temática:', 'lista', 'Cultura')]
    )
    tela.clicar_botao('Enviar')

    linha = tela.esperar().linha('Avaliador Extensão E2E')
    linha.ver_texto('Cultura')
    assert not tela.loc('//td[contains(normalize-space(.), "Segundo Avaliador E2E")]').count(), 'o filtro por área listou avaliador de outra área'


@pytest.fixture
def indicacoes_no_edital(projeto_enviado_em) -> Edital:
    """Dois editais em seleção, cada um com um projeto e uma indicação — do ``avaliador`` num, do ``segundo_avaliador`` no outro."""
    from projetos.tests.factories import AvaliadorIndicadoFactory

    pre_selecao = {'pre_aprovado': True, 'data_pre_avaliacao': datetime.date.today()}
    este = projeto_enviado_em('selecao', **pre_selecao)
    outro = projeto_enviado_em('selecao', **pre_selecao)
    AvaliadorIndicadoFactory(projeto=este, vinculo=vinculo('avaliador'))
    AvaliadorIndicadoFactory(projeto=outro, vinculo=vinculo('segundo_avaliador'))
    return este.edital


def test_avaliadores_indicados_no_edital_e_exportacao(logado_projetos, indicacoes_no_edital):
    """Filtrado pelo edital, lista só quem foi indicado nele; "Exportar para XLS" gera a planilha pela tarefa."""
    edital = indicacoes_no_edital
    tela = Tela(logado_projetos('gerente')).ir(LISTAR_AVALIADORES_DE_PROJETOS)  # o rótulo da opção é o `str` do edital

    tela.ver_titulo('Lista de Avaliadores de Projeto').preencher('Filtrar por Edital:', 'lista', str(edital)).clicar_botao('Enviar')

    expect(celula(tela.esperar(), 'Avaliador Extensão E2E')).to_have_count(1)
    assert not celula(tela, 'Segundo Avaliador E2E').count(), 'o filtro por edital listou avaliador indicado em outro edital'

    tela.clicar_botao('Exportar para XLS')
    tela.esperar().ver_texto('Arquivo gerado com sucesso.')  # `@task` roda na request sob teste; a tela é a da tarefa


@pytest.mark.parametrize(('papel', 'status'), [('gerente', 200), ('coordenador_extensao', 403), ('avaliador', 403)])
def test_relatorios_de_avaliadores_por_papel(logado_projetos, projetos_seed, papel, status):
    """``pode_visualizar_avaliadores_externos``: Gerente, Auditor e Visualizador — não o Coordenador de Extensão."""
    tela = Tela(logado_projetos(papel))
    rotas = (LISTAR_AVALIADORES, LISTAR_AVALIADORES_DE_PROJETOS)

    assert {rota: tela.buscar(rota).status for rota in rotas} == dict.fromkeys(rotas, status)
