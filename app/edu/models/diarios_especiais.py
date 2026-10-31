import math

from djtools.db import models
from edu.managers import DiarioEspecialManager
from edu.models.cadastros_gerais import PERIODO_LETIVO_CHOICES, Modalidade, Turno
from edu.models.logs import LogModel


class ConfiguracaoCreditosEspeciais(LogModel):
    descricao = models.CharFieldPlus('Descrição', width=500)
    quantidade_maxima_creditos_especiais = models.PositiveIntegerField('Quantidade Máxima de Créditos Especiais')
    ativo = models.BooleanField('Ativo', default=True)

    class Meta:
        verbose_name = 'Configuração de Créditos Especiais'
        verbose_name_plural = 'Configurações de Créditos Especiais'

    def get_absolute_url(self):
        return f'/edu/configuracaocreditosespeciais/{self.pk:d}/'

    def tem_alunos_vinculados(self):
        from edu.models.historico import MatriculaPeriodo

        return MatriculaPeriodo.objects.filter(creditoespecial__item_configuracao_creditos_especiais__configuracao=self).exists()

    def pode_ser_excluido(self):
        return not self.matriz_set.exists() and not self.tem_alunos_vinculados()


class ItemConfiguracaoCreditosEspeciais(LogModel):
    configuracao = models.ForeignKeyPlus('edu.ConfiguracaoCreditosEspeciais', verbose_name='Configuração de Créditos Especiais')
    atividade_academica = models.CharFieldPlus('Atividade Acadêmica')
    equivalencia_creditos = models.PositiveIntegerField('Quantidade de Créditos')

    class Meta:
        verbose_name = 'Item de Configuração de Créditos Especiais'
        verbose_name_plural = 'Itens de Configuração de Créditos Especiais'
        ordering = ('id',)

    def __str__(self):
        return self.atividade_academica


class CreditoEspecial(LogModel):
    matricula_periodo = models.ForeignKeyPlus('edu.MatriculaPeriodo', verbose_name='Matrícula Período', on_delete=models.CASCADE)
    item_configuracao_creditos_especiais = models.ForeignKeyPlus(
        'edu.ItemConfiguracaoCreditosEspeciais', on_delete=models.CASCADE, verbose_name='Item de Configuração de Créditos Especiais'
    )

    class Meta:
        verbose_name = 'Crédito Especial'
        verbose_name_plural = 'Créditos Especiais'

    def __str__(self):
        return f'Crédito Especial ({self.pk})'

    def get_ch_equivalente(self):
        if (
            self.matricula_periodo.aluno.curso_campus.modalidade.pk != Modalidade.MESTRADO
            or self.matricula_periodo.aluno.curso_campus.modalidade.pk != Modalidade.DOUTORADO
        ):
            return 20 * self.item_configuracao_creditos_especiais.equivalencia_creditos
        else:
            return 15 * self.item_configuracao_creditos_especiais.equivalencia_creditos


