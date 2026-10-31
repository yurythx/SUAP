from djtools.db import models


class GrupoDeficiencia(models.ModelPlus):
    codigo = models.CharFieldPlus('Código', null=False, blank=False)
    descricao = models.CharFieldPlus('Descrição', null=False, blank=False)

    class Meta:
        verbose_name = 'Grupo de Deficiência'
        verbose_name_plural = 'Grupos de Deficiências'

    def __str__(self):
        return f'[{self.codigo}] - {self.descricao}'


class Deficiencia(models.ModelPlus):
    grupo_deficiencia = models.ForeignKeyPlus('rh.GrupoDeficiencia', verbose_name='Grupo de Deficiência', on_delete=models.CASCADE)
    codigo = models.CharFieldPlus('Código', null=False, blank=False)
    descricao = models.CharFieldPlus('Descrição', null=False, blank=False)

    class Meta:
        verbose_name = 'Deficiência'
        verbose_name_plural = 'Deficiências'

    def __str__(self):
        return f'{self.grupo_deficiencia.descricao} - {self.descricao}'
