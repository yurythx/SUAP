"""Fluxo: o lado do avaliador indicado — ver os projetos indicados, aceitar ou rejeitar a indicação, consultar o que avaliou.

A indicação (feature 004) só vale quando o avaliador a aceita dentro do prazo; rejeitada, o
gestor precisa indicar outro. A tela ``projetos_pre_aprovados`` (link do e-mail de convite) é a
porta: lista só os projetos do campus em que ELE foi indicado, com "Aceitar"/"Rejeitar" por
projeto. A regressão cara é a resposta de um avaliador gravar na indicação de outro — as duas
ações recebem só o projeto na URL e gravam por GET —, ou a lista vazar projeto não indicado.
"""

from __future__ import annotations

import datetime
from typing import TYPE_CHECKING

import pytest
from playwright.sync_api import Locator, expect

from djtools.e2e_ui import Tela
from projetos.tests.e2e.conftest import clicar_em, vinculo

if TYPE_CHECKING:
    from projetos.models import AvaliadorIndicado, Projeto

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

PROJETOS_PRE_APROVADOS = '/projetos/projetos_pre_aprovados/{}/{}/'
ACEITAR = '/projetos/aceitar_indicacao/{}/'
REJEITAR = '/projetos/rejeitar_indicacao/{}/'
VISUALIZAR_PROJETOS_AVALIADOR = '/projetos/visualizar_projetos_avaliador/{}/'
AVALIAR = '/projetos/avaliar/{}/'
CANCELAR_PRE_AVALIACAO = '/projetos/cancelar_pre_avaliacao_projeto/{}/'


def celula(tela: Tela, texto: str) -> Locator:
    """A célula com exatamente ``texto`` — a mesma sonda serve à presença e à ausência."""
    return tela.loc(f'//td[normalize-space(.)="{texto}"]')


@pytest.fixture
def indicacoes(projeto_enviado_em) -> dict[str, AvaliadorIndicado | Projeto]:
    """Edital em seleção com três pré-selecionados: um indicado ao ``avaliador`` (com prazo de aceite), um ao ``segundo_avaliador`` e um a ninguém."""
    from projetos.tests.factories import AvaliadorIndicadoFactory

    pre_selecao = {'pre_aprovado': True, 'data_pre_avaliacao': datetime.date.today()}
    meu = projeto_enviado_em('selecao', sufixo='indicado a mim', **pre_selecao)
    do_outro = projeto_enviado_em('selecao', edital=meu.edital, sufixo='indicado ao outro', **pre_selecao)
    sem_indicacao = projeto_enviado_em('selecao', edital=meu.edital, sufixo='sem indicacao', **pre_selecao)
    prazo = datetime.datetime.now() + datetime.timedelta(days=3)
    return {
        'meu': AvaliadorIndicadoFactory(projeto=meu, vinculo=vinculo('avaliador'), prazo_para_aceite=prazo),
        'do_outro': AvaliadorIndicadoFactory(projeto=do_outro, vinculo=vinculo('segundo_avaliador'), prazo_para_aceite=prazo),
        'sem_indicacao': sem_indicacao,
    }


def projetos_do_avaliador(tela: Tela, projeto: Projeto) -> Tela:
    """A tela de projetos a avaliar do edital, no campus do projeto (a do link do convite)."""
    return tela.ir(PROJETOS_PRE_APROVADOS.format(projeto.edital.pk, projeto.uo.pk)).ver_titulo('Seleção de Projetos')


def test_avaliador_so_ve_os_projetos_em_que_foi_indicado(logado_projetos, indicacoes):
    meu = indicacoes['meu'].projeto
    tela = projetos_do_avaliador(Tela(logado_projetos('avaliador')), meu)

    expect(celula(tela, meu.titulo)).to_have_count(1)
    for outro in (indicacoes['do_outro'].projeto, indicacoes['sem_indicacao']):
        assert not celula(tela, outro.titulo).count(), f'a lista do avaliador mostrou projeto em que ele não foi indicado: {outro.titulo}'


