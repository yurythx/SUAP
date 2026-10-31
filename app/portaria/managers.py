from datetime import timedelta

from django.apps import apps
from django.db import models
from django.db.models import ExpressionWrapper, F

from djtools.utils import get_datetime_now


class AcessoQuerySet(models.query.QuerySet):
    def get_model(self):
        return apps.get_model('portaria', 'Acesso')

    def validos(self):
        return self.annotate(
            expires=ExpressionWrapper(
                F('data_geracao_chave_wifi') + (timedelta(days=1) * F('quantidade_dias_chave_wifi')), output_field=models.DateTimeField()
            )
        ).filter(expires__gt=get_datetime_now().date())


class AcessoManager(models.Manager):
    def get_queryset(self):
        return AcessoQuerySet(self.model, using=self._db)

    def validos(self):
        return self.get_queryset().validos()
