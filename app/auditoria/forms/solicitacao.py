from django.db import transaction

from djtools import forms
from djtools.utils import get_datetime_now
from rh.models import Setor

from ..models import Monitoramento, SolicitacaoProvidencia


class SolicitacaoProvidenciaForm(forms.ModelFormPlus):
    monitoramento = forms.ModelChoiceField(queryset=Monitoramento.objects.none(), label='Monitoramento')
    motivo = forms.CharFieldPlus(widget=forms.Textarea, required=True, label='Solicitação de providência')
    prazo_atendimento = forms.DateFieldPlus(label='Prazo para atendimento', required=True)
    setor = forms.ModelChoiceField(queryset=Setor.objects.suap_ativos().none(), label='Unidade')

    fieldsets = (
        (
            'Dados do monitoramento',
            {
                'fields': (
                    'monitoramento',
                    'setor',
                )
            },
        ),
        (
            'Dados da solicitação',
            {
                'fields': (
                    'motivo',
                    'prazo_atendimento',
                )
            },
        ),
    )

    class Meta:
        model = SolicitacaoProvidencia
        fields = ('motivo', 'prazo_atendimento', 'setor')

    def __init__(self, *args, **kwargs):
        self.monitoramento: Monitoramento = kwargs.pop('monitoramento', None)
        super().__init__(*args, **kwargs)
        #
        self.fields['monitoramento'].initial = self.monitoramento.id
        self.fields['monitoramento'].queryset = Monitoramento.objects.filter(id=self.monitoramento.id)
        self.fields['monitoramento'].widget.attrs['readonly'] = True

        self.fields['setor'].initial = self.monitoramento.unidade.id
        self.fields['setor'].queryset = Setor.objects.suap_ativos().filter(id=self.monitoramento.unidade.id)
        self.fields['setor'].widget.attrs['readonly'] = True

    def clean_prazo_atendimento(self):
        today = get_datetime_now().date()
        prazo = self.cleaned_data.get('prazo_atendimento')
        if today > prazo:
            self.add_error('prazo_atendimento', 'O prazo de resposta não pode ser no passado.')
        #
        return prazo

    def clean(self):
        cleaned_data = super().clean()
        prazo = cleaned_data.get('prazo_atendimento')
        data_limite = self.monitoramento.data_limite
        if prazo and prazo > data_limite:
            msg = f'O prazo de resposta não pode ser maior que a data limite da recomendação: {data_limite}.'
            self.add_error('prazo_atendimento', msg)
        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.monitoramento = self.monitoramento
        instance.save()
        return instance


class CancelarSolicitacaoProvidenciaForm(forms.ModelFormPlus):
    justificativa_cancelamento = forms.CharFieldPlus(label='Justificativa', widget=forms.Textarea(), required=True)

    class Meta:
        model = SolicitacaoProvidencia
        fields = ('justificativa_cancelamento',)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    @transaction.atomic()
    def save(self, *args, **kwargs):
        self.instance.cancelar(self.request.user, self.cleaned_data['justificativa_cancelamento'])
        super().save(*args, **kwargs)
