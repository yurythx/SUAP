"""Cobertura de renderização da tela de conteúdo do documento (issue #17161).

Antes da correção, ``conteudo_documento_com_anexos.html`` incluía o wrapper
completo (``<!DOCTYPE>``/``<html>``/``<body>`` + widget do VLibras) uma vez
para o documento principal e mais uma vez por anexo de texto, instanciando
vários widgets do VLibras na mesma página e quebrando o botão de acessibilidade.

Estes testes chamam a view ``conteudo_documento`` diretamente (via
``RequestFactory``), mockando as dependências de banco/permissão (mesmo estilo
de ``test_assinatura_documento_pessoal.py``), e checam no HTML renderizado que,
para as combinações autenticado/anônimo x com/sem anexos x minuta, a página
sempre resulta em uma única tag ``<html``, um único widget do VLibras e nenhum
``id="watermark"`` duplicado (inválido em HTML).

Usamos ``SimpleNamespace`` (não ``Mock``/``MagicMock``) para o documento: o
resolvedor de variável do Django invoca automaticamente qualquer valor
*callable* durante a travessia de atributos (``documento.x.y`` chama
``documento()`` primeiro se ``documento`` for callable) e tenta ``dict[key]``
antes de ``getattr`` (o que um ``MagicMock`` sempre "acerta" via
``__getitem__``, retornando um mock filho truthy). Ambos os comportamentos
mascaram os valores booleanos que configuramos; ``SimpleNamespace`` não é
callable nem suporta ``__getitem__``, então o Django cai corretamente em
``getattr``.

Os testes do fim do arquivo (issue #17854) passam pelo ``Client`` com documento e usuário reais:
identificador numérico inexistente ou que não é UUID responde 404, não 500.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock
import uuid

import pytest
from django.test import Client

from documento_eletronico import views
from documento_eletronico.models import Documento, DocumentoTexto
from documento_eletronico.status import DocumentoStatus
from documento_eletronico.tests.factories import DocumentoTextoFactory
from rh.tests.factories import ServidorFactory

UUID_DOCUMENTO_ANONIMO = '11111111-1111-1111-1111-111111111111'


def _documento_mock(*, eh_minuta=False, possui_anexos=False, eh_documento_texto=True, tags_anonimizacao=None):
    return SimpleNamespace(
        eh_minuta=eh_minuta,
        eh_documento_texto=eh_documento_texto,
        tags_anonimizacao=tags_anonimizacao,
        boletimperiodo_set=SimpleNamespace(all=list),
        boletimdiario_set=SimpleNamespace(all=list),
        possui_anexos=lambda: possui_anexos,
        possui_assinatura=False,
        assinaturas=[],
        qrcode=None,
        corpo_para_visualizacao='<p>Corpo do documento</p>',
        corpo_para_visualizacao_anonima='<p>Corpo do documento (anônimo)</p>',
        pode_ler=lambda **kwargs: True,
    )


@pytest.fixture(autouse=True)
def _dependencias_sem_banco(monkeypatch):
    monkeypatch.setattr(views, 'app_processo_eletronico_estah_instalada', lambda: False)
    monkeypatch.setattr(views, 'gerar_codigo_verificador_documento', lambda documento: 'codigo-teste')


def _renderizar(rf, monkeypatch, documento, *, autenticado, mostrar_anexos, anexos=None, documento_id: int | str = 1):
    monkeypatch.setattr(views, 'get_documento_texto', lambda _id_uuid: documento)
    if anexos is not None:
        monkeypatch.setattr(views, 'get_anexos_do_documento_visiveis', lambda *_args, **_kwargs: anexos)

    url = f'/documento_eletronico/conteudo_documento/{documento_id}/'
    params = []
    if mostrar_anexos:
        params.append('mostrar_anexos=True')
    if not autenticado:
        params.append('forcar_anonimo=1')
    if params:
        url += '?' + '&'.join(params)

    request = rf.get(url)
    request.session = {}
    request.user = MagicMock(is_anonymous=not autenticado, is_authenticated=autenticado)
    request.user.has_perm.return_value = True

    response = views.conteudo_documento(request, documento_id)
    assert response.status_code == 200
    return response.content.decode()


@pytest.mark.django_db
def test_autenticado_sem_anexos(rf, monkeypatch):
    html = _renderizar(rf, monkeypatch, _documento_mock(), autenticado=True, mostrar_anexos=False)

    assert html.lower().count('<html') == 1
    assert html.count('new window.VLibras.Widget(') == 1
    assert 'id="watermark"' not in html
    assert 'class="watermark"' not in html


@pytest.mark.django_db
def test_autenticado_com_anexo_texto_minuta(rf, monkeypatch):
    anexo = _documento_mock(eh_minuta=True, eh_documento_texto=True)
    html = _renderizar(rf, monkeypatch, _documento_mock(possui_anexos=True), autenticado=True, mostrar_anexos=True, anexos=[anexo])

    assert html.lower().count('<html') == 1
    assert html.count('new window.VLibras.Widget(') == 1
    assert 'id="watermark"' not in html
    assert html.count('class="watermark"') == 1


@pytest.mark.django_db
def test_anonimo_sem_anexos_minuta(rf, monkeypatch):
    html = _renderizar(
        rf,
        monkeypatch,
        _documento_mock(eh_minuta=True),
        autenticado=False,
        mostrar_anexos=False,
        documento_id=UUID_DOCUMENTO_ANONIMO,
    )

    assert html.lower().count('<html') == 1
    assert html.count('new window.VLibras.Widget(') == 1
    assert 'id="watermark"' not in html
    assert html.count('class="watermark"') == 1


@pytest.mark.django_db
def test_multiplos_anexos_minuta_cada_watermark_escopado_ao_proprio_bloco(rf, monkeypatch):
    anexo_1 = _documento_mock(eh_minuta=True, eh_documento_texto=True)
    anexo_2 = _documento_mock(eh_minuta=True, eh_documento_texto=True)
    html = _renderizar(
        rf,
        monkeypatch,
        _documento_mock(eh_minuta=True, possui_anexos=True),
        autenticado=True,
        mostrar_anexos=True,
        anexos=[anexo_1, anexo_2],
    )

    assert html.lower().count('<html') == 1
    assert html.count('new window.VLibras.Widget(') == 1
    assert html.count('class="watermark"') == 3
    assert html.count('class="documento-bloco"') == 3


@pytest.mark.django_db
def test_anonimo_com_anexo_digitalizado(rf, monkeypatch):
    anexo = _documento_mock(eh_documento_texto=False)
    anexo.uuid = uuid.uuid4()
    html = _renderizar(
        rf,
        monkeypatch,
        _documento_mock(possui_anexos=True),
        autenticado=False,
        mostrar_anexos=True,
        anexos=[anexo],
        documento_id=UUID_DOCUMENTO_ANONIMO,
    )

    assert html.lower().count('<html') == 1
    assert html.count('new window.VLibras.Widget(') == 1
    assert 'id="watermark"' not in html
    assert f'visualizar_documento_digitalizado/{anexo.uuid}/' in html


@pytest.mark.django_db
def test_anonimo_com_tags_anonimizacao_exibe_aviso(rf, monkeypatch):
    html = _renderizar(
        rf,
        monkeypatch,
        _documento_mock(tags_anonimizacao=['dados_pessoais']),
        autenticado=False,
        mostrar_anexos=False,
        documento_id=UUID_DOCUMENTO_ANONIMO,
    )

    assert 'Este documento foi anonimizado para preservar a privacidade' in html


@pytest.mark.django_db
def test_autenticado_com_tags_anonimizacao_nao_exibe_aviso(rf, monkeypatch):
    """O aviso de anonimização só aparece na consulta pública (``eh_anonimo``), não para quem está autenticado."""
    html = _renderizar(
        rf,
        monkeypatch,
        _documento_mock(tags_anonimizacao=['dados_pessoais']),
        autenticado=True,
        mostrar_anexos=False,
    )

    assert 'Este documento foi anonimizado para preservar a privacidade' not in html


def _documento_do_servidor(client: Client) -> DocumentoTexto:
    servidor = ServidorFactory()
    user = servidor.get_user()
    client.force_login(user)
    return DocumentoTextoFactory(
        usuario_criacao=user,
        setor_dono=servidor.setor,
        nivel_acesso=Documento.NIVEL_ACESSO_PUBLICO,
        status=DocumentoStatus.STATUS_FINALIZADO,
    )


@pytest.mark.django_db
@pytest.mark.parametrize('identificador', [str(2**128), '9' * 40, '999999999', 'nao-eh-uuid'])
def test_identificador_inexistente_ou_invalido_responde_404(client: Client, sync_permissions: None, identificador: str) -> None:
    _documento_do_servidor(client)

    response = client.get(f'/documento_eletronico/conteudo_documento/{identificador}/')

    assert response.status_code == 404


@pytest.mark.django_db
@pytest.mark.parametrize('campo', ['id', 'uuid'])
def test_documento_existente_por_id_ou_uuid_responde_200(client: Client, sync_permissions: None, campo: str) -> None:
    documento = _documento_do_servidor(client)

    response = client.get(f'/documento_eletronico/conteudo_documento/{getattr(documento, campo)}/')

    assert response.status_code == 200
    assert 'Você não tem permissão' not in response.content.decode()
