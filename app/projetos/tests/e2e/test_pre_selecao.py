"""Fluxo: pré-seleção do projeto enviado (feature 003) — pré-selecionar, não selecionar, ficha e cancelamento.

A pré-seleção é o portão entre "enviado" e "pré-selecionado": só o pré-selecionado recebe
avaliador (feature 004) e entra na classificação. Quem pré-avalia é o Coordenador de Extensão do
campus do projeto (ou o pré-avaliador indicado para ele); o Gerente Sistêmico só cancela uma
pré-avaliação feita. Sem critérios no edital, "Pré-selecionar"/"Não Selecionar" gravam direto;
com critérios, "Pré-avaliar" abre a ficha, que depois é consultada em "Ficha da pré-seleção".

A regressão cara é a pré-seleção gravar o estado errado (ou em projeto de outro campus): o
projeto some da avaliação sem erro visível. Todas estas ações gravam por GET e redirecionam
para o ``Referer`` — sem ele, para si mesmas (``httprr('.')``), o que re-alternaria a
pré-seleção a cada salto. Por isso o caminho é o clique (o browser manda o ``Referer``) ou o
``buscar`` (que não segue redirect), sempre em projeto descartável.
"""

from __future__ import annotations

import datetime
from typing import TYPE_CHECKING

import pytest
from playwright.sync_api import Locator, expect

from djtools.e2e_ui import Tela
from projetos.tests.e2e.conftest import clicar_em, outra_uo, vinculo

if TYPE_CHECKING:
    from comum.models import Vinculo
    from projetos.models import Edital, Projeto

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

PRE_AVALIACAO = '/projetos/pre_avaliacao/'
# Mesma view (`urls.py` aponta as duas para `pre_avaliacao`); só a URL muda.
PRE_AVALIACAO_ALIAS = '/projetos/pre_avaliacao/selecionar_avaliadores/'
PRE_SELECIONAR = '/projetos/pre_selecionar/{}/'
PRE_REJEITAR = '/projetos/pre_rejeitar/{}/'
PRE_APROVAR = '/projetos/pre_aprovar/{}/'
FICHA = '/projetos/ficha_pre_selecao/{}/'
CANCELAR = '/projetos/cancelar_pre_avaliacao_projeto/{}/'

PRE_AVALIADO = 'Projeto pré-avaliado com sucesso.'


def celula(tela: Tela, texto: str) -> Locator:
    """A célula com exatamente ``texto`` — a mesma sonda serve à presença e à ausência."""
    return tela.loc(f'//td[normalize-space(.)="{texto}"]')


def fila_da_pre_selecao(tela: Tela, edital: Edital) -> Tela:
    """Menu "Pré-avaliar": da lista de editais em pré-seleção à fila de projetos do edital."""
    tela.ir(PRE_AVALIACAO).linha(edital.titulo).clicar_icone('exibição')
    return tela.esperar().ver_titulo(f'Pré-Seleção de Projetos - {edital.titulo}')


def situacao(projeto: Projeto) -> tuple[bool, datetime.date | None, Vinculo | None, Vinculo | None]:
    """O que a pré-seleção grava no projeto: (pré-aprovado, data, autor, monitor)."""
    projeto.refresh_from_db()
    return projeto.pre_aprovado, projeto.data_pre_avaliacao, projeto.vinculo_autor_pre_avaliacao, projeto.vinculo_monitor


@pytest.mark.parametrize('rota', [PRE_AVALIACAO, PRE_AVALIACAO_ALIAS])
def test_coordenador_de_extensao_ve_os_editais_em_pre_selecao(logado_projetos, projetos_seed, rota):
    """Só o edital na janela da pré-seleção; o que ainda está em inscrição fica de fora."""
    tela = Tela(logado_projetos('coordenador_extensao')).ir(rota)

    tela.ver_titulo('Editais em pré-seleção')
    expect(celula(tela, projetos_seed.editais['pre_selecao'].titulo)).to_have_count(1)
    assert not celula(tela, projetos_seed.editais['inscricao'].titulo).count(), 'edital ainda em inscrição listado na pré-seleção'


