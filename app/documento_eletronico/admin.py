from django.conf import settings
from django import forms as django_forms
from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Prefetch, QuerySet
from django.http import HttpRequest
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from mptt.admin import MPTTModelAdmin
from reversion_compare.admin import CompareVersionAdmin

from comum.models import Configuracao, User
from comum.utils import get_setor
from djtools.contrib.admin import ModelAdminPlus, get_uo_setor_listfilter
from djtools.contrib.admin.views import ChangeListPlus
from djtools.middleware.threadlocals import get_user
from djtools.templatetags.filters import format_profile, status
from djtools.utils import get_datetime_now, httprr, retira_acentos
from documento_eletronico.forms import (
    CompartilhamentoDocumentosPessoaForm,
    CompartilhamentoDocumentosSetorPessoaForm,
    DocumentoDigitalizadoAnexoSimplesForm,
    DocumentoPessoalDigitalizadoForm,
    DocumentoTextoForm,
    DocumentoTextoPessoalForm,
    ModeloDocumentoForm,
    TipoDocumentoForm,
    TipoDocumentoTextoAddForm,
    TipoDocumentoTextoForm,
)
from documento_eletronico.models import (
    AssinaturaDocumentoTexto,
    Classificacao,
    CompartilhamentoDocumentoPessoa,
    CompartilhamentoSetorPessoa,
    DocumentoDigitalizado,
    DocumentoDigitalizadoAnexoSimples,
    DocumentoDigitalizadoPessoal,
    DocumentoTexto,
    DocumentoTextoAnexoDocumentoDigitalizado,
    DocumentoTextoPessoal,
    HipoteseLegal,
    ModeloDocumento,
    NivelPermissao,
    ConfiguracaoVinculoDocumento,
    PermissoesPaginaListagem,
    RegistroAcaoDocumentoTexto,
    SolicitacaoAssinatura,
    TipoConferencia,
    TipoDocumento,
    TipoDocumentoTexto,
    TipoVinculoDocumento,
)
from documento_eletronico.status import DocumentoStatus, SolicitacaoStatus
from documento_eletronico.utils import eh_auditor, eh_procurador, get_setores_compartilhados
from documento_eletronico.views import get_documento_or_forbidden
from suap import nomenclatura


class CompareVersionAdminPlus(CompareVersionAdmin):
    # Template file used for the compare view:
    compare_template = 'documento_eletronico/reversion-compare/compare.html'

    # change template from django-reversion to add compare selection form:
    object_history_template = 'documento_eletronico/reversion-compare/object_history.html'

    def compare(self, obj, version1, version2):
        diff, has_unfollowed_fields = super().compare(obj, version1, version2)
        if hasattr(self, 'list_display_compare'):
            displayed_diff = []
            for diff_field in diff:
                if diff_field['field'].name in self.list_display_compare:
                    displayed_diff.append(diff_field)

            diff = displayed_diff
        return diff, has_unfollowed_fields


class TipoDocumentoFilter(admin.SimpleListFilter):
    title = 'Tipo'
    parameter_name = 'tipo'

    def lookups(self, request, model_admin):
        tipos = TipoDocumentoTexto.objects.filter(modelos__isnull=False).distinct()
        return tipos.order_by('nome').values_list('id', 'nome')

    def queryset(self, request, queryset):
        if self.value():
            try:
                return queryset.filter(modelo__tipo_documento_texto_id=self.value())
            except Exception:
                pass
        return queryset


class TipoDocumentoDigitalizadoFilter(admin.SimpleListFilter):
    title = 'Tipo'
    parameter_name = 'tipo'

    def lookups(self, request, model_admin):
        tipos = TipoDocumentoTexto.objects.filter(modelos__isnull=False).distinct()
        return tipos.order_by('nome').values_list('id', 'nome')

    def queryset(self, request, queryset):
        if self.value():
            try:
                return queryset.filter(tipo=self.value())
            except Exception:
                pass
        return queryset


class DashboardFilter(admin.SimpleListFilter):
    title = 'Agrupamento'
    parameter_name = 'opcao'

    TODOS = ('0',)
    # Opções do Dashboard
    MEUS_DOCUMENTOS = '1'
    FAVORITOS = '2'
    COMPARTILHADOS_COMIGO = '3'
    # ASSINATURA
    DOCUMENTOS_ESPERANDO_ASSINATURA = '4'
    DOCUMENTOS_ASSINADOS_POR_MIM = '5'
    SOLICITACOES_ASSINATURA = '8'
    # Revisão
    DOCUMENTOS_ESPERANDO_REVISAO = '6'
    DOCUMENTOS_REVISADOS = '7'
    SOLICITACOES_REVISAO = '9'
    VINCULADOS_A_MIM = '10'

    OPCOES = (
        (MEUS_DOCUMENTOS, 'Meus Documentos'),
        (FAVORITOS, 'Favoritos'),
        (COMPARTILHADOS_COMIGO, 'Compartilhados comigo'),
        (VINCULADOS_A_MIM, 'Documentos vinculados a mim'),
        # Assinatura
        (DOCUMENTOS_ESPERANDO_ASSINATURA, 'Documentos esperando assinatura'),
        (DOCUMENTOS_ASSINADOS_POR_MIM, 'Minhas assinaturas'),
        (SOLICITACOES_ASSINATURA, 'Minhas solicitações de assinatura'),
        # Revisão
        (DOCUMENTOS_ESPERANDO_REVISAO, 'Documentos esperando revisão'),
        (DOCUMENTOS_REVISADOS, 'Minhas revisões'),
        (SOLICITACOES_REVISAO, 'Minhas solicitações de revisão'),
    )

    def lookups(self, request, model_admin):
        return DashboardFilter.OPCOES

    def queryset(self, request: HttpRequest, queryset: QuerySet[DocumentoTexto]) -> QuerySet[DocumentoTexto]:
        # O agrupamento já foi aplicado na raiz da listagem (DocumentoTextoChangeList), antes dos filtros laterais (#17718).
        return queryset

    @staticmethod
    def filtrar(opcao: str, queryset: QuerySet[DocumentoTexto], user: User) -> QuerySet[DocumentoTexto]:
        """Os documentos de ``queryset`` na opção de agrupamento ``opcao`` para ``user``; opção desconhecida, nenhum."""
        # Montagem preguiçosa: algumas opções consultam o banco ao montar o filtro (esperando_assinatura materializa os
        # ids pendentes, compartilhados busca setores); só a opção escolhida deve rodar.
        switcher = {
            DashboardFilter.MEUS_DOCUMENTOS: lambda: queryset.proprios(user),
            DashboardFilter.FAVORITOS: lambda: queryset.filter(usuarios_marcadores_favoritos=user),
            DashboardFilter.COMPARTILHADOS_COMIGO: lambda: queryset.compartilhados(user),
            DashboardFilter.VINCULADOS_A_MIM: lambda: queryset.vinculados_a_mim(user),
            # Assinatura
            DashboardFilter.DOCUMENTOS_ESPERANDO_ASSINATURA: lambda: queryset.esperando_assinatura(user),
            DashboardFilter.DOCUMENTOS_ASSINADOS_POR_MIM: lambda: queryset.assinados(user),
            DashboardFilter.SOLICITACOES_ASSINATURA: lambda: queryset.assinatura_requisitada_por(user),
            # Revisao
            DashboardFilter.DOCUMENTOS_ESPERANDO_REVISAO: lambda: queryset.revisao_pendente(user),
            DashboardFilter.DOCUMENTOS_REVISADOS: lambda: queryset.revisados_por(user),
            DashboardFilter.SOLICITACOES_REVISAO: lambda: queryset.requisicao_pendente(user),
        }
        return switcher.get(opcao, queryset.none)()


