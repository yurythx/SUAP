"""Testes de views, formulários e templates de minicurso e turma de minicurso.

Testa as views de ``edu/views/mini_cursos.py``, o ``MonitorMinicursoForm`` e a compilação/renderização
dos templates ``edu/templates/minicurso.html`` e ``edu/templates/turma_minicurso.html``.
"""

from __future__ import annotations

import datetime
from inspect import unwrap
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from django.template.loader import render_to_string

from edu.forms.mini_cursos import MonitorMinicursoForm
from edu.models import MonitorMinicurso
from edu.tests.factories import AlunoFactory, MonitorMinicursoFactory, TurmaMinicursoFactory
from edu.views import mini_cursos


class MockQuerySet(list):
    """QuerySet simulado para templates DB-free."""

    def count(self) -> int:
        return len(self)

    def exists(self) -> bool:
        return len(self) > 0

    def all(self) -> MockQuerySet:
        return self


def test_minicurso_view_retorna_contexto(make_request) -> None:
    request = make_request()
    request.user.has_perm = MagicMock(return_value=False)
    request.user.has_group_cached = MagicMock(return_value=True)

    obj = MagicMock()
    obj.__str__.return_value = 'Minicurso de Extensão'

    with (
        patch.object(mini_cursos, 'get_object_or_404', return_value=obj),
        patch.object(mini_cursos.Minicurso.locals, 'filter') as mock_filter,
    ):
        mock_filter.return_value.exists.return_value = True
        resposta = unwrap(mini_cursos.minicurso)(request, pk=10)

    assert isinstance(resposta, dict)
    assert resposta['title'] == 'Minicurso de Extensão'
    assert resposta['obj'] is obj
    assert resposta['pode_realizar_acoes'] is True
    assert resposta['pode_clonar_curso'] is True


def test_turma_minicurso_view_retorna_contexto(make_request) -> None:
    request = make_request()
    obj = MagicMock()
    obj.__str__.return_value = 'Turma 01 - 2025.1'
    obj.minicurso_id = 5
    obj.integracao_com_moodle = False

    with (
        patch.object(mini_cursos, 'get_object_or_404', return_value=obj),
        patch.object(mini_cursos.Minicurso.locals, 'filter') as mock_minicurso_filter,
        patch.object(mini_cursos.Aluno.objects, 'filter') as mock_aluno_filter,
    ):
        mock_minicurso_filter.return_value.exists.return_value = True
        mock_aluno_filter.return_value.exists.return_value = False
        resposta = unwrap(mini_cursos.turma_minicurso)(request, pk=20)

    assert isinstance(resposta, dict)
    assert resposta['title'] == 'Turma: Turma 01 - 2025.1'
    assert resposta['obj'] is obj
    assert resposta['pode_realizar_acoes'] is True
    assert resposta['possui_aluno_desvinculado'] is False
    assert 'hoje' in resposta
    assert 'participantes' in resposta


def test_template_minicurso_renderiza_sem_erros(make_request) -> None:
    request = make_request()
    request.user.is_authenticated = False
    request.session['menu_as_html'] = '<nav></nav>'
    request.session['theme'] = 'default'

    turma_mock = SimpleNamespace(
        pk=1,
        descricao='Turma A',
        ano_letivo=2025,
        periodo_letivo=1,
        data_inicio=datetime.date(2025, 3, 1),
        data_fim=datetime.date(2025, 4, 1),
        turno='Matutino',
        gerar_matricula=True,
        participanteturmaminicurso_set=MockQuerySet([None] * 15),
        professorminicurso_set=MockQuerySet(),
        monitorminicurso_set=MockQuerySet(),
    )

    conteudo_mock = SimpleNamespace(
        descricao='Introdução ao Tema',
        ch=20,
    )

    diretoria_mock = SimpleNamespace(
        get_absolute_url=lambda: '/edu/diretoria/1/',
        __str__=lambda: 'Diretoria de Extensão',
    )

    minicurso_mock = SimpleNamespace(
        pk=10,
        codigo='0001.REITORIA',
        descricao='Curso de Python Básico',
        ano_letivo=2025,
        periodo_letivo=1,
        modalidade='FIC < 160h',
        diretoria=diretoria_mock,
        codigo_sistec='123456',
        resolucao_criacao='Resolução 01/2025',
        ch_total=40,
        ch_aula=48,
        tipo_hora_aula=50,
        autoinstrucional=False,
        ppc=None,
        ativo=True,
        can_change=True,
        conteudominicurso_set=MockQuerySet([conteudo_mock]),
        turmaminicurso_set=MockQuerySet([turma_mock]),
    )

    context = {
        'super_template': 'admin/base.html',
        'theme': 'default',
        'obj': minicurso_mock,
        'pode_realizar_acoes': True,
        'pode_clonar_curso': True,
        'perms': MagicMock(edu=MagicMock(change_minicurso=True)),
    }

    html = render_to_string('minicurso.html', context, request=request)

    assert 'Identificação' in html
    assert 'Curso de Python Básico' in html
    assert 'Conteúdos' in html
    assert 'Turmas' in html
    assert 'Turmas do minicurso' in html
    assert 'Adicionar turma' in html


