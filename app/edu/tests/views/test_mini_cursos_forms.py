from __future__ import annotations

from inspect import unwrap
from unittest.mock import MagicMock, patch

from edu.forms.mini_cursos import AdicionarParticipanteTurmaMinicursoForm, ImportarParticipantesTurmaMinicursoForm


def test_adicionar_participante_turma_minicurso_processar_usa_aluno_do_participante() -> None:
    turma = MagicMock()
    mock_participante = MagicMock()
    mock_aluno = MagicMock()
    mock_vinculo = MagicMock()
    mock_aluno.get_vinculo.return_value = mock_vinculo
    mock_participante.aluno = mock_aluno
    turma.adicionar_novo_aluno.return_value = mock_participante

    form = AdicionarParticipanteTurmaMinicursoForm(turma_minicurso=turma)
    form.cleaned_data = {'cpf': '12345678901', 'nome': 'Aluno Teste', 'email': 'teste@exemplo.com'}

    with patch('edu.forms.mini_cursos.PessoaFisica.objects.obter_ou_criar', return_value=(MagicMock(), True)):
        unwrap(form.processar)(form)

    turma.adicionar_novo_aluno.assert_called_once()
    assert mock_vinculo.email_pessoal == 'teste@exemplo.com'
    mock_vinculo.save.assert_called_once_with(update_fields=['email_pessoal'])


def test_importar_participantes_turma_minicurso_processar_usa_aluno_do_participante() -> None:
    turma = MagicMock()
    mock_participante = MagicMock()
    mock_aluno = MagicMock()
    mock_vinculo = MagicMock()
    mock_aluno.get_vinculo.return_value = mock_vinculo
    mock_participante.aluno = mock_aluno
    turma.adicionar_novo_aluno.return_value = mock_participante

    form = ImportarParticipantesTurmaMinicursoForm(turma_minicurso=turma)
    form.participantes = [{'cpf': '12345678901', 'nome': 'Aluno Teste', 'email': 'planilha@exemplo.com'}]

    with patch('edu.forms.mini_cursos.PessoaFisica.objects.obter_ou_criar', return_value=(MagicMock(), True)):
        form.processar()

    turma.adicionar_novo_aluno.assert_called_once()
    assert mock_vinculo.email_pessoal == 'planilha@exemplo.com'
    mock_vinculo.save.assert_called_once_with(update_fields=['email_pessoal'])
