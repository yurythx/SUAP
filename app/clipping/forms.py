import datetime

from clipping import rss
from clipping.models import Fonte, PalavraChave, Publicacao, PublicacaoDigital, PublicacaoEletronica, PublicacaoImpressa
from djtools import forms
from djtools.utils import running_tests
from rh.models import UnidadeOrganizacional


class RelatorioForm(forms.FormPlus):
    data_inicio = forms.DateFieldPlus(label='Data de Início', required=True)
    data_fim = forms.DateFieldPlus(label='Data de Término', required=True)
    uo = forms.ModelChoiceField(UnidadeOrganizacional.objects.suap().all(), required=False)
    omitir_graficos = forms.BooleanField(required=False, label='Omitir Gráficos')


class PublicacaoForm(forms.ModelFormPlus):
    palavras_chaves = forms.MultipleModelChoiceFieldPlus(PalavraChave.objects.all(), required=True)
    uos = forms.MultipleModelChoiceFieldPlus(UnidadeOrganizacional.objects.suap().all(), required=False, label='Campus')

    class Meta:
        model = Publicacao
        exclude = ()

    def clean_data(self):
        if self.cleaned_data.get('data') > datetime.date.today():
            raise forms.ValidationError('A data da publicação não pode ser maior que a data de hoje.')

        return self.cleaned_data.get('data')


class PublicacaoDigitalForm(PublicacaoForm):
    class Meta:
        model = PublicacaoDigital
        exclude = ()


class PublicacaoEletronicaForm(PublicacaoForm):
    class Meta:
        model = PublicacaoEletronica
        exclude = ()


class PublicacaoImpressaForm(PublicacaoForm):
    class Meta:
        model = PublicacaoImpressa
        exclude = ()


class FonteForm(forms.ModelFormPlus):
    class Meta:
        model = Fonte
        exclude = ()

    def clean_link(self):
        url = self.cleaned_data['link']
        if running_tests():
            return True
        try:
            itens = rss.read(url)
            if not itens:
                raise forms.ValidationError(f'O link {url} não aponta para um arquivo de rss válido')
            else:
                return url
        except Exception:
            raise forms.ValidationError(f'O link {url} não aponta para um arquivo de rss válido')
