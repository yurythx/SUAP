from djtools.db import models


class ModeloPAFCQuery(models.QuerySet):
    def ativos(self):
        return self.filter(ativo=True)


class ModeloPAFCManager(models.Manager):
    def get_queryset(self):
        return ModeloPAFCQuery(self.model, using=self._db)

    def ativos(self):
        return self.get_queryset().ativos()
