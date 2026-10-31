import datetime
from djtools.db import models


class SetorJornadaHistorico(models.ModelPlus):
    setor = models.ForeignKeyPlus('rh.Setor', verbose_name='Setor', null=False, blank=False, on_delete=models.CASCADE)
    jornada_trabalho = models.ForeignKeyPlus('rh.JornadaTrabalho', verbose_name='Jornada de Trabalho', null=False, blank=False)
    data_inicio_da_jornada = models.DateFieldPlus('Data Inicial da Jornada', null=False, blank=False, default=datetime.datetime.today)
    data_fim_da_jornada = models.DateFieldPlus('Data Final da Jornada', null=True, blank=True)

    def __str__(self):
        # MeuSetor: 2 horas semanas - 01/01/0000 a 31/12/9999
        data_fim = '-'
        if self.data_fim_da_jornada:
            data_fim = self.data_fim_da_jornada.strftime('%d/%m/%Y')

        if self.data_fim_da_jornada:
            return '{}: {} - {} a {}'.format(self.setor, self.jornada_trabalho, self.data_inicio_da_jornada.strftime('%d/%m/%Y'), data_fim)
        else:
            return '{}: {} - a partir de {}'.format(self.setor, self.jornada_trabalho, self.data_inicio_da_jornada.strftime('%d/%m/%Y'))

    class Meta:
        verbose_name = 'Histórico de Jornada do Setor'
        verbose_name_plural = 'Históricos de Jornadas dos Setores'
        ordering = ('setor', '-data_inicio_da_jornada')
