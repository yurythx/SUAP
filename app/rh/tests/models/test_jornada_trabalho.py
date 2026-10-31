import pytest

from rh.tests.factories import JornadaTrabalhoFactory


@pytest.mark.parametrize(
    ('nome', 'semanal', 'diaria'),
    [
        ('40 HORAS SEMANAIS', 40, 8),
        ('DEDICACAO EXCLUSIVA', 40, 8),
        ('30 HORAS SEMANAIS', 30, 6),
        ('25 HORAS SEMANAIS', 25, 5),
        ('20 HORAS SEMANAIS', 20, 4),
        ('44 HORAS SEMANAIS', 44, 8.8),
        ('32,5 HORAS SEMANAIS', 32.5, 6.5),
        ('JORNADA SEM HORAS', None, None),
    ],
)
def test_jornada_semanal_e_diaria_vem_do_nome(nome: str, semanal: float | None, diaria: float | None) -> None:
    jornada = JornadaTrabalhoFactory.build(nome=nome)
    assert jornada.get_jornada_trabalho_semanal() == semanal
    assert jornada.get_jornada_trabalho_diaria() == diaria


def test_jornada_inteira_continua_int() -> None:
    jornada = JornadaTrabalhoFactory.build(nome='40 HORAS SEMANAIS')
    assert type(jornada.get_jornada_trabalho_semanal()) is int
    assert type(jornada.get_jornada_trabalho_diaria()) is int


def test_jornada_semanal_abreviada() -> None:
    assert JornadaTrabalhoFactory.build(nome='DEDICACAO EXCLUSIVA').get_jornada_trabalho_semanal_abreviada() == 'DE'
    assert JornadaTrabalhoFactory.build(nome='36 HORAS SEMANAIS').get_jornada_trabalho_semanal_abreviada() == '36h'
    assert JornadaTrabalhoFactory.build(nome='JORNADA SEM HORAS').get_jornada_trabalho_semanal_abreviada() is None
