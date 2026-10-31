"""Fluxo: registro dos gastos do plano de desembolso e a validação deles pelo monitor (features 006 e 007).

Para cada desembolso planejado, o coordenador registra em "Gerenciar Gasto" o que de fato foi
gasto — ou marca "Gasto não executado", que exige o motivo e grava valor zero. O monitor aprova,
reprova com justificativa ou cancela a avaliação na aba "Gastos" de "Validar Execução". É o
dinheiro do fomento: a regressão cara é o gasto sumir ou mudar de dono, e por isso as sondas de
objeto — o registro chega à view pela QUERYSTRING (``?registro_id``, ``?editar_registro_id``,
``?item_id``), a forma vulnerável de #17490.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest
from playwright.sync_api import expect

from djtools.e2e_fixtures import popup_em
from djtools.e2e_ui import Tela
from projetos.tests.e2e.conftest import clicar_em, vinculo

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

PROJETO = '/projetos/projeto/{}/'
ABA = 'Plano de Desembolso'
REGISTRO_GASTO = '/projetos/registro_gasto/{}/'
VALIDAR = '/projetos/validar_execucao_etapa/{}/'
REPROVAR_GASTO = '/projetos/reprovar_execucao_gasto/{}/'
CANCELAR_GASTO = '/projetos/cancelar_avaliacao_gasto/{}/'


def test_coordenador_registra_edita_e_exclui_o_gasto(logado_projetos, projeto_em_execucao):
    """ "Gerenciar Gasto" → Salvar (ano, mês e descrição vêm do desembolso) → editar pelo ícone → excluir pelo ícone."""
    from projetos.models import RegistroGasto

    execucao = projeto_em_execucao()
    desembolso = execucao.desembolso
    observacao = f'Compra na feira {uuid4().hex[:8]}'
    tela = Tela(logado_projetos('coordenador_projeto')).ir(PROJETO.format(execucao.projeto.pk))

    tela.clicar_aba(ABA)
    clicar_em(tela, REGISTRO_GASTO.format(desembolso.pk))
    tela.ver_texto('Adicionar Gasto').preencher_formulario(
        [('Quantidade', 'texto', '2'), ('Valor Unitário (R$)', 'texto', '150,00'), ('Observação', 'textarea', observacao)]
    )
    tela.clicar_botao('Salvar')
    tela.esperar().sucesso('Gasto registrado com sucesso.')
    registro = RegistroGasto.objects.filter(desembolso=desembolso, observacao=observacao).first()
    assert registro is not None, 'a UI disse que registrou, mas o gasto não persistiu'
    assert (registro.qtd, registro.valor_unitario, registro.ano, registro.mes) == (2, Decimal(150), desembolso.ano, desembolso.mes)

    # Os ícones da tabela são relativos (``?editar_registro_id=``): o literal da rota fica na constante.
    clicar_em(tela, f'?editar_registro_id={registro.pk}')
    tela.ver_texto(f'Editar Gasto - {registro}').preencher('Quantidade', 'texto', '3').clicar_botao('Salvar')
    tela.esperar().sucesso('Gasto registrado com sucesso.')
    registro.refresh_from_db()
    assert registro.qtd == 3, 'a UI disse que editou, mas não persistiu'

    clicar_em(tela, f'?registro_id={registro.pk}')  # `.icon-delete`: o `logado` aceita o confirm
    tela.esperar().sucesso('Registro excluído com sucesso.')
    assert not RegistroGasto.objects.filter(pk=registro.pk).exists(), 'a UI disse que excluiu, mas o gasto continua'


def test_coordenador_anexa_a_nota_fiscal_do_gasto_aprovado_sem_desaprova_lo(logado_projetos, projeto_em_execucao):
    """Gasto aprovado sem nota fiscal (#17507): a edição abre só com os arquivos, e salvar mantém a aprovação."""
    import datetime

    from projetos.tests.factories import RegistroGastoFactory

    execucao = projeto_em_execucao()
    hoje = datetime.date.today()
    registro = RegistroGastoFactory(desembolso=execucao.desembolso, aprovado=True, dt_avaliacao=hoje)
    tela = Tela(logado_projetos('coordenador_projeto')).ir(f'{REGISTRO_GASTO.format(execucao.desembolso.pk)}?editar_registro_id={registro.pk}')

    expect(tela.campo('Valor Unitário (R$)', 'texto')).to_have_count(0)
    tela.preencher('Nota Fiscal ou Cupom', 'arquivo', 'nota.pdf').clicar_botao('Salvar')
    tela.esperar().sucesso('Comprovante de gasto cadastrado com sucesso.')
    registro.refresh_from_db()
    assert bool(registro.arquivo), 'a UI disse que cadastrou, mas a nota fiscal não persistiu'
    assert (registro.aprovado, registro.dt_avaliacao) == (True, hoje), 'anexar a nota fiscal desaprovou o gasto'


def test_gasto_nao_executado_exige_o_motivo_e_grava_valor_zero(logado_projetos, projeto_em_execucao):
    """``RegistroGastoForm.clean``: sem "Observação" é recusado; com ela, o valor unitário vira R$ 0,00."""
    from projetos.models import RegistroGasto

    execucao = projeto_em_execucao()
    tela = Tela(logado_projetos('coordenador_projeto')).ir(REGISTRO_GASTO.format(execucao.desembolso.pk))

    tela.preencher('Gasto não executado', 'checkbox', 'marcar').clicar_botao('Salvar')
    tela.esperar().erro('Informe o motivo pelo qual o desembolso não foi executado.')
    assert not RegistroGasto.objects.filter(desembolso=execucao.desembolso).exists(), 'o formulário recusou, mas o gasto foi gravado'

    tela.preencher('Gasto não executado', 'checkbox', 'marcar').preencher('Observação', 'textarea', 'O fornecedor não entregou.')
    tela.clicar_botao('Salvar')
    tela.esperar().sucesso('Gasto registrado com sucesso.')
    registro = RegistroGasto.objects.get(desembolso=execucao.desembolso)
    assert (registro.valor_unitario, registro.observacao) == (Decimal(0), 'O fornecedor não entregou.'), 'o gasto não executado não zerou o valor'


def test_monitor_aprova_cancela_e_reprova_o_gasto(logado_projetos, projeto_em_execucao):
    """Na aba "Gastos" de "Validar Execução": Aprovar → Cancelar Avaliação → Não Aprovar (popup com justificativa)."""
    from projetos.tests.factories import RegistroGastoFactory

    execucao = projeto_em_execucao()
    registro = RegistroGastoFactory(desembolso=execucao.desembolso)
    tela = Tela(logado_projetos('coordenador_extensao')).ir(VALIDAR.format(execucao.projeto.pk))

    tela.clicar_aba('Gastos').linha(registro.descricao).clicar_botao('Aprovar')  # `.confirm`
    tela.esperar().sucesso('Gasto validado com sucesso.')
    registro.refresh_from_db()
    assert (registro.aprovado, registro.avaliador) == (True, vinculo('coordenador_extensao').relacionamento), 'a aprovação não persistiu'

    tela.clicar_aba('Gastos')
    clicar_em(tela, CANCELAR_GASTO.format(registro.pk))
    tela.esperar().sucesso('Avaliação do gasto cancelada com sucesso.')
    registro.refresh_from_db()
    assert (registro.aprovado, registro.dt_avaliacao, registro.avaliador) == (False, None, None), 'o cancelamento não persistiu'

    tela.clicar_aba('Gastos')
    clicar_em(tela, REPROVAR_GASTO.format(registro.pk))
    popup = popup_em(tela, REPROVAR_GASTO.format(registro.pk)).preencher('Justificativa da Não Aprovação', 'textarea', 'Nota fiscal ilegível.')
    popup.salvar_no_popup('Enviar').sucesso('Gasto avaliado com sucesso.')
    registro.refresh_from_db()
    assert (registro.aprovado, registro.justificativa_reprovacao) == (False, 'Nota fiscal ilegível.'), 'a reprovação não persistiu'
    assert registro.dt_avaliacao is not None, 'reprovado, o gasto continuou sem data de avaliação'


def test_estranho_nao_gerencia_o_gasto(logado_projetos, projeto_em_execucao):
    """Coordenador de OUTRO projeto: "Gerenciar Gasto" e a exclusão por ``?registro_id`` no desembolso alheio dão 403, e o gasto fica."""
    from projetos.models import RegistroGasto
    from projetos.tests.factories import RegistroGastoFactory

    execucao = projeto_em_execucao()
    registro = RegistroGastoFactory(desembolso=execucao.desembolso)
    tela = Tela(logado_projetos('outro_coordenador'))

    rota = REGISTRO_GASTO.format(execucao.desembolso.pk)
    assert (tela.buscar(rota).status, tela.buscar(f'{rota}?registro_id={registro.pk}').status) == (403, 403)
    assert RegistroGasto.objects.filter(pk=registro.pk).exists(), 'o gasto foi apagado por uma rota que respondeu 403'


@pytest.mark.parametrize('papel', ['coordenador_projeto', 'gerente'])
def test_so_o_monitor_reprova_o_gasto(logado_projetos, projeto_em_execucao, papel):
    """``reprovar_execucao_gasto`` é só do monitor — nem o coordenador nem o Gerente Sistêmico (que CANCELA avaliação) reprovam."""
    from projetos.tests.factories import RegistroGastoFactory

    registro = RegistroGastoFactory(desembolso=projeto_em_execucao().desembolso)

    assert Tela(logado_projetos(papel)).buscar(REPROVAR_GASTO.format(registro.pk)).status == 403
    registro.refresh_from_db()
    assert registro.dt_avaliacao is None, 'o gasto foi avaliado por quem recebeu 403'


def test_coordenador_nao_cancela_a_avaliacao_do_gasto(logado_projetos, projeto_em_execucao):
    import datetime

    from projetos.tests.factories import RegistroGastoFactory

    registro = RegistroGastoFactory(desembolso=projeto_em_execucao().desembolso, aprovado=True, dt_avaliacao=datetime.date.today())

    assert Tela(logado_projetos('coordenador_projeto')).buscar(CANCELAR_GASTO.format(registro.pk)).status == 403
    registro.refresh_from_db()
    assert registro.aprovado, 'a avaliação do gasto foi cancelada por quem recebeu 403'


def test_coordenador_nao_apaga_gasto_de_projeto_alheio(logado_projetos, projeto_em_execucao):
    from projetos.models import RegistroGasto
    from projetos.tests.factories import RegistroGastoFactory

    proprio = projeto_em_execucao(sufixo='proprio')
    alheio = RegistroGastoFactory(desembolso=projeto_em_execucao(coordenador='outro_coordenador', sufixo='alheio').desembolso)

    resposta = Tela(logado_projetos('coordenador_projeto')).buscar(f'{REGISTRO_GASTO.format(proprio.desembolso.pk)}?registro_id={alheio.pk}')
    assert RegistroGasto.objects.filter(pk=alheio.pk).exists(), 'o coordenador apagou o gasto de projeto alheio'
    assert resposta.status in (403, 404), f'respondeu {resposta.status} a um pedido para apagar gasto de projeto alheio'


def test_coordenador_nao_edita_gasto_de_projeto_alheio(logado_projetos, projeto_em_execucao):
    """``?editar_registro_id`` de gasto alheio no desembolso PRÓPRIO dá 404 — e o gasto não muda de desembolso.

    O gasto é buscado no desembolso da URL, como na exclusão por ``?registro_id`` (#17564).
    """
    from projetos.models import RegistroGasto
    from projetos.tests.factories import RegistroGastoFactory

    proprio = projeto_em_execucao(sufixo='proprio')
    alheio = RegistroGastoFactory(desembolso=projeto_em_execucao(coordenador='outro_coordenador', sufixo='alheio').desembolso)

    resposta = Tela(logado_projetos('coordenador_projeto')).buscar(f'{REGISTRO_GASTO.format(proprio.desembolso.pk)}?editar_registro_id={alheio.pk}')
    assert resposta.status == 404, f'respondeu {resposta.status} a um pedido para editar gasto de projeto alheio'
    assert RegistroGasto.objects.filter(pk=alheio.pk, desembolso=alheio.desembolso).exists(), 'o gasto alheio mudou de desembolso'


def test_gasto_nao_muda_de_desembolso_pela_edicao(logado_projetos, projeto_em_execucao):
    """Gasto do PRÓPRIO projeto, aberto pela URL de outro desembolso: 404 — salvar ali o moveria de desembolso (#17564)."""
    from projetos.models import RegistroGasto
    from projetos.tests.factories import DesembolsoFactory, RegistroGastoFactory

    execucao = projeto_em_execucao()
    outro = DesembolsoFactory(item=execucao.item, mes=2)
    gasto = RegistroGastoFactory(desembolso=outro)
    tela = Tela(logado_projetos('coordenador_projeto'))

    rota = f'{REGISTRO_GASTO.format(execucao.desembolso.pk)}?editar_registro_id={gasto.pk}'
    assert tela.buscar(rota).status == 404
    assert RegistroGasto.objects.filter(pk=gasto.pk, desembolso=outro).exists(), 'o gasto mudou de desembolso'


def test_coordenador_nao_exclui_gasto_aprovado(logado_projetos, projeto_em_execucao):
    """``?registro_id`` de gasto já aprovado pelo monitor é recusado, como no `pesquisa` (#17565)."""
    import datetime

    from projetos.models import RegistroGasto
    from projetos.tests.factories import RegistroGastoFactory

    execucao = projeto_em_execucao()
    gasto = RegistroGastoFactory(desembolso=execucao.desembolso, aprovado=True, dt_avaliacao=datetime.date.today())

    tela = Tela(logado_projetos('coordenador_projeto')).ir(f'{REGISTRO_GASTO.format(execucao.desembolso.pk)}?registro_id={gasto.pk}')
    tela.ver_texto('Não é possível excluir um registro de gasto avaliado.')
    assert RegistroGasto.objects.filter(pk=gasto.pk).exists(), 'o gasto aprovado foi excluído'


def test_monitor_so_valida_o_projeto_que_monitora(logado_projetos, projeto_em_execucao):
    from projetos.tests.factories import RegistroExecucaoEtapaFactory, RegistroGastoFactory

    monitorado = projeto_em_execucao(sufixo='monitorado')
    alheio = projeto_em_execucao(coordenador='outro_coordenador', monitor='pre_avaliador', sufixo='alheio')
    atividade = RegistroExecucaoEtapaFactory(etapa=alheio.etapa)
    gasto = RegistroGastoFactory(desembolso=alheio.desembolso)
    tela = Tela(logado_projetos('coordenador_extensao'))

    rota = VALIDAR.format(monitorado.projeto.pk)
    tela.buscar(f'{rota}?registro_id={atividade.pk}')
    tela.buscar(f'{rota}?item_id={gasto.pk}')
    atividade.refresh_from_db()
    gasto.refresh_from_db()
    assert (atividade.aprovado, gasto.aprovado) == (False, False), (
        f'o monitor de outro projeto aprovou a atividade ({atividade.aprovado}) e o gasto ({gasto.aprovado}) do projeto alheio'
    )
