"""Gráficos - Percepção de Saúde Bucal (``graficos_percepcao_saude_bucal``): gráficos, filtros, escopo de campus e exportação."""

import datetime

import pytest
from django.contrib.auth.models import Group, Permission
from django.http import HttpResponse
from django.test import Client

from edu.tests.factories import AlunoFactory
from rh.models import Servidor
from rh.tests.factories import ServidorFactory
from saude import tasks
from saude.models import Atendimento, PercepcaoSaudeBucal, Prontuario, TipoAtendimento
from saude.tests.factories import DificuldadeOralFactory, PercepcaoSaudeBucalFactory

URL = '/saude/graficos_percepcao_saude_bucal/'
TAREFA = 'graficos_percepcao_saude_bucal_to_xls'
# Ordem das divs no template: os gráficos 6 a 23 são o grau e o motivo de cada uma das nove dificuldades.
IDS_GRAFICOS = (
    ['grafico1', 'grafico2', 'grafico25', 'grafico3', 'grafico4', 'grafico5', 'grafico24', 'grafico26']
    + [f'grafico{n}' for n in range(6, 24)]
    + ['grafico27', 'grafico28', 'grafico29']
)


@pytest.fixture
def perfil(servidor_profissional: Servidor) -> Servidor:
    """O profissional ganha a permissão da tela; ser do grupo sistêmico fica a cargo de cada teste."""
    user = servidor_profissional.get_user()
    user.user_permissions.add(Permission.objects.get(codename='view_atividadegrupo', content_type__app_label='saude'))
    return servidor_profissional


@pytest.fixture
def coordenador(profissional: Client, perfil: Servidor) -> Client:
    """Profissional que vê os gráficos de todos os campi."""
    perfil.get_user().groups.add(Group.objects.get(name='Coordenador de Saúde Sistêmico'))
    return profissional


@pytest.fixture
def fichas(atendimento_aberto: Atendimento, perfil: Servidor) -> dict[str, PercepcaoSaudeBucal]:
    """Uma ficha por campus: a do profissional (``proprio``) e a de um servidor de outro campus (``outro``)."""
    outro_servidor = ServidorFactory()
    outro_aluno = AlunoFactory()
    outro_atendimento = Atendimento.abrir(
        TipoAtendimento.AVALIACAO_BIOMEDICA, Prontuario.get_prontuario(outro_aluno.get_vinculo()), outro_aluno, outro_servidor.get_user()
    )
    return {
        'proprio': PercepcaoSaudeBucalFactory(
            atendimento=atendimento_aberto,
            profissional=perfil.get_user(),
            respondida=True,
        ),
        'outro': PercepcaoSaudeBucalFactory(
            atendimento=outro_atendimento,
            profissional=outro_servidor.get_user(),
            respondida=True,
            foi_dentista_anteriormente=False,
            tempo_ultima_vez_dentista=5,
            qtd_vezes_fio_dental_ultima_semana=0,
        ),
    }


def test_ficha_do_form_atual_esconde_os_graficos_sem_dado(coordenador: Client, atendimento_aberto: Atendimento, perfil: Servidor) -> None:
    """O form não grava mais o grau das dificuldades, as vezes de fio dental nem o consumo de doces (declarado fora do
    ``Meta.fields``): sem dado, esses gráficos somem (#17622)."""
    PercepcaoSaudeBucalFactory(
        atendimento=atendimento_aberto,
        profissional=perfil.get_user(),
        foi_dentista_anteriormente=True,
        tempo_ultima_vez_dentista=2,
        qts_dias_fio_dental_ultima_semana=3,
        dificuldades=True,
        motivo_dificuldade_sorrir=DificuldadeOralFactory(dificuldade='Dor'),
    )

    resposta = coordenador.get(f'{URL}?uo=')

    assert [grafico.id for grafico in resposta.context['pie_chart_lists']] == ['grafico1', 'grafico2', 'grafico5', 'grafico26', 'grafico7']


def _uo(ficha: PercepcaoSaudeBucal) -> int:
    return ficha.atendimento.usuario_aberto.get_relacionamento().setor.uo_id


def _ids(resposta) -> set[int]:
    return set(resposta.context['registros'].values_list('pk', flat=True))


def test_monta_os_vinte_e_seis_graficos(coordenador: Client, fichas: dict) -> None:
    resposta = coordenador.get(f'{URL}?uo=')

    assert resposta.status_code == 200
    assert _ids(resposta) == {ficha.pk for ficha in fichas.values()}
    assert [grafico.id for grafico in resposta.context['pie_chart_lists']] == IDS_GRAFICOS
    assert 'Exportar para XLS' in resposta.content.decode()


def test_filtra_por_campus(coordenador: Client, fichas: dict) -> None:
    resposta = coordenador.get(f'{URL}?uo={_uo(fichas["outro"])}')

    assert _ids(resposta) == {fichas['outro'].pk}


def test_usuario_sem_grupo_sistemico_so_ve_o_proprio_campus(profissional: Client, perfil: Servidor, fichas: dict) -> None:
    resposta = profissional.get(f'{URL}?uo=')

    assert _ids(resposta) == {fichas['proprio'].pk}


def test_filtra_por_periodo_de_cadastro(coordenador: Client, fichas: dict) -> None:
    hoje = datetime.date.today()
    amanha = hoje + datetime.timedelta(days=1)
    formato = '%d/%m/%Y'

    no_periodo = coordenador.get(f'{URL}?data_inicio={hoje:{formato}}&data_termino={amanha:{formato}}')
    fora_do_periodo = coordenador.get(f'{URL}?data_inicio=01/01/2000&data_termino=02/01/2000')

    assert _ids(no_periodo) == {ficha.pk for ficha in fichas.values()}
    assert not fora_do_periodo.context['registros'].exists()
    assert 'pie_chart_lists' not in fora_do_periodo.context
    assert 'A busca realizada não encontrou nenhum resultado.' in fora_do_periodo.content.decode()


def test_exportacao_usa_a_tarefa_da_tela(coordenador: Client, fichas: dict, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tasks, TAREFA, lambda registros: HttpResponse(f'xls:{registros.count()}'))

    resposta = coordenador.get(f'{URL}?uo={_uo(fichas["proprio"])}&xls=1')

    assert resposta.content.decode() == 'xls:1'


def test_exportacao_sem_fichas_no_periodo_ainda_aciona_a_tarefa(coordenador: Client, fichas: dict, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tasks, TAREFA, lambda registros: HttpResponse(f'xls:{registros.count()}'))

    resposta = coordenador.get(f'{URL}?data_inicio=01/01/2000&data_termino=02/01/2000&xls=1')

    assert resposta.content.decode() == 'xls:0'


def test_formulario_invalido_nao_oferece_exportacao(coordenador: Client, fichas: dict, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tasks, TAREFA, lambda registros: pytest.fail('não deve exportar com o formulário inválido'))

    resposta = coordenador.get(f'{URL}?data_inicio=01/01/2020&xls=1')

    conteudo = resposta.content.decode()
    assert 'Informe a data final.' in conteudo
    assert 'Exportar para XLS' not in conteudo
    assert 'pie_chart_lists' not in resposta.context
