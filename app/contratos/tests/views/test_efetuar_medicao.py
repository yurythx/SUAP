"""Efetuar medição de parcela em contrato que exige empenho (``/contratos/efetuar_medicao/``)."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from django.contrib.auth.models import Group
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test.client import Client

from contratos.models import DocumentoEmpenhoContrato, DocumentoEmpenhoContratoMedicao, Fiscal, Medicao, Parcela
from contratos.tests.factories import DocumentoEmpenhoContratoFactory, FiscalFactory, ParcelaFactory
from protocolo.tests.factories import ProcessoFactory
from rh.tests.factories import ServidorFactory
from tesouro_gerencial.tests.factories import DocumentoEmpenhoItemFactory


@pytest.fixture
def fiscal(sync_permissions: None, settings: Any, tmp_path: Path) -> Fiscal:
    """Fiscal do contrato, no grupo que dá ``contratos.pode_efetuar_medicao``; arquivos vão para ``tmp_path``."""
    settings.MEDIA_ROOT = str(tmp_path)
    servidor = ServidorFactory()
    servidor.get_user().groups.add(Group.objects.get(name='Fiscal de Contrato'))
    processo = ProcessoFactory(vinculo_cadastro=servidor.get_vinculo(), setor_origem=servidor.setor)
    return FiscalFactory(servidor=servidor, contrato__processo=processo, contrato__campus_gerenciador=servidor.setor.uo)


def _empenho_do_contrato(fiscal: Fiscal, saldo: Decimal) -> DocumentoEmpenhoContrato:
    documento = DocumentoEmpenhoContratoFactory(contrato=fiscal.contrato)
    DocumentoEmpenhoItemFactory(documento_empenho=documento.empenho, valor=saldo)
    return documento


def _post_medicao(client: Client, parcela: Parcela, documento: DocumentoEmpenhoContrato, valor: str) -> object:
    contrato = parcela.cronograma.contrato
    dados = {
        'data_inicio': parcela.data_prevista_inicio.strftime('%d/%m/%Y'),
        'data_fim': parcela.data_prevista_fim.strftime('%d/%m/%Y'),
        'numero_documento': 'NF 123',
        'valor_executado': valor,
        'processo': contrato.processo_id,
        'campus': contrato.campus_gerenciador_id,
        'arquivo_medicao': SimpleUploadedFile('medicao.pdf', b'%PDF-1.4 medicao', content_type='application/pdf'),
        'ocorrencia': '',
        'providencia': '',
        'documentos_empenho_medicao-TOTAL_FORMS': '1',
        'documentos_empenho_medicao-INITIAL_FORMS': '0',
        'documentos_empenho_medicao-MIN_NUM_FORMS': '1',
        'documentos_empenho_medicao-MAX_NUM_FORMS': '1000',
        'documentos_empenho_medicao-0-documento_empenho_contrato': documento.pk,
        'documentos_empenho_medicao-0-valor': valor,
    }
    return client.post(f'/contratos/efetuar_medicao/{parcela.pk}/{contrato.pk}/', dados)


@pytest.mark.django_db
def test_medicao_com_valor_acima_do_saldo_do_empenho_nao_e_gravada(client: Client, fiscal: Fiscal) -> None:
    """Formset de empenhos inválido: nada é gravado e a tela volta com o erro (#17747)."""
    documento = _empenho_do_contrato(fiscal, saldo=Decimal('1000.00'))
    parcela = ParcelaFactory(cronograma__contrato=fiscal.contrato)
    client.force_login(fiscal.servidor.get_user())

    resposta = _post_medicao(client, parcela, documento, '1.500,00')

    assert resposta.status_code == 200
    assert 'Valor maior que o disponível' in resposta.content.decode()
    assert Medicao.objects.filter(parcela=parcela).count() == 0


@pytest.mark.django_db
def test_medicao_dentro_do_saldo_do_empenho_e_gravada_com_o_empenho(client: Client, fiscal: Fiscal) -> None:
    documento = _empenho_do_contrato(fiscal, saldo=Decimal('1000.00'))
    parcela = ParcelaFactory(cronograma__contrato=fiscal.contrato)
    client.force_login(fiscal.servidor.get_user())

    resposta = _post_medicao(client, parcela, documento, '800,00')

    assert resposta.status_code == 302
    medicao = Medicao.objects.get(parcela=parcela)
    assert medicao.valor_executado == Decimal('800.00')
    assert DocumentoEmpenhoContratoMedicao.objects.filter(medicao=medicao, documento_empenho_contrato=documento, valor=Decimal('800.00')).count() == 1
