import itertools
import operator
import re
import uuid
from datetime import date, datetime
from functools import reduce
from urllib.parse import urljoin

from django.apps.registry import apps
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.contenttypes.models import ContentType
from django.core.cache import cache
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Case, CharField, F, IntegerField, Max, OuterRef, Q, Subquery, Value, When
from django.dispatch import receiver
from django.http import FileResponse, Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.template import TemplateSyntaxError
from django.template.defaultfilters import pluralize
from django.urls import reverse_lazy
from django.utils.decorators import method_decorator
from django.utils.html import escape
from django.utils.safestring import mark_safe
from django.views.generic.edit import FormView
from formtools.wizard.views import SessionWizardView
from reversion import revisions as reversion
from reversion.models import Version
from sentry_sdk import capture_exception
from django.db.models.functions import TruncDate

if 'catalogo_provedor_servico' in settings.INSTALLED_APPS:
    from catalogo_provedor_servico.models import TemplateNotificaGovBR
from comum.models import APIExterna, Configuracao, Vinculo
from comum.utils import get_setor, get_todos_setores
from djtools import documentos, layout
from djtools.middleware.govbr import govbr_token_required
from djtools.signals import minhas_acoes
from djtools.templatetags.filters import sanitize
from djtools.utils import (
    JsonResponse,
    get_client_ip,
    get_datetime_now,
    httprr,
    ids_da_query,
    permission_required,
    random_with_N_digits,
    render_to_string,
    rtr,
    send_mail,
    send_notification,
)
from documento_eletronico.forms import (
    AssinarDocumentoGovBRForm,
    AvaliarSolicitacaoCompartilhamentoDocumentoDigitalizadoForm,
    ConsultaPublicaDocumentoFormClass,
    DocumentoDigitalizadoAnexoSimplesForm,
    DocumentoTextoForm,
    DocumentoTextoPessoalForm,
    ListarDocumentosTextoForm,
    SolicitarCompartilhamentoDocumentoDigitalizadoForm,
    CriarDocumentoRelacionadoForm,
)
from documento_eletronico.comparacao import gerar_comparacao_documentos, preparar_html_documento
from documento_eletronico.models import AssinaturaDocumentoTexto, Documento, SolicitacaoCompartilhamentoDocumentoDigitalizadoPessoa, TipoDocumento
from documento_eletronico.status import DocumentoStatus
from documento_eletronico.utils import (
    Notificar,
    app_processo_eletronico_estah_instalada,
    gerar_codigo_verificador_documento,
    get_previous,
    get_variaveis,
    imprimir_pdf,
)
from processo_eletronico.utils import iniciar_gerenciamento_compartilhamento
from rh.models import Setor
from rh.views import rh_servidor_view_tab

from . import tasks
from .forms import (
    AssinarDocumentoForm,
    AutenticacaoDocumentoDigitalizado,
    AutenticacaoDocumentoTexto,
    CancelarDocumentoForm,
    DocumentoAlterarNivelAcessoForm,
    DocumentoTextoEditarCorpoForm,
    DocumentoTextoEditarTagsAnonimizacaoForm,
    DocumentoTextoFormEditarInteressados,
    EditarModeloDocumentoForm,
    GeradorIdentificadorDocumentoForm,
    GerenciarCompartilhamentoDocumentoForm,
    GerenciarCompartilhamentoSetorForm,
    RejeitarSolicitacaoAssinaturaForm,
    RevisarDocumentoForm,
    SolicitacaoAssinaturaComAnexacaoForm,
    SolicitacaoAssinaturaEmLoteForm,
    SolicitacaoAssinaturaForm,
    SolicitacaoComplementaresComAnexacaoFormSet,
    SolicitacaoComplementaresFormSet,
    SolicitacaoRevisaoForm,
    VinculoDocumentoTextoForm,
)
from .generators import montar_identificador_sigla
from .models import (
    CompartilhamentoDocumentoPessoa,
    DocumentoDigitalizado,
    DocumentoDigitalizadoAnexoSimples,
    DocumentoDigitalizadoPessoal,
    DocumentoTexto,
    DocumentoTextoAnexoDocumentoDigitalizado,
    DocumentoTextoAnexoDocumentoTexto,
    DocumentoTextoPessoal,
    HipoteseLegal,
    ModeloDocumento,
    NivelAcesso,
    NivelPermissao,
    RegistroAcaoDocumento,
    RegistroAcaoDocumentoTexto,
    ConfiguracaoVinculoDocumento,
    SolicitacaoAssinatura,
    SolicitacaoRevisao,
    SolicitacaoStatus,
    TipoDocumentoTexto,
    TipoPermissao,
    TipoVinculoDocumento,
    VinculoDocumentoTexto,
)
from .utils import acesso_ao_documento_em_funcao_cargo, eh_auditor_chefe, get_documento_texto_tamanho_maximo_em_mb


@layout.atribuidos_a_mim()
def index_atribuidos_a_mim(request):
    pendencias = []

    qtd_documentos_a_assinar = DocumentoTexto.objects.esperando_assinatura(request.user).count()
    if qtd_documentos_a_assinar:
        pendencias.append(
            {
                'titulo': f'Documento{pluralize(qtd_documentos_a_assinar)} Eletrônico{pluralize(qtd_documentos_a_assinar)}',
                'subtitulo': 'aguardando assinatura',
                'qtd': qtd_documentos_a_assinar,
                'url': '/admin/documento_eletronico/documentotexto/?opcao=4',
            }
        )

    qtd_documentos_a_revisar = DocumentoTexto.objects.revisao_pendente(user=request.user).count()
    if qtd_documentos_a_revisar:
        pendencias.append(
            {
                'titulo': f'Documento{pluralize(qtd_documentos_a_revisar)} Eletrônico{pluralize(qtd_documentos_a_revisar)}',
                'subtitulo': 'aguardando revisão',
                'qtd': qtd_documentos_a_revisar,
                'url': '/admin/documento_eletronico/documentotexto/?opcao=6',
            }
        )

    qtd_documentos_a_avaliar_revisao = DocumentoTexto.objects.proprios(request.user).filter(status=DocumentoStatus.STATUS_REVISADO).count()
    if qtd_documentos_a_avaliar_revisao:
        pendencias.append(
            {
                'titulo': f'Documento{pluralize(qtd_documentos_a_avaliar_revisao)} Eletrônico{pluralize(qtd_documentos_a_avaliar_revisao)}',
                'subtitulo': 'aguardando avaliação',
                'qtd': qtd_documentos_a_avaliar_revisao,
                'url': '/admin/documento_eletronico/documentotexto/?opcao=3&status__exact=4',
            }
        )

    return pendencias


@rtr()
@permission_required('documento_eletronico.view_documentotexto')
def dashboard(request):
    title = 'Dashboard: Documentos Eletrônicos'

    meus_documentos = DocumentoTexto.objects.proprios(request.user).count()
    meus_favoritos = DocumentoTexto.objects.filter(usuarios_marcadores_favoritos=request.user).count()
    compartilhados_comigo = DocumentoTexto.objects.compartilhados(request.user).count()
    esperando_minha_assinatura = DocumentoTexto.objects.esperando_assinatura(request.user).count()
    minhas_requisicoes_assinaturas = DocumentoTexto.objects.assinatura_requisitada_por(request.user).count()
    assinados_por_mim = DocumentoTexto.objects.assinados(request.user).count()

    esperando_minha_revisao = DocumentoTexto.objects.revisao_pendente(request.user).count()
    minhas_requisicoes_revisoes = DocumentoTexto.objects.requisicao_pendente(request.user).count()
    revisados_por_mim = DocumentoTexto.objects.revisados_por(request.user).count()
    vinculados_a_mim = DocumentoTexto.objects.vinculados_a_mim(request.user).count()

    estados_terminais = [DocumentoStatus.STATUS_CONCLUIDO, DocumentoStatus.STATUS_FINALIZADO, DocumentoStatus.STATUS_CANCELADO]
    meus_documentos_pendentes = DocumentoTexto.objects.proprios(request.user).exclude(status__in=estados_terminais)
    return locals()


def verificar_permissao_tramite(usuario_setor, processos_incluido):
    for processo in processos_incluido:
        ultimo_tramite = processo.get_ultimo_tramite()
        if ultimo_tramite:
            if ultimo_tramite.get_destino() == usuario_setor:
                return True
        elif processo.setor_criacao == usuario_setor:
            return True

    return False


def get_or_create_solicitacao(solicitante, solicitado, documento, conceder_acesso=False):
    comp_doc_pessoa_criado_via_solicitacao_assinatura = None
    if not documento.pode_ler(solicitado.user, verificar_acesso_cargo=False) and conceder_acesso:
        # Condece permissão para o balizador
        comp_doc_pessoa_criado_via_solicitacao_assinatura, _ = CompartilhamentoDocumentoPessoa.objects.get_or_create(
            vinculo_permitido=solicitado, documento=documento, nivel_permissao=NivelPermissao.LER
        )
    try:
        obj = SolicitacaoAssinatura.objects.get(documento_id=documento.id, solicitado=solicitado, status=SolicitacaoStatus.STATUS_ESPERANDO)
        created = False
    except SolicitacaoAssinatura.MultipleObjectsReturned:
        msg = f'Existem mais de uma solicitação de assinatura pendente para {solicitado} para este documento.'
        raise ValidationError(msg)
    except SolicitacaoAssinatura.DoesNotExist:
        obj = SolicitacaoAssinatura(documento_id=documento.id, solicitado=solicitado, solicitante=solicitante)
        obj.save()

        if comp_doc_pessoa_criado_via_solicitacao_assinatura:
            comp_doc_pessoa_criado_via_solicitacao_assinatura.solicitacao_assinatura = obj
            comp_doc_pessoa_criado_via_solicitacao_assinatura.save(suspender_notificacao=True)
        created = True

    return obj, created


# TODO: Este método não ficaria melhor estando em Documento?
def get_or_create_balizadora(solicitante, solicitado, documento):
    if documento.possui_assinatura():
        return documento.get_solicitacao_balizadora()
    else:
        solicitacao, _ = get_or_create_solicitacao(solicitante, solicitado, documento, True)
        return solicitacao


def construir_ligacoes_entre_solicitacoes(solicitacoes_dict, root):
    for index, solicitacoes in list(solicitacoes_dict.items()):
        condicionantes = solicitacoes_dict.get(index - 1, [root])
        for solicitacao in solicitacoes:
            solicitacao.adicionar_condicionantes(condicionantes)
            solicitacao.save()


def registrar_acao_documento_texto(request, documento, tipo_acao, observacao=''):
    user = request.user
    ip = get_client_ip(request)
    RegistroAcaoDocumentoTexto.registrar_acao(documento=documento, tipo_acao=tipo_acao, user=user, ip=ip, observacao=observacao)


def registar_acesso_documento_texto(request, documento, acesso_via_cargo):
    user = request.user
    ip = get_client_ip(request)
    RegistroAcaoDocumentoTexto.registar_acesso(documento=documento, user=user, ip=ip, acesso_via_cargo=acesso_via_cargo)


def get_documento_or_forbidden(user, documento_id):
    documento = get_documento_texto(documento_id)

    pode_carregar_doc = False

    if documento:
        if user.is_authenticated:
            pode_carregar_doc = documento.pode_ler(user)
        else:
            pode_carregar_doc = True

    if pode_carregar_doc:
        if not documento.eh_documento_pessoal:
            documento_do_usuario = DocumentoTexto.objects.filter(id=documento_id).first()
        else:
            documento_do_usuario = DocumentoTextoPessoal.objects.filter(id=documento_id).first()
        if documento_do_usuario:
            return documento_do_usuario
    raise PermissionDenied


def iter_incrementing_name(name):
    prefix = 'Clone de'
    name = f'Clone de {name} 1'
    r = re.compile(r'(.*?)\s+(\w+)$')
    match = r.match(name)
    if match:
        prefix = match.group(1)
        for i in itertools.count(start=1, step=1):
            yield prefix + f' {i}'
    else:
        yield prefix + name


def get_requisicoes_de_assinatura(usuario):
    solicitacoes = SolicitacaoAssinatura.objects.filter_requisicao_pendente(usuario)
    documentos_ids = solicitacoes.all().values_list('documento_id', flat=True)
    return DocumentoTexto.objects.filter(id__in=documentos_ids)


def get_documentos_a_revisar(pessoa):
    solicitacoes = SolicitacaoRevisao.objects.filter_revisao_pendente(pessoa)
    documentos_ids = solicitacoes.all().values_list('documento_id', flat=True)
    return DocumentoTexto.objects.filter(id__in=documentos_ids)


def get_documentos_revisados(usuario):
    revisados = SolicitacaoRevisao.objects.filter_revisados(usuario)
    documentos_ids = revisados.all().values_list('documento_id', flat=True)
    return DocumentoTexto.objects.filter(id__in=documentos_ids)


def get_requisicoes_de_revisao(usuario):
    solicitacoes = SolicitacaoRevisao.objects.filter_requisicao_pendente(usuario)
    documentos_ids = solicitacoes.all().values_list('documento_id', flat=True)
    return DocumentoTexto.objects.filter(id__in=documentos_ids)


def filtar_por_setor(request, setor):
    # Então buscamos o filtro por setor que fica na área html de "class=pills".
    setores_param = request.GET.get('setores')
    # Se não há um filtro por setores, então verificamos se na URL anterior há esse filtro. Se houver, vamos
    # manter esse filtro na próxima requisição. Isso é necessário para que os outros filtros do
    # form ListarDocumentosTextoForm
    # possam ser aplicados em conjunto com esse filtro de setores.
    if not setores_param:
        setores_param = 'todos'
        url_req_anterior = request.META.get('HTTP_REFERER', '').split('?')
        if len(url_req_anterior) == 2:
            params_req_anterior = url_req_anterior[1].split('&')
            for param in params_req_anterior:
                if 'setores' in param:
                    setores_param = param.split('=')[1]
                    break
    #
    try:
        setores_escolhidos = [Setor.objects.suap_ativos().get(pk=(setores_param or setor.id))]
    except ValueError:
        setores_escolhidos = None
    return setores_param, setores_escolhidos


def _get_por_id_ou_uuid[M: Documento](modelo: type[M], id_uuid: int | str | uuid.UUID) -> M:
    """Busca por ``id`` quando o identificador é numérico; senão, por ``uuid``. Formato inválido ou inexistente: 404 (#17854)."""
    identificador = str(id_uuid)
    if identificador.isdecimal():
        return get_object_or_404(modelo, id=int(identificador))
    try:
        valor_uuid = uuid.UUID(identificador)
    except ValueError:
        raise Http404 from None
    return get_object_or_404(modelo, uuid=valor_uuid)


def get_documento_texto(id_uuid: int | str | uuid.UUID) -> DocumentoTexto:
    return _get_por_id_ou_uuid(DocumentoTexto, id_uuid)


def get_documento_digitalizado(id_uuid: int | str | uuid.UUID) -> DocumentoDigitalizado:
    return _get_por_id_ou_uuid(DocumentoDigitalizado, id_uuid)


@rtr()
@permission_required('documento_eletronico.change_documentotexto, documento_eletronico.change_documentotextopessoal')
def editar_documento(request, documento_id, remontar_partes_documento=None):
    documento = get_documento_or_forbidden(request.user, documento_id)

    title = f'Editar {documento}'

    if not documento.pode_editar(request.user):
        raise PermissionDenied

    if remontar_partes_documento == 'remontar_corpo':
        documento.montar_corpo_padrao()

    # Verifcando se o documento em questão tem alguma pendência com relação a hipótese legal. Se tiver, o usuário será
    # conduzido a tela de edição para que forneça a informação.
    # Obs: (1) Isso é necessário por conta de documentos antigos, sigilosos/restritos, criados em data anterior a versão
    # do SUAP que introduziu o cadastro de Hipóteses Legais. (2) Isso evita o erro "DocumentoTextoEditarCorpoForm
    # has no field named hipotese_legal" quando o usuário tenta salvar a modificação do texto e há algo pendente com relação
    # a hipoótese legal.
    try:
        documento.clean_hipotese_legal()
    except Exception as e:
        error_message = (str(e) or ', '.join(e)) + ' Forneça a informação para poder editar o texto.'
        return httprr(f'/admin/documento_eletronico/documentotexto/{documento.id}/change/', error_message, tag='error')

    form_corpo = DocumentoTextoEditarCorpoForm(request.POST or None, instance=documento, request=request)
    if form_corpo.is_valid():
        with transaction.atomic():
            sid = transaction.savepoint()
            try:
                form_corpo.save()
                observacao = ''
                if documento.estah_para_receber_assinatura_balizadora(user_que_deseja_assinar=request.user):
                    observacao = 'antes de assinar ou rejeitar solicitação de assinatura balizadora.'
                #
                registrar_acao_documento_texto(
                    request=request, documento=documento, tipo_acao=RegistroAcaoDocumento.TIPO_EDICAO, observacao=observacao
                )
                transaction.savepoint_commit(sid)
                msg_sucesso = 'Edição realizada com sucesso.'
                if '_salvar_e_concluir' in request.POST:
                    return concluir_documento(request, documento_id)
                elif '_salvar_e_visualizar' in request.POST:
                    return httprr(f'/documento_eletronico/visualizar_documento/{documento.id}/', msg_sucesso)
                else:
                    messages.success(request, msg_sucesso)
            except Exception as e:
                transaction.savepoint_rollback(sid)
                return httprr(f'/documento_eletronico/visualizar_documento/{documento.id}/', str(e), tag='error')

    documento_texto_tamanho_maximo_em_mb = get_documento_texto_tamanho_maximo_em_mb()
    return locals()