class StatusListFilter(admin.SimpleListFilter):
    title = 'Status'
    parameter_name = 'status'

    def lookups(self, request, model_admin):
        return DocumentoStatus.STATUS_CHOICES

    def queryset(self, request, queryset):
        if self.value():
            # Se o valor for uma lista separada por vírgulas, converta para uma lista de inteiros
            status_values = [int(val) for val in self.value().split(',')]

            # Filtrar o queryset com base na lista de valores de status
            return queryset.filter(status__in=status_values)
        return queryset


class DocumentoTextoChangeList(ChangeListPlus):
    """Carrega as colunas da listagem de uma vez para a página exibida, em vez de uma consulta por linha (#17700).

    O prefetch fica no resultado paginado, não no ``get_queryset`` do admin: não entra no ``COUNT`` nem no
    ``date_hierarchy``, e não pesa em ``get_object``, ações e exportação, que usam o mesmo queryset. Cada prefetch é
    um ``IN`` sobre os ids da página, sem join na listagem (incidente #17674).
    """

    def get_queryset(self, request: HttpRequest) -> QuerySet[DocumentoTexto]:
        # Fica na listagem, não no get_queryset do admin, para não tirar do get_object documentos que o usuário edita sem
        # poder ler (revisor, solicitado da balizadora). Troca a raiz, e não só filtra o resultado, para que o total
        # "(N total)" e as opções dos filtros laterais com autocomplete, montadas da raiz (#17718), também se restrinjam.
        if not getattr(self, '_raiz_restrita', False):
            self.root_queryset = self._raiz(request)
            self._raiz_restrita = True
        return super().get_queryset(request)

    def _raiz(self, request: HttpRequest) -> QuerySet[DocumentoTexto]:
        # Com agrupamento, a opção escolhida, que já filtra pelo usuário. Sem, a visão geral: só o que o usuário pode
        # ler (#17699). O usuário externo já é restrito no get_queryset do admin.
        opcao = request.GET.get(DashboardFilter.parameter_name)
        if opcao:
            return DashboardFilter.filtrar(opcao, self.root_queryset, request.user)
        if request.user.get_vinculo().eh_usuario_externo():
            return self.root_queryset
        return self.root_queryset.legiveis_por(request.user)

    def get_results(self, request: HttpRequest) -> None:
        super().get_results(request)
        self.result_list = self.result_list.prefetch_related(
            'setor_dono',
            'assinatura_balizadora__assinatura',
            # format_profile(vinculo) só lê vinculo.pessoa: sem a pessoa_fisica inteira (#17687).
            Prefetch(
                'assinaturadocumentotexto_set',
                queryset=AssinaturaDocumentoTexto.objects.select_related('assinatura__vinculo__pessoa'),
                to_attr='assinaturas_listagem',
            ),
            Prefetch(
                'solicitacaoassinatura_set',
                queryset=SolicitacaoAssinatura.objects.select_related('solicitado__pessoa'),
                to_attr='solicitacoes_listagem',
            ),
            Prefetch(
                'registroacaodocumentotexto_set',
                queryset=RegistroAcaoDocumentoTexto.objects.filter(tipo=RegistroAcaoDocumentoTexto.TIPO_FINALIZACAO).order_by('-data'),
                to_attr='finalizacoes_listagem',
            ),
            Prefetch(
                'usuarios_marcadores_favoritos',
                queryset=User.objects.filter(pk=request.user.pk).only('pk'),
                to_attr='favoritado_listagem',
            ),
            # get_solicitacao_balizadora_pendente, do ícone de edição (has_change_permission → pode_editar) (#17710).
            Prefetch(
                'solicitacaoassinatura_set',
                # O tipo do vínculo, do solicitado.eh_aluno() de pode_editar (#17722).
                queryset=SolicitacaoAssinatura.objects.filter(status=SolicitacaoStatus.STATUS_ESPERANDO, condicionantes__isnull=True).select_related(
                    'solicitado__tipo_relacionamento'
                ),
                to_attr='balizadoras_pendentes_listagem',
            ),
        )
        # Avalia a página aqui: o cache do queryset guarda estas instâncias, que o template percorre. As checagens de
        # permissão de cada linha (assunto, assinaturas, ícones) passam a ler da página (#17710).
        documentos = list(self.result_list)
        permissoes = PermissoesPaginaListagem(request.user, documentos)
        for documento in documentos:
            documento.permissoes_listagem = permissoes


class DocumentoTextoPessoalChangeList(ChangeListPlus):
    """Carrega as datas da listagem de documentos pessoais de uma vez para a página exibida (#17709).

    Mesmo cuidado de ``DocumentoTextoChangeList``: o prefetch fica no resultado paginado, fora do ``COUNT`` e do
    ``date_hierarchy``.
    """

    def get_results(self, request: HttpRequest) -> None:
        super().get_results(request)
        self.result_list = self.result_list.prefetch_related(
            'assinatura_balizadora__assinatura',
            Prefetch(
                'registroacaodocumentotexto_set',
                queryset=RegistroAcaoDocumentoTexto.objects.filter(tipo=RegistroAcaoDocumentoTexto.TIPO_FINALIZACAO).order_by('-data'),
                to_attr='finalizacoes_listagem',
            ),
        )


