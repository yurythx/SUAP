"""Fluxo: as transições de ciclo de vida do projeto — cancelar, inativar/reativar, reabrir, devolver e as alterações pedidas na execução.

* **Cancelamento** — o coordenador pede ("Cancelar Projeto"), o Coordenador de Extensão do campus
  (ou o gerente) avalia em "Cancelamentos"; o parecer favorável cancela o projeto e pode aprovar o
  próximo da lista de espera.
* **Inativar / reativar / reabrir** — do Gerente Sistêmico: inativa um projeto em execução,
  reativa o inativado, reabre o finalizado (desfazendo a conclusão).
* **Devolver** — o Coordenador de Extensão devolve ao coordenador o projeto enviado, ainda na
  inscrição; "Movimentação" mostra o histórico.
* **Alterações pedidas na execução** — período de execução (o Coordenador de Extensão do campus
  defere ou indefere) e interesse por custeio (o gerente avalia, no admin).

As sondas: quem pede o cancelamento é só o coordenador, quem avalia é o papel de extensão; o
Coordenador de Extensão não avalia alteração nem cancelamento de outro campus (#17520); o POST
forjado de devolução é recusado (#17515); e as rotas laterais de leitura do projeto fecham para
quem a tela do projeto manda para a consulta pública (#17516).
"""

from __future__ import annotations

import datetime
from typing import TYPE_CHECKING
from urllib.parse import urlencode
from uuid import uuid4

import pytest
from playwright.sync_api import expect

from djtools.e2e_fixtures import popup_em
from djtools.e2e_ui import Tela
from projetos.tests.e2e.conftest import PAPEIS, clicar_em, outra_uo, vinculo

if TYPE_CHECKING:
    from playwright.sync_api import APIResponse

    from projetos.models import HistoricoInteresseCusteioProjeto, Projeto, ProjetoCancelado

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

PROJETO = '/projetos/projeto/{}/'
CANCELAR = '/projetos/cancelar_projeto/{}/'
CANCELAMENTOS = '/projetos/solicitacoes_de_cancelamento/'
AVALIAR_CANCELAMENTO = '/projetos/avaliar_cancelamento_projeto/{}/'
INATIVAR = '/projetos/inativar_projeto/{}/'
REATIVAR = '/projetos/reativar_projeto/{}/'
REABRIR = '/projetos/reabrir_projeto/{}/'
HISTORICO = '/projetos/gerenciar_historico_projeto/{}/'
ALTERACOES_DATA = '/projetos/ver_alteracoes_data/{}/'
AVALIAR_ALTERACAO = '/projetos/avaliar_alteracao_datas/{}/{}/'
ALTERACOES_CUSTEIO = '/projetos/ver_alteracoes_interesse_custeio/{}/'
AVALIAR_CUSTEIO = '/projetos/avaliar_historico_custeio/{}/'
PEDIDOS_DE_CUSTEIO = '/admin/projetos/historicointeressecusteioprojeto/'
RELATORIO = '/projetos/relatorio_projeto/{}/'

DEFERIR, INDEFERIR = 1, 2  # a opção no caminho de `avaliar_alteracao_datas`
PARECER = 'Parecer sobre a devolução do projeto'
DEVOLVIDO_POR = '//h4[contains(normalize-space(.), "Devolvido por")]'  # o evento da linha do tempo, com o operador


def postar_formulario(tela: Tela, rota: str, dados: dict[str, str]) -> APIResponse:
    """POST de formulário pela sessão do browser, com o token CSRF dela — para forjar o envio que a tela não oferece.

    ``Tela.postar`` só serve a view ``@csrf_exempt``; aqui o token vem do cookie ``csrftoken``
    (HttpOnly para o JavaScript da página, mas legível pelo contexto do Playwright).
    """
    token = next(cookie['value'] for cookie in tela.pagina.context.cookies() if cookie['name'] == 'csrftoken')
    return tela.pagina.request.post(rota, form={'csrfmiddlewaretoken': token, **dados}, max_redirects=0)


# ------------------------------------------------------------------------------ cancelamento


