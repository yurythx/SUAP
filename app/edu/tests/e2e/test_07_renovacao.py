"""Fluxo 008: renovação de matrícula — configuração, pedido do aluno e processamento.

Sétimo elo, e o único do módulo que envolve os três papéis em sequência dentro do mesmo
fluxo: a secretaria abre a janela de renovação, o **aluno** escolhe os componentes do
próximo período e a secretaria processa os pedidos, gerando as matrículas em diário do
período seguinte. É também o único ponto em que o teste autentica como aluno.

A janela de renovação é datada: a configuração vale de 21/07 a 21/07/2019 e o
processamento acontece em 22/07 — por isso o relógio anda dentro dos testes.
"""

from uuid import uuid4

import pytest
from playwright.sync_api import expect

from djtools.e2e_ui import Tela
from djtools.e2e_fixtures import abrir_popup, escolher_autocomplete, mensagem_de_sucesso

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

DATA = '21/07/2019'
MATRICULA_ALUNO = '20191101010001'


@pytest.fixture
def sufixo():
    return uuid4().hex[:6].upper()


@pytest.fixture
def turmas_2019_2(seed_periodo_fechado):
    """Turmas de 2019.2 do curso 10101 — o destino dos pedidos de renovação.

    Geradas por ORM (mesma chamada do replay da funcionalidade 008) porque quem cobre o
    assistente de geração pela interface é o módulo 03.
    """
    from comum.models import Ano
    from edu.models import (
        CalendarioAcademico,
        ComponenteCurricular,
        CursoCampus,
        HorarioCampus,
        Matriz,
        MatriculaDiario,
        MatriculaPeriodo,
        PedidoMatricula,
        SituacaoMatriculaPeriodo,
        Turma,
        Turno,
    )

    ano = Ano.objects.get(ano=2019)
    curso = CursoCampus.objects.get(codigo='10101')
    matriz = Matriz.objects.get(descricao='Especialização em Educação Profissional')

    # Fecha 2019.1 se ainda estiver aberto: é o fechamento que cria a matrícula-período
    # de 2019.2 no período seguinte da matriz, e o módulo 06 pode ter reaberto o período
    # pela interface logo antes deste módulo rodar.
    for matricula_periodo in MatriculaPeriodo.objects.filter(
        aluno__curso_campus=curso, ano_letivo=ano, periodo_letivo=1, situacao=SituacaoMatriculaPeriodo.MATRICULADO
    ):
        matricula_periodo.fechar_periodo_letivo(True)

    # Desfaz uma renovação anterior: a suíte não dá flush e, com o aluno já matriculado na
    # turma de 2019.2, a tela de matrícula online não teria disciplina nenhuma a oferecer.
    matriculas_2019_2 = MatriculaPeriodo.objects.filter(aluno__curso_campus=curso, ano_letivo=ano, periodo_letivo=2)
    PedidoMatricula.objects.filter(matricula_periodo__in=matriculas_2019_2).delete()
    MatriculaDiario.objects.filter(matricula_periodo__in=matriculas_2019_2).delete()
    matriculas_2019_2.update(turma=None)

    if not Turma.objects.filter(ano_letivo=ano, periodo_letivo=2, curso_campus=curso, matriz=matriz).exists():
        turno = Turno.objects.get(descricao='Matutino')
        Turma.gerar_turmas(
            ano,
            2,
            {1: turno, 2: turno},
            {1: 10, 2: 10},
            {1: 1, 2: 1},
            curso,
            matriz,
            HorarioCampus.objects.get(descricao='Horário Padrão [Aula 45min]'),
            CalendarioAcademico.objects.get(descricao='Calendário Acadêmico Especialização 2019.2'),
            ComponenteCurricular.objects.filter(componente__sigla__in=['POS.0003', 'POS.0002'], matriz=matriz),
            False,
            None,
            True,
        )
    return Turma.objects.filter(ano_letivo=ano, periodo_letivo=2, curso_campus=curso, matriz=matriz)


@pytest.fixture
def renovacao_aberta(turmas_2019_2):
    """Configuração de renovação vigente em 21/07/2019, com o curso 10101 incluído.

    Criada por ORM para os testes do pedido e do processamento não dependerem do teste da
    tela de configuração — e removida no fim, porque uma janela de renovação aberta muda
    o que o aluno vê na tela inicial.
    """
    from comum.models import Ano
    from edu.models import ConfiguracaoPedidoMatricula, CursoCampus, Diretoria

    configuracao, _ = ConfiguracaoPedidoMatricula.get_or_create(
        descricao='Renovação 2019.2',
        ano_letivo=Ano.objects.get(ano=2019),
        periodo_letivo=2,
        data_inicio='2019-07-21',
        data_fim='2019-07-21',
    )
    configuracao.diretorias.add(Diretoria.objects.get(setor__sigla='DIAC/CEN'))
    configuracao.cursos.add(CursoCampus.objects.get(codigo='10101'))
    yield configuracao
    configuracao.pedidomatricula_set.all().delete()
    configuracao.delete()


