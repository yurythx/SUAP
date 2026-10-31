from django.apps import apps
from django.db.models import query

from djtools.db import models


class PerspectivaEstrategicaQueryset(query.QuerySet):
    def get_model(self):
        return apps.get_model('auditoria', 'PerspectivaEstrategica')

    def ativas(self):
        return self.filter(ativa=True)


class PerspectivaEstrategicaManager(models.Manager):
    def get_queryset(self):
        return PerspectivaEstrategicaQueryset(self.model, using=self._db)

    def ativas(self):
        return self.get_queryset().ativas()


class PerspectivaEstrategica(models.ModelPlus):
    nome = models.CharFieldPlus(verbose_name='Nome', unique=True)
    descricao = models.CharField(verbose_name='Descrição', null=True, blank=True, max_length=255)
    ativa = models.BooleanField(default=True, verbose_name='Ativa')

    objects = PerspectivaEstrategicaManager()

    class Meta:
        verbose_name = 'Perspectiva Estratégica'
        verbose_name_plural = 'Perspectivas Estratégicas'

    def __str__(self):
        return f'{self.nome}'