class DocumentoTextoAdmin(ModelAdminPlus):
    list_display = (
        'setor_dono',
        'get_tipo_documento',
        'identificador',
        'get_assunto',
        'get_status',
        'get_nivel_acesso',
        'get_autor',
        'data_criacao',
        'get_assinaturas',
        'get_data_primeira_assinatura',
        'get_data_finalizacao',
        'get_favorito',
    )
    ordering = ['-data_criacao', '-identificador_numero']

    list_filter = (
        DashboardFilter,
        *get_uo_setor_listfilter(parametro_setor='setor_dono', title_setor='Setor Dono', title_uo=f'{nomenclatura.campus} Dono'),
        TipoDocumentoFilter,
        'modelo',
        'nivel_acesso',
        'hipotese_legal',
        StatusListFilter,
        'usuario_criacao',
        'interessados',
    )

    search_fields = [*DocumentoTexto.SEARCH_FIELDS, 'assunto', 'id']

    list_display_icons = True
    list_per_page = 32
    date_hierarchy = 'data_criacao'
    form = DocumentoTextoForm
    actions = ['excluir_documentos_rascunho', 'finalizar_documento_lote', 'assinar_documento_lote']

    fieldsets = (
        (
            'Dados do Documento',
            {'fields': ('tipo', 'modelo', 'assunto', 'setor_dono', 'classificacao')},
        ),
        ('Nível de Acesso', {'fields': ('instrucoes_gerais', 'ciencia_instrucoes_gerais', 'nivel_acesso', 'hipotese_legal')}),
    )

    def get_search_results(self, request, queryset, search_term):
        result, use_distinct = super().get_search_results(request, queryset, search_term)
        tipo = request.GET.get('tipo')
        if tipo and search_term and TipoDocumento.objects.filter(pk=tipo, permite_busca_corpo_conteudo=True).exists():
            return result | queryset.filter(corpo_indexado__contains=retira_acentos(search_term.lower())), use_distinct
        return result, use_distinct

    def get_actions(self, request):
        actions = super().get_actions(request)
        assinar_documento_lote = Configuracao.get_valor_por_chave('documento_eletronico', 'permite_assinatura_lote')
        if request.GET.get('opcao', None) != '4' or not assinar_documento_lote:
            actions.pop('assinar_documento_lote', None)
        permite_finalizacao_lote = Configuracao.get_valor_por_chave('documento_eletronico', 'permite_finalizacao_lote')
        if not permite_finalizacao_lote:
            actions.pop('permite_finalizacao_lote', None)
        return actions

    def assinar_documento_lote(self, request, queryset):
        ids = '-'.join(str(obj.id) for obj in queryset)
        return httprr(f'/documento_eletronico/assinar_documento_lote/?ids={ids}')

    assinar_documento_lote.short_description = 'Assinar documentos em lote'

    def excluir_documentos_rascunho(self, request, queryset):
        qtd_documentos_removidos = 0
        for documento in queryset:
            if not documento.pode_ser_excluido():
                continue

            if not documento.eh_documento_pessoal:
                if 'estagios' in settings.INSTALLED_APPS:
                    if DocumentoTexto.objects.filter(pk=documento.pk, praticaprofissional__isnull=False).exists():
                        continue
                if 'contratos' in settings.INSTALLED_APPS:
                    if not documento.estah_em_rascunho and (documento.medicoes_despacho.exists() or documento.medicoes_termo_definitivo.exists()):
                        continue

            try:
                # Garante que os anexos serao excluidos
                anexos_simples = documento.get_apenas_anexos_digitalizados_simples()
                for anexo_simples in anexos_simples:
                    anexo_simples.delete()

                documento.delete()
                qtd_documentos_removidos += 1
            except Exception:
                self.message_user(request, 'Documentos associados não podem ser removidos.', messages.WARNING)

        if qtd_documentos_removidos > 0:
            self.message_user(request, f'{qtd_documentos_removidos} documentos na situação rascunho foram removidos.')

    excluir_documentos_rascunho.short_description = 'Remover documentos/rascunhos selecionados'

    def finalizar_documento_lote(self, request, queryset):
        from .views import finalizar_documento

        qtd = 0
        for documento in queryset:
            if documento.pode_finalizar_documento(request.user):
                try:
                    finalizar_documento(request, documento.id)
                    qtd += 1
                except Exception:
                    pass
        self.message_user(request, f'Documentos finalizados com sucesso ({qtd}).')

    finalizar_documento_lote.short_description = 'Finalizar documentos selecionados'

    def get_assunto(self, obj):
        user = get_user()

        # Se o documento está finalizado, aplica a regra original:
        # mostra o assunto apenas para quem pode ler (se nível de acesso não for público)
        if obj.status == DocumentoStatus.STATUS_FINALIZADO:
            if obj.nivel_acesso != DocumentoTexto.NIVEL_ACESSO_PUBLICO and not obj.pode_ler(user):
                return 'Assunto Restrito'
            return obj.assunto

        # Se o documento NÃO está finalizado, mostra o assunto apenas para:
        # - Quem pode editar o documento
        # - Quem pode assinar o documento
        if obj.tem_permissao_editar(user) or obj.pode_assinar(user):
            return obj.assunto

        return 'Assunto restrito até a finalização do documento.'

    get_assunto.short_description = 'Assunto'

    def get_tipo_documento(self, obj):
        return obj.modelo.tipo_documento_texto.nome

    get_tipo_documento.short_description = 'Tipo de Documento'
    get_tipo_documento.admin_order_field = 'modelo__tipo_documento_texto'

    def get_status(self, obj):
        return format_html(status(obj.get_status()))

    get_status.short_description = 'Situação do Documento'
    get_status.admin_order_field = 'status'

    def get_nivel_acesso(self, obj):
        return format_html(status(obj.get_nivel_acesso_display()))

    get_nivel_acesso.short_description = 'Nível de Acesso'
    get_nivel_acesso.admin_order_field = 'nivel_acesso'

    def get_assinaturas(self, obj: DocumentoTexto) -> str:
        out = '-'
        user = get_user()
        if obj.nivel_acesso != DocumentoTexto.NIVEL_ACESSO_PUBLICO and not obj.pode_ler(user):
            return out
        # Carregadas por página em DocumentoTextoChangeList.
        assinaturas = obj.assinaturas_listagem
        solicitacoes = obj.solicitacoes_listagem
        total = len(assinaturas) + len(solicitacoes)
        if total < 5:
            if obj.status == DocumentoStatus.STATUS_FINALIZADO:
                out = f"""
                    <ul>
                        {''.join(['<li>' + format_profile(o.assinatura.vinculo, o.assinatura.vinculo.nome) + '</li>' for o in assinaturas])}
                    </ul>
                    """
            elif obj.status in [DocumentoStatus.STATUS_AGUARDANDO_ASSINATURA, DocumentoStatus.STATUS_ASSINADO]:
                out = f"""
                    <ul>
                        {''.join(['<li>' + format_profile(o.solicitado, o.solicitado.nome) + f'{status(o.get_status_display())}</li>' for o in solicitacoes])}
                    </ul>
                    """
        else:
            out = f'<ul>{total} assinaturas</ul>'
        return mark_safe(out)

    get_assinaturas.short_description = 'Assinaturas'

    def get_autor(self, obj):
        autor = obj.usuario_criacao.get_profile()
        return format_profile(autor, autor.nome_usual)

    get_autor.short_description = 'Autor'

    def get_data_primeira_assinatura(self, obj):
        data_primeira_assinatura = obj.get_data_primeira_assinatura()
        if data_primeira_assinatura:
            return data_primeira_assinatura
        return '-'

    get_data_primeira_assinatura.short_description = 'Data da Primeira Assinatura'
    get_data_primeira_assinatura.admin_order_field = 'assinatura_balizadora__assinatura__data_assinatura'

    def get_data_finalizacao(self, obj: DocumentoTexto) -> object:
        # Mesma regra de DocumentoTexto.get_data_finalizacao, sobre a finalização mais recente carregada por página.
        if obj.finalizacoes_listagem:
            return obj.finalizacoes_listagem[0].data
        return '-'

    get_data_finalizacao.short_description = 'Data de Finalização'

    def get_favorito(self, obj: DocumentoTexto) -> str:
        action = 'add'
        css = 'disabled'
        # A exportação CSV/XLS também chama esta coluna, sobre o queryset sem o prefetch do DocumentoTextoChangeList.
        if hasattr(obj, 'favoritado_listagem'):
            favoritado = bool(obj.favoritado_listagem)
        else:
            favoritado = obj.usuarios_marcadores_favoritos.filter(id=self.request.user.id).exists()
        if favoritado:
            action = 'remove'
            css = 'warning'
        return format_html(f"""
                <a href="/documento_eletronico/gerenciar_favoritos/{obj.pk}/{action}/" title="Adicionar aos Favoritos" class="star">
                    <span class="fas fa-star {css}" aria-hidden="true"></span><span class="visually-hidden">Adicionar aos Favoritos</span>
                </a>
            """)

    get_favorito.short_description = 'Favorito'

    def response_change(self, request, obj):
        if '_continue' in request.POST or '_addanother' in request.POST or 'fancybox' in request.GET or '_popup' in request.POST:
            return super().response_change(request, obj)
        else:
            url = reverse_lazy('visualizar_documento', kwargs={'documento_id': obj.id}, current_app='documento_eletronico')
            return httprr(url)

    def get_object(self, request, object_id, from_field=None):
        obj = super().get_object(request, object_id, from_field)
        # Caso exista o parâmatro "clonado", alguns atributos são zerados para forçar o usuário a informá-los.
        obj_clonado = request.GET.get('clonado', False)
        if obj_clonado and obj:
            obj.setor_dono = None
            obj.assunto = None
        return obj

    def get_changelist(self, request: HttpRequest, **kwargs: object) -> type[ChangeListPlus]:
        super().get_changelist(request, **kwargs)
        return DocumentoTextoChangeList

    def get_queryset(self, request: HttpRequest, *args: object, manager: object = None, **kwargs: object) -> QuerySet[DocumentoTexto]:
        qs = super().get_queryset(request, manager, *args, **kwargs)  # .by_user(usuario)

        # dependendo da opcao de agrupamento exclui ou nao documentos pessoais da listagem
        if request.GET.get('opcao') not in (
            DashboardFilter.DOCUMENTOS_ESPERANDO_ASSINATURA,
            DashboardFilter.DOCUMENTOS_ASSINADOS_POR_MIM,
            DashboardFilter.SOLICITACOES_ASSINATURA,
        ):
            qs = qs.impessoais()

        qs = qs.select_related('modelo__tipo_documento_texto')
        qs = qs.select_related('usuario_criacao__vinculo__pessoa__pessoafisica')

        # Se usuário externo restringe somente aos documentos vinculados ou com solicitações de assinatura
        if request.user.get_vinculo().eh_usuario_externo():
            qs1 = list(qs.compartilhados(request.user).values_list('pk', flat=True))
            qs2 = list(qs.assinados(request.user).values_list('pk', flat=True))
            qs3 = list(qs.esperando_assinatura(request.user).values_list('pk', flat=True))
            qs4 = list(qs.vinculados_a_mim(request.user).values_list('pk', flat=True))
            qs = qs.filter(pk__in=qs1 + qs2 + qs3 + qs4)

        return qs.only(
            'setor_dono',
            'modelo__tipo_documento_texto',
            'data_criacao',
            'identificador',
            'assunto',
            'status',
            'nivel_acesso',
            # Sem ele o prefetch da primeira assinatura carregaria o campo adiado linha a linha (#17700).
            'assinatura_balizadora',
            # Só o que o get_autor/format_profile exibe: a pessoa_fisica inteira (template da digital, senha do ponto...)
            # alargava cada linha da listagem (#17687).
            'usuario_criacao__vinculo__pessoa__nome',
            'usuario_criacao__vinculo__pessoa__nome_usual',
            'usuario_criacao__vinculo__pessoa__uuid',
            'usuario_criacao__vinculo__pessoa__pessoafisica__pessoa_ptr',
        )

    def response_add(self, request, obj, post_url_continue=None):
        super().response_add(request, obj, post_url_continue)
        return httprr(f'/documento_eletronico/visualizar_documento/{obj.id}/')

    def add_view(self, request, form_url='', extra_context=None):
        if not get_setores_compartilhados(request.user, NivelPermissao.EDITAR).exists():
            return httprr(
                '/admin/documento_eletronico/documentotexto',
                message='Você não tem permissão em nenhum Setor para adição de Documentos Eletrônicos. '
                'Entre em contato com o Chefe do setor pretendido, e solicite que o mesmo Gerencie o Compartilhamento de Documentos Eletrônicos do setor.',
                tag='error',
            )
        return super().add_view(request, form_url, extra_context)

    # Comentado para atender a nova funcionalidade de permissões do processo e documento eletrônico
    """
    def get_action_bar(self, request, remove_add_button=False):
        items = super(DocumentoTextoAdmin, self).get_action_bar(request, remove_add_button)
        usuario_logado = request.user.get_relacionamento()
        if request.user.eh_servidor and usuario_logado.eh_chefe_do_setor_hoje(usuario_logado.setor):
            for setor in Setor.objects.suap_ativos().filter(
                pk__in=usuario_logado.servidorfuncaohistorico_set.atuais()
                .filter(funcao__codigo__in=Funcao.get_codigos_funcao_chefia())
                .values_list('setor_suap_id', flat=True)
                .distinct()
            ):
                items.append(
                    dict(
                        url='/documento_eletronico/gerenciar_compartilhamento_setor/{0}/'.format(setor.id),
                        label='Gerenciar Compartilhamento: {0}'.format(setor),
                        css_class='popup primary',
                    )
                )
        return items
    """
    # Controle de permissões -------------------------------------------------------------------------------------------

    def has_add_permission(self, request):
        pode_cadastrar = get_setores_compartilhados(request.user, NivelPermissao.EDITAR).exists()
        return bool(pode_cadastrar)

    def has_view_permission(self, request, obj=None):
        if obj:
            return obj.pode_ler(request.user)
        return True

    def has_change_permission(self, request, obj=None):
        if obj:
            return obj.pode_editar(request.user)
        return True

    def has_delete_permission(self, request, obj=None):
        return obj and obj.pode_ser_excluido(request.user)


