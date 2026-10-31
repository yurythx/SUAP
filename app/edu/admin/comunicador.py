from datetime import datetime

from django.contrib import admin
from django.utils.safestring import mark_safe

from djtools.contrib.admin import CustomTabListFilter, ModelAdminPlus
from djtools.templatetags.tags import icon
from edu.models import MensagemEntrada, MensagemSaida, RegistroExclusao, RegistroLeitura


class MensagemEntradaAdmin(ModelAdminPlus):
    list_display = ('get_icone', 'remetente', 'assunto', 'data_envio')
    search_fields = ('assunto', 'remetente__vinculo__pessoa__nome', 'remetente__username')
    ordering = ('-data_envio',)
    list_display_icons = False
    list_filter = (CustomTabListFilter, 'via_suap', 'via_email')
    actions = ('marcar_como_lida', 'enviar_para_lixeira')
    date_hierarchy = 'data_envio'
    show_tab_any_data = False

    def get_actions(self, request):
        actions = super().get_actions(request)
        tab = request.GET.get('tab')
        if tab == 'tab_lixeira':
            actions.pop('enviar_para_lixeira')
        elif tab == 'tab_lidas':
            actions.pop('marcar_como_lida')
        return actions

    def marcar_como_lida(self, request, queryset):
        for mensagem in queryset.exclude(registroleitura__isnull=False, registroexclusao__destinatario_id=request.user.pk):
            RegistroLeitura.objects.create(mensagem=mensagem, destinatario_id=request.user.pk, data_leitura=datetime.today())
        RegistroExclusao.objects.filter(mensagem__in=queryset, destinatario_id=request.user.pk).delete()

    marcar_como_lida.short_description = 'Marcar como lida'

    def enviar_para_lixeira(self, request, queryset):
        for mensagem in queryset.exclude(registroexclusao__isnull=False, registroexclusao__destinatario_id=request.user.pk):
            RegistroExclusao.objects.create(mensagem=mensagem, destinatario_id=request.user.pk, data_exclusao=datetime.today())

    enviar_para_lixeira.short_description = 'Enviar para lixeira'

    def get_icone(self, obj):
        return mark_safe(icon('view', obj.get_absolute_url()))

    get_icone.short_description = 'Ações'

    def get_action_bar(self, request):
        return super(self.__class__, self).get_action_bar(request, True)

    def get_tabs(self, request):
        return ['tab_nao_lidas', 'tab_lidas', 'tab_todas', 'tab_lixeira']

    def tab_todas(self, request, queryset):
        return queryset.exclude(registroexclusao__destinatario_id=request.user.pk)

    tab_todas.short_description = 'Todas'

    def tab_nao_lidas(self, request, queryset):
        return (
            queryset.exclude(remetente=request.user)
            .exclude(registroexclusao__destinatario_id=request.user.pk)
            .exclude(registroleitura__destinatario_id=request.user.pk)
            .distinct()
        )

    tab_nao_lidas.short_description = 'Não Lidas'

    def tab_lidas(self, request, queryset):
        return (
            queryset.exclude(remetente_id=request.user.pk)
            .exclude(registroexclusao__destinatario_id=request.user.pk)
            .filter(registroleitura__destinatario_id=request.user.pk)
            .distinct()
        )

    tab_lidas.short_description = 'Lidas'

    def tab_lixeira(self, request, queryset):
        return queryset.exclude(remetente_id=request.user.pk).filter(registroexclusao__destinatario_id=request.user.pk)

    tab_lixeira.short_description = 'Lixeira'

    def get_queryset(self, request):
        return super().get_queryset(request).filter(destinatarios=request.user).distinct()


admin.site.register(MensagemEntrada, MensagemEntradaAdmin)


class MensagemSaidaAdmin(ModelAdminPlus):
    list_display = ('get_icone', 'remetente', 'assunto', 'data_envio', 'get_qtd_destinatarios', 'get_qtd_leitura')
    search_fields = ('assunto', 'remetente__vinculo__pessoa__nome', 'remetente__username')
    ordering = ('-data_envio',)
    list_display_icons = False
    list_filter = ('via_suap', 'via_email')
    date_hierarchy = 'data_envio'

    def get_qtd_destinatarios(self, obj):
        return mark_safe(obj.get_quantidade_destinatarios())

    get_qtd_destinatarios.short_description = 'Quantidade de Destinatários'

    def get_qtd_leitura(self, obj):
        return mark_safe(obj.get_quantidade_leitura())

    get_qtd_leitura.short_description = 'Quantidade de Leitura'

    def get_icone(self, obj):
        return mark_safe(icon('view', obj.get_absolute_url()))

    get_icone.short_description = 'Ações'

    def get_action_bar(self, request):
        items = super(self.__class__, self).get_action_bar(request, True)
        if request.user.has_perm('edu.add_mensagem'):
            items.append({'url': '/edu/enviar_mensagem/', 'label': 'Nova Mensagem'})
        return items

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if not request.user.has_group_cached(['Administrador Acadêmico']):
            return qs.filter(remetente=request.user)
        return qs.distinct()


admin.site.register(MensagemSaida, MensagemSaidaAdmin)
