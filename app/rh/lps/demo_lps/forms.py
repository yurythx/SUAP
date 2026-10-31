from djtools import forms
from djtools.forms import AutocompleteWidget
from djtools.forms.widgets import TreeWidget
from rh.forms import ServidorInformacoesPessoaisForm
from rh.models import CargoEmprego, Setor

"""
O formulário "ServidorForm" sobrescreve o form original em rh/forms.py. Como o form original tem uma herança quando
sobrescrever metodos que chamem o metodo super() usar a classe da herança. Exemplo método __init__.
"""


class ServidorForm:
    setor = forms.ModelChoiceField(label='Setor SUAP LPS', queryset=Setor.objects.suap_ativos().all(), widget=TreeWidget(), required=False)

    def __init__(self, *args, **kwargs):
        super(ServidorInformacoesPessoaisForm, self).__init__(*args, **kwargs)
        #
        if 'cargo_emprego' in self.fields:
            qs_cargoemprego = CargoEmprego.utilizados
            if self.request.user.has_perm('rh.pode_editar_cargo_emprego_externo'):
                qs_cargoemprego = CargoEmprego.objects

        self.fields['cargo_emprego'] = forms.ModelChoiceField(
            label='Cargo Emprego LPS', queryset=qs_cargoemprego, required=False, widget=AutocompleteWidget(search_fields=CargoEmprego.SEARCH_FIELDS)
        )


"""
O formulário "CargoEmpregoForm" herda direto de ModelForm por que esse formulário não existia originalmente no forms.py
e para a LPS foi redefinido no CargoEmpregoAdmin
"""


class CargoEmpregoForm(forms.ModelFormPlus):
    class Meta:
        model = CargoEmprego
        exclude = ['excluido']
