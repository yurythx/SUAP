"""Consolidação de afastamentos do PAINT (``AfastamentoService``).

O serviço desconta do planejamento mensal do auditor as horas em que ele esteve
afastado, juntando três fontes: os afastamentos que o próprio auditor declarou,
as férias vindas do app ``ferias`` e os afastamentos concedidos pelo RH (SIAPE).

As fontes se sobrepõem — o auditor declara as férias que já sabe que vai tirar e
o mesmo período volta pela sincronização. O invariante que estes testes protegem
é que **um dia afastado desconta uma vez**, não uma vez por fonte que o cobre.
"""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest

from auditoria.forms.afastamento import AfastamentoForm
from auditoria.services.afastamento_service import AfastamentoService
from auditoria.tests import factories as f
from comum.tests.factories import AnoFactory
from ferias.models import Ferias
from ferias.tests.factories import FeriasFactory, ParcelaFeriasFactory
from rh.tests.factories import JornadaTrabalhoFactory, ServidorAfastamentoFactory, ServidorFactory

ANO = 2026
JULHO = 7
JORNADA_DIARIA = 8

# Julho/2026 tem 23 dias úteis (nenhum feriado cadastrado no cenário).
CH_PREVISTA_MENSAL = 23 * JORNADA_DIARIA

# 06 a 10/07/2026 é uma segunda a sexta cheia: 5 dias úteis.
SEMANA_INICIO = date(ANO, JULHO, 6)
SEMANA_FIM = date(ANO, JULHO, 10)
CH_SEMANA = 5 * JORNADA_DIARIA


@pytest.fixture
def cenario_paint(db, sync_permissions) -> SimpleNamespace:
    """PAINT de 2026 com um auditor e seus doze planejamentos mensais.

    O auditor tem jornada de 40h semanais (8h/dia) para que a conversão de dias
    úteis em horas seja previsível. Nenhum afastamento é criado aqui: cada teste
    monta as fontes que quer exercitar.
    """
    auditor = ServidorFactory(jornada_trabalho=JornadaTrabalhoFactory(codigo='40S', nome='40 HORAS SEMANAIS'))

    paint = f.PaintFactory(ano=AnoFactory(ano=ANO))
    planejamento = f.PlanejamentoAnualFactory(auditor=auditor, paint=paint, carga_horaria_prevista=12 * CH_PREVISTA_MENSAL)
    mensais = {
        mes: f.PlanejamentoMensalFactory(planejamento_anual=planejamento, mes=mes, carga_horaria_prevista=CH_PREVISTA_MENSAL) for mes in range(1, 13)
    }

    return SimpleNamespace(auditor=auditor, paint=paint, planejamento=planejamento, mensais=mensais, julho=mensais[JULHO])


def criar_ferias(auditor, data_inicio: date, data_fim: date, *, validado: int = Ferias.VALIDADO) -> None:
    """Registra uma parcela de férias do auditor no período informado."""
    ferias = FeriasFactory(servidor=auditor, ano=AnoFactory(ano=ANO), validado=validado)
    ParcelaFeriasFactory(ferias=ferias, data_inicio=data_inicio, data_fim=data_fim)


def ch_afastada_de_julho(cenario: SimpleNamespace) -> float:
    """Horas descontadas de julho, lidas do planejamento mensal já gravado."""
    cenario.julho.refresh_from_db()
    return CH_PREVISTA_MENSAL - cenario.julho.carga_horaria_homologada


@pytest.mark.django_db(databases='__all__')
class TestFeriasNaoValidadasNaoDescontam:
    def test_ferias_pendentes_de_validacao_nao_descontam_horas(self, cenario_paint):
        """Férias que a chefia ainda não validou não são afastamento consolidado.

        O serviço declara buscar "dados fonte homologadas" e já filtra
        ``cancelado=False`` nos afastamentos do RH; as férias precisam do filtro
        equivalente, senão um pedido de férias ainda em análise derruba a carga
        horária planejada do auditor.
        """
        criar_ferias(cenario_paint.auditor, SEMANA_INICIO, SEMANA_FIM, validado=Ferias.PENDENTE)

        AfastamentoService(cenario_paint.planejamento).importar_afastamentos()

        assert ch_afastada_de_julho(cenario_paint) == 0

    def test_ferias_invalidadas_nao_descontam_horas(self, cenario_paint):
        criar_ferias(cenario_paint.auditor, SEMANA_INICIO, SEMANA_FIM, validado=Ferias.INVALIDADO)

        AfastamentoService(cenario_paint.planejamento).importar_afastamentos()

        assert ch_afastada_de_julho(cenario_paint) == 0

    def test_ferias_validadas_descontam_horas(self, cenario_paint):
        criar_ferias(cenario_paint.auditor, SEMANA_INICIO, SEMANA_FIM)

        AfastamentoService(cenario_paint.planejamento).importar_afastamentos()

        assert ch_afastada_de_julho(cenario_paint) == CH_SEMANA


