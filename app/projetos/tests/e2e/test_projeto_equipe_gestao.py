"""Fluxo: gestão da coordenação do projeto — substituir o coordenador e indicar o membro auxiliar.

São as duas telas que mudam QUEM gerencia o projeto: a substituição troca a participação
responsável (e com ela o ``vinculo_coordenador``, que é o que as permissões do módulo leem) e
registra o histórico; o auxiliar ganha as permissões de edição do coordenador sem sê-lo
(``tem_permissao(..., pode_auxiliar=True)``). A regressão que se pega é a troca não chegar ao
projeto — o coordenador antigo seguiria gerenciando e o novo não.
"""

import pytest

from djtools.e2e_fixtures import popup_em
from djtools.e2e_ui import Tela
from projetos.tests.e2e.conftest import clicar_em, vinculo

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

PROJETO = '/projetos/projeto/{}/'
ABA_EQUIPE = 'Equipe'
ALTERAR_COORDENADOR = '/projetos/alterar_coordenador/{}/'
INDICAR_AUXILIAR = '/projetos/indicar_auxiliar_projeto/{}/'


@pytest.fixture
def projeto_com_membro(projeto_novo):
    """Projeto em edição com o ``outro_coordenador`` como membro (servidor, não responsável)."""
    from projetos.tests.factories import ParticipacaoFactory

    projeto = projeto_novo()
    ParticipacaoFactory(projeto=projeto, vinculo_pessoa=vinculo('outro_coordenador'))
    return projeto


def test_substituicao_do_coordenador(logado_projetos, projeto_com_membro):
    """O membro servidor vira o responsável; o antigo coordenador segue na equipe, não mais responsável."""
    from projetos.models import Participacao, ProjetoHistoricoDeEnvio

    projeto = projeto_com_membro
    tela = Tela(logado_projetos('coordenador_projeto')).ir(PROJETO.format(projeto.pk))

    tela.clicar_aba(ABA_EQUIPE)
    clicar_em(tela, ALTERAR_COORDENADOR.format(projeto.pk))
    popup = popup_em(tela, ALTERAR_COORDENADOR.format(projeto.pk)).preencher_formulario(
        [('Novo Coordenador', 'lista', 'Outro Coordenador E2E'), ('Justificativa', 'textarea', 'Afastamento do coordenador')]
    )
    tela = popup.salvar_no_popup('Enviar').sucesso('Coordenador alterado com sucesso.')

    responsaveis = Participacao.objects.filter(projeto=projeto, responsavel=True).values_list('vinculo_pessoa', flat=True)
    assert list(responsaveis) == [vinculo('outro_coordenador').pk], 'a UI disse que alterou, mas o responsável não mudou'
    assert Participacao.objects.filter(projeto=projeto, vinculo_pessoa=vinculo('coordenador_projeto'), responsavel=False).exists(), (
        'o coordenador antigo saiu da equipe em vez de só deixar a coordenação'
    )
    projeto.refresh_from_db()
    assert projeto.vinculo_coordenador == vinculo('outro_coordenador'), 'a participação mudou, mas o coordenador do projeto não'
    assert ProjetoHistoricoDeEnvio.objects.filter(projeto=projeto, parecer_devolucao__contains='Afastamento do coordenador').exists(), (
        'a troca não ficou no histórico do projeto'
    )


def test_indicacao_do_membro_auxiliar(logado_projetos, projeto_com_membro):
    """ "Indicar Auxiliar" só lista membros ativos não responsáveis e grava ``Projeto.auxiliar``."""
    projeto = projeto_com_membro
    tela = Tela(logado_projetos('coordenador_projeto')).ir(PROJETO.format(projeto.pk))

    tela.clicar_aba(ABA_EQUIPE)
    clicar_em(tela, INDICAR_AUXILIAR.format(projeto.pk))
    popup = popup_em(tela, INDICAR_AUXILIAR.format(projeto.pk)).preencher(
        'Membro Auxiliar do Projeto', 'lista', 'Outro Coordenador E2E (159005) (Servidor)'
    )
    popup.salvar_no_popup('Salvar').sucesso('Membro auxiliar indicado com sucesso.')

    projeto.refresh_from_db()
    assert projeto.auxiliar == vinculo('outro_coordenador'), 'a UI disse que indicou, mas o auxiliar não persistiu'
