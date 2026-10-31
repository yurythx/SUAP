"""Anexo de documento na manifestação de Solicitação de Prorrogação (Demanda 2505).

Especificação 1 (Fases 1/3) -- o bloqueio original de
`Manifestacao.pode_adicionar_documento`/`pode_remover_documento` só liberava o
anexo quando `self.registrada`. Isso já cobria a manifestação de prorrogação
enquanto REGISTRADA; a extensão também libera quando ela está ENVIADA (para
quem já enviou explicitamente e ainda quer anexar mais um documento), fechando
de volta assim que o auditor a recebe (via `Monitoramento.pode_editar_manifestacoes`,
que já nega quando há manifestação corrente `aguardando_analise()`).

Especificação 2 (Fase 4) -- `solicitar_prorrogacao_manifestacao` deixou de
enviar automaticamente a manifestação ao auditor quando quem registra é o
chefe de setor: a manifestação agora nasce sempre REGISTRADA (igual aos
demais tipos, via `MonitoramentoManifestacaoForm`), e o envio passa a
depender de uma ação explícita do usuário -- `POST` em
`entregar_manifestacao`, o mesmo botão "Enviar manifestação" já usado pelos
outros tipos. Isso fecha a corrida em que o auditor podia receber a
manifestação antes do usuário conseguir navegar até a aba "Documentos" e
anexar o comprovante.

Este módulo cobre, isoladamente do caminho feliz de `test_fluxo_http.py`:

1. Unitário de model: prorrogação ENVIADA libera `pode_adicionar_documento`.
2. Unitário de model: após `receber()`, a janela fecha de novo.
3. Unitário de model (regressão): outro tipo de manifestação ENVIADA continua
   negado -- a mudança não vaza para os demais tipos.
4. HTTP fim-a-fim: solicitar prorrogação (nasce REGISTRADA) -> upload
   permitido -> entregar manifestação (REGISTRADA -> ENVIADA) -> auditor
   recebe -> upload volta a ser negado.
5. HTTP: upload permitido logo após a criação via
   `solicitar_prorrogacao_manifestacao`, ainda REGISTRADA (mecanismo
   genérico de `pode_adicionar_documento`, sem depender da extensão da
   Especificação 1).
6. HTTP: `entregar_manifestacao` transiciona a prorrogação REGISTRADA ->
   ENVIADA quando acionada pelo chefe de setor.
"""

from __future__ import annotations

from datetime import timedelta

from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from auditoria.models.manifestacao import ManifestacaoStatus, TipoManifestacao
from auditoria.models.monitoramento import MonitoramentoStatus
from auditoria.tests import factories as f
from comum.utils import get_setor
from djtools.utils import get_datetime_now
from documento_eletronico.models import TipoConferencia, TipoDocumento

# PDF mínimo válido (uma página em branco 72x72pt, sem senha/encriptação) -- passa
# em check_pdf()/check_can_edit_pdf() (djtools/utils/pdf.py), que dependem do
# binário qpdf (settings.QPDF_CMD, default /usr/bin/qpdf; presente na imagem
# Docker do projeto via docker/Dockerfile.base). Rodando localmente fora do
# Docker, exporte QPDF_CMD com o caminho do binário instalado (ex.: `which qpdf`).
_PDF_MINIMO = (
    b'%PDF-1.3\n%\xe2\xe3\xcf\xd3\n1 0 obj\n<<\n/Producer (pypdf)\n>>\nendobj\n'
    b'2 0 obj\n<<\n/Type /Pages\n/Count 1\n/Kids [ 4 0 R ]\n>>\nendobj\n'
    b'3 0 obj\n<<\n/Type /Catalog\n/Pages 2 0 R\n>>\nendobj\n'
    b'4 0 obj\n<<\n/Type /Page\n/Resources <<\n>>\n/MediaBox [ 0.0 0.0 72 72 ]\n/Parent 2 0 R\n>>\nendobj\n'
    b'xref\n0 5\n0000000000 65535 f \n0000000015 00000 n \n0000000054 00000 n \n'
    b'0000000113 00000 n \n0000000162 00000 n \ntrailer\n<<\n/Size 5\n/Root 3 0 R\n/Info 1 0 R\n>>\n'
    b'startxref\n254\n%%EOF\n'
)


def _arquivo_pdf():
    return SimpleUploadedFile('teste.pdf', _PDF_MINIMO, content_type='application/pdf')


def _data(d):
    return d.strftime('%d/%m/%Y')


def _reload(obj):
    """Recarrega a instância do banco (ver nota em test_fluxo_http._reload)."""
    return type(obj).objects.get(pk=obj.pk)


