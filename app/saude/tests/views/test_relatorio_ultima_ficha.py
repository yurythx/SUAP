"""Relatório de Avaliação de Saúde, Gráficos e XLS contam só a ficha mais recente de cada atendimento (#17628).

As views ``adicionar_*`` gravam uma ficha nova a cada salvamento no mesmo atendimento (histórico): as versões
anteriores ficam no banco, mas não contam.
"""

import datetime

import openpyxl
import pytest
from django.contrib.auth.models import Group, Permission
from django.http import HttpResponse
from django.test import Client

from djtools.models import Task
from djtools.storages.utils import download_temporary_file
from edu.models import Aluno
from rh.models import PessoaFisica, Servidor
from saude.models import Antropometria, Atendimento, ExameFisico, NutricaoAlimentacao, Prontuario, SituacaoAtendimento, TipoAtendimento
from saude.tests.factories import AntropometriaFactory, ExameFisicoFactory, HabitosDeVidaFactory, NutricaoAlimentacaoFactory

EXAME_FISICO = ['/saude/graficos_exame_fisico/?uo=', '/saude/relatorio_avaliacao_biomedica/?tipo_relatorio=4']
ANTROPOMETRIA = ['/saude/graficos_antropometria/?uo=', '/saude/relatorio_avaliacao_biomedica/?tipo_relatorio=2']


@pytest.fixture
def coordenador(profissional: Client, servidor_profissional: Servidor) -> Client:
    """Profissional que vê os gráficos de todos os campi."""
    user = servidor_profissional.get_user()
    user.groups.add(Group.objects.get(name='Coordenador de Saúde Sistêmico'))
    user.user_permissions.add(Permission.objects.get(codename='view_atividadegrupo', content_type__app_label='saude'))
    return profissional


def _linhas_xls(cliente: Client, url: str) -> list[tuple]:
    """Linhas de dados (sem o cabeçalho) da planilha exportada pela tarefa."""
    resposta = cliente.get(f'{url}&xls=1')
    tarefa = Task.objects.get(uuid=resposta.url.rstrip('/').rsplit('/', 1)[-1])
    return list(openpyxl.load_workbook(download_temporary_file(tarefa.file)).active.iter_rows(values_only=True))[1:]


def _fatias_com_valor(resposta: HttpResponse, id_grafico: str) -> list[list]:
    (grafico,) = [grafico for grafico in resposta.context['pie_chart_lists'] if grafico.id == id_grafico]
    return [list(fatia) for fatia in grafico.series[0]['data'] if fatia[1]]


@pytest.mark.parametrize('url', EXAME_FISICO)
def test_edicoes_da_ficha_contam_uma_vez_com_o_valor_da_ultima(
    coordenador: Client, atendimento_aberto: Atendimento, servidor_profissional: Servidor, aluno: Aluno, url: str
) -> None:
    ficha = {'atendimento': atendimento_aberto, 'profissional': servidor_profissional.get_user()}
    ExameFisicoFactory(**ficha, ectoscopia_alterada=True)
    ExameFisicoFactory(**ficha, ectoscopia_alterada=True)
    ultima = ExameFisicoFactory(**ficha, ectoscopia_alterada=False)

    resposta = coordenador.get(url)

    assert list(resposta.context['registros'].values_list('pk', flat=True)) == [ultima.pk]
    assert _fatias_com_valor(resposta, 'grafico1') == [['Não tem Alteração na Ectoscopia', 1]]
    assert [(linha[2], linha[5]) for linha in _linhas_xls(coordenador, url)] == [(aluno.matricula, 'Não')]


