import datetime
from typing import Any

from djtools import forms
from rh.models import Servidor
from solenidades.models import AgendamentoSolenidade


class AgendamentoSolenidadeForm(forms.ModelFormPlus):
    class Meta:
        model = AgendamentoSolenidade
        fields = ('data', 'hora_inicio', 'local', 'descricao')

    def clean(self) -> dict[str, Any]:
        data = self.cleaned_data.get('data')
        hora_inicio = self.cleaned_data.get('hora_inicio')
        if not self.errors:
            data_hora = datetime.datetime.combine(data, hora_inicio)
            agora = datetime.datetime.now()
            if agora > data_hora:
                self.add_error('data', 'Não poderão ser solicitados agendamentos para datas passadas.')
                self.add_error('hora_inicio', 'Não poderão ser solicitados agendamentos para datas passadas.')
        return super().clean()

    def save(self, commit):
        self.instance.solicitante = self.request.user.get_vinculo()
        return super().save(commit)


class DeferirAgendamento(forms.ModelFormPlus):
    representante = forms.ModelChoiceFieldPlus(Servidor.objects.ativos(), required=True)

    class Meta:
        model = AgendamentoSolenidade
        fields = ('representante',)

    def save(self):
        instance = super().save()
        instance.responsavel = self.request.user.get_vinculo()
        instance.data_avaliacao = datetime.datetime.now()
        instance.deferida = True
        instance.save()
        instance.enviar_notificacao_status()
        instance.enviar_notificacao_deferimento()
        return instance


class EditarAgendamentoSolenidadeForm(forms.ModelFormPlus):
    class Meta:
        model = AgendamentoSolenidade
        fields = ('data', 'hora_inicio', 'local', 'descricao', 'representante')

    def clean(self) -> dict[str, Any]:
        data = self.cleaned_data.get('data')
        hora_inicio = self.cleaned_data.get('hora_inicio')
        if not self.errors:
            data_hora = datetime.datetime.combine(data, hora_inicio)
            agora = datetime.datetime.now()
            if agora > data_hora:
                self.add_error('data', 'Não poderão ser solicitados agendamentos para datas passadas.')
                self.add_error('hora_inicio', 'Não poderão ser solicitados agendamentos para datas passadas.')
        return super().clean()

    def save(self):
        representante_antigo = AgendamentoSolenidade.objects.get(id=self.instance.id).representante
        instance = super().save()
        novo_representante = instance.representante
        instance.responsavel = self.request.user.get_vinculo()
        instance.data_avaliacao = datetime.datetime.now()
        instance.save()
        if representante_antigo != novo_representante:
            instance.enviar_notificacao_mudanca_representante(representante_antigo, novo_representante)
        return instance
