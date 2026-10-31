"""Regressão do preview quebrado de documento pessoal em Requerimento.

``visualizar_documento_requerimento_pdf`` expunha a URL crua de storage
(``arquivo.url``) para documentos pessoais reaproveitados via
``DocumentoDigitalizadoRequerimentoOutros``, em vez de rotear pelo endpoint
com ACL (``visualizar_documento_digitalizado``, que checa ``pode_ler``). Em
produção (storage S3/MinIO), essa URL é uma presigned URL sem checagem de
ACL alguma.
"""

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from documento_eletronico.tests.factories import PDF_MINIMO, DocumentoDigitalizadoFactory
from processo_eletronico.models import DocumentoDigitalizadoRequerimentoOutros, Requerimento, RequerimentoDigitalizado
from processo_eletronico.tests.factories import TipoProcessoFactory


@pytest.fixture
def requerimento(dois_servidores):
    """Requerimento do servidor ``a`` com um documento pessoal dele reaproveitado."""
    interessado = dois_servidores.a.get_user()
    requerimento = Requerimento(tipo_processo=TipoProcessoFactory(), assunto='Requerimento de teste')
    requerimento.save(request_user=interessado)
    documento_pessoal = DocumentoDigitalizadoFactory(usuario_criacao=interessado)
    vinculo = DocumentoDigitalizadoRequerimentoOutros.objects.create(documento=documento_pessoal, requerimento=requerimento)
    return requerimento, vinculo


def url_preview(requerimento, documento_digitalizado_requerimento_id):
    return f'/processo_eletronico/visualizar_documento_requerimento_pdf/{requerimento.pk}/{documento_digitalizado_requerimento_id}/'


def test_preview_documento_pessoal_usa_endpoint_com_acl(client, dois_servidores, requerimento):
    requerimento, vinculo = requerimento
    client.force_login(dois_servidores.a.get_user())

    response = client.get(url_preview(requerimento, vinculo.pk))

    assert response.status_code == 200
    conteudo = response.content.decode('utf-8')
    assert f'/documento_eletronico/visualizar_documento_digitalizado/{vinculo.documento.pk}/' in conteudo
    assert vinculo.documento.arquivo.name not in conteudo


def test_preview_documento_pessoal_nega_acesso_a_outro_usuario(client, dois_servidores, requerimento):
    # Para quem não é o interessado, Requerimento.get_requerimento_by_user já retorna None antes
    # da busca do documento, então a view devolve 404 (não revela se o documento existe) em vez de 403.
    requerimento, vinculo = requerimento
    client.force_login(dois_servidores.b.get_user())

    response = client.get(url_preview(requerimento, vinculo.pk))

    assert response.status_code == 404


def test_preview_requerimento_digitalizado_bruto_nao_regride(client, dois_servidores, requerimento):
    requerimento, vinculo = requerimento
    requerimento_digitalizado = RequerimentoDigitalizado.objects.create(
        requerimento=requerimento,
        arquivo=SimpleUploadedFile('bruto.pdf', PDF_MINIMO, content_type='application/pdf'),
        tipo=vinculo.documento.tipo,
        assunto='Upload bruto de teste',
        tipo_conferencia=vinculo.documento.tipo_conferencia,
    )
    client.force_login(dois_servidores.a.get_user())

    response = client.get(url_preview(requerimento, requerimento_digitalizado.pk))

    assert response.status_code == 200
    assert requerimento_digitalizado.arquivo.name in response.content.decode('utf-8')


def test_endpoint_com_acl_aceita_interessado_do_requerimento(client, dois_servidores, requerimento):
    _, vinculo = requerimento
    client.force_login(dois_servidores.a.get_user())

    response = client.get(f'/documento_eletronico/visualizar_documento_digitalizado/{vinculo.documento.pk}/?original=sim')

    assert response.status_code == 200
    assert response['Content-Type'] == 'application/pdf'
