from djtools import forms
from edu.models import Credenciamento


class CredenciamentoForm(forms.ModelFormPlus):
    class Meta:
        model = Credenciamento
        exclude = ()

    class Media:
        js = ('/static/edu/js/CredenciamentoForm.js',)

    def clean_numero_ato(self):
        numero = self.cleaned_data['numero_ato']
        if numero:
            if not numero.isdigit():
                raise forms.ValidationError('Informe um número.')
            if numero[0] == '0':
                raise forms.ValidationError('O número não pode iniciar com zero.')
        return numero

    def clean_numero_publicacao(self):
        numero_publicacao = self.cleaned_data['numero_publicacao']
        if numero_publicacao:
            if not numero_publicacao.isdigit():
                raise forms.ValidationError('Informe um número.')
            if numero_publicacao[0] == '0':
                raise forms.ValidationError('O número não pode iniciar com zero.')
        return numero_publicacao

    def clean_secao_publicacao(self):
        secao_publicacao = self.cleaned_data['secao_publicacao']
        if secao_publicacao:
            if not secao_publicacao.isdigit():
                raise forms.ValidationError('Informe um número.')
            if secao_publicacao[0] == '0':
                raise forms.ValidationError('O número não pode iniciar com zero.')
        return secao_publicacao

    def clean_pagina_publicacao(self):
        pagina_publicacao = self.cleaned_data['pagina_publicacao']
        if pagina_publicacao:
            if not pagina_publicacao.isdigit():
                raise forms.ValidationError('Informe um número.')
            if pagina_publicacao[0] == '0':
                raise forms.ValidationError('O número não pode iniciar com zero.')
        return pagina_publicacao
