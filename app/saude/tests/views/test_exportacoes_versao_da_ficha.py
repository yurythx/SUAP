"""Relatório de odontologia e XLS de atendimentos leem só a versão mais recente da ficha (#17629).

As views ``adicionar_*`` gravam uma ficha nova a cada salvamento no mesmo atendimento (histórico): a versão anterior
fica no banco, mas não vale mais. No XLS do admin cada linha traz a ficha do atendimento da linha, não a mais antiga do aluno.
"""

import datetime

import openpyxl
import pytest
from django.contrib.auth.models import Group, Permission
from django.test import Client

from djtools.models import Task
from djtools.storages.utils import download_temporary_file
from edu.models import Aluno
from rh.models import Servidor
from saude.models import Atendimento, Doenca, Prontuario, SituacaoAtendimento, TipoAtendimento
from saude.tests.factories import (
    AntecedentesFamiliaresFactory,
    AntropometriaFactory,
    CidFactory,
    DesenvolvimentoPessoalFactory,
    HabitosDeVidaFactory,
    HipoteseDiagnosticaFactory,
    ProcessoSaudeDoencaFactory,
    SinaisVitaisFactory,
)


@pytest.fixture
def coordenador(profissional: Client, servidor_profissional: Servidor) -> Client:
    """Profissional que vê os relatórios e o admin de atendimentos de todos os campi."""
    user = servidor_profissional.get_user()
    user.groups.add(Group.objects.get(name='Coordenador de Saúde Sistêmico'))
    user.user_permissions.add(
        *Permission.objects.filter(codename__in=['view_atividadegrupo', 'view_atendimento'], content_type__app_label='saude'),
    )
    return profissional


def _linhas_do_xls(resposta) -> list[tuple]:
    """Cabeçalho e linhas da planilha gerada pela tarefa que a resposta redireciona."""
    tarefa = Task.objects.get(uuid=resposta.url.rstrip('/').rsplit('/', 1)[-1])
    return list(openpyxl.load_workbook(download_temporary_file(tarefa.file)).active.iter_rows(values_only=True))


def _fatias(resposta, id_grafico: str) -> dict:
    (grafico,) = [grafico for grafico in resposta.context['pie_chart_lists'] if grafico.id == id_grafico]
    return {fatia[0]: fatia[1] for fatia in grafico.series[0]['data']}


def test_odontologia_gestante_vale_pela_versao_mais_recente_do_saude_doenca(
    coordenador: Client, servidor_profissional: Servidor, aluno: Aluno, prontuario: Prontuario
) -> None:
    user = servidor_profissional.get_user()
    atendimento = Atendimento.abrir(TipoAtendimento.ODONTOLOGICO, prontuario, aluno, user)
    ProcessoSaudeDoencaFactory(atendimento=atendimento, profissional=user, gestante=True)
    ProcessoSaudeDoencaFactory(atendimento=atendimento, profissional=user, gestante=False)

    resposta = coordenador.get('/saude/relatorio_atendimento_odontologia/?data_inicial=&data_final=')

    assert _fatias(resposta, 'grafico4') == {'Tratamento Concluído': 0, 'Tratamento em Andamento': 0}


def test_odontologia_gestante_conta_quando_a_versao_mais_recente_diz_sim(
    coordenador: Client, servidor_profissional: Servidor, aluno: Aluno, prontuario: Prontuario
) -> None:
    user = servidor_profissional.get_user()
    atendimento = Atendimento.abrir(TipoAtendimento.ODONTOLOGICO, prontuario, aluno, user)
    ProcessoSaudeDoencaFactory(atendimento=atendimento, profissional=user, gestante=False)
    ProcessoSaudeDoencaFactory(atendimento=atendimento, profissional=user, gestante=True)

    resposta = coordenador.get('/saude/relatorio_atendimento_odontologia/?data_inicial=&data_final=')

    assert _fatias(resposta, 'grafico4') == {'Tratamento Concluído': 0, 'Tratamento em Andamento': 1}


def test_xls_medico_enfermagem_alergias_so_da_versao_mais_recente(
    coordenador: Client, servidor_profissional: Servidor, aluno: Aluno, prontuario: Prontuario
) -> None:
    user = servidor_profissional.get_user()
    atendimento = Atendimento.abrir(TipoAtendimento.ENFERMAGEM_MEDICO, prontuario, aluno, user)
    for _ in range(3):
        ProcessoSaudeDoencaFactory(atendimento=atendimento, profissional=user, que_alimentos='Amendoim', que_medicamentos='Dipirona')
    ProcessoSaudeDoencaFactory(atendimento=atendimento, profissional=user, que_alimentos='Leite', que_medicamentos='')

    resposta = coordenador.get('/saude/relatorio_atendimento_medico_enfermagem/?data_inicial=&data_final=&xls=1')

    cabecalho, linha = _linhas_do_xls(resposta)
    assert linha[cabecalho.index('Alergias Medicamentosas e Alimentares')] == 'Leite'


