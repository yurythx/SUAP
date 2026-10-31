"""Escopo do Coordenador de Extensão: papel LOCAL, só enxerga e age em projetos do PRÓPRIO campus (#17520).

Decisão de produto (29/09/2026): o Coordenador de Extensão responde pelo campus dele; acesso a
projeto de outro campus é bug. Os grupos "Sistêmico" (Gerente, Pré-Avaliador) e o "Visualizador de
Projetos" continuam com escopo institucional — a correção não pode fechá-los.

Cada teste é parametrizado em ``proprio_campus`` — o controle positivo: o MESMO acesso, pelo mesmo
papel, num projeto do CZN abre ou grava, o que prova que a sonda funciona — e ``na_reitoria`` — a
sonda, num projeto (ou visita) da reitoria. Os vazamentos que a sonda mediu foram fechados na #17520
pelo recorte de campus (``Projeto.is_coordenador_extensao_do_campus`` e
``campus_do_coordenador_extensao``).

Todo projeto aqui sai de ``projeto_em_execucao(monitor=None)``: o default faz do Coordenador de
Extensão do CZN o monitor até de projeto de outro campus, e o monitor tem porta própria em várias
views (``prestacao_contas`` aceita ``vinculo_monitor``) — com ele, a sonda mediria a porta errada.
"""

from __future__ import annotations

import datetime
from collections.abc import Callable, Iterator
from types import SimpleNamespace
from typing import TYPE_CHECKING
from urllib.parse import urlencode
from uuid import uuid4

import pytest
from playwright.sync_api import expect

from djtools.e2e_ui import Tela
from projetos.tests.e2e.conftest import banco, membro, outra_uo
from projetos.tests.e2e.test_ciclo_de_vida import postar_formulario

if TYPE_CHECKING:
    from _pytest.mark.structures import ParameterSet

    from projetos.models import Participacao, Projeto, VisitaTecnica
    from rh.models import UnidadeOrganizacional

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

LISTA_MENSAL = '/projetos/lista_mensal_bolsistas/'
PRESTACAO = '/projetos/prestacao_contas/{}/'
VISUALIZAR_VISITA = '/projetos/visualizar_visita_tecnica/{}/'
CERTIFICADO = '/projetos/emitir_certificado_extensao_pdf/{}/'
DECLARACAO_PARTICIPACAO = '/projetos/emitir_declaracao_participacao_pdf/{}/'
HISTORICO = '/projetos/gerenciar_historico_projeto/{}/'
FINANCEIRO = '/projetos/relatorio_financeiro/'

TABELA_FINANCEIRO = '//table[caption[normalize-space(.)="Lista dos projetos"]]'


def campi() -> list[ParameterSet]:
    """Os dois parâmetros de ``na_reitoria``: o próprio campus (controle) e o outro (sonda)."""
    return [pytest.param(False, id='proprio_campus'), pytest.param(True, id='outro_campus')]


def campus_da_sonda(projetos_seed: SimpleNamespace, na_reitoria: bool) -> UnidadeOrganizacional:
    """A reitoria na sonda; o CZN (o campus do Coordenador de Extensão) no controle."""
    return outra_uo() if na_reitoria else projetos_seed.uo


def em_execucao_sem_monitor(projeto_em_execucao: Callable[..., SimpleNamespace], projetos_seed: SimpleNamespace, na_reitoria: bool) -> Projeto:
    return projeto_em_execucao(uo=campus_da_sonda(projetos_seed, na_reitoria), monitor=None).projeto


# ------------------------------------------------------------------------ lista mensal de bolsistas


