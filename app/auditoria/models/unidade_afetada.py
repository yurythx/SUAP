from djtools.db import models


class UnidadeAfetada(models.Model):
    nome = models.CharField(max_length=50, unique=True)
    ativo = models.BooleanField(verbose_name='Ativo', default=True)

    def __str__(self):
        return self.nome
