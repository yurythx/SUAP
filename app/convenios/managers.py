import datetime

from django.db import models
from django.db.models import QuerySet

from comum.models import Configuracao


class ParceriaInternacionalQueryset(models.QuerySet):
    def ativos(self) -> QuerySet:
        hoje = datetime.date().today()
        return self.filter(data_inicio__lte=hoje, data_fim__gte=hoje)


class ParceriaInternacionalManager(models.Manager):
    def get_queryset(self) -> QuerySet:
        return ParceriaInternacionalQueryset(self.model, using=self._db)

    def filtrar_tipo_internacionalizacao(self, queryset: QuerySet) -> QuerySet:
        tipo_internacionalizacao = Configuracao.get_valor_por_chave('convenios', 'tipo_parceria_relacoes_internacionais')
        if tipo_internacionalizacao:
            queryset = queryset.filter(tipo_id=int(tipo_internacionalizacao))
        return queryset

    def all(self) -> QuerySet:
        return self.filtrar_tipo_internacionalizacao(super().all())
