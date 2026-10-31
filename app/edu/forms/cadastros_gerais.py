from django.core.exceptions import ValidationError

from djtools import forms
from edu.models import (
    ConfiguracaoLivro,
    FormaIngresso,
)


class ConfiguracaoLivroForm(forms.ModelFormPlus):
    class Meta:
        model = ConfiguracaoLivro
        exclude = ('codigo_qacademico',)

    def clean(self):
        invalido = False
        modalidades = []
        uo = self.cleaned_data.get('uo', None)
        if uo:
            modalidades = self.cleaned_data.get('modalidades', [])

            if self.instance.pk is None:
                if ConfiguracaoLivro.objects.filter(uo=uo, modalidades__in=modalidades).exists():
                    invalido = True
            elif ConfiguracaoLivro.objects.filter(uo=uo, modalidades__in=modalidades).exclude(pk=self.instance.pk).exists():
                invalido = True

            if invalido:
                raise ValidationError('A(s) modalidade(s) escolhida(s) já possui(em) uma configuração de livro no campus selecionado.')

            return self.cleaned_data


class FormaIngressoForm(forms.ModelForm):
    class Meta:
        model = FormaIngresso
        exclude = ()

    def clean_racas(self):
        if self.cleaned_data['programa_vaga_etinico'] and not self.cleaned_data['racas']:
            raise forms.ValidationError('Informe as raças/etnias correspondente.')
        return self.cleaned_data['racas']