def test_coordenador_solicita_o_cancelamento(logado_projetos, projeto_em_execucao):
    """ "Cancelar Projeto" (confirm) → justificativa: o pedido fica aguardando parecer, e o botão some (um pedido por projeto)."""
    from projetos.models import ProjetoCancelado

    projeto = projeto_em_execucao().projeto
    justificativa = f'A escola parceira encerrou as atividades {uuid4().hex[:8]}'
    tela = Tela(logado_projetos('coordenador_projeto')).ir(PROJETO.format(projeto.pk))

    clicar_em(tela, CANCELAR.format(projeto.pk))
    tela.ver_titulo('Cancelar Projeto').preencher('Justificativa do Cancelamento', 'textarea', justificativa).clicar_botao('Salvar')
    tela.esperar().sucesso('Solicitação encaminhada para análise.')
    pedido = ProjetoCancelado.objects.filter(projeto=projeto, justificativa_cancelamento=justificativa).first()
    assert pedido is not None, 'a UI disse que encaminhou, mas o pedido de cancelamento não persistiu'
    assert (pedido.data_avaliacao, pedido.cancelado) == (None, False)

    tela.ir(PROJETO.format(projeto.pk))
    expect(tela.loc(f'//a[@href="{CANCELAR.format(projeto.pk)}"]')).to_have_count(0)
    assert tela.buscar(CANCELAR.format(projeto.pk)).status == 403, 'um segundo pedido de cancelamento foi aceito'


@pytest.mark.parametrize('papel', ['outro_coordenador', 'gerente'])
def test_so_o_coordenador_pede_cancelamento(logado_projetos, projeto_em_execucao, papel):
    """``Projeto.pode_cancelar_projeto`` exige ser o responsável — nem o gerente pede pelo coordenador."""
    projeto = projeto_em_execucao().projeto
    assert Tela(logado_projetos(papel)).buscar(CANCELAR.format(projeto.pk)).status == 403


@pytest.fixture
def pedido_de_cancelamento(projeto_em_execucao) -> ProjetoCancelado:
    """Pedido do coordenador num projeto em execução do CZN, aguardando parecer."""
    from projetos.tests.factories import ProjetoCanceladoFactory

    return ProjetoCanceladoFactory(projeto=projeto_em_execucao().projeto)


def test_coordenador_de_extensao_cancela_e_aprova_o_proximo(logado_projetos, pedido_de_cancelamento, projeto_enviado_em):
    """ "Cancelamentos" → "Avaliar": parecer favorável com "Aprovar próximo projeto?" — o primeiro da lista de espera do campus é aprovado."""
    from projetos.models import Projeto

    cancelado = pedido_de_cancelamento.projeto
    espera = projeto_enviado_em('divulgado', edital=cancelado.edital, sufixo='lista de espera', pre_aprovado=True, classificacao=2)
    tela = Tela(logado_projetos('coordenador_extensao')).ir(CANCELAMENTOS)

    tela.ver_titulo('Projetos com Solicitações de Cancelamento').linha(cancelado.titulo).ver_texto('Aguardando avaliação')
    clicar_em(tela, AVALIAR_CANCELAMENTO.format(pedido_de_cancelamento.pk))
    tela.ver_titulo('Avaliar Cancelamento do Projeto').preencher_formulario(
        [
            ('Parecer do Avaliador', 'textarea', 'Parecer favorável ao cancelamento'),
            ('Cancelar projeto?', 'lista', 'Sim'),
            ('Aprovar próximo projeto?', 'lista', 'Sim'),
        ]
    )
    tela.clicar_botao('Salvar')
    tela.esperar().sucesso('Cancelamento avaliado com sucesso.')
    pedido_de_cancelamento.refresh_from_db()
    assert (pedido_de_cancelamento.cancelado, pedido_de_cancelamento.proximo_projeto_id) == (True, espera.pk), (
        'a UI disse que avaliou, mas o parecer não persistiu'
    )
    assert pedido_de_cancelamento.avaliador == vinculo('coordenador_extensao').relacionamento
    assert Projeto.objects.get(pk=cancelado.pk).cancelado, 'o parecer favorável não cancelou o projeto'
    assert Projeto.objects.get(pk=espera.pk).aprovado, 'o próximo da lista de espera não foi aprovado'


