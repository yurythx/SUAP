"""Testes DB-free da renderização do template da aba locais_aula_aluno e seus includes.

Valida a conformidade com as regras do Design System do SUAP:
- Ausência de tabs (indentação com 4 espaços);
- Títulos e rótulos em caixa de sentença (1ª inicial maiúscula);
- Ícone no botão de ação;
- Tabela envolvida em .table-responsive e com caption;
- Alertas vazios padronizados com <strong>Atenção:</strong>.
"""

from pathlib import Path
from unittest.mock import MagicMock

from django.template.loader import render_to_string


def test_template_sem_caracteres_de_tabulacao() -> None:
    template_path = Path(__file__).resolve().parents[2] / 'templates' / 'tabs' / 'aluno_locais_aula.html'
    content = template_path.read_text(encoding='utf-8')
    assert '\t' not in content, 'O template aluno_locais_aula.html não deve conter tabs (\t).'


def test_template_locais_aula_aluno_sem_matriculas_periodo() -> None:
    periodo_letivo_atual = MagicMock()
    periodo_letivo_atual.as_widget = '<div class="search-and-filters"></div>'

    context = {
        'periodo_letivo_atual': periodo_letivo_atual,
        'matriculas_periodo': [],
    }
    rendered = render_to_string('tabs/aluno_locais_aula.html', context)

    assert '<p class="alert alert-warning"><strong>Atenção:</strong> Nenhuma matrícula em diário no ano/período letivo.</p>' in rendered


def test_template_locais_aula_aluno_com_atividades_extras() -> None:
    class DummyPeriodo:
        ano = 2026
        periodo = 2
        as_widget = '<div class="search-and-filters"></div>'

    class DummyObj:
        pk = 452924

    class DummyAtividade:
        pk = 101
        descricao_atividade = 'Treino de Xadrez'
        horarios = '2M1 2M2'

        def get_tipo_atividade_display(self) -> str:
            return 'Atividade de Estudo'

    context = {
        'periodo_letivo_atual': DummyPeriodo(),
        'obj': DummyObj(),
        'matriculas_periodo': [1],
        'turnos': [],
        'matriculas_diario': [],
        'atividades': [DummyAtividade()],
        'perms': {'edu': {'add_horarioatividadeextra': True}},
    }
    rendered = render_to_string('tabs/aluno_locais_aula.html', context)

    assert 'Atividades extras' in rendered
    assert 'Adicionar atividade extra' in rendered
    assert 'icone fas fa-plus' in rendered
    assert '<div class="table-responsive">' in rendered
    assert '<caption>Atividades extras</caption>' in rendered
    assert 'Treino de Xadrez' in rendered
    assert 'class="success" class=' not in rendered
    assert 'class="btn popup success" href="/edu/adicionar_horario_atividade_extra/452924/2026/2/" class="success"' not in rendered
    assert '/edu/editar_horario_atividade_extra/452924/2026/2/101/' in rendered


def test_template_locais_aula_aluno_sem_atividades_extras() -> None:
    class DummyPeriodo:
        ano = 2026
        periodo = 2
        as_widget = '<div class="search-and-filters"></div>'

    class DummyObj:
        pk = 452924

    context = {
        'periodo_letivo_atual': DummyPeriodo(),
        'obj': DummyObj(),
        'matriculas_periodo': [1],
        'turnos': [],
        'matriculas_diario': [],
        'atividades': [],
        'perms': {'edu': {'add_horarioatividadeextra': False}},
    }
    rendered = render_to_string('tabs/aluno_locais_aula.html', context)

    assert '<p class="alert alert-warning"><strong>Atenção:</strong> Nenhuma atividade extra no período letivo selecionado.</p>' in rendered


