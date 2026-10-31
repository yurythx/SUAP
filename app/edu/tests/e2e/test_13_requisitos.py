"""Fluxo 012: gerar turmas no regime de crédito, obrigatórias e optativas.

Continuação direta do módulo 12: com o curso de licenciatura e a matriz com pré/co-requisitos
no lugar, o que a funcionalidade 012 exercita é o assistente de Gerar Turmas no regime de
crédito — que tem uma escolha a mais que o seriado, o **tipo dos componentes**. Obrigatório e
Optativo produzem diários diferentes e é essa diferença que separa os dois testes: no
optativo o passo de dimensionamento por período não se aplica (não há período fixo), e o
assistente passa direto.

A validação de pré/co-requisito na hora de matricular o aluno em diário é declarada como
pendência na própria ``.feature`` ("pendencias: matricular aluno nos diarios validando pre/co
requisitos") — o que existe hoje, nos dois lados, é a geração das turmas.
"""

import pytest

from djtools.e2e_fixtures import escolher_autocomplete, mensagem_de_sucesso

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

DATA = '22/07/2019'


@pytest.fixture
def aluno_de_credito(curso_credito, relogio):
    """Aluna matriculada no curso em regime de crédito (Maria Pereira, 20191201010001).

    Vem do step ``a matrícula do aluno regime de crédito`` do behave — o mesmo que a
    funcionalidade 012 usa como configuração inicial. É ela que o módulo 14 convoca para o
    ENADE.
    """
    from edu.tests.e2e import seed
    from edu.models import Aluno

    curso = curso_credito()
    aluno = Aluno.objects.filter(curso_campus=curso).first()
    if aluno is None:
        seed.step_matricula_aluno_credito(relogio)
        aluno = Aluno.objects.get(curso_campus=curso)
    return aluno


def _gerar_turmas(page, curso, tipo_componente: str, dimensionar: bool) -> None:
    """O assistente de 4 passos, com o recorte por tipo de componente do regime de crédito."""
    page.goto('/edu/gerar_turmas/')
    page.select_option('select[name=ano_letivo]', label='2019')
    page.select_option('select[name=periodo_letivo]', label='2')
    page.select_option('select[name=tipo_componente]', label=tipo_componente)
    # Ancora na matriz da licenciatura: `opcao=''` pega o primeiro resultado e o assistente
    # geraria turma para o par matriz/curso errado.
    escolher_autocomplete(page, 'matriz_curso', curso.codigo, opcao='Licenciatura em Geografia')
    page.click('input[type=submit][value="Continuar"]')

    if dimensionar:
        # `wait_for_selector` antes de contar: `locator.count()` não espera navegação, então
        # sem isto o passo 2 é submetido com zero turmas e o passo 3 vem sem componente algum.
        page.wait_for_selector('select[name=qtd_periodo_1]')
        for indice in (1, 2):
            if page.locator(f'select[name=qtd_periodo_{indice}]').count():
                page.select_option(f'select[name=qtd_periodo_{indice}]', label='1')
                page.select_option(f'select[name=turno_periodo_{indice}]', label='Matutino')
                page.fill(f'input[name=vagas_periodo_{indice}]', '10')
    page.click('input[type=submit][value="Continuar"]')

    page.wait_for_selector('select[name=horario_campus]')
    page.select_option('select[name=horario_campus]', index=1)
    # Calendário pelo NOME: o de 2019.2 da pós tem uma etapa só e o assistente recusa a
    # combinação com os componentes de duas avaliações da licenciatura.
    calendario = page.locator('select[name=calendario_academico] option').filter(has_text='Licenciatura 2019.2').first
    page.select_option('select[name=calendario_academico]', value=calendario.get_attribute('value'))
    componentes = page.locator('input[name=componentes]')
    if not componentes.count():
        campos = page.locator('//form//*[@name]').evaluate_all('els => Array.from(new Set(els.map(e => e.name)))')
        raise AssertionError(f'o passo 3 não ofereceu componente algum. Campos na tela: {campos} | URL: {page.url}')
    for indice in range(componentes.count()):
        componentes.nth(indice).check()
    page.click('input[type=submit][value="Continuar"]')

    try:
        page.wait_for_selector('input[name=confirmacao]', timeout=10000)
    except Exception as falha:
        from djtools.e2e_ui import Tela

        raise AssertionError(f'o assistente não chegou à confirmação. {Tela(page).diagnostico()}') from falha
    page.check('input[name=confirmacao]')
    page.click('input[type=submit][value="Finalizar"]')
    mensagem_de_sucesso(page, 'Turmas geradas com sucesso.')


def test_gera_turmas_com_componentes_obrigatorios(logado_edu, curso_credito, aluno_de_credito):
    """Turmas dos componentes obrigatórios da matriz de licenciatura, período a período."""
    from edu.models import Turma

    curso = curso_credito()
    page = logado_edu('secretario')
    _gerar_turmas(page, curso, 'Obrigatório', dimensionar=True)

    turmas = Turma.objects.filter(ano_letivo__ano=2019, periodo_letivo=2, curso_campus=curso)
    assert turmas.exists(), 'a UI disse que gerou, mas nenhuma turma persistiu'
    assert any(turma.diario_set.exists() for turma in turmas), 'turmas geradas sem diário: os componentes não viraram diário'


def test_gera_turmas_com_componentes_optativos(logado_edu, curso_credito, aluno_de_credito):
    """Componente optativo não pertence a um período da matriz — a turma sai sem periodização.

    É a diferença de fluxo que o regime de crédito introduz: o aluno escolhe o optativo, então
    o assistente não pede dimensionamento por período e a turma nasce fora da grade fixa.
    """
    from edu.models import ComponenteCurricular, Diario

    curso = curso_credito()
    optativos = ComponenteCurricular.objects.filter(matriz__descricao='Licenciatura em Geografia', optativo=True)
    assert optativos.exists(), 'a matriz não tem componente optativo: nada a gerar'

    page = logado_edu('secretario')
    # Dimensiona também no optativo: sem número de turmas o assistente conclui sem criar
    # turma alguma, e aí não existe diário do componente optativo.
    _gerar_turmas(page, curso, 'Optativo', dimensionar=True)

    assert Diario.objects.filter(componente_curricular__in=optativos, turma__curso_campus=curso).exists(), (
        'nenhum diário de componente optativo foi criado'
    )
