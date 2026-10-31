"""Relatório de Avaliação de Saúde (``relatorio_avaliacao_biomedica``): gráficos e exportação por tipo de ficha."""

import datetime

import pytest
from django.contrib.auth.models import Group, Permission
from django.http import HttpResponse
from django.test import Client

from edu.models import Aluno
from rh.models import PessoaFisica, Servidor
from saude import tasks
from saude.models import (
    AcuidadeVisual,
    Antropometria,
    Atendimento,
    DesenvolvimentoPessoal,
    Doenca,
    ExameFisico,
    HabitosDeVida,
    PercepcaoSaudeBucal,
    ProcessoSaudeDoenca,
    Prontuario,
    TipoAtendimento,
    Vinculo,
)
from saude.tests.factories import (
    AcuidadeVisualFactory,
    AntropometriaFactory,
    DesenvolvimentoPessoalFactory,
    ExameFisicoFactory,
    HabitosDeVidaFactory,
    PercepcaoSaudeBucalFactory,
    ProcessoSaudeDoencaFactory,
)

URL = '/saude/relatorio_avaliacao_biomedica/'

# tipo: (query extra, tarefa de exportação, ids das divs dos gráficos na ordem do template)
RELATORIOS = {
    '1': ('', 'exportar_graficos_acuidade_visual_to_xls', ['grafico3', 'grafico1', 'grafico2', 'grafico4']),
    # Só a aluna adulta: os gráficos de homens e de menores de 19 anos ficam sem dado e somem.
    '2': ('', 'graficos_antropometria_to_xls', ['grafico1', 'grafico3', 'grafico7', 'grafico9', 'grafico10', 'grafico12']),
    '3': ('', 'graficos_desenvolvimento_pessoal_to_xls', ['grafico1']),
    '4': ('', 'graficos_exame_fisico_to_xls', [f'grafico{n}' for n in range(1, 7)]),
    '5': ('', 'graficos_habitos_vida_to_xls', [f'grafico{n}' for n in range(1, 19)]),
    '6': (
        '',
        'graficos_percepcao_saude_bucal_to_xls',
        ['grafico1', 'grafico2', 'grafico25', 'grafico3', 'grafico4', 'grafico5', 'grafico24', 'grafico26']
        + [f'grafico{n}' for n in range(6, 24)]
        + ['grafico27', 'grafico28', 'grafico29'],
    ),
    '7': (f'&vinculo={Vinculo.ALUNO}', 'graficos_saude_doenca_to_xls', ['grafico1', 'grafico2', 'grafico3']),
    '8': ('', 'relatorios_atendimentos_odontologicos_to_xls', []),
}
ALTERACOES_EXAME_FISICO = ['ectoscopia_alterada', 'acv_alterado', 'ar_alterado', 'abdome_alterado', 'mmi_alterados', 'mms_alterados']


@pytest.fixture
def coordenador(profissional: Client, servidor_profissional: Servidor) -> Client:
    """Profissional que vê os gráficos de todos os campi."""
    user = servidor_profissional.get_user()
    user.groups.add(Group.objects.get(name='Coordenador de Saúde Sistêmico'))
    user.user_permissions.add(Permission.objects.get(codename='view_atividadegrupo', content_type__app_label='saude'))
    return profissional


@pytest.fixture
def fichas(
    atendimento_aberto: Atendimento, prontuario: Prontuario, aluno: Aluno, servidor_profissional: Servidor, doencas: tuple[Doenca, Doenca]
) -> None:
    """Uma ficha de cada tipo na avaliação aberta de uma aluna adulta, mais um atendimento odontológico.

    As fichas respondem as perguntas dos gráficos: sem dado no período, o gráfico some (#17622).
    """
    PessoaFisica.objects.filter(pk=aluno.pessoa_fisica_id).update(sexo='F', nascimento_data=datetime.date(2000, 1, 1))
    ficha = {'atendimento': atendimento_aberto, 'profissional': servidor_profissional.get_user()}
    # Ficha do form atual: só ela responde o teste com lentes (#17624); a legada, no fim, responde a correção.
    AcuidadeVisualFactory(**ficha, olho_esquerdo='20/20', olho_direito='20/30', teste_com_lente=True)
    AntropometriaFactory(**ficha)
    DesenvolvimentoPessoalFactory(**ficha, problema_aprendizado=True)
    ExameFisicoFactory(**ficha, **dict.fromkeys(ALTERACOES_EXAME_FISICO, True))
    HabitosDeVidaFactory(**ficha, respondida=True)
    PercepcaoSaudeBucalFactory(**ficha, respondida=True)
    ProcessoSaudeDoencaFactory(**ficha, problema_auditivo=True, gestante=False).doencas_cronicas.set(doencas)
    odontologico = Atendimento.abrir(TipoAtendimento.ODONTOLOGICO, prontuario, aluno, ficha['profissional'])
    # Em outro atendimento: no mesmo, seria uma versão anterior da ficha, que não conta (#17628).
    AcuidadeVisualFactory(atendimento=odontologico, profissional=ficha['profissional'], olho_esquerdo='20/20', olho_direito='20/30')