@pytest.mark.parametrize(('rota', 'pre_aprovado'), [(PRE_SELECIONAR, True), (PRE_REJEITAR, False)])
def test_coordenador_de_extensao_pre_avalia_projeto_do_campus(logado_projetos, projeto_enviado_em, rota, pre_aprovado):
    """ "Pré-selecionar" e "Não Selecionar" (edital sem critérios): gravam a decisão, a data e o autor, que vira o monitor."""
    projeto = projeto_enviado_em('pre_selecao')
    tela = fila_da_pre_selecao(Tela(logado_projetos('coordenador_extensao')), projeto.edital)

    clicar_em(tela, rota.format(projeto.pk))
    tela.ver_titulo(f'Pré-Seleção de Projetos - {projeto.edital.titulo}').sucesso(PRE_AVALIADO)

    coordenador = vinculo('coordenador_extensao')
    assert situacao(projeto) == (pre_aprovado, datetime.date.today(), coordenador, coordenador), 'a UI disse que pré-avaliou, mas o projeto não mudou'


def test_pre_aprovar_pela_url(logado_projetos, projeto_enviado_em):
    """``/pre_aprovar/`` não tem link na UI: é ``pre_selecionar(rejeitar=False)``.

    Sem ``Referer`` a view redireciona para si mesma; ``buscar`` não segue o redirect, e a
    mensagem fica para a PRIMEIRA tela renderizada depois — que a consome.
    """
    projeto = projeto_enviado_em('pre_selecao')
    tela = Tela(logado_projetos('coordenador_extensao'))

    assert tela.buscar(PRE_APROVAR.format(projeto.pk)).status == 302
    assert situacao(projeto)[:2] == (True, datetime.date.today()), 'a rota respondeu, mas o projeto não foi pré-selecionado'
    tela.ir(PRE_AVALIACAO).sucesso(PRE_AVALIADO)


def test_pre_avaliacao_pela_ficha_de_criterios(logado_projetos, projeto_enviado_em):
    """Com critérios no edital, "Pré-avaliar" abre a ficha; a ficha gravada é o que "Ficha da pré-seleção" mostra."""
    from projetos.models import ItemPreSelecao, PreSelecao
    from projetos.tests.factories import CriterioPreSelecaoFactory

    projeto = projeto_enviado_em('pre_selecao')
    criterio = CriterioPreSelecaoFactory(edital=projeto.edital, descricao='Proposta aderente ao edital')
    tela = fila_da_pre_selecao(Tela(logado_projetos('coordenador_extensao')), projeto.edital)

    clicar_em(tela, PRE_SELECIONAR.format(projeto.pk))
    tela.ver_titulo(f'Pré-avaliar - {projeto.titulo}').preencher_formulario(
        [
            ('Proposta aderente ao edital', 'lista', 'Sim'),
            ('Parecer', 'textarea', 'Proposta atende ao edital'),
            ('Pré-selecionar este projeto?', 'lista', 'Sim'),
        ]
    )
    tela.clicar_botao('Enviar')
    tela.esperar().ver_titulo(f'Pré-Seleção de Projetos - {projeto.edital.titulo}').sucesso(PRE_AVALIADO)

    assert situacao(projeto)[0], 'a UI disse que pré-avaliou, mas o projeto não foi pré-selecionado'
    ficha = PreSelecao.objects.get(projeto=projeto, avaliador=vinculo('coordenador_extensao'))
    assert ficha.parecer == 'Proposta atende ao edital', 'o parecer da ficha não persistiu'
    assert ItemPreSelecao.objects.filter(avaliacao=ficha, criterio=criterio, aprovado=True).exists(), 'o critério da ficha não persistiu'

    expect(tela.loc(f'//a[@href="{FICHA.format(projeto.pk)}"]')).to_be_visible()  # popup sem <form>: abre pela URL
    tela.ir(FICHA.format(projeto.pk)).ver_titulo(f'Ficha da pré-seleção - {projeto.titulo}')
    tela.linha('Proposta aderente ao edital').ver_texto('Sim')
    tela.linha('Parecer').ver_texto('Proposta atende ao edital')


