"""Fluxo: indicar pré-avaliador e monitor quando quem faria o papel está na equipe do projeto.

O Coordenador de Extensão pré-avalia os projetos do campus e vira o monitor deles — salvo quando
ele mesmo integra a equipe: é o "projeto em conflito". O Gerente Sistêmico resolve o conflito
indicando outra pessoa ("Indicar Pré-Avaliador" antes da seleção, "Gerenciar Monitores" depois
da aprovação), e o indicado passa a ver o projeto na própria fila de pré-seleção.

A regressão cara: o indicado não receber o projeto (a pré-seleção trava sem ninguém saber), ou
um membro da equipe poder ser indicado para avaliar/monitorar o próprio projeto. O indicado é
o ``pre_avaliador``, que já nasce no grupo que a indicação dá: a view faz ``groups.add`` e o
cache de grupos por usuário não deixaria desfazer isso no meio da sessão.
"""

import pytest

from djtools.e2e_fixtures import popup_em
from djtools.e2e_ui import Tela
from projetos.tests.e2e.conftest import clicar_em, outra_uo, vinculo

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

INDICAR_PRE_AVALIADOR = '/projetos/indicar_pre_avaliador/'
SELECIONAR_PRE_AVALIADOR = '/projetos/selecionar_pre_avaliador/{}/'
SELECIONAR_PRE_AVALIADOR_DO_PROJETO = '/projetos/selecionar_pre_avaliador_do_projeto/{}/'
SELECIONAR_MONITOR = '/projetos/selecionar_monitor/{}/'
SELECIONAR_MONITOR_DO_PROJETO = '/projetos/selecionar_monitor_do_projeto/{}/'
PRE_AVALIACAO = '/projetos/pre_avaliacao/'
PRE_SELECIONAR = '/projetos/pre_selecionar/{}/'

PRE_AVALIADORA = 'Pré-Avaliadora Sistêmica E2E'
CONFLITO = 'Projetos em conflito são aqueles'


def indicar_no_popup(tela: Tela, rota: str, nome: str) -> Tela:
    """Abre o popup "Indicar ..." pelo link da linha, escolhe o usuário e envia; devolve a página de trás recarregada."""
    clicar_em(tela, rota)
    return popup_em(tela, rota).preencher('Usuário', 'autocomplete multiplo', nome).salvar_no_popup('Enviar')


def test_gerente_indica_pre_avaliador_e_o_indicado_pre_seleciona(logado_projetos, projeto_enviado_em):
    """Projeto coordenado pelo Coordenador de Extensão (em conflito) → a pré-avaliadora indicada o recebe e o pré-seleciona."""
    projeto = projeto_enviado_em('pre_selecao', coordenador='coordenador_extensao')
    edital = projeto.edital
    tela = Tela(logado_projetos('gerente')).ir(INDICAR_PRE_AVALIADOR)

    clicar_em(tela, SELECIONAR_PRE_AVALIADOR.format(edital.pk))
    tela.ver_titulo(f'Selecionar Pré-Avaliadores - {edital.titulo}').ver_texto(CONFLITO).linha(projeto.titulo)
    indicar_no_popup(tela, SELECIONAR_PRE_AVALIADOR_DO_PROJETO.format(projeto.pk), PRE_AVALIADORA).sucesso('Pré-avaliador cadastrado com sucesso.')

    projeto.refresh_from_db()
    assert projeto.vinculo_autor_pre_avaliacao == vinculo('pre_avaliador'), 'a UI disse que indicou, mas o pré-avaliador não persistiu'

    indicada = Tela(logado_projetos('pre_avaliador')).ir(PRE_AVALIACAO)
    indicada.linha(edital.titulo).clicar_icone('exibição')
    indicada.esperar().ver_titulo(f'Pré-Seleção de Projetos - {edital.titulo}')
    clicar_em(indicada, PRE_SELECIONAR.format(projeto.pk))
    indicada.ver_titulo(f'Pré-Seleção de Projetos - {edital.titulo}').sucesso('Projeto pré-avaliado com sucesso.')

    projeto.refresh_from_db()
    assert (projeto.pre_aprovado, projeto.vinculo_monitor) == (True, vinculo('pre_avaliador')), 'o indicado não conseguiu pré-selecionar'


