"""Fluxo 003: turmas e diários — horário do campus, calendário, assistente e diário.

Terceiro elo, e o de maior maquinário de interface do módulo: o **assistente de Gerar
Turmas** é um wizard de 4 passos cujo passo N só sabe montar suas opções depois de ler o
passo N-1 (o calendário disponível depende da matriz/curso escolhida), e a configuração
do diário é feita por três popups em sequência. Nada disso é exercitado por teste de
unidade — quebra aqui só aparece no browser.

Os alvos são o curso "[CONCEITO]" (código 20202), que o replay cria e não avança: gerar
turma no curso 10101 mexeria no mesmo período letivo que os módulos 05→07 percorrem.
"""

from uuid import uuid4

import pytest
from playwright.sync_api import expect

from djtools.e2e_fixtures import abrir_popup, escolher_autocomplete, mensagem_de_sucesso
from djtools.e2e_ui import Tela

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

DATA = '10/03/2019'


@pytest.fixture
def sufixo():
    return uuid4().hex[:6].upper()


@pytest.fixture
def curso_conceito(edu_seed):
    """``(curso, matriz)`` do par replicado "[CONCEITO]", que mais nenhum módulo avança."""
    from edu.models import CursoCampus, Matriz

    return (
        CursoCampus.objects.get(codigo='20202'),
        Matriz.objects.get(descricao='Especialização em Educação Profissional [CONCEITO]'),
    )


@pytest.fixture
def turma_conceito(curso_conceito):
    """Turma 2019.1 do curso "[CONCEITO]", com dois diários ainda NÃO configurados.

    Montada por ORM (a mesma chamada que o replay usa) porque o alvo deste módulo é
    configurar o diário; deixar isso dependendo do teste do assistente amarraria os dois
    numa ordem de execução.
    """
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


def test_cadastra_horario_do_campus(logado_edu, sufixo):
    """O horário do campus é um formset: o cabeçalho e as faixas de aula no mesmo save."""
    from edu.models import HorarioAula, HorarioCampus

    descricao = f'Horário E2E {sufixo}'
    page = logado_edu('admin_academico')
    try:
        page.goto('/admin/edu/horariocampus/add/')
        page.fill('input[name=descricao]', descricao)
        escolher_autocomplete(page, 'uo', 'CEN')
        page.check('input[name=ativo]')
        for linha, (numero, inicio, termino) in enumerate([('1', '7:00', '7:45'), ('2', '7:50', '8:35')]):
            page.select_option(f'select[name=horarioaula_set-{linha}-numero]', label=numero)
            page.select_option(f'select[name=horarioaula_set-{linha}-turno]', label='Matutino')
            page.fill(f'input[name=horarioaula_set-{linha}-inicio]', inicio)
            page.fill(f'input[name=horarioaula_set-{linha}-termino]', termino)
        page.click('input[name=_save]')

        mensagem_de_sucesso(page, 'Cadastro realizado com sucesso.')
        horario = HorarioCampus.objects.filter(descricao=descricao).first()
        assert horario is not None, 'a UI disse que salvou, mas não persistiu'
        assert HorarioAula.objects.filter(horario_campus=horario).count() == 2, 'as faixas de aula do formset não foram gravadas'
    finally:
        HorarioCampus.objects.filter(descricao=descricao).delete()


