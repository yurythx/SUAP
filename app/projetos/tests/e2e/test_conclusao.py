"""Fluxo: a conclusão do projeto — registro, finalização pelo coordenador, parecer do monitor, finalização sistêmica e o relatório.

O caminho do behave (features 008, 009 e 010): o coordenador **registra a conclusão** (popup na
aba "Conclusão"), **finaliza o projeto** — só sem pendências — e o **monitor** emite o parecer
pela tela de monitoramento, o que conclui o projeto. O gerente tem o atalho da **finalização
sistêmica**, que conclui um projeto em execução de uma vez, e o **relatório do projeto** é o
documento que resume a execução.

As sondas: quem não coordena não registra nem finaliza; só o monitor (e o gerente) emite
parecer — e só depois da finalização, como a tela oferece (#17517); finalizar sem registro de
conclusão não quebra (#17518).
"""

from __future__ import annotations

import datetime
from typing import TYPE_CHECKING
from uuid import uuid4

import pytest
from playwright.sync_api import expect

from djtools.e2e_fixtures import popup_em
from djtools.e2e_ui import Tela
from projetos.tests.e2e.conftest import clicar_em, vinculo

if TYPE_CHECKING:
    from types import SimpleNamespace

    from projetos.models import RegistroConclusaoProjeto

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

PROJETO = '/projetos/projeto/{}/'
REGISTRO_CONCLUSAO = '/projetos/registro_conclusao/{}/'
FINALIZAR_CONCLUSAO = '/projetos/finalizar_conclusao/{}/'
MONITORAMENTO = '/projetos/projetos_em_execucao/'
VALIDAR_EXECUCAO = '/projetos/validar_execucao_etapa/{}/'
AVALIAR_CONCLUSAO = '/projetos/avaliar_conclusao_projeto/{}/'
FINALIZACAO_SISTEMICA = '/projetos/finalizar_projeto_forma_sistemica/{}/'
RELATORIO = '/projetos/relatorio_projeto/{}/'


def sem_pendencias(execucao: SimpleNamespace) -> None:
    """Quita as quatro pendências com que o ``projeto_em_execucao`` nasce (``Projeto.tem_pendencias``).

    A atividade sem execução registrada, o desembolso sem gasto, a falta de foto e a
    caracterização sem a quantidade atendida: registros já avaliados pelo monitor, uma foto e a
    quantidade informada.
    """
    from projetos.models import CaracterizacaoBeneficiario
    from projetos.tests.factories import FotoProjetoFactory, RegistroExecucaoEtapaFactory, RegistroGastoFactory

    avaliado = {'avaliador': vinculo('coordenador_extensao').relacionamento, 'dt_avaliacao': datetime.date.today(), 'aprovado': True}
    RegistroExecucaoEtapaFactory(etapa=execucao.etapa, **avaliado)
    RegistroGastoFactory(desembolso=execucao.desembolso, **avaliado)
    CaracterizacaoBeneficiario.objects.filter(pk=execucao.caracterizacao.pk).update(quantidade_atendida=10)
    FotoProjetoFactory(projeto=execucao.projeto)


def conclusao_registrada(execucao: SimpleNamespace, finalizada: bool = False) -> RegistroConclusaoProjeto:
    """O registro de conclusão ainda sem parecer (a factory, por padrão, já o dá por avaliado); ``finalizada`` marca a finalização do coordenador."""
    from projetos.models import Projeto
    from projetos.tests.factories import RegistroConclusaoProjetoFactory

    registro = RegistroConclusaoProjetoFactory(projeto=execucao.projeto, dt_avaliacao=None, aprovado=False)
    if finalizada:
        Projeto.objects.filter(pk=execucao.projeto.pk).update(data_finalizacao_conclusao=datetime.datetime.now())
    return registro


# ------------------------------------------------------------------ registro e finalização


