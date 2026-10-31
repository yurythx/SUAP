from djtools.db import models
from rh.enums import TipoExtracao


class ExcecaoDado(models.ModelPlus):
    servidor = models.ForeignKeyPlus('rh.Servidor', verbose_name='Servidor', on_delete=models.CASCADE)
    campos = models.ManyToManyFieldPlus('rh.CampoExcecao', verbose_name='Campos')
    tipo_extracao = models.IntegerFieldPlus('Tipo de Extração', choices=TipoExtracao.get_choices(), null=True)

    class Meta:
        verbose_name = 'Exceção Dados'
        verbose_name_plural = 'Exceções Dados'