def test_template_turma_minicurso_renderiza_sem_erros(make_request) -> None:
    request = make_request()
    request.user.is_authenticated = False
    request.session['menu_as_html'] = '<nav></nav>'
    request.session['theme'] = 'default'

    minicurso_mock = SimpleNamespace(
        pk=10,
        descricao='Curso de Python Básico',
        get_absolute_url=lambda: '/edu/minicurso/10/',
        autoinstrucional=False,
    )

    turma_mock = SimpleNamespace(
        pk=25,
        descricao='Turma 2025.1 Manhã',
        minicurso=minicurso_mock,
        ano_letivo=2025,
        periodo_letivo=1,
        data_inicio=datetime.date(2025, 3, 1),
        data_fim=datetime.date(2025, 3, 31),
        turno='Matutino',
        gerar_matricula=False,
        integracao_com_moodle=False,
        url_moodle=None,
        url_ambiente_virtual=None,
        autoinscricional=False,
        professorminicurso_set=MockQuerySet(),
        monitorminicurso_set=MockQuerySet(),
    )

    participantes_mock = MockQuerySet()

    context = {
        'super_template': 'admin/base.html',
        'theme': 'default',
        'obj': turma_mock,
        'hoje': datetime.date(2025, 3, 15),
        'participantes': participantes_mock,
        'possui_aluno_desvinculado': False,
        'pode_realizar_acoes': True,
        'perms': MagicMock(edu=MagicMock(change_minicurso=True, change_turmaminicurso=True, delete_participanteturmaminicurso=True)),
    }

    html = render_to_string('turma_minicurso.html', context, request=request)

    assert 'Dados gerais' in html
    assert 'Visualizar minicurso' in html
    assert 'Professores' in html
    assert 'Monitores' in html
    assert 'Participantes' in html
    assert 'Adicionar professor' in html
    assert 'Adicionar monitor' in html


def test_template_turma_minicurso_com_equipe_e_participantes(make_request) -> None:
    request = make_request()
    request.user.is_authenticated = False
    request.session['menu_as_html'] = '<nav></nav>'
    request.session['theme'] = 'default'

    minicurso_mock = SimpleNamespace(
        pk=10,
        descricao='Curso de Python Avançado',
        get_absolute_url=lambda: '/edu/minicurso/10/',
        autoinstrucional=False,
    )

    professor_mock = SimpleNamespace(
        pk=101,
        get_matricula=lambda: '1987654',
        vinculo=SimpleNamespace(pessoa=SimpleNamespace(nome='Prof. Carlos Alberto')),
    )

    pm_mock = SimpleNamespace(
        pk=50,
        professor=professor_mock,
        carga_horaria=20,
        get_carga_horaria_ha=lambda: 24,
        tipo_id=None,
    )

    aluno_monitor = SimpleNamespace(matricula='20251001', get_nome='Maria Eduarda')
    mm_mock = SimpleNamespace(pk=60, aluno=aluno_monitor, carga_horaria=10)

    turma_mock = SimpleNamespace(
        pk=25,
        descricao='Turma Avançada 2025.1',
        minicurso=minicurso_mock,
        ano_letivo=2025,
        periodo_letivo=1,
        data_inicio=datetime.date(2025, 2, 1),
        data_fim=datetime.date(2025, 2, 28),
        turno='Noturno',
        gerar_matricula=True,
        integracao_com_moodle=False,
        url_moodle=None,
        url_ambiente_virtual=None,
        autoinscricional=False,
        professorminicurso_set=MockQuerySet([pm_mock]),
        monitorminicurso_set=MockQuerySet([mm_mock]),
    )

    aluno_part = SimpleNamespace(
        pessoa_fisica=SimpleNamespace(cpf='111.222.333-44'),
        get_nome='João da Silva',
        matricula='20251099',
        email_notificacao='joao@example.com',
        situacao='Concluído',
        is_concluido=True,
    )

    part_mock = SimpleNamespace(
        pk=201,
        id=201,
        aluno=aluno_part,
        nota=9.5,
        completude=100,
    )

    participantes_mock = MockQuerySet([part_mock])

    context = {
        'super_template': 'admin/base.html',
        'theme': 'default',
        'obj': turma_mock,
        'hoje': datetime.date(2025, 3, 15),
        'participantes': participantes_mock,
        'possui_aluno_desvinculado': False,
        'pode_realizar_acoes': True,
        'perms': MagicMock(edu=MagicMock(change_minicurso=True, change_turmaminicurso=True, delete_participanteturmaminicurso=True)),
    }

    html = render_to_string('turma_minicurso.html', context, request=request)

    assert 'Prof. Carlos Alberto' in html
    assert 'Maria Eduarda' in html
    assert 'João da Silva' in html
    assert '111.222.333-44' in html
    assert 'Imprimir certificado' in html
    assert 'btn_enviar_certificados' in html
    assert 'checkall_participantes' in html


@pytest.mark.django_db
def test_monitor_minicurso_form_clean_aluno_rejeita_aluno_duplicado(sync_permissions) -> None:
    monitor = MonitorMinicursoFactory()
    form = MonitorMinicursoForm(
        data={'aluno': monitor.aluno.pk, 'carga_horaria': 20},
        instance=MonitorMinicurso(turma_minicurso=monitor.turma_minicurso),
    )

    assert form.is_valid() is False
    assert 'Este aluno já está cadastrado como monitor desta turma.' in form.errors['aluno']


@pytest.mark.django_db
def test_monitor_minicurso_form_clean_aluno_aceita_aluno_inedito(sync_permissions) -> None:
    turma = TurmaMinicursoFactory()
    aluno = AlunoFactory()
    form = MonitorMinicursoForm(
        data={'aluno': aluno.pk, 'carga_horaria': 20},
        instance=MonitorMinicurso(turma_minicurso=turma),
    )

    assert form.is_valid() is True
    assert form.cleaned_data['aluno'] == aluno


@pytest.mark.django_db
def test_monitor_minicurso_form_clean_aluno_permite_mesmo_aluno_na_edicao(sync_permissions) -> None:
    monitor = MonitorMinicursoFactory()
    form = MonitorMinicursoForm(
        data={'aluno': monitor.aluno.pk, 'carga_horaria': 30},
        instance=monitor,
    )

    assert form.is_valid() is True
    assert form.cleaned_data['aluno'] == monitor.aluno
