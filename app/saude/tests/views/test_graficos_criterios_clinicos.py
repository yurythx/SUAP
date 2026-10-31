"""Critérios clínicos dos gráficos de Antropometria e Hábitos de Vida: faixas de IMC, escore-z, IAC e objetivo de uso da internet (#17607)."""

import datetime
from decimal import Decimal

import pytest
from django.contrib.auth.models import Permission
from django.test import Client

from comum.models import User
from edu.tests.factories import AlunoFactory
from rh.models import Servidor
from saude.models import Antropometria, Atendimento, Prontuario, TipoAtendimento
from saude.tests.factories import AntropometriaFactory, HabitosDeVidaFactory
from saude.views import _faixa_iac, _faixa_imc_jovens

FILTRO_VAZIO = 'data_inicio=&data_termino=&uo='


def _atendimento(profissional: User, sexo: str = 'M') -> Atendimento:
    aluno = AlunoFactory(pessoa_fisica__sexo=sexo, pessoa_fisica__nascimento_data=datetime.date(2000, 1, 1))
    return Atendimento.abrir(TipoAtendimento.AVALIACAO_BIOMEDICA, Prontuario.get_prontuario(aluno.get_vinculo()), aluno, profissional)


@pytest.fixture
def usuario(servidor_profissional: Servidor) -> User:
    user = servidor_profissional.get_user()
    user.user_permissions.add(Permission.objects.get(codename='view_atividadegrupo', content_type__app_label='saude'))
    return user


def _grafico(resposta, id_grafico: str):
    """Localiza o gráfico pelo id da div: gráficos sem dado são escondidos (#17622), então a posição não é estável."""
    return next(grafico for grafico in resposta.context['pie_chart_lists'] if grafico.id == id_grafico)


def _dados(resposta, id_grafico: str) -> dict[str, int]:
    return dict(_grafico(resposta, id_grafico).series[0]['data'])


# Com estatura de 100 cm o IMC é o próprio peso, e o IAC é o quadril menos 18.
def test_imc_de_adultos_usa_faixas_continuas_da_oms(profissional: Client, usuario: User) -> None:
    """Cada ficha cai em exatamente uma faixa: sem sobreposição, sem buracos, valores fracionários inclusos."""
    pesos = ['17', '18.49', '18.5', '24.9', '25', '29.5', '30', '34.9', '35', '39.9', '40']
    for peso in pesos:
        AntropometriaFactory(atendimento=_atendimento(usuario), profissional=usuario, estatura=100, peso=Decimal(peso))

    resposta = profissional.get(f'/saude/graficos_antropometria/?{FILTRO_VAZIO}')

    assert _dados(resposta, 'grafico1') == {
        'Excesso de magreza': 2,
        'Peso normal': 2,
        'Acima do peso': 2,
        'Obesidade grau 1': 2,
        'Obesidade grau 2': 2,
        'Obesidade grau 3 ou mórbida': 1,
    }
    assert sum(_dados(resposta, 'grafico1').values()) == len(pesos)


@pytest.mark.parametrize(
    ('escore_z', 'faixa'),
    [
        (Decimal('-3.01'), 'Magreza acentuada'),
        (Decimal('-3'), 'Magreza'),
        (Decimal('-2'), 'Eutrofia'),
        (Decimal('0'), 'Eutrofia'),
        (Decimal('1'), 'Sobrepeso'),
        (Decimal('2'), 'Obesidade'),
        (Decimal('2.99'), 'Obesidade'),
        (Decimal('3'), 'Obesidade grave'),
        (Decimal('3.01'), 'Obesidade grave'),
        (None, None),
    ],
)
def test_faixa_imc_jovens_nas_fronteiras(escore_z: Decimal | None, faixa: str | None) -> None:
    assert _faixa_imc_jovens(escore_z) == faixa


