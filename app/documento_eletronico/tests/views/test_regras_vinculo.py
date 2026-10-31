from types import SimpleNamespace
from django.test import Client, RequestFactory

from django.conf import settings
from django.core.exceptions import NON_FIELD_ERRORS, ValidationError
from django.db import IntegrityError, transaction
from django.template.loader import render_to_string
import pytest

from comum.models import User
from comum.utils import get_sigla_reitoria
from documento_eletronico.forms import CriarDocumentoRelacionadoForm, DocumentoTextoEditarCorpoForm, EditarModeloDocumentoForm, TipoDocumentoTextoForm
from documento_eletronico.models import (
    ConfiguracaoVinculoDocumento,
    DocumentoTexto,
    ModeloDocumento,
    TipoDocumentoTexto,
    TipoVinculoDocumento,
    VinculoDocumentoTexto,
)
from documento_eletronico.views import _eh_visualizacao_anonima, _obter_corpo_visualizacao
from documento_eletronico.forms import VinculoDocumentoTextoForm
from documento_eletronico.status import DocumentoStatus
from documento_eletronico.tests.factories import (
    ConfiguracaoVinculoDocumentoFactory,
    DocumentoTextoFactory,
    ModeloDocumentoFactory,
    TipoVinculoDocumentoFactory,
)
from rh.tests.factories import ServidorFactory, SetorFactory


@pytest.mark.django_db
@pytest.mark.usefixtures('sync_permissions')
@pytest.mark.parametrize('regra', ['ausente', 'ativa', 'inativa', 'outros_tipos'])
def test_vinculacao_regulamenta_somente_combinacoes_configuradas(regra: str) -> None:
    usuario = ServidorFactory().get_user()
    modelo = ModeloDocumentoFactory()
    base = DocumentoTextoFactory(modelo=modelo, usuario_criacao=usuario, status=DocumentoStatus.STATUS_FINALIZADO)
    alvo = DocumentoTextoFactory(modelo=modelo, usuario_criacao=usuario, status=DocumentoStatus.STATUS_FINALIZADO)
    tipo_vinculo = TipoVinculoDocumentoFactory()
    configuracao = None
    if regra in ('ativa', 'inativa'):
        configuracao = ConfiguracaoVinculoDocumentoFactory(
            tipo_vinculo_documento=tipo_vinculo,
            tipo_documento_base=modelo.tipo_documento_texto,
            tipo_documento_alvo=modelo.tipo_documento_texto,
            ativo=regra == 'ativa',
        )
    elif regra == 'outros_tipos':
        ConfiguracaoVinculoDocumentoFactory(tipo_vinculo_documento=tipo_vinculo)
    request = RequestFactory().post('/documento_eletronico/vincular_documentos/')
    request.user = usuario
    formulario = VinculoDocumentoTextoForm(
        request=request,
        documento_texto_base=base,
        data={'documento_texto_base': base.pk, 'documento_texto_alvo': alvo.pk, 'tipo_vinculo_documento': tipo_vinculo.pk},
    )

    if regra == 'inativa':
        assert not formulario.is_valid()
        assert 'desativada' in str(formulario.errors['documento_texto_alvo'])
        assert not VinculoDocumentoTexto.objects.filter(documento_texto_base=base, documento_texto_alvo=alvo).exists()
    else:
        assert formulario.is_valid(), formulario.errors
        formulario.save()
        vinculo = VinculoDocumentoTexto.objects.get(documento_texto_base=base, documento_texto_alvo=alvo)
        assert vinculo.configuracao_id == (configuracao.pk if configuracao else None)


