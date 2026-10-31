from __future__ import annotations

from unittest.mock import Mock, PropertyMock, patch

import pytest
from django import forms
from django.core.exceptions import ValidationError
from django.db import transaction

from edu.forms.alunos import AlterarMatrizAlunoForm
from edu.forms.mini_cursos import MinicursoForm
from edu.models.alunos import Aluno
from edu.models.cadastros_gerais import Modalidade
from edu.models.cursos import CursoCampus, Diretoria, Minicurso


@pytest.fixture(autouse=True)
def _mock_atomic_in_tests():
    """Permite exercitar métodos decorados com @transaction.atomic sem exigir conexão com Postgres."""
    with (
        patch.object(transaction.Atomic, '__enter__', return_value=None),
        patch.object(transaction.Atomic, '__exit__', return_value=None),
    ):
        yield


def test_minicurso_save_atribui_modalidade_fic_menos() -> None:
    minicurso = Minicurso(ch_total=40, tipo_hora_aula=60)
    minicurso.codigo = '0001.CNAT'

    with patch.object(CursoCampus, 'save', return_value=None):
        minicurso.save()

    assert minicurso.modalidade_id == Modalidade.FIC_MENOS


def test_minicurso_form_save_atribui_modalidade_fic_menos() -> None:
    form = MinicursoForm.__new__(MinicursoForm)
    form.cleaned_data = {'descricao_certificado': 'Python Básico'}
    instance = Minicurso()
    form.instance = instance

    with patch.object(forms.ModelForm, 'save', return_value=instance):
        resultado = form.save(commit=False)

    assert resultado.modalidade_id == Modalidade.FIC_MENOS
    assert resultado.descricao == 'FIC- Python Básico'
    assert resultado.descricao_historico == 'Python Básico'


def test_minicurso_clonar_atribui_modalidade_fic_menos() -> None:
    minicurso = Minicurso(id=1, ch_total=30, tipo_hora_aula=60)
    minicurso.codigo = '0001.CNAT'

    diretoria = Diretoria(id=10)
    conteudo_mock = Mock()
    mock_manager = Mock()
    mock_manager.all.return_value = [conteudo_mock]

    with (
        patch.object(Minicurso, 'conteudominicurso_set', new_callable=PropertyMock, return_value=mock_manager),
        patch.object(Minicurso, 'save', return_value=None),
    ):
        minicurso.clonar([diretoria])

    assert minicurso.modalidade_id == Modalidade.FIC_MENOS


def test_aluno_nao_fic_exclui_modalidade_fic_menos() -> None:
    qs = Aluno.nao_fic.all()
    query_str = str(qs.query)
    assert f'modalidade_id NOT IN ({Modalidade.FIC}, {Modalidade.PROEJA_FIC_FUNDAMENTAL}, {Modalidade.FIC_MENOS})' in query_str or (
        str(Modalidade.FIC_MENOS) in query_str and 'NOT' in query_str
    )


def test_aluno_minicurso_clean_com_matriz_lanca_validation_error() -> None:
    curso = CursoCampus(modalidade_id=Modalidade.FIC_MENOS)
    aluno = Aluno(curso_campus=curso, matriz_id=99)
    with pytest.raises(ValidationError) as exc_info:
        aluno.clean()
    assert 'matriz' in exc_info.value.message_dict


def test_aluno_minicurso_save_com_matriz_lanca_validation_error() -> None:
    curso = CursoCampus(modalidade_id=Modalidade.FIC_MENOS)
    aluno = Aluno(curso_campus=curso, matriz_id=99)
    with pytest.raises(ValidationError) as exc_info:
        aluno.save()
    assert 'Alunos de curso FIC- (Minicurso) não podem ter matriz curricular informada.' in str(exc_info.value)


def test_alterar_matriz_aluno_form_rejeita_minicurso() -> None:
    form = AlterarMatrizAlunoForm.__new__(AlterarMatrizAlunoForm)
    curso = CursoCampus(modalidade_id=Modalidade.FIC_MENOS)
    form.instance = Aluno(curso_campus=curso)
    form.cleaned_data = {}
    form._errors = {}

    with patch.object(forms.ModelForm, 'clean', return_value={}):
        with pytest.raises(forms.ValidationError) as exc_info:
            form.clean()
        assert 'Alunos de curso FIC- (Minicurso) não possuem matriz curricular.' in str(exc_info.value)


def test_minicurso_clean_forca_modalidade_fic_menos() -> None:
    minicurso = Minicurso(ch_total=40, tipo_hora_aula=60, modalidade_id=Modalidade.FIC)
    minicurso.clean()
    assert minicurso.modalidade_id == Modalidade.FIC_MENOS


