from contextlib import ExitStack
from unittest.mock import Mock, PropertyMock, patch

import pytest
from django.core.exceptions import ValidationError

from edu.models.alunos import Aluno
from edu.models.cadastros_gerais import NivelEnsino, SituacaoMatricula


@pytest.fixture
def aluno_id():
    return 999


def _configurar_dependencias(stack, retornos=None):
    retornos = retornos or [[], [], [], [], []]
    retorno_matricula_diario, retorno_matricula_resumida, retorno_aproveitamento, retorno_certificacao, retorno_matriz = retornos

    matricula_diario = stack.enter_context(patch('edu.models.alunos.MatriculaDiario.objects'))
    matricula_resumida = stack.enter_context(patch('edu.models.alunos.MatriculaDiarioResumida.objects'))
    aproveitamento = stack.enter_context(patch('edu.models.alunos.AproveitamentoEstudo.objects'))
    certificacao = stack.enter_context(patch('edu.models.alunos.CertificacaoConhecimento.objects'))

    matricula_diario.exclude.return_value.filter.return_value.values_list.return_value = retorno_matricula_diario
    matricula_resumida.filter.return_value.values_list.return_value = retorno_matricula_resumida
    aproveitamento.filter.return_value.values_list.return_value = retorno_aproveitamento
    certificacao.filter.return_value.values_list.return_value = retorno_certificacao

    matriz = PropertyMock()
    matriz.return_value.componentecurricular_set.filter.return_value.values_list.return_value = retorno_matriz

    return matricula_diario, matricula_resumida, aproveitamento, certificacao, matriz


def _assert_filtra_por_aluno_id(matricula_diario, matricula_resumida, aproveitamento, certificacao, aluno_id):
    matricula_diario.exclude.return_value.filter.assert_called_once_with(matricula_periodo__aluno_id=aluno_id)
    matricula_resumida.filter.assert_called_once_with(matricula_periodo__aluno_id=aluno_id)
    aproveitamento.filter.assert_called_once_with(matricula_periodo__aluno_id=aluno_id)
    certificacao.filter.assert_called_once_with(matricula_periodo__aluno_id=aluno_id)


def test_lista_componentes_nao_certificaveis_agrega_todas_as_fontes(aluno_id):
    with ExitStack() as stack:
        matricula_diario, matricula_resumida, aproveitamento, certificacao, matriz = _configurar_dependencias(
            stack,
            retornos=[[1, 2], [3], [4], [5], []],
        )
        stack.enter_context(patch.object(Aluno, 'matriz', matriz))

        aluno = Aluno(id=aluno_id)
        componentes = aluno.get_ids_componentes_nao_certificaveis()

        _assert_filtra_por_aluno_id(matricula_diario, matricula_resumida, aproveitamento, certificacao, aluno_id)
        assert componentes == [1, 2, 3, 4, 5]


def test_lista_componentes_nao_certificaveis_vazia_quando_nao_ha_fontes(aluno_id):
    with ExitStack() as stack:
        _, _, _, _, matriz = _configurar_dependencias(stack)
        stack.enter_context(patch.object(Aluno, 'matriz', matriz))

        aluno = Aluno(id=aluno_id)

        assert aluno.get_ids_componentes_nao_certificaveis() == []


def test_lista_componentes_nao_certificaveis_exclui_situacoes_esperadas(aluno_id):
    situacoes_esperadas = {
        13,  # transferido
        1,  # cursando
        6,  # trancado
        7,  # cancelado
    }

    with ExitStack() as stack:
        matricula_diario, _, _, _, matriz = _configurar_dependencias(stack)
        stack.enter_context(patch.object(Aluno, 'matriz', matriz))

        aluno = Aluno(id=aluno_id)
        aluno.get_ids_componentes_nao_certificaveis()

        args, kwargs = matricula_diario.exclude.call_args
        if 'situacao__in' in kwargs:
            situacao_in = set(kwargs['situacao__in'])
        else:
            q_object = args[0]
            situacao_in = set(dict(q_object.children)['situacao__in'])
        assert situacao_in == situacoes_esperadas


# --- pode_solicitar_atividade_complementar ---------------------------------


def _criar_aluno_para_teste_atividade(
    matricula: str = '2020101001',
    nivel_ensino_id: int = NivelEnsino.GRADUACAO,
    situacao_id: int = SituacaoMatricula.MATRICULADO,
) -> tuple[Aluno, Mock]:
    aluno = Aluno()
    aluno.matricula = matricula
    aluno.situacao_id = situacao_id
    curso_campus = Mock()
    curso_campus.modalidade.nivel_ensino_id = nivel_ensino_id
    curso_campus.modalidade.nivel_ensino.pk = nivel_ensino_id
    return aluno, curso_campus


def test_pode_solicitar_atividade_graduacao_ativa() -> None:
    aluno, curso_campus = _criar_aluno_para_teste_atividade(nivel_ensino_id=NivelEnsino.GRADUACAO)
    user = Mock(username='2020101001', is_authenticated=True)
    with patch.object(Aluno, 'curso_campus', PropertyMock(return_value=curso_campus)):
        assert aluno.pode_solicitar_atividade_complementar(user) is True