def test_xls_medico_enfermagem_alergia_repetida_sai_uma_vez(
    coordenador: Client, servidor_profissional: Servidor, aluno: Aluno, prontuario: Prontuario
) -> None:
    user = servidor_profissional.get_user()
    atendimento = Atendimento.abrir(TipoAtendimento.ENFERMAGEM_MEDICO, prontuario, aluno, user)
    for _ in range(3):
        ProcessoSaudeDoencaFactory(atendimento=atendimento, profissional=user, que_alimentos='Amendoim', que_medicamentos='Dipirona')

    resposta = coordenador.get('/saude/relatorio_atendimento_medico_enfermagem/?data_inicial=&data_final=&xls=1')

    cabecalho, linha = _linhas_do_xls(resposta)
    assert linha[cabecalho.index('Alergias Medicamentosas e Alimentares')] == 'Amendoim, Dipirona'


def test_xls_medico_enfermagem_conta_as_hipoteses_por_capitulo_da_cid10(
    coordenador: Client, servidor_profissional: Servidor, aluno: Aluno, prontuario: Prontuario
) -> None:
    user = servidor_profissional.get_user()
    atendimento = Atendimento.abrir(TipoAtendimento.ENFERMAGEM_MEDICO, prontuario, aluno, user)
    for codigo in ('A00', 'B20', 'J45'):
        HipoteseDiagnosticaFactory(atendimento=atendimento, profissional=user, cid=CidFactory(codigo=codigo))

    resposta = coordenador.get('/saude/relatorio_atendimento_medico_enfermagem/?data_inicial=&data_final=&xls=1')

    cabecalho, linha = _linhas_do_xls(resposta)
    assert linha[cabecalho.index('CID-10 por Capítulo')] == (
        'Capítulo I - Algumas doenças infecciosas e parasitárias: 2, Capítulo X - Doenças do aparelho respiratório: 1'
    )


def _ficha_da_versao(atendimento: Atendimento, user, peso: int, pressao: int, atividade_fisica: bool, agravo: Doenca, aprendizado: bool) -> None:
    """Grava uma versão de cada ficha lida pelo XLS do admin."""
    ficha = {'atendimento': atendimento, 'profissional': user}
    AntropometriaFactory(**ficha, peso=peso)
    SinaisVitaisFactory(**ficha, pressao_sistolica=pressao, pressao_diastolica=pressao - 40)
    HabitosDeVidaFactory(**ficha, atividade_fisica=atividade_fisica)
    DesenvolvimentoPessoalFactory(**ficha, problema_aprendizado=aprendizado)
    AntecedentesFamiliaresFactory(**ficha, agravos_primeiro_grau=[agravo])


def test_xls_do_admin_cada_linha_traz_a_ficha_mais_recente_do_seu_atendimento(
    coordenador: Client, servidor_profissional: Servidor, aluno: Aluno, prontuario: Prontuario, doencas: tuple[Doenca, Doenca]
) -> None:
    user = servidor_profissional.get_user()
    doenca_a, doenca_b = doencas
    primeiro = Atendimento.abrir(TipoAtendimento.AVALIACAO_BIOMEDICA, prontuario, aluno, user)
    _ficha_da_versao(primeiro, user, peso=50, pressao=100, atividade_fisica=False, agravo=doenca_a, aprendizado=False)
    _ficha_da_versao(primeiro, user, peso=60, pressao=120, atividade_fisica=True, agravo=doenca_b, aprendizado=True)
    Atendimento.objects.filter(pk=primeiro.pk).update(situacao=SituacaoAtendimento.FECHADO, data_fechado=datetime.datetime.now())
    segundo = Atendimento.abrir(TipoAtendimento.AVALIACAO_BIOMEDICA, prontuario, aluno, user)
    _ficha_da_versao(segundo, user, peso=70, pressao=110, atividade_fisica=False, agravo=doenca_a, aprendizado=False)
    _ficha_da_versao(segundo, user, peso=80, pressao=130, atividade_fisica=False, agravo=doenca_b, aprendizado=True)

    resposta = coordenador.get('/admin/saude/atendimento/?export_to_xls=1&categoria=1&tipo=1&antropometria=Sim')

    cabecalho, *linhas = _linhas_do_xls(resposta)
    colunas = ['Pressão arterial', 'Peso', 'Prática de atividade física', 'Agravos à saúde com parentesco de 1º grau']
    dados = sorted(tuple(linha[cabecalho.index(coluna)] for coluna in colunas) for linha in linhas)
    assert dados == sorted(
        [
            ('120x80 mmHg', '60.000', 'Sim', doenca_b.nome),
            ('130x90 mmHg', '80.000', 'Não', doenca_b.nome),
        ]
    )


def test_xls_do_admin_deixa_vazias_as_fichas_que_o_atendimento_nao_tem(
    coordenador: Client, servidor_profissional: Servidor, aluno: Aluno, prontuario: Prontuario
) -> None:
    user = servidor_profissional.get_user()
    com_ficha = Atendimento.abrir(TipoAtendimento.AVALIACAO_BIOMEDICA, prontuario, aluno, user)
    AntropometriaFactory(atendimento=com_ficha, profissional=user, peso=60)
    Atendimento.objects.filter(pk=com_ficha.pk).update(situacao=SituacaoAtendimento.FECHADO, data_fechado=datetime.datetime.now())
    Atendimento.abrir(TipoAtendimento.AVALIACAO_BIOMEDICA, prontuario, aluno, user)

    resposta = coordenador.get('/admin/saude/atendimento/?export_to_xls=1&categoria=1&tipo=1&antropometria=Sim')

    cabecalho, *linhas = _linhas_do_xls(resposta)
    assert sorted(str(linha[cabecalho.index('Peso')] or '') for linha in linhas) == ['', '60.000']