@pytest.mark.parametrize('url', EXAME_FISICO)
def test_atendimentos_diferentes_do_mesmo_aluno_contam_cada_um(
    coordenador: Client, atendimento_aberto: Atendimento, servidor_profissional: Servidor, aluno: Aluno, prontuario: Prontuario, url: str
) -> None:
    user = servidor_profissional.get_user()
    ExameFisicoFactory(atendimento=atendimento_aberto, profissional=user, ectoscopia_alterada=True)
    Atendimento.objects.filter(pk=atendimento_aberto.pk).update(situacao=SituacaoAtendimento.FECHADO, data_fechado=datetime.datetime.now())
    segundo = Atendimento.abrir(TipoAtendimento.AVALIACAO_BIOMEDICA, prontuario, aluno, user)
    ExameFisicoFactory(atendimento=segundo, profissional=user, ectoscopia_alterada=True)

    resposta = coordenador.get(url)

    por_atendimento = ExameFisico.objects.values('atendimento').distinct().count()
    assert resposta.context['registros'].count() == por_atendimento == 2
    assert _fatias_com_valor(resposta, 'grafico1') == [['Tem Alteração na Ectoscopia', por_atendimento]]
    assert len(_linhas_xls(coordenador, url)) == por_atendimento


def test_refeicoes_contam_so_a_ultima_ficha_de_nutricao_do_atendimento(
    coordenador: Client, atendimento_aberto: Atendimento, servidor_profissional: Servidor
) -> None:
    """O gráfico de refeições dos Hábitos de Vida vem da ficha de Nutrição e Alimentação (#17624), também versionada."""
    ficha = {'atendimento': atendimento_aberto, 'profissional': servidor_profissional.get_user()}
    HabitosDeVidaFactory(**ficha)
    NutricaoAlimentacaoFactory(**ficha, refeicoes_por_dia=NutricaoAlimentacao.RefeicaoDia.QUATRO)
    NutricaoAlimentacaoFactory(**ficha, refeicoes_por_dia=NutricaoAlimentacao.RefeicaoDia.UMA)

    resposta = coordenador.get('/saude/graficos_habitos_vida/?uo=')

    assert _fatias_com_valor(resposta, 'grafico18') == [[NutricaoAlimentacao.RefeicaoDia.UMA.label, 1]]


@pytest.fixture
def aluna_adulta(aluno: Aluno) -> Aluno:
    """Maior de 19 anos: cai nos gráficos de IMC de adultos (grafico1)."""
    PessoaFisica.objects.filter(pk=aluno.pessoa_fisica_id).update(sexo='F', nascimento_data=datetime.date(2000, 1, 1))
    return aluno


@pytest.mark.parametrize('url', ANTROPOMETRIA)
def test_edicoes_da_antropometria_contam_uma_vez_com_o_valor_da_ultima(
    coordenador: Client, atendimento_aberto: Atendimento, servidor_profissional: Servidor, aluna_adulta: Aluno, url: str
) -> None:
    ficha = {'atendimento': atendimento_aberto, 'profissional': servidor_profissional.get_user(), 'estatura': 170}
    AntropometriaFactory(**ficha, peso=50)
    AntropometriaFactory(**ficha, peso=50)
    ultima = AntropometriaFactory(**ficha, peso=95)

    resposta = coordenador.get(url)

    assert list(resposta.context['registros'].values_list('pk', flat=True)) == [ultima.pk]
    assert _fatias_com_valor(resposta, 'grafico1') == [['Obesidade grau 1', 1]]
    assert [linha[2] for linha in _linhas_xls(coordenador, url)] == [aluna_adulta.matricula]


@pytest.mark.parametrize('url', ANTROPOMETRIA)
def test_edicao_que_esvaziou_o_peso_nao_traz_a_versao_anterior_de_volta(
    coordenador: Client, atendimento_aberto: Atendimento, servidor_profissional: Servidor, aluna_adulta: Aluno, url: str
) -> None:
    """A mais recente é escolhida entre todas as versões, antes do filtro de estatura e peso preenchidos."""
    ficha = {'atendimento': atendimento_aberto, 'profissional': servidor_profissional.get_user()}
    AntropometriaFactory(**ficha, peso=60)
    AntropometriaFactory(**ficha, peso=0)

    resposta = coordenador.get(url)

    assert Antropometria.objects.filter(atendimento=atendimento_aberto).count() == 2
    assert not resposta.context['registros'].exists()