def test_cadastra_calendario_academico(logado_edu, sufixo):
    """Calendário define as datas que depois autorizam (ou barram) aula, nota e etapa."""
    from edu.models import CalendarioAcademico

    descricao = f'Calendário E2E {sufixo}'
    page = logado_edu('secretario')
    try:
        page.goto('/admin/edu/calendarioacademico/add/')
        page.fill('input[name=descricao]', descricao)
        page.select_option('select[name=uo]', label='CEN')
        escolher_autocomplete(page, 'diretoria', 'DIAC/CEN')
        page.select_option('select[name=tipo]', label='Semestral')
        escolher_autocomplete(page, 'ano_letivo', '2019')
        page.select_option('select[name=periodo_letivo]', label='1')
        page.fill('input[name=data_inicio]', '2019-03-20')
        page.fill('input[name=data_fim]', '2019-07-18')
        page.fill('input[name=data_fechamento_periodo]', '2019-07-19')
        # "Etapa Única" — a quantidade de etapas define quantos blocos de nota o diário terá.
        page.locator('input[name=qtd_etapas]').first.check()
        page.fill('input[name=data_inicio_etapa_1]', '2019-03-20')
        page.fill('input[name=data_fim_etapa_1]', '2019-07-18')
        page.click('input[name=_save]')

        mensagem_de_sucesso(page, 'Cadastro realizado com sucesso.')
        assert CalendarioAcademico.objects.filter(descricao=descricao).exists(), 'a UI disse que salvou, mas não persistiu'
    finally:
        CalendarioAcademico.objects.filter(descricao=descricao).delete()


def test_gera_turmas_pelo_assistente(logado_edu, curso_conceito):
    """Wizard de 4 passos: curso → nº de turmas por período → horário/componentes → confirmar.

    Cada passo é submetido por GET e reconfigura o seguinte — o calendário oferecido no
    passo 3, por exemplo, só existe porque o passo 1 disse qual matriz/curso e qual
    período letivo. Gera o período 2019.**2** para não colidir com a turma de 2019.1 que
    o ``turma_conceito`` monta.
    """
    from comum.models import Ano
    from edu.models import Turma

    curso, matriz = curso_conceito
    ano = Ano.objects.get(ano=2019)
    page = logado_edu('secretario')

    page.goto('/edu/gerar_turmas/')
    expect(page.get_by_role('heading', name='Gerar Turmas')).to_be_visible()
    page.select_option('select[name=ano_letivo]', label='2019')
    page.select_option('select[name=periodo_letivo]', label='2')
    page.select_option('select[name=tipo_componente]', label='Obrigatório')
    # Busca pelo código do curso, mas ancora a OPÇÃO na matriz: o curso tem mais de uma matriz
    # vinculada e `opcao=''` (primeiro resultado) escolhia um par matriz/curso ao acaso — as
    # turmas saíam para o par errado e a asserção não achava nada.
    escolher_autocomplete(page, 'matriz_curso', curso.codigo, opcao=matriz.descricao)
    page.click('input[type=submit][value="Continuar"]')

    page.select_option('select[name=qtd_periodo_1]', label='1')
    page.select_option('select[name=turno_periodo_1]', label='Matutino')
    page.fill('input[name=vagas_periodo_1]', '10')
    page.click('input[type=submit][value="Continuar"]')

    # index=1: o índice 0 é o "---------" vazio, e escolhê-lo devolve "Este campo é
    # obrigatório" no passo 3 sem sair do lugar.
    page.select_option('select[name=horario_campus]', index=1)
    page.select_option('select[name=calendario_academico]', index=1)
    componentes = page.locator('input[name=componentes]')
    assert componentes.count(), 'o passo 3 não ofereceu componente algum — a matriz/curso do passo 1 não chegou aqui'
    for i in range(componentes.count()):
        componentes.nth(i).check()
    page.click('input[type=submit][value="Continuar"]')

    expect(page.get_by_text('As seguintes turmas e diários serão criados/atualizados')).to_be_visible()
    page.check('input[name=confirmacao]')
    page.click('input[type=submit][value="Finalizar"]')

    mensagem_de_sucesso(page, 'Turmas geradas com sucesso.')
    # Sem filtrar por matriz: o curso 20202 tem DUAS matrizes vinculadas (o `replicar` do
    # replay copia o vínculo da matriz original além de criar o da réplica), e o que este
    # teste afirma é que o assistente gerou turma para o curso escolhido.
    turma = Turma.objects.filter(ano_letivo=ano, periodo_letivo=2, curso_campus=curso).first()
    assert turma is not None, 'a UI disse que gerou, mas não persistiu'
    assert turma.diario_set.exists(), 'turma gerada sem diário: os componentes selecionados não viraram diário'


