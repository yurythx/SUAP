from django.contrib import admin

from djtools.contrib.admin import ModelAdminPlus
from edu.forms import HistoricoImportacaoForm
from edu.models import HistoricoImportacao


class HistoricoImportacaoAdmin(ModelAdminPlus):
    list_display = (
        'id',
        'data',
        'total_alunos_criados',
        'total_alunos_atualizados',
        'total_matriculas_periodo_criadas',
        'total_matriculas_periodo_atualizadas',
    )
    list_display_icons = True
    list_per_page = 15
    form = HistoricoImportacaoForm
    date_hierarchy = 'data'
    export_to_xls = True

    def get_action_bar(self, request):
        items = super(self.__class__, self).get_action_bar(request, True)
        items.append({'url': '/edu/importar_alunos/', 'label': 'Importar Alunos'})
        return items


admin.site.register(HistoricoImportacao, HistoricoImportacaoAdmin)
