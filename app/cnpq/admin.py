from django.contrib import admin

from cnpq.forms import ClassificacaoPeriodicoForm
from cnpq.models import ClassificacaoPeriodico
from djtools.contrib.admin import ModelAdminPlus


class ClassificacaoPeriodicoAdmin(ModelAdminPlus):
    list_display = (
        'periodico',
        'estrato',
        'area_avaliacao',
    )
    list_filter = (
        'estrato',
        'area_avaliacao',
    )
    search_fields = (
        'periodico__nome',
        'periodico__issn',
    )
    list_display_icons = True
    form = ClassificacaoPeriodicoForm


admin.site.register(ClassificacaoPeriodico, ClassificacaoPeriodicoAdmin)
