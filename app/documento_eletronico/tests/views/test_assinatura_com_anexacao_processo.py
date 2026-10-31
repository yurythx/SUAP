"""Assinatura de documento com solicitação de anexação a processo e trâmite com despacho (#17817).

A solicitação podia ser gravada com despacho e sem o perfil do solicitante; ao assinar, o trâmite
automático exige esse perfil: o gov.br mostrava um erro genérico e a assinatura em lote dava 500.
Agora a assinatura do documento é desfeita por inteiro e o assinante vê o motivo. Só o gov.br
(confiabilidade da conta) é mockado.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.contrib.messages import get_messages
from django.core.cache import cache
from django.http import HttpResponse
from django.test import Client

from catalogo_provedor_servico.models import TemplateNotificaGovBR
from comum.utils import get_sigla_reitoria
from documento_eletronico.models import (
    Assinatura,
    AssinaturaDocumentoTexto,
    CompartilhamentoDocumentoPessoa,
    DocumentoTexto,
    NivelPermissao,
    SolicitacaoAssinatura,
)
from documento_eletronico.status import DocumentoStatus, SolicitacaoStatus
from documento_eletronico.tests.factories import DocumentoTextoFactory, SolicitacaoAssinaturaFactory
from processo_eletronico.models import DocumentoTextoProcesso, ModeloDespacho, Processo, SolicitacaoAssinaturaComAnexacaoProcesso, Tramite
from processo_eletronico.tests.factories import CompartilhamentoProcessoEletronicoSetorPessoaFactory, ProcessoFactory
from rh.models import Servidor
from rh.tests.factories import PapelFactory, ServidorFactory, SetorFactory

pytestmark = pytest.mark.django_db

CODIGO_VERIFICACAO = '12345'


def _logar_com_gov_br(client: Client, servidor: Servidor) -> None:
    user = servidor.get_user()
    client.force_login(user)
    sessao = client.session
    expira = (datetime.now() + timedelta(hours=1)).timestamp()
    sessao['token_govbr'] = {'decoded_data': {'exp': expira}, 'access_token': 'token'}
    sessao['autenticou_com_govbr'] = True
    sessao.save()
    cache.set(f'govbr_check_{user.get_vinculo().id}', CODIGO_VERIFICACAO, 300)


def _solicitar_assinatura_com_anexacao(com_perfil_do_solicitante: bool) -> SimpleNamespace:
    """Solicitação de assinatura com anexação a processo e trâmite com despacho, como a tela grava."""
    setor = SetorFactory(sigla=get_sigla_reitoria(), nome='Reitoria', codigo_siorg=str(Processo.CODIGO_SIORG))
    solicitante = ServidorFactory(setor=setor)
    signatario = ServidorFactory(pessoa_fisica__nome_usual='Signatário')
    papel = PapelFactory(servidor=signatario)
    documento = DocumentoTextoFactory(usuario_criacao=solicitante.get_user(), setor_dono=setor, status=DocumentoStatus.STATUS_AGUARDANDO_ASSINATURA)
    solicitacao = SolicitacaoAssinaturaFactory(documento=documento, solicitante=solicitante.get_user(), solicitado=signatario.get_vinculo())
    CompartilhamentoDocumentoPessoa.objects.create(
        documento=documento,
        vinculo_permitido=signatario.get_vinculo(),
        nivel_permissao=NivelPermissao.LER,
        usuario_criacao=solicitante.get_user(),
        solicitacao_assinatura=solicitacao,
    )
    processo = ProcessoFactory(setor_criacao=setor, usuario_gerador=solicitante.get_user())
    processo.interessados.add(solicitante.get_vinculo())  # o post_save do NUP 17 exige um interessado
    destino = SetorFactory()
    SolicitacaoAssinaturaComAnexacaoProcesso.objects.create(
        solicitacao_assinatura=solicitacao,
        processo_para_anexar=processo,
        destinatario_setor_tramite=destino,
        despacho_corpo='Encaminho para providências.',
        papel_solicitante=PapelFactory(servidor=solicitante) if com_perfil_do_solicitante else None,
    )
    ModeloDespacho.objects.create(cabecalho='Cabeçalho', rodape='Rodapé')
    TemplateNotificaGovBR.objects.create(
        id_template='1', tipo_notificacao=TemplateNotificaGovBR.CODIGO_VERIFICADOR, canal_notificacao=TemplateNotificaGovBR.APP_GOVBR
    )
    return SimpleNamespace(
        solicitante=solicitante, signatario=signatario, papel=papel, documento=documento, solicitacao=solicitacao, processo=processo, destino=destino
    )


def _assinar_com_gov_br(client: Client, cenario: SimpleNamespace) -> HttpResponse:
    _logar_com_gov_br(client, cenario.signatario)
    with patch('djtools.middleware.govbr.user_confiability_level', return_value='3'):
        return client.post(
            f'/documento_eletronico/assinar_documento_com_gov_br/{cenario.documento.pk}/',
            {'papel': cenario.papel.pk, 'codigo_verificacao': CODIGO_VERIFICACAO},
        )


def test_gov_br_assina_anexa_e_tramita_com_o_perfil_do_solicitante(client: Client, sync_permissions: None) -> None:
    cenario = _solicitar_assinatura_com_anexacao(com_perfil_do_solicitante=True)

    resposta = _assinar_com_gov_br(client, cenario)

    assert resposta.status_code == 302
    assert AssinaturaDocumentoTexto.objects.filter(documento=cenario.documento, assinatura__vinculo=cenario.signatario.get_vinculo()).exists()
    assert DocumentoTextoProcesso.objects.filter(processo=cenario.processo, documento=cenario.documento).exists()
    assert Tramite.objects.filter(processo=cenario.processo, destinatario_setor=cenario.destino).exists()


def test_gov_br_sem_perfil_do_solicitante_nao_assina_e_explica(client: Client, sync_permissions: None) -> None:
    cenario = _solicitar_assinatura_com_anexacao(com_perfil_do_solicitante=False)

    resposta = _assinar_com_gov_br(client, cenario)

    assert resposta.status_code == 302
    _assert_explica_e_nada_gravado(resposta, cenario)


def test_lote_sem_perfil_do_solicitante_pula_o_documento_e_explica(client: Client, sync_permissions: None) -> None:
    cenario = _solicitar_assinatura_com_anexacao(com_perfil_do_solicitante=False)
    user = cenario.signatario.get_user()
    user.set_password('123')
    user.save()
    client.force_login(user)

    resposta = client.post(f'/documento_eletronico/assinar_documento_lote/?ids={cenario.documento.pk}', {'senha': '123', 'papel': cenario.papel.pk})

    assert resposta.status_code == 302
    _assert_explica_e_nada_gravado(resposta, cenario)
    assert not [m for m in get_messages(resposta.wsgi_request) if m.level_tag == 'success']
    assert not DocumentoTexto.objects.get(pk=cenario.documento.pk).tem_identificador_definitivo


def _assert_explica_e_nada_gravado(resposta: HttpResponse, cenario: SimpleNamespace) -> None:
    erros = [str(m) for m in get_messages(resposta.wsgi_request) if m.level_tag == 'error']
    assert len(erros) == 1
    assert str(cenario.solicitante.get_user()) in erros[0]
    assert 'perfil' in erros[0]
    assert not AssinaturaDocumentoTexto.objects.filter(documento=cenario.documento).exists()
    assert not Assinatura.objects.filter(vinculo=cenario.signatario.get_vinculo()).exists()
    assert SolicitacaoAssinatura.objects.get(pk=cenario.solicitacao.pk).status == SolicitacaoStatus.STATUS_ESPERANDO
    assert DocumentoTexto.objects.get(pk=cenario.documento.pk).status == DocumentoStatus.STATUS_AGUARDANDO_ASSINATURA
    assert not DocumentoTextoProcesso.objects.filter(processo=cenario.processo).exists()
    assert not Tramite.objects.filter(processo=cenario.processo).exists()


def _postar_solicitacao_com_anexacao(client: Client, tipo_busca_encaminhar: str) -> SimpleNamespace:
    """O solicitante preenche despacho e perfil e envia com o radio ``tipo_busca_encaminhar`` escolhido."""
    setor = SetorFactory(sigla=get_sigla_reitoria(), nome='Reitoria', codigo_siorg=str(Processo.CODIGO_SIORG))
    solicitante = ServidorFactory(setor=setor)
    papel_solicitante = PapelFactory(servidor=solicitante)
    signatario = ServidorFactory()
    PapelFactory(servidor=signatario)
    documento = DocumentoTextoFactory(usuario_criacao=solicitante.get_user(), setor_dono=setor, status=DocumentoStatus.STATUS_CONCLUIDO)
    processo = ProcessoFactory(setor_criacao=setor, usuario_gerador=solicitante.get_user())
    CompartilhamentoProcessoEletronicoSetorPessoaFactory(setor_dono=setor, vinculo_permitido=solicitante.get_vinculo())
    destino = SetorFactory()
    client.force_login(solicitante.get_user())

    resposta = client.post(
        f'/documento_eletronico/solicitar_assinatura_com_anexacao/{documento.pk}/',
        {
            'solicitado': signatario.get_vinculo().pk,
            'processo_para_anexar': processo.pk,
            'tipo_busca_encaminhar': tipo_busca_encaminhar,
            'destinatario_setor_autocompletar': destino.pk,
            'despacho_corpo': 'Pa',
            'papel': papel_solicitante.pk if tipo_busca_encaminhar == 'sem_despacho' else '',
            'senha': '',
            'form-TOTAL_FORMS': '0',
            'form-INITIAL_FORMS': '0',
        },
    )
    return SimpleNamespace(resposta=resposta, documento=documento, destino=destino)


def test_solicitacao_sem_despacho_descarta_despacho_e_perfil_digitados(client: Client, sync_permissions: None) -> None:
    """O radio "Sem despacho" só esconde os campos: o texto e o perfil preenchidos antes não podem ser gravados (#17817)."""
    envio = _postar_solicitacao_com_anexacao(client, 'sem_despacho')

    assert envio.resposta.status_code == 302
    anexacao = SolicitacaoAssinaturaComAnexacaoProcesso.objects.get(solicitacao_assinatura__documento=envio.documento)
    assert anexacao.destinatario_setor_tramite == envio.destino
    assert not anexacao.despacho_corpo
    assert anexacao.papel_solicitante is None


def test_solicitacao_com_despacho_continua_exigindo_o_perfil(client: Client, sync_permissions: None) -> None:
    envio = _postar_solicitacao_com_anexacao(client, 'com_despacho')

    assert envio.resposta.status_code == 200
    assert 'É obrigatório informar um papel.' in envio.resposta.content.decode()
    assert not SolicitacaoAssinaturaComAnexacaoProcesso.objects.filter(solicitacao_assinatura__documento=envio.documento).exists()