@pytest.mark.django_db(databases='__all__')
class TestDiaAfastadoDescontaUmaVez:
    """Um dia coberto por mais de uma fonte desconta uma vez só.

    É o caso que os auditores levantaram: o auditor declara as férias que já
    combinou e, depois, a sincronização traz as mesmas férias do ``ferias``.
    """

    def test_periodo_declarado_a_mao_e_importado_desconta_uma_vez(self, cenario_paint):
        f.AfastamentoPlanejadoFactory(planejamento=cenario_paint.julho, data_inicio=SEMANA_INICIO, data_fim=SEMANA_FIM)
        criar_ferias(cenario_paint.auditor, SEMANA_INICIO, SEMANA_FIM)

        AfastamentoService(cenario_paint.planejamento).importar_afastamentos()

        assert ch_afastada_de_julho(cenario_paint) == CH_SEMANA

    def test_sobreposicao_parcial_desconta_apenas_os_dias_distintos(self, cenario_paint):
        """Manual 06-10/07 e férias 08-14/07 cobrem 7 dias úteis distintos.

        06, 07, 08, 09, 10 (seg a sex) mais 13 e 14 (seg e ter) — 08, 09 e 10
        aparecem nas duas fontes e não podem contar duas vezes.
        """
        f.AfastamentoPlanejadoFactory(planejamento=cenario_paint.julho, data_inicio=SEMANA_INICIO, data_fim=SEMANA_FIM)
        criar_ferias(cenario_paint.auditor, date(ANO, JULHO, 8), date(ANO, JULHO, 14))

        AfastamentoService(cenario_paint.planejamento).importar_afastamentos()

        assert ch_afastada_de_julho(cenario_paint) == 7 * JORNADA_DIARIA

    def test_periodos_disjuntos_continuam_somando(self, cenario_paint):
        """Guarda de regressão: sem sobreposição, nada muda."""
        f.AfastamentoPlanejadoFactory(planejamento=cenario_paint.julho, data_inicio=SEMANA_INICIO, data_fim=SEMANA_FIM)
        criar_ferias(cenario_paint.auditor, date(ANO, JULHO, 13), date(ANO, JULHO, 17))

        AfastamentoService(cenario_paint.planejamento).importar_afastamentos()

        assert ch_afastada_de_julho(cenario_paint) == 10 * JORNADA_DIARIA

    def test_ferias_e_afastamento_do_rh_no_mesmo_periodo_descontam_uma_vez(self, cenario_paint):
        """As duas fontes sincronizadas também podem se sobrepor entre si."""
        criar_ferias(cenario_paint.auditor, SEMANA_INICIO, SEMANA_FIM)
        ServidorAfastamentoFactory(servidor=cenario_paint.auditor, data_inicio=SEMANA_INICIO, data_termino=SEMANA_FIM)

        AfastamentoService(cenario_paint.planejamento).importar_afastamentos()

        assert ch_afastada_de_julho(cenario_paint) == CH_SEMANA

    def test_saldo_do_mes_nao_conta_o_dia_duas_vezes(self, cenario_paint):
        """O saldo exibido na tela usa o mesmo critério do valor gravado.

        ``carga_horaria_afastada`` somava registro a registro, então mostrava o
        dobro assim que a sincronização criava a linha importada ao lado da
        declarada à mão.
        """
        f.AfastamentoPlanejadoFactory(planejamento=cenario_paint.julho, data_inicio=SEMANA_INICIO, data_fim=SEMANA_FIM)
        criar_ferias(cenario_paint.auditor, SEMANA_INICIO, SEMANA_FIM)

        AfastamentoService(cenario_paint.planejamento).importar_afastamentos()

        cenario_paint.julho.refresh_from_db()
        assert cenario_paint.julho.carga_horaria_afastada == CH_SEMANA
        assert cenario_paint.julho.saldo == CH_PREVISTA_MENSAL - CH_SEMANA


