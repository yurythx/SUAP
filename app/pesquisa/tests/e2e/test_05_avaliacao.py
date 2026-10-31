"""Fluxo: avaliação do projeto (modo 2).

Com os avaliadores indicados (004), cada um dá o seu parecer. São duas avaliações
independentes do mesmo projeto — é delas que sai a pontuação que a feature 006 usa para
distribuir as bolsas.

**Por que as duas avaliações são UM teste, e não dois.** A receita (seção 1, regra 1) já
manda cadeia de cenários virar um teste; aqui há um motivo mais duro, medido nesta suíte. O
segundo avaliador só consegue avaliar enquanto ``Projeto.aprovado`` for falso
(``Projeto.pode_avaliar_projeto``, ``models.py:2792-2798``) — e o ``GET`` de
``gerenciar_bolsas`` (feature 006) chama ``edital.classifica_projetos_pesquisa``
(``views.py:3403``), que **aprova** o projeto quando ele passa do corte e distribui bolsa.
Qualquer coisa que rode entre as duas avaliações destrói a precondição da segunda.

E alguma coisa roda: nesta suíte a coleta do pytest **não** mantém os casos parametrizados
contíguos. Medido com ``--collect-only -q``::

    18  test_05_avaliacao.py::test_avaliacao_do_projeto[chromium-avaliador_1-...]
    19  test_06_distribuir_bolsas.py::test_distribuicao_das_bolsas
    20  test_05_avaliacao.py::test_avaliacao_do_projeto[chromium-avaliador_2-...]

Confirmado com um ``post_save`` em ``Projeto``: o único ponto que grava ``aprovado=True`` é
``gerenciar_bolsas`` → ``classifica_projetos_pesquisa`` → ``models.py:583``. Separados, o
teste do avaliador 2 falha com "botão 'Avaliar Projeto' não visível" — e o diagnóstico da
tela nem parece do avaliador, porque a barra de ações que sobra é a de outro papel. Unificados,
nada pode rodar no meio, e o teste deixa de depender da ordem de coleta.
"""

import re

import pytest
from playwright.sync_api import expect

from djtools.e2e_ui import Tela

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

# A data que a feature 005 fixa: a mesma janela de seleção da 004 (15→17/01/2018).
DATA = '16/01/2018'

AVALIACAO = '/pesquisa/avaliacao/'

TITULO_EDITAL = 'Nome do edital'
TITULO_PROJETO = 'Título do projeto'

# Os dois cenários da feature — "Primeira Avaliação" e "Segunda Avaliação" — são irmãos:
# mesmo caminho, mesmo formulário, mudando só o avaliador logado e o texto do parecer.
AVALIADORES = [
    ('avaliador_1', 'Parecer do avaliador 1'),
    ('avaliador_2', 'Parecer do avaliador 2'),
]


def test_avaliacao_do_projeto(logado_pesquisa, projeto_do_fluxo):
    """Os dois avaliadores indicados avaliam o projeto, um depois do outro.

    O caminho de cada um é ``Editais em Avaliação → link do edital → Seleção de Projetos →
    linha do projeto → Avaliar → Avaliar Projeto → parecer``. O segundo clique não é decoração:
    entre "Avaliar" e o formulário há o aceite do termo de compromisso, e pular esse passo
    grava a avaliação sem o aceite.

    A asserção de domínio é por avaliador e é dupla: o parecer **por critério** e a pontuação
    do projeto. O parecer não mora em ``Avaliacao.parecer`` — o ``save()`` do formulário nunca
    escreve aquele campo (``forms.py:1409-1429``); ele grava o texto em
    ``ItemAvaliacao.parecer`` e deixa ``Avaliacao.parecer`` no default. Afirmar o campo do
    modelo passaria sempre falso e mandaria procurar defeito na tela.

    A pontuação é o que a feature 006 consome: o formulário exige um ``ChoiceField`` de nota
    por critério e a feature não preenche nenhuma, então quem manda é a primeira opção que o
    navegador seleciona (a maior). Zero aqui significaria projeto chegando à distribuição de
    bolsas sem nota.
    """
    from pesquisa.models import ItemAvaliacao

    projeto = projeto_do_fluxo()

    for papel, parecer in AVALIADORES:
        tela = Tela(logado_pesquisa(papel)).ir(AVALIACAO)
        tela.ver_titulo('Editais em Avaliação')

        tela.linha(TITULO_EDITAL).clicar_link(TITULO_EDITAL)
        tela.ver_titulo('Seleção de Projetos')

        tela.linha(TITULO_PROJETO)
        tela.ver_botao('Avaliar')
        tela.linha(TITULO_PROJETO).clicar_botao('Avaliar')
        # O clique acima NAVEGA. Ancorar no URL de destino, e não num heading, é o que fecha a
        # corrida medida aqui: ``Tela.clicar_botao`` só chama ``esperar()`` antes do clique, e
        # ``wait_for_load_state`` retorna na hora enquanto o documento antigo ainda está em
        # 'load' — a consulta seguinte cai num documento em construção (medido:
        # ``readyState: 'loading'``, zero elementos). ``ver_titulo`` também não serve de
        # âncora: ``get_by_role`` casa por substring e o heading da tela de origem contém o
        # texto procurado, então ele passa sem que a navegação tenha acontecido. O URL do
        # projeto é a única âncora sem ambiguidade. É a corrida da armadilha 15 da receita.
        expect(tela.pagina).to_have_url(re.compile(rf'/pesquisa/projeto/{projeto.pk}/'))

        tela.ver_botao('Avaliar Projeto')
        tela.clicar_botao('Avaliar Projeto')

        tela.ver_titulo(f'Avaliar Projeto - {TITULO_PROJETO}')
        tela.preencher('Parecer', 'TextArea', parecer)
        tela.clicar_botao('Enviar')

        tela.sucesso('Projeto avaliado com sucesso.')
        item = ItemAvaliacao.objects.filter(avaliacao__projeto=projeto, parecer=parecer).first()
        assert item is not None, f'a UI disse que {papel} avaliou, mas não há parecer de critério com o texto {parecer!r}'
        assert item.avaliacao.projeto.pontuacao > 0, f'a UI disse que {papel} avaliou, mas a pontuação do projeto ficou zerada'

    # As duas avaliações têm de conviver: `Avaliacao` é única por (projeto, vínculo), e a
    # segunda gravação não pode ter sobrescrito a primeira.
    assert ItemAvaliacao.objects.filter(avaliacao__projeto=projeto).values('parecer').distinct().count() == 2, (
        'as duas avaliações não coexistem — a segunda sobrescreveu a primeira'
    )
