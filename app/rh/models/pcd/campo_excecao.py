from djtools.db import models


class CampoExcecao(models.ModelPlus):
    campo = models.CharField('Campo', max_length=255)

    class Meta:
        verbose_name = 'Campo de exceção'
        verbose_name_plural = 'Campos de exceção'
