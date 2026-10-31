from django.contrib import admin
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.utils.html import format_html

from djtools.contrib.admin import ModelAdminPlus

from rsc_tae.enums import SituacaoDocumentoPreliminar
from rsc_tae.models import AvaliacaoDocumentoPreliminarRSCTae, DocumentoPreliminarRSCTae, DocumentoPreliminarRSCTaeLog


def _situacao_doc_label(situacao):
    for valor, label in SituacaoDocumentoPreliminar.get_choices():
        if int(valor) == int(situacao or 0):
            return label
    return '-'


@admin.register(DocumentoPreliminarRSCTae)
class DocumentoPreliminarRSCTaeAdmin(ModelAdminPlus):
    list_display_icons = True
    actions = ('excluir_selecionados',)

    list_display = (
        'processo',
        'tipo',
        'data_obtencao_titulacao',
        'get_situacao',
        'get_arquivo',
        'nome_original',
        'cadastrado_por_vinculo',
        'data_cadastro',
    )
    search_fields = (
        'processo__vinculo__pessoa__nome',
        'processo__vinculo__pessoa__pessoafisica__servidor_set__matricula',
        'nome_original',
        'arquivo',
    )
    list_filter = (
        'tipo',
        'data_cadastro',
        'cadastrado_por_vinculo',
    )
    ordering = ('-data_cadastro',)

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('processo', 'processo__vinculo', 'cadastrado_por_vinculo', 'avaliacao')

    @admin.display(description='Situação')
    def get_situacao(self, obj: DocumentoPreliminarRSCTae):
        return _situacao_doc_label(getattr(obj, 'situacao', None))

    @admin.display(description='Arquivo')
    def get_arquivo(self, obj: DocumentoPreliminarRSCTae):
        if not getattr(obj, 'arquivo', None):
            return '-'
        name = obj.nome_original or obj.arquivo.name
        try:
            url = obj.arquivo.url
        except Exception:
            url = ''
        if url:
            return format_html('<a href="{}" target="_blank" rel="noopener">{}</a>', url, name)
        return name

    @admin.action(description='Excluir selecionados')
    def excluir_selecionados(self, request, queryset):
        if not self.has_delete_permission(request):
            raise PermissionDenied

        total = queryset.count()
        queryset.delete()
        self.message_user(request, f'{total} registro(s) excluído(s) com sucesso.', level=messages.SUCCESS)


@admin.register(AvaliacaoDocumentoPreliminarRSCTae)
class AvaliacaoDocumentoPreliminarRSCTaeAdmin(ModelAdminPlus):
    list_display_icons = True
    actions = ('excluir_selecionados',)

    list_display = (
        'documento',
        'get_processo',
        'situacao',
        'avaliado_por_vinculo',
        'data_avaliacao',
        'data_ultima_alteracao',
        'ip_avaliacao',
    )
    search_fields = (
        'documento__nome_original',
        'documento__arquivo',
        'documento__processo__vinculo__pessoa__nome',
        'documento__processo__vinculo__pessoa__pessoafisica__servidor_set__matricula',
    )
    list_filter = (
        'situacao',
        'data_avaliacao',
        'avaliado_por_vinculo',
    )
    ordering = ('-data_avaliacao',)

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('documento', 'documento__processo', 'avaliado_por_vinculo')

    @admin.display(description='Processo')
    def get_processo(self, obj: AvaliacaoDocumentoPreliminarRSCTae):
        try:
            return obj.documento.processo
        except Exception:
            return '-'

    @admin.action(description='Excluir selecionados')
    def excluir_selecionados(self, request, queryset):
        if not self.has_delete_permission(request):
            raise PermissionDenied

        total = queryset.count()
        queryset.delete()
        self.message_user(request, f'{total} registro(s) excluído(s) com sucesso.', level=messages.SUCCESS)


@admin.register(DocumentoPreliminarRSCTaeLog)
class DocumentoPreliminarRSCTaeLogAdmin(ModelAdminPlus):
    list_display_icons = True

    list_display = (
        'processo',
        'documento',
        'acao',
        'executado_por_vinculo',
        'ip',
        'data_cadastro',
        'get_observacao_curta',
    )
    search_fields = (
        'processo__vinculo__pessoa__nome',
        'processo__vinculo__pessoa__pessoafisica__servidor_set__matricula',
        'documento__nome_original',
        'documento__arquivo',
        'executado_por_vinculo__pessoa__nome',
        'observacao',
    )
    list_filter = (
        'acao',
        'data_cadastro',
        'executado_por_vinculo',
    )
    ordering = ('-data_cadastro',)
    readonly_fields = (
        'processo',
        'documento',
        'acao',
        'executado_por_vinculo',
        'ip',
        'user_agent',
        'observacao',
        'data_cadastro',
    )

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('processo', 'documento', 'executado_por_vinculo')

    def has_add_permission(self, request):
        return request.user.is_superuser

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser

    @admin.display(description='Observação')
    def get_observacao_curta(self, obj: DocumentoPreliminarRSCTaeLog):
        txt = (getattr(obj, 'observacao', None) or '').strip()
        if not txt:
            return '-'
        return (txt[:97] + '...') if len(txt) > 100 else txt
