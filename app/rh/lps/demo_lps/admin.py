from django.conf import settings

from djtools.contrib.admin import get_uo_setor_listfilter
from rh.lps.demo_lps.forms import CargoEmpregoForm

"""
O ServidorAdmin abaixo sobrescreve a propriedade list_filter permanecendo com as demais propriedades do admin original.
"""


class ServidorAdmin:
    list_filter = (*get_uo_setor_listfilter(), 'ativo', 'cargo_emprego_area')
    if 'edu' in settings.INSTALLED_APPS:
        list_filter += ('vinculo__professor__disciplina',)


"""
O CargoEmpregoAdmin abaixo retira a propriedade readonly_fields do admin original e adiciona um novo formulário para o
admin de cargo emprego.
"""


class CargoEmpregoAdmin:
    readonly_fields = []
    form = CargoEmpregoForm
