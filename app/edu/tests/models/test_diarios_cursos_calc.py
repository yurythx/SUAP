"""Testes unitários (sem DB) de lógica de periodicidade/CH em diários e componentes.

Cobre branches de ``Diario.get_label_etapa``/``get_periodicidade``/``flexibilizar_data``,
``Componente.get_fator_conversao_hora_aula``, ``ComponenteCurricular.get_ch_semanal`` e
``MatriculaDiario.realizou_todas_avaliacoes_regulares``. Métodos auxiliares e FKs são
mockados; nenhum teste toca o banco.
"""

import datetime
from decimal import Decimal
from unittest.mock import Mock, PropertyMock, patch

from djtools.utils import somar_dias

from edu.models.cursos import Componente, ComponenteCurricular
from edu.models.diarios import Diario, ProfessorDiario
from edu.models.historico import MatriculaDiario


# --- Diario.get_label_etapa -------------------------------------------------


def test_get_label_etapa_mapeia_numeros_e_final():
    with (
        patch.object(Diario, 'get_numero_primeira_etapa', return_value='3'),
        patch.object(Diario, 'get_numero_segunda_etapa', return_value='4'),
    ):
        diario = Diario()
        assert diario.get_label_etapa(1) == '3'
        assert diario.get_label_etapa(2) == '4'
        assert diario.get_label_etapa(5) == 'Final'
        assert diario.get_label_etapa(3) == 3  # default: devolve a própria etapa


# --- Diario.get_periodicidade -----------------------------------------------


def _periodicidade(is_semestral_em_calendario_anual, segundo_semestre, is_anual, qtd_etapas):
    calendario = Mock()
    calendario.qtd_etapas = qtd_etapas
    diario = Diario()
    diario.segundo_semestre = segundo_semestre
    with (
        patch.object(Diario, 'is_semestral_em_calendario_anual', return_value=is_semestral_em_calendario_anual),
        patch.object(Diario, 'is_semestral_segundo_semestre', return_value=segundo_semestre),
        patch.object(Diario, 'is_anual', return_value=is_anual),
        patch.object(Diario, 'calendario_academico', new_callable=PropertyMock, return_value=calendario),
    ):
        return diario.get_periodicidade()


def test_periodicidade_anual_segundo_semestre():
    assert _periodicidade(is_semestral_em_calendario_anual=True, segundo_semestre=True, is_anual=True, qtd_etapas=4) == 'Anual (2° semestre)'


def test_periodicidade_anual_primeiro_semestre():
    assert _periodicidade(is_semestral_em_calendario_anual=True, segundo_semestre=False, is_anual=True, qtd_etapas=4) == 'Anual (1° semestre)'


def test_periodicidade_anual():
    assert _periodicidade(is_semestral_em_calendario_anual=False, segundo_semestre=False, is_anual=True, qtd_etapas=4) == 'Anual'


def test_periodicidade_semestral():
    assert _periodicidade(is_semestral_em_calendario_anual=False, segundo_semestre=False, is_anual=False, qtd_etapas=2) == 'Semestral'


def test_periodicidade_livre():
    assert _periodicidade(is_semestral_em_calendario_anual=False, segundo_semestre=False, is_anual=False, qtd_etapas=1) == 'Livre'


# --- Diario.flexibilizar_data -----------------------------------------------


def test_flexibilizar_data_none_retorna_none():
    assert Diario().flexibilizar_data(None) is None


def test_flexibilizar_data_soma_sete_dias():
    data = datetime.date(2025, 1, 10)
    assert Diario().flexibilizar_data(data) == somar_dias(data, 7)


# --- Componente.get_fator_conversao_hora_aula -------------------------------


def test_fator_conversao_hora_aula():
    with (
        patch.object(Componente, 'get_ch_hora_aula', return_value=80),
        patch.object(Componente, 'get_ch_hora_relogio', return_value=60),
    ):
        componente = Componente()
        componente.ch_hora_relogio = 60
        assert componente.get_fator_conversao_hora_aula() == Decimal(80) / Decimal(60)


def test_fator_conversao_zero_sem_ch_relogio():
    componente = Componente()
    componente.ch_hora_relogio = 0
    assert componente.get_fator_conversao_hora_aula() == Decimal(0)