def test_pode_solicitar_atividade_pos_graduacao_ativa() -> None:
    aluno, curso_campus = _criar_aluno_para_teste_atividade(
        nivel_ensino_id=NivelEnsino.POS_GRADUACAO,
        situacao_id=SituacaoMatricula.MATRICULA_VINCULO_INSTITUCIONAL,
    )
    user = Mock(username='2020101001', is_authenticated=True)
    with patch.object(Aluno, 'curso_campus', PropertyMock(return_value=curso_campus)):
        assert aluno.pode_solicitar_atividade_complementar(user) is True


def test_pode_solicitar_atividade_medio_com_config_desativada() -> None:
    aluno, curso_campus = _criar_aluno_para_teste_atividade(nivel_ensino_id=NivelEnsino.MEDIO)
    user = Mock(username='2020101001', is_authenticated=True)
    with (
        patch.object(Aluno, 'curso_campus', PropertyMock(return_value=curso_campus)),
        patch('edu.models.alunos.Configuracao.get_valor_por_chave', return_value=False),
    ):
        assert aluno.pode_solicitar_atividade_complementar(user) is False


def test_pode_solicitar_atividade_medio_com_config_ativada() -> None:
    aluno, curso_campus = _criar_aluno_para_teste_atividade(nivel_ensino_id=NivelEnsino.MEDIO)
    user = Mock(username='2020101001', is_authenticated=True)
    with (
        patch.object(Aluno, 'curso_campus', PropertyMock(return_value=curso_campus)),
        patch('edu.models.alunos.Configuracao.get_valor_por_chave', return_value=True),
    ):
        assert aluno.pode_solicitar_atividade_complementar(user) is True


@pytest.mark.parametrize(
    'situacao_inativa',
    [
        SituacaoMatricula.CONCLUIDO,
        SituacaoMatricula.TRANCADO,
        SituacaoMatricula.CANCELADO,
        SituacaoMatricula.JUBILADO,
    ],
)
def test_pode_solicitar_atividade_situacao_inativa_retorna_false(situacao_inativa: int) -> None:
    aluno, curso_campus = _criar_aluno_para_teste_atividade(
        nivel_ensino_id=NivelEnsino.MEDIO,
        situacao_id=situacao_inativa,
    )
    user = Mock(username='2020101001', is_authenticated=True)
    with (
        patch.object(Aluno, 'curso_campus', PropertyMock(return_value=curso_campus)),
        patch('edu.models.alunos.Configuracao.get_valor_por_chave', return_value=True),
    ):
        assert aluno.pode_solicitar_atividade_complementar(user) is False


def test_pode_solicitar_atividade_usuario_diferente_retorna_false() -> None:
    aluno, curso_campus = _criar_aluno_para_teste_atividade(matricula='2020101001')
    outro_user = Mock(username='2020101999', is_authenticated=True)
    with patch.object(Aluno, 'curso_campus', PropertyMock(return_value=curso_campus)):
        assert aluno.pode_solicitar_atividade_complementar(outro_user) is False


def test_pode_solicitar_atividade_usuario_none_ou_anonimo_retorna_false() -> None:
    aluno, curso_campus = _criar_aluno_para_teste_atividade(matricula='2020101001')
    anonimo = Mock(username='')
    with patch.object(Aluno, 'curso_campus', PropertyMock(return_value=curso_campus)):
        assert aluno.pode_solicitar_atividade_complementar(None) is False
        assert aluno.pode_solicitar_atividade_complementar(anonimo) is False


def test_pode_solicitar_atividade_sem_curso_ou_sem_modalidade_retorna_false() -> None:
    aluno = Aluno()
    aluno.matricula = '2020101001'
    aluno.situacao_id = SituacaoMatricula.MATRICULADO
    user = Mock(username='2020101001', is_authenticated=True)

    with patch.object(Aluno, 'curso_campus', PropertyMock(return_value=None)):
        assert aluno.pode_solicitar_atividade_complementar(user) is False

    curso_sem_modalidade = Mock(modalidade=None)
    with patch.object(Aluno, 'curso_campus', PropertyMock(return_value=curso_sem_modalidade)):
        assert aluno.pode_solicitar_atividade_complementar(user) is False


# --- clean_fields / clean ----------------------------------------------------


def test_clean_fields_numero_rg_valido_passa() -> None:
    aluno = Aluno(numero_rg='MG12345678')
    aluno.clean_fields(exclude={f.name for f in aluno._meta.fields if f.name != 'numero_rg'})


def test_clean_fields_numero_rg_invalido_lanca_validation_error() -> None:
    aluno = Aluno(numero_rg='12')
    with pytest.raises(ValidationError) as exc_info:
        aluno.clean_fields(exclude={f.name for f in aluno._meta.fields if f.name != 'numero_rg'})

    assert 'numero_rg' in exc_info.value.message_dict
    assert (
        'O campo "Número do RG" deve ter entre 4 e 15 caracteres e pode conter somente letras e números.' in exc_info.value.message_dict['numero_rg']
    )


def test_clean_fields_numero_rg_invalido_ignorado_quando_em_exclude() -> None:
    aluno = Aluno(numero_rg='1.234.567-8')
    aluno.clean_fields(exclude={'numero_rg', *(f.name for f in aluno._meta.fields if f.name != 'numero_rg')})


def test_clean_fields_numero_rg_vazio_passa() -> None:
    aluno = Aluno(numero_rg='')
    aluno.clean_fields(exclude={f.name for f in aluno._meta.fields if f.name != 'numero_rg'})

    aluno_none = Aluno(numero_rg=None)
    aluno_none.clean_fields(exclude={f.name for f in aluno_none._meta.fields if f.name != 'numero_rg'})
