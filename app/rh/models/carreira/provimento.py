from djtools.db import models


class FormaProvimentoVacancia(models.ModelPlus):
    SEARCH_FIELDS = ['codigo', 'descricao']

    CODIGO_PROGRESSAO = '046'
    CODIGO_POSSE_EM_OUTRO_CARGO_INACUMULADO = '611'
    CODIGO_REDISTRIBUICAO = '007'

    codigo = models.CharField(max_length=10, unique=True)
    descricao = models.CharField(max_length=40)

    class Meta:
        verbose_name = 'Provimento de Cargo Vacância'
        verbose_name_plural = 'Provimentos de Cargo Vacância'

    def __str__(self):
        return f'{self.descricao}'