admin.site.register(DocumentoTexto, DocumentoTextoAdmin)


class DocumentoDigitalizadoAdmin(CompareVersionAdminPlus):
    def get_queryset(self, request, manager=None, *args, **kwargs):
        qs = super().get_queryset(request, *args, **kwargs)  # .by_user(usuario)
        # qs = qs.impessoais()  # excluíndo os documentos pessoais da listagem geral.
        return qs


admin.site.register(DocumentoDigitalizado, DocumentoDigitalizadoAdmin)

# Trata-se do "Tipo de Documento Externo".


class TipoDocumentoAdmin(ModelAdminPlus, CompareVersionAdmin):
    list_display = ('nome', 'sigla', 'ativo', 'permite_documentos_pessoais')
    search_fields = ('nome', 'sigla')
    list_display_icons = True
    list_filter = ('permite_documentos_pessoais',)
    form = TipoDocumentoForm
    change_form_template = 'documento_eletronico/templates/adminutils/change_form.html'


admin.site.register(TipoDocumento, TipoDocumentoAdmin)


# Trata-se do "Tipo de Documento Interno", que possui cabeçalho e rodapé.
class TipoDocumentoTextoAdmin(ModelAdminPlus, CompareVersionAdmin):
    list_display = (
        'nome',
        'sigla',
        'ativo',
        'vincular_pessoa',
        'permite_documentos_pessoais',
        'permite_documentos_anexos',
        'consulta_publica',
        'get_opcoes',
    )
    search_fields = ('nome', 'sigla')
    list_display_icons = True
    list_filter = (
        'vincular_pessoa',
        'permite_documentos_pessoais',
        'permite_documentos_anexos',
        'consulta_publica',
    )
    safe_view = True
    form = TipoDocumentoTextoForm
    add_form = TipoDocumentoTextoAddForm

    change_form_template = 'documento_eletronico/templates/adminutils/change_form.html'

    def get_opcoes(self, obj):
        opcoes = f'<li><a href="/documento_eletronico/clonar_tipo_documento/{obj.pk:d}/" class="btn primary">Clonar</a></li>'
        opcoes += f'<li><a href="/admin/documento_eletronico/modelodocumento/?tipo_documento_texto={obj.pk:d}" class="btn default">Lista de Modelos</a></li>'
        return mark_safe(f'<ul class="action-bar">{opcoes}</ul>')

    get_opcoes.short_description = 'Opções'
    get_opcoes.attrs = {'class': 'no-print'}


