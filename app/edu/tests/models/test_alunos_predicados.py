"""Testes unitários (sem DB) de predicados/acessores puros de ``Aluno``.

Os atributos de FK (``pessoa_fisica``, ``matriz``, ``curso_campus``) são isolados
com ``patch.object(..., new_callable=PropertyMock)`` (mesmo padrão de ``test_alunos.py``);
campos simples são setados direto na instância. Nenhum teste toca o banco.
"""

import datetime
from contextlib import ExitStack, contextmanager
from unittest.mock import Mock, PropertyMock, patch

from edu.models.alunos import Aluno
from edu.models.cadastros_gerais import NivelEnsino
from edu.models.cursos import EstruturaCurso
from edu.models.diretorias import Diretoria


@contextmanager
def _props(cls, **valores):
    """Substitui temporariamente atributos de ``cls`` por propriedades mockadas."""
    with ExitStack() as stack:
        for nome, valor in valores.items():
            prop = stack.enter_context(patch.object(cls, nome, new_callable=PropertyMock))
            prop.return_value = valor
        yield


# Aluno.get_email foi removido: o resolvedor único agora é a property email_notificacao
# (institucional-first), testada em rh/tests/test_vinculo_properties_papel.py.


# --- get_nome_social_composto ----------------------------------------------


def test_nome_social_composto_com_nome_social():
    with _props(Aluno, pessoa_fisica=Mock(nome_social='João', nome_registro='João Silva')):
        assert Aluno().get_nome_social_composto() == 'João Silva (João)'


def test_nome_social_composto_sem_nome_social_usa_nome():
    with _props(Aluno, pessoa_fisica=Mock(nome_social='', nome='João Silva')):
        assert Aluno().get_nome_social_composto() == 'João Silva'


# --- get_telefones ----------------------------------------------------------


def test_telefones_sem_nenhum_retorna_traco():
    aluno = Aluno()
    aluno.telefone_principal = ''
    aluno.telefone_secundario = ''
    aluno.telefone_adicional_1 = ''
    aluno.telefone_adicional_2 = ''
    assert aluno.get_telefones() == '-'


def test_telefones_concatena_apenas_os_preenchidos():
    aluno = Aluno()
    aluno.telefone_principal = '1111'
    aluno.telefone_secundario = '2222'
    aluno.telefone_adicional_1 = ''
    aluno.telefone_adicional_2 = '4444'
    assert aluno.get_telefones() == '1111, 2222, 4444'


# --- eh_aluno_migrado_apos_conclusao_curso ---------------------------------


def test_migrado_quando_conclusao_anterior_a_integralizacao():
    aluno = Aluno()
    aluno.data_integralizacao = datetime.datetime(2023, 1, 15)
    aluno.dt_conclusao_curso = datetime.date(2023, 1, 10)
    assert aluno.eh_aluno_migrado_apos_conclusao_curso() is True


def test_nao_migrado_quando_conclusao_posterior():
    aluno = Aluno()
    aluno.data_integralizacao = datetime.datetime(2023, 1, 1)
    aluno.dt_conclusao_curso = datetime.date(2023, 2, 1)
    assert aluno.eh_aluno_migrado_apos_conclusao_curso() is False


def test_nao_migrado_sem_datas():
    aluno = Aluno()
    aluno.data_integralizacao = None
    aluno.dt_conclusao_curso = None
    assert not aluno.eh_aluno_migrado_apos_conclusao_curso()


# --- is_credito / is_seriado / is_fic / is_proitec / is_pronatec -----------


def test_is_credito_verdadeiro():
    with _props(Aluno, matriz=Mock(estrutura=Mock(tipo_avaliacao=EstruturaCurso.TIPO_AVALIACAO_CREDITO))):
        assert Aluno().is_credito() is True


def test_is_credito_falso_para_outro_tipo():
    with _props(Aluno, matriz=Mock(estrutura=Mock(tipo_avaliacao=EstruturaCurso.TIPO_AVALIACAO_SERIADO))):
        assert Aluno().is_credito() is False


def test_is_seriado_verdadeiro():
    with _props(Aluno, matriz=Mock(estrutura=Mock(tipo_avaliacao=EstruturaCurso.TIPO_AVALIACAO_SERIADO))):
        assert Aluno().is_seriado() is True


def test_is_fic_verdadeiro():
    with _props(Aluno, matriz=Mock(estrutura=Mock(tipo_avaliacao=EstruturaCurso.TIPO_AVALIACAO_FIC))):
        assert Aluno().is_fic() is True


def test_is_credito_sem_matriz_e_falsy():
    with _props(Aluno, matriz=None):
        assert not Aluno().is_credito()


def test_is_proitec_verdadeiro():
    with _props(Aluno, matriz=Mock(estrutura=Mock(proitec=True))):
        assert Aluno().is_proitec() is True


def test_is_proitec_falso():
    with _props(Aluno, matriz=Mock(estrutura=Mock(proitec=False))):
        assert Aluno().is_proitec() is False


def test_is_pronatec_verdadeiro():
    curso_campus = Mock()
    curso_campus.diretoria.tipo = Diretoria.TIPO_PRONATEC
    with _props(Aluno, curso_campus=curso_campus):
        assert Aluno().is_pronatec() is True


def test_is_pronatec_falso():
    curso_campus = Mock()
    curso_campus.diretoria.tipo = 1
    with _props(Aluno, curso_campus=curso_campus):
        assert Aluno().is_pronatec() is False
