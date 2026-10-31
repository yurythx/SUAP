"""Fluxo: o desfecho do projeto avaliado — reprovação manual, execução sem fomento e validação de projeto externo.

Com a seleção encerrada e o resultado ainda não divulgado, o Gerente Sistêmico pode reprovar
manualmente um projeto (e reverter), e a rotina de classificação roda de novo sem ele. O projeto
pré-selecionado que NÃO foi selecionado pode ser autorizado a executar sem fomento (em lote, pelo
Gerente ou pelo Coordenador de Extensão do campus); o coordenador aceita ou rejeita em "Projetos
autorizados sem fomento", e aceitar o aprova. Rejeitado, o gerente pode autorizar de novo; em
execução sem fomento, o Coordenador de Extensão do campus (ou o gerente) autoriza o fomento. O
projeto de edital de fomento EXTERNO não passa por avaliação: o monitor defere ou indefere o
registro.

A regressão cara é o ``aprovado`` mudar por quem não deveria — é ele que põe o projeto em
execução. Todas as ações daqui (menos a reprovação) gravam por GET: sempre em projeto descartável,
e as sondas de acesso por ``buscar``.
"""

from __future__ import annotations

import datetime
from collections.abc import Callable
from decimal import Decimal
from typing import TYPE_CHECKING

import pytest
from playwright.sync_api import Locator, expect

from djtools.e2e_ui import Tela
from projetos.tests.e2e.conftest import clicar_em, outra_uo, vinculo

if TYPE_CHECKING:
    from projetos.models import ItemAvaliacao, Projeto

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

PROJETO = '/projetos/projeto/{}/'
REPROVAR = '/projetos/reprovar_manualmente/{}/'
REVERTER = '/projetos/reverter_reprovacao/{}/'
APROVAR_SEM_FOMENTO = '/projetos/aprovar_projetos_sem_fomento/{}/'
AUTORIZAR_EM_LOTE = '/projetos/autorizar_projetos_sem_fomento/{}/'
MEUS_AUTORIZADOS = '/projetos/meus_projetos_autorizados_sem_fomento/'
AVALIAR_EXECUTAR = '/projetos/avaliar_executar_projeto/{}/{}/'
AUTORIZAR_SEM_FOMENTO = '/projetos/autorizar_sem_fomento/{}/'
AUTORIZAR_FOMENTO = '/projetos/autorizar_fomento/{}/'
VALIDAR_EXTERNO = '/projetos/validar_projeto_externo/{}/{}/'

CLASSIFICADO = 'Rotina de classificação dos projetos executada com sucesso.'


def celula(tela: Tela, texto: str) -> Locator:
    """A célula com exatamente ``texto`` — a mesma sonda serve à presença e à ausência."""
    return tela.loc(f'//td[normalize-space(.)="{texto}"]')


def recarregado(projeto: Projeto) -> Projeto:
    projeto.refresh_from_db()
    return projeto


def forjar_registro(tela: Tela, projeto: Projeto) -> None:
    """Acrescenta ao formulário da lista um ``registros`` com o id de um projeto que ela NÃO ofereceu — o POST forjado."""
    tela.loc('//form[@id="bolsas_form"]').evaluate(
        '(form, pk) => { const campo = document.createElement("input"); campo.type = "hidden"; campo.name = "registros"; '
        'campo.value = pk; form.appendChild(campo); }',
        str(projeto.pk),
    )


# ------------------------------------------------------------------ reprovação manual