@rtr()
@permission_required('documento_eletronico.change_modelodocumento')
def editar_modelo_documento(request, modelo_documento_id):
    modelo_documento = get_object_or_404(ModeloDocumento, pk=modelo_documento_id)
    title = f'Editar Modelo de Documento ({modelo_documento})'
    form = EditarModeloDocumentoForm(request.POST or None, instance=modelo_documento)
    if form.is_valid():
        form.save()
        messages.success(request, 'Atualização realizada com sucesso.')

    return locals()


def _obter_contexto_versao_integral(documento: DocumentoTexto, user: object, eh_anonimo: bool = False) -> dict[str, object]:
    vinculos = VinculoDocumentoTexto.objects.filter(
        documento_texto_referencia__isnull=False,
        documento_texto_alvo=documento,
        documento_texto_base__status=DocumentoStatus.STATUS_FINALIZADO,
    ).select_related('documento_texto_base', 'documento_texto_referencia', 'tipo_vinculo_documento')
    vinculo = vinculos.order_by('-data_criacao').first()
    if not vinculo:
        vinculo = (
            VinculoDocumentoTexto.objects.filter(
                documento_texto_referencia__isnull=False,
                documento_texto_base=documento,
                documento_texto_alvo__status=DocumentoStatus.STATUS_FINALIZADO,
            )
            .select_related('documento_texto_alvo', 'documento_texto_referencia', 'tipo_vinculo_documento')
            .first()
        )
    if not vinculo:
        return {}
    documento_vigente = vinculo.documento_texto_base
    documento_original = vinculo.documento_texto_alvo
    referencia = vinculo.documento_texto_referencia or vinculo.documento_texto_alvo
    if not documento_original.pode_ler(user) or not referencia.pode_ler(user) or not documento_vigente.pode_ler(user):
        return {}
    # O próprio vínculo entra mesmo com o documento relacionado ainda em elaboração: ao abri-lo,
    # a procedência o apresenta como relacionado ao original (issue #17857).
    vinculos_retificacao_qs = VinculoDocumentoTexto.objects.filter(
        Q(documento_texto_base__status=DocumentoStatus.STATUS_FINALIZADO) | Q(pk=vinculo.pk),
        documento_texto_referencia__isnull=False,
        documento_texto_alvo=documento_original,
    )
    if documento.pk != documento_original.pk:
        vinculos_retificacao_qs = vinculos_retificacao_qs.filter(data_criacao__lte=vinculo.data_criacao)

    # Exibe apenas as retificações que o usuário pode visualizar.
    vinculos_retificacao = [
        item
        for item in vinculos_retificacao_qs.select_related('documento_texto_base', 'tipo_vinculo_documento').order_by('data_criacao')
        if item.documento_texto_base.pode_ler(user)
    ]

    corpo_original = _obter_corpo_visualizacao(documento_original, eh_anonimo)
    corpo_referencia = _obter_corpo_visualizacao(referencia, eh_anonimo)
    corpo_vigente = _obter_corpo_visualizacao(documento_vigente, eh_anonimo)
    marcado_corpo = gerar_comparacao_documentos(corpo_referencia, corpo_vigente)
    tipo_vinculo = vinculo.tipo_vinculo_documento
    procedencia_original = _renderizar_procedencia_retificacao(documento_original, documento_vigente, tipo_vinculo, vinculos_retificacao, 'original')
    procedencia_comparativa = _renderizar_procedencia_retificacao(
        documento_original, documento_vigente, tipo_vinculo, vinculos_retificacao, 'comparativa'
    )
    procedencia_compilada = _renderizar_procedencia_retificacao(
        documento_original, documento_vigente, tipo_vinculo, vinculos_retificacao, 'compilada'
    )
    procedencia_retificacao = _renderizar_procedencia_retificacao(
        documento_original, documento_vigente, tipo_vinculo, vinculos_retificacao, 'retificacao'
    )
    assinaturas_original = _renderizar_assinaturas_documento(documento_original, procedencia_original)
    assinaturas_comparativa = _renderizar_assinaturas_documento(documento_vigente, procedencia_comparativa)
    assinaturas_compilada = _renderizar_assinaturas_documento(documento_vigente, procedencia_compilada)
    assinaturas_retificacao = _renderizar_assinaturas_documento(documento_vigente, procedencia_retificacao)
    return {
        'documento_original': documento_original,
        'documento_retificacao': documento_vigente,
        'tipo_vinculo': tipo_vinculo,
        'documento_eh_retificacao': documento.pk == documento_vigente.pk,
        'retificacao_html': preparar_html_documento(
            documento_vigente.cabecalho_para_visualizacao + corpo_vigente + assinaturas_retificacao + documento_vigente.rodape_para_visualizacao
        ),
        'original_html': preparar_html_documento(
            documento_original.cabecalho_para_visualizacao + corpo_original + assinaturas_original + documento_original.rodape_para_visualizacao
        ),
        'marcado_html': preparar_html_documento(
            documento_original.cabecalho_para_visualizacao + marcado_corpo + assinaturas_comparativa + documento_original.rodape_para_visualizacao
        ),
        'compilado_html': preparar_html_documento(
            documento_original.cabecalho_para_visualizacao + corpo_vigente + assinaturas_compilada + documento_original.rodape_para_visualizacao
        ),
    }


def _obter_corpo_visualizacao(documento: DocumentoTexto, eh_anonimo: bool) -> str:
    corpo = documento.corpo_para_visualizacao_anonima if eh_anonimo else documento.corpo_para_visualizacao
    return str(sanitize(corpo, 'processo_eletronico'))


def _eh_visualizacao_anonima(request: HttpRequest) -> bool:
    # Usuários autenticados também podem solicitar a pré-visualização pública pela query string.
    return request.user.is_anonymous or 'forcar_anonimo' in request.GET


def _renderizar_assinaturas_documento(documento: DocumentoTexto, procedencia_html: str = '') -> str:
    codigo_verificador = gerar_codigo_verificador_documento(documento)
    return render_to_string(
        'documento_eletronico/assinaturas_include.html',
        {
            'documento': documento,
            'codigo_verificador': codigo_verificador,
            'procedencia_html': procedencia_html,
        },
    )


def _renderizar_procedencia_retificacao(
    documento_original: DocumentoTexto,
    documento_retificacao: DocumentoTexto,
    tipo_vinculo: TipoVinculoDocumento,
    vinculos_retificacao: list[VinculoDocumentoTexto],
    tipo_versao: str,
) -> str:
    return render_to_string(
        'documento_eletronico/procedencia_retificacao_include.html',
        {
            'documento_original': documento_original,
            'documento_retificacao': documento_retificacao,
            'tipo_vinculo': tipo_vinculo,
            'vinculos_retificacao': vinculos_retificacao,
            'tipo_versao': tipo_versao,
        },
    )


def _pode_criar_documento_relacionado(documento: DocumentoTexto, user: object) -> bool:
    pode_gerenciar = documento.tem_permissao_editar(user) or user.has_perm('documento_eletronico.change_documentotexto')
    return bool(
        documento.estah_finalizado
        and not documento.eh_documento_pessoal
        and user.has_perm('documento_eletronico.add_documentotexto')
        and pode_gerenciar
        and ConfiguracaoVinculoDocumento.objects.filter(ativo=True, tipo_documento_alvo=documento.tipo).exists()
    )


@rtr()
@permission_required('documento_eletronico.view_documentotexto')
def visualizar_documento(request, documento_id):
    documento = get_documento_texto(documento_id)
    if not documento:
        raise Http404

    title = documento.identificador
    user = request.user
    #
    tem_permissao_ler = documento.pode_ler(user=user, verificar_acesso_cargo=False)
    tem_permissao_ler_publico = documento.pode_ler(user=request.user, eh_consulta_publica=True)
    pode_compartilhar_documento = documento.pode_compartilhar(user=user)
    acesso_via_cargo = acesso_ao_documento_em_funcao_cargo(user, documento) if not tem_permissao_ler else False
    pode_ler = tem_permissao_ler or acesso_via_cargo
    forcar_anonimo = 'forcar_anonimo' in request.GET
    if not pode_ler:
        raise PermissionDenied

    app_processo_eletronico_disponivel = app_processo_eletronico_estah_instalada()

    processos_incluido = documento.get_processos(exibir_somente_processos_nos_quais_documento_nao_foi_removido=True)
    pode_criar_processo = user.has_perm('processo_eletronico.add_processo')
    title = documento.identificador
    registar_acesso_documento_texto(request, documento, acesso_via_cargo=acesso_via_cargo)
    # Lista os documentos que foram anexados a este
    pode_receber_anexos = documento.pode_receber_anexos()
    pode_editar_documento = bool(documento.tem_permissao_editar(user))
    documentos_texto_anexados = DocumentoTextoAnexoDocumentoTexto.objects.filter(documento=documento)
    documentos_digitalizado_anexados = DocumentoTextoAnexoDocumentoDigitalizado.objects.filter(documento=documento)

    contexto_versao = _obter_contexto_versao_integral(documento, user, eh_anonimo=forcar_anonimo)
    original_html = contexto_versao.get('original_html')
    marcado_html = contexto_versao.get('marcado_html')
    compilado_html = contexto_versao.get('compilado_html')
    retificacao_html = contexto_versao.get('retificacao_html')
    documento_original_retificacao = contexto_versao.get('documento_original')
    documento_retificacao = contexto_versao.get('documento_retificacao')
    tipo_vinculo_versao = contexto_versao.get('tipo_vinculo')
    documento_eh_retificacao = contexto_versao.get('documento_eh_retificacao', False)
    exibir_retificacao_tabs = bool(contexto_versao)

    pode_criar_documento_relacionado = _pode_criar_documento_relacionado(documento, user)

    pode_assinar_com_gov_br = bool(request.user.is_authenticated and request.session.get('autenticou_com_govbr', False))

    if documento.pode_alterar_nivel_acesso(user):
        existe_solicitacoes_aberto = documento.listar_solicitacoes_nivel_acesso_aberto()

    ocultar_acesso_cargo = not eh_auditor_chefe(user)
    registros_acoes = documento.get_registros_acoes(ocultar_acesso_cargo=ocultar_acesso_cargo)

    action_favoritar = 'add'
    texto_favoritar = 'Adicionar aos Favoritos'
    estah_marcado_favorito = False
    if documento.usuarios_marcadores_favoritos.filter(id=request.user.id).exists():
        # mark_safe: this string intentionally contains HTML (span) to preserve the visually-hidden
        # screen-reader text while rendering it as HTML when debugging or when desired.
        title = mark_safe(f'⭐ {title}<span class="visually-hidden"> - Favoritado</span>')
        estah_marcado_favorito = True
        action_favoritar = 'remove'
        texto_favoritar = 'Remover dos Favoritos'
    return locals()


# TODO: Ideia abortada temporariamente. Precisamos de mais tempo para amadurecer os requisitos dessa
# TODO: tela e ver realmente
# a sua necessidade. Caso mais a frente não seja necessário continuar, apagar o código!
@rtr()
@permission_required('documento_eletronico.view_documentotexto')
def meus_documentos(request):
    title = 'Meus Documentos'

    setor = get_setor(request.user)
    setor_escolhido = request.GET.get('setor', setor.id)

    if setor_escolhido == 'todos':
        setor_escolhido = None
    else:
        setor_escolhido = Setor.objects.suap_ativos().get(pk=setor_escolhido)

    setores_visiveis = get_todos_setores(request.user)

    documentos = DocumentoTexto.objects.proprios(request.user)
    documentos_compartilhados = DocumentoTexto.objects.compartilhados(request.user)

    if setor_escolhido:
        documentos = documentos.filter(setor_dono=setor_escolhido)
        documentos_compartilhados = documentos_compartilhados.filter(setor_dono=setor_escolhido)

    meus_registros_acao_documento_recentes = (
        RegistroAcaoDocumento.objects.filter(documento__registroacaodocumento__user=request.user, documento__id__in=documentos)
        .annotate(max=Max('documento__registroacaodocumento__data'))
        .filter(max=F('data'))
        .select_related('documento')
        .order_by('-data')
    )

    meus_setor_registros_acao_documento_recentes = (
        RegistroAcaoDocumento.objects.filter(documento__id__in=documentos)
        .annotate(max=Max('documento__registroacaodocumento__data'))
        .filter(max=F('data'))
        .select_related('documento')
        .order_by('-data')
    )

    return locals()


def render_documento_restrito(request: HttpRequest, documento: Documento, motivo: str, num_paginas: int | None = None) -> HttpResponse:
    paginas = range(num_paginas or getattr(documento, 'numero_paginas', 1))
    return render(
        request,
        'documento_eletronico/templates/imprimir_documento_restrito.html',
        {
            'documento': documento,
            'motivo_restricao': motivo,
            'paginas': paginas,
            'qrcode_data': getattr(documento, 'qrcode_base64image', None),
            'assinaturas_html': documento.imprimir_assinaturas() if hasattr(documento, 'imprimir_assinaturas') else '',
        },
    )


def get_anexos_do_documento_visiveis(documento: Documento, request: HttpRequest, eh_anonimo: bool) -> list[Documento]:
    anexos_do_documento = []
    for anexo in documento.get_todos_anexos():
        pode_ler_anexo = (
            anexo.documento_anexado.pode_ler(user=request.user, eh_consulta_publica=True)
            if eh_anonimo
            else anexo.documento_anexado.pode_ler(user=request.user)
        )
        if pode_ler_anexo:
            anexos_do_documento.append(anexo.documento_anexado)
    return anexos_do_documento


@rtr()
def conteudo_documento(request: HttpRequest, documento_id: int | str) -> HttpResponse:
    documento = get_documento_texto(documento_id)
    if not documento:
        raise Http404

    app_processo_eletronico_disponivel = app_processo_eletronico_estah_instalada()
    eh_anonimo = request.user.is_anonymous or 'forcar_anonimo' in request.GET

    # ... (código de permissão) ...

    if eh_anonimo:
        try:
            documento_id = uuid.UUID(f'{documento_id}')
        except ValueError:
            motivo = 'Este documento não pode ser visualizado na consulta pública (UUID inválido).'
            return render_documento_restrito(request, documento, motivo, num_paginas=1)
        if not isinstance(documento_id, uuid.UUID):
            motivo = 'Este documento não pode ser visualizado na consulta pública (UUID inválido).'
            return render_documento_restrito(request, documento, motivo, num_paginas=1)
        if not documento.pode_ler(user=request.user, eh_consulta_publica=True):
            motivo = 'Este documento não pode ser visualizado na consulta pública devido ao seu nível de acesso ou restrição de permissão.'
            return render_documento_restrito(request, documento, motivo)
    else:
        if not request.user.has_perm('documento_eletronico.view_documentotexto') or not documento.pode_ler(user=request.user):
            motivo = 'Você não tem permissão para visualizar este documento.'
            return render_documento_restrito(request, documento, motivo)

    try:
        codigo_verificador = gerar_codigo_verificador_documento(documento)
    except TemplateSyntaxError as e:
        return HttpResponse(f'Erro ao tentar processar documento. Por favor verifique as variáveis. Detalhes: {escape(e)}')

    mostrar_anexos = request.GET.get('mostrar_anexos')
    if mostrar_anexos and documento.possui_anexos():
        anexos_do_documento = get_anexos_do_documento_visiveis(documento, request, eh_anonimo)
        return render(request, 'documento_eletronico/templates/conteudo_documento_com_anexos.html', locals())

    return render(request, 'documento_eletronico/templates/conteudo_documento.html', locals())


@permission_required('documento_eletronico.add_documentotexto, documento_eletronico.add_documentotextopessoal')
def modelos_tipo_documento(request, tipo_documento_id):
    tipo_documento = get_object_or_404(TipoDocumentoTexto, pk=tipo_documento_id)
    modelos = tipo_documento.get_modelos_ativos()
    modelos = [{'id': '', 'nome': '---------'}, *list(modelos.values('id', 'nome'))]
    return JsonResponse({'modelos': modelos})


@permission_required('documento_eletronico.add_documentotexto')
def gerar_sugestao_identificador_documento_texto(request, tipo_documento_id, setor_dono_id):
    tipo_documento = get_object_or_404(TipoDocumentoTexto, pk=tipo_documento_id)
    setor_dono = get_object_or_404(Setor, pk=setor_dono_id)

    identificador_tipo_documento_sigla, identificador_numero, identificador_ano, identificador_setor_sigla = (
        tipo_documento.get_sugestao_identificador_definitivo(klass=DocumentoTexto, tipo_documento_texto=tipo_documento, setor_dono=setor_dono)
    )

    return JsonResponse(
        {
            'identificador_tipo_documento_sigla': identificador_tipo_documento_sigla,
            'identificador_numero': identificador_numero,
            'identificador_ano': identificador_ano,
            'identificador_setor_sigla': identificador_setor_sigla,
        }
    )


