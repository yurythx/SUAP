"""Gráficos das perguntas novas da avaliação de saúde (Demanda 2301, #17624).

As fichas novas são criadas como o formulário atual as grava: campos novos preenchidos, antigos nulos
(ou com o valor copiado da ficha anterior, já que a tela de cadastro parte da última ficha do atendimento).
"""

from __future__ import annotations

import openpyxl
import pytest
from django.contrib.auth.models import Group, Permission
from django.http import HttpResponse
from django.test import Client

from djtools.html.graficos import BarChart, Chart
from djtools.models import Task
from djtools.storages.utils import download_temporary_file
from edu.tests.factories import AlunoFactory
from rh.models import Servidor
from saude import tasks
from saude.models import AcuidadeVisual, Atendimento, HabitosDeVida, NutricaoAlimentacao, PercepcaoSaudeBucal, Prontuario, TipoAtendimento
from saude.tests.factories import (
    AcuidadeVisualFactory,
    DificuldadeOralFactory,
    HabitosDeVidaFactory,
    NutricaoAlimentacaoFactory,
    PercepcaoSaudeBucalFactory,
    ProcessoSaudeDoencaFactory,
)

FiltroTodos = '?uo='
Doces = PercepcaoSaudeBucal.FrequenciaDoces
Bebida = HabitosDeVida.FrequenciaUso
Refeicao = NutricaoAlimentacao.RefeicaoDia


@pytest.fixture
def coordenador(profissional: Client, servidor_profissional: Servidor) -> Client:
    """Profissional que vê os gráficos de todos os campi."""
    user = servidor_profissional.get_user()
    user.groups.add(Group.objects.get(name='Coordenador de Saúde Sistêmico'))
    user.user_permissions.add(Permission.objects.get(codename='view_atividadegrupo', content_type__app_label='saude'))
    return profissional


@pytest.fixture
def novo_atendimento(servidor_profissional: Servidor):
    """Abre, a cada chamada, a avaliação de outro aluno pelo mesmo profissional."""

    def abrir() -> Atendimento:
        aluno = AlunoFactory()
        return Atendimento.abrir(
            TipoAtendimento.AVALIACAO_BIOMEDICA, Prontuario.get_prontuario(aluno.get_vinculo()), aluno, servidor_profissional.get_user()
        )

    return abrir


def _dados(resposta: HttpResponse, id_div: str) -> list[list]:
    """Pares [rótulo, quantidade] do gráfico cuja div é ``id_div``."""
    grafico: Chart = next(grafico for grafico in resposta.context['pie_chart_lists'] if grafico.id == id_div)
    if isinstance(grafico, BarChart):
        return [list(par) for par in zip(grafico.xAxis['categories'], grafico.series[0]['data'], strict=True)]
    return [list(par) for par in grafico.series[0]['data']]


def test_acuidade_visual_separa_o_teste_com_lente_da_correcao_legada(coordenador: Client, atendimento_aberto: Atendimento, novo_atendimento) -> None:
    AcuidadeVisualFactory(atendimento=atendimento_aberto, olho_esquerdo='20/20', olho_direito='20/20', teste_com_lente=True)
    AcuidadeVisualFactory(atendimento=novo_atendimento(), olho_esquerdo='20/30', olho_direito='20/30', teste_com_lente=False)
    AcuidadeVisualFactory(atendimento=novo_atendimento(), olho_esquerdo='20/40', olho_direito='20/40', com_correcao=True)

    resposta = coordenador.get(f'/saude/graficos_acuidade_visual/{FiltroTodos}')

    assert [grafico.id for grafico in resposta.context['pie_chart_lists']] == ['grafico3', 'grafico1', 'grafico2', 'grafico4']
    # Só a ficha legada (sem `teste_com_lente`) entra no gráfico antigo: as novas não viram "Sem correção".
    assert _dados(resposta, 'grafico3') == [['Com correção', 1]]
    assert _dados(resposta, 'grafico4') == [['Sem lentes corretivas', 1], ['Com lentes corretivas', 1]]