def test_lista_de_cancelamentos_e_do_campus(logado_projetos, projeto_em_execucao):
    """O gerente vê o pedido de outro campus; o Coordenador de Extensão do CZN, não (``solicitacoes_de_cancelamento`` filtra pelo campus)."""
    from projetos.tests.factories import ProjetoCanceladoFactory

    pedido = ProjetoCanceladoFactory(projeto=projeto_em_execucao(uo=outra_uo()).projeto)
    avaliar = f'//a[@href="{AVALIAR_CANCELAMENTO.format(pedido.pk)}"]'

    expect(Tela(logado_projetos('gerente')).ir(CANCELAMENTOS).loc(avaliar)).to_have_count(1)
    expect(Tela(logado_projetos('coordenador_extensao')).ir(CANCELAMENTOS).loc(avaliar)).to_have_count(0)


def test_coordenador_do_projeto_nao_avalia_cancelamento(logado_projetos, pedido_de_cancelamento):
    tela = Tela(logado_projetos('coordenador_projeto'))
    assert (tela.buscar(CANCELAMENTOS).status, tela.buscar(AVALIAR_CANCELAMENTO.format(pedido_de_cancelamento.pk)).status) == (403, 403)


def test_coordenador_de_extensao_nao_avalia_cancelamento_de_outro_campus(logado_projetos, projeto_em_execucao):
    from projetos.tests.factories import ProjetoCanceladoFactory

    pedido = ProjetoCanceladoFactory(projeto=projeto_em_execucao(uo=outra_uo()).projeto)
    status = Tela(logado_projetos('coordenador_extensao')).buscar(AVALIAR_CANCELAMENTO.format(pedido.pk)).status
    assert status == 403, f'o Coordenador de Extensão abriu a avaliação do cancelamento de outro campus (status {status})'


# --------------------------------------------------------------- inativar, reativar, reabrir


def test_gerente_inativa_e_reativa_o_projeto(logado_projetos, projeto_em_execucao):
    """ "Inativar Projeto" → motivo → inativado; "Reativar Projeto" (confirm, grava por GET) → volta à execução."""
    from projetos.models import Projeto, ProjetoHistoricoDeEnvio

    projeto = projeto_em_execucao().projeto
    motivo = f'Coordenador afastado sem substituto {uuid4().hex[:8]}'
    tela = Tela(logado_projetos('gerente')).ir(PROJETO.format(projeto.pk))

    clicar_em(tela, INATIVAR.format(projeto.pk))
    tela.ver_titulo(f'Inativar Projeto - {projeto.titulo}').preencher('Motivo da Inativação', 'textarea', motivo).clicar_botao('Salvar')
    tela.esperar().sucesso('Projeto inativado com sucesso.')
    inativado = Projeto.objects.get(pk=projeto.pk)
    assert (inativado.inativado, inativado.motivo_inativacao) == (True, motivo), 'a UI disse que inativou, mas não persistiu'
    assert inativado.inativado_por == vinculo('gerente').relacionamento

    clicar_em(tela, REATIVAR.format(projeto.pk))
    tela.esperar().sucesso('Projeto reativado com sucesso.')
    assert not Projeto.objects.get(pk=projeto.pk).inativado, 'a UI disse que reativou, mas o projeto continua inativado'
    assert ProjetoHistoricoDeEnvio.objects.filter(projeto=projeto, parecer_devolucao='Projeto reativado').exists()


@pytest.mark.parametrize('papel', ['coordenador_extensao', 'coordenador_projeto'])
def test_inativar_e_reativar_sao_do_gerente(logado_projetos, projeto_em_execucao, papel):
    """Nem o Coordenador de Extensão (que tem ``change_projeto``, a permissão da reativação) inativa ou reativa; a reativação por GET não grava."""
    from projetos.models import Projeto

    ativo = projeto_em_execucao(sufixo='ativo').projeto
    inativo = projeto_em_execucao(sufixo='inativo', inativado=True).projeto
    tela = Tela(logado_projetos(papel))

    assert (tela.buscar(INATIVAR.format(ativo.pk)).status, tela.buscar(REATIVAR.format(inativo.pk)).status) == (403, 403)
    assert Projeto.objects.get(pk=inativo.pk).inativado, 'uma rota que respondeu 403 reativou o projeto'