class DiarioEspecial(LogModel):
    # Manager
    objects = models.Manager()
    locals = DiarioEspecialManager()
    # Fields
    ano_letivo = models.ForeignKeyPlus('comum.Ano', verbose_name='Ano Letivo', null=False, blank=False, on_delete=models.CASCADE)
    periodo_letivo = models.PositiveIntegerField('Período Letivo', choices=PERIODO_LETIVO_CHOICES, null=False, blank=False)
    componente = models.ForeignKeyPlus('edu.Componente')
    is_centro_aprendizagem = models.BooleanField(verbose_name='Centro de Aprendizagem?', default=False)
    descricao = models.CharFieldPlus(verbose_name='Descrição', null=True, blank=True)
    professores = models.ManyToManyFieldPlus('edu.Professor')
    participantes = models.ManyToManyFieldPlus('edu.Aluno')
    sala = models.ForeignKeyPlus('comum.Sala', null=True, blank=True)
    horario_campus = models.ForeignKeyPlus('edu.HorarioCampus', verbose_name='Horário do Campus', on_delete=models.CASCADE)
    diretoria = models.ForeignKeyPlus('edu.Diretoria', on_delete=models.CASCADE)

    # data_inicio = models.DateFieldPlus(u'Data de início', null=True)
    # data_fim = models.DateFieldPlus(u'Data de fim', null=True)

    def get_horario_aulas(self):
        output = []
        turnos_ids = self.horarioauladiarioespecial_set.all().values_list('horario_aula__turno', flat=True).distinct()
        for turno in Turno.objects.filter(id__in=turnos_ids):
            dias_semana = (
                self.horarioauladiarioespecial_set.filter(horario_aula__turno=turno)
                .order_by('dia_semana')
                .values_list('dia_semana', flat=True)
                .distinct()
            )
            for dia_semana in dias_semana:
                if output:
                    output.append(' / ')
                numeros = []
                for numero in (
                    self.horarioauladiarioespecial_set.filter(horario_aula__turno=turno, dia_semana=dia_semana)
                    .values_list('horario_aula__numero', flat=True)
                    .distinct()
                ):
                    if numero not in numeros:
                        numeros.append(str(numero))
                numeros.sort()
                output.append('{}{}{}'.format(dia_semana + 1, turno.descricao[0], ''.join(numeros)))
        return ''.join(output)

    def get_horarios_aula_por_turno(self):
        turnos_ids = self.horario_campus.horarioaula_set.values_list('turno_id', flat=True).distinct()
        dias_semana = HorarioAulaDiarioEspecial.DIA_SEMANA_CHOICES
        turnos = Turno.objects.filter(id__in=turnos_ids).order_by('-id')
        for turno in turnos:
            turno.horarios_aula = []
            turno.dias_semana = dias_semana
            for horario_aula in turno.horarioaula_set.filter(horario_campus=self.horario_campus):
                horario_aula.dias_semana = []
                for dia_semana in dias_semana:
                    numero = dia_semana[0]
                    nome = dia_semana[1]
                    qs = self.horarioauladiarioespecial_set.filter(dia_semana=dia_semana[0], horario_aula=horario_aula)
                    marcado = qs.count()
                    if qs.exists():
                        qs = qs[0]
                    else:
                        qs = None
                    horario_aula.dias_semana.append({'numero': numero, 'nome': nome, 'marcado': marcado, 'horario_aula_diario': qs})
                turno.horarios_aula.append(horario_aula)
        return turnos

    def get_absolute_url(self):
        return f'/edu/diarioespecial/{self.pk:d}/'

    def __str__(self):
        if self.id:
            return self.componente.descricao
        else:
            return str(self.componente)

    def get_nomes_professores(self, excluir_tutores=False):
        lista_nomes = []
        for professor in self.professores.all():
            lista_nomes.append(format(professor.vinculo.pessoa.nome_usual))

        return ', '.join(lista_nomes)

    def get_carga_horaria_semanal_ha(self):
        return math.ceil(float(self.componente.ch_qtd_creditos) / self.professores.count())

    def get_descricao(self):
        return self.descricao or str(self.componente)

    class Meta:
        verbose_name = 'Atividade Específica'
        verbose_name_plural = 'Atividades Específicas'
        permissions = (('cadastrar_encontro_diarioespecial', 'Pode cadastrar Encontro na Atividade Específica'),)


class HorarioAulaDiarioEspecial(LogModel):
    DIA_SEMANA_SEG = 1
    DIA_SEMANA_TER = 2
    DIA_SEMANA_QUA = 3
    DIA_SEMANA_QUI = 4
    DIA_SEMANA_SEX = 5
    DIA_SEMANA_SAB = 6
    DIA_SEMANA_DOM = 7
    DIA_SEMANA_CHOICES = [
        [DIA_SEMANA_SEG, 'Segunda'],
        [DIA_SEMANA_TER, 'Terça'],
        [DIA_SEMANA_QUA, 'Quarta'],
        [DIA_SEMANA_QUI, 'Quinta'],
        [DIA_SEMANA_SEX, 'Sexta'],
        [DIA_SEMANA_SAB, 'Sábado'],
        [DIA_SEMANA_DOM, 'Domingo'],
    ]

    diario_especial = models.ForeignKeyPlus('edu.DiarioEspecial', on_delete=models.CASCADE)
    dia_semana = models.PositiveIntegerField(choices=DIA_SEMANA_CHOICES)
    horario_aula = models.ForeignKeyPlus('edu.HorarioAula', on_delete=models.CASCADE)

    class Meta:
        verbose_name = 'Horário de Aula na Atividade Espec.'
        verbose_name_plural = 'Horários das Aulas na Atividade Espec.'

    def __str__(self):
        return str(self.pk)

    def get_diario_especial(self):
        return self.diario_especial

    @staticmethod
    def get_dias_semana_seg_a_sex():
        dias_semana = []
        for dia in HorarioAulaDiarioEspecial.DIA_SEMANA_CHOICES:
            if dia[0] < 6:
                dias_semana.append(dia)
        return dias_semana

    def get_horario_formatado(self):
        return f'{(self.dia_semana + 1)}{self.horario_aula.turno.descricao[0]}{self.horario_aula.numero}'


class Encontro(LogModel):
    data = models.DateFieldPlus('Data de Realização')
    conteudo = models.TextField(verbose_name='Conteúdo')
    participantes = models.ManyToManyFieldPlus('edu.Aluno')
    diario_especial = models.ForeignKeyPlus('edu.DiarioEspecial', on_delete=models.CASCADE)

    def __str__(self):
        return str(self.pk)

    class Meta:
        verbose_name = 'Encontro - Atividade Específica'
        verbose_name_plural = 'Encontros - Atividade Pedagógica Específica'
        ordering = ('data',)
