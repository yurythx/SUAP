"""Testes de regressão da issue #17137: processo eletrônico criado a partir de chamado da
Central de Serviços não saía com anexos e encaminhamentos.

Duas causas raiz distintas, ambas corrigidas em `processo_eletronico/tasks.py`:

1. O primeiro anexo (o extrato do chamado, gerado localmente e marcado como `temporario=True`)
   sempre derrubava a task inteira em storage local: `cache_file()` era chamado com o caminho
   absoluto retornado por `upload_temporary_file()` como se fosse uma chave relativa de
   storage, e o Django rejeita isso com `SuspiciousFileOperation`.
2. Mesmo sem esse crash, um único anexo com formato não suportado impedia a criação do primeiro
   trâmite (o "encaminhamento" do processo) para o processo inteiro, mesmo com outros anexos
   válidos já salvos.

Os testes exercitam as funções reais (não cópias da lógica), isolando apenas as bordas de DB
pesadas (persistência do documento, trâmite) via monkeypatch.
"""

import os
import tempfile
from unittest import mock

import pytest
from django.core.exceptions import ValidationError

from processo_eletronico import tasks as tasks_module


@pytest.mark.django_db
def test_um_anexo_invalido_nao_impede_primeiro_tramite_nem_anexacao_do_anexo_valido(monkeypatch):
    # Um anexo válido (será "convertido" com sucesso) e um anexo com formato não suportado
    # (simula, por exemplo, um .msg ou .rar anexado a um chamado da Central de Serviços).
    pdf_valido = tempfile.NamedTemporaryFile(suffix='.pdf', delete=False)
    pdf_valido.write(b'%PDF-1.4 conteudo fake')
    pdf_valido.close()

    anexo_invalido = tempfile.NamedTemporaryFile(suffix='.rar', delete=False)
    anexo_invalido.write(b'conteudo binario qualquer')
    anexo_invalido.close()

    # cache_file normalmente baixa do storage remoto; aqui os anexos já são caminhos locais reais.
    monkeypatch.setattr(tasks_module, 'cache_file', lambda caminho, remote_storage=None: caminho)

    # magic.Magic(...).from_file(...) é chamado uma vez por anexo, na ordem em que aparecem em `anexos`.
    fake_magic = mock.MagicMock()
    fake_magic.Magic.return_value.from_file.side_effect = ['application/pdf', 'application/x-rar-compressed']
    monkeypatch.setattr(tasks_module, 'magic', fake_magic)

    fake_doc = mock.MagicMock(name='DocumentoDigitalizado_instance')
    fake_doc.arquivo.name = pdf_valido.name
    monkeypatch.setattr(tasks_module.DocumentoDigitalizado, 'criar', mock.MagicMock(return_value=fake_doc))

    # A verificação de integridade do PDF já convertido não é o alvo deste teste.
    monkeypatch.setattr(tasks_module, 'full_check_file', mock.MagicMock(return_value=True))

    tramite_mock = mock.MagicMock()
    monkeypatch.setattr(tasks_module, 'Tramite', tramite_mock)

    processo = mock.MagicMock(name='Processo_instance')
    processo.numero_protocolo = '23000.000001/2026-00'

    anexos = [
        {
            'path': pdf_valido.name,
            'name': 'extrato_chamado_1.pdf',
            'descricao': 'Extrato do Chamado 1',
            'tipo_documento': mock.MagicMock(),
            'nivel_acesso': 1,
            'temporario': True,
            'url_publica': 'http://example.test/chamado/1/',
        },
        {
            'path': anexo_invalido.name,
            'name': 'anexo_usuario.rar',
            'descricao': 'Anexo enviado pelo usuário',
            'tipo_documento': mock.MagicMock(),
            'nivel_acesso': 1,
            'temporario': False,
            'url_publica': 'http://example.test/anexo/1/',
        },
    ]

    try:
        tasks_module.criar_arquivos_e_primeiro_tramite_de_processo(
            processo=processo,
            anexos=anexos,
            usuario=mock.MagicMock(),
            papel=mock.MagicMock(),
            setor_criacao=mock.MagicMock(),
            corpo_despacho='',
            setor_destino=mock.MagicMock(),
            url_redirecionamento=None,
            notify=False,
            on_finish=None,
            on_finish_extra_params=None,
        )
    finally:
        os.unlink(pdf_valido.name)
        os.unlink(anexo_invalido.name)

    # O anexo válido é anexado ao processo...
    assert processo.adicionar_documento_digitalizado.call_count == 1

    # ...e o primeiro trâmite (o "encaminhamento" do processo) é sempre criado, mesmo havendo um
    # anexo com formato não suportado — o erro deve apenas ser reportado (via on_finish), nunca
    # impedir o encaminhamento do processo nem a anexação dos demais arquivos válidos.
    assert tramite_mock.return_value.tramitar_processo.call_count == 1