@pytest.fixture
def projeto_finalizado(projeto_em_execucao) -> Projeto:
    """Projeto concluído: conclusão avaliada e finalizada — o que a reabertura desfaz."""
    from projetos.models import Projeto
    from projetos.tests.factories import RegistroConclusaoProjetoFactory

    projeto = projeto_em_execucao().projeto
    RegistroConclusaoProjetoFactory(projeto=projeto)
    Projeto.objects.filter(pk=projeto.pk).update(data_finalizacao_conclusao=datetime.datetime.now(), concluido=True)
    return Projeto.objects.get(pk=projeto.pk)


def test_gerente_reabre_o_projeto_finalizado(logado_projetos, projeto_finalizado):
    """ "Reabrir Projeto" (confirm) → parecer: a finalização e o parecer do monitor são desfeitos."""
    from projetos.models import ProjetoHistoricoDeEnvio, RegistroConclusaoProjeto

    projeto = projeto_finalizado
    tela = Tela(logado_projetos('gerente')).ir(PROJETO.format(projeto.pk))

    clicar_em(tela, REABRIR.format(projeto.pk))
    tela.ver_titulo(f'Reabertura do Projeto: {projeto.titulo}').preencher(PARECER, 'textarea', 'Relatório final incompleto').clicar_botao('Salvar')
    tela.esperar().sucesso('Reabertura do projeto realizada com sucesso.')
    projeto.refresh_from_db()
    assert (projeto.data_finalizacao_conclusao, projeto.concluido) == (None, False), 'a UI disse que reabriu, mas o projeto continua finalizado'
    assert RegistroConclusaoProjeto.objects.get(projeto=projeto).dt_avaliacao is None
    assert ProjetoHistoricoDeEnvio.objects.filter(projeto=projeto, situacao=ProjetoHistoricoDeEnvio.REBAERTO).exists()


def test_reabrir_e_do_gerente(logado_projetos, projeto_finalizado):
    assert Tela(logado_projetos('coordenador_extensao')).buscar(REABRIR.format(projeto_finalizado.pk)).status == 403


# ------------------------------------------------------------------------ devolução e histórico


def test_coordenador_de_extensao_devolve_o_projeto_enviado(logado_projetos, projeto_enviado_em):
    """ "Devolver Projeto" com o edital em inscrição: o projeto volta à edição e a "Movimentação" registra a devolução.

    O coordenador vê a devolução e a justificativa, mas não quem devolveu (só pré-avaliador e gerente veem o operador).
    """
    from projetos.models import Projeto, ProjetoHistoricoDeEnvio

    projeto = projeto_enviado_em('inscricao')
    justificativa = f'Faltou detalhar a metodologia {uuid4().hex[:8]}'
    tela = Tela(logado_projetos('coordenador_extensao')).ir(PROJETO.format(projeto.pk))

    clicar_em(tela, HISTORICO.format(projeto.pk))  # "Devolver Projeto"
    tela.preencher(PARECER, 'textarea', justificativa).clicar_botao('Salvar')
    tela.esperar().sucesso('Devolução do projeto registrada com sucesso.')
    expect(tela.loc(DEVOLVIDO_POR)).to_contain_text('Coordenador Extensão E2E')
    assert Projeto.objects.get(pk=projeto.pk).data_conclusao_planejamento is None, 'a UI disse que devolveu, mas o projeto continua enviado'
    assert ProjetoHistoricoDeEnvio.objects.filter(
        projeto=projeto, situacao=ProjetoHistoricoDeEnvio.DEVOLVIDO, parecer_devolucao=justificativa
    ).exists()

    tela = Tela(logado_projetos('coordenador_projeto')).ir(PROJETO.format(projeto.pk))
    tela.ver_texto('Atenção: Projeto Devolvido.').ver_texto(justificativa)
    tela.ir(HISTORICO.format(projeto.pk)).ver_texto(justificativa)
    expect(tela.loc(DEVOLVIDO_POR)).to_have_count(0)


def test_devolucao_por_post_sem_a_tela(logado_projetos, projeto_enviado_em):
    """Controle positivo de ``postar_formulario``: o mesmo POST que a sonda abaixo forja, feito por quem PODE devolver, devolve."""
    from projetos.models import Projeto

    projeto = projeto_enviado_em('inscricao')
    resposta = postar_formulario(Tela(logado_projetos('coordenador_extensao')), HISTORICO.format(projeto.pk), {'parecer_devolucao': 'Devolvido'})

    assert resposta.status == 302, f'o POST de devolução não foi aceito (status {resposta.status})'
    assert Projeto.objects.get(pk=projeto.pk).data_conclusao_planejamento is None


