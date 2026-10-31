from django.contrib import admin
from comum import utils
from djtools.contrib.admin import ModelAdminPlus

from edu.models import MensagemResponsavel


class MensagemResponsavelAdmin(ModelAdminPlus):
    search_fields = 'assunto', 'conteudo'
    list_display = 'uo', 'remetente', 'assunto', 'data_envio', 'pode_interagir'
    date_hierarchy = 'data_envio'
    list_filter = ('uo', 'remetente', 'destinatarios', 'pode_interagir')
    list_display_icons = True

    def get_action_bar(self, request, remove_add_button=False):
        actions = super().get_action_bar(request, remove_add_button)
        for action in actions:
            if action['url'] == 'add/':
                action['url'] = '/edu/enviar_mensagem_responsavel/'
        return actions

    def get_queryset(self, request, manager=None, *args, **kwargs):
        qs = super().get_queryset(request, manager, *args, **kwargs)
        if request.user.is_superuser:
            return qs
        q = qs.none()
        if request.user.has_group_cached(['Diretor Acadêmico', 'Membro ETEP']):
            q = q | qs.filter(uo=utils.get_uo(request.user))
        if request.user.has_group_cached(['Coordenador de Curso']):
            q = q | qs.model.objects.filter(remetente=request.user)
        return q


admin.site.register(MensagemResponsavel, MensagemResponsavelAdmin)
