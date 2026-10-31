from django.apps import apps
from auditoria.models.servico import TipoServico
from comum.models import Vinculo
from djtools.db import models
from django.db.models.query import QuerySet


class AcaoQueryset(QuerySet):
    def get_model(self):
        return apps.get_model('auditoria', 'Acao')

    def ativas(self):
        return self.filter(ativo=True)


class AcaoManager(models.Manager):
    def get_queryset(self):
        return AcaoQueryset(self.model, using=self._db)

    def ativas(self):
        return self.get_queryset().ativas()


class Acao(models.Model):
    SEARCH_FIELDS = ['nome']
    nome = models.CharField(max_length=255, unique=True, verbose_name='Nome da ação')
    tipo_servico = models.ForeignKey(TipoServico, verbose_name='Tipo de Serviço', on_delete=models.CASCADE, null=False, blank=False)
    ativo = models.BooleanField(default=True, verbose_name='Ativo')
    criado_por = models.ForeignKeyPlus(
        Vinculo, on_delete=models.SET_NULL, null=True, blank=True, related_name='%(app_label)s_%(class)s_criado_por', verbose_name='Criado por'
    )
    alterado_por = models.ForeignKeyPlus(
        Vinculo, on_delete=models.SET_NULL, null=True, blank=True, related_name='%(app_label)s_%(class)s_alterado_por', verbose_name='Alterado por'
    )
    criado_em = models.DateTimeField(auto_now_add=True, verbose_name='Criado em')
    modificado_em = models.DateTimeField(auto_now=True, verbose_name='Atualizado em')

    objects = AcaoManager()

    class Meta:
        verbose_name = 'Ação da Auditoria'
        verbose_name_plural = 'Ações da Auditoria'

    def __str__(self):
        return self.nome

    def get_absolute_url(self):
        return f'/admin/auditoria/acao/{self.id}'
