from django.contrib import admin
from djtools.contrib.admin import ModelAdminPlus
from django.contrib import messages
from django.core.exceptions import PermissionDenied

from rsc_tae.models import RolSaberCompetenciaPreenchimento


@admin.register(RolSaberCompetenciaPreenchimento)
class RolSaberCompetenciaPreenchimentoAdmin(ModelAdminPlus):
    list_display_icons = True
    actions = ('excluir_selecionados',)
    list_display = (
        'vinculo',
        'rol_saber_competencia',
        'quantidade',
        'get_pontuacao_total',
        'data_alteracao',
    )
    search_fields = (
        'vinculo__pessoa__nome',
        'vinculo__pessoa__pessoafisica__servidor_set__matricula',
        'rol_saber_competencia__titulo',
        'rol_saber_competencia__descricao',
    )
    list_filter = ('rol_saber_competencia',)
    ordering = ('-data_alteracao',)

    @admin.display(description='Pontuação total')
    def get_pontuacao_total(self, obj):
        try:
            return obj.pontuacao_total
        except Exception:
            return '-'

    @admin.action(description='Excluir selecionados')
    def excluir_selecionados(self, request, queryset):
        if not self.has_delete_permission(request):
            raise PermissionDenied

        total = queryset.count()
        queryset.delete()
        self.message_user(request, f'{total} registro(s) excluído(s) com sucesso.', level=messages.SUCCESS)