admin.site.register(TipoDocumentoTexto, TipoDocumentoTextoAdmin)


class ModeloDocumentoAdmin(ModelAdminPlus, CompareVersionAdminPlus):
    list_display = (
        'get_tipo_documento',
        'nome',
        'ativo',
        'permite_nivel_acesso_sigiloso',
        'permite_nivel_acesso_restrito',
        'permite_nivel_acesso_publico',
        'get_nivel_acesso_padrao',
        'get_opcoes',
    )
    search_fields = ('nome',)
    list_filter = ('tipo_documento_texto', 'permite_nivel_acesso_sigiloso', 'permite_nivel_acesso_restrito', 'permite_nivel_acesso_publico')
    list_display_icons = True
    safe_view = True
    form = ModeloDocumentoForm
    fieldsets = ModeloDocumentoForm.fieldsets

    def get_nivel_acesso_padrao(self, obj):
        return obj.get_nivel_acesso_padrao_display()

    get_nivel_acesso_padrao.admin_order_field = 'nivel_acesso_padrao'
    get_nivel_acesso_padrao.short_description = 'Nível de Acesso Padrão'

    def get_tipo_documento(self, obj):
        return obj.tipo_documento_texto.nome

    get_tipo_documento.admin_order_field = 'tipo_documento_texto__nome'
    get_tipo_documento.short_description = 'Tipo de Documento'

    def get_opcoes(self, obj):
        opcoes = f'<li><a href="/documento_eletronico/clonar_modelo_documento/{obj.pk:d}/" class="btn primary">Clonar</a></li>'
        opcoes += f'<li><a href="/admin/documento_eletronico/modelodocumento/{obj.pk:d}/delete/" class="btn danger">Apagar</a></li>'
        return mark_safe(f'<ul class="action-bar">{opcoes}</ul>')

    #
    get_opcoes.short_description = 'Opções'
    get_opcoes.attrs = {'class': 'no-print'}

    def save_model(self, request, obj, form, change):
        obj.setor_dono = get_setor(request.user)
        super().save_model(request, obj, form, change)

    def response_add(self, request, obj, post_url_continue=None):
        super().response_add(request, obj, post_url_continue)
        return httprr(f'/documento_eletronico/editar_modelo_documento/{obj.id:d}/')

    def change_view(self, request, object_id, form_url='', extra_context=None):
        return httprr(f'/documento_eletronico/editar_modelo_documento/{object_id}/')


admin.site.register(ModeloDocumento, ModeloDocumentoAdmin)


class HipoteseLegalAdmin(ModelAdminPlus):
    list_display = ('descricao', 'base_legal', 'nivel_acesso')
    search_fields = ('descricao',)


admin.site.register(HipoteseLegal, HipoteseLegalAdmin)


class ClassificacaoAdmin(ModelAdminPlus, MPTTModelAdmin):
    list_display = ('get_descricao', 'suficiente_para_classificar_processo', 'ativo', 'mec', 'migrado')
    search_fields = ('codigo', 'descricao')
    list_filter = ('ativo', 'mec', 'migrado')
    list_display_icons = True

    def get_descricao(self, obj):
        return mark_safe('<span class="sublevel">{}|---</span> {}'.format(obj.get_level() * '&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;', obj))

    #
    get_descricao.short_description = 'Descrição'


admin.site.register(Classificacao, ClassificacaoAdmin)


class TipoConferenciaAdmin(ModelAdminPlus):
    search_fields = ('descricao',)


admin.site.register(TipoConferencia, TipoConferenciaAdmin)