def test_configura_diario(logado_edu, turma_conceito):
    """Local, horário e professor — os três popups que tornam um diário utilizável.

    Sem professor vinculado o diário não aparece em "Meus Diários" e nenhuma etapa pode
    ser entregue; é o passo que liga o diário ao fluxo do módulo 05.
    """
    from edu.models import ProfessorDiario

    diario = turma_conceito.diario_set.order_by('pk').first()
    # A suíte não dá flush: sem zerar, a segunda execução tentaria vincular o mesmo
    # professor de novo e a tela recusaria.
    #
    # O `except` devolve o vínculo se a UI falhar no meio. Sem ele, uma falha em qualquer
    # passo abaixo deixa o diário do curso "[CONCEITO]" SEM PROFESSOR permanentemente: o
    # guard de `seed_conceito` (conftest.py) é o CPF da aluna, que continua existindo, então
    # o seed nunca reconstrói o vínculo — e `test_10_conceito` passa a falhar em toda
    # execução seguinte com `pode_registrar_nota() == False`. Uma flakada aqui envenenava o
    # banco para as próximas execuções em `--reuse-db`.
    professores_diario = list(ProfessorDiario.objects.filter(diario=diario))
    ProfessorDiario.objects.filter(diario=diario).delete()
    diario.horarioauladiario_set.all().delete()

    try:
        page = logado_edu('secretario')
        page.goto(f'/edu/diario/{diario.pk}/')

        popup = abrir_popup(page, 'Definir Local')
        escolher_autocomplete(page, 'sala', 'Sala 101', escopo=popup)
        popup.locator('input[type=submit]').first.click()
        mensagem_de_sucesso(page, 'Local definido com sucesso.')

        popup = abrir_popup(page, 'Definir Horário')
        # A grade é uma matriz de dia da semana por faixa de aula; basta uma marcação para o
        # diário passar a ter horário.
        popup.locator('input[name=horario]').first.check()
        popup.locator('input[type=submit]').first.click()
        mensagem_de_sucesso(page, 'Horário definido com sucesso.')

        popup = abrir_popup(page, 'Adicionar Professor')
        escolher_autocomplete(page, 'vinculo', '100007', escopo=popup)
        escolher_autocomplete(page, 'tipo', 'Principal', escopo=popup)
        popup.locator('input[name=percentual_ch]').fill('100')
        popup.locator('input[type=submit]').first.click()
        mensagem_de_sucesso(page, 'Professor adicionado/atualizado com sucesso.')
    except Exception:
        if not ProfessorDiario.objects.filter(diario=diario).exists():
            for professor_diario in professores_diario:
                professor_diario.pk = None
                professor_diario.save()
        raise

    diario.refresh_from_db()
    assert diario.local_aula is not None, 'local de aula não gravado'
    assert diario.horarioauladiario_set.exists(), 'horário de aula não gravado'
    assert ProfessorDiario.objects.filter(diario=diario, professor__vinculo__user__username='100007').exists(), 'professor não vinculado ao diário'


def test_professor_nao_gera_turmas(logado_edu):
    """Gerar turmas é procedimento de secretaria; o professor não tem a permissão."""
    page = logado_edu('professor')
    assert page.goto('/edu/gerar_turmas/').status == 403


def test_cadastra_tipo_de_professor_em_diario(logado_edu, sufixo):
    """O tipo de professor é o vínculo dele com o diário (Principal, Colaborador...).

    Pré-cadastro da funcionalidade 003: sem ele a configuração do diário não consegue
    adicionar professor, porque o campo Tipo é obrigatório lá.
    """
    from edu.models import TipoProfessorDiario

    descricao = f'Principal E2E {sufixo}'
    tipos = TipoProfessorDiario.objects.filter(descricao=descricao)
    try:
        tela = Tela(logado_edu('admin_academico')).ir('/admin/edu/tipoprofessordiario/add/')
        tela.preencher('Descrição', 'texto', descricao)
        tela.clicar_botao('Salvar')

        tela.sucesso('Cadastro realizado com sucesso.')
        assert tipos.exists(), 'a UI disse que salvou, mas não persistiu'
    finally:
        tipos.delete()
