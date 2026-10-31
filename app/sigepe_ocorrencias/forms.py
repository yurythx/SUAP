from djtools import forms
from sigepe_ocorrencias.models import PacoteOcorrenciaSigepe


class UploadArquivoRetornoForm(forms.ModelFormPlus):
    class Meta:
        model = PacoteOcorrenciaSigepe
        fields = ('arquivo_retorno_arquivo',)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['arquivo_retorno_arquivo'].required = True


class PacoteOcorrenciaSigepeForm(forms.ModelFormPlus):
    class Meta:
        model = PacoteOcorrenciaSigepe
        exclude = ()

    def clean(self):
        ano = self.cleaned_data.get('ano')
        mes = self.cleaned_data.get('mes')

        if ano:
            if ano < 2025:
                raise forms.ValidationError('Só é possível gerar as ocorrências de 2025 em diante.')
            if mes and ano == 2025 and mes < 10:
                raise forms.ValidationError('Só é possível gerar as ocorrências de 10/2025 em diante.')

        return self.cleaned_data
