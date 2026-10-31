"""Criação e edição de documentos em "Minhas Ações" (#17452).

A tela agrupa por dia para não listar cada salvamento do mesmo documento, mas o agrupamento era
só por dia: aparecia uma criação e uma edição por dia, qualquer que fosse o número de documentos.
Agora é uma linha por (dia, documento) em cada ação.
"""

from __future__ import annotations

from datetime import datetime

import pytest
from django.test import Client

from documento_eletronico.models import DocumentoTexto, RegistroAcaoDocumento
from documento_eletronico.tests.factories import DocumentoTextoFactory, RegistroAcaoDocumentoTextoFactory
from rh.tests.factories import ServidorFactory

pytestmark = pytest.mark.django_db

CRIACAO = RegistroAcaoDocumento.TIPO_CRIACAO
EDICAO = RegistroAcaoDocumento.TIPO_EDICAO


def _documentos_listados(client: Client, vinculo_id: int, categoria: str) -> list[DocumentoTexto]:
    resposta = client.get(
        '/comum/minhas_acoes_suap/',
        {'usuario': vinculo_id, 'datahora_inicio': '2026-09-22T00:00', 'datahora_fim': '2026-09-23T23:59:59'},
    )
    assert resposta.status_code == 200
    acoes = resposta.context['areas']['Documentos Eletrônicos'][categoria]
    return [documento for documento, _descricao, _url in acoes]


def test_lista_todos_os_documentos_criados_e_editados_uma_vez_por_dia(client: Client, sync_permissions) -> None:
    servidor = ServidorFactory()
    user = servidor.get_user()
    a, b, c, d, e, f = (DocumentoTextoFactory(usuario_criacao=user) for _ in range(6))
    historico = [
        # 22/09: F criado às 23h30 (fica no dia 22) e salvo de novo no mesmo dia.
        (f, CRIACAO, datetime(2026, 9, 22, 23, 30)),
        (f, EDICAO, datetime(2026, 9, 22, 23, 45)),
        # 23/09: A, B e C criados; A ainda editado duas vezes no mesmo dia.
        (a, CRIACAO, datetime(2026, 9, 23, 9, 0)),
        (a, EDICAO, datetime(2026, 9, 23, 9, 30)),
        (a, EDICAO, datetime(2026, 9, 23, 14, 0)),
        (b, CRIACAO, datetime(2026, 9, 23, 10, 0)),
        (c, CRIACAO, datetime(2026, 9, 23, 11, 0)),
        # 23/09: D e E (criados antes do período) editados várias vezes; F editado no dia seguinte ao da criação.
        (d, EDICAO, datetime(2026, 9, 23, 8, 0)),
        (d, EDICAO, datetime(2026, 9, 23, 12, 0)),
        (d, EDICAO, datetime(2026, 9, 23, 16, 0)),
        (f, EDICAO, datetime(2026, 9, 23, 8, 30)),
        (e, EDICAO, datetime(2026, 9, 23, 13, 0)),
        (e, EDICAO, datetime(2026, 9, 23, 15, 0)),
    ]
    for documento, tipo, data in historico:
        RegistroAcaoDocumentoTextoFactory(documento=documento, user=user, tipo=tipo, data=data)
    client.force_login(user)
    vinculo_id = servidor.get_vinculo().pk

    criados = _documentos_listados(client, vinculo_id, 'Criação de Documentos')
    editados = _documentos_listados(client, vinculo_id, 'Edição de Documentos')

    # Dia mais recente primeiro; dentro do dia, pelo horário do primeiro registro.
    assert criados == [a, b, c, f]
    # A (criado e editado no dia 23) e F no dia 22 aparecem só como criação; F editado no dia 23 aparece.
    assert editados == [d, f, e]
