from datetime import datetime

from django.contrib.admin.widgets import FilteredSelectMultiple

from comum.utils import get_uo
from djtools import forms
from documento_eletronico.models import Documento, TipoDocumento
from rh.models import Setor

from .models import BoletimProgramado, ConfiguracaoSetorBoletim


class BoletimProgramadoForm(forms.ModelFormPlus):
    tipo_documento = forms.ModelMultipleChoiceField(
        label='Tipos de documentos', queryset=TipoDocumento.ativos, required=True, widget=FilteredSelectMultiple('Tipos de Documentos', True)
    )
    nivel_acesso = forms.MultipleChoiceField(
        label='Nível de Acesso de Documentos', choices=Documento.NIVEL_ACESSO_CHOICES, required=False, widget=forms.CheckboxSelectMultiplePlus()
    )

    class Meta:
        model = BoletimProgramado
        fields = ['titulo', 'tipo_documento', 'nivel_acesso', 'programado', 'programado_semanal', 'programado_mensal']

    def clean(self):
        cleaned_data = super().clean()
        if not (cleaned_data.get('programado') or cleaned_data.get('programado_semanal') or cleaned_data.get('programado_mensal')):
            self.add_error('programado', 'Selecione pelo menos um tipo de recorrência: diária, semanal ou mensal')
        return cleaned_data


class GerarBoletimMesForm(forms.FormPlus):
    METHOD = 'GET'
    SUBMIT_LABEL = 'Gerar Boletim'

    ano = forms.IntegerField(label='Selecione o Ano:', required=False, widget=forms.Select())
    mes = forms.MesField(label='Selecione o Mês:', required=False, choices=[])

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        maior_ano = datetime.now().year
        _anos = list(range(maior_ano, 2017, -1))
        ANO_CHOICES = [[a, f'{a}'] for a in _anos]
        self.fields['ano'].widget.choices = ANO_CHOICES


class ConfiguracaoSetorBoletimForm(forms.ModelFormPlus):
    setor_documento = forms.ModelChoiceField(Setor.objects)

    class Meta:
        model = ConfiguracaoSetorBoletim
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        user = self.request.user
        if user.groups.filter(name='Gerente de Boletins de Serviço') and not user.groups.filter(name='Gerente Sistêmico de Boletins de Serviço'):
            uo = get_uo(user)
            self.fields['setor_documento'].queryset = Setor.objects.suap_ativos().filter(uo=uo)
        else:
            self.fields['setor_documento'].queryset = Setor.objects.suap_ativos()
