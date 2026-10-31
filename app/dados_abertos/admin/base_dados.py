from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.db.models import Count, Exists, OuterRef
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.urls import path, reverse_lazy
from django.utils.html import format_html, format_html_join
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _
from djtools.contrib.admin import ModelAdminPlus
from djtools.templatetags.tags import icon

from ..enums import SituacaoLAI
from ..forms import BaseDadosForm
from .permissoes import AcaoDeAlteracaoMixin
from ..models import BaseDados, PDABaseDados
from ..services.ckan_api_service import get_ckan_service
from ..services.metadados import extras_dcat
from ..services.ckan_service import (
    sync_dataset_resources_with_ckan,
    sync_dataset_with_ckan,
)
from .inlines import RecursoDadosInline


@admin.register(BaseDados)
class BaseDadosAdmin(AcaoDeAlteracaoMixin, ModelAdminPlus):
    class Media:
        js = ('dados_abertos/js/auto_slug.js',)

    list_display = (
        'titulo',
        'nome',
        'organizacao',
        'recursos_qtd',
        'situacao_base',
        'id_remoto',
        'sincronizado_em',
    )
    list_filter = ('estado', 'organizacao')
    search_fields = (
        'nome',
        'titulo',
        'notas',
        'id_remoto',
        # ArrayField de texto: o get_search_results já acrescenta __icontains, que no PostgreSQL
        # compara com o array convertido em texto, casando um trecho de qualquer tag.
        'tags',
    )
    readonly_fields = ('sincronizado_em', 'extras_enviados_ckan')
    date_hierarchy = 'sincronizado_em'
    ordering = ('titulo', 'nome')
    inlines = [RecursoDadosInline]
    actions = ['action_sync_ckan', 'action_sync_resources_ckan', 'action_sync_resources_ckan_forcado']
    list_display_icons = True
    form = BaseDadosForm

    fieldsets = (
        (_('Informações principais'), {'fields': ('nome', 'titulo', 'notas', 'organizacao', 'licenca', 'tags', 'tema', 'estado')}),
        (_('Responsáveis'), {'fields': ('autor', 'autor_email', 'mantenedor', 'mantenedor_email', 'versao')}),
        (
            _('Cobertura e observância legal (DCAT-BR)'),
            {
                'fields': (
                    ('cobertura_espacial', 'valor_cobertura_espacial', 'granularidade_espacial'),
                    ('cobertura_temporal_inicio', 'cobertura_temporal_fim'),
                    'observancia_legal',
                    'ods',
                    ('dados_genero', 'dados_raca_etnia'),
                )
            },
        ),
        (_('Integração CKAN'), {'fields': ('id_remoto', 'sincronizado_em', 'extras', 'extras_enviados_ckan')}),
    )

    @admin.display(description=_('Extras que sobem ao CKAN (conforme salvo)'))
    def extras_enviados_ckan(self, obj: BaseDados | None) -> str:
        """Os extras exatamente como sobem no sync: campos do DCAT-BR, periodicidade do PDA e extras livres."""
        if not obj or not obj.pk:
            return '-'
        extras = extras_dcat(obj)
        return format_html('<dl class="definition-list">{}</dl>', format_html_join('', '<dt>{}</dt><dd>{}</dd>', extras.items()))

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path(
                '<int:pk>/sync/',
                self.admin_site.admin_view(self.sync_dataset_view),
                name='dados_abertos_basedados_sync',
            ),
            path(
                '<int:pk>/sync-resources/',
                self.admin_site.admin_view(self.sync_dataset_resources_view),
                name='dados_abertos_basedados_sync_resources',
            ),
        ]
        return custom + urls

    def sync_dataset_view(self, request, pk: int):
        obj = get_object_or_404(BaseDados, pk=pk)
        if not self.has_change_permission(request, obj):
            raise PermissionDenied

        list_url = reverse_lazy('admin:dados_abertos_basedados_changelist')
        if not obj.lai_liberada_para_sync():
            self.message_user(request, obj.motivo_bloqueio_lai(), level=messages.ERROR)
            return HttpResponseRedirect(list_url)

        service = get_ckan_service()
        if not service:
            self.message_user(request, _('API CKAN não configurada ou inativa.'), level=messages.ERROR)
            return HttpResponseRedirect(list_url)

        try:
            ok, err = sync_dataset_with_ckan(BaseDados.objects.filter(pk=pk), service.base_url, service.api_key)
            if err:
                self.message_user(request, _('Erros durante a sincronização.'), level=messages.ERROR)
                return HttpResponseRedirect(list_url)
            if ok:
                self.message_user(request, _('Dataset sincronizado com sucesso.'))
            else:
                self.message_user(request, _('Nenhuma alteração necessária no CKAN.'))
        except Exception as ex:
            self.message_user(request, _('Falha ao sincronizar dataset: %(erro)s') % {'erro': str(ex)}, level=messages.ERROR)
        return HttpResponseRedirect(list_url)

    def sync_dataset_resources_view(self, request, pk: int):
        obj = get_object_or_404(BaseDados, pk=pk)
        if not self.has_change_permission(request, obj):
            raise PermissionDenied

        list_url = reverse_lazy('admin:dados_abertos_basedados_changelist')
        if not obj.lai_liberada_para_sync():
            self.message_user(request, obj.motivo_bloqueio_lai(), level=messages.ERROR)
            return HttpResponseRedirect(list_url)

        service = get_ckan_service()
        if not service:
            self.message_user(request, _('API CKAN não configurada ou inativa.'), level=messages.ERROR)
            return HttpResponseRedirect(list_url)

        try:
            ok, err = sync_dataset_resources_with_ckan(BaseDados.objects.filter(pk=pk), service.base_url, service.api_key)
            if err:
                self.message_user(request, _('Erros durante a sincronização de recursos.'), level=messages.ERROR)
                return HttpResponseRedirect(list_url)
            if ok:
                self.message_user(request, _('Recursos do dataset sincronizados com sucesso.'))
            else:
                self.message_user(request, _('Nenhum recurso necessitou de atualização no CKAN.'))
        except Exception as ex:
            self.message_user(request, _('Falha ao sincronizar recursos do dataset: %(erro)s') % {'erro': str(ex)}, level=messages.ERROR)
        return HttpResponseRedirect(list_url)

    def save_formset(self, request, form, formset, change):
        """Salva os recursos do inline e repassa os avisos do espelho CSV.

        Sem isto o aviso morreria dentro do formulário do inline: o recurso seria salvo e o
        espelho silenciosamente não.
        """
        super().save_formset(request, form, formset, change)
        for formulario in getattr(formset, 'forms', []):
            aviso = getattr(formulario, 'aviso_espelho', '')
            if aviso:
                self.message_user(request, aviso, level=messages.WARNING)

    @admin.display(description=_('Ações'))
    def show_list_display_icons(self, obj: BaseDados) -> str:
        """Ver/editar conforme a permissão; sincronizar só para quem pode alterar a base."""
        out = [super().show_list_display_icons(obj)]
        if not self.has_change_permission(self.request, obj):
            return mark_safe(''.join(out))
        out.append(icon('sync', reverse_lazy('admin:dados_abertos_basedados_sync', args=[obj.pk]), 'Sincronizar Dataset'))
        out.append(icon('database', reverse_lazy('admin:dados_abertos_basedados_sync_resources', args=[obj.pk]), 'Sincronizar Recursos'))
        return mark_safe(''.join(out))

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        # anota qtd de recursos e a presença de cada estado de deliberação LAI (via Exists,
        # sem inflar a contagem de recursos nem gerar N consultas). A situação é derivada em situacao_base().
        relacoes = PDABaseDados.objects.filter(base_dados=OuterRef('pk'))
        return qs.annotate(
            _recursos_qtd=Count('recursos'),
            _tem_relacao=Exists(relacoes),
            _tem_devolvido=Exists(relacoes.filter(situacao_lai=SituacaoLAI.DEVOLVIDO)),
            _tem_em_analise=Exists(relacoes.filter(situacao_lai=SituacaoLAI.EM_ANALISE)),
            _tem_pendente=Exists(relacoes.filter(situacao_lai=SituacaoLAI.PENDENTE)),
        )

    def _situacao_base(self, obj):
        """(rótulo, classe DS) da situação da base no ciclo LAI/CKAN, por precedência (mostra o que trava/próximo passo)."""
        if not obj._tem_relacao:
            return 'Não vinculada a PDA', 'status-neutro'
        if not obj._recursos_qtd:
            return 'Sem recurso', 'status-warning'
        if obj._tem_devolvido:
            return 'Devolvida para ajustes', 'status-error'
        if obj._tem_em_analise:
            return 'Em análise do LAI', 'status-info'
        if obj._tem_pendente:
            return 'Aguardando envio ao LAI', 'status-alert'
        # tem relação e recurso, e nenhuma relação pendente/em análise/devolvida => todas LIBERADO
        if obj.id_remoto:
            return 'Sincronizada com o CKAN', 'status-success'
        return 'Liberada (aguardando sincronização)', 'status-success'

    @admin.display(description=_('Situação'))
    def situacao_base(self, obj):
        rotulo, classe = self._situacao_base(obj)
        return mark_safe(f'<span class="status {classe}">{rotulo}</span>')

    @admin.display(description=_('Recursos'), ordering='_recursos_qtd')
    def recursos_qtd(self, obj):
        return obj._recursos_qtd

    @admin.action(description=_('Sincronizar datasets com CKAN'), permissions=('alterar',))
    def action_sync_ckan(self, request, queryset):
        service = get_ckan_service()
        if not service:
            self.message_user(request, _('API CKAN não configurada ou inativa.'), level=messages.ERROR)
            return
        bloqueadas = [b for b in queryset if not b.lai_liberada_para_sync()]
        liberadas = queryset.exclude(pk__in=[b.pk for b in bloqueadas])
        if bloqueadas:
            nomes = ', '.join(str(b) for b in bloqueadas[:5])
            self.message_user(
                request,
                _('%(n)s base(s) bloqueada(s) pela análise LAI e ignorada(s): %(nomes)s') % {'n': len(bloqueadas), 'nomes': nomes},
                level=messages.WARNING,
            )
        if not liberadas:
            return
        try:
            ok, err = sync_dataset_with_ckan(liberadas, service.base_url, service.api_key)
            self.message_user(request, _('Sincronização de datasets concluída. Sucessos: %(ok)s | Erros: %(err)s') % {'ok': ok, 'err': err})
        except Exception as ex:
            self.message_user(request, _('Falha geral ao sincronizar datasets: %(erro)s') % {'erro': str(ex)}, level=messages.ERROR)

    def _liberadas_pelo_lai(self, request, queryset):
        """Filtra o queryset pelas bases liberadas pelo LAI, avisando sobre as bloqueadas."""
        bloqueadas = [b for b in queryset if not b.lai_liberada_para_sync()]
        if bloqueadas:
            nomes = ', '.join(str(b) for b in bloqueadas[:5])
            self.message_user(
                request,
                _('%(n)s base(s) bloqueada(s) pela análise LAI e ignorada(s): %(nomes)s') % {'n': len(bloqueadas), 'nomes': nomes},
                level=messages.WARNING,
            )
        return queryset.exclude(pk__in=[b.pk for b in bloqueadas])

    def _sincronizar_recursos(self, request, queryset, *, force_file: bool):
        """Corpo comum das duas actions de sincronização de recursos.

        ``force_file`` reenvia o arquivo mesmo sem diferença detectável. É o que resolve o caso
        em que o conteúdo sumiu do CKAN sem o SUAP saber: o ``resource_show`` continua
        respondendo (o metadado remoto sobrevive), então a sincronização normal conclui que não
        há nada a fazer e o download segue quebrado.
        """
        service = get_ckan_service()
        if not service:
            self.message_user(request, _('API CKAN não configurada ou inativa.'), level=messages.ERROR)
            return
        liberadas = self._liberadas_pelo_lai(request, queryset)
        if not liberadas:
            return
        try:
            ok, err = sync_dataset_resources_with_ckan(liberadas, service.base_url, service.api_key, force_file=force_file)
            self.message_user(request, _('Sincronização de recursos concluída. Sucessos: %(ok)s | Erros: %(err)s') % {'ok': ok, 'err': err})
        except Exception as ex:
            self.message_user(request, _('Falha geral ao sincronizar recursos: %(erro)s') % {'erro': str(ex)}, level=messages.ERROR)

    @admin.action(description=_('Sincronizar recursos dos datasets com CKAN'), permissions=('alterar',))
    def action_sync_resources_ckan(self, request, queryset):
        self._sincronizar_recursos(request, queryset, force_file=False)

    @admin.action(description=_('Sincronizar recursos FORÇANDO o reenvio do arquivo (use quando o arquivo sumiu do CKAN)'), permissions=('alterar',))
    def action_sync_resources_ckan_forcado(self, request, queryset):
        """Reenvia os arquivos mesmo quando nenhuma diferença é detectada.

        Serve para os casos em que o arquivo no CKAN divergiu do local sem que o
        SUAP tenha registro disso — reenvio interrompido, remoção manual no CKAN
        ou storage restaurado de backup.
        """
        self._sincronizar_recursos(request, queryset, force_file=True)
