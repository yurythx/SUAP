"""Telas de detalhe dos atendimentos x perguntas novas da Demanda 2301 (#17626).

Ficha nova: campos novos preenchidos e os antigos nulos. Ficha antiga: o contrário.
A tela mostra as perguntas que a ficha tem, sem "talvez" nem pergunta vazia.
"""

import re
from decimal import Decimal

import pytest
from django.test import Client

from edu.models import Aluno
from rh.models import Servidor
from saude.models import Atendimento, DificuldadeOral, Prontuario, TipoAtendimento
from saude.tests.factories import (
    DificuldadeOralFactory,
    GrupoAlimentoFactory,
    HabitosDeVidaFactory,
    NutricaoAlimentacaoFactory,
    PercepcaoSaudeBucalFactory,
    ProcessoSaudeDoencaFactory,
)


@pytest.fixture
def nutricional(profissional: Client, aluno: Aluno, prontuario: Prontuario, servidor_profissional: Servidor) -> Atendimento:
    return Atendimento.abrir(TipoAtendimento.NUTRICIONAL, prontuario, aluno, servidor_profissional.get_user())


@pytest.fixture
def odontologico(profissional: Client, aluno: Aluno, prontuario: Prontuario, servidor_profissional: Servidor) -> Atendimento:
    return Atendimento.abrir(TipoAtendimento.ODONTOLOGICO, prontuario, aluno, servidor_profissional.get_user())


def _ficha(atendimento: Atendimento, servidor: Servidor) -> dict:
    return {'atendimento': atendimento, 'profissional': servidor.get_user()}


def _abrir(cliente: Client, rota: str, atendimento: Atendimento) -> str:
    resposta = cliente.get(f'/saude/{rota}/{atendimento.id}/')
    assert resposta.status_code == 200
    return resposta.content.decode()


# Item 1: hábitos de vida no atendimento nutricional


def test_nutricional_habitos_ficha_nova(profissional: Client, nutricional: Atendimento, servidor_profissional: Servidor) -> None:
    ficha = _ficha(nutricional, servidor_profissional)
    HabitosDeVidaFactory(
        **ficha,
        atividade_fisica=False,
        usa_drogas=False,
        vida_sexual_ativa=False,
        fuma=True,
        idade_fumo='15',
        frequencia_uso_fumo='4 ou mais por semana',
        bebe=True,
        idade_bebida='16',
        frequencia_uso_bebida='2 a 4x por mês',
    )
    NutricaoAlimentacaoFactory(**ficha, refeicoes_por_dia='4 refeições')

    html = _abrir(profissional, 'atendimento_nutricional', nutricional)

    assert '4 ou mais por semana' in html
    assert '2 a 4x por mês' in html
    assert 'Experimentou inicialmente com que idade (ano): 15' in html
    assert 'Experimentou inicialmente com que idade (ano): 16' in html
    assert '4 refeições' in html
    # Sono e internet saíram do formulário: a pergunta não existe na ficha nova.
    assert 'talvez' not in html
    assert 'Tem dificuldade para dormir' not in html
    assert 'Faz uso de internet' not in html


def test_nutricional_habitos_ficha_antiga(profissional: Client, nutricional: Atendimento, servidor_profissional: Servidor) -> None:
    HabitosDeVidaFactory(**_ficha(nutricional, servidor_profissional), respondida=True, frequencia_fumo=Decimal('10.0'))

    html = _abrir(profissional, 'atendimento_nutricional', nutricional)

    assert 'Número de cigarros por dia: 10' in html
    assert 'Frequência mínima de ingestão de bebidas alcoólicas: 1x/dia' in html
    assert 'Tem dificuldade para dormir' in html
    assert 'Horas de sono diárias: 8 ou mais horas/dia' in html
    assert '3 refeições' in html
    assert 'Faz uso de internet' in html
    assert 'Qual o tempo de uso: 2 a 3 horas/dia' in html


# Item 2: percepção de saúde bucal no atendimento odontológico


def _percepcao_nova(ficha: dict) -> DificuldadeOral:
    motivo = DificuldadeOralFactory(dificuldade='Dor ao mastigar')
    PercepcaoSaudeBucalFactory(**ficha, dificuldades=True, motivo_dificuldade_comer=motivo, motivo_dificuldade_estudar_trabalhar=motivo)
    return motivo