@pytest.mark.django_db
class TestPermissaoVincularDocumentos:
    """``vincular_documentos`` só cria vínculo em documento base que o usuário pode editar."""

    def _documento_concluido(self, usuario: User, status: int = DocumentoStatus.STATUS_CONCLUIDO) -> DocumentoTexto:
        return DocumentoTextoFactory(usuario_criacao=usuario, setor_dono=usuario.get_vinculo().relacionamento.setor, status=status)

    def test_leitor_sem_permissao_de_editar_nao_vincula(self, client: Client, sync_permissions: None) -> None:
        base = self._documento_concluido(ServidorFactory().get_user())
        leitor = ServidorFactory().get_user()
        client.force_login(leitor)

        resposta = client.get(f'/documento_eletronico/vincular_documentos/{base.pk}/')

        assert resposta.status_code == 403

    def test_documento_base_do_post_e_ignorado(self, client: Client, sync_permissions: None) -> None:
        usuario = ServidorFactory().get_user()
        base = self._documento_concluido(usuario)
        alvo = self._documento_concluido(usuario, status=DocumentoStatus.STATUS_FINALIZADO)
        documento_alheio = self._documento_concluido(ServidorFactory().get_user())
        client.force_login(usuario)

        client.post(
            f'/documento_eletronico/vincular_documentos/{base.pk}/',
            {
                'documento_texto_base': documento_alheio.pk,
                'documento_texto_alvo': alvo.pk,
                'tipo_vinculo_documento': TipoVinculoDocumentoFactory().pk,
            },
        )

        assert VinculoDocumentoTexto.objects.filter(documento_texto_base=base, documento_texto_alvo=alvo).exists()
        assert not VinculoDocumentoTexto.objects.filter(documento_texto_base=documento_alheio).exists()


@pytest.fixture
def tipos_documento(db):
    portaria = TipoDocumentoTexto.objects.create(nome='Portaria para teste', sigla='PORT-TESTE')
    edital = TipoDocumentoTexto.objects.create(nome='Edital para teste', sigla='EDIT-TESTE')
    retificacao_edital = TipoDocumentoTexto.objects.create(nome='Retificação de Edital para teste', sigla='RET-EDIT-TESTE')
    return portaria, edital, retificacao_edital


@pytest.fixture
def tipo_vinculo(db):
    return TipoVinculoDocumento.objects.create(
        descricao='Retificação para teste',
        descricao_voz_ativa='retifica',
        descricao_voz_passiva='é retificado por',
        modo_uso=TipoVinculoDocumento.MODO_REGULAMENTADO,
    )


@pytest.mark.django_db
class TestConfiguracaoVinculoDocumento:
    def test_rejeita_configuracao_para_vinculo_livre(self, tipos_documento):
        portaria, _, _ = tipos_documento
        tipo_livre = TipoVinculoDocumento.objects.create(
            descricao='Referência livre para teste',
            descricao_voz_ativa='referencia',
            descricao_voz_passiva='é referenciado por',
        )
        configuracao = ConfiguracaoVinculoDocumento(
            tipo_vinculo_documento=tipo_livre,
            tipo_documento_base=portaria,
            tipo_documento_alvo=portaria,
        )

        with pytest.raises(ValidationError, match='Somente tipos de vínculo regulamentados') as excecao:
            configuracao.full_clean()

        assert NON_FIELD_ERRORS in excecao.value.error_dict

    def test_rejeita_modelo_padrao_de_outro_tipo(self, tipos_documento, tipo_vinculo):
        portaria, edital, _ = tipos_documento
        modelo_edital = ModeloDocumento.objects.create(nome='Modelo de edital para teste', tipo_documento_texto=edital)
        configuracao = ConfiguracaoVinculoDocumento(
            tipo_vinculo_documento=tipo_vinculo,
            tipo_documento_base=portaria,
            tipo_documento_alvo=portaria,
            modelo_padrao=modelo_edital,
        )

        with pytest.raises(ValidationError, match='modelo padrão deve pertencer ao tipo do documento base'):
            configuracao.full_clean()

    def test_impede_regra_duplicada(self, tipos_documento, tipo_vinculo):
        portaria, _, _ = tipos_documento
        dados = {
            'tipo_vinculo_documento': tipo_vinculo,
            'tipo_documento_base': portaria,
            'tipo_documento_alvo': portaria,
        }
        ConfiguracaoVinculoDocumento.objects.create(**dados)

        with pytest.raises(IntegrityError), transaction.atomic():
            ConfiguracaoVinculoDocumento.objects.create(**dados)

    def test_formulario_exibe_apenas_configuracoes_do_tipo_alvo(self, tipos_documento, tipo_vinculo):
        portaria, edital, retificacao_edital = tipos_documento
        modelo_portaria = ModeloDocumento.objects.create(nome='Modelo de portaria para teste', tipo_documento_texto=portaria)
        modelo_retificacao = ModeloDocumento.objects.create(nome='Modelo de retificação para teste', tipo_documento_texto=retificacao_edital)
        configuracao_portaria = ConfiguracaoVinculoDocumento.objects.create(
            tipo_vinculo_documento=tipo_vinculo,
            tipo_documento_base=portaria,
            tipo_documento_alvo=portaria,
            modelo_padrao=modelo_portaria,
        )
        configuracao_edital = ConfiguracaoVinculoDocumento.objects.create(
            tipo_vinculo_documento=tipo_vinculo,
            tipo_documento_base=retificacao_edital,
            tipo_documento_alvo=edital,
            modelo_padrao=modelo_retificacao,
        )

        formulario = CriarDocumentoRelacionadoForm(documento=SimpleNamespace(tipo=edital))

        assert list(formulario.fields['configuracao'].queryset) == [configuracao_edital]
        assert list(formulario.fields['modelo'].queryset) == [modelo_retificacao]
        assert configuracao_portaria not in formulario.fields['configuracao'].queryset