@permission_required('documento_eletronico.add_documentotexto, documento_eletronico.add_documentotextopessoal')
def nivel_acesso_padrao_classificacoes_modelo_documento(request, modelo_documento_id):
    modelo_documento = get_object_or_404(ModeloDocumento, pk=modelo_documento_id)
    classificacoes = modelo_documento.classificacao.all()

    niveis_acesso_permitidos_keys, niveis_acesso_permitidos_values = modelo_documento.niveis_acesso_permitidos
    niveis_acesso_permitidos = []
    for i in range(len(niveis_acesso_permitidos_keys)):
        niveis_acesso_permitidos.append({'id': niveis_acesso_permitidos_keys[i], 'descricao': niveis_acesso_permitidos_values[i]})

    return JsonResponse(
        {
            'niveis_acesso_permitidos': niveis_acesso_permitidos,
            'nivel_acesso_padrao': modelo_documento.nivel_acesso_padrao,
            'classificacoes': list(classificacoes.values('id', 'codigo', 'descricao')),
        }
    )


@rtr('processo_eletronico/templates/permissoes.html')
@login_required
def gerenciar_compartilhamento_setor(request):
    uc = 'doc'

    # ---------------------------------------
    # Validacoes e Setor escolhido
    # ---------------------------------------
    setor_escolhido, setores_chefe, _, msg_orientacao_acesso, msg_alerta_codigo_protocolo = iniciar_gerenciamento_compartilhamento(request)

    # ---------------------------------------
    # Compartilhamentos de Documentos
    # ---------------------------------------
    title = 'Permissões para Documentos e Processos Eletrônicos'

    form = GerenciarCompartilhamentoSetorForm(request.POST or None, request=request, setor=setor_escolhido)
    form.fieldsets = (
        ('Permissões para Setores:', {'fields': ('setores_permitidos_podem_ler', 'setores_permitidos_podem_escrever')}),
        (
            'Permissões para Servidores/Prestadores de Serviço:',
            {'fields': ('pessoas_permitidas_podem_ler', 'pessoas_permitidas_podem_escrever')},
        ),
    )

    if form.is_valid():
        form.save()
        messages.success(request, 'Operação realizada com sucesso.')

    return locals()


@permission_required('documento_eletronico.add_documentotexto, documento_eletronico.add_documentotextopessoal')
def get_hipoteses_legais_by_documento_nivel_acesso(request, documento_nivel_acesso_id):
    documento_nivel_acesso_id = int(documento_nivel_acesso_id)
    nivel_acesso = None
    if documento_nivel_acesso_id == Documento.NIVEL_ACESSO_SIGILOSO:
        nivel_acesso = NivelAcesso.SIGILOSO
    elif documento_nivel_acesso_id == Documento.NIVEL_ACESSO_RESTRITO:
        nivel_acesso = NivelAcesso.RESTRITO

    hipoteses_legais = []
    if nivel_acesso:
        # Este for está sendo feito para poder obter a descrição da Hipótese Legal de acordo com o que está sendo definido
        # no respectivo método __str__.
        for hl in HipoteseLegal.objects.filter(nivel_acesso=nivel_acesso.name):
            hipoteses_legais.append({'id': hl.id, 'descricao': str(hl)})

    return JsonResponse({'hipoteses_legais': [{'id': '', 'descricao': '---------'}, *hipoteses_legais]})


@rtr()
@permission_required('documento_eletronico.change_documentotexto')
def gerenciar_favoritos(request: HttpRequest, documento_id: int, operacao: str) -> HttpResponse | dict[str, object]:
    documento_texto = get_object_or_404(DocumentoTexto, pk=documento_id)
    user = request.user
    if not documento_texto.pode_ler(user):
        raise PermissionDenied

    url = request.META.get('HTTP_REFERER')
    if operacao == 'add':
        if not documento_texto.estah_marcado_como_favorito(user):
            documento_texto.usuarios_marcadores_favoritos.add(user)
            return httprr(url, 'Documento adicionado aos seus favoritos.')
        else:
            return httprr(url, 'Documento já pertence aos seus favoritos.')

    elif operacao == 'remove':
        if documento_texto.estah_marcado_como_favorito(user):
            documento_texto.usuarios_marcadores_favoritos.remove(user)
            return httprr(url, 'Documento removido dos seus favoritos.')
        else:
            return httprr(url, 'Documento não pertence aos seus favoritos.')

    return locals()


@rtr()
@permission_required('documento_eletronico.change_documentotexto, documento_eletronico.change_documentotextopessoal')
def gerenciar_compartilhamento_documento(request, documento_id):
    title = 'Gerenciamento de Compartilhamento de Documento'

    documento = get_documento_or_forbidden(request.user, documento_id)

    if not documento.pode_compartilhar():
        raise PermissionDenied

    form = GerenciarCompartilhamentoDocumentoForm(request.POST or None, request=request, documento=documento)
    if form.is_valid():
        form.save()
        return httprr('..', 'Gerenciamento salvo com sucesso.')

    # Setores e pessoas que podem ler/escrever no documento
    compartilhamentos_documento_pessoa_ler = documento.compartilhamento_pessoa_documento.filter(nivel_permissao=NivelPermissao.LER)
    compartilhamentos_documento_pessoa_editar = documento.compartilhamento_pessoa_documento.filter(nivel_permissao=NivelPermissao.EDITAR)
    return locals()


def visualizar_documento_digitalizado(request, documento_id):
    if request.user.is_anonymous and str(documento_id).isdigit():
        return httprr('/', 'Autentique no SUAP para poder visualizar esse documento através de seu identificador.')
    documento = get_documento_digitalizado(documento_id)

    eh_anonimo = request.user.is_anonymous
    if eh_anonimo:
        if not documento.pode_ler(user=request.user, eh_consulta_publica=True):
            motivo = 'Este documento não pode ser visualizado na consulta pública devido ao seu nível de acesso ou restrição de permissão.'
            num_paginas = getattr(documento, 'numero_paginas', 1)
            return render(
                request,
                'documento_eletronico/templates/imprimir_documento_restrito.html',
                {
                    'documento': documento,
                    'motivo_restricao': motivo,
                    'paginas': range(num_paginas),
                },
            )
    else:
        if not documento.pode_ler(user=request.user):
            motivo = 'Você não tem permissão para visualizar este documento.'
            num_paginas = getattr(documento, 'numero_paginas', 1)
            return render(
                request,
                'documento_eletronico/templates/imprimir_documento_restrito.html',
                {
                    'documento': documento,
                    'motivo_restricao': motivo,
                    'paginas': range(num_paginas),
                },
            )

    if documento.arquivo.name.split('.')[-1] == 'html':
        return imprimir_pdf(documento.arquivo.open('r'), documento)

    # TODO Registrar Ação
    try:
        if request.GET.get('original') and request.GET.get('original') == 'sim':
            # Arquivos de media. Ex: private-media/processo_eletronico/diac/zl/0d04cdb93b43e359973ac28.mov.pdf
            if documento.arquivo.name.split('.')[-2] in settings.CONTENT_TYPES:
                return FileResponse(open(documento.arquivo.path[0:-4], 'rb'))
            response = FileResponse(documento.arquivo.open('rb'), content_type='application/pdf')
        else:
            pdf = documento.get_pdf(user=request.user, eh_consulta_publica=eh_anonimo)
            response = HttpResponse(pdf, content_type='application/pdf')
            response['Content-Disposition'] = 'inline; filename=documento.pdf'
    except OSError as e:
        if settings.DEBUG:
            raise e
        return httprr('/', 'Falha ao tentar visualizar documento digitalizado, por favor tente novamente.', 'error')
    except Exception as e:
        return httprr('/', str(e), 'error')
    return response


@method_decorator(login_required, name='dispatch')
class AssinarDocumentoSenhaWizard(SessionWizardView):
    form_list = [GeradorIdentificadorDocumentoForm, AssinarDocumentoForm]
    template_name = 'documento_eletronico/assinatura_senha.html'

    def get_context_data(self, form, **kwargs):
        context = super().get_context_data(form, **kwargs)

        solicitacao_assinatura_com_anexacao_processo = self.documento.get_solicitacao_assinatura_com_anexacao_processo()
        if (
            solicitacao_assinatura_com_anexacao_processo
            and solicitacao_assinatura_com_anexacao_processo.solicitacao_assinatura.solicitado == self.request.user.get_profile()
        ):
            context['processo_para_anexar'] = solicitacao_assinatura_com_anexacao_processo.processo_para_anexar

        context['documento'] = self.documento
        return context

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def dispatch(self, request, *args, **kwargs):
        self.documento_id = kwargs.get('documento_id')
        self.documento = get_documento_or_forbidden(self.request.user, self.documento_id)
        try:
            self.exibir_tela_para_gerar_identificador = self.documento.estah_para_receber_assinatura_balizadora(request.user)
        except ValidationError as e:
            return httprr('/', str(e), 'error')

        if not self.exibir_tela_para_gerar_identificador:
            self.form_list = {'0': AssinarDocumentoForm}
            try:
                del request.session['wizard_assinar_documento_senha_wizard']
            except Exception:
                pass
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self, step=None):
        kwargs = super().get_form_kwargs(step)
        kwargs.update({'request': self.request})
        if step is None or step == '0' and self.exibir_tela_para_gerar_identificador:
            kwargs.update({'documento_id': self.documento_id})
        return kwargs

    def render(self, form=None, **kwargs):
        documento = get_documento_or_forbidden(self.request.user, self.documento_id)
        if not documento.pode_assinar(self.request.user):
            raise PermissionDenied
        return super().render(form, **kwargs)

    def done(self, form_list, **kwargs):
        documento = get_documento_or_forbidden(self.request.user, self.documento_id)
        if not documento.pode_assinar(self.request.user):
            raise PermissionDenied

        for form in form_list:
            if not form.is_valid():
                raise Exception('Os dados submetidos estão incorretos.')

        with transaction.atomic():
            sid = transaction.savepoint()
            try:
                cleaned_data = self.get_all_cleaned_data()
                papel = form.cleaned_data.get('papel')

                # Caso o documento ainda não tenha identificador, ele será atribuído nesse momento e o conteúdo
                # (cabeçalho, corpo e rodapé) processados.
                data_emissao = get_datetime_now()
                if self.exibir_tela_para_gerar_identificador and not documento.tem_identificador_definitivo:
                    identificador_tipo_documento_sigla, identificador_numero, identificador_ano, identificador_setor_sigla = (
                        documento.get_sugestao_identificador_definitivo(
                            tipo_documento_texto=documento.modelo.tipo_documento_texto, setor_dono=documento.setor_dono
                        )
                    )
                    if identificador_tipo_documento_sigla != cleaned_data['identificador_tipo_documento_sigla']:
                        raise ValidationError('Tipo de documento escolhido incompatível.')
                    if identificador_numero != cleaned_data['identificador_numero']:
                        raise ValidationError('Número do documento escolhido incompatível.')

                    if documento.usa_sequencial_anual and identificador_ano and (identificador_ano != cleaned_data['identificador_ano']):
                        raise ValidationError('Ano do documento escolhido incompatível.')
                    if identificador_setor_sigla != cleaned_data['identificador_setor_sigla']:
                        raise ValidationError('Setor do documento escolhido incompatível.')

                    documento.atribuir_identificador_e_processar_conteudo_final(
                        identificador_tipo_documento_sigla=identificador_tipo_documento_sigla,
                        identificador_numero=identificador_numero,
                        identificador_ano=identificador_ano,
                        identificador_setor_sigla=identificador_setor_sigla,
                        identificador_dono_documento=None,
                        data_emissao=data_emissao,
                    )
                    documento.save()

                # Assinar o documento
                documento.assinar_via_senha(self.request.user, papel, data_emissao)

                # Registrar ação
                msg = f'Documento assinado por {self.request.user}'
                registrar_acao_documento_texto(self.request, documento, RegistroAcaoDocumento.TIPO_ASSINATURA, msg)

                target = reverse_lazy('visualizar_documento', kwargs={'documento_id': self.documento_id}, current_app='documento_eletronico')
                transaction.savepoint_commit(sid)

                # Notificação_email Demanda_495
                solicitacao = documento.get_solicitacao_balizadora()
                if solicitacao.solicitado == self.request.user.get_profile():
                    solicitacoes_dependentes = solicitacao.get_solicitacoes_dependentes()
                    if solicitacoes_dependentes:
                        Notificar.solicitacao_assinatura_condicionantes(solicitacoes_dependentes, documento)
                if documento.pode_notificar_conclusao_assinaturas():
                    Notificar.solicitacao_assinatura_concluida(solicitacao, documento)
                return httprr(target, 'Documento assinado com sucesso.')
            except Exception as e:
                transaction.savepoint_rollback(sid)
                error_message = e or ', '.join(e)
                return httprr('.', message=error_message, tag='error')


@method_decorator(login_required, name='dispatch')
class AssinarDocumentoLoteFormView(FormView):
    form_class = AssinarDocumentoForm
    template_name = 'default.html'

    def get_context_data(self, *args, **kwargs):
        context = super().get_context_data(*args, **kwargs)
        context.update(h1='Assinar Documentos em Lote')
        return context

    def form_valid(self, form: AssinarDocumentoForm) -> HttpResponse:
        assinados = 0
        for documento in DocumentoTexto.objects.filter(id__in=ids_da_query(self.request, sep='-')):
            try:
                get_documento_or_forbidden(self.request.user, documento.id)
            except PermissionDenied:
                continue
            if not documento.pode_assinar(self.request.user):
                continue
            # Cada documento é atômico: o que a regra de negócio barrar fica sem assinatura e o lote segue (#17817).
            try:
                with transaction.atomic():
                    self._assinar(documento, form.cleaned_data['papel'])
                assinados += 1
            except ValidationError as e:
                messages.error(self.request, f'{documento}: {"; ".join(e.messages)}')
        return httprr('/admin/documento_eletronico/documentotexto/?opcao=1', 'Documentos assinados com sucesso' if assinados else '')

    def _assinar(self, documento: DocumentoTexto, papel: object) -> None:
        data_emissao = get_datetime_now()
        if not documento.tem_identificador_definitivo:
            identificador_tipo_documento_sigla, identificador_numero, identificador_ano, identificador_setor_sigla = (
                documento.get_sugestao_identificador_definitivo(
                    tipo_documento_texto=documento.modelo.tipo_documento_texto, setor_dono=documento.setor_dono
                )
            )

            documento.atribuir_identificador_e_processar_conteudo_final(
                identificador_tipo_documento_sigla=identificador_tipo_documento_sigla,
                identificador_numero=identificador_numero,
                identificador_ano=identificador_ano,
                identificador_setor_sigla=identificador_setor_sigla,
                identificador_dono_documento=None,
                data_emissao=data_emissao,
            )
            documento.save()
        # Assinar o documento
        documento.assinar_via_senha(self.request.user, papel, data_emissao)
        # Registrar ação
        msg = f'Documento assinado por {self.request.user}'
        registrar_acao_documento_texto(self.request, documento, RegistroAcaoDocumento.TIPO_ASSINATURA, msg)
        # Notificação_email Demanda_495
        solicitacao = documento.get_solicitacao_balizadora()
        if solicitacao.solicitado == self.request.user.get_profile():
            solicitacoes_dependentes = solicitacao.get_solicitacoes_dependentes()
            if solicitacoes_dependentes:
                Notificar.solicitacao_assinatura_condicionantes(solicitacoes_dependentes, documento)
        if documento.pode_notificar_conclusao_assinaturas():
            Notificar.solicitacao_assinatura_concluida(solicitacao, documento)


@rtr()
@permission_required('documento_eletronico.change_documentotexto')
def revisar_documento(request, documento_id):
    documento = get_object_or_404(DocumentoTexto, pk=documento_id)
    if not documento.sou_revisor(request.user):
        raise PermissionDenied
    title = 'Revisão de Documento'

    form = RevisarDocumentoForm(request.POST or None)
    if form.is_valid():
        notas_revisor = form.cleaned_data.get('notas_revisor')
        solicitacao = SolicitacaoRevisao.objects.filter(
            documento_id=documento_id, revisor=request.user.get_vinculo(), data_resposta__isnull=True
        ).first()
        #
        if solicitacao:
            try:
                solicitacao.deferir_solicitacao()
                solicitacao.data_resposta = get_datetime_now()
                solicitacao.notas_revisor = notas_revisor
                solicitacao.save()
                #
                compartilhamento = CompartilhamentoDocumentoPessoa.objects.filter(
                    vinculo_permitido=solicitacao.revisor,
                    documento=documento,
                    nivel_permissao=NivelPermissao.EDITAR,
                    tipo_permissao=TipoPermissao.REVISAO,
                ).first()
                #
                if compartilhamento:
                    compartilhamento.delete()
                #
                RegistroAcaoDocumentoTexto.objects.create(
                    tipo=RegistroAcaoDocumento.TIPO_REVISADO, documento=documento, ip=request.META.get('REMOTE_ADDR', ''), observacao=notas_revisor
                )
            except Exception:
                raise PermissionDenied
            #
            app_label = documento._meta.app_label
            model_name = documento._meta.model_name
            if documento.pode_ler(request.user):
                url = reverse_lazy('visualizar_documento', kwargs={'documento_id': documento_id}, current_app='documento_eletronico')
            else:
                url = documento.get_documentos_url()
            return httprr(url, 'Revisão de documento realizada com sucesso.')
        else:
            raise PermissionDenied
    else:
        return locals()