def test_estranho_nao_devolve_projeto_por_post_forjado(logado_projetos, projeto_em_execucao):
    from projetos.models import Projeto

    projeto = projeto_em_execucao().projeto
    resposta = postar_formulario(Tela(logado_projetos('outro_coordenador')), HISTORICO.format(projeto.pk), {'parecer_devolucao': 'Forjado'})

    depois = Projeto.objects.get(pk=projeto.pk)
    assert (resposta.status, depois.aprovado, depois.data_conclusao_planejamento is not None) == (403, True, True), (
        f'POST forjado: status {resposta.status}; o projeto em execução ficou aprovado={depois.aprovado}, '
        f'enviado={depois.data_conclusao_planejamento is not None}'
    )


# ------------------------------------------------------------- alteração do período de execução


def test_coordenador_de_extensao_defere_e_indefere_alteracoes_de_datas(logado_projetos, projeto_em_execucao):
    """ "Alterações do Período de Execução": "Deferir" (confirm, grava por GET) aplica as novas datas; "Indeferir" pede justificativa."""
    from projetos.models import HistoricoAlteracaoPeriodoProjeto, Projeto
    from projetos.tests.factories import HistoricoAlteracaoPeriodoProjetoFactory

    projeto = projeto_em_execucao().projeto
    deferido, indeferido = (
        HistoricoAlteracaoPeriodoProjetoFactory(projeto=projeto, vinculo_registrado_por=vinculo('coordenador_projeto')) for _ in '12'
    )
    tela = Tela(logado_projetos('coordenador_extensao')).ir(PROJETO.format(projeto.pk))

    clicar_em(tela, ALTERACOES_DATA.format(projeto.pk))
    tela.ver_titulo('Alterações no Período de Execução do Projeto')
    clicar_em(tela, AVALIAR_ALTERACAO.format(deferido.pk, DEFERIR))
    tela.esperar().sucesso('Alteração deferida com sucesso.')
    deferido.refresh_from_db()
    assert (deferido.aceito, deferido.validado_por) == (True, vinculo('coordenador_extensao')), 'a UI disse que deferiu, mas não persistiu'
    assert Projeto.objects.get(pk=projeto.pk).inicio_execucao == deferido.novo_inicio_execucao, 'o deferimento não aplicou o novo período'

    clicar_em(tela, AVALIAR_ALTERACAO.format(indeferido.pk, INDEFERIR))
    tela.ver_titulo('Avaliar solicitação de alteração das datas do projeto').preencher('Justificativa', 'textarea', 'Prazo do edital não permite')
    tela.clicar_botao('Enviar')
    tela.esperar().sucesso('Alteração indeferida com sucesso.')
    assert HistoricoAlteracaoPeriodoProjeto.objects.filter(
        pk=indeferido.pk, aceito=False, justificativa_validacao='Prazo do edital não permite'
    ).exists()


@pytest.mark.parametrize(
    ('papel', 'outro_campus', 'status'),
    [
        ('gerente', True, 200),
        # Papel LOCAL (decisão 42): aqui a view confere o campus (`mesmo_campus`).
        ('coordenador_extensao', True, 403),
        ('coordenador_projeto', False, 403),
    ],
)
def test_avaliar_alteracao_de_datas_por_papel(logado_projetos, projeto_em_execucao, papel, outro_campus, status):
    """Sonda pela opção "Indeferir", que no GET só abre o formulário (o "Deferir" grava por GET)."""
    from projetos.tests.factories import HistoricoAlteracaoPeriodoProjetoFactory

    projeto = projeto_em_execucao(uo=outra_uo() if outro_campus else None).projeto
    pedido = HistoricoAlteracaoPeriodoProjetoFactory(projeto=projeto, vinculo_registrado_por=vinculo('coordenador_projeto'))
    assert Tela(logado_projetos(papel)).buscar(AVALIAR_ALTERACAO.format(pedido.pk, INDEFERIR)).status == status


