import datetime
import json
import re

from freezegun import freeze_time

from djtools.history import serializers
from djtools.history.constants import STATUS_VIEWED
from djtools.history.serializers import get_now_formatted

# Formato que o parser do fluentbit espera: %Y-%m-%dT%H:%M:%S.%L (fração obrigatória).
FLUENTBIT_RE = re.compile(r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}$')


@freeze_time('2026-05-27 20:06:33')
def test_get_now_formatted_inclui_fracao_quando_microsecond_zero():
    # Regressão: isoformat() sem timespec omitia a fração com microsecond == 0,
    # gerando '2026-05-27T20:06:33' e quebrando o parser do fluentbit.
    assert get_now_formatted() == '2026-05-27T20:06:33.000000'


@freeze_time('2026-05-27 20:06:33.123456')
def test_get_now_formatted_preserva_microssegundos():
    assert get_now_formatted() == '2026-05-27T20:06:33.123456'


@freeze_time('2026-05-27 20:06:33')
def test_get_now_formatted_casa_com_formato_fluentbit():
    assert FLUENTBIT_RE.match(get_now_formatted())


@freeze_time('2026-05-27 20:06:33')
def test_get_now_formatted_eh_parseavel_de_volta():
    valor = get_now_formatted()
    assert datetime.datetime.fromisoformat(valor) == datetime.datetime(2026, 5, 27, 20, 6, 33)


def _capturar_record(monkeypatch, pk):
    registros = []
    monkeypatch.setattr(serializers, 'get_qualified_model_name', lambda inst: 'app.Modelo')
    monkeypatch.setattr(serializers, 'get_request_data', dict)
    monkeypatch.setattr(serializers.log, 'info', registros.append)

    historia = type('History', (), {'disabled': False})
    instancia = type('Obj', (), {'pk': pk, 'History': historia})()

    # STATUS_VIEWED pula o cálculo de diff (não exige campos do modelo).
    serializers.process_data(instancia, None, STATUS_VIEWED)
    assert registros, 'esperava um log emitido'
    return json.loads(registros[0])


def test_process_data_emite_pk_hash_como_string(monkeypatch):
    # Regressão: PK não-inteiro (hash/UUID) era rejeitado no OpenSearch (campo [long]).
    record = _capturar_record(monkeypatch, '227e1d3b57296f9e4afd0de57a2e64b13e6ecce3')
    assert record['pk'] == '227e1d3b57296f9e4afd0de57a2e64b13e6ecce3'
    assert isinstance(record['pk'], str)


def test_process_data_converte_pk_inteiro_para_string(monkeypatch):
    record = _capturar_record(monkeypatch, 123)
    assert record['pk'] == '123'
    assert isinstance(record['pk'], str)


def test_process_data_preserva_pk_none(monkeypatch):
    record = _capturar_record(monkeypatch, None)
    assert record['pk'] is None