@permission_required('documento_eletronico.change_documentotexto')
@transaction.atomic()
def cancelar_revisao(request, documento_id):
    documento = get_object_or_404(DocumentoTexto, pk=documento_id)
    if documento.pode_cancelar_revisao():
        solicitacao = (
            SolicitacaoRevisao.objects.filter(documento_id=documento_id, data_resposta__isnull=True)
            .filter(Q(solicitante=request.user) | Q(revisor=request.user.get_vinculo()))
            .first()
        )
        if solicitacao:
            documento.cancelar_revisao()
            documento.save()
            solicitacao.delete()
            compartilhamento = CompartilhamentoDocumentoPessoa.objects.filter(
                vinculo_permitido=solicitacao.revisor,
                documento=documento,
                nivel_permissao=NivelPermissao.EDITAR,
                tipo_permissao=TipoPermissao.REVISAO,
            ).first()
            if compartilhamento:
                compartilhamento.delete()

            RegistroAcaoDocumentoTexto.objects.create(
                tipo=RegistroAcaoDocumento.TIPO_CANCELAR_REVISAO,
                documento=documento,
                ip=request.META.get('REMOTE_ADDR', ''),
                observacao=f'Revisão cancelada por {request.user}.',
            )

            if documento.pode_ler(request.user):
                url = reverse_lazy('visualizar_documento', kwargs={'documento_id': documento_id}, current_app='documento_eletronico')
            else:
                url = documento.get_documentos_url()

            Notificar.cancelamento_revisao(solicitacao.revisor, documento)
            return httprr(url, 'Revisão cancelada com sucesso.')
    raise PermissionDenied


@rtr()
@permission_required('documento_eletronico.change_documentotexto')
def solicitar_revisao(request, documento_id):
    documento = get_object_or_404(DocumentoTexto, pk=documento_id)
    if not documento.pode_solicitar_revisao(request.user):
        raise PermissionDenied
    title = 'Solicitação de Revisão'
    form = SolicitacaoRevisaoForm(request.POST or None)
    if form.is_valid():
        revisor = form.cleaned_data.get('revisor')
        obs = form.cleaned_data.get('observacao')

        with transaction.atomic():
            # Caso seja necessário adiciona permissão de edicao para
            # o revisor.
            if not documento.tem_permissao_editar(revisor.user):
                solicitacao, created = CompartilhamentoDocumentoPessoa.objects.get_or_create(
                    vinculo_permitido=revisor, documento=documento, nivel_permissao=NivelPermissao.EDITAR, tipo_permissao=TipoPermissao.REVISAO
                )
            SolicitacaoRevisao.objects.get_or_create(
                documento_id=documento_id, revisor=revisor, solicitante=request.user, data_resposta__isnull=True, defaults={'observacao': obs}
            )
            RegistroAcaoDocumentoTexto.objects.create(
                tipo=RegistroAcaoDocumento.TIPO_SOLICITAR_REVISAO,
                documento=documento,
                ip=request.META.get('REMOTE_ADDR', ''),
                observacao=f'{revisor.user}:{obs}',
            )
            documento.colocar_em_revisao()
            documento.save()

        Notificar.solicitacao_revisao(revisor, documento)
        return httprr('..', f'O documento foi enviado a {revisor.user} para revisão.')

    return locals()


@rtr('documento_eletronico/solicitar_assinatura.html')
@permission_required('documento_eletronico.change_documentotexto, documento_eletronico.change_documentotextopessoal')
@login_required
def solicitar_assinatura(request, documento_id):
    documento = get_documento_or_forbidden(request.user, documento_id)
    if not documento.pode_solicitar_assinatura(request.user):
        raise PermissionDenied

    title = 'Solicitações de Assinaturas'
    preencher_solicitacao_assinaturas_form = SolicitacaoAssinaturaEmLoteForm(request.GET or None)
    solicitados = []
    nao_processados = []
    mostrar_formulario_preencher_lote = '' if preencher_solicitacao_assinaturas_form.is_bound else 'collapsed'
    vinculos = Vinculo.objects.assinadores()
    main_form = SolicitacaoAssinaturaForm(request.POST or None, request=request, documento=documento)
    formset = SolicitacaoComplementaresFormSet(request.POST or None, form_kwargs={'request': request, 'documento': documento})

    if preencher_solicitacao_assinaturas_form.is_valid():
        metodo_busca = preencher_solicitacao_assinaturas_form.cleaned_data.get('metodo_busca')
        solicitados_raw = preencher_solicitacao_assinaturas_form.cleaned_data.get('solicitados').strip()

        if solicitados_raw and metodo_busca:
            solicitados = [s for s in re.split(r'[,\s;]+', solicitados_raw) if s]
            if len(solicitados) > 50:
                nao_processados = ', '.join(solicitados[50:])
                solicitados = solicitados[:50]
            if metodo_busca == 'matricula':
                when_statements = [When(user__username=username, then=Value(index)) for index, username in enumerate(solicitados, start=1)]
                vinculos = vinculos.filter(user__username__in=solicitados)

            elif metodo_busca == 'email_academico':
                # Subqueries para cada tipo de relacionamento
                from comum.models import PrestadorServico
                from edu.models import Aluno
                from rh.models import Servidor

                servidor_ct = ContentType.objects.get_for_model(Servidor)
                prestador_ct = ContentType.objects.get_for_model(PrestadorServico)
                aluno_ct = ContentType.objects.get_for_model(Aluno)

                def sub_email(model):
                    return Subquery(model.objects.filter(pk=OuterRef('id_relacionamento')).values('email_academico')[:1])

                vinculos = vinculos.annotate(
                    email_academico=Case(
                        When(tipo_relacionamento=servidor_ct, then=sub_email(Servidor)),
                        When(tipo_relacionamento=prestador_ct, then=sub_email(PrestadorServico)),
                        When(tipo_relacionamento=aluno_ct, then=sub_email(Aluno)),
                        default=Value(''),
                        output_field=CharField(),
                    )
                )

                when_statements = [When(email_academico=email, then=Value(index)) for index, email in enumerate(solicitados, start=1)]
                vinculos = vinculos.filter(email_academico__in=solicitados)

            # Ordenar por prioridade dos solicitados
            vinculos = vinculos.annotate(custom_order=Case(*when_statements, default=Value(0), output_field=IntegerField())).order_by('custom_order')

            initial = {'solicitado': vinculos[0]} if vinculos else None
            possui_assinatura__ou_solicitacao_de_assinatura_balizadora = documento.tem_assinatura_ou_solicitacao_assinatura_balizadora()
            if not possui_assinatura__ou_solicitacao_de_assinatura_balizadora:
                main_form = SolicitacaoAssinaturaForm(request.POST or None, request=request, documento=documento, initial=initial)
                if len(vinculos) > 1:
                    formset = SolicitacaoComplementaresFormSet(
                        request.POST or None,
                        form_kwargs={'request': request, 'documento': documento},
                        initial=[{'solicitado': vinculo, 'ordem': 1} for vinculo in vinculos[1:]],
                    )
            else:
                main_form = SolicitacaoAssinaturaForm(
                    request.POST or None,
                    request=request,
                    documento=documento,
                )

                formset = SolicitacaoComplementaresFormSet(
                    request.POST or None,
                    form_kwargs={'request': request, 'documento': documento},
                    initial=[{'solicitado': vinculo, 'ordem': 1} for vinculo in vinculos],
                )

    outras_solicitacoes_complementares = SolicitacaoAssinatura.objects.filter(documento=documento).distinct()

    try:
        with transaction.atomic():
            if main_form.is_valid() and formset.is_valid():
                solicitado = main_form.cleaned_data.get('solicitado')
                if solicitado and solicitado.eh_aluno():
                    aluno = solicitado.user.get_relacionamento()
                    aluno.criar_papel_discente()

                root = get_or_create_balizadora(request.user, solicitado, documento)
                solicitacoes = {}

                for solicitacao_complementar in outras_solicitacoes_complementares.exclude(condicionantes__isnull=True):
                    ordem = solicitacao_complementar.ordem_assinatura()
                    solicitacoes.setdefault(ordem, []).append(solicitacao_complementar)

                for form in formset:
                    if form.is_valid():
                        solicitado = form.cleaned_data.get('solicitado')
                        ordem = int(form.cleaned_data.get('ordem', 1))
                        if solicitado:
                            if solicitado.eh_aluno():
                                aluno = solicitado.user.get_relacionamento()
                                aluno.criar_papel_discente()
                            solicitacao, created = get_or_create_solicitacao(request.user, solicitado, documento, True)
                            if created:
                                solicitacoes.setdefault(ordem, []).append(solicitacao)

                if solicitacoes:
                    construir_ligacoes_entre_solicitacoes(solicitacoes, root)

                url = reverse_lazy('visualizar_documento', kwargs={'documento_id': documento_id}, current_app='documento_eletronico')
                Notificar.solicitacao_assinatura(main_form.cleaned_data.get('solicitado'), documento)
                return httprr(url, 'Sua solicitação foi enviada com sucesso.')

    except Exception as e:
        raise e

    return locals()


@rtr('documento_eletronico/solicitar_assinatura_com_anexacao.html')
@permission_required('documento_eletronico.change_documentotexto')
def solicitar_assinatura_com_anexacao(request, documento_id):
    documento = get_documento_or_forbidden(request.user, documento_id)
    # Se for documento pessoal não pode solicitar assinatura com anexação
    # - Para solicitar é necessário que o documento não tenha documento.tem_identificador_definitivo
    # - Todos os documentos pessoais devem ser assinadaos pelo seu criador (solicitação de lobão na demanda 1078/1068)
    # - Para que o documento não seja corra o rsico de ser adicionado ao processo sem assinatura do seu criador
    # - Não se pode solicitar assinatura para si mesmo
    # - Não existe um "pode_solicitar_assinatura_com_anexacao" e por isso Essa rotina está aqui
    # Conclusão: não pode solicitar assinatura com anexação
    if documento.eh_documento_pessoal or not documento.pode_solicitar_assinatura(request.user):
        raise PermissionDenied

    if not get_setor(request.user):
        return httprr(documento.get_absolute_url(), 'O usuário não possui nenhum setor associado.', 'error')

    title = 'Solicitações de Assinaturas com Posterior Anexação ao Processo'
    formset = SolicitacaoComplementaresComAnexacaoFormSet(request.POST or None, form_kwargs={'request': request, 'documento': documento})
    main_form = SolicitacaoAssinaturaComAnexacaoForm(request.POST or None, request=request, documento=documento)
    try:
        with transaction.atomic():
            if main_form.is_valid() and formset.is_valid():
                from processo_eletronico.models import SolicitacaoAssinaturaComAnexacaoProcesso
                from processo_eletronico.views import verifica_pode_editar_processo

                verifica_pode_editar_processo(main_form.cleaned_data['processo_para_anexar'])
                solicitado = main_form.cleaned_data.get('solicitado')
                if solicitado and solicitado.eh_aluno():
                    aluno = solicitado.user.get_relacionamento()
                    aluno.criar_papel_discente()
                # Passo 1 - Criar ou recuperar a solicitação balizadora
                root = get_or_create_balizadora(request.user, solicitado, documento)
                solicitar_assinatura = get_or_create_balizadora(request.user, solicitado, documento)
                solicitar_assinatura_com_anexacao_para_processo = SolicitacaoAssinaturaComAnexacaoProcesso.objects.create(
                    solicitacao_assinatura=solicitar_assinatura,
                    processo_para_anexar=main_form.cleaned_data['processo_para_anexar'],
                    destinatario_setor_tramite=main_form.get_destino(),
                    papel_solicitante=main_form.cleaned_data['papel'],
                    despacho_corpo=main_form.cleaned_data['despacho_corpo'],
                    # Essa opção só vai existir se a configuração do SUAP estiver habilitada para permitir
                    # ao remetente fazer a distribuição do processo no ato do encaminhamento do processo.
                    # Por isso usamos o "get"!
                    vinculo_para_distribuir=main_form.cleaned_data.get('vinculo_para_distribuir'),
                )
                url = reverse_lazy('visualizar_documento', kwargs={'documento_id': documento_id}, current_app='documento_eletronico')

                solicitacoes = {}
                for form in formset:
                    solicitado = form.cleaned_data.get('solicitado', None)
                    solicitados = []
                    solicitados.append(solicitado)
                    ordem_solicitacao = int(form.cleaned_data.get('ordem', 1))
                    if form.is_valid() and solicitado:
                        if solicitado.eh_aluno():
                            aluno = solicitado.user.get_relacionamento()
                            aluno.criar_papel_discente()
                        solicitacao, created = get_or_create_solicitacao(request.user, solicitado, documento, True)
                        if not created:
                            continue
                        if ordem_solicitacao in solicitacoes:
                            solicitacoes[ordem_solicitacao].append(solicitacao)
                        else:
                            solicitacoes[ordem_solicitacao] = [solicitacao]
                # Se eu adicionei alguma solicitação condicionada então anota ai
                if list(solicitacoes.keys()):
                    construir_ligacoes_entre_solicitacoes(solicitacoes, solicitar_assinatura)

                url = reverse_lazy('visualizar_documento', kwargs={'documento_id': documento_id}, current_app='documento_eletronico')
                Notificar.solicitacao_assinatura(main_form.cleaned_data.get('solicitado'), documento)
                return httprr(url, 'Sua solicitação foi enviada com sucesso.')
            return locals()
    except PermissionDenied:
        msg = 'O processo não permite alterações no momento ou você não possui permissão para essa operação.'
        return httprr('.', message=msg, tag='error')
    except Exception as e:
        return httprr('.', message=str(e), tag='error')


@permission_required('documento_eletronico.change_documentotexto, documento_eletronico.change_documentotextopessoal')
def concluir_documento(request, documento_id):
    documento = get_documento_texto(documento_id)
    if not documento:
        raise Http404
    if not documento.pode_concluir_documento(request.user):
        raise PermissionDenied
    match = reverse_lazy('visualizar_documento', kwargs={'documento_id': documento_id}, current_app='documento_eletronico')
    try:
        with transaction.atomic(), reversion.create_revision():
            deve_adicionar_avaliacao_revisao = (
                not documento.eh_documento_pessoal and documento.pode_rejeitar_revisao(request.user) and documento.estah_em_revisado
            )

            documento.concluir()
            documento.save()
            if deve_adicionar_avaliacao_revisao:
                solicitacao_revisao = documento.get_ultima_solicitacao_revisao_sem_avaliacao()
                solicitacao_revisao.adicionar_avaliacao_deferida(request.user)
                registrar_acao_documento_texto(
                    request, documento, RegistroAcaoDocumento.TIPO_AVALIACAO_REVISAO, solicitacao_revisao.get_status_avaliacao()
                )
            documento.indexar_conteudo()
        return httprr(match, 'Operação realizada com sucesso.')
    except Exception as error:
        error_message = '; '.join(error)
        return httprr(match, message=error_message, tag='error')


@permission_required('documento_eletronico.change_documentotexto')
@rtr()
def cancelar_documento(request, documento_id):
    documento = get_documento_or_forbidden(request.user, documento_id)
    title = documento.identificador
    #
    match = reverse_lazy('visualizar_documento', kwargs={'documento_id': documento_id}, current_app='documento_eletronico')
    if not documento.pode_ser_cancelado(request.user):
        if documento.status == DocumentoStatus.STATUS_FINALIZADO:
            return httprr(match, 'O documento não pode ser cancelado, pois está sendo usado por algum processo.', tag='error')
        else:
            return httprr(match, 'O documento não pode ser cancelado.', tag='error')
    #
    form = CancelarDocumentoForm(request.POST or None, instance=documento)
    if form.is_valid():
        try:
            form.save()
            registrar_acao_documento_texto(request, documento, RegistroAcaoDocumento.TIPO_CANCELAR_DOCUMENTO, documento.justificativa_cancelamento)
            #
            return httprr(match, 'Operação realizada com sucesso.')
        except Exception:
            raise PermissionDenied
    return locals()


@permission_required('documento_eletronico.change_documentotexto, documento_eletronico.change_documentotextopessoal')
def retornar_para_rascunho(request, documento_id):
    documento = get_documento_or_forbidden(request.user, documento_id)
    if documento.pode_retornar_para_rascunho(request.user):
        url = reverse_lazy('visualizar_documento', kwargs={'documento_id': documento_id}, current_app='documento_eletronico')
        with transaction.atomic(), reversion.create_revision():
            documento.editar_documento()
            documento.save()
        return httprr(url, 'Operação realizada com sucesso.')
    raise PermissionDenied


