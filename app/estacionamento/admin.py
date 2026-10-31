from django.contrib import admin

from djtools.contrib.admin import ModelAdminPlus
from estacionamento.forms import VeiculoCombustivelForm, VeiculoCorForm, VeiculoForm, VeiculoMarcaForm, VeiculoModeloForm
from estacionamento.models import Veiculo, VeiculoCombustivel, VeiculoCor, VeiculoMarca, VeiculoModelo


class VeiculoModeloAdmin(ModelAdminPlus):
    form = VeiculoModeloForm
    search_fields = ('nome',)
    list_display = ('nome', 'marca', 'tipo_especie')
    list_filter = ('marca',)
    list_display_icons = True


admin.site.register(VeiculoModelo, VeiculoModeloAdmin)


class VeiculoCorAdmin(ModelAdminPlus):
    form = VeiculoCorForm


admin.site.register(VeiculoCor, VeiculoCorAdmin)


class VeiculoCombustivelAdmin(ModelAdminPlus):
    form = VeiculoCombustivelForm


admin.site.register(VeiculoCombustivel, VeiculoCombustivelAdmin)


class VeiculoMarcaAdmin(ModelAdminPlus):
    form = VeiculoMarcaForm


admin.site.register(VeiculoMarca, VeiculoMarcaAdmin)


class VeiculoAdmin(ModelAdminPlus):
    form = VeiculoForm
    search_fields = ('modelo__nome', 'placa_codigo_atual', 'placa_municipio_atual__nome', 'cor__nome')
    list_display = (
        'icone_editar',
        'modelo',
        'placa_codigo_atual',
        'placa_municipio_atual',
        'cor',
        'ano_fabric',
        'get_condutor_principal',
        'get_telefone_condutor_principal',
        'get_setor_condutor_principal',
    )
    fieldsets = [(None, {'fields': ('modelo', 'cor', 'ano_fabric', ('placa_codigo_atual', 'placa_municipio_atual'), 'vinculos_condutores')})]

    def icone_editar(self, obj):
        return 'Editar'

    icone_editar.short_description = ''
    icone_editar.attrs = {'width': '18px'}


admin.site.register(Veiculo, VeiculoAdmin)