@pytest.mark.parametrize(
    ('escore_z', 'classificacao'),
    [(Decimal('0'), Antropometria.EUTROFIA), (Decimal('3'), Antropometria.OBESIDADE_GRAVE), (None, None)],
)
def test_classificacao_do_model_usa_as_mesmas_faixas_do_grafico(
    usuario: User, monkeypatch: pytest.MonkeyPatch, escore_z: Decimal | None, classificacao: str | None
) -> None:
    """z = 0 é Eutrofia e z = 3 é Obesidade grave também na classificação exibida na ficha."""
    aluno = AlunoFactory(
        pessoa_fisica__sexo='M', pessoa_fisica__nascimento_data=datetime.date.today().replace(year=datetime.date.today().year - 15, day=1)
    )
    atendimento = Atendimento.abrir(TipoAtendimento.AVALIACAO_BIOMEDICA, Prontuario.get_prontuario(aluno.get_vinculo()), aluno, usuario)
    antropometria = AntropometriaFactory(atendimento=atendimento, profissional=usuario)
    monkeypatch.setattr(Antropometria, 'get_imc_jovens', lambda self: escore_z)  # fronteira: a tabela LMS tem o z; aqui só o limite

    assert antropometria.get_classificacao_IMC() == classificacao


@pytest.mark.parametrize(
    ('iac', 'limites', 'faixa'),
    [
        # mulheres: abaixo de 21 | 21 a < 33 | 33 a 38 | > 38
        (20.5, (21, 33, 38), 'Abaixo do normal'),
        (21, (21, 33, 38), 'Normal'),
        (32.5, (21, 33, 38), 'Normal'),
        (33, (21, 33, 38), 'Sobrepeso'),
        (38, (21, 33, 38), 'Sobrepeso'),
        (38.5, (21, 33, 38), 'Obesidade'),
        # homens: abaixo de 8 | 8 a < 21 | 21 a 25 | > 25
        (7, (8, 21, 25), 'Abaixo do normal'),
        (8, (8, 21, 25), 'Normal'),
        (20.5, (8, 21, 25), 'Normal'),
        (21, (8, 21, 25), 'Sobrepeso'),
        (25, (8, 21, 25), 'Sobrepeso'),
        (25.5, (8, 21, 25), 'Obesidade'),
    ],
)
def test_faixa_iac_nas_fronteiras(iac: float, limites: tuple[int, int, int], faixa: str) -> None:
    assert _faixa_iac(iac, *limites) == faixa


def test_graficos_de_iac_contam_valores_fracionarios_e_abaixo_do_normal(profissional: Client, usuario: User) -> None:
    for sexo, quadril in [('F', '38.5'), ('F', '50.5'), ('M', '25'), ('M', '38.5')]:  # IAC 20,5 e 32,5 (F); 7 e 20,5 (M)
        AntropometriaFactory(atendimento=_atendimento(usuario, sexo), profissional=usuario, estatura=100, quadril=Decimal(quadril))

    resposta = profissional.get(f'/saude/graficos_antropometria/?{FILTRO_VAZIO}')

    assert _dados(resposta, 'grafico9') == {'Abaixo do normal': 1, 'Normal': 1, 'Sobrepeso': 0, 'Obesidade': 0}
    assert _dados(resposta, 'grafico8') == {'Abaixo do normal': 1, 'Normal': 1, 'Sobrepeso': 0, 'Obesidade': 0}
    assert _dados(resposta, 'grafico7') == {'Abaixo do normal': 2, 'Normal': 2, 'Sobrepeso': 0, 'Obesidade': 0}


def test_objetivo_de_uso_da_internet_conta_por_ficha(profissional: Client, usuario: User) -> None:
    """Três fichas com a mesma combinação contam 3 por objetivo, não 1 por combinação distinta."""
    for _ in range(3):
        HabitosDeVidaFactory(atendimento=_atendimento(usuario), profissional=usuario, objetivo_uso_internet='Jogos;Redes Sociais')
    HabitosDeVidaFactory(atendimento=_atendimento(usuario), profissional=usuario, objetivo_uso_internet='Trabalho')

    resposta = profissional.get(f'/saude/graficos_habitos_vida/?{FILTRO_VAZIO}')

    assert _grafico(resposta, 'grafico16').title['text'] == 'Objetivo de Uso da Internet'
    assert _dados(resposta, 'grafico16') == {'Pesquisa relacionada a estudo': 0, 'Jogos': 3, 'Redes Sociais': 3, 'Trabalho': 1, 'Outros': 0}