@rtr()
@permission_required('documento_eletronico.view_documentotexto')
def visualizar_variaveis(request):
    title = 'Visualização de Variáveis'
    variaveis = get_variaveis(documento_identificador='MEMO 1/2017 - COSINF/DIGTI/RE/IFRN', to_dict=False)
    return locals()


# Não há a notação @login_required porque a página pode ser acessada pelo público externo para conferência de documento
# público.


def get_context(request, documento_id, orientacao):
    documento = get_documento_or_forbidden(request.user, documento_id)

    # Código adicionado para tratar a exibição quando o documento for autenticado
    # Se for um usuário não autenticado só mostra o documento se vinher junto o hash
    leitura_para_barramento = False
    consulta_publica_hash = None
    if request.user.is_anonymous:
        consulta_publica_hash = request.GET.get('hash')
        leitura_para_barramento = True
        if documento.hash_conteudo != consulta_publica_hash:
            raise PermissionDenied('Você não tem permissão de visualizar o documento.')
    elif not request.user.has_perm('documento_eletronico.view_documentotexto'):
        raise PermissionDenied('Você não tem permissão de visualizar o documento.')

    if orientacao == 'paisagem':
        orientacao = 'landscape'
    else:
        orientacao = 'portrait'

    eh_consulta_publica = False
    if consulta_publica_hash:
        eh_consulta_publica = True
    return documento, consulta_publica_hash, leitura_para_barramento, eh_consulta_publica, orientacao


def imprimir_documento_pdf(request: HttpRequest, documento_id: int, orientacao: str | None = None) -> HttpResponse:
    documento, consulta_publica_hash, leitura_para_barramento, eh_consulta_publica, orientacao = get_context(request, documento_id, orientacao)

    versao = request.GET.get('retificacao')
    if versao:
        # A impressão deve aplicar a mesma anonimização da visualização HTML,
        # inclusive na consulta pública feita por usuário não autenticado.
        contexto_versao = _obter_contexto_versao_integral(
            documento,
            request.user,
            eh_anonimo=_eh_visualizacao_anonima(request),
        )
        chave_html = {
            'documento': 'retificacao_html',
            'original': 'original_html',
            'marcado': 'marcado_html',
            'compilado': 'compilado_html',
        }.get(versao)
        if not chave_html or not contexto_versao or (versao == 'documento' and not contexto_versao['documento_eh_retificacao']):
            raise PermissionDenied
        documento_impresso = contexto_versao['documento_retificacao'] if versao == 'documento' else contexto_versao['documento_original']
        registrar_acao_documento_texto(request, documento_impresso, RegistroAcaoDocumento.TIPO_IMPRESSAO)
        return tasks.imprimir_versao_pdf(request, str(contexto_versao[chave_html]), orientacao)

    registrar_acao_documento_texto(request, documento, RegistroAcaoDocumento.TIPO_IMPRESSAO)
    return tasks.imprimir_pdf(request, documento, consulta_publica_hash, leitura_para_barramento, eh_consulta_publica, orientacao)


@permission_required('documento_eletronico.view_documentotexto')
def exportar_pdfa(request, documento_id, orientacao=None):
    documento, consulta_publica_hash, leitura_para_barramento, eh_consulta_publica, orientacao = get_context(request, documento_id, orientacao)

    registrar_acao_documento_texto(request, documento, RegistroAcaoDocumento.TIPO_IMPRESSAO)
    return tasks.imprimir_pdfa(request, documento, consulta_publica_hash, leitura_para_barramento, eh_consulta_publica, orientacao)


@rtr()
def autenticar_documento(request):
    title = 'Autenticar Documento'
    codigo_autenticacao = request.GET.get('codigo_autenticacao')
    codigo_verificador = request.GET.get('codigo_verificador')
    form = AutenticacaoDocumentoTexto(request.POST or None, codigo_autenticacao=codigo_autenticacao, codigo_verificador=codigo_verificador)
    if form.is_valid():
        documento = form.processar()
    return locals()


@rtr()
def verificar_documento_externo(request):
    title = 'Verificar Documento Externo'
    codigo_autenticacao = request.GET.get('codigo_autenticacao')
    codigo_verificador = request.GET.get('codigo_verificador')
    form = AutenticacaoDocumentoDigitalizado(request.POST or None, codigo_autenticacao=codigo_autenticacao, codigo_verificador=codigo_verificador)
    if form.is_valid():
        try:
            documento = form.processar()
            if documento:
                if documento.nivel_acesso in [Documento.NIVEL_ACESSO_SIGILOSO, Documento.NIVEL_ACESSO_RESTRITO]:
                    return httprr('.', f'Documento {documento.get_nivel_acesso_display()} é válido.')
                arquivo = documento.arquivo
                arquivo.seek(0)
                return HttpResponse(arquivo.read(), content_type='application/pdf')
            else:
                return httprr('.', 'Documento inexistente.', 'error')
        except Exception:
            return httprr('.', 'Erro ao procurar o documento.', 'error')
    return locals()


@rtr()
@transaction.atomic()
@login_required()
def rejeitar_assinatura(request: HttpRequest, documento_id: int) -> HttpResponse | dict[str, object]:
    title = 'Rejeitar Solicitação de Assinatura'
    documento = get_documento_or_forbidden(request.user, documento_id)
    # O mesmo vínculo pode ter mais de uma solicitação pendente no documento; rejeita a mais antiga,
    # como faz a assinatura (AssinaturaDocumentoTexto._notificar_assinatura).
    solicitacao = SolicitacaoAssinatura.objects.filter(
        documento_id=documento_id, data_resposta__isnull=True, solicitado=request.user.get_vinculo()
    ).first()
    if solicitacao is None:
        raise Http404

    if solicitacao.documento.identificador and solicitacao.documento.estah_aguardando_assinatura and not solicitacao.eh_balizadora:
        solicitacao.documento.marcar_como_assinado()

    url = None
    if documento.eh_documento_pessoal:
        url = '/admin/documento_eletronico/documentotextopessoal/'
    else:
        url = '/admin/documento_eletronico/documentotexto/'

    form = RejeitarSolicitacaoAssinaturaForm(request.POST or None, instance=solicitacao)
    if form.is_valid():
        with transaction.atomic():
            sid = transaction.savepoint()
            try:
                form.save()
                registrar_acao_documento_texto(
                    request=request, documento=documento, tipo_acao=RegistroAcaoDocumento.TIPO_SOLICITACAO_ASSINATURA_REJEITADA
                )
                assunto = '[SUAP] Documento Eletrônico: Rejeição de Solicitação de Assinatura'
                mensagem = (
                    '<h1>Documento Eletrônico</h1> <h2>Rejeição de Solicitação de Assinatura</h2>'
                    f'<p>A solicitação de assinatura do documento {solicitacao.documento} foi rejeitada por {solicitacao.solicitado} com a seguinte '
                    f'justificativa: {solicitacao.justificativa_rejeicao}</p>'
                )
                #
                send_notification(
                    assunto, ''.join(mensagem), settings.DEFAULT_FROM_EMAIL, [solicitacao.solicitante.get_vinculo()], fail_silently=True
                )
                return httprr(url, 'Solicitação rejeitada com sucesso. Um e-mail foi enviado ao solicitante.')

            except Exception as e:
                transaction.savepoint_rollback(sid)
                return httprr(f'/documento_eletronico/visualizar_documento/{documento.id}/', str(e), tag='error')

    return locals()


@login_required()
@permission_required('documento_eletronico.view_documentotexto')
def verificar_integridade(request, documento_id):
    documento = get_documento_or_forbidden(request.user, documento_id)
    match = documento.get_documentos_url()
    if documento.estah_assinado:
        for assinatura_documento in documento.assinaturadocumentotexto_set.all():
            if not assinatura_documento.validar_documento():
                return httprr(match, message=f'O documento "{documento}" foi violado.', tag='error')
        #
        return httprr(match, f'O documento "{documento}" encontra-se íntegro.')
    raise PermissionDenied


@rtr()
@permission_required('documento_eletronico.change_modelodocumento')
def clonar_modelo_documento(request, modelo_documento_id):
    modelo_documento = get_object_or_404(ModeloDocumento, pk=modelo_documento_id)
    classificacoes = modelo_documento.classificacao.all()
    modelo_documento.id = None
    for nome in iter_incrementing_name(modelo_documento.nome):
        try:
            if not ModeloDocumento.objects.filter(nome=nome).exists():
                modelo_documento.nome = nome
                modelo_documento.save()
                modelo_documento.classificacao.set(classificacoes)
                return httprr(f'/admin/documento_eletronico/modelodocumento/{modelo_documento.id}/', 'Modelo de Documento clonado com sucesso.')
        except Exception:
            raise PermissionDenied
    return httprr('/admin/documento_eletronico/modelodocumento/', 'Modelo de Documento não pode ser clonado.', tag='error')


@rtr()
@permission_required('documento_eletronico.change_tipodocumento')
def clonar_tipo_documento(request, tipo_documento_id):
    tipo_documento = get_object_or_404(TipoDocumentoTexto, pk=tipo_documento_id)
    for nome in iter_incrementing_name(tipo_documento.nome):
        try:
            if not TipoDocumentoTexto.objects.filter(nome=nome).exists():
                tipo_documento_clone = TipoDocumentoTexto()
                tipo_documento_clone.cabecalho_padrao = tipo_documento.cabecalho_padrao
                tipo_documento_clone.rodape_padrao = tipo_documento.rodape_padrao
                tipo_documento_clone.nome = nome
                tipo_documento_clone.sigla = ''.join([word[0] for word in nome.split()])
                tipo_documento_clone.save()
                return httprr(f'/admin/documento_eletronico/tipodocumento/{tipo_documento_clone.id}/', 'Tipo de Documento clonado com sucesso.')
        except Exception:
            raise PermissionDenied
    return httprr('/admin/documento_eletronico/tipodocumento/', 'O Tipo de Documento não pode ser clonado.', tag='error')


@transaction.atomic
def _criar_documento_vinculado(
    usuario: object,
    original: DocumentoTexto,
    configuracao: ConfiguracaoVinculoDocumento,
    modelo: ModeloDocumento,
    usar_conteudo_vigente_como_base: bool,
) -> DocumentoTexto:
    # Impede que requisições simultâneas criem mais de um documento em elaboração
    # para a mesma configuração e o mesmo documento original.
    # 1. A primeira obtém o bloqueio, verifica e cria o documento.
    # 2. A segunda aguarda.
    # 3. Após a primeira concluir, a segunda continua, encontra o documento já criado e rejeita a duplicação.
    original = DocumentoTexto.objects.select_for_update().get(pk=original.pk)
    vinculo_em_elaboracao = (
        VinculoDocumentoTexto.objects.filter(
            configuracao=configuracao,
            documento_texto_alvo=original,
        )
        .exclude(documento_texto_base__status__in=(DocumentoStatus.STATUS_FINALIZADO, DocumentoStatus.STATUS_CANCELADO))
        .exists()
    )
    if vinculo_em_elaboracao:
        raise ValidationError('Já existe um documento relacionado em elaboração para esta configuração.')
    referencia = None
    corpo_base = None
    if usar_conteudo_vigente_como_base:
        ultimo_vinculo = (
            VinculoDocumentoTexto.objects.filter(
                configuracao=configuracao,
                documento_texto_alvo=original,
                documento_texto_base__status=DocumentoStatus.STATUS_FINALIZADO,
                documento_texto_referencia__isnull=False,
            )
            .select_related('documento_texto_base')
            .order_by('-data_criacao')
            .first()
        )
        referencia = ultimo_vinculo.documento_texto_base if ultimo_vinculo else original
        corpo_base = referencia.corpo
    novo = DocumentoTexto.adicionar_documento_texto(
        usuario=usuario,
        setor_dono=original.setor_dono,
        assunto=f'{configuracao.tipo_vinculo_documento.descricao} de {original.identificador}',
        modelo=modelo,
        nivel_acesso=original.nivel_acesso,
        hipotese_legal=original.hipotese_legal,
        corpo=corpo_base,
    )
    vinculo = VinculoDocumentoTexto(
        tipo_vinculo_documento=configuracao.tipo_vinculo_documento,
        documento_texto_base=novo,
        documento_texto_alvo=original,
        documento_texto_referencia=referencia,
        configuracao=configuracao,
    )
    vinculo.full_clean()
    vinculo.save()
    return novo


@rtr()
@login_required
@permission_required('documento_eletronico.add_documentotexto')
def criar_documento_relacionado(request: HttpRequest, documento_id: int) -> HttpResponse | dict[str, object]:
    original = get_documento_or_forbidden(request.user, documento_id)
    if not _pode_criar_documento_relacionado(original, request.user):
        raise PermissionDenied

    configuracoes = ConfiguracaoVinculoDocumento.objects.filter(ativo=True, tipo_documento_alvo=original.tipo)
    if not configuracoes.exists():
        return httprr(original.get_absolute_url(), 'Não há configurações de vínculo para este tipo de documento.', tag='error')

    title = f'Criar documento relacionado a {original.identificador}'
    form = CriarDocumentoRelacionadoForm(request.POST or None, request=request, documento=original)
    if form.is_valid():
        configuracao = form.cleaned_data['configuracao']
        modelo = form.cleaned_data['modelo']
        usar_conteudo_vigente_como_base = form.cleaned_data['usar_conteudo_vigente_como_base']
        try:
            novo = _criar_documento_vinculado(request.user, original, configuracao, modelo, usar_conteudo_vigente_como_base)
        except ValidationError as erro:
            return httprr(original.get_absolute_url(), ' '.join(erro.messages), tag='error')

        return httprr(f'/documento_eletronico/editar_documento/{novo.pk}/', 'Documento relacionado criado. Edite o documento e finalize.')

    return locals()


@rtr()
@permission_required('documento_eletronico.change_documentotexto')
def clonar_documento(request, documento_id):
    title = 'Clonar Documento Eletrônico'
    documento = get_documento_or_forbidden(request.user, documento_id)
    if not documento.pode_clonar_documento(request.user):
        raise ValidationError('O documento não pode ser clonado.')

    if not documento.modelo.tipo_documento_texto.ativo:
        messages.error(request, f'O tipo do documento {documento.modelo.tipo_documento_texto} não pode ser clonado pois está inativo.')
        return httprr(documento.get_absolute_url())

    mensagem_alteracao = ''
    if not documento.hipotese_legal and documento.nivel_acesso in [Documento.NIVEL_ACESSO_RESTRITO, Documento.NIVEL_ACESSO_SIGILOSO]:
        mensagem_alteracao = (
            f', no entanto o nível de acesso do documento clonado foi alterado para {documento.modelo.get_nivel_acesso_padrao_display()}'
        )
    if request.method == 'POST':
        form = DocumentoTextoForm(request.POST, request=request)
        if documento.eh_documento_pessoal:
            form = DocumentoTextoPessoalForm(request.POST, request=request)

        if form.is_valid():
            setor = None

            if form.cleaned_data['tipo'] != documento.tipo:
                return httprr(
                    f'/documento_eletronico/clonar_documento/{documento.id}/',
                    'Não é permitido alterar o tipo do documento a ser clonado.',
                    tag='error',
                )

            if not documento.eh_documento_pessoal:
                setor = get_setor(request.user)

            instance = form.save()
            instance.corpo = documento.corpo
            instance.save()

            return httprr(
                f'/documento_eletronico/visualizar_documento/{form.instance.id}/',
                f'Documento foi clonado com sucesso{mensagem_alteracao}.',
            )
    else:
        initial = {
            'tipo': documento.tipo.id,
            'modelo': documento.modelo.id,
            'assunto': f'{documento.assunto}',
            'hipotese_legal': documento.hipotese_legal.id if documento.hipotese_legal else None,
            'classificacao': documento.modelo.classificacao.all() if documento.modelo.classificacao else None,
        }
        if documento.eh_documento_pessoal:
            form = DocumentoTextoPessoalForm(initial=initial, request=request)
        else:
            initial['setor_dono'] = documento.setor_dono.id if not documento.eh_documento_pessoal else None
            form = DocumentoTextoForm(initial=initial, request=request)
        messages.success(request, 'Para prosseguir com a clonagem edite as informações necessárias e informe o assunto do documento.')

    return locals()


@transaction.atomic()
@permission_required('documento_eletronico.change_documentotexto')
def rejeitar_revisao(request, documento_id):
    documento = get_object_or_404(DocumentoTexto, pk=documento_id)
    if documento.pode_rejeitar_revisao(request.user):
        solicitacao = (
            SolicitacaoRevisao.objects.filter(documento_id=documento_id, data_resposta__isnull=False, status=SolicitacaoStatus.STATUS_DEFERIDA)
            .order_by('-data_solicitacao')
            .first()
        )
        # reverting
        with transaction.atomic():
            try:
                previous_instance = get_previous(documento, solicitacao.data_solicitacao)
                previous_instance.revert()
            except Version.DoesNotExist:
                return httprr('..', 'Você deve Concluir o documento, pois não existe alteração na revisão.')

        documento = get_object_or_404(DocumentoTexto, pk=documento_id)
        documento.cancelar_revisao()
        documento.save()
        solicitacao.adicionar_avaliacao_indeferida(request.user)
        registrar_acao_documento_texto(request, documento, RegistroAcaoDocumento.TIPO_AVALIACAO_REVISAO, solicitacao.get_status_avaliacao())
        url = reverse_lazy('visualizar_documento', kwargs={'documento_id': documento.id}, current_app='documento_eletronico')
        return httprr(url, 'Revisão rejeitada com sucesso.')
    #
    raise PermissionDenied


