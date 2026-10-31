import datetime

from django.contrib import admin
from django.utils.html import format_html

from djtools.contrib.admin import ModelAdminPlus

from rsc_tae.models import AvaliadorAuxiliarRSCTae


@admin.register(AvaliadorAuxiliarRSCTae)
class AvaliadorAuxiliarRSCTaeAdmin(ModelAdminPlus):
    list_display = (
        'vinculo',
        'get_campus',
        'data_habilitacao',
        'get_situacao',
        'get_disponibilidade',
        'data_inativacao',
        'cadastrado_por_vinculo',
    )
    list_display_icons = True
    search_fields = ('vinculo__pessoa__nome',)
    list_filter = ('ativo',)
    ordering = ('vinculo__pessoa__nome',)
    date_hierarchy = 'data_habilitacao'
    readonly_fields = ('data_cadastro', 'data_alteracao')

    fieldsets = (
        (
            None,
            {
                'fields': ('vinculo', 'ativo', 'data_habilitacao', 'data_inativacao', 'observacao'),
            },
        ),
        (
            'Auditoria',
            {
                'fields': ('cadastrado_por_vinculo', 'data_cadastro', 'data_alteracao'),
                'classes': ('collapse',),
            },
        ),
    )

    actions = ['action_inativar']

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('vinculo__pessoa', 'vinculo__setor__uo')

    def changelist_view(self, request, extra_context=None):
        from rsc_tae.views._helpers import _ids_servidores_indisponiveis

        self._ids_indisponiveis = _ids_servidores_indisponiveis()
        return super().changelist_view(request, extra_context)

    @admin.display(description='Campus')
    def get_campus(self, obj):
        try:
            return obj.vinculo.setor.uo.sigla
        except Exception:
            return '—'

    @admin.display(description='Situação')
    def get_situacao(self, obj):
        if obj.ativo and not obj.data_inativacao:
            return format_html('<span class="status status-success">Ativo</span>')
        return format_html('<span class="status status-error">Inativo</span>')

    @admin.display(description='Disponibilidade')
    def get_disponibilidade(self, obj):
        if not (obj.ativo and not obj.data_inativacao):
            return format_html('<span class="status status-error">Inativo</span>')
        ids_indisponiveis = getattr(self, '_ids_indisponiveis', set())
        try:
            vinculo = obj.vinculo
            if (
                hasattr(vinculo, 'tipo_relacionamento')
                and vinculo.tipo_relacionamento
                and vinculo.tipo_relacionamento.model == 'servidor'
                and vinculo.id_relacionamento in ids_indisponiveis
            ):
                from rsc_tae.views._helpers import _motivo_indisponibilidade_vinculo

                motivo = _motivo_indisponibilidade_vinculo(vinculo) or 'Indisponível'
                return format_html('<span class="status status-alert" title="{}">{}</span>', motivo, motivo)
        except Exception:
            pass
        return format_html('<span class="status status-success">Disponível</span>')

    @admin.action(description='Inativar avaliadores selecionados')
    def action_inativar(self, request, queryset):
        hoje = datetime.date.today()
        atualizados = 0
        for obj in queryset.filter(ativo=True, data_inativacao__isnull=True):
            obj.inativar(data=hoje)
            atualizados += 1
        if atualizados:
            self.message_user(request, f'{atualizados} avaliador(es) inativado(s).')
        else:
            self.message_user(request, 'Nenhum avaliador ativo selecionado.', level='warning')