def test_gerente_reprova_manualmente_e_a_classificacao_o_deixa_de_fora(logado_projetos, projeto_avaliado):
    """ "Reprovar manualmente" → justificativa → a rotina de classificação roda, e o projeto (nota 9 de 10) sai reprovado."""
    projeto = projeto_avaliado(nota=9, pontuacao=Decimal(9), aprovado=True).avaliacao.projeto
    tela = Tela(logado_projetos('gerente')).ir(PROJETO.format(projeto.pk))

    clicar_em(tela, REPROVAR.format(projeto.pk))
    tela.ver_titulo(f'Reprovar projeto manualmente - {projeto.titulo}').preencher('Justificativa para a reprovação', 'textarea', 'Plágio.')
    tela.clicar_botao('Salvar')

    tela.esperar().ver_texto(CLASSIFICADO)  # `@task` síncrono: a tela é a da tarefa (armadilha 3)
    projeto = recarregado(projeto)
    assert (projeto.justificativa_reprovacao_manual, projeto.reprovacao_manual_por) == ('Plágio.', vinculo('gerente')), 'a reprovação não persistiu'
    assert not projeto.aprovado, 'reprovado manualmente, o projeto continuou aprovado depois da classificação'


def test_gerente_reverte_a_reprovacao_e_a_classificacao_o_aprova(logado_projetos, projeto_avaliado):
    """ "Reverter reprovação" apaga a reprovação e reclassifica: nota 9 de 10, o projeto volta a ser aprovado."""
    reprovado = {
        'reprovacao_manual_em': datetime.datetime.now(),
        'justificativa_reprovacao_manual': 'Plágio.',
        'reprovacao_manual_por': vinculo('gerente'),
    }
    projeto = projeto_avaliado(nota=9, pontuacao=Decimal(9), **reprovado).avaliacao.projeto
    tela = Tela(logado_projetos('gerente')).ir(PROJETO.format(projeto.pk))

    clicar_em(tela, REVERTER.format(projeto.pk))
    tela.esperar().ver_texto(CLASSIFICADO)

    projeto = recarregado(projeto)
    assert (projeto.reprovacao_manual_em, projeto.justificativa_reprovacao_manual) == (None, None), 'a reprovação não foi revertida'
    assert projeto.aprovado, 'revertida a reprovação, a classificação não aprovou o projeto de nota 9'


@pytest.mark.parametrize('papel', ['coordenador_extensao', 'coordenador_projeto'])
def test_so_o_gerente_reprova_e_reverte(logado_projetos, projeto_avaliado, papel):
    reprovado = projeto_avaliado(sufixo='reprovado', reprovacao_manual_em=datetime.datetime.now()).avaliacao.projeto
    aprovado = projeto_avaliado(sufixo='aprovado', edital=reprovado.edital, aprovado=True).avaliacao.projeto
    tela = Tela(logado_projetos(papel))

    assert (tela.buscar(REPROVAR.format(aprovado.pk)).status, tela.buscar(REVERTER.format(reprovado.pk)).status) == (403, 403)
    assert recarregado(reprovado).reprovacao_manual_em is not None, 'a reprovação foi revertida por quem recebeu 403'


# ------------------------------------------------------------------ execução sem fomento


def test_coordenador_de_extensao_autoriza_sem_fomento_o_nao_selecionado_do_campus(logado_projetos, projeto_avaliado):
    """ "Aprovar sem fomento" lista o pré-selecionado não aprovado do campus; "Aplicar" autoriza. O de outro campus, nem forjado."""
    proprio = projeto_avaliado(sufixo='proprio').avaliacao.projeto
    alheio = projeto_avaliado(edital=proprio.edital, uo=outra_uo(), sufixo='alheio').avaliacao.projeto
    tela = Tela(logado_projetos('coordenador_extensao')).ir(APROVAR_SEM_FOMENTO.format(proprio.edital.pk))

    tela.ver_titulo(f'Aprovar projetos sem fomento: {proprio.edital}')
    expect(celula(tela, proprio.titulo)).to_have_count(1)
    assert not celula(tela, alheio.titulo).count(), 'a lista do Coordenador de Extensão mostrou projeto de outro campus'
    expect(tela.loc(f'//form[@action="{AUTORIZAR_EM_LOTE.format(proprio.edital.pk)}"]')).to_have_count(1)
    forjar_registro(tela, alheio)
    tela.selecionar_item(proprio.titulo).clicar_botao('Aplicar')

    tela.esperar().sucesso('Projetos autorizados com sucesso.')
    proprio = recarregado(proprio)
    assert (proprio.autorizada_sem_fomento, proprio.autorizada_sem_fomento_por) == (True, vinculo('coordenador_extensao')), (
        'a autorização não persistiu'
    )
    assert not recarregado(alheio).autorizada_sem_fomento, 'o projeto de outro campus, forjado no POST, foi autorizado'


