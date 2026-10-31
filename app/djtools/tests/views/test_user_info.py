"""Privacidade das informações exibidas no popup de usuários."""

import pytest
from django.template.loader import render_to_string


@pytest.mark.parametrize('requisitante_eh_aluno', [True, False])
@pytest.mark.parametrize(
    ('identificador', 'cpf', 'eh_prestador', 'identificador_para_aluno'),
    [
        ('12345678909', '123.456.789-09', True, '***.456.789-**'),
        ('AB123456', '', True, 'AB123456'),
        ('1234567', '123.456.789-09', False, '1234567'),
    ],
)
def test_popup_mascara_cpf_e_oculta_outros_vinculos_para_aluno(
    requisitante_eh_aluno: bool, identificador: str, cpf: str, eh_prestador: bool, identificador_para_aluno: str
) -> None:
    """O aluno vê CPF mascarado, sem afetar passaporte ou matrícula institucional."""
    outra_matricula = '20262011280001'
    html = render_to_string(
        'user_info.html',
        {
            'eh_pessoafisica': True,
            'requisitante_eh_aluno': requisitante_eh_aluno,
            'nome': 'Pessoa de Exemplo',
            'profile': {'id': 1, 'eh_prestador': eh_prestador, 'cpf': cpf},
            'user': {'username': identificador},
            'vinculo': {'eh_prestador': eh_prestador},
            'tem_mais_de_1_vinculo': True,
            'vinculos': [
                {'get_relacionamento_title': 'Aluno', 'relacionamento': {'matricula': outra_matricula, 'get_absolute_url': '/edu/aluno/exemplo/'}},
            ],
        },
    )

    assert 'Pessoa de Exemplo' in html
    if requisitante_eh_aluno:
        assert identificador_para_aluno in html
        if identificador_para_aluno != identificador:
            assert identificador not in html
        assert outra_matricula not in html
        assert 'Outros vínculos' not in html
    else:
        assert identificador in html
        assert outra_matricula in html
        assert 'Outros vínculos' in html