class TestProtecaoVinculoDocumento:
    def test_impede_remover_vinculo_regulamentado(self):
        vinculo = VinculoDocumentoTexto(configuracao_id=1)

        with pytest.raises(ValidationError, match='compõem o histórico'):
            vinculo.delete()


class TestEditorDocumento:
    def test_aplica_css_documental_somente_aos_editores_do_modulo(self):
        widgets = (
            DocumentoTextoEditarCorpoForm.base_fields['corpo'].widget,
            TipoDocumentoTextoForm.base_fields['cabecalho_padrao'].widget,
            TipoDocumentoTextoForm.base_fields['rodape_padrao'].widget,
            EditarModeloDocumentoForm.base_fields['corpo_padrao'].widget,
        )

        assert all(widget.mce_attrs['content_css'] == '/static/documento_eletronico/css/documento.css' for widget in widgets)
        assert all('style' not in widget.attrs for widget in widgets)
        assert settings.TINYMCE_DEFAULT_CONFIG['width'] == '100%'
        assert settings.TINYMCE_DEFAULT_CONFIG['height'] == 600


class TestApresentacaoVinculoIntegral:
    @pytest.mark.parametrize(
        ('is_anonymous', 'query', 'esperado'),
        [
            (True, {}, True),
            (False, {'forcar_anonimo': '1'}, True),
            (False, {}, False),
        ],
    )
    def test_identifica_contexto_de_visualizacao_anonima(self, is_anonymous: bool, query: dict[str, str], esperado: bool) -> None:
        request = SimpleNamespace(user=SimpleNamespace(is_anonymous=is_anonymous), GET=query)

        assert _eh_visualizacao_anonima(request) is esperado

    def test_usa_corpo_anonimizado_na_visualizacao_publica(self):
        documento = SimpleNamespace(
            corpo_para_visualizacao='<p>Nome visível</p>',
            corpo_para_visualizacao_anonima='<p>&lt;ANONIMIZADO&gt;</p>',
        )

        resultado = _obter_corpo_visualizacao(documento, eh_anonimo=True)

        assert 'Nome visível' not in resultado
        assert '&lt;ANONIMIZADO&gt;' in resultado

    def test_opcao_explicita_que_copia_integralmente_o_conteudo(self):
        campo = CriarDocumentoRelacionadoForm.base_fields['usar_conteudo_vigente_como_base']

        assert campo.label == 'Criar a partir do conteúdo vigente'
        assert 'Copia integralmente' in campo.help_text
        assert 'onde se lê' in campo.help_text

    def test_procedencia_utiliza_descricao_do_tipo_de_vinculo(self):
        original = SimpleNamespace(identificador='PORTARIA 1/2026')
        relacionado = SimpleNamespace(identificador='PORTARIA 2/2026', get_absolute_url=lambda: '/documento/2/')
        tipo_vinculo = SimpleNamespace(descricao_voz_ativa='substitui')
        vinculo = SimpleNamespace(documento_texto_base=relacionado, tipo_vinculo_documento=tipo_vinculo)

        resultado = render_to_string(
            'documento_eletronico/procedencia_retificacao_include.html',
            {
                'documento_original': original,
                'documento_retificacao': relacionado,
                'tipo_vinculo': tipo_vinculo,
                'vinculos_retificacao': [vinculo],
                'tipo_versao': 'retificacao',
            },
        )

        assert 'Este documento substitui PORTARIA 1/2026.' in resultado
        assert 'PORTARIA 2/2026' in resultado


