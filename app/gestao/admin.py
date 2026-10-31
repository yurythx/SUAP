from django.contrib import admin
from django.utils.safestring import mark_safe

from djtools.contrib.admin import ModelAdminPlus
from gestao.models import Indicador, Variavel


class VariavelAdmin(ModelAdminPlus):
    list_display = ('nome', 'sigla', 'descricao', 'fonte')
    exclude = ['valor']
    ordering = ('sigla',)
    search_fields = ('nome', 'sigla', 'fonte', 'descricao')
    list_display_icons = True


admin.site.register(Variavel, VariavelAdmin)


class IndicadorAdmin(ModelAdminPlus):
    list_display = ('nome', 'sigla', 'formula', 'get_metodo_medicao', 'get_fonte_dados', 'orgao_regulamentador')
    list_filter = ('orgao_regulamentador',)
    ordering = ('nome',)
    search_fields = ('nome', 'sigla')
    list_display_icons = True

    def get_metodo_medicao(self, obj):
        lista = []
        for variavel in obj.get_variaveis():
            if not lista.count(variavel.__str__()):
                lista.append(variavel.__str__())
                lista.append('<br>')
        return mark_safe(''.join(lista))

    get_metodo_medicao.short_description = 'Método de Medição'

    def get_fonte_dados(self, obj):
        lista = []
        for variavel in obj.get_variaveis():
            if not lista.count(variavel.fonte):
                lista.append(variavel.fonte)
                lista.append('<br>')
        return mark_safe(''.join(lista))

    get_fonte_dados.short_description = 'Fonte de Dados'


admin.site.register(Indicador, IndicadorAdmin)


class ConfiguracaoGestaoAdmin(ModelAdminPlus):
    list_display = ('uo', 'qtd_computadores')
    ordering = ('uo__sigla',)


try:
    from edu.models import ConfiguracaoGestao

    admin.site.register(ConfiguracaoGestao, ConfiguracaoGestaoAdmin)
except Exception:
    pass