@pytest.mark.parametrize('tipo', RELATORIOS)
def test_relatorio_monta_os_graficos_do_tipo(coordenador: Client, fichas: None, tipo: str) -> None:
    extra, _tarefa, ids = RELATORIOS[tipo]

    resposta = coordenador.get(f'{URL}?tipo_relatorio={tipo}{extra}')

    assert resposta.status_code == 200
    assert resposta.context['registros'].exists()
    assert [grafico.id for grafico in resposta.context['pie_chart_lists']] == ids


@pytest.mark.parametrize('tipo', RELATORIOS)
def test_exportacao_usa_a_tarefa_do_tipo(coordenador: Client, fichas: None, monkeypatch: pytest.MonkeyPatch, tipo: str) -> None:
    extra, tarefa, _ids = RELATORIOS[tipo]
    monkeypatch.setattr(tasks, tarefa, lambda registros: HttpResponse(f'{tarefa}:{registros.exists()}'))

    resposta = coordenador.get(f'{URL}?tipo_relatorio={tipo}{extra}&xls=1')

    assert resposta.content.decode() == f'{tarefa}:True'


@pytest.mark.parametrize('tipo', [tipo for tipo in RELATORIOS if tipo != '8'])
def test_periodo_de_um_dia_inclui_as_fichas_de_hoje(coordenador: Client, fichas: None, tipo: str) -> None:
    extra = RELATORIOS[tipo][0]
    hoje = f'{datetime.date.today():%d/%m/%Y}'

    resposta = coordenador.get(f'{URL}?tipo_relatorio={tipo}{extra}&data_inicio={hoje}&data_termino={hoje}')

    assert resposta.context['registros'].exists()


@pytest.mark.parametrize('tipo', [tipo for tipo in RELATORIOS if tipo != '8'])
def test_periodo_usa_a_abertura_do_atendimento_e_nao_a_edicao_da_ficha(
    coordenador: Client, fichas: None, atendimento_aberto: Atendimento, tipo: str
) -> None:
    """Ficha de março editada em setembro continua no relatório de março (#17621)."""
    Atendimento.objects.filter(pk=atendimento_aberto.pk).update(data_aberto=datetime.datetime(2025, 3, 10, 9, 0))
    # `data_cadastro` é `auto_now`: só um update fora do save simula a edição posterior.
    for modelo in (AcuidadeVisual, Antropometria, DesenvolvimentoPessoal, ExameFisico, HabitosDeVida, PercepcaoSaudeBucal, ProcessoSaudeDoenca):
        modelo.objects.filter(atendimento=atendimento_aberto).update(data_cadastro=datetime.datetime(2025, 9, 10, 9, 0))
    extra = RELATORIOS[tipo][0]

    marco = coordenador.get(f'{URL}?tipo_relatorio={tipo}{extra}&data_inicio=01/03/2025&data_termino=31/03/2025')
    setembro = coordenador.get(f'{URL}?tipo_relatorio={tipo}{extra}&data_inicio=01/09/2025&data_termino=30/09/2025')

    assert marco.context['registros'].exists()
    assert not setembro.context['registros'].exists()


def test_periodo_sem_fichas_nao_monta_graficos(coordenador: Client, fichas: None) -> None:
    resposta = coordenador.get(f'{URL}?tipo_relatorio=1&data_inicio=01/01/2000&data_termino=02/01/2000')

    assert not resposta.context['registros'].exists()
    assert 'pie_chart_lists' not in resposta.context
    assert 'A busca realizada não encontrou nenhum resultado.' in resposta.content.decode()
