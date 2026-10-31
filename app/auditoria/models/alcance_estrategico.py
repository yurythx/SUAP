from djtools.db import models


class AlcanceEstrategico(models.Model):
    descricao = models.CharField(max_length=100, unique=True)
    ativo = models.BooleanField(verbose_name='Ativo', default=True)

    def __str__(self):
        return self.descricao
