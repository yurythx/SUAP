from comum.models import Ano
from djtools import forms
from ..models.paint import Paint


class PaintForm(forms.ModelFormPlus):
    ano = forms.ModelChoiceFieldPlus(
        label='Ano', queryset=Ano.objects.ultimos(), required=True, help_text='Selecione o ano para o qual deseja criar ou editar o PAINT.'
    )
    inicio_periodo_planejamento = forms.DateFieldPlus(
        label='Início do Período de Planejamento Anual',
        required=True,
        help_text='Data de início do período de planejamento anual.',
    )
    fim_periodo_planejamento = forms.DateFieldPlus(
        label='Fim do Período de Planejamento Anual',
        required=True,
        help_text='Data de fim do período de planejamento anual.',
    )

    class Meta:
        model = Paint
        fields = ['ano', 'inicio_periodo_planejamento', 'fim_periodo_planejamento', 'sincronizar_afastamentos_suap']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['ano'].queryset = Ano.objects.ultimos()

    def clean(self):
        cleaned_data = super().clean()
        inicio = cleaned_data.get('inicio_periodo_planejamento')
        fim = cleaned_data.get('fim_periodo_planejamento')
        if inicio and fim and inicio > fim:
            self.add_error('inicio_periodo_planejamento', 'A data de início do período de planejamento não pode ser posterior à data de fim.')
        if inicio and fim and (fim - inicio).days < 0:
            self.add_error('fim_periodo_planejamento', 'O período de planejamento deve ter pelo menos um dia de duração.')
        if inicio and fim and (fim - inicio).days > 365:
            self.add_error('fim_periodo_planejamento', 'O período de planejamento não pode exceder 365 dias.')
        return cleaned_data

    def save(self, commit=True):
        paint: Paint = super().save(commit=False)
        if commit:
            paint.atualizado_por = self.request.user.get_vinculo()
            paint.save()
        return paint
