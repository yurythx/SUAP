"""Filtro de período das telas de atendimentos: o último dia do período entra (``data_aberto`` é datetime)."""

import datetime

import pytest
from django.contrib.auth.models import Group, Permission
from django.test import Client

from edu.models import Aluno
from rh.models import Servidor
from saude.models import Atendimento, Prontuario, TipoAtendimento

# tela: (url, parâmetros de data, tipo do atendimento, nome da variável de contexto com os atendimentos filtrados)
TELAS = {
    'indicadores': ('/saude/indicadores/', 'data_inicio={d}&data_termino={d}', TipoAtendimento.AVALIACAO_BIOMEDICA, 'atendimentos'),
    'odontologicos': (
        '/saude/relatorios_atendimentos_odontologicos/',
        'data_inicial={d}&data_final={d}',
        TipoAtendimento.ODONTOLOGICO,
        'atendimentos',
    ),
}


@pytest.fixture
def coordenador(profissional: Client, servidor_profissional: Servidor) -> Client:
    """Profissional que vê os relatórios de todos os campi."""
    user = servidor_profissional.get_user()
    user.groups.add(Group.objects.get(name='Coordenador de Saúde Sistêmico'))
    user.user_permissions.add(Permission.objects.get(codename='view_prontuario', content_type__app_label='saude'))
    return profissional


@pytest.mark.parametrize('tela', TELAS)
def test_periodo_de_um_dia_inclui_os_atendimentos_de_hoje(
    coordenador: Client, servidor_profissional: Servidor, prontuario: Prontuario, aluno: Aluno, tela: str
) -> None:
    url, datas, tipo, variavel = TELAS[tela]
    atendimento = Atendimento.abrir(tipo, prontuario, aluno, servidor_profissional.get_user())
    hoje = f'{datetime.date.today():%d/%m/%Y}'

    resposta = coordenador.get(f'{url}?{datas.format(d=hoje)}')

    assert resposta.status_code == 200
    assert atendimento in resposta.context[variavel]
