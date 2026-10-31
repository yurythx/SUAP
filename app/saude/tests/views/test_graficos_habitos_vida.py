"""Gráficos - Hábitos de Vida (``graficos_habitos_vida``): gráficos, filtros, exportação e restrição por campus."""

import datetime

import pytest
from django.contrib.auth.models import Group, Permission
from django.http import HttpResponse
from django.test import Client

from comum.models import User
from edu.tests.factories import AlunoFactory
from rh.models import Servidor
from rh.tests.factories import ServidorFactory
from saude import tasks
from saude.models import Atendimento, HabitosDeVida, Prontuario, TipoAtendimento
from saude.tests.factories import HabitosDeVidaFactory

URL = '/saude/graficos_habitos_vida/'
IDS_GRAFICOS = [f'grafico{n}' for n in range(1, 19)]
SEM_RESULTADO = 'A busca realizada não encontrou nenhum resultado.'


@pytest.fixture
def usuario(servidor_profissional: Servidor):
    user = servidor_profissional.get_user()
    user.user_permissions.add(Permission.objects.get(codename='view_atividadegrupo', content_type__app_label='saude'))
    return user


@pytest.fixture
def coordenador(profissional: Client, usuario) -> Client:
    """Profissional que vê os gráficos de todos os campi."""
    usuario.groups.add(Group.objects.get(name='Coordenador de Saúde Sistêmico'))
    profissional.login(user=usuario)
    return profissional


# Campos que o form atual não grava (saíram na Demanda 2301; ``horas_sono`` é declarado mas está fora do
# ``Meta.fields``): só fichas antigas os têm preenchidos.
CAMPOS_FORA_DO_FORM = (
    'frequencia_bebida',
    'dificuldade_dormir',
    'horas_sono',
    'refeicoes_por_dia',
    'uso_internet',
    'tempo_uso_internet',
    'objetivo_uso_internet',
)


def _ficha_do_form_atual(atendimento: Atendimento, profissional: User) -> HabitosDeVida:
    """Ficha nova: o que o form grava respondido, os campos fora dele nulos."""
    return HabitosDeVidaFactory(atendimento=atendimento, profissional=profissional, respondida=True, **dict.fromkeys(CAMPOS_FORA_DO_FORM))


@pytest.fixture
def ficha_do_campus(usuario, atendimento_aberto: Atendimento):
    """Ficha antiga de um atendimento aberto pelo profissional (campus do profissional), com os 16 gráficos respondidos."""
    return HabitosDeVidaFactory(atendimento=atendimento_aberto, profissional=usuario, respondida=True)


@pytest.fixture
def ficha_de_outro_campus(sync_permissions):
    """Ficha de um atendimento aberto por um servidor de outro campus."""
    outro = ServidorFactory().get_user()
    aluno = AlunoFactory()
    atendimento = Atendimento.abrir(TipoAtendimento.AVALIACAO_BIOMEDICA, Prontuario.get_prontuario(aluno.get_vinculo()), aluno, outro)
    return HabitosDeVidaFactory(atendimento=atendimento, profissional=outro, objetivo_uso_internet='Trabalho')


def test_monta_os_dezesseis_graficos(coordenador: Client, ficha_do_campus) -> None:
    resposta = coordenador.get(f'{URL}?data_inicio=&data_termino=&uo=')

    assert resposta.status_code == 200
    assert list(resposta.context['registros']) == [ficha_do_campus]
    assert [grafico.id for grafico in resposta.context['pie_chart_lists']] == IDS_GRAFICOS


def test_ficha_do_form_atual_esconde_os_graficos_das_perguntas_removidas(coordenador: Client, usuario, atendimento_aberto: Atendimento) -> None:
    """O form não grava mais objetivo/tempo de internet, sono, refeições...: a ficha nasce com ``None`` (#17609, #17622).

    Sem dado no período, esses gráficos somem em vez de aparecer zerados ou só com "Não Informado".
    """
    _ficha_do_form_atual(atendimento_aberto, usuario)

    resposta = coordenador.get(f'{URL}?data_inicio=&data_termino=&uo=')

    assert resposta.status_code == 200
    escondidos = ['grafico6', 'grafico9', 'grafico10', 'grafico11', 'grafico15', 'grafico16']
    assert [grafico.id for grafico in resposta.context['pie_chart_lists']] == [ident for ident in IDS_GRAFICOS if ident not in escondidos]


def test_periodo_antigo_com_dado_ainda_mostra_o_grafico(coordenador: Client, usuario, atendimento_aberto: Atendimento) -> None:
    """Ficha antiga com o objetivo de uso da internet preenchido mantém o gráfico no período dela; o período recente, não."""
    HabitosDeVidaFactory(atendimento=atendimento_aberto, profissional=usuario, respondida=True)
    # O período é o da abertura do atendimento (#17621).
    Atendimento.objects.filter(pk=atendimento_aberto.pk).update(data_aberto=datetime.datetime(2020, 3, 10, 10, 0))
    aluno = AlunoFactory()
    recente = Atendimento.abrir(TipoAtendimento.AVALIACAO_BIOMEDICA, Prontuario.get_prontuario(aluno.get_vinculo()), aluno, usuario)
    _ficha_do_form_atual(recente, usuario)
    hoje = f'{datetime.date.today():%d/%m/%Y}'

    periodo_antigo = coordenador.get(f'{URL}?data_inicio=01/03/2020&data_termino=31/03/2020&uo=')
    periodo_recente = coordenador.get(f'{URL}?data_inicio={hoje}&data_termino={hoje}&uo=')

    def objetivo(resposta) -> list:
        return [grafico.series[0]['data'] for grafico in resposta.context['pie_chart_lists'] if grafico.id == 'grafico16']

    assert objetivo(periodo_antigo) == [[['Pesquisa relacionada a estudo', 0], ['Jogos', 1], ['Redes Sociais', 1], ['Trabalho', 0], ['Outros', 0]]]
    assert objetivo(periodo_recente) == []


def test_exportacao_usa_a_tarefa_de_xls(coordenador: Client, ficha_do_campus, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tasks, 'graficos_habitos_vida_to_xls', lambda registros: HttpResponse(f'xls:{registros.count()}'))

    resposta = coordenador.get(f'{URL}?data_inicio=&data_termino=&uo=&xls=1')

    assert resposta.content.decode() == 'xls:1'


def test_periodo_sem_fichas_nao_monta_graficos(coordenador: Client, ficha_do_campus) -> None:
    resposta = coordenador.get(f'{URL}?data_inicio=01/01/2000&data_termino=02/01/2000&uo=')

    assert not resposta.context['registros'].exists()
    assert 'pie_chart_lists' not in resposta.context
    assert SEM_RESULTADO in resposta.content.decode()


def test_coordenador_filtra_por_campus(coordenador: Client, ficha_do_campus, ficha_de_outro_campus) -> None:
    todas = coordenador.get(f'{URL}?data_inicio=&data_termino=&uo=')
    do_outro = coordenador.get(f'{URL}?uo={ficha_de_outro_campus.atendimento.usuario_aberto.vinculo.setor.uo_id}')

    assert set(todas.context['registros']) == {ficha_do_campus, ficha_de_outro_campus}
    assert list(do_outro.context['registros']) == [ficha_de_outro_campus]


def test_profissional_so_ve_as_fichas_do_proprio_campus(profissional: Client, usuario, ficha_do_campus, ficha_de_outro_campus) -> None:
    resposta = profissional.get(f'{URL}?data_inicio=&data_termino=&uo=')

    assert list(resposta.context['registros']) == [ficha_do_campus]
