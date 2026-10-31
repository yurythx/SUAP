from djtools.db import models


class NivelEscolaridade(models.ModelPlus):
    nome = models.CharField(max_length=45)
    codigo = models.CharField(max_length=10, null=True, unique=True)
    descricao = models.CharField(max_length=60)
    excluido = models.BooleanField(default=False)

    class Meta:
        db_table = 'nivel_escolaridade'
        verbose_name = 'Nível de Escolaridade'
        verbose_name_plural = 'Níveis de Escolaridade'

    def __str__(self):
        return self.nome
