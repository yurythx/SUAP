from comum import utils
from comum.utils import get_uo
from djtools import forms
from djtools.forms.widgets import (
    AutocompleteWidget,
)
from edu.models import Matriz, PrevisaoQuantidadeAlunos, SimulacaoAfastamento, SimulacaoCargaHorariaProfessor, SimulacaoContratacao


class TaxaEvasaoForm(forms.ModelFormPlus):
    class Meta:
        model = PrevisaoQuantidadeAlunos
        fields = [f'taxa_evasao_{i}' for i in range(1, 11)]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for i in range(self.instance.matriz.qtd_periodos_letivos + 1, 11):
            self.fields.pop(f'taxa_evasao_{i}')


class QuantidadeAlunosForm(forms.ModelFormPlus):
    class Meta:
        model = PrevisaoQuantidadeAlunos
        fields = [f'qtd_alunos_{i}' for i in range(1, 11)]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for i in range(self.instance.matriz.qtd_periodos_letivos + 1, 11):
            self.fields.pop(f'qtd_alunos_{i}')


class SimulacaoAfastamentoForm(forms.ModelFormPlus):
    class Meta:
        model = SimulacaoAfastamento
        exclude = ('cenario',)


class SimulacaoContratacaoForm(forms.ModelFormPlus):
    class Meta:
        model = SimulacaoContratacao
        exclude = ('cenario',)


class PrevisaoQuantidadeAlunosFormset(forms.models.BaseInlineFormSet):
    matriz = forms.ModelChoiceFieldPlus(Matriz.objects, label='Matriz', required=True, widget=AutocompleteWidget(search_fields=Matriz.SEARCH_FIELDS))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        uo = get_uo()
        if uo.sigla != utils.get_sigla_reitoria():
            for form in self.forms:
                form.fields['matriz'].queryset = form.fields['matriz'].queryset.filter(matrizcurso__curso_campus__diretoria__setor__uo=uo)


class SimulacaoCargaHorariaProfessorForm(forms.ModelFormPlus):
    class Meta:
        model = SimulacaoCargaHorariaProfessor
        fields = 'professor', 'ch_sala_aula_semanal'