def test_avaliador_aceita_a_indicacao(logado_projetos, indicacoes):
    indicacao = indicacoes['meu']
    tela = projetos_do_avaliador(Tela(logado_projetos('avaliador')), indicacao.projeto)

    clicar_em(tela, ACEITAR.format(indicacao.projeto.pk))
    tela.ver_titulo('Seleção de Projetos').sucesso('Indicação aceita com sucesso.')

    indicacao.refresh_from_db()
    assert indicacao.aceito_em is not None, 'a UI disse que aceitou, mas o aceite não persistiu'
    assert not tela.loc(f'//a[@href="{ACEITAR.format(indicacao.projeto.pk)}"]').count(), 'a indicação aceita continua oferecendo "Aceitar"'


def test_avaliador_rejeita_a_indicacao(logado_projetos, indicacoes):
    indicacao = indicacoes['meu']
    tela = projetos_do_avaliador(Tela(logado_projetos('avaliador')), indicacao.projeto)

    clicar_em(tela, REJEITAR.format(indicacao.projeto.pk))
    tela.ver_titulo('Seleção de Projetos').sucesso('Indicação rejeitada com sucesso.')

    indicacao.refresh_from_db()
    assert indicacao.rejeitado, 'a UI disse que rejeitou, mas a rejeição não persistiu'
    assert indicacao.rejeitado_em is not None, 'rejeitou sem registrar quando'


def test_avaliador_nao_responde_indicacao_de_outro_avaliador(logado_projetos, indicacoes):
    """Com o projeto em que só o OUTRO foi indicado, aceitar e rejeitar dão 403 e a indicação dele fica intacta.

    O controle positivo são os dois testes acima: a mesma rota, no projeto em que ele foi indicado, grava.
    """
    alheia = indicacoes['do_outro']
    tela = Tela(logado_projetos('avaliador'))

    respostas = {rota: tela.buscar(rota.format(alheia.projeto.pk)).status for rota in (ACEITAR, REJEITAR)}

    assert respostas == {ACEITAR: 403, REJEITAR: 403}, f'o avaliador respondeu pela indicação de outro: {respostas}'
    alheia.refresh_from_db()
    assert (alheia.aceito_em, alheia.rejeitado) == (None, False), 'a indicação do outro avaliador foi alterada'


RESPONDIDA_EM = datetime.datetime(2020, 1, 1, 8, 0)


def ja_rejeitada(indicacao: AvaliadorIndicado) -> None:
    indicacao.rejeitado, indicacao.rejeitado_em = True, RESPONDIDA_EM
    indicacao.save()


def ja_avaliada(indicacao: AvaliadorIndicado) -> None:
    from projetos.tests.factories import AvaliacaoFactory

    AvaliacaoFactory(projeto=indicacao.projeto, vinculo=indicacao.vinculo)


def ja_aceita(indicacao: AvaliadorIndicado) -> None:
    indicacao.aceito_em = RESPONDIDA_EM
    indicacao.save()


@pytest.mark.parametrize(
    ('estado', 'rota'),
    [
        (ja_rejeitada, ACEITAR),
        (ja_rejeitada, REJEITAR),
        (ja_avaliada, ACEITAR),
        (ja_avaliada, REJEITAR),
        (ja_aceita, ACEITAR),
    ],
    ids=['rejeitada-aceitar', 'rejeitada-rejeitar', 'avaliada-aceitar', 'avaliada-rejeitar', 'aceita-aceitar'],
)
def test_avaliador_nao_responde_indicacao_fora_do_estado_da_tela(logado_projetos, indicacoes, estado, rota):
    """#17548: a rota exige o mesmo estado em que ``projetos_pre_aprovados`` oferece o botão (``pendente_avaliacao``
    e, no aceite, ``pode_aceitar_indicacao``); fora dele, 403 e a indicação fica intacta.

    Quem já avaliou vê "Editar Avaliação", não "Rejeitar": rejeitar ali tiraria a avaliação gravada do alcance dele
    sem tirá-la da média. O controle positivo são ``test_avaliador_aceita_a_indicacao``/``..._rejeita_...``.
    """
    indicacao = indicacoes['meu']
    estado(indicacao)
    indicacao.refresh_from_db()
    antes = (indicacao.aceito_em, indicacao.rejeitado, indicacao.rejeitado_em)

    resposta = Tela(logado_projetos('avaliador')).buscar(rota.format(indicacao.projeto.pk))

    assert resposta.status == 403, f'{rota} respondeu {resposta.status} para indicação {estado.__name__}'
    indicacao.refresh_from_db()
    assert (indicacao.aceito_em, indicacao.rejeitado, indicacao.rejeitado_em) == antes, 'a indicação foi alterada'


