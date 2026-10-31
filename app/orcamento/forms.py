from djtools import forms
from djtools.forms.widgets import AutocompleteWidget, BrDataWidget
from financeiro.models import NaturezaDespesa, UnidadeGestora
from orcamento.models import EstruturaProgramaticaFinanceira, UnidadeMedida
from rh.models import Pessoa

# -------------------------------------------------------------------------------


class ConfiguracaoForm(forms.FormPlus):
    unidade_responsavel = forms.IntegerFieldPlus(
        label='Unidade Gestora', help_text='Codigo da unidade gestora responsável', max_length=6, required=False
    )


class UnidadeMedidaForm(forms.ModelFormPlus):
    nome = forms.CapitalizeTextField(label='Nome', help_text='Ex.: Projeto, Processo', widget=forms.TextInput(attrs={'size': '88'}), max_length=30)

    class Meta:
        model = UnidadeMedida
        exclude = ()


class EstruturaProgramaticaFinanceiraForm(forms.ModelFormPlus):
    unidade_medida = forms.ModelChoiceField(label='Unidade de Medida', queryset=UnidadeMedida.objects.all(), required=False)
    quantidade = forms.IntegerFieldPlus(widget=forms.TextInput(), max_length=5, required=False)

    class Meta:
        model = EstruturaProgramaticaFinanceira
        exclude = ()


# filtros para execucao orcamentaria de ug
class ExecucaoOrcamentariaUGFiltroForm(forms.FormPlus):
    choices_rec = [['ugr', 'por Unidade Gestora Responsável'], ['nat', 'por Natureza de Despesa']]
    recursos = forms.ChoiceField(choices=choices_rec, widget=forms.Select(attrs={'onchange': 'submeter_form(this)'}))

    class Media:
        js = ['/static/orcamento/js/ExecucaoOrcamentariaUGFiltroForm.js']

    def __init__(self, *args, **kwargs):
        if 'recursos' in kwargs:
            id_rec = kwargs.pop('recursos')
            super().__init__(*args, **kwargs)
            self.fields['recursos'].initial = id_rec
        else:
            super().__init__(*args, **kwargs)
            self.fields['recursos'] = forms.ChoiceField(choices=self.choices_rec, widget=forms.Select())


# filtros para detalhamento da execucao orcamentaria de uma ug
class NotasFiltroForm(forms.FormPlus):
    choices_tn = [['nc', 'Notas de Crédito'], ['nd', 'Notas de Dotação']]
    tipo_nota = forms.ChoiceField(label='Tipo', choices=choices_tn, widget=forms.Select(attrs={'onchange': 'submeter_form(this)'}))

    class Media:
        js = ['/static/orcamento/js/NotasFiltroForm.js']

    def __init__(self, *args, **kwargs):
        if 'tipo_nota' in kwargs:
            id_nota = kwargs.pop('tipo_nota')
            super().__init__(*args, **kwargs)
            self.fields['tipo_nota'].initial = id_nota
        else:
            super().__init__(*args, **kwargs)
            self.fields['tipo_nota'] = forms.ChoiceField(label='Tipo', choices=self.choices_tn, widget=forms.Select())


class NotaEmpenhoConsultaForm(forms.FormPlus):
    numero = forms.CharField(label='Número', required=False)
    descricao = forms.CharField(label='Descrição do Item', widget=forms.TextInput(attrs={'size': '100'}), required=False)
    natureza_desp = forms.ModelChoiceField(
        label='Natureza de Despesa',
        required=False,
        queryset=NaturezaDespesa.objects.all(),
        widget=AutocompleteWidget(search_fields=NaturezaDespesa.SEARCH_FIELDS),
    )
    data_inicial = forms.DateFieldPlus(label='Período de Emissão', widget=BrDataWidget(), help_text='Data de início', required=False)
    data_final = forms.DateFieldPlus(help_text='Data final', widget=BrDataWidget(), required=False)
    emitente = forms.ModelChoiceField(
        label='Emitente', required=False, queryset=UnidadeGestora.objects.all(), widget=AutocompleteWidget(extraParams=UnidadeGestora.SEARCH_FIELDS)
    )
    fornecedor = forms.ModelChoiceField(
        label='Fornecedor', required=False, queryset=Pessoa.objects.all(), widget=AutocompleteWidget(search_fields=Pessoa.SEARCH_FIELDS)
    )

    fieldsets = [(None, {'fields': ('numero', 'descricao', 'natureza_desp', 'emitente', 'fornecedor', ('data_inicial', 'data_final'))})]

    def clean(self):
        if (
            self.cleaned_data['numero'] == ''
            and self.cleaned_data['descricao'] == ''
            and self.cleaned_data['data_inicial'] is None
            and self.cleaned_data['data_final'] is None
            and self.cleaned_data['emitente'] is None
            and self.cleaned_data['fornecedor'] is None
            and self.cleaned_data['natureza_desp'] is None
        ):
            raise forms.ValidationError('Preencha alguma das informações para a realização da consulta.')

        if self.cleaned_data['data_inicial'] is not None and self.cleaned_data['data_final'] is None:
            raise forms.ValidationError('Forneça a data final do período de emissão.')

        if self.cleaned_data['data_inicial'] is None or self.cleaned_data['data_final'] is None:
            raise forms.ValidationError('Ambos os campos de data são obrigatórios.')
        elif self.cleaned_data['data_final'] < self.cleaned_data['data_inicial']:
            raise forms.ValidationError('A data limite deve ser posterior a data inicial.')

        return self.cleaned_data
