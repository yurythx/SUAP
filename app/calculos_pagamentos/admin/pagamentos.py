from django.contrib import admin
from django.utils.safestring import mark_safe

from calculos_pagamentos.models.pagamentos import ArquivoPagamento, ConfigPagamento, Pagamento, Rubrica, Sequencia

# from djtools.contrib.admin.options import ModelAdminPlus
from djtools.contrib.admin import ModelAdminPlus
from djtools.db import models
from djtools.forms.widgets import CheckboxSelectMultiplePlus


# Adicionado por IFMA/Tássio em setembro de 2018.
class SequenciaAdmin(ModelAdminPlus):
    pass


admin.site.register(Sequencia, SequenciaAdmin)


# Adicionado por IFMA/Tássio em setembro de 2018.
class RubricaAdmin(ModelAdminPlus):
    list_display = ['__str__', 'get_sequencias', 'teto_seq', 'metodo_get_valor']
    search_fields = ['codigo', 'descricao']
    list_filter = ['descricao']
    formfield_overrides = {
        models.ManyToManyFieldPlus: {'widget': CheckboxSelectMultiplePlus()},
    }

    def get_sequencias(self, obj):
        return ', '.join([f'{x}' for x in obj.sequencias.all().values_list('numero', flat=True)])

    get_sequencias.short_description = 'Sequências'


admin.site.register(Rubrica, RubricaAdmin)


# Adicionado por IFMA/Tássio em setembro de 2018.
class ConfigPagamentoAdmin(ModelAdminPlus):
    list_display = ['tipo_calculo', 'get_rubricas']

    def get_rubricas(self, obj):
        return ', '.join([f'{x.__str__()}' for x in obj.rubricas.all()])

    get_rubricas.short_description = 'Rubricas'


admin.site.register(ConfigPagamento, ConfigPagamentoAdmin)


# Adicionado por IFMA/Tássio em outubro de 2018.
class PagamentoAdmin(ModelAdminPlus):
    list_display = ['__str__', 'mes_inicial', 'mes_final', 'situacao']
    search_fields = ['calculo__servidor__matricula', 'calculo__servidor__pessoa_fisica__nome']
    list_filter = ['configuracao__tipo_calculo', 'situacao', 'arquivo', 'linhas__sequencia']
    list_display_icons = True

    def mes_inicial(self, obj):
        return f'{obj.mes_inicio.month}/{obj.mes_inicio.year}'

    mes_inicial.short_description = 'Mês Inicial'

    def mes_final(self, obj):
        return f'{obj.mes_fim.month}/{obj.mes_fim.year}'

    mes_final.short_description = 'Mês Final'

    def get_action_bar(self, request):
        items = super().get_action_bar(request)
        # Pegar mesmo queryset que está sendo exibido
        # from django.contrib.admin.views.main import ChangeList
        # cl = ChangeList(request, self.model, self.list_display, self.list_display_links, self.list_filter,
        #                 self.date_hierarchy, self.search_fields, self.list_select_related, self.list_per_page,
        #                 self.list_max_show_all, self.list_editable, self)
        # lista = cl.get_queryset(request)
        lista = self.get_current_queryset(request)
        # Filtrar não processados e pegar ids
        lista = lista.filter(situacao=1).values_list('id', flat=True)
        lista = [f'{x}' for x in lista]
        lista_str = ','.join(lista)

        if request.user.has_perm('calculos_pagamentos.add_pagamento'):
            items.append({'url': '/calculos_pagamentos/gerar_arquivo_nao_processados/', 'label': 'Gerar Arquivo Batch'})
            # Limpando sessão para uso
            request.session.pop('ids', None)
            # Guardando ids na sessão
            request.session['ids'] = lista_str

            items.append({'url': '/calculos_pagamentos/arquivo_aceitos/', 'label': 'Carregar Arquivo de Aceitos', 'css_class': 'success'})
            items.append({'url': '/calculos_pagamentos/arquivo_rejeitados/', 'label': 'Carregar Arquivo de Rejeitados', 'css_class': 'danger'})
        return items

    def has_change_permission(self, request, obj=None):
        if obj:
            return request.user.is_superuser
        return super().has_change_permission(request, obj)

    def has_add_permission(self, request):
        return False


admin.site.register(Pagamento, PagamentoAdmin)


# Adicionado por IFMA/Tássio em dezembro de 2018.
class ArquivoPagamentoAdmin(ModelAdminPlus):
    list_display = ['__str__', 'opcoes']
    list_display_icons = True

    def opcoes(self, obj):
        return mark_safe(
            f"""<a class='btn' href='/calculos_pagamentos/regerar_arquivo/{obj.id}/'>
                                Regerar Arquivo
                            </a>
                            <a class='btn' href='/calculos_pagamentos/listar_matriculas/{obj.id}/'>
                                Listar Matrículas
                            </a>"""
        )

    opcoes.short_description = 'Opções'


admin.site.register(ArquivoPagamento, ArquivoPagamentoAdmin)
