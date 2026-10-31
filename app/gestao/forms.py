from djtools import forms
from gestao.models import PeriodoReferencia


class PeriodoReferenciaForm(forms.ModelFormPlus):
    class Meta:
        model = PeriodoReferencia
        exclude = ('user',)


class PeriodoReferenciaGlobalForm(PeriodoReferenciaForm):
    pass


class ConfiguracaoForm(forms.FormPlus):
    ano_referencia = forms.CharField(label='Ano de Referência', required=False)
    data_inicio = forms.CharField(label='Data de Início', required=False, help_text='Formato dd/mm/AAAA')
    data_termino = forms.CharField(label='Data de Término', required=False, help_text='Formato dd/mm/AAAA')


class CompararaVariavelForm(forms.FormPlus):
    arquivo = forms.FileFieldPlus(
        label='Arquivo',
        help_text='Arquivo CSV contendo: Código da unidade gestora executora, Nome da unidade gestora executora, Natureza do empenho e o Valor.',
    )
