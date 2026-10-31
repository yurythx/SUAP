import operator
from functools import reduce

from django.db import models
from django.db.models.query_utils import Q

from djtools.utils import get_datetime_now

from .status import AgendamentoStatus, SolicitacaoAgendamentoStatus


class SolicitacaoAgendamentoQueryset(models.query.QuerySet):
    def pendentes(self):
        return self.filter(status=SolicitacaoAgendamentoStatus.STATUS_ESPERANDO)

    def deferidas(self):
        return self.filter(status=SolicitacaoAgendamentoStatus.STATUS_DEFERIDA)

    def indeferidas(self):
        return self.filter(status=SolicitacaoAgendamentoStatus.STATUS_INDEFERIDA)

    def finalizadas(self):
        return self.filter(status=SolicitacaoAgendamentoStatus.STATUS_FINALIZADO)

    def expiradas(self):
        hoje = get_datetime_now()
        q_filters = [Q(data_fim__lt=hoje.date()), Q(data_fim=hoje.date(), hora_fim__lt=hoje.time())]
        return self.deferidas().filter(reduce(operator.or_, q_filters))


class SolicitacaoAgendamentoManager(models.Manager):
    def get_queryset(self):
        return SolicitacaoAgendamentoQueryset(self.model, using=self._db)

    def pendentes(self):
        return self.get_queryset().pendentes()

    def deferidas(self):
        return self.get_queryset().deferidas()

    def indeferidas(self):
        return self.get_queryset().indeferidas()

    def expiradas(self):
        return self.get_queryset().expiradas()

    def finalizadas(self):
        return self.get_queryset().finalizadas()


class AgendamentoQueryset(models.query.QuerySet):
    def ativos(self):
        return self.filter(status=AgendamentoStatus.STATUS_ATIVO)

    def inativos(self):
        return self.filter(status=AgendamentoStatus.STATUS_INATIVO)

    def finalizados(self):
        return self.filter(status=AgendamentoStatus.STATUS_FINALIZADO)

    def expirados(self):
        hoje = get_datetime_now()
        q_filters = [Q(data_fim__lt=hoje.date()), Q(data_fim=hoje.date(), hora_fim__lt=hoje.time())]
        return self.filter(reduce(operator.or_, q_filters))


class AgendamentoManager(models.Manager):
    def get_queryset(self):
        return AgendamentoQueryset(self.model, using=self._db)

    def ativos(self):
        return self.get_queryset().ativos()

    def inativos(self):
        return self.get_queryset().inativos()

    def expirados(self):
        return self.get_queryset().expirados()

    def finalizados(self):
        return self.get_queryset().finalizados()
