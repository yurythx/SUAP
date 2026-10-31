from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.urls import path, reverse_lazy
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _
from djtools.contrib.admin import ModelAdminPlus
from djtools.templatetags.tags import icon

from ..forms import OrganizacaoForm
from ..models import Organizacao
from ..services.ckan_api_service import get_ckan_service
from ..services.ckan_service import sync_organization_with_ckan


@admin.register(Organizacao)
class OrganizacaoAdmin(ModelAdminPlus):
    class Media:
        js = ('dados_abertos/js/auto_slug.js',)

    list_display = ('titulo', 'nome', 'estado', 'id_remoto', 'sincronizado_em')
    list_filter = ('estado',)
    search_fields = ('nome', 'titulo', 'descricao', 'id_remoto')
    readonly_fields = ('sincronizado_em',)
    list_display_icons = True
    form = OrganizacaoForm

    fieldsets = (
        (_('Informações principais'), {'fields': ('nome', 'titulo', 'descricao', 'url_imagem', 'imagem', 'estado')}),
        (_('Integração CKAN'), {'fields': ('id_remoto', 'sincronizado_em', 'extras')}),
    )

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path(
                '<int:pk>/sync/',
                self.admin_site.admin_view(self.sync_organizacao_view),
                name='dados_abertos_organizacao_sync',
            ),
        ]
        return custom + urls

    def sync_organizacao_view(self, request, pk: int):
        obj = get_object_or_404(Organizacao, pk=pk)
        if not self.has_change_permission(request, obj):
            raise PermissionDenied

        service = get_ckan_service()
        if not service:
            self.message_user(request, _('API CKAN não configurada ou inativa.'), level=messages.ERROR)
            return HttpResponseRedirect(reverse_lazy('admin:dados_abertos_organizacao_changelist'))

        try:
            ok, _err, errors = sync_organization_with_ckan(Organizacao.objects.filter(pk=pk), service.base_url, service.api_key)
            if errors:
                for e in errors[:5]:
                    self.message_user(request, e, level=messages.ERROR)
                if len(errors) > 5:
                    self.message_user(request, _('Mais erros ocultados: %(qtd)s') % {'qtd': len(errors) - 5}, level=messages.ERROR)
            if ok:
                self.message_user(request, _('Organização sincronizada com sucesso.'))
            elif not errors:
                self.message_user(request, _('Nenhuma alteração necessária no CKAN.'))
        except Exception as ex:
            self.message_user(request, _('Falha ao sincronizar: %(erro)s') % {'erro': str(ex)}, level=messages.ERROR)

        return HttpResponseRedirect(reverse_lazy('admin:dados_abertos_organizacao_changelist'))

    @admin.display(description=_('Ações'))
    def show_list_display_icons(self, obj: Organizacao) -> str:
        """Ver/editar conforme a permissão; sincronizar só para quem pode alterar a organização."""
        out = [super().show_list_display_icons(obj)]
        if self.has_change_permission(self.request, obj):
            out.append(icon('sync fa-sync', reverse_lazy('admin:dados_abertos_organizacao_sync', args=[obj.pk]), 'Sincronizar'))
        return mark_safe(''.join(out))
