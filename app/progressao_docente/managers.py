from django.db import models


class CriterioQuery(models.QuerySet):
    def necessita_arquivo(self):
        return self.filter(necessita_arquivos=True)

    def autoavaliacao(self):
        return self.filter(autoavaliacao=True)

    def do_avaliador(self):
        return self.filter(autoavaliacao=False)


class CriterioManager(models.Manager):
    def necessita_arquivo(self):
        return self.get_queryset().necessita_arquivo()

    def autoavaliacao(self):
        return self.get_queryset().autoavaliacao()

    def do_avaliador(self):
        return self.get_queryset().do_avaliador()

    def get_queryset(self):
        return CriterioQuery(self.model, using=self._db)
