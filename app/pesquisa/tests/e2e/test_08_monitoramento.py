"""Fluxo: monitoramento do projeto (modo 2).

A execução registrada na 007 é validada pelo **supervisor** do projeto — o Coordenador de
Pesquisa que fez a pré-seleção (003). É o único ponto da cadeia em que alguém que não é o
coordenador do projeto aprova o que ele registrou, e é o que dá ao acompanhamento um segundo
par de olhos.

O que este arquivo pega: a fila de monitoramento (``projetos_em_execucao`` filtra
``aprovado=True`` **e** ``edital.divulgacao_selecao < hoje`` — um edital com a data de
divulgação errada esvazia a fila em silêncio, como já aconteceu com a de pré-avaliação da 003),
e as duas abas de ``Validar Execução`` — "Metas" e "Gastos" —, que são o mesmo gesto sobre
objetos diferentes e por isso ficam no mesmo arquivo, mas como testes separados.
"""

import pytest

from djtools.e2e_ui import Tela

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

# A data que a feature 008 fixa: a mesma janela de execução da 007.
DATA = '20/01/2018'

MONITORAMENTO = '/pesquisa/projetos_em_execucao/'

TITULO_PROJETO = 'Título do projeto'

DESCRICAO_ATIVIDADE = 'Descrição da Atividade 1'
OBSERVACAO_GASTO = 'Obs sobre o registro do gasto'


def _validar_execucao(tela: Tela) -> Tela:
    """Monitoramento → linha do projeto → "Acompanhar Validação" → a tela de validação."""
    tela.ir(MONITORAMENTO)
    tela.ver_titulo('Monitoramento')
    tela.linha(TITULO_PROJETO)
    tela.ver_botao('Acompanhar Validação')
    tela.linha(TITULO_PROJETO).clicar_botao('Acompanhar Validação')
    return tela.ver_titulo('Validar Execução')


def test_validacao_das_atividades(logado_pesquisa):
    """O supervisor aprova a execução da atividade registrada na 007.

    A aprovação não grava só um "ok": ela é o que permite o projeto concluir (a conclusão
    exige execução validada), então a asserção é sobre o estado que a feature 009 vai cobrar de
    volta — não sobre a mensagem.
    """
    from pesquisa.models import RegistroExecucaoEtapa

    tela = Tela(logado_pesquisa('coordenador_pesquisa'))
    _validar_execucao(tela)

    tela.clicar_aba('Metas')
    tela.linha(DESCRICAO_ATIVIDADE)
    tela.ver_botao('Aprovar')
    tela.linha(DESCRICAO_ATIVIDADE).clicar_botao('Aprovar')

    tela.sucesso('Execução de atividade validada com sucesso.')
    execucao = RegistroExecucaoEtapa.objects.filter(etapa__descricao=DESCRICAO_ATIVIDADE, etapa__meta__projeto__titulo=TITULO_PROJETO).first()
    assert execucao is not None, 'a UI disse que validou, mas não há execução para a atividade'
    # `aprovado` é o que a conclusão (feature 009) lê de volta: a conclusão exige execução
    # validada, então afirmar a mensagem sem isto deixaria a 009 falhar longe da causa.
    assert execucao.aprovado, 'a UI disse que validou, mas a execução não ficou marcada como aprovada'
    assert execucao.avaliador_id, 'a UI disse que validou, mas o registro não ficou com o supervisor responsável'


def test_validacao_dos_gastos(logado_pesquisa):
    """O supervisor aprova o gasto registrado na 007 — a última obrigação do monitoramento.

    O recorte é a linha pelo texto de ``Observação``, que é o que a tela mostra ao supervisor:
    o gasto não tem título próprio, e é a observação que o identifica.
    """
    from pesquisa.models import RegistroGasto

    tela = Tela(logado_pesquisa('coordenador_pesquisa'))
    _validar_execucao(tela)

    tela.clicar_aba('Gastos')
    tela.linha(OBSERVACAO_GASTO)
    tela.ver_botao('Aprovar')
    tela.linha(OBSERVACAO_GASTO).clicar_botao('Aprovar')

    tela.sucesso('Gasto validado com sucesso.')
    gasto = RegistroGasto.objects.filter(descricao=OBSERVACAO_GASTO).order_by('-id').first()
    assert gasto is not None, 'a UI disse que validou, mas o gasto sumiu'
    assert gasto.aprovado, 'a UI disse que validou, mas o gasto não ficou marcado como aprovado'
    assert gasto.dt_avaliacao is not None, 'a UI disse que validou, mas o gasto ficou sem data de avaliação'