class ConfiguracaoVinculoDocumentoForm(django_forms.ModelForm):
    class Meta:
        model = ConfiguracaoVinculoDocumento
        fields = ('tipo_vinculo_documento', 'tipo_documento_alvo', 'tipo_documento_base', 'modelo_padrao', 'ativo')
        labels = {
            'tipo_documento_base': 'Tipo do novo documento',
            'tipo_documento_alvo': 'Tipo do documento original/alvo',
        }
        help_texts = {
            'tipo_documento_base': 'Tipo do documento que será criado e praticará a ação.',
            'tipo_documento_alvo': 'Tipo do documento finalizado a partir do qual a ação será iniciada.',
        }


class ConfiguracaoVinculoDocumentoInline(admin.StackedInline):
    model = ConfiguracaoVinculoDocumento
    form = ConfiguracaoVinculoDocumentoForm
    extra = 1
    fields = ('tipo_documento_alvo', 'tipo_documento_base', 'modelo_padrao', 'ativo')
    show_change_link = True
    can_delete = False

    def has_view_permission(self, request: HttpRequest, obj=None) -> bool:
        return request.user.has_perm('documento_eletronico.view_tipovinculodocumento')

    def has_add_permission(self, request: HttpRequest, obj=None) -> bool:
        return request.user.has_perm('documento_eletronico.change_tipovinculodocumento')

    def has_change_permission(self, request: HttpRequest, obj=None) -> bool:
        return request.user.has_perm('documento_eletronico.change_tipovinculodocumento')

    def has_delete_permission(self, request: HttpRequest, obj=None) -> bool:
        return False


class TipoVinculoDocumentoAdmin(ModelAdminPlus, CompareVersionAdmin):
    search_fields = ('descricao',)
    list_display = ('descricao', 'descricao_voz_ativa', 'descricao_voz_passiva', 'modo_uso', 'get_opcoes')
    list_filter = ('modo_uso',)
    inlines = (ConfiguracaoVinculoDocumentoInline,)

    def get_opcoes(self, obj: TipoVinculoDocumento) -> str:
        return mark_safe(
            f'<ul class="action-bar"><li><a class="btn" '
            f'href="/admin/documento_eletronico/configuracaovinculodocumento/?tipo_vinculo_documento={obj.pk}">Configurações</a></li></ul>'
        )

    get_opcoes.short_description = 'Opções'
    get_opcoes.attrs = {'class': 'no-print'}


admin.site.register(TipoVinculoDocumento, TipoVinculoDocumentoAdmin)


class ConfiguracaoVinculoDocumentoAdmin(ModelAdminPlus, CompareVersionAdmin):
    form = ConfiguracaoVinculoDocumentoForm
    list_display = (
        'tipo_vinculo_documento',
        'get_tipo_documento_original',
        'get_tipo_novo_documento',
        'modelo_padrao',
        'ativo',
    )
    list_filter = ('tipo_vinculo_documento', 'ativo')
    search_fields = ('tipo_documento_base__nome', 'tipo_documento_alvo__nome', 'tipo_vinculo_documento__descricao')
    list_display_icons = True

    def has_delete_permission(self, request: HttpRequest, obj=None) -> bool:
        return False

    @admin.display(description='Tipo do novo documento', ordering='tipo_documento_base')
    def get_tipo_novo_documento(self, obj: ConfiguracaoVinculoDocumento) -> TipoDocumentoTexto:
        return obj.tipo_documento_base

    @admin.display(description='Tipo do documento original/alvo', ordering='tipo_documento_alvo')
    def get_tipo_documento_original(self, obj: ConfiguracaoVinculoDocumento) -> TipoDocumentoTexto:
        return obj.tipo_documento_alvo


admin.site.register(ConfiguracaoVinculoDocumento, ConfiguracaoVinculoDocumentoAdmin)


class CompartilhamentoDocumentoPessoaAdmin(ModelAdminPlus):
    list_filter = ('documento',)
    search_fields = ('documento__identificador', 'vinculo_permitido__pessoa__nome')
    list_display = ('documento', 'vinculo_permitido', 'nivel_permissao', 'data_criacao', 'usuario_criacao')
    list_display_icons = True

    form = CompartilhamentoDocumentosPessoaForm

    def get_pessoa(self, obj):
        return f'{obj.vinculo_permitido.pessoa.nome}'

    #
    get_pessoa.short_description = 'Pessoa'


admin.site.register(CompartilhamentoDocumentoPessoa, CompartilhamentoDocumentoPessoaAdmin)


class CompartilhamentoSetorPessoaAdmin(ModelAdminPlus):
    list_filter = ('setor_dono',)
    search_fields = ('setor_dono__sigla', 'vinculo_permitido__pessoa__nome')
    list_display = ('setor_dono', 'vinculo_permitido', 'nivel_permissao', 'data_criacao', 'usuario_criacao')
    list_display_icons = True

    form = CompartilhamentoDocumentosSetorPessoaForm


admin.site.register(CompartilhamentoSetorPessoa, CompartilhamentoSetorPessoaAdmin)


class DocumentoTextualPessoalAuditorFilter(admin.SimpleListFilter):
    title = 'Agrupamento'
    parameter_name = 'opcao'

    TODOS = ('0',)
    # Opções do Dashboard
    MEUS_DOCUMENTOS = '1'

    OPCOES = ((MEUS_DOCUMENTOS, 'Meus Documentos'),)

    def lookups(self, request, model_admin):
        return DocumentoTextualPessoalAuditorFilter.OPCOES

    def queryset(self, request, queryset):
        switcher = {
            DocumentoTextualPessoalAuditorFilter.MEUS_DOCUMENTOS: queryset.proprios(request.user),
        }

        if self.value():
            return switcher.get(self.value(), queryset.none())
        return queryset


