from decimal import Decimal

from django.contrib import admin
from djtools.contrib.admin import ModelAdminPlus
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.utils.formats import number_format
from django.utils.html import format_html

from rsc_tae.models import RolSaberCompetenciaAnexo
from rsc_tae.models.anexo import taxa_por_papel


@admin.register(RolSaberCompetenciaAnexo)
class RolSaberCompetenciaAnexoAdmin(ModelAdminPlus):
    list_display_icons = True
    actions = ('excluir_selecionados',)
    list_display = (
        'processo',
        'rol_saber_competencia',
        'papel',
        'pontuacao',
        'get_pontuacao_unidade',
        'get_pontuacao_total',
        'get_arquivo',
        'nome_original',
        'cadastrado_por',
        'data_cadastro',
    )
    search_fields = (
        'processo__vinculo__pessoa__nome',
        'processo__vinculo__pessoa__pessoafisica__servidor_set__matricula',
        'rol_saber_competencia__titulo',
        'nome_original',
        'arquivo',
    )
    list_filter = (
        'processo',
        'rol_saber_competencia',
        'papel',
        'data_cadastro',
    )
    ordering = ('-data_cadastro',)

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('processo', 'rol_saber_competencia', 'cadastrado_por')

    @admin.display(description='Pontuação unidade')
    def get_pontuacao_unidade(self, obj):
        try:
            valor = obj.rol_saber_competencia.pontuacao_unidade
        except Exception:
            valor = None
        if valor is None:
            return '-'
        try:
            return number_format(valor, decimal_pos=2)
        except Exception:
            return str(valor)

    @admin.display(description='Pontuação total')
    def get_pontuacao_total(self, obj):
        try:
            unidades = getattr(obj, 'pontuacao', None) or Decimal('0')
            # Usa a taxa do papel (titular/substituto) do anexo; itens sem papel usam a taxa única.
            taxa = taxa_por_papel(obj.rol_saber_competencia, obj.papel) or Decimal('0')
            total = unidades * taxa
            return number_format(total, decimal_pos=2)
        except Exception:
            return '-'

    @admin.action(description='Excluir selecionados')
    def excluir_selecionados(self, request, queryset):
        if not self.has_delete_permission(request):
            raise PermissionDenied

        total = queryset.count()
        queryset.delete()
        self.message_user(request, f'{total} registro(s) excluído(s) com sucesso.', level=messages.SUCCESS)

    @admin.display(description='Arquivo')
    def get_arquivo(self, obj):
        if not getattr(obj, 'arquivo', None):
            return '-'
        name = obj.nome_original or obj.arquivo.name
        try:
            url = obj.arquivo.url
        except Exception:
            url = ''
        if url:
            return format_html('<a href="{}" target="_blank" rel="noopener">{}</a>', url, name)
        return name
