"""Fluxo: o lado do ATENDENTE do erro (feature 002 do behave).

As duas ações que mudam o estado do atendimento: assumir/mover a situação e corrigir a URL de
onde o erro acontece. Ambas são governadas por grupo — `vinculo_pode_ser_atendente` é
`in_group(user, 'Analista')` (`erros/models.py:139`) — e por situação: `get_situacoes_disponiveis`
(`erros/models.py:212`) devolve um conjunto diferente para cada estado, e é dele que sai o menu
"Alterar situação". Se essa tabela regredir, a tela some botões sem dar erro.
"""

import pytest

from djtools.e2e_ui import Tela

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

# URL válida e resolvível (o formulário exige que a view exista) e deliberadamente diferente
# da view do fluxo de abertura — ver a docstring do conftest.
NOVA_URL = 'http://localhost:8000/comum/acessibilidade/'


def test_atendente_assume_e_move_para_em_correcao(logado_erros, erro_aberto):
    """Assumir e depois mover a situação, num teste só: o menu de situações só existe para quem assumiu.

    Assumir tem efeito colateral proposital — `gerenciar_atendente` (`erros/models.py:378`)
    move o erro de "Reportado" para "Em análise" sozinho —, e é por isso que "Devolver"
    aparece logo depois. A régua de situação é afirmada por `ver_status`, que exige o passo
    **ativo**: os quatro rótulos estão sempre no DOM.
    """
    from erros.models import Erro

    tela = Tela(logado_erros('atendente')).ir(erro_aberto.get_absolute_url())
    tela.ver_botao('Assumir')
    tela.clicar_botao('Assumir')

    tela.sucesso('Você agora é o Atendente Principal deste erro.')
    tela.ver_status('Em análise')
    tela.ver_botao('Devolver')
    erro_aberto.refresh_from_db()
    assert erro_aberto.situacao == Erro.SITUACAO_EM_ANALISE, 'assumir deveria mover a situação para Em análise'
    assert erro_aberto.atendente_atual.user.username == '103011', 'a UI disse que assumiu, mas o atendente atual não mudou'

    tela.clicar_botao('Alterar situação')
    tela.clicar_botao('Em correção')

    tela.sucesso('Situação alterada com sucesso.')
    tela.ver_status('Em correção')
    erro_aberto.refresh_from_db()
    assert erro_aberto.situacao == Erro.SITUACAO_EM_CORRECAO, 'a UI disse que alterou, mas a situação não persistiu'


def test_atendente_edita_url_do_erro(logado_erros, erro_em_analise):
    """Troca a URL do erro pelo popup de Opções.

    A troca não é só cosmética: `alterar_url` (`erros/models.py:395`) recalcula a `view` a
    partir da URL nova, e é a `view` que define o módulo afetado e a triagem de duplicidade.
    """
    tela = Tela(logado_erros('atendente')).ir(erro_em_analise.get_absolute_url())
    tela.clicar_botao('Opções')
    tela.clicar_botao('Editar URL do Erro')

    popup = tela.popup()
    popup.ver_texto(f'Alterar URL do Erro {erro_em_analise.pk}')
    popup.preencher('Nova URL do Erro', 'texto', NOVA_URL)
    popup.salvar_no_popup('Enviar')

    tela.sucesso('URL do erro alterada com sucesso.')
    erro_em_analise.refresh_from_db()
    assert erro_em_analise.url == NOVA_URL, 'a UI disse que alterou, mas a URL não persistiu'
    assert erro_em_analise.view == 'comum.views.acessibilidade', f'a view deveria acompanhar a URL nova, veio {erro_em_analise.view!r}'
