from django.contrib import admin
from django.utils.html import format_html

from djtools.contrib.admin import ModelAdminPlus

from rsc_tae.models import BancoPontosRSCTae, MovimentoBancoPontosRSCTae


class MovimentoBancoPontosInline(admin.TabularInline):
    model = MovimentoBancoPontosRSCTae
    extra = 0
    readonly_fields = (
        'tipo',
        'valor',
        'saldo_apos',
        'processo',
        'descricao',
        'realizado_por_vinculo',
        'data_movimento',
    )
    fields = readonly_fields
    ordering = ('-data_movimento',)
    max_num = 0
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(BancoPontosRSCTae)
class BancoPontosRSCTaeAdmin(ModelAdminPlus):
    list_display = (
        'get_servidor',
        'get_campus',
        'saldo',
        'data_atualizacao',
        'get_total_movimentos',
    )
    list_display_icons = True
    search_fields = ('vinculo__pessoa__nome',)
    ordering = ('vinculo__pessoa__nome',)
    readonly_fields = ('vinculo', 'saldo', 'data_atualizacao')
    inlines = [MovimentoBancoPontosInline]

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('vinculo__pessoa', 'vinculo__setor__uo').prefetch_related('movimentos')

    @admin.display(description='Servidor')
    def get_servidor(self, obj):
        try:
            return obj.vinculo.pessoa.nome
        except Exception:
            return '—'

    @admin.display(description='Campus')
    def get_campus(self, obj):
        try:
            return obj.vinculo.setor.uo.sigla
        except Exception:
            return '—'

    @admin.display(description='Movimentos')
    def get_total_movimentos(self, obj):
        return obj.movimentos.count()

    def has_add_permission(self, request):
        return request.user.is_superuser

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser


@admin.register(MovimentoBancoPontosRSCTae)
class MovimentoBancoPontosRSCTaeAdmin(ModelAdminPlus):
    list_display = (
        'get_servidor',
        'get_tipo_display',
        'valor',
        'saldo_apos',
        'processo',
        'realizado_por_vinculo',
        'data_movimento',
    )
    list_display_icons = True
    list_filter = ('tipo',)
    search_fields = (
        'banco__vinculo__pessoa__nome',
        'descricao',
    )
    ordering = ('-data_movimento',)
    readonly_fields = (
        'banco',
        'tipo',
        'valor',
        'saldo_apos',
        'processo',
        'descricao',
        'realizado_por_vinculo',
        'data_movimento',
    )
    date_hierarchy = 'data_movimento'

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .select_related(
                'banco__vinculo__pessoa',
                'processo__vinculo__pessoa',
                'realizado_por_vinculo__pessoa',
            )
        )

    @admin.display(description='Servidor')
    def get_servidor(self, obj):
        try:
            return obj.banco.vinculo.pessoa.nome
        except Exception:
            return '—'

    @admin.display(description='Tipo')
    def get_tipo_display(self, obj):
        if obj.eh_credito:
            return format_html('<span class="status status-success">{}</span>', obj.get_tipo_display())
        return format_html('<span class="status status-error">{}</span>', obj.get_tipo_display())

    def has_add_permission(self, request):
        return request.user.is_superuser

    def has_change_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser
