from djtools.db import models


class CargoClasse(models.ModelPlus):
    codigo = models.CharField(max_length=10, null=True, unique=True)
    nome = models.CharField(max_length=40)
    excluido = models.BooleanField(default=False)

    class Meta:
        verbose_name = 'Classe do Cargo'
        verbose_name_plural = 'Classes do Cargo'

    def __str__(self):
        return self.nome


class QuantitativoCargoClassePorCampus(models.ModelPlus):
    cargo_classe = models.ForeignKeyPlus('rh.CargoClasse', verbose_name='Cargo classe', null=False)
    uo = models.ForeignKeyPlus('rh.UnidadeOrganizacional', verbose_name='Unidade Organizacional', null=False)
    quantidade = models.PositiveIntegerFieldPlus('Quantidade de vagas')

    class Meta:
        verbose_name = 'Quantitativo de classe de cargo por unidade organizacional'
        verbose_name_plural = 'Quantitativos de classes de cargo por unidades organizacionais'
        unique_together = ('cargo_classe', 'uo')

    def __str__(self):
        return f'{self.quantidade} vagas {self.cargo_classe} para {self.uo}'