@transaction.atomic()
@permission_required('documento_eletronico.change_documentotexto, documento_eletronico.change_documentotextopessoal')
def finalizar_documento(request, documento_id, retornar_response=True):
    documento = get_documento_or_forbidden(request.user, documento_id)

    url = reverse_lazy('visualizar_documento', kwargs={'documento_id': documento_id}, current_app='documento_eletronico')

    # Se for um documento pessoal deve exigir, no mínimo, a assinatura do dono do documento
    if documento.eh_documento_pessoal:
        assinou = AssinaturaDocumentoTexto.objects.filter(documento=documento, assinatura__vinculo=documento.usuario_criacao.get_vinculo()).exists()
        if not assinou:
            return (
                httprr(url, 'O documento pessoal só pode ser finalizado se tiver, no mínimo, a assinatura de quem o criou.', tag='error')
                if retornar_response
                else None
            )

    if documento.pode_finalizar_documento(request.user):
        documento.finalizar_documento()
        try:
            documento.save()
        except ValidationError as e:
            return httprr(url, str(e), 'error') if retornar_response else None
        # Registrar ação
        registrar_acao_documento_texto(request, documento, RegistroAcaoDocumento.TIPO_FINALIZACAO)
        return httprr(url, 'Documento finalizado com sucesso.') if retornar_response else None

    raise PermissionDenied


@rtr()
@permission_required('documento_eletronico.change_documentotexto')
def vincular_documentos(request: HttpRequest, documento_texto_base_id: int) -> HttpResponse | dict[str, object]:
    title = 'Vincular Documentos'
    documento_texto_base = get_object_or_404(DocumentoTexto, pk=documento_texto_base_id)
    if not documento_texto_base.pode_vincular_documentos(request.user):
        raise PermissionDenied
    form = VinculoDocumentoTextoForm(data=request.POST or None, request=request, documento_texto_base=documento_texto_base)
    if form.is_valid():
        form.save()
        url = reverse_lazy('visualizar_documento', kwargs={'documento_id': documento_texto_base_id}, current_app='documento_eletronico')
        return httprr(url, 'Vínculo criado com sucesso.')

    return locals()


@permission_required('documento_eletronico.change_documentotexto')
def remover_vinculo_documento_texto(
    request: HttpRequest,
    vinculo_documento_texto_id: int,
    documento_id: int,
) -> HttpResponse:
    vinculo_documento_texto = get_object_or_404(VinculoDocumentoTexto, pk=vinculo_documento_texto_id)
    documento = get_documento_or_forbidden(request.user, documento_id)
    url = reverse_lazy('visualizar_documento', kwargs={'documento_id': documento_id}, current_app='documento_eletronico')
    documentos_vinculo = (vinculo_documento_texto.documento_texto_base_id, vinculo_documento_texto.documento_texto_alvo_id)
    if documento.pk not in documentos_vinculo or not documento.tem_permissao_editar(request.user):
        raise PermissionDenied
    if not vinculo_documento_texto.pode_ser_removido:
        return httprr(url, 'Este vínculo não pode ser removido, pois compõe o histórico dos documentos.', tag='error')
    vinculo_documento_texto.delete()
    return httprr(url, 'Operação realizada com sucesso.')


@permission_required('documento_eletronico.change_documentotexto')
def remover_solicitacao_assinatura(request, solicitacao_assinatura_id):
    solicitacao = get_object_or_404(SolicitacaoAssinatura, id=solicitacao_assinatura_id)
    redirect_url = reverse_lazy('visualizar_documento', kwargs={'documento_id': solicitacao.documento_id}, current_app='documento_eletronico')
    if solicitacao.status == SolicitacaoStatus.STATUS_ESPERANDO:
        try:
            solicitacao.delete_removendo_solicitacoes_dependentes()
            Notificar.remocao_solicitacao_assinatura(solicitacao.solicitado, solicitacao.documento)
            mensagem = 'Solicitação removida com sucesso.'
            tag = 'success'
        except ValidationError as error:
            return httprr(redirect_url, ' '.join(error), 'error')
    else:
        mensagem = 'Solicitação só pode ser removida se ela estiver na situação ESPERANDO.'
        tag = 'error'
    return httprr(redirect_url, mensagem, tag)


@permission_required('documento_eletronico.change_documentotexto, documento_eletronico.change_documentotextopessoal')
def excluir_documento_texto(request, documento_id):
    documento = get_documento_or_forbidden(request.user, documento_id)
    if not documento.pode_ser_excluido():
        raise PermissionDenied

    if not documento.eh_documento_pessoal:
        if 'estagios' in settings.INSTALLED_APPS:
            if DocumentoTexto.objects.filter(pk=documento.pk, praticaprofissional__isnull=False).exists():
                return httprr(
                    request.META.get('HTTP_REFERER', '/'),
                    'Erro ao tentar excluir. Esse documento é referenciado por uma prática profissional no módulo de estágios.',
                    'error',
                )
        if 'contratos' in settings.INSTALLED_APPS:
            if not documento.estah_em_rascunho and (documento.medicoes_despacho.exists() or documento.medicoes_termo_definitivo.exists()):
                return httprr(
                    request.META.get('HTTP_REFERER', '/'),
                    'Erro ao tentar excluir. Esse documento é referenciado por uma medição no módulo de contratos.',
                    'error',
                )

    try:
        # Garante que os anexos serao excluidos
        anexos_simples = documento.get_apenas_anexos_digitalizados_simples()
        for anexo_simples in anexos_simples:
            anexo_simples.delete()

        documento.delete()
    except Exception as e:
        return httprr(request.META.get('HTTP_REFERER', '/'), f'Não é possível excluir este documento. Detalhes: {e!s}', 'error')

    url = None
    if documento.eh_documento_pessoal:
        url = '/admin/documento_eletronico/documentotextopessoal/'
    else:
        url = '/admin/documento_eletronico/documentotexto/'

    return httprr(url, 'Documento removido com sucesso.')


@rtr()
@login_required()
def solicitar_compartilhamento_documento_digitalizado(request, processo_id, documento_id):
    documento = get_object_or_404(DocumentoDigitalizado, id=documento_id)
    processos_incluido = documento.get_processos(exibir_somente_processos_nos_quais_documento_nao_foi_removido=True).first()
    app_processo_eletronico_disponivel = app_processo_eletronico_estah_instalada()
    if app_processo_eletronico_disponivel:
        Processo = apps.get_model('processo_eletronico', 'Processo')
        processo_incluido = documento.get_processos(exibir_somente_processos_nos_quais_documento_nao_foi_removido=True).filter(id=processo_id).first()
        if (
            documento.eh_documento_digitalizado
            and documento.eh_privado
            and not documento.pode_ler(request.user, verificar_acesso_cargo=False)
            and processo_incluido
            and processos_incluido.pode_editar(request.user)
            and not documento.tem_solicitacao_pendente_compartilhamento(request.user)
        ):
            title = f'Solicitar visualização do Documento {documento.assunto}'
            form = SolicitarCompartilhamentoDocumentoDigitalizadoForm(
                request.POST or None, solicitante=request.user.get_vinculo(), documento=documento, processo=processo_incluido
            )
            if form.is_valid():
                form.save()
                return httprr('..', 'Solicitação de visualização feita com sucesso.')
            return locals()
    raise PermissionDenied('Você não pode solicitar visualização a esse documento.')


@rtr('documento_eletronico/avaliar_solicitacao_compartilhamento_documento_digitalizado.html')
@login_required()
def avaliar_solicitacao_compartilhamento_documento_digitalizado(request, processo_id, solicitacao_id):
    solicitacao = get_object_or_404(SolicitacaoCompartilhamentoDocumentoDigitalizadoPessoa, id=solicitacao_id)
    usuario_solicitacao = solicitacao.usuario_solicitacao
    documento = solicitacao.documento
    title = f'Avaliar Solicitação de visualização do Documento {documento.assunto}'
    app_processo_eletronico_disponivel = app_processo_eletronico_estah_instalada()
    if app_processo_eletronico_disponivel:
        processo_incluido = documento.get_processos(exibir_somente_processos_nos_quais_documento_nao_foi_removido=True).filter(id=processo_id).first()
        documento_removido = None
        if documento.eh_documento_digitalizado and processo_incluido and documento.tem_permissao_editar(request.user):
            documento_removido = False
        else:
            processo = documento.get_processos(exibir_somente_processos_nos_quais_documento_nao_foi_removido=False).filter(id=processo_id).first()
            if documento in [doc.documento for doc in processo.get_documentos_removidos()]:
                documento_removido = True
            else:
                return httprr('..', 'Você não pode avaliar a solicitação de visualização desse documento.')
        #
        form = AvaliarSolicitacaoCompartilhamentoDocumentoDigitalizadoForm(
            request.POST or None,
            instance=solicitacao,
            processo=processo_incluido,
            documento_removido=documento_removido,
            documento_eh_privado=documento.eh_privado,
        )
        if form.is_valid():
            form.save()
            return httprr('..', 'Avaliação da Solicitação de Visualização feita com sucesso.')
        return locals()

    raise PermissionDenied


@rtr()
@login_required()
def documento_texto_editar_interessados(request, documento_id):
    documento = get_object_or_404(DocumentoTexto, id=documento_id)
    target = reverse_lazy('visualizar_documento', kwargs={'documento_id': documento_id}, current_app='documento_eletronico')
    title = f'Editar Interessados do documento {documento}'
    if not documento.admite_interessados():
        return httprr(target, 'Esse tipo de documento não aceita interessados.', tag='error')
    #
    if not documento.pode_vincular_interessado(request.user):
        raise PermissionDenied('Você não pode editar os interessados desse documento ou o presente documento não está finalizado.')
    #
    form = DocumentoTextoFormEditarInteressados(request.POST or None, documento=documento, request=request)
    if form.is_valid():
        interessados = form.cleaned_data.get('interessados')
        set_objeto = set(documento.interessados.all())
        set_form = set(interessados)
        if set_objeto != set_form:
            interessados_removidos = set_objeto.difference(set_form)
            interessados_adicionados = set_form.difference(set_objeto)

            motivo = 'Interessados adicionados: {}; Interessados Removidos: {}. Justificativa: {}'.format(
                ','.join([str(interessado) for interessado in interessados_adicionados] or ['Nenhum']),
                ', '.join([str(interessado) for interessado in interessados_removidos] or ['Nenhum']),
                form.cleaned_data.get('observacao_alteracao_interessados'),
            )
            documento.adicionar_interessados(interessados)
            registrar_acao_documento_texto(request, documento, RegistroAcaoDocumento.TIPO_EDICAO_INTERESSADOS, motivo)
            # Notificar os interessados
            assunto = '[SUAP] Documento Eletrônico: Vinculação como interessado no documento'
            url_documento = urljoin(settings.SITE_URL, documento.get_absolute_url())
            if interessados_adicionados:
                mensagem_adicionados = f"""
                <h1>Documento Eletrônico</h1> <h2>Vinculação como interessado no documento</h2>
                <p>Você foi vinculado(a) ao documento <a href="{url_documento}">{documento}</a>. </p>
                """
                send_notification(
                    assunto,
                    mensagem_adicionados,
                    settings.DEFAULT_FROM_EMAIL,
                    interessados_adicionados,
                    html=mensagem_adicionados,
                    fail_silently=True,
                )
            if interessados_removidos:
                documento.remover_interessados(interessados_removidos)
                mensagem_removidos = f"""
                <h1>Documento Eletrônico</h1>
                <h2>Desvinculação como interessado no documento</h2>
                <p>Você foi desvinculado(a) ao documento <a href="{url_documento}">{documento}</a>.</p>
                """
                send_notification(
                    assunto, mensagem_removidos, settings.DEFAULT_FROM_EMAIL, interessados_removidos, html=mensagem_removidos, fail_silently=True
                )

            return httprr(target, 'Os interessados no documento foram alterados com sucesso.')
        return httprr(target, 'Não houve alteração nos interessados do documento.', tag='error')
    #
    return locals()


@rtr()
@login_required()
def documento_texto_reprocessar_interessados(request, documento_id):
    documento = get_object_or_404(DocumentoTexto, id=documento_id)
    target = reverse_lazy('visualizar_documento', kwargs={'documento_id': documento_id}, current_app='documento_eletronico')
    if not documento.pode_reprocessar_interessados(request.user):
        return httprr(target, 'Você não pode editar os interessados desse documento ou o presente documento não está finalizado.', 'error')

    interessados_adicionados = documento.reprocessar_interessados()
    if interessados_adicionados:
        interessados = ','.join([str(interessado) for interessado in interessados_adicionados] or ['Nenhum'])
        motivo = f'Interessados adicionados: {interessados}; Justificativa: Reprocessamento automático de interessados.'
        registrar_acao_documento_texto(request, documento, RegistroAcaoDocumento.TIPO_EDICAO_INTERESSADOS, motivo)
    return httprr(
        target,
        'Interessados reprocessados com sucesso.',
    )


# View que se conecta a view rh.views.servidor
@receiver(rh_servidor_view_tab)
def servidor_view_tab_signal(sender, request, servidor, verificacao_propria, eh_chefe, **kwargs):
    tipo_portarias = TipoDocumento.objects.filter(nome__icontains='Portaria')
    portarias = DocumentoTexto.objects.filter(
        interessados__pessoa__pessoafisica__cpf=servidor.pessoa_fisica.cpf,
        modelo__tipo_documento_texto__in=tipo_portarias,
        status=DocumentoStatus.STATUS_FINALIZADO,
    )

    if portarias.exists():
        return render_to_string(
            template_name='documento_eletronico/templates/servidor_view_tab.html',
            context={'lps_context': {'nome_modulo': 'documento_eletronico'}, 'servidor': servidor, 'portarias': portarias},
            request=request,
        )
    return False


@rtr()
@login_required
def assinar_via_senha_documento_pessoal(request, documento_id):
    title = 'Assinatura de Documento com Senha'

    # Verifica se pode assinar
    # ------------------------
    documento = get_documento_or_forbidden(request.user, documento_id)
    if not documento.pode_assinar(request.user):
        raise PermissionDenied

    if not request.user.get_profile().get_cpf_ou_passaporte():
        raise PermissionDenied('Usuário não possui CPF.')

    if not request.user.get_profile().nome_usual:
        raise PermissionDenied('Usuário não possui nome usual.')

    # Verifica se foi com solicitacao de anexacao
    # ------------------------
    solicitacao_assinatura_com_anexacao_processo = documento.get_solicitacao_assinatura_com_anexacao_processo()
    if (
        solicitacao_assinatura_com_anexacao_processo
        and solicitacao_assinatura_com_anexacao_processo.solicitacao_assinatura.solicitado == request.user.get_profile()
    ):
        processo_para_anexar = solicitacao_assinatura_com_anexacao_processo.processo_para_anexar

    # Gera a sugestao do identificador apenas quando ainda nao ha identificador definitivo.
    identificador_tipo_documento_sigla = None
    identificador_numero = None
    identificador_ano = None
    identificador_dono_documento = None
    if not documento.tem_identificador_definitivo:
        identificador_tipo_documento_sigla, identificador_numero, identificador_ano, identificador_dono_documento = (
            documento.get_sugestao_identificador_definitivo(
                tipo_documento_texto=documento.modelo.tipo_documento_texto, usuario=documento.usuario_criacao, documento_id=documento_id
            )
        )

    form = AssinarDocumentoForm(request.POST or None)
    if form.is_valid():
        with transaction.atomic():
            sid = transaction.savepoint()
            try:
                papel = form.cleaned_data.get('papel')

                data_emissao = get_datetime_now()

                if not documento.tem_identificador_definitivo:
                    documento.atribuir_identificador_e_processar_conteudo_final(
                        identificador_tipo_documento_sigla=identificador_tipo_documento_sigla,
                        identificador_numero=identificador_numero,
                        identificador_ano=identificador_ano,
                        identificador_setor_sigla=None,
                        identificador_dono_documento=identificador_dono_documento,
                        data_emissao=data_emissao,
                    )
                    documento.save()

                # Assinar o documento
                documento.assinar_via_senha(request.user, papel, data_emissao)

                # Registrar ação
                obs = f'Documento assinado por {request.user}'
                registrar_acao_documento_texto(request, documento, RegistroAcaoDocumento.TIPO_ASSINATURA, obs)
                target = reverse_lazy('visualizar_documento', kwargs={'documento_id': documento_id}, current_app='documento_eletronico')
                transaction.savepoint_commit(sid)
                # Notificação_email Demanda_495
                solicitacao = documento.get_solicitacao_balizadora()
                if solicitacao.solicitado == request.user.get_profile():
                    solicitacoes_dependentes = solicitacao.get_solicitacoes_dependentes()
                    if solicitacoes_dependentes:
                        Notificar.solicitacao_assinatura_condicionantes(solicitacoes_dependentes, documento)

                return httprr(target, 'Documento assinado com sucesso.')
            except Exception as e:
                transaction.savepoint_rollback(sid)
                error_message = e or ', '.join(e)
                return httprr('.', message=error_message, tag='error')

    return locals()