def test_odontologico_percepcao_ficha_nova(profissional: Client, odontologico: Atendimento, servidor_profissional: Servidor) -> None:
    _percepcao_nova(_ficha(odontologico, servidor_profissional))

    html = _abrir(profissional, 'atendimento_odontologico', odontologico)

    assert 'Grau de dificuldade em estudar/trabalhar' in html
    assert 'Dor ao mastigar' in html
    # Sem grau gravado, a coluna deriva Sim/Não da presença do motivo.
    assert re.search(r'Grau de dificuldade em comer</td>\s*<td><span[^>]*>Sim</span>', html)
    assert re.search(r'Grau de dificuldade em sorrir</td>\s*<td><span[^>]*>Não</span>', html)
    assert 'Grau de dificuldade em estudar</td>' not in html
    assert 'Grau de dificuldade em trabalhar</td>' not in html


def test_odontologico_percepcao_ficha_antiga(profissional: Client, odontologico: Atendimento, servidor_profissional: Servidor) -> None:
    PercepcaoSaudeBucalFactory(**_ficha(odontologico, servidor_profissional), respondida=True)

    html = _abrir(profissional, 'atendimento_odontologico', odontologico)

    assert 'Grau de dificuldade em estudar</td>' in html
    assert 'Grau de dificuldade em trabalhar</td>' in html
    assert '>Alto</span>' in html
    assert 'estudar/trabalhar' not in html


# Item 3: fio dental na avaliação biomédica


def test_biomedica_fio_dental_nao_mantem_a_pergunta(profissional: Client, atendimento_aberto: Atendimento, servidor_profissional: Servidor) -> None:
    PercepcaoSaudeBucalFactory(**_ficha(atendimento_aberto, servidor_profissional), usa_fio_dental=False, qtd_por_dia_consome_acucar='Uma vez')

    html = _abrir(profissional, 'avaliacao_biomedica', atendimento_aberto)

    assert 'Usa fio dental' in html
    assert 'Em quantos dias você usou o fio dental' not in html


def test_biomedica_fio_dental_sim_mostra_os_dias(profissional: Client, atendimento_aberto: Atendimento, servidor_profissional: Servidor) -> None:
    PercepcaoSaudeBucalFactory(**_ficha(atendimento_aberto, servidor_profissional), usa_fio_dental=True, qts_dias_fio_dental_ultima_semana=5)

    html = _abrir(profissional, 'avaliacao_biomedica', atendimento_aberto)

    assert 'Usa fio dental' in html
    assert 'Em quantos dias você usou o fio dental' in html


# Item 4: processo saúde-doença


@pytest.mark.parametrize(('rota', 'tipo'), [('atendimento_nutricional', 'nutricional'), ('atendimento_odontologico', 'odontologico')])
def test_processo_ficha_nova_nao_mostra_perguntas_vazias(
    request: pytest.FixtureRequest, profissional: Client, servidor_profissional: Servidor, rota: str, tipo: str
) -> None:
    atendimento = request.getfixturevalue(tipo)
    ProcessoSaudeDoencaFactory(**_ficha(atendimento, servidor_profissional))

    html = _abrir(profissional, rota, atendimento)

    assert 'Alergias a alimentos' not in html
    assert 'Transtorno psiquiátrico' not in html
    assert 'Procurou algum psiquiatra' not in html


@pytest.mark.parametrize(('rota', 'tipo'), [('atendimento_nutricional', 'nutricional'), ('atendimento_odontologico', 'odontologico')])
def test_processo_mostra_alergia_alimentar_da_nutricao(
    request: pytest.FixtureRequest, profissional: Client, servidor_profissional: Servidor, rota: str, tipo: str
) -> None:
    atendimento = request.getfixturevalue(tipo)
    ficha = _ficha(atendimento, servidor_profissional)
    ProcessoSaudeDoencaFactory(**ficha)
    nutricao = NutricaoAlimentacaoFactory(**ficha, tem_alergia_alimentos=True, alergia_alimentos_outros='Kiwi')
    nutricao.alergia_alimentos.add(GrupoAlimentoFactory(descricao='Laticínios'))

    html = _abrir(profissional, rota, atendimento)

    assert 'Alergias a alimentos' in html
    assert 'Laticínios' in html
    assert 'Kiwi' in html


def test_processo_ficha_antiga_mantem_alergia_alimentar(profissional: Client, nutricional: Atendimento, servidor_profissional: Servidor) -> None:
    ProcessoSaudeDoencaFactory(
        **_ficha(nutricional, servidor_profissional),
        alergia_alimentos=True,
        que_alimentos='Amendoim',
        transtorno_psiquiatrico=True,
        qual_transtorno_psiquiatrico='Ansiedade',
        psiquiatra=True,
    )

    html = _abrir(profissional, 'atendimento_nutricional', nutricional)

    assert 'Amendoim' in html
    assert 'Transtorno psiquiátrico' in html
    assert 'Ansiedade' in html
    assert 'Procurou algum psiquiatra' in html