def test_configura_renovacao_de_matricula(logado_edu, sufixo, turmas_2019_2):
    """Cria a janela de renovação e informa os cursos que participam dela."""
    from edu.models import ConfiguracaoPedidoMatricula

    descricao = f'Renovação E2E {sufixo}'
    page = logado_edu('secretario')
    try:
        page.goto('/admin/edu/configuracaopedidomatricula/add/')
        page.fill('input[name=descricao]', descricao)
        escolher_autocomplete(page, 'ano_letivo', '2019')
        page.select_option('select[name=periodo_letivo]', label='2')
        # `diretorias` sai como input escondido já preenchido quando o usuário enxerga
        # uma única diretoria — que é o caso do secretário.
        page.fill('input[name=data_inicio]', '2019-07-21')
        page.fill('input[name=data_fim]', '2019-07-21')
        page.click('input[name=_save]')

        mensagem_de_sucesso(page, 'Cadastro realizado com sucesso.')
        configuracao = ConfiguracaoPedidoMatricula.objects.filter(descricao=descricao).first()
        assert configuracao is not None, 'a UI disse que salvou, mas não persistiu'

        page.goto(f'/edu/configuracao_pedido_matricula/{configuracao.pk}/?tab=cursos')
        popup = abrir_popup(page, 'Informar Cursos')
        escolher_autocomplete(page, 'cursos', '10101', escopo=popup, opcao='')
        popup.locator('input[type=submit]').first.click()

        # A view responde com `httprr('..')` SEM `close_popup`: a confirmação é renderizada
        # DENTRO do iframe e só chega à página de trás se o SUAP recarregá-la. O fato estável,
        # que não depende desse encadeamento, é o vínculo no banco.
        cursos = configuracao.cursos.filter(codigo='10101')
        for _ in range(15):
            if cursos.exists():
                break
            page.wait_for_timeout(1000)
        assert cursos.exists(), f'curso não vinculado à renovação. {Tela(page).diagnostico()}'
    finally:
        ConfiguracaoPedidoMatricula.objects.filter(descricao=descricao).delete()


def test_aluno_realiza_pedido_de_matricula(logado_edu, renovacao_aberta):
    """O aluno escolhe os componentes do próximo período dentro da janela de renovação."""
    from edu.models import Aluno, PedidoMatricula

    aluno = Aluno.objects.get(matricula=MATRICULA_ALUNO)
    page = logado_edu(MATRICULA_ALUNO, senha='123')
    page.goto(f'/edu/pedido_matricula_seriado/{aluno.pk}/')
    expect(page.get_by_role('heading', name='Matrícula Online')).to_be_visible()

    # A tela oferece a turma (rádio) e os componentes obrigatórios dela (checkbox).
    page.locator('input[type=radio][name=turma]').first.check()
    diarios = page.locator('input[type=checkbox][name=diario_obrigatorio]')
    assert diarios.count(), 'nenhum componente oferecido ao aluno: a turma de 2019.2 não chegou à tela'
    for i in range(diarios.count()):
        diarios.nth(i).check()
    page.click('input[type=submit]')

    mensagem_de_sucesso(page, 'Pedido de matrícula salvo com sucesso.')
    assert PedidoMatricula.objects.filter(matricula_periodo__aluno=aluno, configuracao_pedido_matricula=renovacao_aberta).exists(), (
        'pedido de matrícula não registrado'
    )


def test_secretaria_processa_pedidos_de_matricula(logado_edu, relogio, renovacao_aberta, turmas_2019_2):
    """O processamento converte os pedidos em matrícula de período e de diário."""
    from edu.models import Aluno, MatriculaDiario, MatriculaPeriodo, PedidoMatricula, PedidoMatriculaDiario

    aluno = Aluno.objects.get(matricula=MATRICULA_ALUNO)
    matricula_periodo = MatriculaPeriodo.objects.filter(aluno=aluno, ano_letivo__ano=2019, periodo_letivo=2).first()
    assert matricula_periodo is not None, 'o fechamento de 2019.1 não gerou a matrícula-período de 2019.2'

    turma = turmas_2019_2.get(periodo_matriz=matricula_periodo.periodo_matriz)
    pedido = PedidoMatricula.objects.get_or_create(
        matricula_periodo_id=matricula_periodo.id, configuracao_pedido_matricula_id=renovacao_aberta.id, turma_id=turma.id
    )[0]
    for diario in turma.diario_set.all():
        PedidoMatriculaDiario.objects.get_or_create(pedido_matricula=pedido, diario=diario)

    relogio.congelar('22/07/2019')
    page = logado_edu('secretario')
    page.goto(f'/edu/processar_pedidos_matricula/{renovacao_aberta.pk}/')

    # Processamento assíncrono (``edu/tasks.py:processar_pedidos_matricula``): a resposta é
    # a tela da tarefa, e o efeito só aparece no banco quando ela termina.
    expect(page.get_by_role('heading', name='Processar Pedidos de Matrícula')).to_be_visible()
    _esperar(
        lambda: MatriculaDiario.objects.filter(matricula_periodo=matricula_periodo).exists(),
        'o processamento não gerou matrícula em diário para o aluno',
    )


def _esperar(condicao, mensagem: str, tentativas: int = 30) -> None:
    """Espera a tarefa assíncrona refletir no banco (ver ``test_06_encerramento``)."""
    import time

    for _ in range(tentativas):
        if condicao():
            return
        time.sleep(1)
    raise AssertionError(mensagem)
