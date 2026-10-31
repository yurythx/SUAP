"""
Created on 18/12/2012

"""

from django.core.exceptions import ValidationError

from comum.models import Ano
from comum.utils import get_setor
from djtools import forms
from djtools.forms.widgets import AutocompleteWidget, TreeWidget
from ferias.models import Ferias, InterrupcaoFerias
from rh.models import Servidor, Setor


class PlanejamentoFeriasForm(forms.ModelFormPlus):
    class Meta:
        model = Ferias
        exclude = (
            'servidor',
            'ano',
            'validado',
            'data_interrupcao_periodo1',
            'data_interrupcao_periodo2',
            'data_interrupcao_periodo3',
            'data_inicio_interrupcao_periodo1',
            'data_fim_interrupcao_periodo1',
            'data_inicio_interrupcao_periodo2',
            'data_fim_interrupcao_periodo2',
            'data_inicio_interrupcao_periodo3',
            'data_fim_interrupcao_periodo3',
            'quitacao',
            'cadastrado',
            'observacao_validacao',
            'criado_em',
            'validado_em',
            'cadastrado_em',
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['data_inicio_periodo1'].required = True
        self.fields['data_fim_periodo1'].required = True

        show_fields = (('data_inicio_periodo1', 'data_fim_periodo1'), ('data_inicio_periodo2', 'data_fim_periodo2'))

        # regra para operadores de raio-x
        if self.instance and self.instance.servidor and self.instance.servidor.opera_raio_x:
            self.fields['data_inicio_periodo2'].required = True
            self.fields['data_fim_periodo2'].required = True
            self.fields['data_inicio_periodo3'].widget = forms.HiddenInput()
            self.fields['data_fim_periodo3'].widget = forms.HiddenInput()
            self.fields['gratificacao_natalina'].choices = [[0, 'Sem Adiantamento'], [1, 'Período 1'], [2, 'Período 2']]
            self.fields['setenta_porcento'].choices = [[0, 'Sem Adiantamento'], [1, 'Período 1'], [2, 'Período 2'], [4, 'Períodos 1 e 2']]

        else:
            show_fields += (('data_inicio_periodo3', 'data_fim_periodo3'),)

        show_fields += ('observacao_criacao', 'gratificacao_natalina', 'setenta_porcento')

        self.fieldsets = ((None, {'fields': show_fields}),)

    def save(self, commit=True):
        super().save(commit=commit)


class PlanejamentoFeriasFormDocentes(forms.ModelFormPlus):
    class Meta:
        model = Ferias
        exclude = (
            'servidor',
            'ano',
            'validado',
            'data_inicio_periodo1',
            'data_inicio_periodo2',
            'data_inicio_periodo3',
            'data_fim_periodo1',
            'data_fim_periodo2',
            'data_fim_periodo3',
            'data_interrupcao_periodo1',
            'data_interrupcao_periodo2',
            'data_interrupcao_periodo3',
            'data_inicio_interrupcao_periodo1',
            'data_fim_interrupcao_periodo1',
            'data_inicio_interrupcao_periodo2',
            'data_fim_interrupcao_periodo2',
            'data_inicio_interrupcao_periodo3',
            'data_fim_interrupcao_periodo3',
            'quitacao',
            'cadastrado',
            'observacao_validacao',
            'criado_em',
            'validado_em',
            'cadastrado_em',
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def save(self, commit=True):
        super().save(commit=commit)


class ValidacaoPlanejamentoFeriasForm(forms.ModelFormPlus):
    VALIDACAO_CHOICES_FORMULARIO = [[1, 'Validado'], [2, 'Invalidado']]

    validacao = forms.ChoiceField(label='Validação:', choices=VALIDACAO_CHOICES_FORMULARIO, required=True, widget=forms.RadioSelect)

    class Meta:
        model = Ferias
        exclude = (
            'servidor',
            'ano',
            'validado',
            'data_inicio_periodo1',
            'data_inicio_periodo2',
            'data_inicio_periodo3',
            'data_fim_periodo1',
            'data_fim_periodo2',
            'data_fim_periodo3',
            'gratificacao_natalina',
            'setenta_porcento',
            'data_interrupcao_periodo1',
            'data_interrupcao_periodo2',
            'data_interrupcao_periodo3',
            'data_inicio_interrupcao_periodo1',
            'data_fim_interrupcao_periodo1',
            'data_inicio_interrupcao_periodo2',
            'data_fim_interrupcao_periodo2',
            'data_inicio_interrupcao_periodo3',
            'data_fim_interrupcao_periodo3',
            'quitacao',
            'cadastrado',
            'observacao_criacao',
            'criado_em',
            'validado_em',
            'cadastrado_em',
        )

    def save(self, commit=True):
        super().save(commit=commit)

    def clean(self):
        super().clean()
        if not self.cleaned_data.get('validacao'):
            raise forms.ValidationError('O campo Validação tem preechimento obrigatório.')
        return self.cleaned_data


class FeriasForm(forms.ModelFormPlus):
    servidor = forms.ModelChoiceField(
        label='Servidor', queryset=Servidor.objects, required=True, widget=AutocompleteWidget(search_fields=Servidor.SEARCH_FIELDS)
    )

    class Meta:
        model = Ferias
        exclude = ()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['servidor'].queryset = Servidor.objects.all()


class InterrupcaoFeriasForm(forms.ModelFormPlus):
    data_interrupcao_periodo = forms.DateFieldPlus(label='Data de Interrupção do Período', required=False)
    data_inicio_continuacao_periodo = forms.DateFieldPlus(label='Data de Início da Continuação', required=False)
    data_fim_continuacao_periodo = forms.DateFieldPlus(label='Data Fim da Continuação', required=False)

    class Meta:
        model = InterrupcaoFerias
        exclude = ()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def clean(self):
        ferias = None
        data_interrupcao_periodo = self.cleaned_data.get('data_interrupcao_periodo')
        data_inicio_continuacao_periodo = self.cleaned_data.get('data_inicio_continuacao_periodo')
        data_fim_continuacao_periodo = self.cleaned_data.get('data_fim_continuacao_periodo')

        if self.instance:
            ferias = self.instance.ferias

        if data_interrupcao_periodo and ferias:
            #
            # verificando se o tempo de continuidade bate com o tempo que sobrou da interrupção

            # interrupções
            interrupcoes = ferias.interrupcaoferias_set.all()
            eh_interrupcao_de_interrupcao = False
            for interrupcao in interrupcoes:
                if interrupcao.data_inicio_continuacao_periodo <= data_interrupcao_periodo <= interrupcao.data_fim_continuacao_periodo:
                    eh_interrupcao_de_interrupcao = True
                    self._check_dias(
                        data_interrupcao_periodo,
                        data_inicio_continuacao_periodo,
                        data_fim_continuacao_periodo,
                        interrupcao.data_inicio_continuacao_periodo,
                        interrupcao.data_fim_continuacao_periodo,
                    )
                    break

            # período 1
            if (
                not eh_interrupcao_de_interrupcao
                and ferias.data_inicio_periodo1
                and ferias.data_inicio_periodo1 <= data_interrupcao_periodo <= ferias.data_fim_periodo1
            ):
                self._check_dias(
                    data_interrupcao_periodo,
                    data_inicio_continuacao_periodo,
                    data_fim_continuacao_periodo,
                    ferias.data_inicio_periodo1,
                    ferias.data_fim_periodo1,
                )

            # período 2
            if (
                not eh_interrupcao_de_interrupcao
                and ferias.data_inicio_periodo2
                and ferias.data_inicio_periodo2 <= data_interrupcao_periodo <= ferias.data_fim_periodo2
            ):
                self._check_dias(
                    data_interrupcao_periodo,
                    data_inicio_continuacao_periodo,
                    data_fim_continuacao_periodo,
                    ferias.data_inicio_periodo2,
                    ferias.data_fim_periodo2,
                )

            # período 3
            if (
                not eh_interrupcao_de_interrupcao
                and ferias.data_inicio_periodo3
                and ferias.data_inicio_periodo3 <= data_interrupcao_periodo <= ferias.data_fim_periodo3
            ):
                self._check_dias(
                    data_interrupcao_periodo,
                    data_inicio_continuacao_periodo,
                    data_fim_continuacao_periodo,
                    ferias.data_inicio_periodo3,
                    ferias.data_fim_periodo3,
                )

        return self.cleaned_data

    def _check_dias(
        self, data_interrupcao_periodo, data_inicio_continuacao_periodo, data_fim_continuacao_periodo, data_inicio_periodo, data_fim_periodo
    ):
        dias_de_ferias_no_periodo = (data_fim_periodo - data_inicio_periodo).days + 1
        dias_de_ferias_tirados = (data_interrupcao_periodo - data_inicio_periodo).days
        diferenca_dias = dias_de_ferias_no_periodo - dias_de_ferias_tirados
        dias_continuidade = (data_fim_continuacao_periodo - data_inicio_continuacao_periodo).days + 1
        if diferenca_dias != dias_continuidade:
            raise ValidationError(f'O período de continuidade deve somar {diferenca_dias} dias, mas está somando {dias_continuidade} dias.')

    def clean_data_interrupcao_periodo(self):
        data_interrupcao = self.cleaned_data.get('data_interrupcao_periodo')
        ferias = None
        if self.instance:
            ferias = self.instance.ferias
        if data_interrupcao and ferias:
            #
            # devemos verificar se essa data interrompe de fato um período (os três períodos normais ou uma interrupção).

            # normais
            if (
                ferias.data_inicio_periodo1
                and not ferias.data_inicio_periodo1 <= data_interrupcao <= ferias.data_fim_periodo1
                and ferias.data_inicio_periodo2
                and not ferias.data_inicio_periodo2 <= data_interrupcao <= ferias.data_fim_periodo2
                and ferias.data_inicio_periodo3
                and not ferias.data_inicio_periodo3 <= data_interrupcao <= ferias.data_fim_periodo3
            ):
                # interrupções
                interrupcoes = ferias.interrupcaoferias_set.all()
                interrompe_periodo_de_continuidade = False
                for interrupcao in interrupcoes:
                    if interrupcao.data_inicio_continuacao_periodo <= data_interrupcao <= interrupcao.data_fim_continuacao_periodo:
                        interrompe_periodo_de_continuidade = True
                        break

                if not interrompe_periodo_de_continuidade:
                    raise ValidationError('A data de interrupção não está interrompendo um período válido.')

        return data_interrupcao


def CalendarioFeriasFormFactory(user):
    class FormCalendarioFerias(forms.FormPlus):
        ano_inicio = forms.ModelChoiceField(label='Ano Início', required=True, queryset=Ano.objects.all())
        ano_fim = forms.ModelChoiceField(label='Ano Fim', required=True, queryset=Ano.objects.all())
        setor = forms.ModelChoiceField(
            queryset=Setor.objects.suap_ativos().all(), widget=TreeWidget(root_nodes=[user.get_vinculo().setor]), initial=get_setor().id
        )
        incluir_subsetores = forms.BooleanField(widget=forms.CheckboxInput, required=False, label='Incluir Subsetores')

    return FormCalendarioFerias
