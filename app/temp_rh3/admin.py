from django.contrib import admin
from django.utils.safestring import mark_safe

from cpa.forms import QuestionarioForm
from djtools.contrib.admin import ModelAdminPlus
from temp_rh3.models import QuestionarioAcumuloCargos


class QuestionarioAcumuloCargosAdmin(ModelAdminPlus):
    list_display = ('descricao', 'publico', 'ano', 'get_campus')
    ordering = ('id',)
    search_fields = ('descricao',)
    list_filter = ('ano', 'publico')
    list_display_icons = True
    form = QuestionarioForm

    def get_campus(self, obj):
        return mark_safe(obj.get_campus() or ' - ')

    get_campus.short_description = 'Campus'


admin.site.register(QuestionarioAcumuloCargos, QuestionarioAcumuloCargosAdmin)
