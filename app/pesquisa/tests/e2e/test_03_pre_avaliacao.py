"""Fluxo: pré-avaliação do projeto (modo 2).

A pré-avaliação é a primeira triagem: o Coordenador de Pesquisa confere se o projeto
submetido está de acordo com o edital antes de gastar avaliador com ele. É o portão que
separa "submetido" de "pré-selecionado", e é o único ponto da cadeia em que quem age é o
Coordenador de Pesquisa (108002) — o mesmo servidor que depois supervisiona a execução
(feature 008) e valida a conclusão (feature 011).

O que este arquivo pega: o projeto enviado pela 002 tem de aparecer na fila de pré-seleção do
edital correto (é o ``período`` do edital que decide isso, e um edital com o período de
pré-seleção errado esvazia a fila em silêncio), e a justificativa tem de ser obrigatória —
sem ela ``pre_selecionar`` recusa, e a cadeia para aqui.
"""

import pytest

from djtools.e2e_ui import Tela

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

# A data que a feature 003 fixa. O edital da 001 tem ``inicio_pre_selecao`` em 11/01/2018, então
# esta é a primeira data em que a fila de pré-seleção não está vazia.
DATA = '12/01/2018'

PRE_AVALIACAO = '/pesquisa/pre_avaliacao/pesquisa/'

TITULO_EDITAL = 'Nome do edital'
TITULO_PROJETO = 'Título do projeto'


def test_pre_avaliacao_do_projeto(logado_pesquisa):
    """O Coordenador de Pesquisa pré-seleciona o projeto com justificativa.

    O caminho é ``editais → linha do edital → ícone de exibição → linha do projeto →
    Pré-selecionar → justificativa``. A asserção de domínio é ``pre_aprovado``: a mensagem de
    sucesso sozinha não distingue "pré-avaliado" de "justificativa gravada e projeto ainda na
    fila", que é o que aconteceria se a view falhasse depois de salvar o parecer.
    """
    from pesquisa.models import Projeto

    tela = Tela(logado_pesquisa('coordenador_pesquisa')).ir(PRE_AVALIACAO)
    tela.ver_titulo('Editais')

    tela.linha(TITULO_EDITAL).clicar_icone('exibição')
    tela.ver_titulo(f'Pré-Seleção de Projetos - {TITULO_EDITAL}')

    tela.linha(TITULO_PROJETO)
    tela.ver_botao('Pré-selecionar')
    tela.linha(TITULO_PROJETO).clicar_botao('Pré-selecionar')

    tela.ver_titulo(f'Justificativa da Pré-Avaliação - {TITULO_PROJETO}')
    tela.preencher('Justificativa da Pré-Avaliação', 'TextArea', 'Parecer do coordenador de pesquisa')
    tela.clicar_botao('Salvar')

    tela.sucesso('Projeto pré-avaliado com sucesso.')
    projeto = Projeto.objects.get(titulo=TITULO_PROJETO)
    projeto.refresh_from_db()
    assert projeto.pre_aprovado, 'a UI disse que pré-avaliou, mas o projeto continua não pré-selecionado'
    assert projeto.data_pre_avaliacao is not None, 'a UI disse que pré-avaliou, mas a data da pré-seleção ficou vazia'