def test_template_tabela_locais_com_diarios() -> None:
    class DummyProfSet:
        def exists(self) -> bool:
            return False

    class DummyComponente:
        componente = 'Matemática'

    class DummyDiario:
        pk = 12345
        componente_curricular = DummyComponente()
        professordiario_set = DummyProfSet()
        get_locais_aula = 'Sala 10'
        get_horario_aulas = '2M12'

    class DummyMatriculaDiario:
        diario = DummyDiario()

    context = {
        'matriculas_diario': [DummyMatriculaDiario()],
        'perms': {'edu': {'add_professordiario': True}},
    }
    rendered = render_to_string('includes/tabela_locais.html', context)

    assert '<div class="table-responsive">' in rendered
    assert '<caption>Diários do período letivo</caption>' in rendered
    assert '12345' in rendered
    assert 'Matemática' in rendered


def test_template_tabela_locais_sem_diarios() -> None:
    context = {'matriculas_diario': []}
    rendered = render_to_string('includes/tabela_locais.html', context)

    assert '<p class="alert alert-warning"><strong>Atenção:</strong> Nenhum diário no período letivo selecionado.</p>' in rendered


def test_template_tabela_horario_legenda_e_alerta() -> None:
    context_vazio = {'turnos': []}
    rendered_vazio = render_to_string('includes/tabela_horario.html', context_vazio)

    assert '<p class="alert alert-warning"><strong>Atenção:</strong> Nenhum horário de aula definido no período letivo.</p>' in rendered_vazio

    class DummyTurno:
        vazio = False
        dias_semana = [(1, 'Segunda')]
        horarios_aula: list = []

        def __str__(self) -> str:
            return 'Matutino'

    class DummyTurnos(list):
        as_form = False
        vazio = False

    context_com_turno = {'turnos': DummyTurnos([DummyTurno()]), 'impressao': False}
    rendered_com_turno = render_to_string('includes/tabela_horario.html', context_com_turno)

    assert '<li class="warning">Atividade de lazer</li>' in rendered_com_turno
    assert '<li class="extra">Atividade de estudo</li>' in rendered_com_turno
    assert '<li class="warning">Atividade de Lazer</li>' not in rendered_com_turno
    assert '<li class="extra">Atividade de Estudo</li>' not in rendered_com_turno


def test_template_tabela_horario_quando_turnos_vazio_eh_true_exibe_alerta() -> None:
    class DummyTurnos(list):
        as_form = False
        vazio = True

    context = {'turnos': DummyTurnos([1]), 'impressao': False}
    rendered = render_to_string('includes/tabela_horario.html', context)

    assert '<p class="alert alert-warning"><strong>Atenção:</strong> Nenhum horário de aula definido no período letivo.</p>' in rendered
    assert '<div class="legenda">' not in rendered


def test_template_tabela_horario_com_aulas_ativas_renderiza_caption() -> None:
    class DummyHorarioAula:
        vazio = False
        dias_semana = [{'numero': 1, 'marcado': False, 'conflito': False, 'horarios': []}]

        def __str__(self) -> str:
            return '07:00 - 07:45'

    class DummyTurno:
        vazio = False
        dias_semana = [(1, 'Segunda')]
        horarios_aula = [DummyHorarioAula()]

        def __str__(self) -> str:
            return 'Matutino'

    class DummyTurnos(list):
        as_form = False
        vazio = False

    context = {'turnos': DummyTurnos([DummyTurno()]), 'impressao': False}
    rendered = render_to_string('includes/tabela_horario.html', context)

    assert '<caption>Horários de aula - Matutino</caption>' in rendered
    assert '<div class="calendario calendario-mensal table-responsive p-0">' in rendered


def test_template_tabela_horario_quando_turnos_vazio_com_as_form_exibe_alerta() -> None:
    class DummyTurnos(list):
        as_form = True
        vazio = False

    context = {'turnos': DummyTurnos(), 'impressao': False}
    rendered = render_to_string('includes/tabela_horario.html', context)

    assert '<p class="alert alert-warning"><strong>Atenção:</strong> Nenhum horário de aula definido no período letivo.</p>' in rendered
    assert '<form action="" method="post">' not in rendered
    assert '<input type="submit" value="Salvar">' not in rendered