def test_percepcao_bucal_mostra_fio_dental_doces_e_motivo_de_estudar_e_trabalhar(
    coordenador: Client, atendimento_aberto: Atendimento, novo_atendimento
) -> None:
    motivo_novo, motivo_legado = DificuldadeOralFactory(), DificuldadeOralFactory()
    PercepcaoSaudeBucalFactory(
        atendimento=atendimento_aberto,
        usa_fio_dental=False,
        qtd_por_dia_consome_acucar=Doces.QUATRO_MAIS_VEZES,
        motivo_dificuldade_estudar_trabalhar=motivo_novo,
    )
    # Ficha nova copiada de uma legada: o motivo antigo de estudar continua gravado e não pode contar de novo.
    PercepcaoSaudeBucalFactory(
        atendimento=novo_atendimento(),
        usa_fio_dental=True,
        qts_dias_fio_dental_ultima_semana=3,
        qtd_por_dia_consome_acucar=Doces.NENHUMA,
        motivo_dificuldade_estudar_trabalhar=motivo_novo,
        motivo_dificuldade_estudar=motivo_novo,
        qtd_vezes_fio_dental_ultima_semana=5,
    )
    PercepcaoSaudeBucalFactory(
        atendimento=novo_atendimento(),
        motivo_dificuldade_estudar=motivo_legado,
        motivo_dificuldade_trabalhar=motivo_legado,
        qtd_vezes_fio_dental_ultima_semana=2,
        qtd_dias_consumiu_doce_ultima_semana=4,
    )

    resposta = coordenador.get(f'/saude/graficos_percepcao_saude_bucal/{FiltroTodos}')

    assert [grafico.id for grafico in resposta.context['pie_chart_lists']][-3:] == ['grafico27', 'grafico28', 'grafico29']
    assert _dados(resposta, 'grafico27') == [['Não usa', 1], ['3 dias', 1]]
    # Na ordem das opções do formulário, não na alfabética.
    assert _dados(resposta, 'grafico28') == [[Doces.NENHUMA.label, 1], [Doces.QUATRO_MAIS_VEZES.label, 1]]
    assert _dados(resposta, 'grafico29') == [[motivo_novo.dificuldade, 2]]
    assert sorted(_dados(resposta, 'grafico26')) == sorted([[motivo_novo.dificuldade, 2], [motivo_legado.dificuldade, 2]])


def test_habitos_de_vida_mostram_frequencia_de_bebida_e_refeicoes_da_ficha_de_nutricao(
    coordenador: Client, atendimento_aberto: Atendimento, novo_atendimento
) -> None:
    HabitosDeVidaFactory(atendimento=atendimento_aberto, bebe=True, frequencia_uso_bebida=Bebida.DUAS_SEMANA)
    NutricaoAlimentacaoFactory(atendimento=atendimento_aberto, refeicoes_por_dia=Refeicao.QUATRO)
    com_habitos_legados = novo_atendimento()
    HabitosDeVidaFactory(atendimento=com_habitos_legados, bebe=True, frequencia_bebida=3, refeicoes_por_dia=4)
    NutricaoAlimentacaoFactory(atendimento=com_habitos_legados, refeicoes_por_dia=Refeicao.UMA)
    HabitosDeVidaFactory(atendimento=novo_atendimento(), bebe=False, frequencia_uso_bebida=Bebida.NUNCA)
    # Nutrição de um atendimento sem ficha de hábitos não entra na tela de Hábitos de Vida.
    NutricaoAlimentacaoFactory(atendimento=novo_atendimento(), refeicoes_por_dia=Refeicao.SEIS)

    resposta = coordenador.get(f'/saude/graficos_habitos_vida/{FiltroTodos}')

    assert [grafico.id for grafico in resposta.context['pie_chart_lists']][-2:] == ['grafico17', 'grafico18']
    assert _dados(resposta, 'grafico17') == [[Bebida.DUAS_SEMANA.label, 1]]
    assert _dados(resposta, 'grafico18') == [[Refeicao.UMA.label, 1], [Refeicao.QUATRO.label, 1]]


