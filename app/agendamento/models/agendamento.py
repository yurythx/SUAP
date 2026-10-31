#
from django.conf import settings
from django.utils.dateformat import format, time_format

#
from django_fsm import FSMIntegerField, transition

from agendamento.managers import AgendamentoManager

# Local module imports
from agendamento.status import AgendamentoStatus

#
from djtools.db import models
from djtools.db.models import CurrentUserField
from djtools.utils import get_datetime_now


class Agendamento(models.ModelPlus):
    #
    status = FSMIntegerField('Status', default=AgendamentoStatus.STATUS_INATIVO, choices=AgendamentoStatus.STATUS_CHOICES, protected=True)
    #
    data_hora_inicio = models.DateTimeFieldPlus('Data/Hora inicial', null=True)
    data_hora_fim = models.DateTimeFieldPlus('Data/Hora final', null=True)
    #
    justificativa_cancelamento = models.TextField('Justificativa do Cancelamento', blank=True)
    cancelada_por = CurrentUserField(default=None)
    data_cancelamento = models.DateTimeFieldPlus('Data da Cancelamento', null=True)

    objects = AgendamentoManager()

    class Meta:
        abstract = True

    @property
    def solicitante(self):
        return self.solicitacao.solicitante

    @property
    def data_fim(self):
        return self.data_hora_fim.date()

    @property
    def data_inicio(self):
        return self.data_hora_inicio.date()

    @property
    def ativo(self):
        return self.status == AgendamentoStatus.STATUS_ATIVO

    @property
    def inativo(self):
        return self.status == AgendamentoStatus.STATUS_INATIVO

    @property
    def finalizado(self):
        return self.status == AgendamentoStatus.STATUS_FINALIZADO

    ###
    def get_ocorrencias(self):
        return f'{time_format(self.data_hora_inicio, settings.TIME_FORMAT)} as {time_format(self.data_hora_fim, settings.TIME_FORMAT)} em {format(self.data_hora_inicio, settings.DATE_FORMAT)}'

    def existe_agendamentos(self):
        model = type(self)
        return model.objects.filter(solicitacao=self.solicitacao).exclude(id=self.id).exists()

    def pode_finalizar(self):
        hoje = get_datetime_now()
        return not self.finalizado and self.possui_permissao() and (self.inativo and hoje > self.data_hora_fim)

    def pode_ativar(self):
        hoje = get_datetime_now()
        return self.possui_permissao() and self.inativo and (self.data_hora_inicio <= hoje < self.data_hora_fim)

    def pode_inativar(self):
        return self.possui_permissao() and self.ativo

    ##############################################################################
    #  Transições
    ##############################################################################
    @transition(
        field=status,
        source=[AgendamentoStatus.STATUS_INATIVO, AgendamentoStatus.STATUS_ATIVO],
        target=AgendamentoStatus.STATUS_ATIVO,
        conditions=[pode_ativar],
    )
    def ativar(self):
        pass

    #

    @transition(
        field=status,
        source=[AgendamentoStatus.STATUS_ATIVO, AgendamentoStatus.STATUS_INATIVO],
        target=AgendamentoStatus.STATUS_INATIVO,
        conditions=[pode_inativar],
    )
    def inativar(self):
        pass

    @transition(field=status, source=AgendamentoStatus.STATUS_INATIVO, target=AgendamentoStatus.STATUS_FINALIZADO)
    def finalizar(self):
        pass

    #
    def possui_permissao(self):
        raise NotImplementedError

    def _finalizar_solicitacao(self):
        raise NotImplementedError

    #

    def save(self, *args, **kwargs):
        if self.pode_finalizar():
            self.finalizar()
            self._finalizar_solicitacao()
        #
        super().save(*args, **kwargs)
