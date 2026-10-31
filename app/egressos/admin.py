from django.contrib import admin

from comum.utils import get_uo
from djtools.contrib.admin import CustomTabListFilter, ModelAdminPlus
from egressos.forms import PesquisaForm
from egressos.models import Pesquisa


class PesquisaAdmin(ModelAdminPlus):
    list_display_icons = True
    list_display = ['titulo', 'descricao', 'modalidade', 'inicio', 'fim']
    search_fields = ('titulo', 'descricao')
    list_filter = [CustomTabListFilter, 'modalidade', 'conclusao', 'uo', 'curso_campus']
    form = PesquisaForm

    fieldsets = (
        ('Dados da Pesquisa', {'fields': (('titulo',), ('descricao',))}),
        ('Público Alvo', {'fields': ('modalidade', 'conclusao', 'uo', 'curso_campus')}),
    )

    def get_queryset(self, request, *args, **kwargs):
        qs = super().get_queryset(request, *args, **kwargs)
        if request.user.has_perm('egressos.eh_gestor_egressos_sistemico'):
            return qs
        return qs.filter(uo=get_uo(request.user))


admin.site.register(Pesquisa, PesquisaAdmin)