def test_gerente_cancela_a_pre_avaliacao(logado_projetos, projeto_enviado_em):
    """O cancelamento devolve o projeto à fila: zera a decisão e apaga a ficha."""
    from projetos.models import PreSelecao
    from projetos.tests.factories import PreSelecaoFactory

    coordenador = vinculo('coordenador_extensao')
    projeto = projeto_enviado_em('pre_selecao', pre_aprovado=True, data_pre_avaliacao=datetime.date.today(), vinculo_autor_pre_avaliacao=coordenador)
    PreSelecaoFactory(projeto=projeto, avaliador=coordenador)
    tela = fila_da_pre_selecao(Tela(logado_projetos('gerente')), projeto.edital)

    clicar_em(tela, CANCELAR.format(projeto.pk))
    tela.ver_titulo(f'Pré-Seleção de Projetos - {projeto.edital.titulo}').sucesso('Pré-avaliação cancelada com sucesso.')

    assert situacao(projeto)[:2] == (False, None), 'a UI disse que cancelou, mas a pré-avaliação continua gravada'
    assert not PreSelecao.objects.filter(projeto=projeto).exists(), 'a pré-avaliação foi cancelada, mas a ficha ficou'


def test_coordenador_de_extensao_nao_pre_avalia_projeto_de_outro_campus(logado_projetos, projeto_enviado_em):
    """Cada ação, com o id de projeto de outro campus, responde 403 e não grava — o controle positivo é o do próprio campus."""
    alheio = projeto_enviado_em('pre_selecao', uo=outra_uo(), sufixo='alheio')
    proprio = projeto_enviado_em('pre_selecao', edital=alheio.edital, sufixo='proprio')
    tela = Tela(logado_projetos('coordenador_extensao'))
    rotas = (PRE_SELECIONAR, PRE_REJEITAR, PRE_APROVAR, FICHA)

    respostas = {rota: tela.buscar(rota.format(alheio.pk)).status for rota in rotas}

    assert respostas == dict.fromkeys(rotas, 403), f'rotas que não barraram o outro campus: { {r: s for r, s in respostas.items() if s != 403} }'
    assert situacao(alheio)[:2] == (False, None), 'o projeto de outro campus foi pré-avaliado por quem recebeu 403'
    assert tela.buscar(PRE_SELECIONAR.format(proprio.pk)).status == 302, 'a sonda não pré-avalia nem o projeto do próprio campus'
    assert situacao(proprio)[0], 'o controle positivo respondeu, mas não gravou'


@pytest.mark.parametrize('papel', ['coordenador_projeto', 'avaliador', 'aluno'])
def test_quem_nao_pre_avalia_nao_abre_a_pre_selecao(logado_projetos, projeto_enviado_em, papel):
    """``pode_pre_avaliar_projeto`` só no Coordenador de Extensão, no Gerente e no Pré-Avaliador."""
    projeto = projeto_enviado_em('pre_selecao')
    tela = Tela(logado_projetos(papel))
    rotas = (PRE_AVALIACAO, PRE_AVALIACAO_ALIAS, *(rota.format(projeto.pk) for rota in (PRE_SELECIONAR, PRE_REJEITAR, PRE_APROVAR, FICHA)))

    assert {rota: tela.buscar(rota).status for rota in rotas} == dict.fromkeys(rotas, 403)
    assert situacao(projeto)[:2] == (False, None), 'o projeto foi pré-avaliado por quem recebeu 403'


def test_reavaliar_pela_ficha_nao_rejeita_o_pre_selecionado(logado_projetos, projeto_enviado_em):
    """Projeto já pré-selecionado, reavaliado pela ficha com "Sim", continua pré-selecionado (#17579)."""
    from projetos.tests.factories import CriterioPreSelecaoFactory

    coordenador = vinculo('coordenador_extensao')
    projeto = projeto_enviado_em('pre_selecao', pre_aprovado=True, data_pre_avaliacao=datetime.date.today(), vinculo_autor_pre_avaliacao=coordenador)
    CriterioPreSelecaoFactory(edital=projeto.edital, descricao='Proposta aderente ao edital')
    tela = fila_da_pre_selecao(Tela(logado_projetos('coordenador_extensao')), projeto.edital)

    clicar_em(tela, PRE_SELECIONAR.format(projeto.pk))
    tela.ver_titulo(f'Pré-avaliar - {projeto.titulo}').preencher_formulario(
        [
            ('Proposta aderente ao edital', 'lista', 'Sim'),
            ('Parecer', 'textarea', 'Mantida a pré-seleção'),
            ('Pré-selecionar este projeto?', 'lista', 'Sim'),
        ]
    )
    tela.clicar_botao('Enviar')
    tela.esperar().ver_titulo(f'Pré-Seleção de Projetos - {projeto.edital.titulo}').sucesso(PRE_AVALIADO)

    assert situacao(projeto)[0], 'o avaliador escolheu "Sim", mas o projeto foi rejeitado'