def test_autorizacao_em_lote_so_grava_projeto_da_lista(logado_projetos, projeto_avaliado):
    listado = projeto_avaliado(sufixo='listado').avaliacao.projeto
    ja_aprovado = projeto_avaliado(sufixo='ja aprovado', aprovado=True).avaliacao.projeto  # outro edital, mesmo campus
    tela = Tela(logado_projetos('coordenador_extensao')).ir(APROVAR_SEM_FOMENTO.format(listado.edital.pk))

    forjar_registro(tela, ja_aprovado)
    tela.selecionar_item(listado.titulo).clicar_botao('Aplicar')
    tela.esperar().sucesso('Projetos autorizados com sucesso.')

    assert not recarregado(ja_aprovado).autorizada_sem_fomento, 'projeto já aprovado de outro edital, forjado no POST, saiu autorizado sem fomento'


def autorizado_sem_fomento(projeto_avaliado: Callable[..., ItemAvaliacao], **campos: object) -> Projeto:
    """Pré-selecionado não aprovado, já autorizado pelo Coordenador de Extensão a executar sem fomento."""
    autorizacao = {
        'autorizada_sem_fomento': True,
        'autorizada_sem_fomento_em': datetime.datetime.now(),
        'autorizada_sem_fomento_por': vinculo('coordenador_extensao'),
    }
    return projeto_avaliado(**{**autorizacao, **campos}).avaliacao.projeto


@pytest.mark.parametrize(('opcao', 'esperado'), [(1, (True, True)), (2, (False, False))], ids=['aceita', 'rejeita'])
def test_coordenador_aceita_ou_rejeita_executar_sem_fomento(logado_projetos, projeto_avaliado, opcao, esperado):
    """ "Aceitar executar" aprova o projeto; "Rejeitar executar" não. Nos dois casos a manifestação fica registrada."""
    projeto = autorizado_sem_fomento(projeto_avaliado)
    tela = Tela(logado_projetos('coordenador_projeto')).ir(MEUS_AUTORIZADOS)

    tela.ver_titulo('Projetos autorizados a entrar em execução sem fomento')
    expect(celula(tela, projeto.titulo)).to_have_count(1)
    clicar_em(tela, AVALIAR_EXECUTAR.format(projeto.pk, opcao))
    tela.sucesso('Manifestação registrada com sucesso.')

    projeto = recarregado(projeto)
    assert (projeto.aceita_sem_fomento, projeto.aprovado) == esperado, 'a manifestação não gravou o que a UI mostrou'
    assert projeto.avaliacao_aceite_sem_fomento_por == vinculo('coordenador_projeto'), 'a manifestação não registrou quem'
    assert not celula(tela, projeto.titulo).count(), 'o projeto manifestado continua na lista'


def test_coordenador_nao_aprova_sozinho_projeto_nao_autorizado(logado_projetos, projeto_avaliado):
    projeto = projeto_avaliado().avaliacao.projeto
    resposta = Tela(logado_projetos('coordenador_projeto')).buscar(AVALIAR_EXECUTAR.format(projeto.pk, 1))

    assert not recarregado(projeto).aprovado, 'o coordenador aprovou o próprio projeto sem autorização de execução sem fomento'
    assert resposta.status == 403, f'respondeu {resposta.status} ao aceite de execução sem autorização'