@rtr()
@login_required
@govbr_token_required
def assinar_documento_com_gov_br(request: HttpRequest, documento_id: int) -> HttpResponse | dict:
    title = 'Assinatura de Documento'

    # Verifica se pode assinar
    # ------------------------
    documento = get_documento_or_forbidden(request.user, documento_id)
    if not documento.pode_assinar(request.user):
        raise PermissionDenied

    if not request.user.get_profile().get_cpf_ou_passaporte():
        raise PermissionDenied('Usuário não possui CPF.')

    if not request.user.get_profile().nome_usual:
        raise PermissionDenied('Usuário não possui nome usual.')

    # Verifica se foi com solicitacao de anexacao
    # ------------------------
    solicitacao_assinatura_com_anexacao_processo = documento.get_solicitacao_assinatura_com_anexacao_processo()
    if (
        solicitacao_assinatura_com_anexacao_processo
        and solicitacao_assinatura_com_anexacao_processo.solicitacao_assinatura.solicitado == request.user.get_profile()
    ):
        processo_para_anexar = solicitacao_assinatura_com_anexacao_processo.processo_para_anexar

    # Gera a sugestao do identificador
    # ------------------------
    identificador = _sugerir_identificador_gov_br(documento)
    identificador_tipo_documento_sigla, identificador_numero, identificador_ano, identificador_dono_documento = identificador

    form = AssinarDocumentoGovBRForm(request.POST or None, request=request)
    form.gerar_codigo_verificacao()

    if form.is_valid():
        return _assinar_com_gov_br(request, documento, form.cleaned_data.get('papel'), identificador)

    return locals()


def _sugerir_identificador_gov_br(documento: DocumentoTexto) -> tuple:
    """Sigla do tipo, número, ano e dono (ou setor) sugeridos para o identificador definitivo de ``documento``.

    Com identificador definitivo não há sugestão: vazios, que o template exibe em branco.
    """
    if documento.tem_identificador_definitivo:
        return '', '', '', ''
    tipo_documento_texto = documento.modelo.tipo_documento_texto
    if isinstance(documento, DocumentoTextoPessoal):
        return documento.get_sugestao_identificador_definitivo(
            tipo_documento_texto=tipo_documento_texto, usuario=documento.usuario_criacao, documento_id=documento.pk
        )
    return documento.get_sugestao_identificador_definitivo(tipo_documento_texto=tipo_documento_texto, setor_dono=documento.setor_dono)


def _assinar_com_gov_br(request: HttpRequest, documento: DocumentoTexto, papel: object, identificador: tuple) -> HttpResponse:
    """Assina ``documento`` com ``papel``; qualquer falha desfaz tudo o que foi gravado (#17817)."""
    identificador_tipo_documento_sigla, identificador_numero, identificador_ano, identificador_dono_documento = identificador
    documento_id = documento.pk
    with transaction.atomic():
        sid = transaction.savepoint()
        try:
            data_emissao = get_datetime_now()
            if (
                not isinstance(documento, DocumentoTextoPessoal)
                and documento.tem_identificador_definitivo
                and documento.identificador_setor_sigla != montar_identificador_sigla(documento.setor_dono)
            ):
                documento.identificador_setor_sigla = montar_identificador_sigla(documento.setor_dono)
                documento.save()

            if not documento.tem_identificador_definitivo:
                documento.atribuir_identificador_e_processar_conteudo_final(
                    identificador_tipo_documento_sigla=identificador_tipo_documento_sigla,
                    identificador_numero=identificador_numero,
                    identificador_ano=identificador_ano,
                    identificador_setor_sigla=not isinstance(documento, DocumentoTextoPessoal)
                    and montar_identificador_sigla(documento.setor_dono)
                    or None,
                    identificador_dono_documento=identificador_dono_documento,
                    data_emissao=data_emissao,
                )
            documento.save()

            # Assinar o documento
            documento.assinar_via_senha(request.user, papel, data_emissao)

            # Registrar ação
            registrar_acao_documento_texto(request, documento, RegistroAcaoDocumento.TIPO_ASSINATURA, f'Documento assinado por {request.user}')

            target = reverse_lazy('visualizar_documento', kwargs={'documento_id': documento_id}, current_app='documento_eletronico')
            transaction.savepoint_commit(sid)

            # Notificação_email Demanda_495
            solicitacao = documento.get_solicitacao_balizadora()
            if solicitacao.solicitado == request.user.get_profile():
                solicitacoes_dependentes = solicitacao.get_solicitacoes_dependentes()
                if solicitacoes_dependentes:
                    Notificar.solicitacao_assinatura_condicionantes(solicitacoes_dependentes, documento)

            return httprr(target, 'Documento assinado com sucesso.')
        except ValidationError as e:
            # Regra de negócio que impede a assinatura: o assinante precisa ver o motivo (#17817).
            transaction.savepoint_rollback(sid)
            return httprr('.', message='; '.join(e.messages), tag='error')
        except Exception as e:
            transaction.savepoint_rollback(sid)
            capture_exception(e)
            if settings.DEBUG:
                raise e
            return httprr('.', message='Ocorreu um erro ao assinar documento', tag='error')


@rtr()
@login_required()
def visualizar_documento_digitalizado_pessoal(request, documento_id):
    documento = get_object_or_404(DocumentoDigitalizadoPessoal, pk=documento_id)

    title = documento

    if not documento.pode_ler(user=request.user):
        raise PermissionDenied
    return locals()


@rtr('documento_eletronico/templates/visualizar_documento_digitalizado_pessoal.html')
@login_required()
def visualizar_documento_digitalizado_anexo_simples(request, documento_id):
    documento = get_object_or_404(DocumentoDigitalizadoAnexoSimples, pk=documento_id)

    title = documento

    if not documento.pode_ler(user=request.user):
        raise PermissionDenied
    return locals()


@permission_required('documento_eletronico.change_documentotexto')
@rtr()
def editar_documento_digitalizado_anexo_simples(request, documento_id):
    documento = get_object_or_404(DocumentoDigitalizadoAnexoSimples, pk=documento_id)
    if not documento.pode_editar(user=request.user):
        raise PermissionDenied

    title = f'Editar {documento}'

    form = DocumentoDigitalizadoAnexoSimplesForm(data=request.POST or None, instance=documento, request=request)
    if form.is_valid():
        form.save()
        return httprr('..', 'Documento atualizado com sucesso.', close_popup=True)
    return locals()


@rtr()
@login_required()
def alterar_nivel_acesso_documento_digitalizado_anexo_simples(request: HttpRequest, documento_id: int) -> HttpResponse:
    documento = get_object_or_404(DocumentoDigitalizadoAnexoSimples, pk=documento_id)
    vinculo_documento = documento.get_vinculo_documento_texto()
    if not vinculo_documento or not documento.pode_alterar_nivel_acesso(request.user):
        raise PermissionDenied

    title = f'Alterar Nível de Acesso do Anexo {documento}'
    form = DocumentoAlterarNivelAcessoForm(request.POST or None, request=request, documento=documento)
    if form.is_valid():
        try:
            documento.alterar_nivel_acesso(
                int(form.cleaned_data.get('nivel_acesso')),
                form.cleaned_data.get('hipotese_legal'),
                request.user,
                request.META.get('REMOTE_ADDR', ''),
                form.cleaned_data.get('justificativa'),
                form.cleaned_data.get('vinculos_compartilhados'),
            )
            redirect_url = reverse_lazy(
                'visualizar_documento', kwargs={'documento_id': vinculo_documento.documento_id}, current_app='documento_eletronico'
            )
            return httprr(redirect_url, 'Nível de Acesso alterado com sucesso.')
        except Exception as e:
            error_message = f'{e}' or ', '.join(e.messages)
            return httprr('..', error_message, tag='error')

    return locals()


@rtr()
@login_required()
def alterar_nivel_acesso_documento_texto_anexo(request: HttpRequest, documento_id: int) -> HttpResponse:
    documento = get_object_or_404(DocumentoTexto, pk=documento_id)
    vinculo_documento = documento.get_vinculo_documento_texto_anexado()
    if not vinculo_documento or not documento.pode_alterar_nivel_acesso_como_anexo(request.user):
        raise PermissionDenied

    title = f'Alterar Nível de Acesso do Anexo {documento}'
    form = DocumentoAlterarNivelAcessoForm(request.POST or None, request=request, documento=documento)
    if form.is_valid():
        try:
            documento.alterar_nivel_acesso_como_anexo(
                int(form.cleaned_data.get('nivel_acesso')),
                form.cleaned_data.get('hipotese_legal'),
                request.user,
                request.META.get('REMOTE_ADDR', ''),
                form.cleaned_data.get('justificativa'),
            )
            redirect_url = reverse_lazy(
                'visualizar_documento', kwargs={'documento_id': vinculo_documento.documento_id}, current_app='documento_eletronico'
            )
            return httprr(redirect_url, 'Nível de Acesso alterado com sucesso.')
        except Exception as e:
            error_message = f'{e}' or ', '.join(e.messages)
            return httprr('..', error_message, tag='error')

    return locals()


@rtr('processo_eletronico/templates/listar_documentos_adicionar.html')
@permission_required('documento_eletronico.change_documentotexto')
def listar_documentos_anexar(request, documento_id):
    instance = get_documento_or_forbidden(request.user, documento_id)

    if not instance.pode_receber_anexos():
        raise PermissionDenied

    title = f'Documentos que podem ser anexados {instance}'

    is_anexar_documento = True
    view_action = 'anexar_documento_a_documentotexto'

    # Filtrar os dados
    setor = get_setor(request.user)
    initial = {'campus': setor.uo.pk, 'setor': setor.pk, 'ano': get_datetime_now().year}
    tem_apenas_tab = len(request.GET) == 1 and request.GET.get('tab')
    parametros_para_processar = initial
    if request.GET and not tem_apenas_tab:
        parametros_para_processar = request.GET
    form = ListarDocumentosTextoForm(parametros_para_processar, request=request, exceto_documento=instance)
    documentos, documentos_compartilhados, params, order_str = form.processar()

    # Exclusao dos documentos que nao podem ser anexados
    # - Documentos internos (texto) que ja tenham sido anexados a instance
    # - Documentos digitalizados que ja tenham sido anexados a instance
    documentos_internos_ja_anexados_ids = DocumentoTextoAnexoDocumentoTexto.objects.filter(documento=instance).values_list(
        'documento_anexado__id', flat=True
    )
    documentos_digitalizados_ja_anexados_ids = DocumentoTextoAnexoDocumentoDigitalizado.objects.filter(documento=instance).values_list(
        'documento_anexado__id', flat=True
    )
    #
    documentos = documentos.filter(status=DocumentoStatus.STATUS_FINALIZADO)
    documentos = documentos.exclude(id__in=documentos_internos_ja_anexados_ids)
    documentos = documentos.order_by(
        '-data_criacao', 'identificador_tipo_documento_sigla', 'identificador_numero', 'identificador_ano', 'identificador_setor_sigla'
    )
    #
    documentos_pessoais = DocumentoTextoPessoal.objects.proprios(request.user).defer('cabecalho', 'rodape', 'corpo')
    documentos_pessoais = documentos_pessoais.filter(status=DocumentoStatus.STATUS_FINALIZADO)
    documentos_pessoais = documentos_pessoais.exclude(id__in=documentos_internos_ja_anexados_ids)
    #
    documentos_pessoais_digitalizados = DocumentoDigitalizadoPessoal.objects.filter(usuario_criacao=request.user)
    documentos_pessoais_digitalizados = documentos_pessoais_digitalizados.exclude(id__in=documentos_digitalizados_ja_anexados_ids)

    return locals()


@transaction.atomic()
@permission_required('documento_eletronico.change_documentotexto')
def anexar_documento_a_documentotexto(request, documentotexto_id, documento_id):
    # Documento que vai receber o anexo
    instance = get_documento_or_forbidden(request.user, documentotexto_id)

    if not instance.pode_receber_anexos():
        raise PermissionDenied

    # Documento que serah anexado
    documento = None
    try:
        documento = get_documento_or_forbidden(request.user, documento_id)
    except Exception:
        try:
            documento = get_documento_digitalizado(documento_id)
        except Exception:
            raise Http404

    # Anexando
    d = None
    if documento.eh_documento_texto:
        d = DocumentoTextoAnexoDocumentoTexto()
    elif documento.eh_documento_digitalizado:
        d = DocumentoTextoAnexoDocumentoDigitalizado()
    d.documento = instance
    d.documento_anexado = documento
    d.save()

    redirect_url = reverse_lazy('visualizar_documento', kwargs={'documento_id': instance.id}, current_app='documento_eletronico')

    return httprr(redirect_url, 'Documento anexado com sucesso.')


@transaction.atomic()
@permission_required('documento_eletronico.change_documentotexto')
def desanexar_documento(request, documentotexto_id, documento_id):
    # Documento que tem o anexo
    instance = get_documento_or_forbidden(request.user, documentotexto_id)

    if not instance.pode_receber_anexos():
        raise PermissionDenied

    # Documento que serah dexanexado
    documento = None
    try:
        documento = get_documento_or_forbidden(request.user, documento_id)
    except Exception:
        try:
            documento = get_documento_digitalizado(documento_id)
        except Exception:
            raise Http404

    # Desanexando
    qs = None
    if documento.eh_documento_texto:
        qs = DocumentoTextoAnexoDocumentoTexto.objects.filter(documento=instance, documento_anexado=documento)
    elif documento.eh_documento_digitalizado:
        qs = DocumentoTextoAnexoDocumentoDigitalizado.objects.filter(documento=instance, documento_anexado=documento)
    if not qs or not qs.exists():
        raise Http404
    qs.delete()

    redirect_url = reverse_lazy('visualizar_documento', kwargs={'documento_id': instance.id}, current_app='documento_eletronico')

    return httprr(redirect_url, 'Documento desanexado com sucesso.')


@rtr()
@permission_required('documento_eletronico.pode_alterar_nivel_acesso_documento_texto')
def alterar_nivel_acesso_documento_texto(request, documento_texto_id):
    documento = get_documento_or_forbidden(request.user, documento_texto_id)
    user = request.user
    if not documento.pode_alterar_nivel_acesso(user):
        raise PermissionDenied

    title = f'Alterar Nível de Acesso do Documento {documento}'

    existe_solicitacoes_aberto = documento.existe_solicitacoes_nivel_acesso_aberto()
    if existe_solicitacoes_aberto:
        error_message = (
            'Não é possível alterar o nível de acesso sem antes analisar as solicitações de alteração de nível de acesso que estão em aberto.'
        )
        return httprr('..', error_message, tag='error')

    #
    form = DocumentoAlterarNivelAcessoForm(request.POST or None, request=request, documento=documento)
    if form.is_valid():
        try:
            DocumentoTexto.alterar_nivel_acesso(
                documento,
                int(form.cleaned_data.get('nivel_acesso')),
                form.cleaned_data.get('hipotese_legal'),
                request.user,
                request.META.get('REMOTE_ADDR', ''),
                form.cleaned_data.get('justificativa'),
            )

            # Importante para usabilidade
            url = None
            if request.GET.get('processo'):
                url = reverse_lazy('processo', kwargs={'processo_id': request.GET.get('processo')}, current_app='processo_eletronico')
            elif documento.pode_ler(request.user):
                url = reverse_lazy('visualizar_documento', kwargs={'documento_id': documento.id}, current_app='documento_eletronico')
            else:
                # Se o usuario editar o nivel de acesso e por isso nao tiver mais acesso ao documento
                # - Sera redirecionado a lista de documentos
                url = '/admin/processo_eletronico/processo/?opcao=1'

            return httprr(url, 'Nível de Acesso alterado com sucesso.')
        except Exception as e:
            error_message = f'{e}' or ', '.join(e.messages)
            return httprr('..', error_message, tag='error')

    #
    return locals()