def test_minicurso_clean_com_matriz_lanca_validation_error() -> None:
    minicurso = Minicurso(id=1, ch_total=40, tipo_hora_aula=60)
    mock_mc = Mock()
    mock_mc.exists.return_value = True
    with patch.object(Minicurso, 'matrizcurso_set', new_callable=PropertyMock, return_value=mock_mc):
        with pytest.raises(ValidationError) as exc_info:
            minicurso.clean()
        assert 'Minicursos não podem possuir matriz curricular.' in str(exc_info.value)


def test_minicurso_save_com_matriz_lanca_validation_error() -> None:
    minicurso = Minicurso(id=1, ch_total=40, tipo_hora_aula=60)
    mock_mc = Mock()
    mock_mc.exists.return_value = True
    with patch.object(Minicurso, 'matrizcurso_set', new_callable=PropertyMock, return_value=mock_mc):
        with pytest.raises(ValidationError) as exc_info:
            minicurso.save()
        assert 'Minicursos não podem possuir matriz curricular.' in str(exc_info.value)


def test_cursocampus_regular_novo_com_modalidade_fic_menos_rejeita_clean() -> None:
    curso = CursoCampus(modalidade_id=Modalidade.FIC_MENOS, codigo='CC001')
    with patch.object(CursoCampus.objects, 'filter') as mock_filter:
        mock_filter.return_value.exclude.return_value.exists.return_value = False
        with pytest.raises(ValidationError) as exc_info:
            curso.clean()
        assert 'modalidade' in exc_info.value.message_dict


def test_cursocampus_regular_novo_com_modalidade_fic_menos_rejeita_save() -> None:
    curso = CursoCampus(modalidade_id=Modalidade.FIC_MENOS, codigo='CC001')
    with pytest.raises(ValidationError) as exc_info:
        curso.save()
    assert 'A modalidade FIC- é exclusiva de Minicursos.' in str(exc_info.value)


def test_cursocampus_regular_com_matriz_rejeita_fic_menos() -> None:
    curso = CursoCampus(id=10, modalidade_id=Modalidade.FIC_MENOS, ch_total=40)
    mock_mc = Mock()
    mock_mc.exists.return_value = True
    with patch.object(CursoCampus, 'matrizcurso_set', new_callable=PropertyMock, return_value=mock_mc):
        with pytest.raises(ValidationError) as exc_info:
            curso.save()
        assert 'Cursos da modalidade FIC- (Minicurso) não podem ter matrizes associadas.' in str(exc_info.value)


def test_matrizcurso_clean_rejeita_minicurso() -> None:
    from edu.models.cursos import MatrizCurso

    curso = CursoCampus(id=1, modalidade_id=Modalidade.FIC_MENOS)
    matriz_curso = MatrizCurso(curso_campus=curso)
    with pytest.raises(ValidationError) as exc_info:
        matriz_curso.clean()
    assert 'curso_campus' in exc_info.value.message_dict


def test_matrizcurso_save_rejeita_minicurso() -> None:
    from edu.models.cursos import MatrizCurso

    curso = CursoCampus(id=1, modalidade_id=Modalidade.FIC_MENOS)
    matriz_curso = MatrizCurso(curso_campus=curso)
    with pytest.raises(ValidationError) as exc_info:
        matriz_curso.save()
    assert 'Cursos da modalidade FIC- (Minicurso) não podem possuir matriz curricular.' in str(exc_info.value)


def test_aluno_eh_aluno_minicurso_sem_curso_campus_retorna_false() -> None:
    aluno = Aluno()
    aluno.curso_campus = None
    assert aluno.eh_aluno_minicurso() is False


def test_cursocampus_form_clean_modalidade_rejeita_fic_menos() -> None:
    from edu.forms.cursos import CursoCampusForm

    form = CursoCampusForm.__new__(CursoCampusForm)
    form.cleaned_data = {'modalidade': Modalidade(id=Modalidade.FIC_MENOS), 'mesmo_curso': None}
    with pytest.raises(forms.ValidationError) as exc_info:
        form.clean_modalidade()
    assert 'A modalidade FIC- é exclusiva de Minicursos' in str(exc_info.value)


def test_matrizcurso_form_clean_rejeita_minicurso() -> None:
    from edu.forms.cursos import MatrizCursoForm

    form = MatrizCursoForm.__new__(MatrizCursoForm)
    curso = CursoCampus(id=1, modalidade_id=Modalidade.FIC_MENOS)
    form.cleaned_data = {'curso_campus': curso}
    form._errors = {}
    with patch.object(forms.ModelForm, 'clean', return_value=form.cleaned_data):
        with pytest.raises(forms.ValidationError) as exc_info:
            form.clean()
        assert 'Cursos da modalidade FIC- (Minicurso) não podem possuir matriz curricular.' in str(exc_info.value)
