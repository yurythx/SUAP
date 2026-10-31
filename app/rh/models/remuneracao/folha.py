from djtools.choices import Meses
from djtools.db import models
from djtools.utils import get_datetime_now


class CronogramaFolha(models.ModelPlus):
    mes = models.PositiveIntegerField('Mês', null=False, blank=False)
    ano = models.ForeignKeyPlus('comum.Ano', verbose_name='Ano', null=False, blank=False, on_delete=models.CASCADE)
    data_abertura_atualizacao_folha = models.DateFieldPlus('Abertura do SIAPE para Atualização da Folha', null=False, blank=False)
    data_fechamento_processamento_folha = models.DateFieldPlus('Fechamento do SIAPE para Processamento da Folha', null=False, blank=False)
    data_consulta_previa_folha = models.DateFieldPlus('Consulta da Prévia da Folha', null=False, blank=False)
    data_abertura_proxima_folha = models.DateFieldPlus('Abertura da Próxima Folha', null=False, blank=False)
    data_cadastro = models.DateTimeFieldPlus('Data de Cadastro', null=True, blank=True, auto_now_add=True)

    class Meta:
        verbose_name = 'Cronograma da Folha'
        verbose_name_plural = 'Cronogramas das Folhas'

    def __str__(self):
        return f'{Meses.get_mes(self.mes)}/{self.ano.ano}'

    @classmethod
    def get_cronograma_hoje(cls):
        hoje = get_datetime_now().date()
        qs_cronograma = CronogramaFolha.objects.filter(data_fechamento_processamento_folha__gte=hoje).order_by('data_fechamento_processamento_folha')
        return qs_cronograma.first()