def test_coordenador_registra_e_edita_a_conclusao(logado_projetos, projeto_em_execucao):
    """Feature 008: "Registrar Conclusão" (popup) e, depois, "Editar Registro de Conclusão" no mesmo lugar."""
    from projetos.models import RegistroConclusaoProjeto

    projeto = projeto_em_execucao().projeto
    rota = REGISTRO_CONCLUSAO.format(projeto.pk)
    tela = Tela(logado_projetos('coordenador_projeto')).ir(PROJETO.format(projeto.pk))

    tela.clicar_aba('Conclusão')
    clicar_em(tela, rota)
    popup = popup_em(tela, rota).preencher_formulario(
        [
            ('Resultados Alcançados', 'textarea', 'descricao dos resultados alcancados'),
            ('Disseminação dos Resultados', 'textarea', 'descricao da disseminacao'),
            ('Observação', 'textarea', 'Obs sobre a conclusão'),
        ]
    )
    tela = popup.salvar_no_popup('Salvar').sucesso('Conclusão do projeto registrada com sucesso.')
    registro = RegistroConclusaoProjeto.objects.filter(projeto=projeto).first()
    assert registro is not None, 'a UI disse que registrou, mas a conclusão não persistiu'
    assert (registro.resultados_alcancados, registro.disseminacao_resultados, registro.dt_avaliacao) == (
        'descricao dos resultados alcancados',
        'descricao da disseminacao',
        None,
    )

    tela.clicar_aba('Conclusão').ver_texto('Aguardando o coordenador finalizar o projeto')
    clicar_em(tela, rota)  # agora "Editar Registro de Conclusão"
    popup_em(tela, rota).preencher('Observação', 'textarea', 'Obs revista').salvar_no_popup('Salvar').sucesso(
        'Conclusão do projeto registrada com sucesso.'
    )
    registro.refresh_from_db()
    assert registro.obs == 'Obs revista', 'a UI disse que editou, mas não persistiu'
    assert RegistroConclusaoProjeto.objects.filter(projeto=projeto).count() == 1, 'a edição criou um segundo registro'


def test_coordenador_finaliza_o_projeto_sem_pendencias(logado_projetos, projeto_em_execucao):
    """Feature 009: com a conclusão registrada e nada pendente, "Finalizar projeto" (confirm) fecha a execução e espera o monitor."""
    from projetos.models import ProjetoHistoricoDeEnvio

    execucao = projeto_em_execucao()
    sem_pendencias(execucao)
    conclusao_registrada(execucao)
    projeto = execucao.projeto
    tela = Tela(logado_projetos('coordenador_projeto')).ir(PROJETO.format(projeto.pk))

    clicar_em(tela, FINALIZAR_CONCLUSAO.format(projeto.pk))  # `.confirm`: o `logado` aceita
    tela.esperar().sucesso('Conclusão finalizada com sucesso.')
    projeto.refresh_from_db()
    assert projeto.data_finalizacao_conclusao is not None, 'a UI disse que finalizou, mas a data de finalização não foi gravada'
    assert ProjetoHistoricoDeEnvio.objects.filter(projeto=projeto, situacao=ProjetoHistoricoDeEnvio.FINALIZADO).exists()
    tela.clicar_aba('Conclusão').ver_texto('Aguardando parecer do monitor do projeto')


def test_projeto_com_pendencias_nao_finaliza(logado_projetos, projeto_em_execucao):
    """Com pendências a tela não oferece "Finalizar projeto", e a rota devolve para a aba "Pendências" sem gravar."""
    execucao = projeto_em_execucao()
    conclusao_registrada(execucao)
    projeto = execucao.projeto
    tela = Tela(logado_projetos('coordenador_projeto')).ir(PROJETO.format(projeto.pk))

    expect(tela.loc(f'//a[@href="{FINALIZAR_CONCLUSAO.format(projeto.pk)}"]')).to_have_count(0)
    tela.ir(FINALIZAR_CONCLUSAO.format(projeto.pk)).erro('O projeto não pode ser finalizado. Verifique as pendências.')
    projeto.refresh_from_db()
    assert projeto.data_finalizacao_conclusao is None, 'o projeto com pendências foi finalizado'