def test_membro_da_equipe_nao_pode_ser_pre_avaliador(logado_projetos, projeto_enviado_em):
    """Indicar o próprio coordenador do projeto é recusado, com a mensagem, e nada é gravado."""
    projeto = projeto_enviado_em('pre_selecao', coordenador='coordenador_extensao')
    tela = Tela(logado_projetos('gerente')).ir(f'{SELECIONAR_PRE_AVALIADOR.format(projeto.edital.pk)}?status_avaliacao=0')

    tela.linha(projeto.titulo)
    indicar_no_popup(tela, SELECIONAR_PRE_AVALIADOR_DO_PROJETO.format(projeto.pk), 'Coordenador Extensão E2E').erro(
        'é membro do projeto e por este motivo não pode ser indicado como pré-avaliador/monitor.'
    )

    projeto.refresh_from_db()
    assert projeto.vinculo_autor_pre_avaliacao is None, 'a UI recusou, mas o membro foi gravado como pré-avaliador'


def test_gerente_indica_monitor_para_projeto_em_conflito(logado_projetos, projeto_enviado_em):
    """Aprovado com o próprio coordenador de monitor → a indicação troca o monitor e o projeto sai da lista de conflito."""
    projeto = projeto_enviado_em('selecao', pre_aprovado=True, aprovado=True, vinculo_monitor=vinculo('coordenador_projeto'))
    tela = Tela(logado_projetos('gerente')).ir(SELECIONAR_MONITOR.format(projeto.edital.pk))

    tela.ver_titulo(f'Selecionar Monitores - {projeto.edital.titulo}').ver_texto(CONFLITO).linha(projeto.titulo)
    indicar_no_popup(tela, SELECIONAR_MONITOR_DO_PROJETO.format(projeto.pk), PRE_AVALIADORA).sucesso('Monitor cadastrado com sucesso.')

    projeto.refresh_from_db()
    assert projeto.vinculo_monitor == vinculo('pre_avaliador'), 'a UI disse que indicou, mas o monitor não persistiu'
    tela.ver_texto('Nenhum projeto pendente de indicação de monitor foi encontrado.')


@pytest.mark.parametrize('rota', [SELECIONAR_PRE_AVALIADOR_DO_PROJETO, SELECIONAR_MONITOR_DO_PROJETO])
def test_coordenador_de_extensao_so_indica_no_proprio_campus(logado_projetos, projeto_enviado_em, rota):
    """O formulário de indicação abre para projeto do campus e é recusado (redirect com "Permissão negada.") para o de outro."""
    alheio = projeto_enviado_em('pre_selecao', uo=outra_uo(), sufixo='alheio')
    proprio = projeto_enviado_em('pre_selecao', edital=alheio.edital, sufixo='proprio')
    tela = Tela(logado_projetos('coordenador_extensao'))

    assert tela.buscar(rota.format(proprio.pk)).status == 200, 'a sonda não abre nem o projeto do próprio campus'
    assert tela.buscar(rota.format(alheio.pk)).status == 302, 'o formulário de indicação abriu para projeto de outro campus'
    tela.ir(PRE_AVALIACAO).erro('Permissão negada.')


@pytest.mark.parametrize(('papel', 'status'), [('gerente', 200), ('coordenador_extensao', 200), ('pre_avaliador', 403), ('coordenador_projeto', 403)])
def test_indicacao_de_pre_avaliador_e_monitor_por_papel(logado_projetos, projetos_seed, papel, status):
    """``pode_avaliar_cancelamento_projeto``: só o Gerente e o Coordenador de Extensão indicam."""
    edital = projetos_seed.editais['pre_selecao']
    tela = Tela(logado_projetos(papel))
    rotas = (INDICAR_PRE_AVALIADOR, SELECIONAR_PRE_AVALIADOR.format(edital.pk), SELECIONAR_MONITOR.format(edital.pk))

    assert {rota: tela.buscar(rota).status for rota in rotas} == dict.fromkeys(rotas, status)


def test_lista_de_editais_para_indicar_pre_avaliador(logado_projetos, projetos_seed):
    """Da inscrição até o início da seleção: o edital em pré-seleção aparece; o já em seleção, não."""
    tela = Tela(logado_projetos('coordenador_extensao')).ir(INDICAR_PRE_AVALIADOR)

    clicar_em(tela, SELECIONAR_PRE_AVALIADOR.format(projetos_seed.editais['pre_selecao'].pk))
    tela.ir(INDICAR_PRE_AVALIADOR)
    assert not tela.loc(f'//a[@href="{SELECIONAR_PRE_AVALIADOR.format(projetos_seed.editais["selecao"].pk)}"]').count(), (
        'edital já em seleção oferecido para indicar pré-avaliador'
    )
