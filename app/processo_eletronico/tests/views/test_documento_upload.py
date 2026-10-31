"""Anexar documento externo ao processo: assinatura por senha ou, para usuário externo, Gov.BR.

A assinatura por token (certificado A3 via navegador) nunca foi usada e não verificava a cadeia
de confiança ICP-Brasil. Escolher "token" no passo 1 do ``DocumentoUploadWizard`` anexava o
documento ao processo **sem assinatura nenhuma** (a chamada ao ``sign()`` do ``hwsign.js`` estava
comentada no template e a validação voltava cedo sem certificado). A opção foi removida; a anexação por senha segue igual.

O usuário externo assina com Gov.BR: o passo 2 autentica pelo Gov.BR, e o documento é assinado
como na senha. Até a #17477 ele era anexado sem assinatura.

Não há escolha de tipo de assinatura na tela (#17483): o radio tinha uma opção só, e o tipo sai do usuário.
"""

from __future__ import annotations

import re
from io import BytesIO
from types import SimpleNamespace
from unittest import mock

import pytest
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from pypdf import PdfWriter

from documento_eletronico.models import AssinaturaDocumentoDigitalizado, Documento
from documento_eletronico.tests.factories import TipoConferenciaFactory, TipoDocumentoFactory
from comum.tests.factories import PrestadorServicoFactory
from processo_eletronico.models import DocumentoDigitalizadoProcesso
from processo_eletronico.tests.factories import ProcessoFactory
from rh.models import Setor
from rh.tests.factories import PapelFactory, ServidorFactory

pytestmark = pytest.mark.django_db

SENHA = '123'
CODIGO_GOVBR = '54321'


def _pdf() -> SimpleUploadedFile:
    escritor = PdfWriter()
    escritor.add_blank_page(width=100, height=100)
    conteudo = BytesIO()
    escritor.write(conteudo)
    return SimpleUploadedFile('documento.pdf', conteudo.getvalue(), content_type='application/pdf')


@pytest.fixture
def cenario(client: Client, sync_permissions: None, setor_com_siorg: Setor) -> SimpleNamespace:
    """Servidor com papel ativo e senha, logado, num processo do próprio setor."""
    servidor = ServidorFactory(setor=setor_com_siorg)
    papel = PapelFactory(servidor=servidor)
    user = servidor.get_user()
    user.set_password(SENHA)
    user.save()
    client.force_login(user)
    processo = ProcessoFactory(setor_criacao=setor_com_siorg, usuario_gerador=user)
    url = f'/processo_eletronico/documento_upload/{processo.pk}/'
    passo = re.search(r'name="([\w-]+-current_step)"', client.get(url).content.decode()).group(1)
    return SimpleNamespace(client=client, url=url, passo=passo, processo=processo, papel=papel, user=user, setor=setor_com_siorg)


@pytest.fixture
def cenario_externo(client: Client, sync_permissions: None, setor_com_siorg: Setor) -> SimpleNamespace:
    """Usuário externo (prestador sem ocupação) com o papel de usuário externo, logado via Gov.BR,
    no processo que ele mesmo criou (sem trâmites, então pode editá-lo)."""
    prestador = PrestadorServicoFactory()
    prestador.criar_papel_usuario_externo()
    user = prestador.get_user()
    client.force_login(user)
    sessao = client.session
    sessao['autenticou_com_govbr'] = True
    sessao['token_govbr'] = {'access_token': 'token-de-teste'}
    sessao.save()
    cache.set(f'govbr_check_{user.get_vinculo().id}', CODIGO_GOVBR, 300)
    processo = ProcessoFactory(setor_criacao=setor_com_siorg, usuario_gerador=user)
    url = f'/processo_eletronico/documento_upload/{processo.pk}/'
    passo = re.search(r'name="([\w-]+-current_step)"', client.get(url).content.decode()).group(1)
    papel = user.get_relacionamento().papeis_ativos.get()
    return SimpleNamespace(client=client, url=url, passo=passo, processo=processo, papel=papel, user=user, setor=setor_com_siorg)


def _enviar_passo_1(cenario: SimpleNamespace, assunto: str) -> None:
    cenario.client.post(
        cenario.url,
        {
            cenario.passo: '0',
            'arquivo': _pdf(),
            'tipo_conferencia': TipoConferenciaFactory().pk,
            'tipo': TipoDocumentoFactory().pk,
            'assunto': assunto,
            'setor_dono': cenario.setor.pk,
            'dono_documento': cenario.user.get_vinculo().pk,
            'nivel_acesso': Documento.NIVEL_ACESSO_PUBLICO,
        },
    )


def test_formulario_nao_exibe_tipo_de_assinatura(cenario: SimpleNamespace) -> None:
    html = cenario.client.get(cenario.url).content.decode()

    assert 'name="tipo_assinatura"' not in html


def test_passo_de_assinatura_sem_senha_nao_anexa_documento(cenario: SimpleNamespace) -> None:
    """Antes, "token" + perfil anexava o documento ao processo sem assinatura; sem senha, nada é anexado."""
    _enviar_passo_1(cenario, 'Documento sem senha')
    cenario.client.post(cenario.url, {cenario.passo: '1', 'papel': cenario.papel.pk})

    assert not DocumentoDigitalizadoProcesso.objects.filter(processo=cenario.processo).exists()


def test_anexacao_por_senha_assina_e_anexa(cenario: SimpleNamespace) -> None:
    _enviar_passo_1(cenario, 'Documento via senha')
    cenario.client.post(cenario.url, {cenario.passo: '1', 'papel': cenario.papel.pk, 'senha': SENHA})

    vinculo = DocumentoDigitalizadoProcesso.objects.get(processo=cenario.processo)
    assert vinculo.documento.assunto == 'Documento via senha'
    assert AssinaturaDocumentoDigitalizado.objects.filter(documento=vinculo.documento, assinatura__vinculo=cenario.user.get_vinculo()).exists()


def test_usuario_externo_via_govbr_assina_e_anexa(cenario_externo: SimpleNamespace) -> None:
    """Antes da #17477, "Assinar com Gov.BR" anexava o documento sem assinatura."""
    assert 'name="tipo_assinatura"' not in cenario_externo.client.get(cenario_externo.url).content.decode()

    _enviar_passo_1(cenario_externo, 'Documento via Gov.BR')
    # Nível de confiabilidade da conta Gov.BR: consulta à API do Gov.BR (fronteira de rede), prata = '2'.
    with mock.patch('djtools.middleware.govbr.user_confiability_level', return_value='2'):
        cenario_externo.client.post(
            cenario_externo.url, {cenario_externo.passo: '1', 'papel': cenario_externo.papel.pk, 'codigo_verificacao': CODIGO_GOVBR}
        )

    vinculo = DocumentoDigitalizadoProcesso.objects.get(processo=cenario_externo.processo)
    assert vinculo.documento.assunto == 'Documento via Gov.BR'
    assert AssinaturaDocumentoDigitalizado.objects.filter(
        documento=vinculo.documento, assinatura__vinculo=cenario_externo.user.get_vinculo()
    ).exists()
