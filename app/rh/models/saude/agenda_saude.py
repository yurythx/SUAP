from djtools.db import models
from djtools.utils import get_datetime_now


class AgendaAtendimentoHorario(models.ModelPlus):
    acao_saude = models.ForeignKeyPlus('rh.AcaoSaude', verbose_name='Ação de Saúde', on_delete=models.CASCADE, null=True)
    profissional = models.ForeignKeyPlus('rh.Servidor', verbose_name='Profissional', on_delete=models.CASCADE, null=True)
    hora_inicio = models.TimeFieldPlus('Início do Atendimento', null=False, blank=False)
    hora_fim = models.TimeFieldPlus('Fim do Atendimento', null=False, blank=False)
    quantidade_vaga = models.PositiveIntegerField('Quantidade de Vagas', null=False, blank=False, default=0)

    class Meta:
        verbose_name = 'Horário de Atendimento'
        verbose_name_plural = 'Horários de Atendimento'

    def tem_vaga_disponivel(self, dia):
        return self.quantidade_vaga > HorarioAgendado.objects.filter(horario=self, cancelado=False, data_consulta=dia).count()

    def pode_agendar(self, dia):
        return self.tem_vaga_disponivel(dia) and self.acao_saude.em_periodo_inscricao()

    def horario_atendimento(self):
        return 'De {} até {}'.format(self.hora_inicio.strftime('%H:%M'), self.hora_fim.strftime('%H:%M'))

    def esta_agendado_em_algum_horario(self, vinculo):
        return HorarioAgendado.objects.filter(horario__acao_saude=self.acao_saude, solicitante=vinculo, cancelado=False).exists()

    def __str__(self):
        return f'Hora do atendimento: {self.horario_atendimento()} ({self.profissional})'


class HorarioAgendado(models.ModelPlus):
    horario = models.ForeignKeyPlus(AgendaAtendimentoHorario, verbose_name='Horário', on_delete=models.CASCADE)
    data_consulta = models.DateFieldPlus('Data da Consulta', null=True, blank=True)
    solicitante = models.ForeignKeyPlus('comum.Vinculo', null=True, blank=True, related_name='solicitante', on_delete=models.CASCADE)
    retorno = models.BooleanField('É um retorno?', null=False, blank=True, default=False)
    cancelado = models.BooleanField('Cancelado', null=False, blank=True, default=False)
    data_cancelamento = models.DateTimeFieldPlus('Data de Cancelamento', null=True, blank=True)
    data_cadastro = models.DateTimeFieldPlus(auto_now_add=True, null=True)

    class Meta:
        verbose_name = 'Horário Agendado'
        verbose_name_plural = 'Horários Agendados'
        permissions = (('pode_cancelar_agendamento', 'Pode Cancelar Agendamento'),)

    def cancelar_horario(self):
        self.cancelado = True
        self.data_cancelamento = get_datetime_now()
        self.save()


class DataConsultaBloqueada(models.ModelPlus):
    acao_saude = models.ForeignKeyPlus('rh.AcaoSaude', verbose_name='Ação de Saúde', on_delete=models.CASCADE, null=True)
    data_consulta_bloqueada = models.DateFieldPlus('Data da Consulta', null=False)
    motivo_bloqueio = models.CharFieldPlus('Motivo do Bloqueio', max_length=100)
    houve_remarcacao = models.BooleanField('Houve Remarcaçao de Consulta', default=False)

    class Meta:
        verbose_name = 'Data de Consulta Bloqueada'
        verbose_name_plural = 'Datas de Consultas Bloqueadas'

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
