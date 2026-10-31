from djtools.db import models


class RegimeJuridico(models.ModelPlus):
    SEARCH_FIELDS = ['sigla', 'nome']

    codigo_regime = models.CharField(max_length=2, null=True, db_index=True)
    sigla = models.CharField(max_length=10, null=True, unique=True)
    nome = models.CharField(max_length=40)
    excluido = models.BooleanField(default=False)

    class Meta:
        db_table = 'regime_juridico'

    def __str__(self):
        return self.nome
