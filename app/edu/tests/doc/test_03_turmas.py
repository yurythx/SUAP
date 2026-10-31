"""Tarefa 3 — abrir o período letivo: calendário, turmas e diários.

Duas tarefas da doc moram aqui, na ordem em que o campus as executa: cadastrar o
calendário acadêmico (que é o que autoriza aula, nota e fechamento nas datas certas) e
rodar o assistente de Gerar Turmas, que cria a turma e um diário por componente. Configurar
o diário (local, horário, professor) é a etapa que fecha a segunda tarefa: sem professor
vinculado o diário não aparece em "Meus Diários" e nada pode ser lançado.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from djtools.e2e_fixtures import abrir_popup, mensagem_de_sucesso
from djtools.e2e_ui import Tela
from edu.tests.doc.conftest import anotar, escolher

pytestmark = [pytest.mark.doc, pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

DATA = '10/03/2019'


@pytest.fixture
def sufixo():
    return uuid4().hex[:6].upper()


@pytest.fixture
def curso_conceito(edu_seed):
    """``(curso, matriz)`` do par "[CONCEITO]", que nenhuma outra tarefa avança."""
    from edu.models import CursoCampus, Matriz

    return (
        CursoCampus.objects.get(codigo='20202'),
        Matriz.objects.get(descricao='Especialização em Educação Profissional [CONCEITO]'),
    )


@pytest.fixture
def turma_conceito(curso_conceito):
    """Turma 2019.1 do curso "[CONCEITO]" com dois diários ainda NÃO configurados."""
    from comum.models import Ano
    from edu.models import CalendarioAcademico, ComponenteCurricular, HorarioCampus, Turma, Turno

    curso, matriz = curso_conceito
    ano = Ano.objects.get(ano=2019)
    turma = Turma.objects.filter(ano_letivo=ano, periodo_letivo=1, curso_campus=curso, matriz=matriz).first()
    if turma is None:
        Turma.gerar_turmas(
            ano,
            1,
            {1: Turno.objects.get(descricao='Matutino')},
            {1: 10},
            {1: 1},
            curso,
            matriz,
            HorarioCampus.objects.get(descricao='Horário Padrão [Aula 45min]'),
            CalendarioAcademico.objects.get(descricao='Calendário Acadêmico Especialização 2019.1'),
            ComponenteCurricular.objects.filter(componente__sigla__in=['POS.0001', 'POS.0003'], matriz=matriz),
            False,
            None,
            True,
        )
        turma = Turma.objects.get(ano_letivo=ano, periodo_letivo=1, curso_campus=curso, matriz=matriz)
    return turma


def test_cadastrar_calendario_academico(logado_edu, sufixo, capturar):
    """O calendário é o que autoriza (ou barra) aula, nota e fechamento nas datas certas."""
    from edu.models import CalendarioAcademico

    descricao = f'Calendário DOC {sufixo}'
    calendarios = CalendarioAcademico.objects.filter(descricao=descricao)
    page = logado_edu('secretario')
    try:
        tela = Tela(page).ir('/admin/edu/calendarioacademico/correntes/')
        tela.ver_titulo('Calendários Acadêmicos')
        anotar('calendario-listagem', tela)
        capturar(page, 'calendario-listagem')
        tela.clicar_botao('Adicionar Calendário Acadêmico')
        anotar('calendario-formulario', tela)

        page.fill('input[name=descricao]', descricao)
        page.select_option('select[name=uo]', label='CEN')
        escolher(page, 'diretoria', 'DIAC/CEN')
        page.select_option('select[name=tipo]', label='Semestral')
        escolher(page, 'ano_letivo', '2019')
        page.select_option('select[name=periodo_letivo]', label='1')
        page.fill('input[name=data_inicio]', '2019-03-20')
        page.fill('input[name=data_fim]', '2019-07-18')
        page.fill('input[name=data_fechamento_periodo]', '2019-07-19')
        page.locator('input[name=qtd_etapas]').first.check()
        page.fill('input[name=data_inicio_etapa_1]', '2019-03-20')
        page.fill('input[name=data_fim_etapa_1]', '2019-07-18')
        capturar(page, 'calendario-formulario')
        page.click('input[name=_save]')

        mensagem_de_sucesso(page, 'Cadastro realizado com sucesso.')
        assert calendarios.exists(), 'a UI disse que salvou, mas não persistiu'
    finally:
        calendarios.delete()


def test_gerar_turmas_pelo_assistente(logado_edu, curso_conceito, capturar):
    """O assistente de 4 passos: cada passo só sabe montar suas opções depois do anterior."""
    from comum.models import Ano
    from edu.models import Turma

    curso, matriz = curso_conceito
    ano = Ano.objects.get(ano=2019)
    page = logado_edu('secretario')

    tela = Tela(page).ir('/edu/gerar_turmas/')
    tela.ver_titulo('Gerar Turmas')
    anotar('turma-assistente-1', tela)
    page.select_option('select[name=ano_letivo]', label='2019')
    page.select_option('select[name=periodo_letivo]', label='2')
    page.select_option('select[name=tipo_componente]', label='Obrigatório')
    escolher(page, 'matriz_curso', curso.codigo, opcao=matriz.descricao)
    capturar(page, 'turma-assistente-1')
    page.click('input[type=submit][value="Continuar"]')

    anotar('turma-assistente-2', Tela(page))
    page.select_option('select[name=qtd_periodo_1]', label='1')
    page.select_option('select[name=turno_periodo_1]', label='Matutino')
    page.fill('input[name=vagas_periodo_1]', '10')
    capturar(page, 'turma-assistente-2')
    page.click('input[type=submit][value="Continuar"]')

    anotar('turma-assistente-3', Tela(page))
    page.select_option('select[name=horario_campus]', index=1)
    page.select_option('select[name=calendario_academico]', index=1)
    componentes = page.locator('input[name=componentes]')
    assert componentes.count(), 'o passo 3 não ofereceu componente algum'
    for indice in range(componentes.count()):
        componentes.nth(indice).check()
    capturar(page, 'turma-assistente-3')
    page.click('input[type=submit][value="Continuar"]')

    tela = Tela(page)
    tela.ver_texto('As seguintes turmas e diários serão criados/atualizados')
    anotar('turma-assistente-4', tela)
    capturar(page, 'turma-assistente-4')
    page.check('input[name=confirmacao]')
    page.click('input[type=submit][value="Finalizar"]')

    mensagem_de_sucesso(page, 'Turmas geradas com sucesso.')
    turma = Turma.objects.filter(ano_letivo=ano, periodo_letivo=2, curso_campus=curso).first()
    assert turma is not None, 'a UI disse que gerou, mas não persistiu'
    assert turma.diario_set.exists(), 'turma gerada sem diário: os componentes selecionados não viraram diário'
    capturar(page, 'turma-listagem')


def test_configurar_diario(logado_edu, turma_conceito, capturar):
    """Local, horário e professor — os três popups que tornam um diário utilizável."""
    from edu.models import ProfessorDiario

    diario = turma_conceito.diario_set.order_by('pk').first()
    ProfessorDiario.objects.filter(diario=diario).delete()
    diario.horarioauladiario_set.all().delete()

    page = logado_edu('secretario')
    tela = Tela(page).ir(f'/edu/diario/{diario.pk}/')
    anotar('diario-ficha', tela)
    capturar(page, 'diario-ficha')

    popup = abrir_popup(page, 'Definir Local')
    escolher(page, 'sala', 'Sala 101', escopo=popup)
    capturar(page, 'diario-local')
    popup.locator('input[type=submit]').first.click()
    mensagem_de_sucesso(page, 'Local definido com sucesso.')

    popup = abrir_popup(page, 'Definir Horário')
    popup.locator('input[name=horario]').first.check()
    capturar(page, 'diario-horario')
    popup.locator('input[type=submit]').first.click()
    mensagem_de_sucesso(page, 'Horário definido com sucesso.')

    popup = abrir_popup(page, 'Adicionar Professor')
    escolher(page, 'vinculo', '100007', escopo=popup)
    escolher(page, 'tipo', 'Principal', escopo=popup)
    popup.locator('input[name=percentual_ch]').fill('100')
    capturar(page, 'diario-professor')
    popup.locator('input[type=submit]').first.click()
    mensagem_de_sucesso(page, 'Professor adicionado/atualizado com sucesso.')

    diario.refresh_from_db()
    assert diario.local_aula is not None, 'local de aula não gravado'
    assert diario.horarioauladiario_set.exists(), 'horário de aula não gravado'
    assert ProfessorDiario.objects.filter(diario=diario, professor__vinculo__user__username='100007').exists(), 'professor não vinculado ao diário'