def test_ficha_do_form_atual_troca_os_graficos_antigos_pelos_novos(coordenador: Client, atendimento_aberto: Atendimento) -> None:
    """Só fichas do form atual no período: os gráficos das perguntas antigas somem (#17622) e os novos aparecem."""
    PercepcaoSaudeBucalFactory(
        atendimento=atendimento_aberto,
        foi_dentista_anteriormente=True,
        tempo_ultima_vez_dentista=2,
        usa_fio_dental=True,
        qts_dias_fio_dental_ultima_semana=3,
        qtd_por_dia_consome_acucar=Doces.UMA_VEZ,
        dificuldades=True,
        motivo_dificuldade_estudar_trabalhar=DificuldadeOralFactory(),
    )
    HabitosDeVidaFactory(atendimento=atendimento_aberto, bebe=True, frequencia_uso_bebida=Bebida.DUAS_SEMANA)
    NutricaoAlimentacaoFactory(atendimento=atendimento_aberto)

    bucal = [grafico.id for grafico in coordenador.get(f'/saude/graficos_percepcao_saude_bucal/{FiltroTodos}').context['pie_chart_lists']]
    habitos = [grafico.id for grafico in coordenador.get(f'/saude/graficos_habitos_vida/{FiltroTodos}').context['pie_chart_lists']]

    assert not {'grafico3', 'grafico4', 'grafico17', 'grafico19', 'grafico25'} & set(bucal)
    assert bucal[-3:] == ['grafico27', 'grafico28', 'grafico29']
    assert not {'grafico6', 'grafico11'} & set(habitos)
    assert habitos[-2:] == ['grafico17', 'grafico18']


def test_exportacoes_trazem_as_colunas_novas(coordenador: Client, atendimento_aberto: Atendimento, monkeypatch: pytest.MonkeyPatch) -> None:
    motivo = DificuldadeOralFactory()
    AcuidadeVisualFactory(atendimento=atendimento_aberto, teste_com_lente=True)
    PercepcaoSaudeBucalFactory(
        atendimento=atendimento_aberto,
        usa_fio_dental=True,
        qts_dias_fio_dental_ultima_semana=2,
        qtd_por_dia_consome_acucar=Doces.UMA_VEZ,
        motivo_dificuldade_estudar_trabalhar=motivo,
    )
    planilhas = []
    monkeypatch.setattr(tasks, 'XlsResponse', lambda rows, processo: planilhas.append(rows))

    coordenador.get(f'/saude/graficos_acuidade_visual/{FiltroTodos}&xls=1')
    coordenador.get(f'/saude/graficos_percepcao_saude_bucal/{FiltroTodos}&xls=1')

    acuidade, percepcao = planilhas
    assert dict(zip(*acuidade, strict=True))[AcuidadeVisual._meta.get_field('teste_com_lente').verbose_name] is True
    linha = dict(zip(*percepcao, strict=True))
    assert linha['Você usa fio dental?'] is True
    assert linha['Em quantos dias você usou o fio dental nos últimos 7 dias?'] == 2
    assert linha[PercepcaoSaudeBucal._meta.get_field('qtd_por_dia_consome_acucar').verbose_name] == Doces.UMA_VEZ
    assert linha['Motivo da dificuldade em estudar ou trabalhar'] == motivo


VAZIO = '-'  # como o XLS grava a célula sem resposta


def _planilha(cliente: Client, url: str) -> dict[str, dict]:
    """Lê o XLS que a tela gera: a linha de cada paciente (pela matrícula), indexada pelo cabeçalho."""
    resposta = cliente.get(url)
    tarefa = Task.objects.get(uuid=resposta.url.rstrip('/').rsplit('/', 1)[-1])
    cabecalho, *linhas = openpyxl.load_workbook(download_temporary_file(tarefa.file)).active.iter_rows(values_only=True)
    return {linha[cabecalho.index('Matrícula')]: dict(zip(cabecalho, linha, strict=True)) for linha in linhas}


def test_xls_de_habitos_traz_as_respostas_novas_e_mantem_as_da_ficha_antiga(
    coordenador: Client, atendimento_aberto: Atendimento, novo_atendimento
) -> None:
    HabitosDeVidaFactory(
        atendimento=atendimento_aberto,
        fuma=True,
        frequencia_uso_fumo=Bebida.DUAS_MES,
        idade_fumo='15',
        bebe=True,
        frequencia_uso_bebida=Bebida.DUAS_SEMANA,
        idade_bebida='16',
        usa_drogas=True,
        frequencia_uso_droga=Bebida.UMA_VEZ_MES,
        idade_drogas='17',
    )
    NutricaoAlimentacaoFactory(atendimento=atendimento_aberto, refeicoes_por_dia=Refeicao.QUATRO)
    legado = novo_atendimento()
    HabitosDeVidaFactory(atendimento=legado, fuma=True, frequencia_fumo=5, bebe=True, frequencia_bebida=3, refeicoes_por_dia=4)

    planilha = _planilha(coordenador, f'/saude/graficos_habitos_vida/{FiltroTodos}&xls=1')

    nova = planilha[atendimento_aberto.aluno.matricula]
    assert nova['Fuma - frequência de uso'] == Bebida.DUAS_MES.label
    assert nova['Fuma - idade em que experimentou'] == '15'
    assert nova['Bebidas alcoólicas - frequência de uso'] == Bebida.DUAS_SEMANA.label
    assert nova['Bebidas alcoólicas - idade em que experimentou'] == '16'
    assert nova['Drogas - frequência de uso'] == Bebida.UMA_VEZ_MES.label
    assert nova['Drogas - idade em que experimentou'] == '17'
    assert nova['Quantas refeições faz por dia (Nutrição e Alimentação)'] == Refeicao.QUATRO.label
    antiga = planilha[legado.aluno.matricula]
    assert antiga['Número de cigarros por dia'] == '5.0'
    assert antiga['Frequência mínima de ingestão de bebidas alcoólicas'] == '3'
    assert antiga['Quantas refeições faz por dia'] == '4'
    assert antiga['Fuma - frequência de uso'] == VAZIO
    assert antiga['Quantas refeições faz por dia (Nutrição e Alimentação)'] == '3 refeições'


