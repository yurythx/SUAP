from djtools.db import models


class TipoUnidadeOrganizacional(models.ModelPlus):
    descricao = models.CharFieldPlus('Descrição')

    class Meta:
        verbose_name = 'Tipo de Unidade Organizacional'
        verbose_name_plural = 'Tipos de Unidade Organizacional'

    def __str__(self):
        return self.descricao
