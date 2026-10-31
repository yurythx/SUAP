from functools import reduce
from operator import and_ as AND

from django.apps import apps
from django.db import models
from django.db.models import Q

from .models import SolicitacaoStatus
from .status import CienciaStatus


class TipoProcessoQueryset(models.query.QuerySet):
    def get_model(self):
        return apps.get_model('processo_eletronico', 'TipoProcesso')

    def ativos(self):
        return self.filter(ativo=True)


class TipoProcessoManager(models.Manager):
    def get_queryset(self):
        return TipoProcessoQueryset(self.model, using=self._db)

    def ativos(self):
        return self.get_queryset().ativos()


class SolicitacaoDespachoManager(models.Manager):
    def solicitacao_pendente(self, solicitado, processo_id=None):
        q_list = [Q(solicitado=solicitado), Q(data_resposta__isnull=True), Q(status=SolicitacaoStatus.STATUS_ESPERANDO)]
        if processo_id:
            q_list.append(Q(processo__id=processo_id))
        return self.get_queryset().filter(reduce(AND, q_list))

    def requisicao_pendente(self, user):
        return self.get_queryset().filter(solicitante=user, data_resposta__isnull=True, status=SolicitacaoStatus.STATUS_ESPERANDO)


class SolicitacaoCienciaManager(models.Manager):
    def solicitacoes_pendentes(self):
        return self.get_queryset().filter(data_ciencia__isnull=True, status=CienciaStatus.STATUS_ESPERANDO)

    def solicitacoes_consideradas_cientes(self):
        return self.get_queryset().filter(data_ciencia__isnull=True, status=CienciaStatus.STATUS_CONSIDERADO_CIENTE)

    def solicitacoes_pendentes_por_processo(self, processo):
        return self.get_queryset().filter(processo=processo, data_ciencia__isnull=True, status=CienciaStatus.STATUS_ESPERANDO)
