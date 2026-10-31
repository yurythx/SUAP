from djtools import forms
from django.contrib.contenttypes.models import ContentType

from comum.models import Vinculo
from ..papeis import get_auditores_ativos
from ..models import PermissaoDeChefe, AcaoPermissao, LiberacaoProgramada


ALVOS_PERMITIDOS = {
    'LiberacaoProgramada': ('Liberação Programada', LiberacaoProgramada),
}


class ConcederPermissaoDeChefeForm(forms.ModelFormPlus):
    vinculo_permitido = forms.ModelChoiceFieldPlus(
        label='Auditor',
        queryset=Vinculo.objects.none(),
        required=True,
        help_text='Auditor que receberá a permissão concedida.',
    )
    modelo = forms.ChoiceField(
        label='Modelo',
        choices=[(modelo, label) for modelo, (label, _) in ALVOS_PERMITIDOS.items()],
        required=True,
        help_text='Escolha o tipo (sub-modelo) sobre o qual a permissão vale.',
    )
    acao = forms.ChoiceField(
        label='Ação',
        choices=AcaoPermissao.choices,
        required=True,
    )

    class Meta:
        model = PermissaoDeChefe
        fields = [
            'vinculo_permitido',
            'acao',
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['vinculo_permitido'].queryset = get_auditores_ativos()

    def clean(self):
        cleaned_data = super().clean()
        modelo = self.cleaned_data.get('modelo')

        if modelo not in ALVOS_PERMITIDOS:
            self.add_error('modelo', 'Modelo inválido.')

        _, klass = ALVOS_PERMITIDOS[modelo]
        ct = ContentType.objects.get_for_model(klass, for_concrete_model=False)
        cleaned_data['content_type'] = ct
        return cleaned_data

    def save(self, commit=True):
        instance: PermissaoDeChefe = super().save(commit=False)
        instance.concedido_por = self.request.user
        instance.content_type = self.cleaned_data['content_type']

        if commit:
            instance.save()
        return instance


class RevogarPermissaoDeChefeForm(forms.FormPlus):
    motivo_revogacao = forms.CharFieldPlus(label='Motivo da revogação', widget=forms.Textarea(), required=True)
