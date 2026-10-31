from djtools.db import models


class DiplomaLegal(models.ModelPlus):
    codigo = models.CharField(max_length=10, null=True, unique=True)
    nome = models.CharField(max_length=40)
    sigla = models.CharField(max_length=10)
    excluido = models.BooleanField(default=False)

    class Meta:
        db_table = 'diploma_legal'
        verbose_name = 'Diploma Legal'
        verbose_name_plural = 'Diplomas Legais'

    def __str__(self):
        return self.sigla
