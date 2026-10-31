"""Telas de gráficos de Exame Físico e de Desenvolvimento Pessoal: gráficos, filtros e exportação."""

import datetime
from types import SimpleNamespace

import pytest
from django.contrib.auth.models import Group, Permission
from django.db.models import QuerySet
from django.http import HttpResponse
from django.test import Client

from edu.tests.factories import AlunoFactory
from rh.models import Servidor
from rh.tests.factories import ServidorFactory
from saude import tasks
from saude.models import Atendimento, DesenvolvimentoPessoal, ExameFisico, Prontuario, TipoAtendimento
from saude.tests.factories import DesenvolvimentoPessoalFactory, ExameFisicoFactory

# tela: (url, modelo da ficha, tarefa de exportação, ids das divs dos gráficos na ordem do template)
TELAS = {
    'exame_fisico': ('/saude/graficos_exame_fisico/', ExameFisico, 'graficos_exame_fisico_to_xls', [f'grafico{n}' for n in range(1, 7)]),
    'desenvolvimento_pessoal': (
        '/saude/graficos_desenvolvimento_pessoal/',
        DesenvolvimentoPessoal,
        'graficos_desenvolvimento_pessoal_to_xls',
        ['grafico1'],
    ),
}
# Um gráfico por alteração: sem resposta no período, o gráfico some (#17622).
ALTERACOES_EXAME_FISICO = ['ectoscopia_alterada', 'acv_alterado', 'ar_alterado', 'abdome_alterado', 'mmi_alterados', 'mms_alterados']


def _permitir_graficos(servidor: Servidor) -> None:
    permissao = Permission.objects.get(codename='view_atividadegrupo', content_type__app_label='saude')
    servidor.get_user().user_permissions.add(permissao)


@pytest.fixture
def coordenador(profissional: Client, servidor_profissional: Servidor) -> Client:
    """Profissional que vê os gráficos de todos os campi."""
    _permitir_graficos(servidor_profissional)
    servidor_profissional.get_user().groups.add(Group.objects.get(name='Coordenador de Saúde Sistêmico'))
    return profissional


@pytest.fixture
def restrito(profissional: Client, servidor_profissional: Servidor) -> Client:
    """Profissional que só vê os gráficos do próprio campus."""
    _permitir_graficos(servidor_profissional)
    return profissional


@pytest.fixture
def fichas(atendimento_aberto: Atendimento, servidor_profissional: Servidor) -> SimpleNamespace:
    """Uma ficha de cada tela no campus do profissional e outra num segundo campus."""
    outro_servidor = ServidorFactory()
    outro_aluno = AlunoFactory()
    outro_atendimento = Atendimento.abrir(
        TipoAtendimento.AVALIACAO_BIOMEDICA, Prontuario.get_prontuario(outro_aluno.get_vinculo()), outro_aluno, outro_servidor.get_user()
    )
    for atendimento, servidor, alterado in (
        (atendimento_aberto, servidor_profissional, True),
        (outro_atendimento, outro_servidor, False),
    ):
        user = servidor.get_user()
        ExameFisicoFactory(atendimento=atendimento, profissional=user, **dict.fromkeys(ALTERACOES_EXAME_FISICO, alterado))
        DesenvolvimentoPessoalFactory(atendimento=atendimento, profissional=user, problema_aprendizado=alterado)
    return SimpleNamespace(
        uo_propria=servidor_profissional.setor.uo,
        uo_outra=outro_servidor.setor.uo,
        propria=atendimento_aberto,
        outra=outro_atendimento,
    )


@pytest.mark.parametrize('tela', TELAS)
def test_monta_os_graficos_da_tela(coordenador: Client, fichas: SimpleNamespace, tela: str) -> None:
    url, modelo, _tarefa, ids = TELAS[tela]

    resposta = coordenador.get(f'{url}?uo=')

    assert resposta.status_code == 200
    assert set(resposta.context['registros']) == set(modelo.objects.all())
    assert [grafico.id for grafico in resposta.context['pie_chart_lists']] == ids


@pytest.mark.parametrize('tela', TELAS)
def test_sem_filtro_enviado_so_mostra_o_formulario(coordenador: Client, fichas: SimpleNamespace, tela: str) -> None:
    resposta = coordenador.get(TELAS[tela][0])

    assert resposta.status_code == 200
    assert 'registros' not in resposta.context
    assert 'pie_chart_lists' not in resposta.context