def _preparar_monitoramento(c):
    """Leva o monitoramento de `cenario_atendimento` a EM_MONITORAMENTO com uma
    solicitação de providência ativa e CIENTE -- pré-requisito para que
    ``Monitoramento.pode_editar_manifestacoes``/``pode_adicionar_manifestacao``
    (usados por ``Manifestacao.pode_adicionar_documento`` e pela view
    ``solicitar_prorrogacao_manifestacao``) retornem True para o gestor.

    Mesmo padrão de ``test_deadlocks_maquina_estado.montar_em_revisao``: monta o
    estado diretamente via factories/transições FSM, sem replay de HTTP.
    """
    mon = _reload(c.monitoramento)
    solicitacao = f.SolicitacaoProvidenciaFactory(monitoramento=mon, setor=c.setor)
    if mon.status == MonitoramentoStatus.REGISTRADO:
        mon.iniciar_monitoramento()
        mon.save()
    solicitacao = _reload(solicitacao)
    solicitacao.informar_ciencia(c.gestor_user)
    solicitacao.save()
    return _reload(mon), _reload(solicitacao)


def _montar_manifestacao_enviada(c, tipo):
    """Cria (via factory) e envia (via transição FSM real) uma manifestação do
    ``tipo`` informado, sobre um monitoramento/solicitação já preparados."""
    mon, solicitacao = _preparar_monitoramento(c)
    manifestacao = f.ManifestacaoFactory(monitoramento=mon, solicitacao_providencia=solicitacao, incluido_por=c.gestor_user, tipo=tipo)
    manifestacao.enviar(c.gestor_user)
    manifestacao.save()
    return manifestacao


class TestPodeAdicionarDocumentoProrrogacao:
    """Casos 1-3 da Fase 3: unitários de model, direto em pode_adicionar_documento/pode_remover_documento."""

    def test_libera_para_prorrogacao_enviada(self, cenario_atendimento):
        c = cenario_atendimento
        manifestacao = _montar_manifestacao_enviada(c, TipoManifestacao.SOLICITACAO_PRORROGACAO)
        assert manifestacao.status == ManifestacaoStatus.ENVIADA
        assert manifestacao.pode_adicionar_documento(c.gestor_user) is True
        assert manifestacao.pode_remover_documento(c.gestor_user) is True

    def test_fecha_janela_apos_receber(self, cenario_atendimento):
        c = cenario_atendimento
        manifestacao = _montar_manifestacao_enviada(c, TipoManifestacao.SOLICITACAO_PRORROGACAO)
        manifestacao.receber(c.auditor_user)
        manifestacao.save()
        manifestacao = _reload(manifestacao)
        assert manifestacao.status == ManifestacaoStatus.RECEBIDA
        assert manifestacao.pode_adicionar_documento(c.gestor_user) is False
        assert manifestacao.pode_remover_documento(c.gestor_user) is False

    def test_outros_tipos_continuam_restritos_a_registrada(self, cenario_atendimento):
        c = cenario_atendimento
        manifestacao = _montar_manifestacao_enviada(c, TipoManifestacao.ENCAMINHAMENTO_PROVIDENCIAS)
        assert manifestacao.status == ManifestacaoStatus.ENVIADA
        assert manifestacao.pode_adicionar_documento(c.gestor_user) is False
        assert manifestacao.pode_remover_documento(c.gestor_user) is False


def _solicitar_prorrogacao_via_http(c, mon, solicitacao):
    """POST em `solicitar_prorrogacao_manifestacao` como o gestor (chefe de setor).

    Desde a Fase 4, o envio automático foi removido: a manifestação nasce
    sempre REGISTRADA, mesmo quando quem registra é o chefe de setor.
    """
    client = c.client
    client.force_login(c.gestor_user)
    prazo_solicitado = solicitacao.prazo_atual + timedelta(days=10)
    resp = client.post(
        reverse('auditoria:solicitar_prorrogacao_manifestacao', kwargs={'monitoramento_id': mon.id}),
        {
            'tipo': TipoManifestacao.SOLICITACAO_PRORROGACAO.value,
            'texto': 'Justificativa para a prorrogação.',
            'prazo_atual': _data(solicitacao.prazo_atual),
            'prazo_solicitado': _data(prazo_solicitado),
        },
    )
    assert resp.status_code in (200, 302)
    manifestacao = mon.manifestacoes.order_by('-id').first()
    assert manifestacao is not None
    assert manifestacao.tipo == TipoManifestacao.SOLICITACAO_PRORROGACAO
    assert manifestacao.status == ManifestacaoStatus.REGISTRADA
    return manifestacao


def _upload_documento(client, manifestacao, tipo_documento, tipo_conferencia, setor_dono_id, dono_documento_id, assunto):
    return client.post(
        reverse('auditoria:upload_documento_manifestacao', kwargs={'manifestacao_id': manifestacao.id}),
        {
            'assunto': assunto,
            'tipo': tipo_documento.id,
            'tipo_conferencia': tipo_conferencia.id,
            'setor_dono': setor_dono_id,
            'dono_documento': dono_documento_id,
            # DocumentoDigitalizadoForm declara identificador_numero/ano como
            # IntegerFieldPlus explícito (não herdado do model, onde são
            # blank=True): isso os torna required=True no form.
            'identificador_numero': '1',
            'identificador_ano': str(get_datetime_now().year),
            'arquivo': _arquivo_pdf(),
        },
    )