def test_estranho_nao_registra_nem_finaliza_a_conclusao(logado_projetos, projeto_em_execucao):
    """Quem não coordena o projeto: as duas rotas dão 403 — e a finalização, que grava por GET, não grava."""
    execucao = projeto_em_execucao()
    sem_pendencias(execucao)
    conclusao_registrada(execucao)
    projeto = execucao.projeto
    tela = Tela(logado_projetos('outro_coordenador'))

    assert (tela.buscar(REGISTRO_CONCLUSAO.format(projeto.pk)).status, tela.buscar(FINALIZAR_CONCLUSAO.format(projeto.pk)).status) == (403, 403)
    projeto.refresh_from_db()
    assert projeto.data_finalizacao_conclusao is None, 'uma rota que respondeu 403 finalizou o projeto'


def test_finalizar_sem_registro_de_conclusao_nao_quebra(logado_projetos, projeto_em_execucao):
    execucao = projeto_em_execucao()
    sem_pendencias(execucao)

    status = Tela(logado_projetos('coordenador_projeto')).buscar(FINALIZAR_CONCLUSAO.format(execucao.projeto.pk)).status
    assert status in (302, 403), f'finalizar sem registro de conclusão respondeu {status}'


# -------------------------------------------------------------------------- parecer do monitor


def test_monitor_emite_o_parecer_da_conclusao(logado_projetos, projeto_em_execucao):
    """Feature 010: Monitoramento → "Acompanhar Validação" → aba "Conclusão do Projeto" → "Emitir Parecer" (popup) conclui o projeto."""
    from projetos.models import Projeto

    execucao = projeto_em_execucao()
    registro = conclusao_registrada(execucao, finalizada=True)
    projeto = execucao.projeto
    tela = Tela(logado_projetos('coordenador_extensao')).ir(MONITORAMENTO)

    tela.ver_titulo('Monitoramento').linha(projeto.titulo)
    clicar_em(tela, VALIDAR_EXECUCAO.format(projeto.pk))  # "Acompanhar Validação"
    tela.clicar_aba('Conclusão do Projeto')
    clicar_em(tela, AVALIAR_CONCLUSAO.format(registro.pk))  # "Emitir Parecer"
    popup = popup_em(tela, AVALIAR_CONCLUSAO.format(registro.pk)).preencher('Observação', 'textarea', 'Obs sobre a finalização')
    popup.salvar_no_popup('Enviar').sucesso('Conclusão do projeto registrada com sucesso.')
    registro.refresh_from_db()
    assert (registro.dt_avaliacao, registro.obs_avaliador) == (datetime.date.today(), 'Obs sobre a finalização'), (
        'a UI disse que registrou o parecer, mas ele não persistiu'
    )
    assert registro.avaliador == vinculo('coordenador_extensao').relacionamento
    assert Projeto.objects.get(pk=projeto.pk).concluido, 'o parecer não concluiu o projeto'


@pytest.mark.parametrize(('papel', 'status'), [('gerente', 200), ('coordenador_projeto', 403), ('pre_avaliador', 403)])
def test_parecer_da_conclusao_e_do_monitor_ou_do_gerente(logado_projetos, projeto_em_execucao, papel, status):
    """O monitor é o Coordenador de Extensão; o coordenador do projeto e um Pré-Avaliador Sistêmico que não monitora recebem 403."""
    registro = conclusao_registrada(projeto_em_execucao(), finalizada=True)
    assert Tela(logado_projetos(papel)).buscar(AVALIAR_CONCLUSAO.format(registro.pk)).status == status


