from django.contrib import admin
from django.shortcuts import redirect, reverse
from django.utils.safestring import mark_safe

from djtools.contrib.admin import ModelAdminPlus
from edu.models.napne import ApoioEspecializado, SugestaoRecurso


@admin.register(ApoioEspecializado)
class ApoioEspecializadoAdmin(ModelAdminPlus):
    list_display = ('nome', 'faz_entrevista', 'ativo', 'get_opcoes')
    search_fields = ('nome',)
    list_display_icons = True

    def get_opcoes(self, obj):
        return mark_safe(
            f'<a href="{reverse("napne_listar_profissionais", kwargs={"apoio_id": obj.pk})}" class="btn default popup">Listar profissionais</a>'
        )

    get_opcoes.short_description = 'Opções'

    def response_add(self, request, obj):
        return redirect('admin:edu_apoioespecializado_changelist')


@admin.register(SugestaoRecurso)
class SugestaoRecursoAdmin(ModelAdminPlus):
    list_display = ('nome', 'ativo')
    search_fields = ('nome',)

    def response_add(self, request, obj):
        return redirect('admin:edu_sugestaorecurso_changelist')
