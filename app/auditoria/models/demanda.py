from django.apps import apps
from django.db.models.query import QuerySet

from djtools.db import models


class OrigemDemandaQueryset(QuerySet):
    def get_model(self):
        return apps.get_model('auditoria', 'OrigemDemanda')

    def ativas(self):
        return self.filter(ativa=True)


class OrigemDemandaManager(models.Manager):
    def get_queryset(self):
        return OrigemDemandaQueryset(self.model, using=self._db)

    def ativas(self):
        return self.get_queryset().ativas()


class OrigemDemanda(models.ModelPlus):
    nome = models.CharFieldPlus(verbose_name='Nome', unique=True)
    descricao = models.CharField(verbose_name='Descrição', null=True, blank=True, max_length=255)
    ativa = models.BooleanField(default=True, verbose_name='Ativa')

    objects = OrigemDemandaManager()

    class Meta:
        verbose_name = 'Origem da demanda'
        verbose_name_plural = 'Origens das demandas'

    def __str__(self):
        return self.nome
