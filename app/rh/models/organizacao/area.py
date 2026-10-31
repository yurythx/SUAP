from djtools.db import models
from rh.managers import AreaConhecimentoManager


class AreaConhecimento(models.ModelPlus):
    SEARCH_FIELDS = ['descricao', 'codigo']
    superior = models.ForeignKeyPlus('rh.AreaConhecimento', null=True, verbose_name='Superior', on_delete=models.CASCADE)
    codigo = models.CharField('Código', max_length=8, unique=True)
    descricao = models.CharField('Descrição', max_length=255)

    objects = AreaConhecimentoManager()

    class Meta:
        verbose_name = 'Área do Conhecimento'
        verbose_name_plural = 'Áreas de Conhecimento'

    def __str__(self):
        return f'{self.descricao} ({self.superior})' if self.superior else self.descricao
