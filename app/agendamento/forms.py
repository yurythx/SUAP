from datetime import datetime

from django.core.exceptions import ValidationError

#
from djtools import forms
from djtools.utils import get_datetime_now


class SolicitacaoAgendamentoBaseForm(forms.BaseForm):
    #
    def verificar_recorrencia(self, data):
        semana = [
            data['recorrencia_segunda'],
            data['recorrencia_terca'],
            data['recorrencia_quarta'],
            data['recorrencia_quinta'],
            data['recorrencia_sexta'],
            data['recorrencia_sabado'],
            data['recorrencia_domingo'],
        ]
        if not any(semana):
            raise ValidationError('Selecione, no mínimo, um dia da semana')

    #
    def verificar_datas(self, data):
        if data['hora_fim'] < data['hora_inicio']:
            self.add_error('hora_fim', 'Hora de términio deve ocorrer depois da hora de início')
        #
        if data['data_fim'] < data['data_inicio']:
            self.add_error('data_fim', 'Data de Fim deve ser maior ou igual a Data de Início.')
        #
        data_hora_inicio = datetime.combine(data['data_inicio'], data['hora_inicio'])
        hoje = get_datetime_now()
        #
        if data_hora_inicio < hoje:
            if data['data_inicio'] < hoje.date():
                self.add_error('data_inicio', 'Data de início deve ocorrer em alguma data no futuro')
            #
            if data['hora_inicio'] < hoje.time():
                self.add_error('hora_inicio', 'A hora de início deve ocorrer em algum ponto no futuro')

    #
    def clean(self):
        cleaned_data = super().clean()
        if self.is_valid():
            self.verificar_datas(cleaned_data)
            self.verificar_recorrencia(cleaned_data)
        return cleaned_data


#


class SolicitacaoAgendamentoForm(SolicitacaoAgendamentoBaseForm, forms.FormPlus):
    data_inicio = forms.DateFieldPlus(label='Data de Início', required=True)
    data_fim = forms.DateFieldPlus(label='Data de Término', required=True)
    hora_inicio = forms.TimeFieldPlus(label='Hora início', required=True)
    hora_fim = forms.TimeFieldPlus(label='Hora fim', required=True)
    #
    recorrencia_segunda = forms.BooleanField(label='Segunda', required=False)
    recorrencia_terca = forms.BooleanField(label='Terça', required=False)
    recorrencia_quarta = forms.BooleanField(label='Quarta', required=False)
    recorrencia_quinta = forms.BooleanField(label='Quinta', required=False)
    recorrencia_sexta = forms.BooleanField(label='Sexta', required=False)
    recorrencia_sabado = forms.BooleanField(label='Sábado', required=False)
    recorrencia_domingo = forms.BooleanField(label='Domingo', required=False)


class SolicitacaoAgendamentoModelForm(SolicitacaoAgendamentoBaseForm, forms.ModelFormPlus):
    data_inicio = forms.DateFieldPlus(label='Data de Início', required=True)
    data_fim = forms.DateFieldPlus(label='Data de Término', required=True)
    hora_inicio = forms.TimeFieldPlus(label='Hora início', required=True)
    hora_fim = forms.TimeFieldPlus(label='Hora fim', required=True)
    #
    recorrencia_segunda = forms.BooleanField(label='Segunda', required=False)
    recorrencia_terca = forms.BooleanField(label='Terça', required=False)
    recorrencia_quarta = forms.BooleanField(label='Quarta', required=False)
    recorrencia_quinta = forms.BooleanField(label='Quinta', required=False)
    recorrencia_sexta = forms.BooleanField(label='Sexta', required=False)
    recorrencia_sabado = forms.BooleanField(label='Sábado', required=False)
    recorrencia_domingo = forms.BooleanField(label='Domingo', required=False)
