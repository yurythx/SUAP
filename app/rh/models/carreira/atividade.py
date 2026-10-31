from djtools.db import models


class AtividadesUsadasManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(servidor__isnull=False).distinct()

    def __str__(self):
        return self.nome


class Atividade(models.ModelPlus):
    codigo = models.CharField(max_length=10, null=True, unique=True)
    nome = models.CharField(max_length=40)
    excluido = models.BooleanField(default=False)

    DIRETOR_GERAL = '0009'
    DIRETOR = '0099'
    REITOR = '0062'

    objects = models.Manager()
    usadas = AtividadesUsadasManager()

    class Meta:
        db_table = 'atividade'
        verbose_name = 'Atividade'
        verbose_name_plural = 'Atividades'
        ordering = ['nome']

    def __str__(self):
        return f'{self.codigo} - {self.nome}'