@pytest.mark.parametrize('tela', TELAS)
def test_filtra_por_campus_e_periodo(coordenador: Client, fichas: SimpleNamespace, tela: str) -> None:
    url, modelo, _tarefa, ids = TELAS[tela]
    # `data_cadastro` é datetime e o filtro compara com a data (meia-noite): o término tem de ser depois de hoje.
    ontem, amanha = (datetime.date.today() + datetime.timedelta(days=dias) for dias in (-1, 1))

    no_campus = coordenador.get(f'{url}?uo={fichas.uo_outra.pk}&data_inicio={ontem:%d/%m/%Y}&data_termino={amanha:%d/%m/%Y}')
    fora_do_periodo = coordenador.get(f'{url}?data_inicio=01/01/2000&data_termino=02/01/2000')

    assert list(no_campus.context['registros']) == list(modelo.objects.filter(atendimento=fichas.outra))
    assert [grafico.id for grafico in no_campus.context['pie_chart_lists']] == ids
    assert not fora_do_periodo.context['registros'].exists()
    assert 'pie_chart_lists' not in fora_do_periodo.context
    assert 'A busca realizada não encontrou nenhum resultado.' in fora_do_periodo.content.decode()


@pytest.mark.parametrize('tela', TELAS)
def test_periodo_de_um_dia_inclui_as_fichas_de_hoje(coordenador: Client, fichas: SimpleNamespace, tela: str) -> None:
    url, modelo, _tarefa, _ids = TELAS[tela]
    hoje = f'{datetime.date.today():%d/%m/%Y}'

    resposta = coordenador.get(f'{url}?uo=&data_inicio={hoje}&data_termino={hoje}')

    assert set(resposta.context['registros']) == set(modelo.objects.all())


@pytest.mark.parametrize('tela', TELAS)
def test_exportacao_usa_a_tarefa_da_tela_com_as_fichas_filtradas(
    coordenador: Client, fichas: SimpleNamespace, monkeypatch: pytest.MonkeyPatch, tela: str
) -> None:
    url, modelo, tarefa, _ids = TELAS[tela]
    monkeypatch.setattr(tasks, tarefa, lambda registros: HttpResponse(','.join(str(pk) for pk in sorted(registros.values_list('pk', flat=True)))))

    resposta = coordenador.get(f'{url}?uo={fichas.uo_propria.pk}&xls=1')

    assert resposta.content.decode() == str(modelo.objects.get(atendimento=fichas.propria).pk)


@pytest.mark.parametrize('tela', TELAS)
def test_sem_acesso_a_todos_os_campi_so_ve_o_proprio(restrito: Client, fichas: SimpleNamespace, tela: str) -> None:
    url, modelo, _tarefa, _ids = TELAS[tela]

    resposta = restrito.get(f'{url}?uo=')

    assert list(resposta.context['registros']) == list(modelo.objects.filter(atendimento=fichas.propria))


# grupo: vê as fichas de todos os campi? (#17618: o Coordenador de Atividades Estudantis é de campus)
COORDENADORES_AE = {'Coordenador de Atividades Estudantis': False, 'Coordenador de Atividades Estudantis Sistêmico': True}
SEM_FILTRO = 'data_inicio=&data_termino=&uo='


def _logar_coordenador_ae(cliente: Client, servidor_profissional: Servidor, grupo: str) -> Client:
    """Servidor do campus do profissional só com o grupo: a permissão da tela vem do próprio grupo."""
    user = ServidorFactory(setor=servidor_profissional.setor).get_user()
    cliente.login(user=user)
    user.groups.add(Group.objects.get(name=grupo))
    return cliente


def _exames_visiveis(fichas: SimpleNamespace, grupo: str) -> QuerySet:
    if COORDENADORES_AE[grupo]:
        return ExameFisico.objects.all()
    return ExameFisico.objects.filter(atendimento=fichas.propria)


@pytest.mark.parametrize('grupo', COORDENADORES_AE)
@pytest.mark.parametrize(
    'url', ['/saude/graficos_exame_fisico/?', '/saude/relatorio_avaliacao_biomedica/?tipo_relatorio=4&'], ids=['graficos', 'relatorio']
)
def test_coordenador_ae_com_campus_vazio(suap_client: Client, servidor_profissional: Servidor, fichas: SimpleNamespace, grupo: str, url: str) -> None:
    cliente = _logar_coordenador_ae(suap_client, servidor_profissional, grupo)

    resposta = cliente.get(url + SEM_FILTRO)

    assert resposta.status_code == 200
    assert set(resposta.context['registros']) == set(_exames_visiveis(fichas, grupo))


@pytest.mark.parametrize('grupo', COORDENADORES_AE)
def test_coordenador_ae_exporta_xls_com_campus_vazio(
    suap_client: Client, servidor_profissional: Servidor, fichas: SimpleNamespace, monkeypatch: pytest.MonkeyPatch, grupo: str
) -> None:
    monkeypatch.setattr(tasks, 'graficos_exame_fisico_to_xls', lambda registros: HttpResponse(str(sorted(registros.values_list('pk', flat=True)))))
    cliente = _logar_coordenador_ae(suap_client, servidor_profissional, grupo)

    resposta = cliente.get(f'/saude/graficos_exame_fisico/?{SEM_FILTRO}&xls=1')

    assert resposta.content.decode() == str(sorted(_exames_visiveis(fichas, grupo).values_list('pk', flat=True)))
