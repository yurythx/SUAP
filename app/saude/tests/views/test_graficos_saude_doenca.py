"""Processo saúde-doença: tela de gráficos e ramo do relatório de avaliação (tipo 7)."""

import re

import pytest
from django.contrib.auth.models import Group, Permission
from django.http import HttpResponse
from django.test import Client

from edu.models import Aluno
from rh.models import PessoaFisica, Servidor
from rh.tests.factories import ServidorFactory
from saude import tasks
from saude.models import Atendimento, Doenca, ProcessoSaudeDoenca, Prontuario, TipoAtendimento, Vinculo
from saude.tests.factories import ProcessoSaudeDoencaFactory

GRAFICOS = '/saude/graficos_saude_doenca/?'
RELATORIO = '/saude/relatorio_avaliacao_biomedica/?tipo_relatorio=7&'
SEM_VINCULO = 'data_inicio=&data_termino=&uo=&vinculo='


@pytest.fixture
def ficha_aluno(
    atendimento_aberto: Atendimento, aluno: Aluno, servidor_profissional: Servidor, doencas: tuple[Doenca, Doenca]
) -> ProcessoSaudeDoenca:
    """Ficha de uma aluna, aberta no campus do profissional logado, com doença crônica e as perguntas dos gráficos respondidas.

    Sem resposta no período, o gráfico some (#17622): a aluna e as respostas mantêm os três gráficos na tela.
    """
    PessoaFisica.objects.filter(pk=aluno.pessoa_fisica_id).update(sexo='F')
    ficha = ProcessoSaudeDoencaFactory(
        atendimento=atendimento_aberto, profissional=servidor_profissional.get_user(), problema_auditivo=True, gestante=False
    )
    ficha.doencas_cronicas.set(doencas)
    return ficha


@pytest.fixture
def ficha_servidor_outro_campus(db: None) -> ProcessoSaudeDoenca:
    """Ficha de um servidor, aberta por um médico de outro campus."""
    medico = ServidorFactory().get_user()
    medico.groups.add(Group.objects.get(name='Médico'))
    paciente = ServidorFactory()
    prontuario = Prontuario.get_prontuario(paciente.get_vinculo())
    atendimento = Atendimento.abrir(TipoAtendimento.ENFERMAGEM_MEDICO, prontuario, paciente, medico)
    return ProcessoSaudeDoencaFactory(atendimento=atendimento, profissional=medico)


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


@pytest.mark.parametrize('url', ['/saude/graficos_saude_doenca/', '/saude/relatorio_avaliacao_biomedica/'], ids=['graficos', 'relatorio'])
def test_filtro_vinculo_abre_em_todos(coordenador: Client, url: str) -> None:
    html = coordenador.get(url).content.decode()

    select = re.search(r'<select[^>]*name="vinculo".*?</select>', html, re.DOTALL)
    assert select, 'a tela não tem o filtro Vínculo'
    opcoes = re.findall(r'<option value="([^"]*)"( selected)?>([^<]*)</option>', select.group())
    assert opcoes[0] == ('', ' selected', 'Todos')
    assert [valor for valor, _, _ in opcoes[1:]] == [str(valor) for valor, _ in Vinculo.VINCULO_CHOICES]


@pytest.mark.parametrize('url', [GRAFICOS, RELATORIO], ids=['graficos', 'relatorio'])
def test_vinculo_vazio_mostra_todos_os_vinculos(
    coordenador: Client, ficha_aluno: ProcessoSaudeDoenca, ficha_servidor_outro_campus: ProcessoSaudeDoenca, url: str
) -> None:
    resposta = coordenador.get(url + SEM_VINCULO)

    assert resposta.status_code == 200
    assert set(resposta.context['registros']) == {ficha_aluno, ficha_servidor_outro_campus}


def test_graficos_iguais_aos_do_relatorio_com_lista_de_alunos(coordenador: Client, ficha_aluno: ProcessoSaudeDoenca) -> None:
    resposta = coordenador.get(f'{GRAFICOS}{SEM_VINCULO}0')

    graficos = [(type(grafico).__name__, grafico.id) for grafico in resposta.context['pie_chart_lists']]
    assert graficos == [('BarChart', 'grafico1'), ('PieChart', 'grafico2'), ('PieChart', 'grafico3')]
    assert ficha_aluno in resposta.context['lista_alunos_doenca']
    assert 'Lista de alunos por doença crônica' in resposta.content.decode()


@pytest.mark.parametrize('url', [GRAFICOS, RELATORIO], ids=['graficos', 'relatorio'])
def test_lista_de_alunos_tem_uma_linha_por_ficha(coordenador: Client, ficha_aluno: ProcessoSaudeDoenca, url: str) -> None:
    assert ficha_aluno.doencas_cronicas.count() == 2

    resposta = coordenador.get(url + SEM_VINCULO)

    assert list(resposta.context['lista_alunos_doenca']) == [ficha_aluno]


def test_graficos_exporta_xls(coordenador: Client, ficha_aluno: ProcessoSaudeDoenca, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tasks, 'graficos_saude_doenca_to_xls', lambda registros: HttpResponse(f'xls:{list(registros.values_list("pk", flat=True))}'))

    resposta = coordenador.get(f'{GRAFICOS}{SEM_VINCULO}&xls=1')

    assert resposta.content.decode() == f'xls:{[ficha_aluno.pk]}'


def test_graficos_restritos_ao_campus_do_usuario(
    restrito: Client, ficha_aluno: ProcessoSaudeDoenca, ficha_servidor_outro_campus: ProcessoSaudeDoenca
) -> None:
    resposta = restrito.get(GRAFICOS + SEM_VINCULO)

    assert list(resposta.context['registros']) == [ficha_aluno]
