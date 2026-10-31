"""Fluxo: entrar e sair do acompanhamento de um erro alheio (modo 2).

As três ações que a tela do erro executa por parâmetro de GET e que nenhuma ``.feature``
exercita — ``?interessar``, ``?desinteressar`` e ``?devolver`` (``erros/views.py:357-372``).
São o que faz o módulo funcionar como fila de acompanhamento:

* **tornar-se interessado** é como alguém passa a receber notificação de um erro que outra
  pessoa reportou; é o botão que a tela de "erros similares" oferece para evitar duplicata;
* **remover interesse** só é permitido a quem **não** é o informante (``erros/models.py:189``):
  quem reportou não pode se descolar do próprio erro;
* **devolver** é o atendente admitindo que aquilo não é com ele — zera o atendente atual e
  devolve o erro à fila (``erros/models.py:248-252``). Sem isso, um erro assumido por engano
  fica preso a uma pessoa.

Nenhuma das três apaga registro: interesse desligado vira ``ativo=False``
(``erros/models.py:435-439``), e é essa flag — não a ausência de linha — que as asserções
verificam.
"""

import pytest

from djtools.e2e_ui import Tela

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

URL_ERRO = '/erros/erro/{}/'


def test_analista_se_interessa_e_depois_remove_o_interesse(logado_erros, vinculos_erros, erro_aberto):
    """Entrar e sair, num teste só: sair exige o interesse que o passo anterior criou."""
    from erros.models import InteressadoErro

    auxiliar = vinculos_erros['atendente_auxiliar']
    tela = Tela(logado_erros('atendente_auxiliar')).ir(URL_ERRO.format(erro_aberto.pk))
    tela.clicar_botao('Tornar-se interessado')

    tela.sucesso('Você agora é um Interessado deste erro.')
    interesse = InteressadoErro.objects.filter(erro=erro_aberto, vinculo=auxiliar).first()
    assert interesse is not None, 'a UI disse que registrou, mas o interesse não persistiu'
    assert interesse.ativo

    tela.clicar_botao('Remover interesse')

    tela.sucesso('Interesse removido com sucesso.')
    interesse.refresh_from_db()
    assert not interesse.ativo, 'a UI disse que removeu, mas o interesse continua ativo'


def test_informante_nao_pode_se_desinteressar_do_proprio_erro(logado_erros, erro_aberto):
    """Quem reportou continua interessado mesmo pedindo a saída pela URL.

    A ausência do botão (``erros/templates/erro.html:95-97``) é só a metade visível da regra —
    e sozinha ela testaria o template, não a regra: apagar ``and pode_se_desinteressar`` da
    view (``erros/views.py:370``) deixaria o teste verde. Por isso o pedido é feito **na URL**,
    como faria quem monta o endereço à mão, e o fato afirmado é o interesse continuar ativo.
    """
    tela = Tela(logado_erros('interessado')).ir(URL_ERRO.format(erro_aberto.pk))
    assert 'Remover interesse' not in tela.botoes_na_tela(), 'o informante não pode se descolar do próprio erro'

    tela.ir(f'{URL_ERRO.format(erro_aberto.pk)}?desinteressar=1')

    assert erro_aberto.interessadoerro_set.filter(vinculo=erro_aberto.informante, ativo=True).exists(), (
        'a view aceitou desinteressar o informante do próprio erro'
    )


def test_atendente_devolve_o_erro_para_a_fila(logado_erros, erro_em_analise):
    """Devolver zera o atendente atual e deixa o rastro na linha do tempo."""
    from erros.models import HistoricoComentarioErro

    tela = Tela(logado_erros('atendente')).ir(URL_ERRO.format(erro_em_analise.pk))
    tela.clicar_botao('Devolver')

    tela.sucesso('Erro devolvido com sucesso.')
    erro_em_analise.refresh_from_db()
    assert erro_em_analise.atendente_atual is None, 'a UI disse que devolveu, mas o erro continua com atendente'
    assert HistoricoComentarioErro.objects.filter(erro=erro_em_analise, descricao='devolveu o atendimento.').exists(), (
        'a devolução deveria ficar registrada na linha do tempo'
    )
