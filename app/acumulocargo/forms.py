import datetime

from django.core.exceptions import ValidationError

from acumulocargo.models import DeclaracaoAcumulacaoCargo, PeriodoDeclaracaoAcumuloCargos
from djtools import forms
from djtools.forms.widgets import FilteredSelectMultiplePlus
from rh.models import UnidadeOrganizacional


class PeriodoDeclaracaoAcumuloCargosForm(forms.ModelFormPlus):
    campus = forms.ModelMultipleChoiceField(
        label='Campi', queryset=UnidadeOrganizacional.objects.suap().all(), widget=FilteredSelectMultiplePlus('', True), required=False
    )

    class Meta:
        model = PeriodoDeclaracaoAcumuloCargos
        exclude = ()


class DeclaracaoAcumulacaoCargoForm(forms.ModelFormPlus):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        servidor = self.request.user.get_relacionamento()
        self.fields['servidor'].widget = forms.HiddenInput()
        self.fields['servidor'].initial = servidor.pk

        self.fields['periodo_declaracao_acumulo_cargo'].widget = forms.HiddenInput()
        hoje = datetime.date.today()
        qs_periodo_declaracao = PeriodoDeclaracaoAcumuloCargos.objects.filter(data_inicio__lte=hoje, data_fim__gte=hoje)
        periodo_declaracao_id = None
        if qs_periodo_declaracao.exists():
            periodo_declaracao_id = qs_periodo_declaracao[0].id

        self.fields['periodo_declaracao_acumulo_cargo'].initial = periodo_declaracao_id

    class Meta:
        model = DeclaracaoAcumulacaoCargo
        exclude = ('data_cadastro',)

    def clean(self):
        cleaned_data = super().clean()
        _errors = []

        # if cleaned_data.get('nao_possui_outro_vinculo') and (cleaned_data.get('tem_outro_cargo_acumulavel') or cleaned_data.get('tem_pensao ') or cleaned_data.get('tem_aposentadoria') or cleaned_data.get('tem_atuacao_gerencial') or cleaned_data.get('exerco_atividade_remunerada_privada')):
        #     msg = u"Se você marcar o campo que não possui outro vínculo, não pode marcar os outros campos."
        #     _errors.append(msg)

        if not cleaned_data.get('nao_possui_outro_vinculo') and not (
            cleaned_data.get('tem_outro_cargo_acumulavel')
            or cleaned_data.get('tem_pensao')
            or cleaned_data.get('tem_aposentadoria')
            or cleaned_data.get('tem_atuacao_gerencial')
            or cleaned_data.get('exerco_atividade_remunerada_privada')
        ):
            msg = 'Você precisa marcar um dos campos da Declaração de acumulação de cargos.'
            _errors.append(msg)

        if _errors:
            raise ValidationError(_errors)

        return cleaned_data