@rtr()
@permission_required('documento_eletronico.pode_alterar_nivel_acesso_documento_digitalizado')
def alterar_nivel_acesso_documento_digitalizado(request, documento_digitalizado_id):
    documento = get_object_or_404(DocumentoDigitalizado, id=documento_digitalizado_id)
    user = request.user
    if not documento.pode_alterar_nivel_acesso(user):
        raise PermissionDenied

    existe_solicitacoes_aberto = documento.existe_solicitacoes_nivel_acesso_aberto()
    if existe_solicitacoes_aberto:
        error_message = (
            'Não é possível alterar o nível de acesso sem antes analisar as solicitações de alteração de nível de acesso que estão em aberto.'
        )
        return httprr('..', error_message, tag='error')

    #
    title = f'Alterar Nível de Acesso do Documento Digitalizado {documento}'

    form = DocumentoAlterarNivelAcessoForm(request.POST or None, request=request, documento=documento)
    if form.is_valid():
        try:
            documento.alterar_nivel_acesso(
                int(form.cleaned_data.get('nivel_acesso')),
                form.cleaned_data.get('hipotese_legal'),
                request.user,
                request.META.get('REMOTE_ADDR', ''),
                form.cleaned_data.get('justificativa'),
                form.cleaned_data.get('vinculos_compartilhados'),
            )
            return httprr('..', 'Nível de Acesso alterado com sucesso.')
        except Exception as e:
            error_message = f'{e}' or ', '.join(e.messages)
            return httprr('..', error_message, tag='error')

    return locals()


@login_required()
def enviar_codigo_verificacao_govbr(request):
    # API NOTIFICA GOV BR
    API_KEY_NOTIFICA_GOVBR = (
        Configuracao.get_valor_por_chave('catalogo_provedor_servico', 'api_key_notifica_govbr')
        or 'balcao_digital-c4764905-0bb2-4259-ae69-cc8efa2f7402-12ed59cf-b52b-4655-b0c1-242858612cc5'
    )
    TEMPLATE_CODIGO_VERIFICADOR_SUAP_APP_GOVBR = (
        TemplateNotificaGovBR.objects.filter(
            tipo_notificacao=TemplateNotificaGovBR.CODIGO_VERIFICADOR, canal_notificacao=TemplateNotificaGovBR.APP_GOVBR
        )
        .first()
        .id_template
    )

    if not TEMPLATE_CODIGO_VERIFICADOR_SUAP_APP_GOVBR:
        messages.add_message(
            request,
            messages.ERROR,
            'Não é possível enviar a notificação pois não foi localizado o id Template da Plataforma Notifica. Entre em contato com os administradores do sistema!',
        )

    if not settings.DEBUG and not APIExterna.NOTIFICA_GOVBR.ativo:
        messages.add_message(
            request,
            messages.ERROR,
            'Não é possível enviar o código de verificação pois a integração do SUAP com a Plataforma Notifica está desativada!',
        )

    force_new_code = request.GET.get('action', False)
    if settings.DEBUG and API_KEY_NOTIFICA_GOVBR == '111111':
        cache.set(f'govbr_check_{request.user.get_vinculo().id}', '11111', 300)
    if not cache.get(f'govbr_check_{request.user.get_vinculo().id}', None) or force_new_code:
        codigo_verificacao = random_with_N_digits(5)
        cache.set(f'govbr_check_{request.user.get_vinculo().id}', codigo_verificacao, 300)
        try:
            from notifications_python_client.notifications import NotificationsAPIClient

            cliente_notifica_govbr = NotificationsAPIClient(API_KEY_NOTIFICA_GOVBR)
            cpf = request.user.get_profile().cpf.replace('.', '').replace('-', '')
            cliente_notifica_govbr.send_app_govbr_cpf_notification(
                cpf=cpf,
                template_id=TEMPLATE_CODIGO_VERIFICADOR_SUAP_APP_GOVBR,
                personalisation={
                    'instituicao_sigla': Configuracao.get_valor_por_chave('comum', 'instituicao_sigla'),
                    'codigo_verificacao': codigo_verificacao,
                },
            )
            messages.add_message(request, messages.SUCCESS, 'Código enviado com sucesso para App Gov.BR. A validade deste código é de 5 minutos!')
        except Exception:
            messages.add_message(
                request,
                messages.ERROR,
                'Houve um erro ao enviar código de verificação para o aplicativo Gov.BR, certifique-se que possui o aplicativo Gov.BR instalado.',
            )
            enviar_codigo_verificacao_email(request)
            return HttpResponse('ERROR')
    return HttpResponse('OK')


@login_required()
def enviar_codigo_verificacao_email(request):
    force_new_code = request.GET.get('action', False)

    if not cache.get(f'govbr_check_{request.user.get_vinculo().id}', None) or force_new_code:
        codigo_verificacao = random_with_N_digits(5)
        cache.set(f'govbr_check_{request.user.get_vinculo().id}', codigo_verificacao, 300)
        instituicao = Configuracao.get_valor_por_chave('comum', 'instituicao_sigla')
        title = f'Código de Verificação - SUAP/{instituicao}'
        instituicao = Configuracao.get_valor_por_chave('comum', 'instituicao_sigla')
        message = f"""<p>Seu código de verificação no SUAP/{instituicao}: {codigo_verificacao}<p>

                      <p>A validade deste código é de 5 minutos.<p>
                  """
        try:
            # email_secundario migrou p/ Vinculo.email_notificacao; obtém do vínculo do user.
            vinculo = request.user.get_vinculo()
            email_secundario = vinculo.email_notificacao if vinculo else None
            if email_secundario:
                send_mail(title, message, settings.DEFAULT_FROM_EMAIL, [email_secundario])
            messages.add_message(
                request, messages.SUCCESS, f'Código enviado com sucesso para o e-mail: {email_secundario}. A validade deste código é de 5 minutos.'
            )
        except Exception:
            messages.add_message(
                request,
                messages.ERROR,
                'Houve um erro ao enviar código de verificação por e-mail, certifique-se que o usuário possui e-mail secundário cadastrado no SUAP.',
            )
            return HttpResponse('ERROR')
    return HttpResponse('OK')


@documentos.emissao_documentos()
def emissao_documentos(request, data):
    vinculo = request.user.get_vinculo()
    for documento in DocumentoTexto.objects.filter(
        interessados=vinculo, status=DocumentoStatus.STATUS_FINALIZADO, nivel_acesso=Documento.NIVEL_ACESSO_PUBLICO
    ):
        data.append(
            ('Documentos Eletrônicos(Interessado)', f'{documento.tipo}', f'{documento.modelo}', f'{documento}', f'{documento.get_absolute_url()}')
        )

    for documento in DocumentoTexto.objects.filter(
        pk__in=Subquery(
            AssinaturaDocumentoTexto.objects.filter(assinatura__vinculo=vinculo, documento__nivel_acesso=Documento.NIVEL_ACESSO_PUBLICO).values(
                'documento_id'
            )
        )
    ):
        data.append(
            ('Documentos Eletrônicos(Assinados)', f'{documento.tipo}', f'{documento.modelo}', f'{documento}', f'{documento.get_absolute_url()}')
        )


def _filtro_periodo(campo: str, datahora_inicio: datetime | None, datahora_fim: datetime | None) -> dict[str, datetime]:
    """Lookups ``<campo>__gte``/``<campo>__lte`` para os limites informados do período."""
    filtros = {}
    if datahora_inicio:
        filtros[f'{campo}__gte'] = datahora_inicio
    if datahora_fim:
        filtros[f'{campo}__lte'] = datahora_fim
    return filtros


def _registros_por_dia_e_documento(user_id: int, tipo: int, filtros: dict[str, datetime]) -> list[RegistroAcaoDocumentoTexto]:
    """Primeiro registro da ação ``tipo`` do usuário em cada (dia, documento), do dia mais recente ao mais antigo.

    Cada salvamento gera um registro: agrupar por dia e documento evita repetir o mesmo documento
    no dia sem esconder os demais documentos (#17452). O ``DISTINCT ON`` exige que o ``ORDER BY``
    comece pelos seus campos, por isso a ordem de exibição (no dia, por horário) é feita em Python.
    Com ``USE_TZ = False`` a data é gravada no horário local e o ``TruncDate`` não converte fuso.
    """
    registros = (
        RegistroAcaoDocumentoTexto.objects.filter(tipo=tipo, user_id=user_id, documento__isnull=False, **filtros)
        .select_related('documento')
        .annotate(day=TruncDate('data'))
        .order_by('day', 'documento_id', 'data')
        .distinct('day', 'documento_id')
    )
    return sorted(registros, key=lambda registro: (-registro.day.toordinal(), registro.data))


def _acoes_criacao_edicao_documentos(user_id: int, filtros: dict[str, datetime]) -> list[tuple]:
    """Criações e edições de documentos do usuário, uma linha por (dia, documento) em cada ação.

    O documento criado num dia não se repete como edição no mesmo dia; editado em outro dia, a
    edição aparece, porque é trabalho daquele dia.
    """
    acoes = []
    criados_no_dia: set[tuple[date, int]] = set()
    for tipo, acao in ((RegistroAcaoDocumento.TIPO_CRIACAO, 'Criação'), (RegistroAcaoDocumento.TIPO_EDICAO, 'Edição')):
        for registro in _registros_por_dia_e_documento(user_id, tipo, filtros):
            chave = (registro.day, registro.documento_id)
            if tipo == RegistroAcaoDocumento.TIPO_CRIACAO:
                criados_no_dia.add(chave)
            elif chave in criados_no_dia:
                continue
            acoes.append(
                (
                    'Documentos Eletrônicos',
                    f'{acao} de Documentos',
                    registro.documento,
                    f'{registro.get_tipo_display()} em {registro.data.strftime("%d/%m/%Y %H:%M")}',
                    f'{registro.documento.get_absolute_url()}',
                )
            )
    return acoes


@minhas_acoes.registrar_acao()
def minhas_acoes_documento_eletronico(
    request: HttpRequest, data: list[tuple], datahora_inicio: datetime | None, datahora_fim: datetime | None
) -> None:
    vinculo = request.user.get_vinculo()
    user_id = request.user.id

    data.extend(_acoes_criacao_edicao_documentos(user_id, _filtro_periodo('data', datahora_inicio, datahora_fim)))

    filters_assinaturas_documentos = _filtro_periodo('assinatura__data_assinatura', datahora_inicio, datahora_fim)

    qs_assinaturas = (
        AssinaturaDocumentoTexto.objects.filter(assinatura__vinculo=vinculo, **filters_assinaturas_documentos)
        .select_related('documento__modelo', 'documento__modelo__tipo_documento_texto', 'assinatura')
        .only(
            'documento__identificador',
            'documento_id',
            'documento__modelo__nome',
            'documento__modelo__tipo_documento_texto__nome',
            'assinatura__data_assinatura',
        )
        .order_by('assinatura__data_assinatura')
    )
    for doc_assinatura in qs_assinaturas:
        data.append(
            (
                'Documentos Eletrônicos',
                'Assinaturas',
                doc_assinatura.documento,
                f'em {doc_assinatura.assinatura.data_assinatura.strftime("%d/%m/%Y %H:%M")}',
                f'{doc_assinatura.documento.get_absolute_url()}',
            )
        )

    filters_solicitacoes_de_assinaturas_documentos = _filtro_periodo('data_solicitacao', datahora_inicio, datahora_fim)

    qs_solicitacoes_assinaturas = (
        SolicitacaoAssinatura.objects.filter(solicitante_id=user_id, **filters_solicitacoes_de_assinaturas_documentos)
        .exclude(solicitado=vinculo)
        .select_related('documento', 'solicitado')
        .order_by('data_solicitacao')
    )

    for doc_solicitadas_assinatura in qs_solicitacoes_assinaturas:
        data.append(
            (
                'Documentos Eletrônicos',
                'Solicitações de Assinatura',
                doc_solicitadas_assinatura.documento,
                f'em {doc_solicitadas_assinatura.data_solicitacao.strftime("%d/%m/%Y %H:%M")} para {doc_solicitadas_assinatura.solicitado.nome}',
                f'{doc_solicitadas_assinatura.documento.get_absolute_url()}',
            )
        )

    filters_solicitacoes_de_revisoes = _filtro_periodo('data_solicitacao', datahora_inicio, datahora_fim)

    qs_solicitacoes_revisoes = (
        SolicitacaoRevisao.objects.filter(solicitante_id=user_id, **filters_solicitacoes_de_revisoes)
        .exclude(revisor=vinculo)
        .select_related('documento', 'revisor')
        .order_by('data_solicitacao')
    )
    for doc_solicitadas_revisoes in qs_solicitacoes_revisoes:
        data.append(
            (
                'Documentos Eletrônicos',
                'Solicitações de Revisão',
                doc_solicitadas_revisoes.documento,
                f'em {doc_solicitadas_revisoes.data_solicitacao.strftime("%d/%m/%Y %H:%M")} para {doc_solicitadas_revisoes.revisor.nome}',
                f'{doc_solicitadas_revisoes.documento.get_absolute_url()}',
            )
        )

    filters_de_revisoes = _filtro_periodo('data_resposta', datahora_inicio, datahora_fim)
    qs_revisoes = SolicitacaoRevisao.objects.filter(revisor=vinculo, **filters_de_revisoes).select_related('documento').order_by('data_resposta')
    for revisao in qs_revisoes:
        data.append(
            (
                'Documentos Eletrônicos',
                'Revisões',
                revisao.documento,
                f'em {revisao.data_resposta.strftime("%d/%m/%Y %H:%M")}',
                f'{revisao.documento.get_absolute_url()}',
            )
        )


@layout.servicos_anonimos()
def servicos_anonimos(request):
    tem_tipos_documentos_habilitados = TipoDocumento.objects.filter(consulta_publica=True).exists()
    servicos_anonimos = []
    if tem_tipos_documentos_habilitados:
        servicos_anonimos.append(
            {'categoria': 'Consultas gerais', 'url': '/documento_eletronico/consulta_publica/', 'icone': 'file', 'titulo': 'Documentos Eletrônicos'}
        )

    return servicos_anonimos


@rtr('documento_eletronico/templates/consulta_publica_documentos.html')
def consulta_publica(request):
    servicos_anonimos = layout.gerar_servicos_anonimos(request)
    title = 'Documentos Eletrônicos'
    category = 'Consultas'
    icon = 'file'
    tipos_documentos_habilitados = TipoDocumento.objects.filter(consulta_publica=True)
    tem_tipos_documentos_habilitados = tipos_documentos_habilitados.exists()

    if tem_tipos_documentos_habilitados:
        # Obter os parâmetros da consulta atual (exceto 'page')
        consulta_atual = {key: value for key, value in request.GET.items() if key != 'page'}

        # Obter os parâmetros armazenados na sessão
        consulta_anterior = request.session.get('consulta_publica_documentos_params', {})

        # Verificar se os parâmetros mudaram
        parametros_alterados = consulta_atual != consulta_anterior

        # Criar o formulário
        ConsultaPublicaDocumentoForm = ConsultaPublicaDocumentoFormClass(parametros_alterados)
        form = ConsultaPublicaDocumentoForm(request.GET or None, tipos_documentos=tipos_documentos_habilitados)

        # Validar o formulário
        if form.is_valid():
            # Se os parâmetros mudaram, exigir validação do ReCaptcha
            if parametros_alterados and not form.cleaned_data.get('recaptcha'):
                form.add_error('recaptcha', 'Por favor, resolva o ReCaptcha para continuar.')

            else:
                # Atualizar os parâmetros na sessão
                request.session['consulta_publica_documentos_params'] = consulta_atual

                # Filtrar os documentos
                documentos_eletronicos = DocumentoTexto.objects.filter(
                    modelo__tipo_documento_texto__consulta_publica=True,
                    status=DocumentoStatus.STATUS_FINALIZADO,
                    nivel_acesso=DocumentoTexto.NIVEL_ACESSO_PUBLICO,
                )
                assunto = form.cleaned_data.get('assunto')
                if assunto:
                    q_filters = [Q(assunto__icontains=assunto), Q(identificador__icontains=assunto)]
                    documentos_eletronicos = documentos_eletronicos.filter(reduce(operator.or_, q_filters))
                tipo_documento = form.cleaned_data.get('tipo_documento')
                if tipo_documento:
                    documentos_eletronicos = documentos_eletronicos.filter(modelo__tipo_documento_texto=tipo_documento)
                setor = form.cleaned_data.get('setor')
                if setor:
                    documentos_eletronicos = documentos_eletronicos.filter(setor_dono=setor)

    return locals()


@rtr()
@permission_required('documento_eletronico.change_documentotexto, documento_eletronico.change_documentotextopessoal')
def editar_tags_anonimizacao(request: HttpRequest, documento_id: int) -> HttpResponse | dict[str, object]:
    documento = get_documento_or_forbidden(request.user, documento_id)

    title = f'Editar {documento}'

    # Antes do reprocessamento: ele grava as tags, então não pode ficar fora da permissão.
    if not documento.pode_editar_tags_anonimizacao(request.user):
        raise PermissionDenied

    if 'auto_reprocessar' in request.GET:
        tags = documento.get_tags_suap_ai_processadas()
        if tags:
            documento.tags_anonimizacao = tags
            documento.save()
            return httprr(f'/documento_eletronico/editar_tags_anonimizacao/{documento.pk}/', 'Tags de anonimização reprocessadas com sucesso.')

    form = DocumentoTextoEditarTagsAnonimizacaoForm(request.POST or None, instance=documento, request=request)
    if form.is_valid():
        form.save()
        return httprr(f'/documento_eletronico/visualizar_documento/{documento.pk}/', 'Tags de anonimização atualizadas com sucesso.')
    return locals()