@pytest.mark.parametrize('na_reitoria', campi())
def test_lista_mensal_de_bolsistas_so_do_proprio_campus(logado_projetos, projeto_em_execucao, projetos_seed, na_reitoria):
    """A folha de bolsistas do mês traz nome, matrícula e conta bancária: o Coordenador de Extensão só vê a do campus dele."""
    from comum.tests.factories import AnoFactory
    from projetos.tests.factories import ProjetoAnexoFactory

    execucao = projeto_em_execucao(uo=campus_da_sonda(projetos_seed, na_reitoria), monitor=None)
    conta = f'{uuid4().int % 10**6:06d}-9'
    participacao = membro(execucao.projeto, 'aluno', instituicao=banco(), numero_agencia='3293-X', tipo_conta='Conta Corrente', numero_conta=conta)
    hoje = datetime.date.today()
    ano = AnoFactory(ano=hoje.year)
    ProjetoAnexoFactory(
        projeto=execucao.projeto,
        participacao=participacao,
        vinculo_membro_equipe=participacao.vinculo_pessoa,
        desembolso=execucao.desembolso,
        ano=ano,
        mes=hoje.month,
    )

    tela = Tela(logado_projetos('coordenador_extensao')).ir(f'{LISTA_MENSAL}?{urlencode({"ano": ano.pk, "mes": hoje.month})}')
    tela.ver_titulo('Lista Mensal de Bolsistas')
    bolsista = tela.loc(f'//tr[contains(normalize-space(.), "{execucao.projeto.titulo}") and contains(normalize-space(.), "{conta}")]')
    expect(bolsista).to_have_count(0 if na_reitoria else 1)


# ----------------------------------------------------------------------------- prestação de contas


@pytest.mark.parametrize('na_reitoria', campi())
def test_prestacao_de_contas_so_do_proprio_campus(logado_projetos, projeto_em_execucao, projetos_seed, na_reitoria):
    projeto = em_execucao_sem_monitor(projeto_em_execucao, projetos_seed, na_reitoria)
    status = Tela(logado_projetos('coordenador_extensao')).buscar(PRESTACAO.format(projeto.pk)).status
    assert status == (403 if na_reitoria else 200), f'o Coordenador de Extensão do CZN recebeu {status} na prestação de contas'


# ---------------------------------------------------------------------------------- visita técnica


@pytest.fixture
def visita_tecnica_em(projetos_seed) -> Iterator[Callable[[UnidadeOrganizacional], VisitaTecnica]]:
    """``(uo) -> VisitaTecnica`` do campus ``uo``; apagadas no fim (não são filhas de edital, a cascata não as leva)."""
    from projetos.tests.factories import VisitaTecnicaFactory

    visitas: list[VisitaTecnica] = []

    def _em(uo: UnidadeOrganizacional) -> VisitaTecnica:
        visitas.append(VisitaTecnicaFactory(campus=uo, instituicao_visitada=f'Escola parceira {uuid4().hex[:8]}'))
        return visitas[-1]

    yield _em
    for visita in visitas:
        visita.delete()


@pytest.mark.parametrize('na_reitoria', campi())
def test_visita_tecnica_so_do_proprio_campus(logado_projetos, visita_tecnica_em, projetos_seed, na_reitoria):
    visita = visita_tecnica_em(campus_da_sonda(projetos_seed, na_reitoria))
    status = Tela(logado_projetos('coordenador_extensao')).buscar(VISUALIZAR_VISITA.format(visita.pk)).status
    assert status == (403 if na_reitoria else 200), f'o Coordenador de Extensão do CZN recebeu {status} na ficha da visita técnica'


# ------------------------------------------------------------- certificado e declaração de participação


def membro_que_saiu(projeto: Projeto) -> Participacao:
    """O ``avaliador`` que entrou no início da execução e saiu 10 dias depois — tem direito a certificado."""
    from projetos.models import HistoricoEquipe
    from projetos.tests.factories import HistoricoEquipeFactory

    saida = projeto.inicio_execucao + datetime.timedelta(days=10)
    participacao = membro(projeto, 'avaliador', ativo=False, data_inativacao=saida)
    HistoricoEquipe.objects.filter(participante=participacao).update(data_movimentacao_saida=saida)
    HistoricoEquipeFactory(participante=participacao, tipo_de_evento=HistoricoEquipe.EVENTO_INATIVAR_PARTICIPANTE, data_movimentacao=saida)
    return participacao


