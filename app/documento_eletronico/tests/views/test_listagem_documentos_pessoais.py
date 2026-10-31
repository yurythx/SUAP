"""Listagem de documentos pessoais no admin (``DocumentoTextoPessoalAdmin``) sem consultas linha a linha (#17709).

Datas da primeira assinatura e da finalização, e o dono, são carregados por página.
"""

from __future__ import annotations

import re

import pytest
from django.db import connection
from django.http import HttpResponse
from django.test import Client
from django.test.utils import CaptureQueriesContext
from django.utils import formats, timezone

from comum.models import User
from documento_eletronico.models import Assinatura, AssinaturaDocumentoTexto, DocumentoTexto, RegistroAcaoDocumentoTexto
from documento_eletronico.status import DocumentoStatus
from documento_eletronico.tests.factories import DocumentoTextoFactory, RegistroAcaoDocumentoTextoFactory
from rh.models import Papel, Servidor
from rh.tests.factories import PapelFactory, ServidorFactory

pytestmark = pytest.mark.django_db

URL = '/admin/documento_eletronico/documentotextopessoal/'
# A permissão de leitura/edição por linha (``tem_permissao_editar``) consulta os compartilhamentos do documento: regra
# de permissão, fora do escopo do #17709. Descontada da conta, e só ela.
SQL_PERMISSAO = '"documento_eletronico_compartilhamentodocumentopessoa"'


def _documentos_assinados(servidor: Servidor, papel: Papel, quantidade: int) -> list[DocumentoTexto]:
    """Documentos do ``servidor``, assinados por ele e finalizados."""
    user = servidor.get_user()
    documentos = []
    for _ in range(quantidade):
        documento = DocumentoTextoFactory(usuario_criacao=user, status=DocumentoStatus.STATUS_FINALIZADO)
        assinatura = Assinatura.objects.create(
            vinculo=user.get_vinculo(), cpf=servidor.pessoa_fisica.cpf, nome_papel=papel.detalhamento, papel=papel, hmac=f'hmac-{documento.pk}'
        )
        documento.assinatura_balizadora = AssinaturaDocumentoTexto.objects.create(documento=documento, assinatura=assinatura)
        documento.save()
        RegistroAcaoDocumentoTextoFactory(documento=documento, user=user, tipo=RegistroAcaoDocumentoTexto.TIPO_FINALIZACAO)
        documentos.append(documento)
    return documentos


def _listar(client: Client) -> tuple[HttpResponse, int]:
    """GET na listagem; devolve a resposta e o nº de consultas, sem as da regra de permissão."""
    # Sem os caches por processo do perfil, que mascarariam a carga do dono linha a linha.
    User.VINCULOS.clear()
    User.PESSOAS_FISICAS.clear()
    with CaptureQueriesContext(connection) as consultas:
        resposta = client.get(URL, {'q': ''})
    assert resposta.status_code == 200
    return resposta, len([q for q in consultas.captured_queries if SQL_PERMISSAO not in q['sql']])


def _linha(resposta: HttpResponse, documento: DocumentoTexto) -> str:
    html = resposta.content.decode()
    return re.search(rf'<tr[^>]*>(?:(?!</tr>).)*/visualizar_documento/{documento.pk}/(?:(?!</tr>).)*</tr>', html, re.DOTALL).group(0)


def test_listagem_pessoal_nao_consulta_o_banco_linha_a_linha(client: Client, sync_permissions: None) -> None:
    servidor = ServidorFactory(pessoa_fisica__nome='Dona Documental')
    papel = PapelFactory(servidor=servidor)
    client.force_login(servidor.get_user())
    # A 1ª requisição paga custos únicos da sessão (grupos, preferências, notificações): fica fora da comparação.
    _listar(client)

    documentos = _documentos_assinados(servidor, papel, 2)
    resposta, com_dois = _listar(client)
    assert len(resposta.context['cl'].result_list) == 2

    documentos += _documentos_assinados(servidor, papel, 4)
    resposta, com_seis = _listar(client)
    assert len(resposta.context['cl'].result_list) == 6

    assert com_seis - com_dois <= 2, f'{com_dois} consultas com 2 documentos, {com_seis} com 6'

    # O conteúdo das colunas segue o mesmo.
    documento = documentos[-1]
    linha = _linha(resposta, documento)
    primeira = formats.localize(timezone.template_localtime(documento.assinatura_balizadora.assinatura.data_assinatura))
    finalizacao = RegistroAcaoDocumentoTexto.objects.get(documento=documento, tipo=RegistroAcaoDocumentoTexto.TIPO_FINALIZACAO).data
    assert 'Dona Documental' in linha
    assert f'<td class="field-get_data_primeira_assinatura nowrap">{primeira}</td>' in linha
    assert f'<td class="field-get_data_finalizacao nowrap">{formats.localize(timezone.template_localtime(finalizacao))}</td>' in linha


def test_listagem_pessoal_sem_assinatura_nem_finalizacao_mostra_traco(client: Client, sync_permissions: None) -> None:
    servidor = ServidorFactory()
    documento = DocumentoTextoFactory(usuario_criacao=servidor.get_user())
    client.force_login(servidor.get_user())

    resposta, _ = _listar(client)

    assert '<td class="field-get_data_primeira_assinatura">-</td><td class="field-get_data_finalizacao">-</td>' in _linha(resposta, documento)