# --- ComponenteCurricular.get_ch_semanal ------------------------------------


def test_ch_semanal_anual_primeiro_semestre():
    cc = ComponenteCurricular()
    cc.qtd_avaliacoes = 4
    cc.ch_semanal_1s = 4
    cc.ch_semanal_2s = 6
    assert cc.get_ch_semanal(semestre=1) == 4


def test_ch_semanal_anual_segundo_semestre():
    cc = ComponenteCurricular()
    cc.qtd_avaliacoes = 4
    cc.ch_semanal_1s = 4
    cc.ch_semanal_2s = 6
    assert cc.get_ch_semanal(semestre=2) == 6


def test_ch_semanal_semestral_segundo_semestre():
    cc = ComponenteCurricular()
    cc.qtd_avaliacoes = 2
    cc.segundo_semestre = True
    cc.ch_semanal_1s = 4
    cc.ch_semanal_2s = 6
    assert cc.get_ch_semanal(semestre=2) == 6


def test_ch_semanal_outros_usa_primeiro_semestre():
    cc = ComponenteCurricular()
    cc.qtd_avaliacoes = 1
    cc.ch_semanal_1s = 5
    assert cc.get_ch_semanal(semestre=1) == 5


def test_ch_semanal_semestre_none_retorna_primeiro_semestre():
    cc = ComponenteCurricular()
    cc.ch_semanal_1s = 4
    cc.ch_semanal_2s = 6
    assert cc.get_ch_semanal(semestre=None) == 4


def test_ch_semanal_semestre_none_quando_ch_1s_nula():
    cc = ComponenteCurricular()
    cc.componente = Componente(ch_qtd_creditos=4)
    cc.ch_semanal_1s = None
    cc.ch_semanal_2s = 6
    assert cc.get_ch_semanal(semestre=None) == 4


def test_ch_semanal_semestre_none_sem_ch_configurada():
    cc = ComponenteCurricular()
    cc.componente = Componente(ch_qtd_creditos=0)
    cc.ch_semanal_1s = None
    cc.ch_semanal_2s = None
    assert cc.get_ch_semanal(semestre=None) == 0


# --- ProfessorDiario.get_qtd_creditos_efetiva -------------------------------


def _criar_professor_diario(
    *,
    is_anual=False,
    is_semestral_em_calendario_anual=False,
    diario_segundo_semestre=False,
    cc_segundo_semestre=False,
    ch_semanal_1s=4,
    ch_semanal_2s=6,
    ch_qtd_creditos=4,
    percentual_ch=100,
    periodo_letivo_ch=None,
):
    cc = ComponenteCurricular()
    cc.componente = Componente(ch_qtd_creditos=ch_qtd_creditos)
    cc.segundo_semestre = cc_segundo_semestre
    cc.ch_semanal_1s = ch_semanal_1s
    cc.ch_semanal_2s = ch_semanal_2s

    diario = Diario()
    diario.componente_curricular = cc
    diario.is_anual = Mock(return_value=is_anual)
    diario.is_semestral_em_calendario_anual = Mock(return_value=is_semestral_em_calendario_anual)
    diario.segundo_semestre = diario_segundo_semestre

    pd = ProfessorDiario(percentual_ch=percentual_ch, periodo_letivo_ch=periodo_letivo_ch)
    pd.diario = diario
    return pd


def test_qtd_creditos_efetiva_diario_semestral_regular():
    pd = _criar_professor_diario(
        is_anual=False,
        is_semestral_em_calendario_anual=False,
        ch_semanal_1s=4,
        ch_semanal_2s=0,
    )
    # Em diário semestral regular (não anual), consulta cc.get_ch_semanal(None)
    # mantendo os créditos efetivos tanto no período letivo 1 quanto no 2
    assert pd.get_qtd_creditos_efetiva(periodo_letivo=1) == 4
    assert pd.get_qtd_creditos_efetiva(periodo_letivo=2) == 4


