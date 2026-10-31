"""Empenhos do SIAFI sem requisição de despesa (``NotaEmpenho.get_empenhos_sem_requisicao`` e helpers).

Um documento de empenho (NE ou RO) aparece quando nenhuma requisição o informou, salvo quando o
empenho se compensa (NE + ROs somam zero) e não há nada a regularizar.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from plan_estrategico.models import NotaEmpenho, PlanoAtividade
from plan_estrategico.tests.factories import NotaEmpenhoFactory, PlanoInternoPlanoAtividadeFactory
from tesouro_gerencial.models import DocumentoEmpenho, EventoNotaEmpenho
from tesouro_gerencial.tests.factories import (
    DocumentoEmpenhoFactory,
    DocumentoEmpenhoItemFactory,
    EventoNotaEmpenhoFactory,
    PlanoInternoFactory,
    UnidadeGestoraFactory,
)

pytestmark = pytest.mark.django_db

ANO = date.today().year
CODIGOS_UG = ['999001']
INCLUSAO, REFORCO, ANULACAO = EventoNotaEmpenho.INCLUSAO, EventoNotaEmpenho.REFORCO, EventoNotaEmpenho.ANULACAO


@pytest.fixture
def plano_atividade() -> PlanoAtividade:
    return PlanoInternoPlanoAtividadeFactory().plano_atividade


def empenho(numero: str, valor: str, evento: int = INCLUSAO, inicial: DocumentoEmpenho | None = None, **kwargs: object) -> DocumentoEmpenho:
    """Documento de empenho com um item; ``inicial`` faz dele um RO daquela NE."""
    tipo = DocumentoEmpenho.TIPO_RO if inicial else DocumentoEmpenho.TIPO_NE
    documento = DocumentoEmpenhoFactory(numero=numero, tipo=tipo, documento_empenho_inicial=inicial, **kwargs)
    DocumentoEmpenhoItemFactory(documento_empenho=documento, valor=Decimal(valor), evento=EventoNotaEmpenhoFactory(codigo=str(evento)))
    return documento


def numeros_sem_requisicao(plano_atividade: PlanoAtividade) -> set[str]:
    return set(NotaEmpenho.get_empenhos_sem_requisicao(plano_atividade, CODIGOS_UG).values_list('numero', flat=True))


def test_ne_sem_requisicao_aparece_e_some_quando_informada(plano_atividade: PlanoAtividade) -> None:
    ne = empenho(f'{ANO}NE000001', '1000.00')
    assert numeros_sem_requisicao(plano_atividade) == {ne.numero}

    nota = NotaEmpenhoFactory(numero_empenho=ne.numero)
    assert numeros_sem_requisicao(plano_atividade) == set()

    # Linha cancelada não conta como requisição.
    nota.status = NotaEmpenho.STATUS_CANCELADA
    nota.save()
    assert numeros_sem_requisicao(plano_atividade) == {ne.numero}


def test_ignora_ne_sem_itens_e_fora_do_ano_da_ug_ou_do_pi_do_plano(plano_atividade: PlanoAtividade) -> None:
    DocumentoEmpenhoFactory(numero=f'{ANO}NE000001', tipo=DocumentoEmpenho.TIPO_NE)
    empenho(f'{ANO - 1}NE000002', '1000.00', data_emissao=date(ANO - 1, 6, 1))
    empenho(f'{ANO}NE000003', '1000.00', emitente_ug=UnidadeGestoraFactory(codigo='888001'))
    empenho(f'{ANO}NE000004', '1000.00', plano_interno=PlanoInternoFactory(codigo='FORA'))

    assert numeros_sem_requisicao(plano_atividade) == set()


@pytest.mark.parametrize(('evento', 'valor'), [(REFORCO, '300.00'), (ANULACAO, '-300.00')])
def test_ro_de_reforco_ou_anulacao_aparece_ate_ser_informado(plano_atividade: PlanoAtividade, evento: int, valor: str) -> None:
    ne = empenho(f'{ANO}NE000001', '1000.00')
    ro = empenho(f'{ANO}RO000001', valor, evento=evento, inicial=ne)
    NotaEmpenhoFactory(numero_empenho=ne.numero)
    assert numeros_sem_requisicao(plano_atividade) == {ro.numero}

    NotaEmpenhoFactory(numero_empenho=ne.numero, numero_ro=ro.numero)
    assert numeros_sem_requisicao(plano_atividade) == set()


def test_ro_de_inclusao_segue_a_ne_de_origem(plano_atividade: PlanoAtividade) -> None:
    ne = empenho(f'{ANO - 1}NE000001', '1000.00', data_emissao=date(ANO - 1, 6, 1))
    ro = empenho(f'{ANO}RO000001', '200.00', inicial=ne)
    assert numeros_sem_requisicao(plano_atividade) == {ro.numero}

    NotaEmpenhoFactory(numero_empenho=ne.numero)
    assert numeros_sem_requisicao(plano_atividade) == set()


def test_empenho_anulado_por_inteiro_sem_requisicao_nao_aparece(plano_atividade: PlanoAtividade) -> None:
    ne = empenho(f'{ANO}NE000001', '1000.00')
    empenho(f'{ANO}RO000001', '-1000.00', evento=ANULACAO, inicial=ne)

    assert numeros_sem_requisicao(plano_atividade) == set()


def test_inclusao_e_anulacao_por_ro_de_mesmo_valor_se_compensam(plano_atividade: PlanoAtividade) -> None:
    """Formato do SIAFI desde 2021: NE sem itens, inclusão (positiva) e anulação (negativa) chegam como ROs.

    O importador grava o valor com o sinal da planilha, "(1.000,00)" vira -1000; a compensação depende disso.
    """
    ne = DocumentoEmpenhoFactory(numero=f'{ANO}NE000001', tipo=DocumentoEmpenho.TIPO_NE)
    inclusao = empenho(f'{ANO}RO000001', '1000.00', evento=INCLUSAO, inicial=ne)
    empenho(f'{ANO}RO000002', '-1000.00', evento=ANULACAO, inicial=ne)
    assert numeros_sem_requisicao(plano_atividade) == set()

    empenho(f'{ANO}RO000003', '-400.00', evento=ANULACAO, inicial=ne)
    assert numeros_sem_requisicao(plano_atividade) == {inclusao.numero, f'{ANO}RO000002', f'{ANO}RO000003'}


def test_saldo_zero_considera_ro_de_outro_ano(plano_atividade: PlanoAtividade) -> None:
    ne = empenho(f'{ANO}NE000001', '1000.00')
    empenho(f'{ANO + 1}RO000001', '-1000.00', evento=ANULACAO, inicial=ne, data_emissao=date(ANO + 1, 1, 10))

    assert numeros_sem_requisicao(plano_atividade) == set()


def test_empenho_zerado_em_requisicao_mantem_os_ros_pendentes(plano_atividade: PlanoAtividade) -> None:
    """NE informada e saldo total zero, mas os ROs sem requisição não se compensam: ainda há o que regularizar."""
    ne = empenho(f'{ANO}NE000001', '1000.00')
    NotaEmpenhoFactory(numero_empenho=ne.numero)
    reforco = empenho(f'{ANO}RO000001', '500.00', evento=REFORCO, inicial=ne)
    anulacao = empenho(f'{ANO}RO000002', '-1500.00', evento=ANULACAO, inicial=ne)

    assert numeros_sem_requisicao(plano_atividade) == {reforco.numero, anulacao.numero}


def test_reforco_e_anulacao_que_se_compensam_nao_aparecem(plano_atividade: PlanoAtividade) -> None:
    ne = empenho(f'{ANO}NE000001', '1000.00')
    NotaEmpenhoFactory(numero_empenho=ne.numero)
    empenho(f'{ANO}RO000001', '500.00', evento=REFORCO, inicial=ne)
    empenho(f'{ANO}RO000002', '-500.00', evento=ANULACAO, inicial=ne)

    assert numeros_sem_requisicao(plano_atividade) == set()


def test_reforco_e_anulacao_que_nao_se_compensam_aparecem(plano_atividade: PlanoAtividade) -> None:
    ne = empenho(f'{ANO}NE000001', '1000.00')
    NotaEmpenhoFactory(numero_empenho=ne.numero)
    reforco = empenho(f'{ANO}RO000001', '500.00', evento=REFORCO, inicial=ne)
    anulacao = empenho(f'{ANO}RO000002', '-200.00', evento=ANULACAO, inicial=ne)

    assert numeros_sem_requisicao(plano_atividade) == {reforco.numero, anulacao.numero}


def test_get_empenhos_com_saldo_zero_soma_ne_e_ros() -> None:
    zerada = empenho(f'{ANO}NE000001', '1000.00')
    empenho(f'{ANO}RO000001', '-1000.00', evento=ANULACAO, inicial=zerada)
    com_saldo = empenho(f'{ANO}NE000002', '1000.00')
    empenho(f'{ANO}RO000002', '-400.00', evento=ANULACAO, inicial=com_saldo)

    assert NotaEmpenho.get_empenhos_com_saldo_zero({zerada.numero, com_saldo.numero}) == {zerada.numero}


def test_get_empenhos_em_requisicao_pela_ne_ou_pelo_ro() -> None:
    pela_ne = empenho(f'{ANO}NE000001', '1000.00')
    pelo_ro = empenho(f'{ANO}NE000002', '1000.00')
    ro = empenho(f'{ANO}RO000001', '-1000.00', evento=ANULACAO, inicial=pelo_ro)
    sem_requisicao = empenho(f'{ANO}NE000003', '1000.00')
    NotaEmpenhoFactory(numero_empenho=pela_ne.numero)
    NotaEmpenhoFactory(numero_empenho=None, numero_ro=ro.numero)
    notas = NotaEmpenho.objects.exclude(status=NotaEmpenho.STATUS_CANCELADA)
    numeros_ne = notas.filter(numero_empenho__isnull=False).values('numero_empenho')
    numeros_ro = notas.filter(numero_ro__isnull=False).values('numero_ro')
    empenhos = {pela_ne.numero, pelo_ro.numero, sem_requisicao.numero}

    assert NotaEmpenho.get_empenhos_em_requisicao(empenhos, numeros_ne, numeros_ro) == {pela_ne.numero, pelo_ro.numero}
    assert NotaEmpenho.get_empenhos_em_requisicao(set(), numeros_ne, numeros_ro) == set()


def test_registros_trazem_cada_item_com_empenho_de_origem_e_macroprocesso(plano_atividade: PlanoAtividade) -> None:
    ne = empenho(f'{ANO}NE000001', '1000.00')
    ro = empenho(f'{ANO}RO000001', '-300.00', evento=ANULACAO, inicial=ne)

    registros = NotaEmpenho.get_registros_empenhos_sem_requisicao(plano_atividade, CODIGOS_UG)

    assert [(r.documento_empenho.numero, r.numero_empenho, r.valor, r.evento.codigo) for r in registros] == [
        (ne.numero, ne.numero, Decimal('1000.00'), str(INCLUSAO)),
        (ro.numero, ne.numero, Decimal('-300.00'), str(ANULACAO)),
    ]
    assert {r.macroprocesso for r in registros} == {'01-Manutenção do campus'}
