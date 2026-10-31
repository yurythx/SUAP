import datetime

import pytest

from boletim_servico import models


@pytest.mark.django_db
def test_gera_boletim_diario_com_documentos_do_dia(criar_documento, criar_boletim_programado):
    criar_documento()
    criar_documento()

    criar_boletim_programado()

    boletim = models.BoletimDiario.objects.get()
    assert models.BoletimDiario.objects.count() == 1
    assert boletim.documentos.count() == 2


@pytest.mark.django_db
def test_gera_edicoes_extras_incrementais_para_mesma_data(criar_documento, criar_boletim_programado):
    documento_primeira_edicao = criar_documento()
    boletim_programado = criar_boletim_programado()

    primeira_edicao = models.BoletimDiario.objects.get()
    assert primeira_edicao.edicao_extra == 0
    assert primeira_edicao.documentos.get() == documento_primeira_edicao

    documento_segunda_edicao = criar_documento()
    boletim_programado.gerar_boletim_diario(data=datetime.datetime(2018, 8, 13))
    segunda_edicao = models.BoletimDiario.objects.order_by('id').last()
    assert segunda_edicao.edicao_extra == 1
    assert segunda_edicao.data == primeira_edicao.data
    assert segunda_edicao.documentos.get() == documento_segunda_edicao

    documento_terceira_edicao = criar_documento()
    boletim_programado.gerar_boletim_diario(data=datetime.datetime(2018, 8, 13))
    terceira_edicao = models.BoletimDiario.objects.order_by('id').last()
    assert terceira_edicao.edicao_extra == 2
    assert terceira_edicao.documentos.get() == documento_terceira_edicao