def test_indicado_nao_age_sobre_projeto_com_pre_selecao_cancelada(logado_projetos, indicacoes):
    """#17560: o Gerente cancela a pré-avaliação e o projeto sai da lista do avaliador; a indicação fica, mas
    avaliar, aceitar e rejeitar passam a dar 403 e nada é gravado. O controle positivo é o "Avaliar" antes do cancelamento.
    """
    from projetos.models import Avaliacao

    indicacao = indicacoes['meu']
    projeto = indicacao.projeto
    avaliador = Tela(logado_projetos('avaliador'))
    assert avaliador.buscar(AVALIAR.format(projeto.pk)).status == 200, 'premissa: o indicado abre a avaliação do pré-selecionado'

    Tela(logado_projetos('gerente')).buscar(CANCELAR_PRE_AVALIACAO.format(projeto.pk))
    projeto.refresh_from_db()
    assert not projeto.pre_aprovado, 'premissa: o Gerente cancelou a pré-avaliação'

    respostas = {rota: avaliador.buscar(rota.format(projeto.pk)).status for rota in (AVALIAR, ACEITAR, REJEITAR)}

    assert respostas == {AVALIAR: 403, ACEITAR: 403, REJEITAR: 403}, f'o indicado agiu sobre projeto não pré-selecionado: {respostas}'
    indicacao.refresh_from_db()
    assert (indicacao.aceito_em, indicacao.rejeitado) == (None, False), 'a indicação foi alterada'
    assert not Avaliacao.objects.filter(projeto=projeto).exists(), 'gravou avaliação de projeto não pré-selecionado'


def test_avaliador_consulta_os_projetos_que_avaliou(logado_projetos, indicacoes):
    """``visualizar_projetos_avaliador`` lista as avaliações DELE no edital, não as dos outros."""
    from projetos.tests.factories import AvaliacaoFactory

    meu, do_outro = indicacoes['meu'].projeto, indicacoes['do_outro'].projeto
    AvaliacaoFactory(projeto=meu, vinculo=vinculo('avaliador'))
    AvaliacaoFactory(projeto=do_outro, vinculo=vinculo('segundo_avaliador'))
    tela = Tela(logado_projetos('avaliador')).ir(VISUALIZAR_PROJETOS_AVALIADOR.format(meu.edital.pk))

    tela.ver_titulo(f'Projetos avaliados - {meu.edital.titulo}')
    expect(celula(tela, meu.titulo)).to_have_count(1)
    assert not celula(tela, do_outro.titulo).count(), 'a consulta do avaliador mostrou a avaliação de outro avaliador'


@pytest.mark.parametrize(('papel', 'status'), [('avaliador', 200), ('coordenador_projeto', 200), ('aluno', 403)])
def test_telas_do_avaliador_por_papel(logado_projetos, projetos_seed, papel, status):
    """``pode_se_tornar_avaliador`` (Servidor, Prestador, Externo): o aluno não abre; o servidor abre (a lista vem vazia)."""
    edital = projetos_seed.editais['selecao']
    tela = Tela(logado_projetos(papel))
    rotas = (PROJETOS_PRE_APROVADOS.format(edital.pk, projetos_seed.uo.pk), VISUALIZAR_PROJETOS_AVALIADOR.format(edital.pk))

    assert {rota: tela.buscar(rota).status for rota in rotas} == dict.fromkeys(rotas, status)


def test_projetos_a_avaliar_fora_da_selecao(logado_projetos, projetos_seed):
    """Fora do período de seleção a tela do avaliador responde 403 (o edital em pré-seleção ainda não chegou lá)."""
    edital = projetos_seed.editais['pre_selecao']
    resposta = Tela(logado_projetos('avaliador')).buscar(PROJETOS_PRE_APROVADOS.format(edital.pk, projetos_seed.uo.pk))
    assert resposta.status == 403