def test_gerente_autoriza_de_novo_quem_rejeitou_executar_sem_fomento(logado_projetos, projeto_avaliado):
    """O coordenador rejeitou; "Autorizar execução sem fomento" zera a manifestação e o projeto volta à lista dele."""
    rejeitou = {'aceita_sem_fomento': False, 'avaliacao_aceite_sem_fomento_em': datetime.datetime.now()}
    projeto = autorizado_sem_fomento(projeto_avaliado, **rejeitou, avaliacao_aceite_sem_fomento_por=vinculo('coordenador_projeto'))
    tela = Tela(logado_projetos('gerente')).ir(PROJETO.format(projeto.pk))

    clicar_em(tela, AUTORIZAR_SEM_FOMENTO.format(projeto.pk))
    tela.sucesso('Projeto autorizado com sucesso.')

    projeto = recarregado(projeto)
    assert (projeto.aceita_sem_fomento, projeto.avaliacao_aceite_sem_fomento_em) == (None, None), 'a manifestação anterior não foi zerada'
    assert projeto.autorizada_sem_fomento_por == vinculo('gerente'), 'a nova autorização não registrou quem'
    coordenador = Tela(logado_projetos('coordenador_projeto')).ir(MEUS_AUTORIZADOS)
    expect(celula(coordenador, projeto.titulo)).to_have_count(1)


def test_coordenador_de_extensao_nao_reautoriza_projeto_de_outro_campus(logado_projetos, projeto_avaliado):
    rejeitou = {'aceita_sem_fomento': False, 'avaliacao_aceite_sem_fomento_em': datetime.datetime.now()}
    projeto = autorizado_sem_fomento(projeto_avaliado, uo=outra_uo(), sufixo='outro campus', **rejeitou)
    resposta = Tela(logado_projetos('coordenador_extensao')).buscar(AUTORIZAR_SEM_FOMENTO.format(projeto.pk))

    assert recarregado(projeto).aceita_sem_fomento is False, 'a execução sem fomento de outro campus foi reautorizada'
    assert resposta.status == 403, f'respondeu {resposta.status} à reautorização de projeto de outro campus'


def test_coordenador_de_extensao_autoriza_o_fomento_do_projeto_do_campus(logado_projetos, projeto_avaliado):
    """Em execução sem fomento, "Autorizar Fomento" registra a autorização (e as abas financeiras voltam)."""
    aceitou = {'aceita_sem_fomento': True, 'aprovado': True, 'avaliacao_aceite_sem_fomento_em': datetime.datetime.now()}
    projeto = autorizado_sem_fomento(projeto_avaliado, **aceitou)
    tela = Tela(logado_projetos('coordenador_extensao')).ir(PROJETO.format(projeto.pk))

    clicar_em(tela, AUTORIZAR_FOMENTO.format(projeto.pk))
    tela.sucesso('Fomento autorizado com sucesso.')

    projeto = recarregado(projeto)
    assert projeto.fomento_autorizado_em is not None, 'a UI disse que autorizou, mas o fomento não foi autorizado'
    assert projeto.fomento_autorizado_por == vinculo('coordenador_extensao'), 'a autorização não registrou quem'


@pytest.mark.parametrize('papel', ['coordenador_extensao', 'pre_avaliador'])
def test_fomento_de_outro_campus_nao_e_autorizado(logado_projetos, projeto_avaliado, papel):
    """O Coordenador de Extensão do CZN (papel local) e o Pré-Avaliador não autorizam o fomento de projeto da reitoria.

    A view não responde 403: sem a condição, cai no template default (200, tela vazia) — mas não grava.
    """
    aceitou = {'aceita_sem_fomento': True, 'aprovado': True, 'avaliacao_aceite_sem_fomento_em': datetime.datetime.now()}
    projeto = autorizado_sem_fomento(projeto_avaliado, uo=outra_uo(), sufixo='outro campus', **aceitou)

    Tela(logado_projetos(papel)).buscar(AUTORIZAR_FOMENTO.format(projeto.pk))

    assert recarregado(projeto).fomento_autorizado_em is None, f'o {papel} autorizou o fomento de projeto de outro campus'


