from __future__ import annotations

from edu.forms.alunos import AtualizarDadosSISTECAlunoForm
from edu.models.alunos import Aluno


def test_atualizar_dados_sistec_aluno_form_valido_mesmo_com_rg_legado_invalido() -> None:
    # Aluno existente no banco com RG em formato legado fora do regex ^[a-zA-Z0-9]{4,15}$
    aluno = Aluno(
        numero_rg='1.234.567-8',
        data_inicio_ciclo=None,
        data_prevista_termino_ciclo=None,
        codigo_sistec=None,
    )

    data = {
        'data_inicio_ciclo': '10/02/2025',
        'data_prevista_termino_ciclo': '20/12/2028',
        'codigo_sistec': '123456789',
    }

    form = AtualizarDadosSISTECAlunoForm(data=data, instance=aluno)

    assert form.is_valid() is True
    assert 'numero_rg' not in form.errors
    assert not form.non_field_errors()