@pytest.mark.django_db
class TestVisualizacaoDocumentoRelacionado:
    """Visualização (``visualizar_documento``) do documento relacionado criado a partir de um documento finalizado.

    Issue #17857 (Sentry SUAP-WYH): abrir a retificação ainda em rascunho respondia 500 (``IndexError``) porque a
    procedência só listava retificações finalizadas e a lista ficava vazia.
    """

    def _criar_relacionado(self, client: Client) -> tuple[DocumentoTexto, DocumentoTexto]:
        """Cria, pela tela, o documento relacionado (em rascunho) a partir de um original finalizado."""
        servidor = ServidorFactory(setor=SetorFactory(sigla=get_sigla_reitoria(), nome='Reitoria'))
        usuario = servidor.get_user()
        client.force_login(usuario)
        modelo = ModeloDocumentoFactory()
        original = DocumentoTextoFactory(
            modelo=modelo,
            usuario_criacao=usuario,
            setor_dono=servidor.setor,
            status=DocumentoStatus.STATUS_FINALIZADO,
            corpo='<p>Texto original</p>',
        )
        configuracao = ConfiguracaoVinculoDocumentoFactory(
            tipo_vinculo_documento=TipoVinculoDocumentoFactory(descricao_voz_ativa='retifica'),
            tipo_documento_base=modelo.tipo_documento_texto,
            tipo_documento_alvo=modelo.tipo_documento_texto,
        )

        resposta = client.post(
            f'/documento_eletronico/criar_documento_relacionado/{original.pk}/',
            {'configuracao': configuracao.pk, 'modelo': modelo.pk, 'usar_conteudo_vigente_como_base': 'on'},
        )

        relacionado = VinculoDocumentoTexto.objects.get(documento_texto_alvo=original).documento_texto_base
        assert resposta.url == f'/documento_eletronico/editar_documento/{relacionado.pk}/'
        assert relacionado.status == DocumentoStatus.STATUS_RASCUNHO
        # O identificador é gravado depois da inserção; a instância da factory não o tem.
        return DocumentoTexto.objects.get(pk=original.pk), relacionado

    def test_relacionado_em_rascunho_exibe_a_propria_procedencia(self, client: Client, sync_permissions: None) -> None:
        original, relacionado = self._criar_relacionado(client)

        resposta = client.get(f'/documento_eletronico/visualizar_documento/{relacionado.pk}/')

        assert resposta.status_code == 200
        html = resposta.content.decode()
        assert f'Este documento retifica {original.identificador}.' in html
        assert f'href="{relacionado.get_absolute_url()}"' in html

    def test_relacionado_finalizado_exibe_a_procedencia_no_original(self, client: Client, sync_permissions: None) -> None:
        original, relacionado = self._criar_relacionado(client)
        DocumentoTexto.objects.filter(pk=relacionado.pk).update(status=DocumentoStatus.STATUS_FINALIZADO)

        resposta = client.get(f'/documento_eletronico/visualizar_documento/{original.pk}/')

        assert resposta.status_code == 200
        html = resposta.content.decode()
        assert f'Documento apresentado: {original.identificador} — conteúdo consolidado.' in html
        assert f'href="{relacionado.get_absolute_url()}"' in html