def test_rota_so_aceita_a_acao_que_a_tela_oferece(logado_projetos, projeto_enviado_em, edital_novo):
    """``pre_aprovar``/``pre_selecionar`` não invertem o pré-selecionado; ``pre_rejeitar`` não desfaz o fluxo contínuo (#17579)."""
    from projetos.models import Edital, Projeto
    from projetos.tests.e2e.conftest import janela

    hoje = datetime.date.today()
    pre_selecionado = projeto_enviado_em('pre_selecao', pre_aprovado=True, data_pre_avaliacao=hoje)
    continuo = edital_novo(**janela('pre_selecao'), campus_especifico=True, tipo_edital=Edital.EXTENSAO_FLUXO_CONTINUO)
    aprovado = {
        'pre_aprovado': True,
        'aprovado': True,
        'data_pre_avaliacao': hoje,
        'data_avaliacao': hoje,
        'vinculo_autor_avaliacao': vinculo('gerente'),
    }
    do_continuo = projeto_enviado_em('pre_selecao', edital=continuo, **aprovado)
    tela = Tela(logado_projetos('coordenador_extensao'))

    respostas = {rota: tela.buscar(rota.format(pre_selecionado.pk)).status for rota in (PRE_APROVAR, PRE_SELECIONAR)}
    respostas[PRE_REJEITAR] = tela.buscar(PRE_REJEITAR.format(do_continuo.pk)).status

    assert respostas == dict.fromkeys(respostas, 403), f'rotas que aceitaram a ação que a tela não oferece: {respostas}'
    assert situacao(pre_selecionado)[:2] == (True, hoje), 'o projeto pré-selecionado foi rejeitado'
    gravado = Projeto.objects.filter(pk=do_continuo.pk).values(*aprovado).get()
    assert gravado == aprovado | {'vinculo_autor_avaliacao': vinculo('gerente').pk}, 'a pré-seleção do fluxo contínuo foi desfeita'


def test_cota_de_pre_aprovados_atingida(logado_projetos, projeto_enviado_em):
    """Com a cota do campus atingida, a tela não oferece "Pré-selecionar" e a rota recusa (#17579)."""
    from projetos.models import OfertaProjeto

    ocupante = projeto_enviado_em('pre_selecao', pre_aprovado=True, data_pre_avaliacao=datetime.date.today(), sufixo='ocupante')
    projeto = projeto_enviado_em('pre_selecao', edital=ocupante.edital, sufixo='na fila')
    OfertaProjeto.objects.filter(edital=projeto.edital).update(qtd_aprovados=1)
    tela = fila_da_pre_selecao(Tela(logado_projetos('coordenador_extensao')), projeto.edital)

    tela.linha(projeto.titulo).ver_texto('Cota de pré-aprovados atingida')
    assert not tela.loc(f'//a[@href="{PRE_SELECIONAR.format(projeto.pk)}"]').count(), 'a tela oferece "Pré-selecionar" com a cota atingida'
    assert tela.buscar(PRE_SELECIONAR.format(projeto.pk)).status == 403
    assert situacao(projeto)[:2] == (False, None), 'o projeto foi pré-selecionado acima da cota'


def test_ficha_de_projeto_sem_ficha_nao_quebra(logado_projetos, projeto_enviado_em):
    projeto = projeto_enviado_em('pre_selecao', pre_aprovado=True, data_pre_avaliacao=datetime.date.today())
    resposta = Tela(logado_projetos('coordenador_extensao')).buscar(FICHA.format(projeto.pk))
    assert resposta.status == 200, f'a ficha de projeto sem ficha devolveu {resposta.status}'
