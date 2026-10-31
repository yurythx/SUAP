from django.apps import apps
from django.db.models.query import QuerySet

from djtools.db import models


class TipoServicoQueryset(QuerySet):
    def get_model(self):
        return apps.get_model('auditoria', 'TipoServico')

    def ativos(self):
        return self.filter(ativo=True)


class TipoServicoManager(models.Manager):
    def get_queryset(self):
        return TipoServicoQueryset(self.model, using=self._db)

    def ativos(self):
        return self.get_queryset().ativos()


class TipoServico(models.ModelPlus):
    SEARCH_FIELDS = ['nome']
    nome = models.CharField(verbose_name='Nome', max_length=100, unique=True)
    descricao = models.CharField(verbose_name='Descrição', null=True, blank=True, max_length=255)
    gera_ordem_servico = models.BooleanField(verbose_name='Gera Ordem de Serviço?', default=True)
    requer_revisor = models.BooleanField(default=True, verbose_name='Requer revisor?')
    ativo = models.BooleanField(default=True, verbose_name='Ativo')

    #
    objects = TipoServicoManager()

    class Meta:
        verbose_name = 'Tipo de serviço'
        verbose_name_plural = 'Tipos de serviços'

    def __str__(self):
        return self.nome
