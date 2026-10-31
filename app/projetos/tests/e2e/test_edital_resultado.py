"""Fluxo: classificar os projetos do edital e publicar o resultado (features 005 e 010, lado do edital).

É a ponta do edital onde a regra de negócio vira lista pública: a rotina "Classificar Projetos"
ordena os pré-selecionados pela pontuação e aprova só os que cabem na oferta do campus E
atingem o ponto de corte (metade da pontuação máxima); o resultado parcial e o final mostram
os aprovados de cada janela, e o relatório de classificação lista todos os pré-selecionados. A
regressão cara aqui é aprovar quem não cabe na vaga, ou publicar o resultado fora da janela.
"""

import pytest
from playwright.sync_api import Locator, expect

from djtools.e2e_ui import Tela
from projetos.tests.e2e.conftest import clicar_em

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

RESULTADO = '/projetos/resultado_edital/{}/'
DIVULGAR = '/projetos/divulgar_resultado_edital/{}/{}/'
CLASSIFICACAO = '/projetos/classificacao_projetos/'
CLASSIFICACAO_DO_EDITAL = '/projetos/classificacao_projetos_edital/{}/'
EDITAL = '/projetos/edital/{}/'
EXECUTAR_CLASSIFICACAO = '/projetos/executar_rotina_classificacao_edital/{}/'

FINAL, PARCIAL = 1, 2


def celula(tela: Tela, texto: str) -> Locator:
    """A célula de tabela com exatamente ``texto``. A mesma sonda serve à presença e à ausência."""
    return tela.loc(f'//td[normalize-space(.)="{texto}"]')


@pytest.mark.parametrize(
    ('periodo', 'estado', 'aprovado', 'fora_da_janela', 'rotulo', 'por_campus'),
    [
        (FINAL, 'divulgado', 'aprovado_divulgado', 'resultado_parcial', 'RESULTADO FINAL', True),
        (FINAL, 'divulgado_geral', 'aprovado_divulgado_geral', 'resultado_parcial', 'RESULTADO FINAL', False),
        (PARCIAL, 'resultado_parcial', 'aprovado_parcial', 'divulgado', 'RESULTADO PARCIAL', True),
    ],
)
def test_servidor_consulta_o_resultado_do_edital(logado_projetos, projetos_seed, periodo, estado, aprovado, fora_da_janela, rotulo, por_campus):
    """Cada menu de resultado lista só o edital da sua janela; o resultado agrupa pela forma de seleção.

    Seleção por campus agrupa os aprovados pelo nome da UO; seleção geral, num grupo "Geral".
    """
    edital, projeto = projetos_seed.editais[estado], projetos_seed.projetos[aprovado]
    grupo = projetos_seed.uo.nome if por_campus else 'Geral'
    assert projeto.aprovado, 'o seed perdeu a premissa do teste'
    assert edital.pode_visualizar_resultado(None, periodo), 'o seed perdeu a premissa do teste'

    tela = Tela(logado_projetos('coordenador_projeto')).ir(f'{RESULTADO.format(periodo)}?ano={edital.inicio_inscricoes.year}')
    expect(celula(tela, edital.titulo)).to_have_count(1)
    assert not celula(tela, projetos_seed.editais[fora_da_janela].titulo).count(), 'edital de outra janela listado'

    clicar_em(tela, DIVULGAR.format(edital.pk, periodo))
    tela.ver_texto(f'{rotulo} DO {edital.titulo}').ver_texto(f'{grupo} - 1 Projeto(s) aprovado(s)').ver_texto(projeto.titulo)


@pytest.mark.parametrize(('estado', 'aprovado'), [('divulgado', 'aprovado_divulgado'), ('divulgado_geral', 'aprovado_divulgado_geral')])
def test_gerente_ve_a_classificacao_do_edital(logado_projetos, projetos_seed, estado, aprovado):
    """O relatório de classificação lista os pré-selecionados, na seleção por campus e na geral."""
    edital, projeto = projetos_seed.editais[estado], projetos_seed.projetos[aprovado]
    tela = Tela(logado_projetos('gerente')).ir(f'{CLASSIFICACAO}?ano={edital.inicio_inscricoes.year}')

    tela.linha(edital.titulo)
    clicar_em(tela, CLASSIFICACAO_DO_EDITAL.format(edital.pk))
    tela.ver_texto(f'CLASSIFICAÇÃO DO {edital.titulo}').linha(projeto.titulo).ver_texto('(Coordenador)')
    assert projeto.pre_aprovado, 'a classificação listou projeto que não foi pré-selecionado'


def test_rotina_de_classificacao_aprova_so_quem_cabe_na_oferta(logado_projetos, edital_para_classificar):
    """Nota 9 e nota 7, UMA vaga no campus: a rotina classifica 1º e 2º e aprova só o primeiro.

    A rotina é assíncrona por desenho (``tasks.executa_rotina_classificacao_projetos_edital``); sob
    teste roda na própria request e a tela é a da tarefa (``/djtools/process/<uuid>/``). Em seguida
    o gerente pré-visualiza o resultado parcial — janela de seleção, só ele pode — e só o aprovado
    aparece.
    """
    from projetos.models import Projeto

    edital = edital_para_classificar
    tela = Tela(logado_projetos('gerente')).ir(EDITAL.format(edital.pk))
    clicar_em(tela, EXECUTAR_CLASSIFICACAO.format(edital.pk))
    tela.ver_texto('Rotina de classificação dos projetos executada com sucesso.')

    resultado = {p.titulo.rsplit(' ', 1)[-1]: (p.classificacao, p.aprovado) for p in Projeto.objects.filter(edital=edital)}
    assert resultado == {'9': (1, True), '7': (2, False)}, f'classificação/aprovação por nota: {resultado}'

    tela.ir(DIVULGAR.format(edital.pk, PARCIAL))
    expect(celula(tela, f'{edital.titulo} nota 9')).to_have_count(1)
    assert not celula(tela, f'{edital.titulo} nota 7').count(), 'o não aprovado apareceu no resultado parcial'
