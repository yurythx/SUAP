"""Tarefas 8 e 9 — fechar/reabrir o período letivo e corrigir lançamento já entregue.

Fechar o período é o que consolida o resultado do aluno e habilita a matrícula no período
seguinte; reabrir é o desfazer. Entre os dois mora a correção: quando a etapa já está
entregue, quem quiser mexer nela precisa primeiro **tomar a posse** do diário.

As duas telas de fechamento são assistentes de dois passos e processam em segundo plano —
a resposta é a tela da tarefa, não uma mensagem de sucesso; por isso a asserção espera o
banco, como fazem os e2e.
"""

from __future__ import annotations

import time

import pytest

from djtools.e2e_ui import Tela
from edu.tests.doc.conftest import anotar, escolher

pytestmark = [pytest.mark.doc, pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

DATA = '20/07/2019'

FECHAR = '/edu/fechar_periodo_letivo/'
REABRIR = '/edu/abrir_periodo_letivo/'


@pytest.fixture
def turma_2019_1(seed_periodo_executado):
    """Turma 2019.1 do curso 10101, com a etapa 1 já executada (aula, nota, entrega)."""
    from edu.models import Turma

    return Turma.objects.get(ano_letivo__ano=2019, periodo_letivo=1, curso_campus__codigo='10101')


@pytest.fixture
def periodo_aberto(turma_2019_1):
    from edu.models import MatriculaPeriodo, SituacaoMatriculaPeriodo

    MatriculaPeriodo.objects.filter(turma=turma_2019_1).update(situacao=SituacaoMatriculaPeriodo.MATRICULADO)
    return turma_2019_1


@pytest.fixture
def periodo_fechado(turma_2019_1):
    from edu.models import MatriculaPeriodo, SituacaoMatriculaPeriodo

    MatriculaPeriodo.objects.filter(turma=turma_2019_1).update(situacao=SituacaoMatriculaPeriodo.APROVADO)
    return turma_2019_1


def _esperar(condicao, mensagem: str, tentativas: int = 30) -> None:
    """Espera a tarefa assíncrona refletir no banco."""
    for _ in range(tentativas):
        if condicao():
            return
        time.sleep(1)
    raise AssertionError(mensagem)


def _selecionar_turma(page, turma) -> None:
    """Passo 1 dos dois assistentes: ano, período, tipo "Por Turma" e a turma."""
    page.select_option('select[name=ano_letivo]', label='2019')
    page.select_option('select[name=periodo_letivo]', label='1')
    page.check('input[name=tipo][value="TURMA"]')
    escolher(page, 'turma', str(turma), opcao='')


def test_fechar_periodo_letivo(logado_edu, periodo_aberto, capturar):
    """Tarefa 8, etapa 1 — o assistente de fechamento, com a opção de forçar."""
    from edu.models import MatriculaPeriodo, SituacaoMatriculaPeriodo

    page = logado_edu('admin_academico')
    tela = Tela(page).ir(FECHAR)
    tela.ver_titulo('Fechar período letivo')
    anotar('fechar-passo-1', tela)
    _selecionar_turma(page, periodo_aberto)
    capturar(page, 'fechar-passo-1')
    page.click('input[type=submit][value="Continuar"]')

    tela.esperar()
    anotar('fechar-passo-2', tela)
    page.check('input[name=forcar_fechamento]')
    page.check('input[name=confirmado]')
    capturar(page, 'fechar-passo-2')
    page.click('input[type=submit][value="Finalizar"]')

    tela.esperar()
    anotar('fechar-resultado', tela)
    capturar(page, 'fechar-resultado')
    _esperar(
        lambda: not MatriculaPeriodo.objects.filter(turma=periodo_aberto, situacao=SituacaoMatriculaPeriodo.MATRICULADO).exists(),
        'o período continua matriculado depois do fechamento',
    )


def test_reabrir_periodo_letivo(logado_edu, periodo_fechado, capturar):
    """Tarefa 8, etapa 2 — reabrir devolve o período à situação matriculada."""
    from edu.models import MatriculaPeriodo, SituacaoMatriculaPeriodo

    page = logado_edu('secretario')
    tela = Tela(page).ir(REABRIR)
    anotar('reabrir-passo-1', tela)
    _selecionar_turma(page, periodo_fechado)
    capturar(page, 'reabrir-passo-1')
    page.click('input[type=submit][value="Continuar"]')

    tela.esperar()
    anotar('reabrir-passo-2', tela)
    page.check('input[name=confirmado]')
    capturar(page, 'reabrir-passo-2')
    page.click('input[type=submit][value="Finalizar"]')

    tela.esperar()
    _esperar(
        lambda: MatriculaPeriodo.objects.filter(turma=periodo_fechado, situacao=SituacaoMatriculaPeriodo.MATRICULADO).exists(),
        'o período não voltou para matriculado depois da reabertura',
    )


def test_tomar_posse_do_diario_e_lancar_nota(logado_edu, turma_2019_1, capturar):
    """Tarefa 9 — a secretaria assume a etapa entregue, corrige a nota e devolve ao professor."""
    from edu.models import Diario, MatriculaDiario, NotaAvaliacao

    diario = turma_2019_1.diario_set.get(componente_curricular__componente__sigla='POS.0003')
    Diario.objects.filter(pk=diario.pk).update(posse_etapa_1=Diario.POSSE_PROFESSOR, situacao=Diario.SITUACAO_ABERTO)

    page = logado_edu('secretario')
    tela = Tela(page).ir(f'/edu/diario/{diario.pk}/')
    anotar('diario-secretaria', tela)
    capturar(page, 'diario-secretaria')
    tela.clicar_botao('Transferir para o Registro')
    tela.esperar()
    tela.sucesso('Posse transferida com sucesso')
    diario.refresh_from_db()
    assert diario.em_posse_do_registro(1), 'a posse da etapa 1 não passou para o registro escolar'

    avaliacao = NotaAvaliacao.objects.filter(
        matricula_diario__diario=diario,
        matricula_diario__situacao=MatriculaDiario.SITUACAO_CURSANDO,
        item_configuracao_avaliacao__configuracao_avaliacao__etapa=1,
    ).first()
    assert avaliacao is not None, 'diário sem avaliação para aluno cursando: nada a lançar'

    tela.ir(f'/edu/registrar_chamada/{diario.pk}/1/')
    anotar('registro-chamada', tela)
    capturar(page, 'registro-chamada')

    # A planilha de notas da secretaria é a aba "Registro de Notas" do próprio diário
    # (`/edu/diario/<pk>/?tab=notas_faltas`); `/edu/meu_diario/` é a porta do PROFESSOR e ali
    # o campo nem renderiza para quem não é o professor do diário.
    tela.ir(f'/edu/diario/{diario.pk}/?tab=notas_faltas')
    anotar('diario-notas-secretaria', tela)
    campo = page.locator(f'input[name="1;{avaliacao.matricula_diario_id};{avaliacao.item_configuracao_avaliacao_id}"]')
    campo.fill('80')
    campo.blur()
    tela.esperar()
    capturar(page, 'nota-registro')
    avaliacao.refresh_from_db()
    assert avaliacao.nota == 80, 'nota lançada pela secretaria não persistiu'

    # Devolver a posse é o que fecha a tarefa: sem isto o professor continua sem poder mexer.
    tela.ir(f'/edu/diario/{diario.pk}/')
    tela.clicar_botao('Transferir para o Professor')
    tela.esperar()
    tela.sucesso('Posse transferida com sucesso')
    diario.refresh_from_db()
    assert not diario.em_posse_do_registro(1), 'a posse da etapa 1 não voltou para o professor'