@pytest.mark.django_db(databases='__all__')
class TestAfastamentoFormRejeitaSobreposicao:
    """O formulário não deixa o auditor declarar duas vezes o mesmo dia.

    O cálculo já é imune à sobreposição, mas duas linhas para o mesmo período
    continuariam aparecendo na tela do planejamento sem explicação.
    """

    def _dados(self, data_inicio: date, data_fim: date) -> dict:
        return {
            'data_inicio': data_inicio.strftime('%d/%m/%Y'),
            'data_fim': data_fim.strftime('%d/%m/%Y'),
            'motivo': 'Curso de capacitação',
            'tipo_afastamento': f.TipoAfastamentoFactory().pk,
        }

    def test_rejeita_afastamento_que_sobrepoe_outro_do_mesmo_mes(self, cenario_paint):
        f.AfastamentoPlanejadoFactory(planejamento=cenario_paint.julho, data_inicio=SEMANA_INICIO, data_fim=SEMANA_FIM)

        form = AfastamentoForm(self._dados(date(ANO, JULHO, 8), date(ANO, JULHO, 14)), planejamento=cenario_paint.julho)

        assert not form.is_valid()
        assert 'sobrepõe' in str(form.errors).lower()

    def test_aceita_afastamento_em_periodo_livre(self, cenario_paint):
        f.AfastamentoPlanejadoFactory(planejamento=cenario_paint.julho, data_inicio=SEMANA_INICIO, data_fim=SEMANA_FIM)

        form = AfastamentoForm(self._dados(date(ANO, JULHO, 13), date(ANO, JULHO, 17)), planejamento=cenario_paint.julho)

        assert form.is_valid(), form.errors

    def test_edicao_nao_conflita_com_o_proprio_registro(self, cenario_paint):
        """Editar o motivo de um afastamento não pode esbarrar nele mesmo."""
        afastamento = f.AfastamentoPlanejadoFactory(planejamento=cenario_paint.julho, data_inicio=SEMANA_INICIO, data_fim=SEMANA_FIM)

        form = AfastamentoForm(self._dados(SEMANA_INICIO, SEMANA_FIM), instance=afastamento, planejamento=cenario_paint.julho)

        assert form.is_valid(), form.errors


@pytest.mark.django_db(databases='__all__')
class TestSincronizacaoDesligadaNoPaint:
    """O PAINT controla se a consolidação busca férias e afastamentos do SUAP.

    Desligada, a sincronização **congela** o que já veio: os registros importados
    continuam valendo, mas nenhuma fonte nova é consultada.
    """

    def test_paint_novo_nasce_com_a_sincronizacao_ligada(self, cenario_paint):
        assert cenario_paint.paint.sincronizar_afastamentos_suap is True

    def test_nao_importa_ferias_com_a_sincronizacao_desligada(self, cenario_paint):
        cenario_paint.paint.sincronizar_afastamentos_suap = False
        cenario_paint.paint.save(update_fields=['sincronizar_afastamentos_suap'])
        criar_ferias(cenario_paint.auditor, SEMANA_INICIO, SEMANA_FIM)

        AfastamentoService(cenario_paint.planejamento).importar_afastamentos()

        assert ch_afastada_de_julho(cenario_paint) == 0
        assert not cenario_paint.julho.afastamentos.filter(importado=True).exists()

    def test_afastamento_declarado_continua_descontando_com_a_sincronizacao_desligada(self, cenario_paint):
        cenario_paint.paint.sincronizar_afastamentos_suap = False
        cenario_paint.paint.save(update_fields=['sincronizar_afastamentos_suap'])
        f.AfastamentoPlanejadoFactory(planejamento=cenario_paint.julho, data_inicio=SEMANA_INICIO, data_fim=SEMANA_FIM)

        AfastamentoService(cenario_paint.planejamento).importar_afastamentos()

        assert ch_afastada_de_julho(cenario_paint) == CH_SEMANA

    def test_desligar_congela_o_que_ja_havia_sido_importado(self, cenario_paint):
        """Férias importadas antes continuam valendo; férias novas não entram."""
        criar_ferias(cenario_paint.auditor, SEMANA_INICIO, SEMANA_FIM)
        AfastamentoService(cenario_paint.planejamento).importar_afastamentos()

        cenario_paint.paint.sincronizar_afastamentos_suap = False
        cenario_paint.paint.save(update_fields=['sincronizar_afastamentos_suap'])
        criar_ferias(cenario_paint.auditor, date(ANO, JULHO, 13), date(ANO, JULHO, 17))

        AfastamentoService(cenario_paint.planejamento).importar_afastamentos()

        assert cenario_paint.julho.afastamentos.filter(importado=True).count() == 1
        assert ch_afastada_de_julho(cenario_paint) == CH_SEMANA