class DocumentoTextoPessoalAdmin(ModelAdminPlus):
    list_display_icons = True
    list_display = (
        'get_tipo_documento',
        'identificador',
        'get_assunto',
        'get_status',
        'get_nivel_acesso',
        'get_dono',
        'data_criacao',
        'get_data_primeira_assinatura',
        'get_data_finalizacao',
    )
    ordering = ['-data_criacao', '-identificador_numero']
    list_per_page = 32
    date_hierarchy = 'data_criacao'
    search_fields = [*DocumentoTexto.SEARCH_FIELDS, 'assunto', 'id']

    form = DocumentoTextoPessoalForm

    fieldsets = (
        (
            'Dados do Documento',
            {'fields': ('tipo', 'modelo', 'assunto', 'classificacao')},
        ),
        ('Nível de Acesso', {'fields': ('instrucoes_gerais', 'ciencia_instrucoes_gerais', 'nivel_acesso', 'hipotese_legal')}),
    )

    # ------------------------
    # LIST DISPLAY
    # ------------------------

    def changelist_view(self, request, extra_context=None):
        referrer = request.META.get('HTTP_REFERER', '')
        if len(request.GET) == 0 and '?' not in referrer:
            if self._possui_acesso_pelo_cargo(request.user):
                get_param = 'opcao=1'
                return redirect(f'{request.path}?{get_param}')
        return super().changelist_view(request, extra_context=extra_context)

    def get_assunto(self, obj):
        user = get_user()

        # Se o documento está finalizado, aplica a regra original:
        # mostra o assunto apenas para quem pode ler (se nível de acesso não for público)
        if obj.status == DocumentoStatus.STATUS_FINALIZADO:
            if obj.nivel_acesso != DocumentoTexto.NIVEL_ACESSO_PUBLICO and not obj.pode_ler(user):
                return 'Assunto Restrito'
            return obj.assunto

        # Se o documento NÃO está finalizado, mostra o assunto apenas para:
        # - Quem pode editar o documento (prioriza permissões por compartilhamento)
        # - Quem pode assinar o documento
        if (hasattr(obj, 'tem_permissao_editar') and obj.tem_permissao_editar(user)) or obj.pode_editar(user) or obj.pode_assinar(user):
            return obj.assunto

        return 'Assunto Restrito'

    get_assunto.short_description = 'Assunto'

    def get_tipo_documento(self, obj):
        return obj.modelo.tipo_documento_texto.nome

    get_tipo_documento.short_description = 'Tipo de Documento'
    get_tipo_documento.admin_order_field = 'modelo__tipo_documento_texto'

    def get_status(self, obj):
        return format_html(status(obj.get_status()))

    get_status.short_description = 'Situação do Documento'
    get_status.admin_order_field = 'status'

    def get_nivel_acesso(self, obj):
        return format_html(status(obj.get_nivel_acesso_display()))

    get_nivel_acesso.short_description = 'Nível de Acesso'
    get_nivel_acesso.admin_order_field = 'nivel_acesso'

    def get_assinado_por(self, obj: DocumentoTexto) -> str:
        assinaturas = obj.assinaturadocumentotexto_set.select_related('assinatura__vinculo__pessoa')
        return ', '.join([format_profile(o.assinatura.pessoa, o.assinatura.pessoa.nome) for o in assinaturas])

    get_assinado_por.short_description = 'Assinado por'

    def get_dono(self, obj: DocumentoTexto) -> str:
        dono = obj.usuario_criacao.get_profile()
        return format_profile(dono, dono.nome_usual)

    get_dono.short_description = 'Dono'

    def get_data_primeira_assinatura(self, obj: DocumentoTexto) -> object:
        # Carregada por página em DocumentoTextoPessoalChangeList (assinatura_balizadora__assinatura).
        return obj.get_data_primeira_assinatura() or '-'

    get_data_primeira_assinatura.short_description = 'Data da Primeira Assinatura'

    def get_data_finalizacao(self, obj: DocumentoTexto) -> object:
        # Mesma regra de DocumentoTexto.get_data_finalizacao, sobre a finalização mais recente carregada por página.
        # A exportação CSV/XLS não passa pela changelist: sem o cache, cai na consulta do model.
        if hasattr(obj, 'finalizacoes_listagem'):
            return obj.finalizacoes_listagem[0].data if obj.finalizacoes_listagem else '-'
        return obj.get_data_finalizacao() or '-'

    get_data_finalizacao.short_description = 'Data de Finalização'

    # ------------------------
    # METODOS
    # ------------------------

    def _possui_acesso_pelo_cargo(self, user):
        return eh_auditor(user) or eh_procurador(user)

    def get_list_filter(self, request):
        list_filter = ('nivel_acesso', 'status', TipoDocumentoFilter)
        if self._possui_acesso_pelo_cargo(request.user):
            list_filter += (DocumentoTextualPessoalAuditorFilter,)
        return list_filter

    def response_change(self, request, obj):
        if '_continue' in request.POST or '_addanother' in request.POST or 'fancybox' in request.GET or '_popup' in request.POST:
            return super().response_change(request, obj)
        else:
            url = reverse_lazy('visualizar_documento', kwargs={'documento_id': obj.id}, current_app='documento_eletronico')
            return httprr(url)

    def get_object(self, request, object_id, from_field=None):
        obj = super().get_object(request, object_id, from_field)
        # Caso exista o parâmatro "clonado", alguns atributos são zerados para forçar o usuário a informá-los.
        obj_clonado = request.GET.get('clonado', False)
        if obj_clonado and obj:
            obj.assunto = None
        return obj

    def get_changelist(self, request: HttpRequest, **kwargs: object) -> type[ChangeListPlus]:
        super().get_changelist(request, **kwargs)
        return DocumentoTextoPessoalChangeList

    def get_queryset(self, request, *args, manager=None, **kwargs):
        qs = super().get_queryset(request, manager, *args, **kwargs)  # .by_user(usuario)
        if not self._possui_acesso_pelo_cargo(request.user):
            qs = qs.filter(usuario_criacao=request.user)
        #
        qs = qs.select_related('modelo__tipo_documento_texto')
        qs = qs.select_related('usuario_criacao__vinculo__pessoa__pessoafisica')

        # identificador, data_criacao, setor_dono e assinatura_balizadora são lidos por linha (coluna, permissão e prefetch
        # da primeira assinatura): adiados, cada um viraria uma consulta por documento (#17709).
        return qs.only(
            'modelo__tipo_documento_texto',
            'assunto',
            'status',
            'nivel_acesso',
            'identificador',
            'data_criacao',
            'setor_dono',
            'assinatura_balizadora',
            'usuario_criacao__vinculo__pessoa__pessoafisica',
        )

    def response_add(self, request, obj, post_url_continue=None):
        return httprr(f'/documento_eletronico/visualizar_documento/{obj.id}/')

    def has_view_permission(self, request, obj=None):
        has_view_permission = super().has_view_permission(request, obj)
        if has_view_permission and obj:
            return obj.pode_ler(request.user)
        return has_view_permission

    def has_change_permission(self, request, obj=None):
        has_change_permission = super().has_change_permission(request, obj)
        if has_change_permission and obj:
            return obj.pode_editar(request.user)
        return has_change_permission

    def has_delete_permission(self, request, obj=None):
        has_delete_permission = super().has_delete_permission(request, obj)
        return has_delete_permission and obj and obj.pode_ser_excluido(request.user)


admin.site.register(DocumentoTextoPessoal, DocumentoTextoPessoalAdmin)