# Documento -> (rota, participação que tem direito a ele, nome que sai no documento).
DOCUMENTOS = {
    'certificado': (CERTIFICADO, membro_que_saiu, 'Avaliador Extensão E2E'),
    'declaracao': (DECLARACAO_PARTICIPACAO, lambda projeto: membro(projeto, 'segundo_avaliador'), 'Segundo Avaliador E2E'),
}


@pytest.mark.parametrize('documento', list(DOCUMENTOS))
@pytest.mark.parametrize('na_reitoria', campi())
def test_documentos_de_participacao_so_do_proprio_campus(logado_projetos, projeto_em_execucao, projetos_seed, na_reitoria, documento):
    """O certificado (membro que saiu) e a declaração (membro ativo) de membro de projeto de outro campus não saem para ele."""
    rota, participante, nome = DOCUMENTOS[documento]
    projeto = em_execucao_sem_monitor(projeto_em_execucao, projetos_seed, na_reitoria)
    resposta = Tela(logado_projetos('coordenador_extensao')).buscar(rota.format(participante(projeto).pk))

    if na_reitoria:
        # Hoje a view nega com `httprr('/', ..., 'error')`; um 403 também é negar.
        assert resposta.status == 403 or resposta.headers.get('location') == '/', (
            f'o {documento} saiu (status {resposta.status}, nome no corpo: {nome in resposta.text()})'
        )
    else:
        assert (resposta.status, nome in resposta.text()) == (200, True), f'o {documento} do membro do CZN não saiu (status {resposta.status})'


# ------------------------------------------------------------------------------------------- devolução


@pytest.mark.parametrize('na_reitoria', campi())
def test_devolucao_so_no_proprio_campus(logado_projetos, projeto_enviado_em, projetos_seed, na_reitoria):
    """O POST de "Devolver Projeto" (o mesmo do controle ``test_devolucao_por_post_sem_a_tela``) num projeto enviado, na inscrição."""
    from projetos.models import Projeto

    projeto = projeto_enviado_em('inscricao', uo=campus_da_sonda(projetos_seed, na_reitoria))
    resposta = postar_formulario(Tela(logado_projetos('coordenador_extensao')), HISTORICO.format(projeto.pk), {'parecer_devolucao': 'Devolvido'})

    devolvido = Projeto.objects.get(pk=projeto.pk).data_conclusao_planejamento is None
    assert (resposta.status, devolvido) == ((403, False) if na_reitoria else (302, True)), (
        f'devolução pelo Coordenador de Extensão do CZN: status {resposta.status}, projeto devolvido={devolvido}'
    )


# ------------------------------------------------------------------------------- relatório financeiro


@pytest.mark.parametrize('na_reitoria', campi())
def test_relatorio_financeiro_so_do_proprio_campus(logado_projetos, projeto_em_execucao, catalogo_do_edital, projetos_seed, na_reitoria):
    """Filtrado pelo campus do projeto: o gerente (institucional) o vê — prova que o filtro é válido —, o Coordenador de Extensão só se for do CZN."""
    from financeiro.models import NaturezaDespesa
    from projetos.tests.factories import RecursoFactory

    uo = campus_da_sonda(projetos_seed, na_reitoria)
    projeto = projeto_em_execucao(uo=uo, monitor=None).projeto
    recurso = RecursoFactory(edital=projeto.edital, despesa=NaturezaDespesa.objects.get(codigo='339018'))
    url = f'{FINANCEIRO}?{urlencode({"edital": projeto.edital_id, "recurso": recurso.pk, "uo": uo.pk})}'
    linha = f'{TABELA_FINANCEIRO}//tr[contains(normalize-space(.), "{projeto.titulo}")]'

    expect(Tela(logado_projetos('gerente')).ir(url).loc(linha)).to_have_count(1)
    expect(Tela(logado_projetos('coordenador_extensao')).ir(url).loc(linha)).to_have_count(0 if na_reitoria else 1)