def test_anexo_temporario_gerado_localmente_nao_causa_suspicious_file_operation(monkeypatch):
    """Regressão: em storage local (dev/homologação sem S3), o extrato do chamado é sempre o
    primeiro anexo e é `temporario=True`. `upload_temporary_file()` retorna o caminho absoluto
    do arquivo quando o storage não é remoto — antes do fix esse caminho absoluto era passado
    para `cache_file()` como se fosse uma chave relativa de storage, e o `Storage.save()` do
    Django rejeita nomes absolutos com `SuspiciousFileOperation`. Isso derrubava a task inteira
    antes de processar qualquer anexo, deixando o processo sem nenhum documento e sem trâmite.
    """
    from djtools.storages import upload_temporary_file

    pdf_extrato = tempfile.NamedTemporaryFile(suffix='.pdf', delete=False)
    pdf_extrato.write(b'%PDF-1.4 conteudo fake do extrato')
    pdf_extrato.close()
    caminho_extrato = upload_temporary_file(pdf_extrato.name)  # é o que centralservicos/views.py faz

    fake_doc = mock.MagicMock(name='DocumentoDigitalizado_instance')
    fake_doc.arquivo.name = pdf_extrato.name
    monkeypatch.setattr(tasks_module.DocumentoDigitalizado, 'criar', mock.MagicMock(return_value=fake_doc))
    monkeypatch.setattr(tasks_module, 'full_check_file', mock.MagicMock(return_value=True))

    # Não depender do libmagic real reconhecer o conteúdo fake como PDF (varia por ambiente) —
    # o que este teste cobre é a resolução do caminho de storage, não a detecção de mimetype.
    fake_magic = mock.MagicMock()
    fake_magic.Magic.return_value.from_file.return_value = 'application/pdf'
    monkeypatch.setattr(tasks_module, 'magic', fake_magic)

    try:
        doc = tasks_module._copiar_anexo_como_documento_digitalizado(
            caminho_arquivo=caminho_extrato,
            nome_arquivo='extrato_chamado_1.pdf',
            descricao='Extrato do Chamado 1',
            tipo_documento=mock.MagicMock(),
            nivel_acesso=1,
            temporario=True,
            url_publica='http://example.test/chamado/1/',
            usuario=mock.MagicMock(),
            papel=mock.MagicMock(),
        )
    finally:
        os.unlink(pdf_extrato.name)

    assert doc is fake_doc


def test_verificar_integridade_pdf_com_erro_de_validacao_retorna_mensagem_amigavel(monkeypatch):
    pdf = tempfile.NamedTemporaryFile(suffix='.pdf', delete=False)
    pdf.write(b'%PDF-1.4 conteudo fake')
    pdf.close()

    # doc.arquivo.name normalmente é uma chave relativa no storage padrão; aqui já é um caminho
    # local real, então cache_file (que baixaria do storage remoto) não entra no caminho do teste.
    monkeypatch.setattr(tasks_module, 'cache_file', lambda caminho, remote_storage=None: caminho)
    monkeypatch.setattr(
        tasks_module,
        'full_check_file',
        mock.MagicMock(side_effect=ValidationError('Arquivo protegido com senha, encriptado, corrompido ou mal formado.')),
    )

    try:
        erro = tasks_module._verificar_integridade_pdf_gerado(mock.MagicMock(), pdf.name)
    finally:
        os.unlink(pdf.name)

    assert erro == 'Arquivo protegido com senha, encriptado, corrompido ou mal formado.'


def test_verificar_integridade_pdf_com_erro_inesperado_nao_expoe_detalhe_tecnico(monkeypatch):
    """Regressão: uma dependência de sistema ausente (ex.: o binário `qpdf`) não pode aparecer,
    com caminho de arquivo e código de erro, na mensagem de fechamento do chamado que o usuário
    final da Central de Serviços vê. O erro real deve ir só para o Sentry."""
    pdf = tempfile.NamedTemporaryFile(suffix='.pdf', delete=False)
    pdf.write(b'%PDF-1.4 conteudo fake')
    pdf.close()

    monkeypatch.setattr(tasks_module, 'cache_file', lambda caminho, remote_storage=None: caminho)
    monkeypatch.setattr(
        tasks_module,
        'full_check_file',
        mock.MagicMock(side_effect=FileNotFoundError(2, 'No such file or directory', '/usr/bin/qpdf')),
    )
    capture_exception_mock = mock.MagicMock()
    monkeypatch.setattr(tasks_module.sentry_sdk, 'capture_exception', capture_exception_mock)

    try:
        erro = tasks_module._verificar_integridade_pdf_gerado(mock.MagicMock(), pdf.name)
    finally:
        os.unlink(pdf.name)

    assert 'qpdf' not in erro
    assert 'Errno' not in erro
    assert capture_exception_mock.call_count == 1
