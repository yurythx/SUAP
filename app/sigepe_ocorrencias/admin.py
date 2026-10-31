from django.contrib import admin
from django.http import HttpResponseRedirect
from django.urls import reverse
from djtools.templatetags.filters import status

from djtools.contrib.admin import ModelAdminPlus

from sigepe_ocorrencias.models import PacoteOcorrenciaSigepe, OcorrenciaSigepe
from sigepe_ocorrencias.forms import PacoteOcorrenciaSigepeForm


@admin.register(PacoteOcorrenciaSigepe)
class PacoteOcorrenciaSigepeAdmin(ModelAdminPlus):
    list_display = ('id', 'mes', 'ano', 'get_situacao')

    ordering = ('-ano', '-mes')

    list_display_icons = True

    fields = ('ano', 'mes')

    form = PacoteOcorrenciaSigepeForm

    def get_situacao(self, obj):
        return status(obj.get_situacao_display())

    get_situacao.short_description = 'Situação'

    def has_change_permission(self, request, obj=None):
        return False

    def render_view_object(self, request, obj_pk):
        return HttpResponseRedirect(reverse('visualizar_pacote', args=[obj_pk]))


# temporario
@admin.register(OcorrenciaSigepe)
class OcorrenciaSigepeAdmin(ModelAdminPlus):
    list_display = (
        'vinculo',
        'vinculo__setor',
        'vinculo__setor__uo',
        'tipo_ocorrencia',
        'data_inicio',
        'data_fim',
        'tem_efeito_financeiro',
        'erro_envio',
    )
    list_filter = ('erro_envio', 'vinculo')