def test_qtd_creditos_efetiva_diario_anual_regular():
    pd = _criar_professor_diario(
        is_anual=True,
        is_semestral_em_calendario_anual=False,
        ch_semanal_1s=4,
        ch_semanal_2s=6,
    )
    assert pd.get_qtd_creditos_efetiva(periodo_letivo=1) == 4
    assert pd.get_qtd_creditos_efetiva(periodo_letivo=2) == 6


def test_qtd_creditos_efetiva_semestral_em_calendario_anual_alternado():
    # CC previsto para o 2º semestre (ch_2s=6), mas ofertado no 1º semestre do diário
    pd = _criar_professor_diario(
        is_anual=True,
        is_semestral_em_calendario_anual=True,
        diario_segundo_semestre=False,
        cc_segundo_semestre=True,
        ch_semanal_1s=0,
        ch_semanal_2s=6,
    )
    # periodo_letivo=1 inverte e busca carga horária do semestre 2 (6 créditos)
    assert pd.get_qtd_creditos_efetiva(periodo_letivo=1) == 6
    # periodo_letivo=2 inverte e busca carga horária do semestre 1 (0 créditos)
    assert pd.get_qtd_creditos_efetiva(periodo_letivo=2) == 0


def test_qtd_creditos_efetiva_semestral_em_calendario_anual_sem_alternancia():
    # CC previsto para o 2º semestre (ch_2s=6) e ofertado no 2º semestre do diário
    pd = _criar_professor_diario(
        is_anual=True,
        is_semestral_em_calendario_anual=True,
        diario_segundo_semestre=True,
        cc_segundo_semestre=True,
        ch_semanal_1s=0,
        ch_semanal_2s=6,
    )
    # periodo_letivo=1 não tem aulas (0)
    assert pd.get_qtd_creditos_efetiva(periodo_letivo=1) == 0
    # periodo_letivo=2 busca normalmente do 2º semestre (6)
    assert pd.get_qtd_creditos_efetiva(periodo_letivo=2) == 6


def test_qtd_creditos_efetiva_percentual_parcial_arredonda_para_cima():
    pd = _criar_professor_diario(
        is_anual=False,
        ch_semanal_1s=5,
        percentual_ch=50,
    )
    # 5 créditos * 50% = 2.5 -> math.ceil -> 3 créditos
    assert pd.get_qtd_creditos_efetiva(periodo_letivo=1) == 3


def test_qtd_creditos_efetiva_sem_percentual_ch_retorna_zero():
    pd = _criar_professor_diario(
        is_anual=False,
        ch_semanal_1s=4,
        percentual_ch=None,
    )
    assert pd.get_qtd_creditos_efetiva(periodo_letivo=1) == 0


# --- MatriculaDiario.realizou_todas_avaliacoes_regulares --------------------


def _realizou(qtd_avaliacoes, conceito=False, **notas):
    diario = Mock()
    diario.componente_curricular.qtd_avaliacoes = qtd_avaliacoes
    diario.is_lancamento_conceito.return_value = conceito
    with patch.object(MatriculaDiario, 'diario', new_callable=PropertyMock, return_value=diario):
        matricula = MatriculaDiario()
        for campo, valor in notas.items():
            setattr(matricula, campo, valor)
        return matricula.realizou_todas_avaliacoes_regulares()


def test_realizou_quando_nao_ha_avaliacoes():
    assert _realizou(qtd_avaliacoes=0) is True


def test_nao_realizou_quando_lancamento_por_conceito():
    assert _realizou(qtd_avaliacoes=2, conceito=True) is False


def test_realizou_uma_avaliacao():
    assert _realizou(qtd_avaliacoes=1, nota_1=9) is True
    assert _realizou(qtd_avaliacoes=1, nota_1=None) is False


def test_realizou_duas_avaliacoes():
    assert _realizou(qtd_avaliacoes=2, nota_1=9, nota_2=8) is True
    assert _realizou(qtd_avaliacoes=2, nota_1=9, nota_2=None) is False


def test_realizou_quatro_avaliacoes():
    assert _realizou(qtd_avaliacoes=4, nota_1=9, nota_2=8, nota_3=7, nota_4=6) is True
    assert _realizou(qtd_avaliacoes=4, nota_1=9, nota_2=8, nota_3=7, nota_4=None) is False