def test_monitor_so_emite_parecer_depois_da_finalizacao(logado_projetos, projeto_em_execucao):
    from projetos.models import Projeto

    execucao = projeto_em_execucao()
    registro = conclusao_registrada(execucao)  # registrada, NÃO finalizada
    rota = AVALIAR_CONCLUSAO.format(registro.pk)
    tela = Tela(logado_projetos('coordenador_extensao'))

    if tela.buscar(rota).status == 200:  # o defeito: o formulário abre antes da finalização
        tela.ir(rota).preencher('Observação', 'textarea', 'Parecer antecipado').clicar_botao('Enviar')
        tela.esperar()
    projeto = Projeto.objects.get(pk=execucao.projeto.pk)
    assert not projeto.concluido, 'o monitor concluiu um projeto que o coordenador ainda não finalizou'


# ----------------------------------------------------------------------- finalização sistêmica


def test_gerente_finaliza_o_projeto_de_forma_sistemica(logado_projetos, projeto_em_execucao):
    """ "Finalização sistêmica" (confirm) → motivo → o projeto em execução sai concluído, com o motivo no registro de conclusão."""
    from projetos.models import Projeto, RegistroConclusaoProjeto

    projeto = projeto_em_execucao().projeto
    motivo = f'Coordenador desligado da instituição {uuid4().hex[:8]}'
    tela = Tela(logado_projetos('gerente')).ir(PROJETO.format(projeto.pk))

    clicar_em(tela, FINALIZACAO_SISTEMICA.format(projeto.pk))
    tela.ver_titulo(f'Finalizar projeto de forma sistêmica - {projeto.titulo}')
    tela.preencher('Motivo da finalização sistêmica do projeto', 'textarea', motivo).clicar_botao('Salvar')
    tela.esperar().sucesso('Projeto finalizado com sucesso.')
    expect(tela.loc('//span[contains(@class, "status") and normalize-space(.)="Concluído"]').first).to_be_visible()
    projeto = Projeto.objects.get(pk=projeto.pk)
    assert (projeto.concluido, projeto.motivo_finalizacao_sistemica) == (True, motivo), 'a UI disse que finalizou, mas não persistiu'
    assert projeto.finalizacao_sistemica_em is not None
    registro = RegistroConclusaoProjeto.objects.get(projeto=projeto)
    assert (registro.dt_avaliacao, registro.obs_avaliador) == (datetime.date.today(), motivo)


@pytest.mark.parametrize(('papel', 'estado', 'status'), [('coordenador_extensao', 'execucao', 403), ('gerente', 'em_edicao', 403)])
def test_finalizacao_sistemica_negada(logado_projetos, projeto_em_execucao, projetos_seed, papel, estado, status):
    """Só o gerente, e só em projeto em execução (o em edição do seed não é)."""
    projeto = projeto_em_execucao().projeto if estado == 'execucao' else projetos_seed.projetos[estado]
    assert Tela(logado_projetos(papel)).buscar(FINALIZACAO_SISTEMICA.format(projeto.pk)).status == status


# ----------------------------------------------------------------------------- relatório


def test_coordenador_abre_o_relatorio_do_projeto(logado_projetos, projeto_em_execucao):
    """Submenu "Visualizar" → "Relatório" (``?html=1``) e o "Imprimir em PDF" dele (sob teste, o ``@documento`` devolve HTML)."""
    projeto = projeto_em_execucao().projeto
    tela = Tela(logado_projetos('coordenador_projeto')).ir(PROJETO.format(projeto.pk))

    tela.clicar_botao('Visualizar')
    expect(tela.loc(f'//a[@href="{RELATORIO.format(projeto.pk)}?html=1"]')).to_have_count(1)
    tela.ir(f'{RELATORIO.format(projeto.pk)}?html=1').ver_texto('IDENTIFICAÇÃO DO PROJETO').ver_texto('EQUIPE PARTICIPANTE').ver_texto(projeto.titulo)
    clicar_em(tela, RELATORIO.format(projeto.pk))  # "Imprimir em PDF"
    tela.ver_texto('RELATÓRIO PARCIAL DO PROJETO').ver_texto('UNIDADE PROPONENTE')
