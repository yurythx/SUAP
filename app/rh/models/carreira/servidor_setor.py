from djtools.db import models


class ServidorSetorHistorico(models.ModelPlus):
    servidor = models.ForeignKeyPlus('rh.Servidor', null=False)
    setor = models.ForeignKeyPlus('rh.Setor', null=False, on_delete=models.CASCADE)
    data_inicio_no_setor = models.DateField(null=False)
    data_fim_no_setor = models.DateField(null=True, blank=True)

    class Meta:
        db_table = 'suap_servidorsetorhistorico'
        unique_together = ('servidor', 'data_inicio_no_setor')
        verbose_name = 'Histórico Setor Servidor'
        verbose_name_plural = 'Histórico Setores Servidor'

    def __str__(self):
        return '{} - {} - {}'.format(self.servidor.pessoa_fisica.nome, self.setor.nome, self.data_inicio_no_setor.strftime('%d/%m/%Y'))


class ServidorSetorLotacaoHistorico(models.ModelPlus):
    servidor = models.ForeignKeyPlus('rh.Servidor', null=False, blank=False)
    setor_lotacao = models.ForeignKeyPlus('rh.Setor', null=False, blank=False, on_delete=models.CASCADE)
    setor_exercicio = models.ForeignKeyPlus(
        'rh.Setor', related_name='servidor_setor_exercicio_historico', null=False, blank=False, on_delete=models.CASCADE
    )
    data_inicio_setor_lotacao = models.DateField(null=False, blank=False, db_index=True)
    data_fim_setor_lotacao = models.DateFieldPlus(null=True, blank=True)
    hora_atualizacao_siape = models.DateTimeFieldPlus(null=False, blank=False)

    class Meta:
        unique_together = ('servidor', 'data_inicio_setor_lotacao')
        verbose_name = 'Histórico Setor de Lotação do Servidor'
        verbose_name_plural = 'Histórico Setores de Lotação do Servidor'

    def __str__(self):
        return '{} - {} (Exercício::. {}) - de {} até '.format(
            self.servidor.pessoa_fisica.nome,
            self.setor_lotacao.sigla,
            self.setor_exercicio.sigla,
            self.data_inicio_setor_lotacao.strftime('%d/%m/%Y'),
        )
