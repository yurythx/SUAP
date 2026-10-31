"""Fluxo: indicação de avaliadores do projeto (modo 2).

Pré-selecionado o projeto (003), o Diretor de Pesquisa indica quem o avalia. A escolha sai da
comissão do edital — cadastrada na feature 001 — e é ela que a feature 005 lê para montar a
lista de quem pode avaliar.

O que este arquivo pega, e que não é óbvio na feature: a listagem de projetos é
``div.general-box`` (cartão, não tabela) e **só renderiza depois do filtro ser submetido**
(``pesquisa/templates/selecionar_avaliadores.html`` envolve a lista em ``{% if form.is_bound %}``).
É por isso que o cenário clica "Enviar" antes de "Selecionar avaliadores" — sem esse clique a
tela fica sem cartão nenhum, e o sintoma é "botão não encontrado", que parece seletor quebrado.
"""

import pytest

from djtools.e2e_ui import Tela

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

# A data que a feature 004 fixa: dentro da seleção do edital (15→17/01/2018).
DATA = '16/01/2018'

INDICAR = '/pesquisa/pre_avaliacao/selecionar_avaliadores/'

TITULO_EDITAL = 'Nome do edital'
TITULO_PROJETO = 'Título do projeto'


def test_indicacao_de_avaliadores_do_projeto(logado_pesquisa):
    """O Diretor indica os dois avaliadores da comissão para o projeto pré-selecionado.

    A asserção de domínio conta **dois** ``AvaliadorIndicado``: a feature marca os dois
    checkboxes no mesmo formulário, e gravar só um deixaria a feature 005 sem a segunda
    avaliação — o projeto seguiria para a distribuição de bolsas com metade dos pareceres, sem
    nenhum erro visível.
    """
    from pesquisa.models import AvaliadorIndicado

    tela = Tela(logado_pesquisa('diretor')).ir(INDICAR)
    tela.ver_titulo('Editais em Avaliação')

    tela.linha(TITULO_EDITAL).clicar_icone('exibição')
    tela.ver_titulo(f'Selecionar avaliadores dos Projetos do {TITULO_EDITAL}')

    # O filtro tem de ser submetido para a lista de projetos existir no DOM.
    tela.clicar_botao('Enviar')
    tela.cartao(TITULO_PROJETO).clicar_botao('Selecionar avaliadores')

    tela.ver_titulo(f'Indicar Avaliadores do Projeto {TITULO_PROJETO}')
    # Segundo filtro, agora o de avaliadores — mesma regra, outra tela.
    tela.clicar_botao('Enviar')
    tela.selecionar_item('Avaliador1 Pesquisa')
    tela.selecionar_item('Avaliador2 Pesquisa')
    tela.clicar_botao('Salvar')

    tela.sucesso('Avaliadores cadastrados com sucesso.')
    indicados = AvaliadorIndicado.objects.filter(projeto__titulo=TITULO_PROJETO)
    nomes = sorted(indicados.values_list('vinculo__pessoa__nome', flat=True))
    assert nomes == ['Avaliador1 Pesquisa', 'Avaliador2 Pesquisa'], f'a UI disse que salvou, mas os indicados foram {nomes}'