class DocumentoDigitalizadoPessoalAuditorFilter(admin.SimpleListFilter):
    title = 'Agrupamento'
    parameter_name = 'opcao'

    TODOS = ('0',)
    # Opções do Dashboard
    MEUS_DOCUMENTOS = '1'

    OPCOES = ((MEUS_DOCUMENTOS, 'Meus Documentos'),)

    def lookups(self, request, model_admin):
        return DocumentoDigitalizadoPessoalAuditorFilter.OPCOES

    def queryset(self, request, queryset):
        switcher = {
            DocumentoDigitalizadoPessoalAuditorFilter.MEUS_DOCUMENTOS: queryset.filter(usuario_criacao=request.user),
        }

        if self.value():
            return switcher.get(self.value(), queryset.none())
        return queryset


class DocumentoDigitalizadoPessoalAdmin(ModelAdminPlus):
    list_display_icons = True
    form = DocumentoPessoalDigitalizadoForm

    list_per_page = 25
    date_hierarchy = 'data_criacao'
    ordering = ('-data_criacao',)
    search_fields = ('assunto',)

    fieldsets = (
        ('Dados do documento', {'fields': ('tipo', 'assunto')}),
        ('Nível de Acesso', {'fields': ('instrucoes_gerais', 'ciencia_instrucoes_gerais', 'nivel_acesso', 'hipotese_legal')}),
    )

    fieldsets_add = (
        ('Dados do documento', {'fields': ('tipo', 'arquivo', 'tipo_conferencia', 'assunto')}),
        ('Nível de Acesso', {'fields': ('instrucoes_gerais', 'ciencia_instrucoes_gerais', 'nivel_acesso', 'hipotese_legal')}),
        (
            'Dados Adicionais',
            {'fields': (('identificador_numero', 'identificador_ano'), 'identificador_setor_sigla', 'identificador_tipo_documento_sigla')},
        ),
        (
            'Assinatura',
            {
                'fields': (
                    'papel',
                    'senha',
                )
            },
        ),
    )

    def _possui_acesso_pelo_cargo(self, user):
        return user.has_group_cached('Auditor')

    def get_list_display(self, request):
        list_display = (*super().get_list_display(request), 'assunto', 'tipo')
        if self._possui_acesso_pelo_cargo(request.user):
            list_display += ('dono_documento',)
        return (*list_display, 'nivel_acesso', 'data_criacao')

    def get_list_filter(self, request):
        list_filter = ('nivel_acesso', TipoDocumentoDigitalizadoFilter)
        if self._possui_acesso_pelo_cargo(request.user):
            list_filter += (
                'dono_documento',
                DocumentoDigitalizadoPessoalAuditorFilter,
            )
        return list_filter

    def save_model(self, request, obj, form, change):
        sid = transaction.savepoint()
        try:
            is_insert = not obj.id

            if is_insert:
                obj.data_criacao = get_datetime_now()
                obj.usuario_criacao = request.user
                obj.dono_documento = request.user.get_vinculo()
            obj.data_ultima_modificacao = get_datetime_now()
            obj.usuario_ultima_modificacao = request.user

            obj.save()

            if is_insert:
                papel = form.cleaned_data.get('papel')
                obj.assinar_via_senha(request.user, papel)

            transaction.savepoint_commit(sid)
        except Exception as e:
            transaction.savepoint_rollback(sid)
            raise ValidationError(f'{e}')

    def get_fieldsets(self, request, obj=None):
        if obj:
            return self.fieldsets
        else:
            return self.fieldsets_add

    def get_queryset(self, request, *args, manager=None, **kwargs):
        qs = super().get_queryset(request, manager, *args, **kwargs)
        if not self._possui_acesso_pelo_cargo(request.user):
            qs = qs.filter(usuario_criacao=request.user)
        return qs

    def has_view_permission(self, request, obj=None):
        has_view_permission = super().has_view_permission(request, obj)
        if has_view_permission and obj:
            return obj.pode_ler(request.user)
        return has_view_permission

    def has_change_permission(self, request, obj=None):
        has_change_permission = super().has_change_permission(request, obj)
        if has_change_permission and obj:
            return obj.pode_editar(request.user)
        return False

    def add_view(self, request, form_url='', extra_context=None):
        # Cria papel (quando ele ainda não existe)
        # - para que alunos possam criar documentos pessoais
        # - para que alunos possam executar as outras operações relacionadas ao documento pessoal
        vinculo = request.user.get_vinculo()
        if vinculo.eh_aluno():
            vinculo.relacionamento.criar_papel_discente()
        return super().add_view(request, form_url, extra_context)

    def changelist_view(self, request, extra_context=None):
        referrer = request.META.get('HTTP_REFERER', '')
        if len(request.GET) == 0 and '?' not in referrer:
            if self._possui_acesso_pelo_cargo(request.user):
                get_param = 'opcao=1'
                return redirect(f'{request.path}?{get_param}')
        return super().changelist_view(request, extra_context=extra_context)


admin.site.register(DocumentoDigitalizadoPessoal, DocumentoDigitalizadoPessoalAdmin)


class DocumentoDigitalizadoAnexoSimplesAdmin(ModelAdminPlus):
    add_form = DocumentoDigitalizadoAnexoSimplesForm

    def save_model(
        self, request: HttpRequest, obj: DocumentoDigitalizadoAnexoSimples, form: DocumentoDigitalizadoAnexoSimplesForm, change: bool
    ) -> None:
        sid = transaction.savepoint()
        try:
            documento_id = request.GET.get('documento_id')
            documento = get_documento_or_forbidden(request.user, documento_id)

            # Salva o anexo
            obj.usuario_criacao = request.user
            obj.data_ultima_modificacao = get_datetime_now()
            obj.usuario_ultima_modificacao = request.user
            obj.anexo_simples = True
            obj.save()
            obj.assinar_via_senha(request.user, form.cleaned_data.get('papel'))

            # Vincula como anexo
            d = DocumentoTextoAnexoDocumentoDigitalizado()
            d.documento = documento
            d.documento_anexado = obj
            d.save()

            transaction.savepoint_commit(sid)
        except Exception as e:
            transaction.savepoint_rollback(sid)
            raise ValidationError(f'{e}')

    def response_add(self, request, obj, post_url_continue=None):
        documento_id = request.GET.get('documento_id')
        return httprr(f'/documento_eletronico/visualizar_documento/{documento_id}/')

    def add_view(self, request, form_url='', extra_context=None):
        documento_id = request.GET.get('documento_id')

        # documento = get_object_or_404(DocumentoTexto, pk=documento_id)
        documento = get_documento_or_forbidden(request.user, documento_id)

        if not documento.pode_receber_anexos():
            raise PermissionDenied
        extra_context = extra_context or {}
        extra_context['title'] = f'Adicionar anexo para o documento {documento}'
        return super(ModelAdminPlus, self).add_view(request, form_url, extra_context)


admin.site.register(DocumentoDigitalizadoAnexoSimples, DocumentoDigitalizadoAnexoSimplesAdmin)
