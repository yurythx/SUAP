"""Tarefa 10 — renovar a matrícula para o período seguinte.

Três atos encadeados e três papéis: a secretaria abre a janela de renovação e informa os
cursos, o aluno escolhe as disciplinas dentro dela, e a secretaria processa os pedidos —
é o processamento que converte pedido em matrícula de período e de diário.
"""

from __future__ import annotations

import time
from uuid import uuid4

import pytest

from djtools.e2e_fixtures import abrir_popup
from djtools.e2e_ui import Tela
from edu.tests.doc.conftest import anotar, escolher

pytestmark = [pytest.mark.doc, pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

DATA = '21/07/2019'
MATRICULA_ALUNO = '20191101010001'


@pytest.fixture
def sufixo():
    return uuid4().hex[:6].upper()


@pytest.fixture
def turmas_2019_2(seed_periodo_fechado):
    """Turmas de 2019.2 do curso 10101 — o destino dos pedidos de renovação."""
    from comum.models import Ano
    from edu.models import (
        CalendarioAcademico,
        ComponenteCurricular,
        CursoCampus,
        HorarioCampus,
        MatriculaDiario,
        MatriculaPeriodo,
        Matriz,
        PedidoMatricula,
        SituacaoMatriculaPeriodo,
        Turma,
        Turno,
    )

    ano = Ano.objects.get(ano=2019)
    curso = CursoCampus.objects.get(codigo='10101')
    matriz = Matriz.objects.get(descricao='Especialização em Educação Profissional')

    for matricula_periodo in MatriculaPeriodo.objects.filter(
        aluno__curso_campus=curso, ano_letivo=ano, periodo_letivo=1, situacao=SituacaoMatriculaPeriodo.MATRICULADO
    ):
        matricula_periodo.fechar_periodo_letivo(True)

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
    """Configuração de renovação vigente em 21/07/2019, com o curso 10101 incluído."""
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


def _esperar(condicao, mensagem: str, tentativas: int = 30) -> None:
    for _ in range(tentativas):
        if condicao():
            return
        time.sleep(1)
    raise AssertionError(mensagem)


def test_configurar_renovacao(logado_edu, sufixo, turmas_2019_2, capturar):
    """Etapa 1 — a secretaria abre a janela e informa quais cursos participam dela."""
    from edu.models import ConfiguracaoPedidoMatricula

    descricao = f'Renovação DOC {sufixo}'
    configuracoes = ConfiguracaoPedidoMatricula.objects.filter(descricao=descricao)
    page = logado_edu('secretario')
    try:
        tela = Tela(page).ir('/admin/edu/configuracaopedidomatricula/')
        tela.ver_titulo('Renovações de Matrícula')
        anotar('renovacao-listagem', tela)
        capturar(page, 'renovacao-listagem')
        tela.clicar_botao('Adicionar Renovação de Matrícula')
        anotar('renovacao-formulario', tela)

        page.fill('input[name=descricao]', descricao)
        escolher(page, 'ano_letivo', '2019')
        page.select_option('select[name=periodo_letivo]', label='2')
        page.fill('input[name=data_inicio]', '2019-07-21')
        page.fill('input[name=data_fim]', '2019-07-21')
        capturar(page, 'renovacao-formulario')
        page.click('input[name=_save]')

        tela.sucesso('Cadastro realizado com sucesso.')
        configuracao = configuracoes.first()
        assert configuracao is not None, 'a UI disse que salvou, mas não persistiu'

        tela.ir(f'/edu/configuracao_pedido_matricula/{configuracao.pk}/?tab=cursos')
        anotar('renovacao-ficha', tela)
        capturar(page, 'renovacao-ficha')
        popup = abrir_popup(page, 'Informar Cursos')
        escolher(page, 'cursos', '10101', escopo=popup, opcao='')
        capturar(page, 'renovacao-cursos')
        popup.locator('input[type=submit]').first.click()

        cursos = configuracao.cursos.filter(codigo='10101')
        _esperar(cursos.exists, f'curso não vinculado à renovação. {Tela(page).diagnostico()}', tentativas=15)
    finally:
        configuracoes.delete()


def test_aluno_faz_o_pedido_de_matricula(logado_edu, renovacao_aberta, capturar):
    """Etapa 2 — o aluno escolhe a turma e as disciplinas do próximo período."""
    from edu.models import Aluno, PedidoMatricula

    aluno = Aluno.objects.get(matricula=MATRICULA_ALUNO)
    page = logado_edu(MATRICULA_ALUNO, senha='123')
    tela = Tela(page).ir('/')
    anotar('aluno-inicio-renovacao', tela)
    capturar(page, 'aluno-inicio-renovacao')

    tela.ir(f'/edu/pedido_matricula_seriado/{aluno.pk}/')
    tela.ver_titulo('Matrícula Online')
    anotar('pedido-matricula', tela)
    page.locator('input[type=radio][name=turma]').first.check()
    diarios = page.locator('input[type=checkbox][name=diario_obrigatorio]')
    assert diarios.count(), 'nenhum componente oferecido ao aluno: a turma de 2019.2 não chegou à tela'
    for indice in range(diarios.count()):
        diarios.nth(indice).check()
    capturar(page, 'pedido-matricula')
    page.click('input[type=submit]')

    tela.sucesso('Pedido de matrícula salvo com sucesso.')
    assert PedidoMatricula.objects.filter(matricula_periodo__aluno=aluno, configuracao_pedido_matricula=renovacao_aberta).exists(), (
        'pedido de matrícula não registrado'
    )
    capturar(page, 'pedido-matricula-resultado')


def test_processar_pedidos_de_matricula(logado_edu, relogio, renovacao_aberta, turmas_2019_2, capturar):
    """Etapa 3 — o processamento converte os pedidos em matrícula de período e de diário."""
    from edu.models import Aluno, MatriculaDiario, MatriculaPeriodo, PedidoMatricula, PedidoMatriculaDiario

    aluno = Aluno.objects.get(matricula=MATRICULA_ALUNO)
    matricula_periodo = MatriculaPeriodo.objects.filter(aluno=aluno, ano_letivo__ano=2019, periodo_letivo=2).first()
    assert matricula_periodo is not None, 'o fechamento de 2019.1 não gerou a matrícula-período de 2019.2'

    turma = turmas_2019_2.get(periodo_matriz=matricula_periodo.periodo_matriz)
    # `ModelPlus.get_or_create` preenche o primeiro TextField nulo do modelo com um texto
    # de rascunho — e em `PedidoMatricula` esse campo é `motivo_impedimento_matricula_vinculo`,
    # que desde 2fda1727d7 marca o pedido como JÁ PROCESSADO em `is_processado()`. O pedido
    # nasceria processado e a view recusaria com "O pedido não pode ser processado.".
    pedido = PedidoMatricula.objects.get_or_create(
        matricula_periodo_id=matricula_periodo.id, configuracao_pedido_matricula_id=renovacao_aberta.id, turma_id=turma.id
    )[0]
    for diario in turma.diario_set.all():
        PedidoMatriculaDiario.objects.get_or_create(pedido_matricula=pedido, diario=diario)

    relogio.congelar('22/07/2019')
    page = logado_edu('secretario')
    tela = Tela(page).ir(f'/edu/configuracao_pedido_matricula/{renovacao_aberta.pk}/')
    anotar('renovacao-pedidos', tela)
    capturar(page, 'renovacao-pedidos')

    tela.ir(f'/edu/processar_pedidos_matricula/{renovacao_aberta.pk}/')
    tela.ver_titulo('Processar Pedidos de Matrícula')
    anotar('processar-pedidos', tela)
    capturar(page, 'processar-pedidos')
    _esperar(
        lambda: MatriculaDiario.objects.filter(matricula_periodo=matricula_periodo).exists(),
        'o processamento não gerou matrícula em diário para o aluno',
    )
