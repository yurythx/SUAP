from django.contrib import admin

from djtools.contrib.admin import ModelAdminPlus
from edu.forms import LogForm
from edu.models import Log


class LogAdmin(ModelAdminPlus):
    list_display = ('id', 'user', 'dt', 'nome_modelo', 'ref', 'descricao')
    list_filter = ('nome_modelo', 'tipo')
    search_fields = ('descricao', 'ref', 'id')
    list_display_icons = True
    export_to_xls = True
    form = LogForm


admin.site.register(Log, LogAdmin)
