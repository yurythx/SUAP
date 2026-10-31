from comum.models import Vinculo
from djtools import forms

from ..models import NucleoAuditoria
from ..papeis import get_auditores_ativos


class NucleoAuditoriaForm(forms.ModelFormPlus):
    coordenador = forms.ModelChoiceFieldPlus(label='Coordenador', queryset=Vinculo.objects, required=True)
    membros = forms.MultipleModelChoiceFieldPlus(
        label='Membros', queryset=Vinculo.objects, help_text='Vincule auditores a este núcleo', required=True
    )

    class Meta:
        model = NucleoAuditoria
        fields = ('nome', 'descricao', 'membros', 'coordenador', 'ramal', 'email', 'ativo')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        auditor_qs = get_auditores_ativos()
        self.fields['coordenador'].queryset = auditor_qs
        self.fields['membros'].queryset = auditor_qs

    def clean(self):
        cleaned_data = super().clean()
        coordenador = cleaned_data.get('coordenador')
        membros = cleaned_data.get('membros')
        if coordenador not in membros:
            self.add_error('coordenador', 'O coordenador deve ser escolhido dentre os membros do núcleo')
        return cleaned_data