class TestUploadDocumentoProrrogacaoHTTP:
    """Caso 4-6 da Fase 4: fim-a-fim via cliente de teste HTTP."""

    def test_gestor_anexa_documento_antes_de_enviar_e_perde_acesso_apos_receber(self, cenario_atendimento):
        c = cenario_atendimento
        client = c.client
        mon, solicitacao = _preparar_monitoramento(c)

        tipo_documento = TipoDocumento.objects.create(nome='Ofício de Teste 2505', sigla='OF-TESTE-2505')
        tipo_conferencia = TipoConferencia.objects.create(descricao='Cópia Simples de Teste 2505')
        setor_dono_id = get_setor(c.gestor_user).id
        dono_documento_id = c.gestor.get_vinculo().id

        def _upload(assunto):
            return _upload_documento(client, manifestacao, tipo_documento, tipo_conferencia, setor_dono_id, dono_documento_id, assunto)

        # Gestor solicita a prorrogação -- a manifestação nasce REGISTRADA (Fase 4:
        # o envio automático foi removido da view).
        manifestacao = _solicitar_prorrogacao_via_http(c, mon, solicitacao)

        # Upload de documento externo pelo gestor, ainda REGISTRADA -- permitido pelo
        # mecanismo genérico de `pode_adicionar_documento` (caso `registrada`).
        resp = _upload('Comprovante para a prorrogação')
        assert resp.status_code in (200, 302)
        manifestacao = _reload(manifestacao)
        assert manifestacao.documentos.nao_removidos().count() == 1

        # Gestor envia a manifestação explicitamente -- REGISTRADA -> ENVIADA.
        resp = client.post(reverse('auditoria:entregar_manifestacao', kwargs={'manifestacao_id': manifestacao.id}))
        assert resp.status_code in (200, 302)
        manifestacao = _reload(manifestacao)
        assert manifestacao.status == ManifestacaoStatus.ENVIADA

        # Auditor recebe a manifestação -- a janela de anexo se fecha (via
        # Monitoramento.pode_editar_manifestacoes, que nega quando há manifestação
        # corrente aguardando_analise()).
        client.force_login(c.auditor_user)
        resp = client.post(reverse('auditoria:receber_manifestacao', kwargs={'manifestacao_id': manifestacao.id}))
        assert resp.status_code in (200, 302)
        manifestacao = _reload(manifestacao)
        assert manifestacao.status == ManifestacaoStatus.RECEBIDA

        client.force_login(c.gestor_user)
        resp = _upload('Novo documento após recebimento')
        assert resp.status_code in (200, 302)
        manifestacao = _reload(manifestacao)
        assert manifestacao.documentos.nao_removidos().count() == 1

    def test_upload_documento_permitido_enquanto_registrada(self, cenario_atendimento):
        c = cenario_atendimento
        client = c.client
        mon, solicitacao = _preparar_monitoramento(c)

        tipo_documento = TipoDocumento.objects.create(nome='Ofício de Teste 2505 (registrada)', sigla='OF-TESTE-2505-REG')
        tipo_conferencia = TipoConferencia.objects.create(descricao='Cópia Simples de Teste 2505 (registrada)')
        setor_dono_id = get_setor(c.gestor_user).id
        dono_documento_id = c.gestor.get_vinculo().id

        manifestacao = _solicitar_prorrogacao_via_http(c, mon, solicitacao)
        assert manifestacao.status == ManifestacaoStatus.REGISTRADA

        resp = _upload_documento(
            client, manifestacao, tipo_documento, tipo_conferencia, setor_dono_id, dono_documento_id, 'Comprovante enquanto registrada'
        )
        assert resp.status_code in (200, 302)
        manifestacao = _reload(manifestacao)
        assert manifestacao.documentos.nao_removidos().count() == 1

    def test_entregar_manifestacao_transiciona_prorrogacao_de_registrada_para_enviada(self, cenario_atendimento):
        c = cenario_atendimento
        client = c.client
        mon, solicitacao = _preparar_monitoramento(c)

        manifestacao = _solicitar_prorrogacao_via_http(c, mon, solicitacao)
        assert manifestacao.status == ManifestacaoStatus.REGISTRADA

        resp = client.post(reverse('auditoria:entregar_manifestacao', kwargs={'manifestacao_id': manifestacao.id}))
        assert resp.status_code in (200, 302)
        manifestacao = _reload(manifestacao)
        assert manifestacao.status == ManifestacaoStatus.ENVIADA
