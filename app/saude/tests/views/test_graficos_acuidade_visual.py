"""Tela de gráficos da acuidade visual: ramo do relatório de avaliação (tipo 1) com filtros e exportação próprios."""

import datetime

import pytest
from django.contrib.auth.models import Group, Permission
from django.http import HttpResponse
from django.test import Client

from rh.models import Servidor
from rh.tests.factories import ServidorFactory
from saude import tasks
from saude.models import AcuidadeVisual, Atendimento, Prontuario, TipoAtendimento
from saude.tests.factories import AcuidadeVisualFactory

GRAFICOS = '/saude/graficos_acuidade_visual/'
SEM_FILTRO = '?data_inicio=&data_termino=&uo='
# `_filtrar_periodo_e_campus` compara datetime com date: o período precisa cobrir hoje com folga.
HOJE = datetime.date.today()
PERIODO = f'?data_inicio={(HOJE - datetime.timedelta(days=1)):%d/%m/%Y}&data_termino={(HOJE + datetime.timedelta(days=1)):%d/%m/%Y}&uo='


@pytest.fixture
def ficha_do_campus(atendimento_aberto: Atendimento, servidor_profissional: Servidor) -> AcuidadeVisual:
    """Ficha aberta no campus do profissional logado."""
    return AcuidadeVisualFactory(
        atendimento=atendimento_aberto, profissional=servidor_profissional.get_user(), olho_esquerdo='20/20', olho_direito='20/30', com_correcao=True
    )


@pytest.fixture
def ficha_outro_campus(db: None) -> AcuidadeVisual:
    """Ficha aberta por um médico de outro campus."""
    medico = ServidorFactory().get_user()
    medico.groups.add(Group.objects.get(name='Médico'))
    paciente = ServidorFactory()
    prontuario = Prontuario.get_prontuario(paciente.get_vinculo())
    atendimento = Atendimento.abrir(TipoAtendimento.ENFERMAGEM_MEDICO, prontuario, paciente, medico)
    return AcuidadeVisualFactory(atendimento=atendimento, profissional=medico, olho_esquerdo='20/50', olho_direito='20/50', com_correcao=False)


def _com_permissao(profissional: Client, servidor: Servidor, *grupos: str) -> Client:
    user = servidor.get_user()
    user.user_permissions.add(Permission.objects.get(codename='view_atividadegrupo', content_type__app_label='saude'))
    for grupo in grupos:
        user.groups.add(Group.objects.get(name=grupo))
    return profissional


@pytest.fixture
def coordenador(profissional: Client, servidor_profissional: Servidor) -> Client:
    """Vê as fichas de todos os campi."""
    return _com_permissao(profissional, servidor_profissional, 'Coordenador de Saúde Sistêmico')


@pytest.fixture
def restrito(profissional: Client, servidor_profissional: Servidor) -> Client:
    """Fora de ``GRUPOS_VE_GRAFICOS_TODOS``: só vê as fichas do próprio campus."""
    return _com_permissao(profissional, servidor_profissional)


def test_monta_os_tres_graficos_no_periodo(coordenador: Client, ficha_do_campus: AcuidadeVisual, ficha_outro_campus: AcuidadeVisual) -> None:
    resposta = coordenador.get(GRAFICOS + PERIODO)

    assert resposta.status_code == 200
    assert set(resposta.context['registros']) == {ficha_do_campus, ficha_outro_campus}
    assert [grafico.id for grafico in resposta.context['pie_chart_lists']] == ['grafico3', 'grafico1', 'grafico2']
    assert 'Exportar para XLS' in resposta.content.decode()


def test_filtra_por_campus(coordenador: Client, ficha_do_campus: AcuidadeVisual, ficha_outro_campus: AcuidadeVisual) -> None:
    campus_do_medico = ficha_outro_campus.atendimento.usuario_aberto.vinculo.setor.uo_id

    resposta = coordenador.get(f'{GRAFICOS}?data_inicio=&data_termino=&uo={campus_do_medico}')

    assert list(resposta.context['registros']) == [ficha_outro_campus]


def test_exporta_xls_das_fichas_filtradas(
    coordenador: Client, ficha_do_campus: AcuidadeVisual, ficha_outro_campus: AcuidadeVisual, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        tasks, 'exportar_graficos_acuidade_visual_to_xls', lambda registros: HttpResponse(f'xls:{sorted(registros.values_list("pk", flat=True))}')
    )

    resposta = coordenador.get(f'{GRAFICOS}{PERIODO}&xls=1')

    assert resposta.content.decode() == f'xls:{sorted([ficha_do_campus.pk, ficha_outro_campus.pk])}'


def test_restrito_so_ve_o_proprio_campus(restrito: Client, ficha_do_campus: AcuidadeVisual, ficha_outro_campus: AcuidadeVisual) -> None:
    resposta = restrito.get(GRAFICOS + SEM_FILTRO)

    assert list(resposta.context['registros']) == [ficha_do_campus]


def test_sem_filtro_pede_os_filtros(coordenador: Client, ficha_do_campus: AcuidadeVisual) -> None:
    resposta = coordenador.get(GRAFICOS)

    assert 'pie_chart_lists' not in resposta.context
    assert 'Utilize os filtros para emitir o relatório.' in resposta.content.decode()


def test_periodo_usa_a_abertura_do_atendimento_e_nao_a_edicao_da_ficha(
    coordenador: Client, ficha_do_campus: AcuidadeVisual, ficha_outro_campus: AcuidadeVisual
) -> None:
    """Ficha de março editada em setembro continua no gráfico de março (#17621)."""
    Atendimento.objects.filter(pk=ficha_do_campus.atendimento_id).update(data_aberto=datetime.datetime(2025, 3, 10, 9, 0))
    # `data_cadastro` é `auto_now`: só um update fora do save simula a edição posterior.
    AcuidadeVisual.objects.filter(pk=ficha_do_campus.pk).update(data_cadastro=datetime.datetime(2025, 9, 10, 9, 0))

    marco = coordenador.get(f'{GRAFICOS}?data_inicio=01/03/2025&data_termino=31/03/2025&uo=')
    setembro = coordenador.get(f'{GRAFICOS}?data_inicio=01/09/2025&data_termino=30/09/2025&uo=')

    assert list(marco.context['registros']) == [ficha_do_campus]
    assert not setembro.context['registros'].exists()


def test_periodo_sem_fichas_nao_monta_graficos(coordenador: Client, ficha_do_campus: AcuidadeVisual) -> None:
    resposta = coordenador.get(f'{GRAFICOS}?data_inicio=01/01/2000&data_termino=02/01/2000&uo=')

    assert not resposta.context['registros'].exists()
    assert 'pie_chart_lists' not in resposta.context
    assert 'A busca realizada não encontrou nenhum resultado.' in resposta.content.decode()
