"""Regressão de ``ae/tasks.py``: aluno sem matrícula corrente não derruba a geração da análise.

O ``semestre_atual`` era montado com ``get_matriculas_periodo()[0]``, que estourava
``IndexError`` — e a task inteira respondia 500 — quando o aluno tem caracterização mas
nenhuma matrícula no período corrente (egresso, trancado ou dado legado ainda inscrito).
"""

from types import SimpleNamespace

from ae.tasks import _semestre_atual


def test_semestre_vazio_sem_matricula_corrente():
    """Sem matrícula no período, o campo fica vazio em vez de estourar ``IndexError``."""
    aluno = SimpleNamespace(get_matriculas_periodo=list)
    assert _semestre_atual(aluno) == ''


def test_semestre_com_matricula_corrente():
    """Com matrícula, o campo segue no formato ``periodo/ano`` do período letivo."""
    matricula = SimpleNamespace(periodo_letivo=2, ano_letivo=2024)
    aluno = SimpleNamespace(get_matriculas_periodo=lambda: [matricula])
    assert _semestre_atual(aluno) == '2/2024'