def test_xls_de_acuidade_nao_diz_nao_em_com_correcao_na_ficha_nova(coordenador: Client, atendimento_aberto: Atendimento, novo_atendimento) -> None:
    AcuidadeVisualFactory(atendimento=atendimento_aberto, teste_com_lente=False, usa_lente=True, usa_lente_detalhes='Óculos para miopia')
    legado_sem = novo_atendimento()
    AcuidadeVisualFactory(atendimento=legado_sem)
    legado_com = novo_atendimento()
    AcuidadeVisualFactory(atendimento=legado_com, com_correcao=True)

    planilha = _planilha(coordenador, f'/saude/graficos_acuidade_visual/{FiltroTodos}&xls=1')

    nova = planilha[atendimento_aberto.aluno.matricula]
    assert nova['Com Correção'] == VAZIO
    assert nova['Já faz uso de lentes de correção'] == 'Sim'
    assert nova['Detalhes do uso de lente'] == 'Óculos para miopia'
    assert planilha[legado_sem.aluno.matricula]['Com Correção'] == 'Não'
    assert planilha[legado_com.aluno.matricula]['Com Correção'] == 'Sim'


def test_xls_de_percepcao_bucal_traz_a_frequencia_de_escovacao(coordenador: Client, atendimento_aberto: Atendimento) -> None:
    PercepcaoSaudeBucalFactory(atendimento=atendimento_aberto, frequencia_escovacao=PercepcaoSaudeBucal.FrequenciaEscovacao.DUAS_A_TRES)

    planilha = _planilha(coordenador, f'/saude/graficos_percepcao_saude_bucal/{FiltroTodos}&xls=1')

    escovacao = PercepcaoSaudeBucal._meta.get_field('frequencia_escovacao').verbose_name
    assert planilha[atendimento_aberto.aluno.matricula][escovacao] == PercepcaoSaudeBucal.FrequenciaEscovacao.DUAS_A_TRES.label


def test_xls_de_saude_doenca_usa_a_alergia_da_nutricao_so_quando_a_ficha_antiga_nao_tem(
    coordenador: Client, atendimento_aberto: Atendimento, novo_atendimento
) -> None:
    ProcessoSaudeDoencaFactory(atendimento=atendimento_aberto)
    NutricaoAlimentacaoFactory(atendimento=atendimento_aberto, tem_alergia_alimentos=True, alergia_alimentos_outros='Amendoim')
    antiga = novo_atendimento()
    ProcessoSaudeDoencaFactory(atendimento=antiga, alergia_alimentos=True, que_alimentos='Leite')
    NutricaoAlimentacaoFactory(atendimento=antiga, tem_alergia_alimentos=True, alergia_alimentos_outros='Soja')
    sem_alergia = novo_atendimento()
    ProcessoSaudeDoencaFactory(atendimento=sem_alergia)
    NutricaoAlimentacaoFactory(atendimento=sem_alergia, tem_alergia_alimentos=False)

    planilha = _planilha(coordenador, '/saude/graficos_saude_doenca/?data_inicio=&data_termino=&uo=&vinculo=&xls=1')

    alergias = {matricula: (linha['Alergia a alimentos'], linha['Quais alimentos']) for matricula, linha in planilha.items()}
    assert alergias == {
        atendimento_aberto.aluno.matricula: ('Sim', 'Amendoim'),
        antiga.aluno.matricula: ('Sim', 'Leite'),
        sem_alergia.aluno.matricula: (VAZIO, VAZIO),
    }
