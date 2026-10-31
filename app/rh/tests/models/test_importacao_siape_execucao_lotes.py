"""Detecção de deadlock para a retentativa de lote da importação SIAPE."""

import psycopg
from django.db import OperationalError

from rh.importacao_siape.execucao_lotes import _eh_deadlock


def _operational_error_com_causa(causa: BaseException | None) -> OperationalError:
    erro = OperationalError('erro de banco')
    erro.__cause__ = causa
    return erro


def test_reconhece_deadlock_pelo_tipo_da_causa():
    assert _eh_deadlock(_operational_error_com_causa(psycopg.errors.DeadlockDetected('deadlock detected'))) is True


def test_reconhece_deadlock_pelo_sqlstate_mesmo_com_outro_tipo_de_causa():
    # mais robusto que depender só do tipo: um driver que troque a classe da exceção, mas
    # mantenha o sqlstate 40P01, ainda deve ser reconhecido como deadlock.
    causa = psycopg.errors.LockNotAvailable('lock not available')
    causa.sqlstate = '40P01'
    assert _eh_deadlock(_operational_error_com_causa(causa)) is True


def test_nao_reconhece_outro_erro_operacional_do_banco():
    assert _eh_deadlock(_operational_error_com_causa(psycopg.errors.UniqueViolation('duplicado'))) is False


def test_nao_reconhece_operational_error_sem_causa():
    assert _eh_deadlock(OperationalError('erro de banco')) is False


def test_nao_reconhece_excecao_que_nao_e_operational_error():
    assert _eh_deadlock(_operational_error_com_causa(psycopg.errors.DeadlockDetected('deadlock')).__cause__) is False
    assert _eh_deadlock(RuntimeError('outra coisa')) is False