def test_alteracao_ja_avaliada_nao_se_reavalia(logado_projetos, projeto_em_execucao):
    from projetos.tests.factories import HistoricoAlteracaoPeriodoProjetoFactory

    pedido = HistoricoAlteracaoPeriodoProjetoFactory(projeto=projeto_em_execucao().projeto, aceito=True, validado_em=datetime.datetime.now())
    assert Tela(logado_projetos('coordenador_extensao')).buscar(AVALIAR_ALTERACAO.format(pedido.pk, DEFERIR)).status == 403


# --------------------------------------------------------------------- interesse por custeio


@pytest.fixture
def pedido_de_custeio(projeto_em_execucao) -> HistoricoInteresseCusteioProjeto:
    """O coordenador pediu para passar a ter interesse no custeio (cartão pesquisador) do projeto em execução."""
    from projetos.tests.factories import HistoricoInteresseCusteioProjetoFactory

    projeto = projeto_em_execucao(tem_interesse_cartao_pesquisador=False).projeto
    return HistoricoInteresseCusteioProjetoFactory(projeto=projeto, cadastrado_por=vinculo('coordenador_projeto'))


def test_gerente_defere_o_interesse_por_custeio(logado_projetos, pedido_de_custeio):
    """ "Alterações no Interesse por Custeio" (admin) → "Avaliar" (popup): deferido, o projeto passa a ter interesse; o coordenador vê o resultado."""
    from projetos.models import Projeto

    projeto = pedido_de_custeio.projeto
    tela = Tela(logado_projetos('gerente')).ir(f'{PEDIDOS_DE_CUSTEIO}?{urlencode({"q": projeto.titulo})}')

    clicar_em(tela, AVALIAR_CUSTEIO.format(pedido_de_custeio.pk))
    popup = popup_em(tela, AVALIAR_CUSTEIO.format(pedido_de_custeio.pk)).preencher_formulario(
        [('Aceitar solicitação?', 'lista', 'Sim'), ('Justificativa', 'texto', 'Há recurso de custeio no edital')]
    )
    popup.salvar_no_popup('Salvar').sucesso('Solicitação avaliada com sucesso.')
    pedido_de_custeio.refresh_from_db()
    assert (pedido_de_custeio.aceito, pedido_de_custeio.avaliado_por) == (True, vinculo('gerente')), 'a UI disse que avaliou, mas não persistiu'
    assert Projeto.objects.get(pk=projeto.pk).tem_interesse_cartao_pesquisador, 'o deferimento não mudou o interesse do projeto'

    tela = Tela(logado_projetos('coordenador_projeto')).ir(PROJETO.format(projeto.pk))
    clicar_em(tela, ALTERACOES_CUSTEIO.format(projeto.pk))
    tela.ver_titulo('Alterações no Interesse por Custeio').linha(pedido_de_custeio.justificativa).ver_texto('Há recurso de custeio no edital')


def test_interesse_por_custeio_e_avaliado_pelo_gerente_uma_vez(logado_projetos, pedido_de_custeio):
    """O Coordenador de Extensão não avalia; e o pedido já avaliado não reabre nem para o gerente."""
    from projetos.models import HistoricoInteresseCusteioProjeto

    rota = AVALIAR_CUSTEIO.format(pedido_de_custeio.pk)
    assert Tela(logado_projetos('coordenador_extensao')).buscar(rota).status == 403
    HistoricoInteresseCusteioProjeto.objects.filter(pk=pedido_de_custeio.pk).update(aceito=False, avaliado_em=datetime.datetime.now())
    assert Tela(logado_projetos('gerente')).buscar(rota).status == 403


# ------------------------------------------------------------ leituras laterais do projeto


@pytest.mark.parametrize('rota', [f'{RELATORIO}?html=1', HISTORICO, ALTERACOES_DATA, ALTERACOES_CUSTEIO])
@pytest.mark.parametrize('papel', ['aluno', 'outro_coordenador'])
def test_estranho_nao_le_o_projeto_pelas_rotas_laterais(logado_projetos, projeto_em_execucao, rota, papel):
    projeto = projeto_em_execucao().projeto
    resposta = Tela(logado_projetos(papel)).buscar(rota.format(projeto.pk))
    matricula = PAPEIS['coordenador_projeto'] in resposta.text()
    assert resposta.status in (302, 403), (
        f'{papel} leu {rota.format(projeto.pk)} de um projeto alheio (status {resposta.status}; matrícula do coordenador na página: {matricula})'
    )
