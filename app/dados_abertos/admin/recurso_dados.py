from django.contrib import admin, messages
from django.utils.translation import gettext_lazy as _
from djtools.contrib.admin import ModelAdminPlus

from ..forms import RecursoDadosForm
from .permissoes import AcaoDeAlteracaoMixin
from ..models import RecursoDados
from ..services.ckan_api_service import get_ckan_service
from ..services.ckan_service import sync_resource_with_ckan


@admin.register(RecursoDados)
class RecursoDadosAdmin(AcaoDeAlteracaoMixin, ModelAdminPlus):
    form = RecursoDadosForm

    list_display = (
        'nome',
        'dataset',
        'formato',
        'fonte',
        'mimetype',
        'id_remoto',
        'sincronizado_em',
    )
    list_filter = ('formato',)
    search_fields = ('nome', 'descricao', 'mimetype', 'id_remoto', 'dataset__titulo', 'dataset__nome')
    readonly_fields = ('sincronizado_em',)
    date_hierarchy = 'sincronizado_em'
    ordering = ('nome',)
    actions = ['action_sync_ckan']
    list_display_icons = True

    fieldsets = (
        (_('Informações principais'), {'fields': ('dataset', 'nome', 'descricao', 'formato', 'gerar_csv')}),
        (_('Fonte do recurso'), {'fields': ('url', 'arquivo', 'mimetype')}),
        (_('Integração CKAN'), {'fields': ('id_remoto', 'sincronizado_em')}),
    )

    def save_model(self, request, obj, form, change):
        """Salva e, se pedido, gera o espelho — avisando quando o conteúdo não tabula."""
        super().save_model(request, obj, form, change)
        aviso = form.aplicar_espelho(obj)
        if aviso:
            self.message_user(request, aviso, level=messages.WARNING)

    @admin.display(description=_('Fonte'))
    def fonte(self, obj):
        # mostra um indicativo rápido de onde vem o recurso
        if obj.arquivo:
            return _('Arquivo')
        if obj.url:
            return _('URL')
        return '-'

    @admin.action(description=_('Sincronizar com CKAN'), permissions=('alterar',))
    def action_sync_ckan(self, request, queryset):
        service = get_ckan_service()
        if not service:
            self.message_user(request, _('API CKAN não configurada ou inativa.'), level=messages.ERROR)
            return
        bloqueados = [r for r in queryset if not (r.dataset_id and r.dataset.lai_liberada_para_sync())]
        if bloqueados:
            self.message_user(
                request,
                _('%(n)s recurso(s) de base(s) não liberada(s) pelo LAI e ignorado(s).') % {'n': len(bloqueados)},
                level=messages.WARNING,
            )
        liberados = queryset.exclude(pk__in=[r.pk for r in bloqueados])
        if not liberados:
            return
        ok, err = sync_resource_with_ckan(liberados, service.base_url, service.api_key)
        self.message_user(request, _('Sincronização de recursos concluída. Sucessos: %(ok)s | Erros: %(err)s') % {'ok': ok, 'err': err})