@pytest.mark.parametrize(
    ('papel', 'esperado'),
    [
        ('gerente', {'aprovar': 200, 'meus': 200}),
        ('coordenador_extensao', {'aprovar': 200, 'meus': 200}),
        ('coordenador_projeto', {'aprovar': 403, 'meus': 200}),
        ('avaliador', {'aprovar': 403, 'meus': 200}),
    ],
)
def test_telas_de_execucao_sem_fomento_por_papel(logado_projetos, projetos_seed, papel, esperado):
    """ "Aprovar sem fomento": ``add_edital`` (Gerente e Coordenador de Extensão); "Meus autorizados": ``pode_interagir_com_projeto``."""
    tela = Tela(logado_projetos(papel))
    rotas = {'aprovar': APROVAR_SEM_FOMENTO.format(projetos_seed.editais['resultado_parcial'].pk), 'meus': MEUS_AUTORIZADOS}

    assert {nome: tela.buscar(rota).status for nome, rota in rotas.items()} == esperado


# ------------------------------------------------------------------ projeto de fomento externo


@pytest.fixture
def externo_monitorado(edital_novo, projeto_enviado_em) -> Projeto:
    """Projeto enviado em edital de fomento EXTERNO, com o Coordenador de Extensão como monitor e sem avaliação."""
    edital = edital_novo(tipo_fomento='Externo', campus_especifico=True)
    return projeto_enviado_em('inscricao', edital=edital, vinculo_monitor=vinculo('coordenador_extensao'))


@pytest.mark.parametrize(
    ('opcao', 'mensagem', 'aprovado'),
    [('1', 'Projeto deferido com sucesso.', True), ('2', 'Projeto indeferido com sucesso.', False)],
    ids=['defere', 'indefere'],
)
def test_monitor_defere_ou_indefere_o_registro_do_projeto_externo(logado_projetos, externo_monitorado, opcao, mensagem, aprovado):
    """ "Deferir Registro"/"Indeferir Registro": o monitor decide pré-seleção e seleção de uma vez, com a data de hoje."""
    projeto = externo_monitorado
    tela = Tela(logado_projetos('coordenador_extensao')).ir(PROJETO.format(projeto.pk))

    clicar_em(tela, VALIDAR_EXTERNO.format(projeto.pk, opcao))
    tela.sucesso(mensagem)

    projeto = recarregado(projeto)
    assert (projeto.pre_aprovado, projeto.aprovado) == (aprovado, aprovado), 'a decisão do monitor não persistiu'
    assert (projeto.data_avaliacao, projeto.vinculo_autor_avaliacao) == (datetime.date.today(), vinculo('coordenador_extensao'))


def test_so_o_monitor_valida_e_so_com_opcao_valida(logado_projetos, externo_monitorado):
    """Quem não é o monitor, e o monitor com opção inexistente: 403, e o projeto fica sem decisão."""
    projeto = externo_monitorado
    respostas = {
        'nao monitor': Tela(logado_projetos('coordenador_projeto')).buscar(VALIDAR_EXTERNO.format(projeto.pk, '1')).status,
        'opcao invalida': Tela(logado_projetos('coordenador_extensao')).buscar(VALIDAR_EXTERNO.format(projeto.pk, '3')).status,
    }

    assert respostas == {'nao monitor': 403, 'opcao invalida': 403}
    assert (recarregado(projeto).aprovado, projeto.data_avaliacao) == (False, None), 'o projeto externo foi decidido por quem recebeu 403'


def test_monitor_nao_aprova_projeto_interno_pela_validacao_de_externo(logado_projetos, projeto_enviado_em):
    projeto = projeto_enviado_em(
        'selecao', pre_aprovado=True, data_pre_avaliacao=datetime.date.today(), vinculo_monitor=vinculo('coordenador_extensao')
    )
    resposta = Tela(logado_projetos('coordenador_extensao')).buscar(VALIDAR_EXTERNO.format(projeto.pk, '1'))

    assert not recarregado(projeto).aprovado, 'o monitor aprovou projeto de edital interno sem avaliação'
    assert resposta.status == 403, f'respondeu {resposta.status} à validação de externo em projeto interno'
