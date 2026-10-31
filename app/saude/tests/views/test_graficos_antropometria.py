"""Gráficos - Antropometria (``graficos_antropometria``): gráficos e exportação respeitam o filtro e o campus do usuário."""

import datetime

import openpyxl
import pytest
from django.contrib.auth.models import Group, Permission
from django.test import Client

from comum.models import User
from djtools.models import Task
from djtools.storages.utils import download_temporary_file
from edu.models import Aluno
from edu.tests.factories import AlunoFactory
from rh.models import Servidor
from rh.tests.factories import ServidorFactory
from saude.models import Antropometria, Atendimento, Prontuario, TipoAtendimento
from saude.tests.factories import AntropometriaFactory

URL = '/saude/graficos_antropometria/'
FILTRO_VAZIO = 'data_inicio=&data_termino=&uo='


def _ficha(profissional: User, nascimento: datetime.date = datetime.date(2000, 1, 1), sexo: str = 'M', **medidas: int | None) -> Aluno:
    """Avaliação biomédica aberta por ``profissional`` (o campus da ficha é o dele) com uma antropometria."""
    aluno = AlunoFactory(pessoa_fisica__sexo=sexo, pessoa_fisica__nascimento_data=nascimento)
    atendimento = Atendimento.abrir(TipoAtendimento.AVALIACAO_BIOMEDICA, Prontuario.get_prontuario(aluno.get_vinculo()), aluno, profissional)
    AntropometriaFactory(atendimento=atendimento, profissional=profissional, **medidas)
    return aluno


def _pode_ver_graficos(user: User) -> None:
    user.user_permissions.add(Permission.objects.get(codename='view_atividadegrupo', content_type__app_label='saude'))


@pytest.fixture
def profissional_outro_campus(servidor_profissional: Servidor) -> User:
    servidor = ServidorFactory(cargo_emprego=servidor_profissional.cargo_emprego)
    assert servidor.setor.uo != servidor_profissional.setor.uo
    return servidor.get_user()


def test_exportacao_de_usuario_restrito_so_traz_fichas_do_proprio_campus(
    profissional: Client, servidor_profissional: Servidor, profissional_outro_campus: User
) -> None:
    """Quem não vê os gráficos de todos os campi exporta só as fichas abertas no próprio campus (#17608)."""
    user = servidor_profissional.get_user()
    _pode_ver_graficos(user)
    do_campus = _ficha(user)
    _ficha(user, estatura=0)
    _ficha(profissional_outro_campus)

    resposta = profissional.get(f'{URL}?{FILTRO_VAZIO}&xls=1')

    tarefa = Task.objects.get(uuid=resposta.url.rstrip('/').rsplit('/', 1)[-1])
    linhas = list(openpyxl.load_workbook(download_temporary_file(tarefa.file)).active.iter_rows(values_only=True))
    assert [linha[2] for linha in linhas[1:]] == [do_campus.matricula]


@pytest.mark.parametrize('peso', [None, 0])
def test_ficha_sem_peso_nao_derruba_graficos_nem_exportacao(profissional: Client, servidor_profissional: Servidor, peso: int | None) -> None:
    """Ficha legada sem peso (aluno de 10 a 19 anos) fica fora de gráficos e XLS em vez de dar 500 (#17620)."""
    user = servidor_profissional.get_user()
    _pode_ver_graficos(user)
    adolescente = datetime.date.today().replace(day=1, year=datetime.date.today().year - 15)
    com_peso = _ficha(user, nascimento=adolescente)
    _ficha(user, nascimento=adolescente, peso=peso)

    for url in (URL, '/saude/relatorio_avaliacao_biomedica/?tipo_relatorio=2'):
        resposta = profissional.get(f'{url}{"&" if "?" in url else "?"}{FILTRO_VAZIO}')
        assert resposta.status_code == 200
        assert list(resposta.context['registros'].values_list('atendimento__aluno', flat=True)) == [com_peso.pk]
        (imc_menores,) = [grafico for grafico in resposta.context['pie_chart_lists'] if grafico.id == 'grafico4']
        assert sum(quantidade for _rotulo, quantidade in imc_menores.series[0]['data']) == 1

    resposta = profissional.get(f'{URL}?{FILTRO_VAZIO}&xls=1')
    tarefa = Task.objects.get(uuid=resposta.url.rstrip('/').rsplit('/', 1)[-1])
    linhas = list(openpyxl.load_workbook(download_temporary_file(tarefa.file)).active.iter_rows(values_only=True))
    assert [linha[2] for linha in linhas[1:]] == [com_peso.matricula]


def test_graficos_contam_so_as_fichas_do_campus_filtrado(
    suap_client: Client, servidor_profissional: Servidor, profissional_outro_campus: User
) -> None:
    """Todos os 12 gráficos, inclusive IAC e RCQ, contam só o campus escolhido; o RCQ Geral tem div própria (#17606).

    O campus filtrado tem homem e mulher, maior e menor de 19 anos: sem dado, o gráfico some (#17622).
    """
    coordenador = ServidorFactory(cargo_emprego=servidor_profissional.cargo_emprego).get_user()
    coordenador.groups.add(Group.objects.get(name='Coordenador de Saúde Sistêmico'))
    _pode_ver_graficos(coordenador)
    _ficha(servidor_profissional.get_user())
    adolescente = datetime.date.today().replace(day=1, year=datetime.date.today().year - 15)
    for nascimento in (datetime.date(2000, 1, 1), adolescente):
        for sexo in ('M', 'F'):
            _ficha(profissional_outro_campus, nascimento=nascimento, sexo=sexo)
    suap_client.login(user=coordenador)

    resposta = suap_client.get(f'{URL}?data_inicio=&data_termino=&uo={profissional_outro_campus.get_relacionamento().setor.uo.pk}')

    graficos = resposta.context['pie_chart_lists']
    assert [grafico.id for grafico in graficos] == [f'grafico{n}' for n in range(1, 13)]
    rcq_geral = graficos[9]
    assert rcq_geral.title['text'] == 'Razão Cintura-Quadril (RCQ) - Geral'
    no_campus = Antropometria.objects.filter(atendimento__usuario_aberto=profissional_outro_campus).count()
    assert sum(quantidade for _rotulo, quantidade in rcq_geral.series[0]['data']) == no_campus
    assert '<div id="grafico10"' in resposta.content.decode()
