from djtools.db import models


class Banco(models.ModelPlus):
    codigo = models.CharField(max_length=3)
    sigla = models.CharField(max_length=15)
    nome = models.CharField(max_length=30)
    excluido = models.BooleanField(default=False)

    def __str__(self):
        return self.nome

    def get_ext_combo_template(self):
        return f'{self.codigo} - {self.nome}'
