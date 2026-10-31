from django.apps import apps
from django.db.models.query import QuerySet

from djtools.db import models


class NucleoAuditoriaQueryset(QuerySet):
    def get_model(self):
        return apps.get_model('auditoria', 'NucleoAuditoria')

    def ativos(self):
        return self.filter(ativo=True)


class NucleoAuditoriaManager(models.Manager):
    def get_queryset(self):
        return NucleoAuditoriaQueryset(self.model, using=self._db)

    def ativos(self):
        return self.get_queryset().ativos()


class NucleoAuditoria(models.ModelPlus):
    SEARCH_FIELDS = ['id', 'nome']

    nome = models.CharFieldPlus(verbose_name='Nome', unique=True, max_length=25)
    descricao = models.CharFieldPlus(verbose_name='Descrição', max_length=200, null=True, blank=True)
    coordenador = models.ForeignKeyPlus(
        'comum.Vinculo', verbose_name='Coordenador', null=False, blank=False, related_name='%(app_label)s_%(class)s_coordenador'
    )
    membros = models.ManyToManyFieldPlus('comum.Vinculo', verbose_name='Membros')
    email = models.CharFieldPlus(max_length=255, verbose_name='E-mail principal', null=True, blank=True)
    ramal = models.CharFieldPlus(verbose_name='Ramal', null=True, blank=True, max_length=10)
    ativo = models.BooleanField(default=True)

    objects = NucleoAuditoriaManager()

    class Meta:
        verbose_name = 'Núcleo de Auditoria'
        verbose_name_plural = 'Núcleos de Auditoria'

    def __str__(self):
        return self.nome

    def get_absolute_url(self):
        return f'/admin/auditoria/nucleoauditoria/{self.id}'
