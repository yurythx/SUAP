from djtools.db import models
from edu.models.cadastros_gerais import PERIODO_LETIVO_CHOICES


class MotivoAfastamentoSalaAula(models.ModelPlus):
    descricao = models.CharFieldPlus('Descrição')

    class Meta:
        verbose_name = 'Motivo de Afastamento de Sala de Aula'
        verbose_name_plural = 'Motivos de Afastamento de Sala de Aula'

    def __str__(self):
        return self.descricao


class AfastamentoSalaAula(models.ModelPlus):
    SEM_SUBSTITUICAO = 1
    PROFESSOR_SUBSTITUTO = 2
    PROFESSOR_VISITANTE = 3
    PROFESSOR_TEMPORARIO = 4

    TIPO_SUBSTITUICAO_CHOICES = [
        [SEM_SUBSTITUICAO, 'Sem substituição'],
        [PROFESSOR_SUBSTITUTO, 'Professor Substituto'],
        [PROFESSOR_VISITANTE, 'Professor Visitante'],
        [PROFESSOR_TEMPORARIO, 'Professor Temporário'],
    ]

    professor = models.ForeignKeyPlus('edu.professor', verbose_name='Professor', on_delete=models.CASCADE)
    motivo = models.ForeignKeyPlus(MotivoAfastamentoSalaAula, verbose_name='Motivo', on_delete=models.CASCADE)
    ano_inicio = models.ForeignKeyPlus('comum.ano', verbose_name='Ano do Início', on_delete=models.CASCADE, related_name='rn1')
    periodo_inicio = models.IntegerField('Período do Início', choices=PERIODO_LETIVO_CHOICES)
    ano_termino = models.ForeignKeyPlus(
        'comum.ano', verbose_name='Ano do Término', on_delete=models.CASCADE, related_name='rn2', null=True, blank=True
    )
    periodo_termino = models.IntegerField('Período do Término', null=True, blank=True, choices=[['', ''], *PERIODO_LETIVO_CHOICES])
    tipo_substituicao = models.IntegerField('Tipo de Substituição', choices=TIPO_SUBSTITUICAO_CHOICES)
    percentual = models.IntegerField('Percentual (%)', default=100)

    class Meta:
        verbose_name = 'Afastamento de Sala de Aula'
        verbose_name_plural = 'Afastamentos de Sala de Aula'

    def __str__(self):
        return f'{self.professor} [{self.ano_inicio}/{self.periodo_inicio}]'
