import datetime
import math

from django.db.models.aggregates import Sum
from djtools.db import models
from django.db.models import Q
from edu.models.cadastros_gerais import PERIODO_LETIVO_CHOICES, HorarioCampus, Turno
from edu.models.logs import LogModel
from rh.models import Servidor


class ConfiguracaoAtividadeDocente(LogModel):
    SEARCH_FIELDS = ['ano_letivo_inicio__ano']
    ano_letivo_inicio = models.ForeignKeyPlus('comum.Ano', verbose_name='Ano Letivo', on_delete=models.CASCADE)
    periodo_letivo_inicio = models.PositiveIntegerField(verbose_name='Período Letivo', choices=PERIODO_LETIVO_CHOICES)

    ha_semanal = models.PositiveIntegerField('H/A Semanal')
    ha_minima_semanal = models.PositiveIntegerField('H/A Mínima Semanal')
    percentual_reducao_20h = models.PositiveIntegerField('% redução - 20H')
    percentual_reducao_cd1 = models.PositiveIntegerField('% redução - CD1')
    percentual_reducao_cd2 = models.PositiveIntegerField('% redução - CD2')
    percentual_reducao_cd3 = models.PositiveIntegerField('% redução - CD3')
    percentual_reducao_cd4 = models.PositiveIntegerField('% redução - CD4')
    percentual_reducao_fg1 = models.PositiveIntegerField('% redução - FG1/FCC/FUC1')
    percentual_reducao_fg2 = models.PositiveIntegerField('% redução - FG2')
    percentual_reducao_fg3 = models.PositiveIntegerField('% redução - FG3')
    percentual_reducao_fg4 = models.PositiveIntegerField('% redução - FG4')
    percentual_reducao_fa_reitoria = models.PositiveIntegerField('% redução - FA na Reitoria')
    percentual_reducao_fa_campus = models.PositiveIntegerField('% redução - FA nos Campus')

    portaria_normativa = models.FileFieldPlus(upload_to='edu/configuracao_atividade_docente/', verbose_name='Portaria Normativa')

    class Meta:
        verbose_name = 'Configuração de Atividade Docente'
        verbose_name_plural = 'Configurações de Atividade Docente'
        permissions = (('deferir_configuracaoatividadedocente', 'Pode deferir Configuração de Atividade Docente'),)

    def __str__(self):
        return f'Configuração {self.ano_letivo_inicio}.{self.periodo_letivo_inicio}'

    def replicar(self):
        obj = self
        obj.pk = None
        obj.save()
        return obj

    def get_absolute_url(self):
        return f'/pit_rit/configuracaoatividadedocente/{self.pk}/'

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        from edu.models.professores import Professor

        qs_servidor = (
            Servidor.objects.docentes().exclude(servidorafastamento__data_termino__gte=datetime.date.today()).values_list('pk', flat=True).distinct()
        )
        for professor_id in Professor.objects.filter(vinculo__id_relacionamento__in=qs_servidor).values_list('pk', flat=True).distinct():
            if not PlanoIndividualTrabalho.objects.filter(
                professor_id=professor_id, ano_letivo=self.ano_letivo_inicio, periodo_letivo=self.periodo_letivo_inicio
            ).exists():
                pit = PlanoIndividualTrabalho()
                pit.configuracao = self
                pit.professor_id = professor_id
                pit.ano_letivo = self.ano_letivo_inicio
                pit.periodo_letivo = self.periodo_letivo_inicio
                pit.save()


class TipoAtividadeDocente(LogModel):
    ENSINO = 0
    PESQUISA = 1
    EXTENSAO = 2
    GESTAO = 3
    CARGO_FUNCAO = 4
    CATEGORIA_CHOICES = [[ENSINO, 'Ensino'], [PESQUISA, 'Pesquisa'], [EXTENSAO, 'Extensão'], [GESTAO, 'Gestão'], [CARGO_FUNCAO, 'Cargo/Função']]

    descricao = models.CharFieldPlus('Descrição', unique=True)
    ch_minima_semanal = models.PositiveIntegerField('CH Min. Semanal')
    ch_maxima_semanal = models.PositiveIntegerField('CH Máx. Semanal')
    categoria = models.PositiveIntegerField(choices=CATEGORIA_CHOICES)
    exige_documentacao = models.BooleanField('Exige Documentação', default=False)
    exige_horario = models.BooleanField('Exige Horário', default=True)
    ativo = models.BooleanField('Ativo', default=True)

    class Meta:
        verbose_name = 'Tipo de Atividade Docente'
        verbose_name_plural = 'Tipos de Atividade Docente'


class PlanoIndividualTrabalho(models.ModelPlus):
    SEARCH_FIELDS = ['aluno__pessoa_fisica__nome_registro', 'aluno__pessoa_fisica__nome_social', 'aluno__matricula']

    configuracao = models.ForeignKeyPlus('pit_rit.ConfiguracaoAtividadeDocente')
    professor = models.ForeignKeyPlus('edu.Professor')

    ano_letivo = models.ForeignKeyPlus('comum.Ano', verbose_name='Ano Letivo', on_delete=models.CASCADE)
    periodo_letivo = models.PositiveIntegerField('Período Letivo', db_index=True)

    relatos_ensino = models.TextField(verbose_name='Relatos do Ensino', null=True, blank=True)
    relatos_pesquisa = models.TextField(verbose_name='Relatos da Pesquisa', null=True, blank=True)
    relatos_extensao = models.TextField(verbose_name='Relatos da Extensão', null=True, blank=True)
    relatos_gestao = models.TextField(verbose_name='Relatos da Gestão', null=True, blank=True)

    deferida = models.BooleanField('Publicada', default=None, null=True)

    objects = models.Manager()

    class Meta:
        verbose_name = 'Plano Individual de Trabalho'
        verbose_name_plural = 'Planos Individuais de Trabalho'

    def __str__(self):
        return f'R.I.T. de {self.professor} referente ao período {self.ano_letivo}/{self.periodo_letivo}'

    def get_percentual_preenchimento_relatorio(self):
        percentual = 0
        if self.relatos_ensino and self.relatos_ensino.strip():
            percentual += 25
        if self.relatos_pesquisa and self.relatos_pesquisa.strip():
            percentual += 25
        if self.relatos_extensao and self.relatos_extensao.strip():
            percentual += 25
        if self.relatos_gestao and self.relatos_gestao.strip():
            percentual += 25
        return percentual

    def get_absolute_url(self):
        return f'/edu/professor/{self.professor.pk}/?tab=planoatividades&ano-periodo={self.ano_letivo.ano}.{self.periodo_letivo}'

    def get_vinculos_minicurso(self):
        return self.professor.get_vinculos_minicurso(self.ano_letivo.ano, self.periodo_letivo)

    def get_ch_minicursos(self):
        soma = 0
        for vinculo in self.get_vinculos_minicurso():
            soma += vinculo.get_carga_horaria_semanal_ha()
        return soma

    def get_ch_minicursos_ha(self):
        soma_ch_semanal = 0
        for ch in self.get_vinculos_minicurso():
            soma_ch_semanal += ch.get_carga_horaria_semanal_ha()
        return soma_ch_semanal

    def get_vinculo_diarios(self, fic=None):
        return self.professor.get_vinculo_diarios(self.ano_letivo.ano, self.periodo_letivo, fic, True, False)

    def get_ch_diarios(self, fic=False):
        ch_semanal_diarios = 0
        for professor_diario in self.get_vinculo_diarios(fic):
            ch_diario = professor_diario.get_qtd_creditos_efetiva(self.periodo_letivo)
            professor_diario.ch_qtd_creditos = ch_diario
            ch_semanal_diarios += ch_diario
        return ch_semanal_diarios

    def get_vinculos_diarios_especiais(self):
        return self.professor.get_vinculos_diarios_especiais(self.ano_letivo.ano, self.periodo_letivo)

    def get_ch_semanal_atividades_ensino(self):
        diarios_especiais = self.professor.diarioespecial_set.all()
        atividades_ensino = self.atividadedocente_set.filter(tipo_atividade__categoria=TipoAtividadeDocente.ENSINO)
        ch_semanal_atividades_ensino = (
            atividades_ensino.filter(deferida=True).aggregate(soma_ch_semanal=Sum('ch_aula_efetiva')).get('soma_ch_semanal') or 0
        )

        ch_semanal_diarios_especiais = 0
        for diario_especial in diarios_especiais:
            ch_semanal_diarios_especiais += math.ceil(float(diario_especial.componente.ch_qtd_creditos) / diario_especial.professores.count())

        if ch_semanal_diarios_especiais != 0 and ch_semanal_diarios_especiais >= 6:
            ch_semanal_diarios_especiais = 6

        return ch_semanal_atividades_ensino + ch_semanal_diarios_especiais

    def get_atividades(self, tipo=None):
        qs = self.atividadedocente_set.all()
        if tipo is not None:
            qs = qs.filter(tipo_atividade__categoria=tipo)
        return qs

    def get_ch_semanal_atividades(self, tipo=None):
        qs = self.get_atividades(tipo)
        ch = qs.filter(deferida=True).aggregate(soma_ch_semanal=Sum('ch_aula_efetiva')).get('soma_ch_semanal') or 0
        return ch

    def get_atividades_ensino(self):
        return self.get_atividades(TipoAtividadeDocente.ENSINO)

    def get_atividades_pesquisa(self):
        return self.get_atividades(TipoAtividadeDocente.PESQUISA)

    def get_ch_semanal_atividades_pesquisa(self):
        return self.get_ch_semanal_atividades(TipoAtividadeDocente.PESQUISA)

    def get_atividades_extensao(self):
        return self.get_atividades(TipoAtividadeDocente.EXTENSAO)

    def get_ch_semanal_atividades_extensao(self):
        return self.get_ch_semanal_atividades(TipoAtividadeDocente.EXTENSAO)

    def get_atividades_gestao(self):
        return self.get_atividades(TipoAtividadeDocente.GESTAO)

    def get_ch_semanal_atividades_gestao(self):
        return self.get_ch_semanal_atividades(TipoAtividadeDocente.GESTAO)

    def get_atividades_cargo_funcao(self):
        return self.get_atividades(TipoAtividadeDocente.CARGO_FUNCAO)

    def get_ch_semanal_atividades_cargo_funcao(self):
        return self.get_ch_semanal_atividades(TipoAtividadeDocente.CARGO_FUNCAO)

    def get_atividade_cargo_funcao_semestral(self):
        qs = self.get_atividades_cargo_funcao().filter(periodicidade='Semestral', deferida=True)
        return qs.exists() and qs[0] or None

    def get_ch_semanal_total(self):
        if self.get_atividade_cargo_funcao_semestral():
            return 53

        # Calculando as CH com base no número de professores no diário e diário especial e arredondando para cima.
        ch_semanal_diarios = self.get_ch_diarios(False) * 2
        ch_semanal_diarios_fic = self.get_ch_diarios(True) * 2
        ch_semanal_minicursos = self.get_ch_minicursos() * 2
        ch_semanal_atividades_ensino = self.get_ch_semanal_atividades_ensino()
        ch_semanal_atividades_pesquisa = self.get_ch_semanal_atividades_pesquisa()
        ch_semanal_atividades_extensao = self.get_ch_semanal_atividades_extensao()
        ch_semanal_atividades_gestao = self.get_ch_semanal_atividades_gestao()
        ch_semanal_atividades_cargo_funcao = self.get_ch_semanal_atividades_cargo_funcao()
        ch_total_semanal = (
            ch_semanal_diarios
            + ch_semanal_diarios_fic
            + ch_semanal_minicursos
            + ch_semanal_atividades_ensino
            + ch_semanal_atividades_pesquisa
            + ch_semanal_atividades_extensao
            + ch_semanal_atividades_gestao
            + ch_semanal_atividades_cargo_funcao
        )
        return ch_total_semanal > 53 and 53 or ch_total_semanal


class AtividadeDocente(LogModel):
    pit = models.ForeignKeyPlus('pit_rit.PlanoIndividualTrabalho', on_delete=models.CASCADE, null=True)
    descricao = models.CharFieldPlus('Descrição', max_length=60)
    tipo_atividade = models.ForeignKeyPlus('pit_rit.TipoAtividadeDocente', on_delete=models.CASCADE)
    periodicidade = models.CharFieldPlus(verbose_name='Periodicidade', choices=[[x, x] for x in ['Semestral', 'Eventual']], default='Semestral')
    ch_aula = models.PositiveIntegerField('Carga-Horária', help_text='Caga-horária semanal prevista na normativa')
    ch_aula_efetiva = models.DecimalFieldPlus('Carga-Horária', help_text='C.H. semanal efetiva', null=True, blank=True)
    qtd_dias = models.IntegerField('Quantidade de Dias', null=True, blank=True)
    comprovante = models.FileFieldPlus(
        verbose_name='Comprovante',
        upload_to='edu/atividades_docente/',
        filetypes=['pdf', 'jpeg', 'jpg', 'png'],
        check_mimetype=False,
        null=True,
        blank=True,
        help_text='Arquivo nos formatos PDF, JPG/JPEG ou PNG',
    )
    sala = models.ForeignKeyPlus('comum.Sala', null=True, blank=True)
    deferida = models.BooleanField('Deferida', default=None, null=True)

    class Meta:
        verbose_name = 'Atividade Docente'
        verbose_name_plural = 'Atividades Docentes'
        permissions = (('deferir_atividadedocente', 'Pode deferir Atividade Docente'),)

    def get_horario_aulas(self):
        output = []
        turnos_ids = self.horarioaulaatividadedocente_set.all().values_list('horario_aula__turno', flat=True).distinct()
        for turno in Turno.objects.filter(id__in=turnos_ids):
            dias_semana = (
                self.horarioaulaatividadedocente_set.filter(horario_aula__turno=turno)
                .order_by('dia_semana')
                .values_list('dia_semana', flat=True)
                .distinct()
            )
            for dia_semana in dias_semana:
                if output:
                    output.append(' / ')
                numeros = []
                for numero in (
                    self.horarioaulaatividadedocente_set.filter(horario_aula__turno=turno, dia_semana=dia_semana)
                    .values_list('horario_aula__numero', flat=True)
                    .distinct()
                ):
                    if numero not in numeros:
                        numeros.append(str(numero))
                numeros.sort()
                output.append('{}{}{}'.format(dia_semana + 1, turno.descricao[0], ''.join(numeros)))
        return ''.join(output)

    def is_aguardando_deferimento(self):
        return not self.deferida and (not self.tipo_atividade.exige_horario or self.get_horario_aulas())

    def get_horarios_aula_por_turno(self):
        from edu.models.cursos import CursoCampus

        if self.pit.professor.vinculo.relacionamento.setor_lotacao:
            uo_lotacao = self.pit.professor.vinculo.relacionamento.setor_lotacao.uo.equivalente or None
        else:
            uo_lotacao = self.pit.professor.vinculo.relacionamento.setor.uo

        if not uo_lotacao:
            return Turno.objects.none()

        qs_horario_campus = HorarioCampus.objects.filter(uo__pk=uo_lotacao.pk, eh_padrao=True)

        if qs_horario_campus.exists():
            horario_campus = qs_horario_campus[0]
            turnos_ids = horario_campus.horarioaula_set.values_list('turno_id', flat=True).distinct()
            dias_semana = HorarioAulaAtividadeDocente.DIA_SEMANA_CHOICES
            turnos = Turno.objects.filter(id__in=turnos_ids).order_by('-id')
            for turno in turnos:
                turno.horarios_aula = []
                turno.dias_semana = dias_semana
                for horario_aula in turno.horarioaula_set.filter(horario_campus=horario_campus):
                    horario_aula.dias_semana = []
                    for dia_semana in dias_semana:
                        numero = dia_semana[0]
                        nome = dia_semana[1]
                        qs = self.horarioaulaatividadedocente_set.filter(dia_semana=dia_semana[0], horario_aula=horario_aula)

                        if self.pit.periodo_letivo == 1:
                            desabilitado = (
                                horario_aula.horarioauladiario_set.filter(
                                    dia_semana=dia_semana[0],
                                    diario__ano_letivo=self.pit.ano_letivo,
                                    diario__periodo_letivo=self.pit.periodo_letivo,
                                    diario__professordiario__professor=self.pit.professor,
                                    diario__professordiario__ativo=True,
                                ).exists()
                                or horario_aula.horarioauladiario_set.filter(
                                    dia_semana=dia_semana[0],
                                    diario__ano_letivo=self.pit.ano_letivo,
                                    diario__professordiario__professor=self.pit.professor,
                                    diario__turma__curso_campus__periodicidade=CursoCampus.PERIODICIDADE_ANUAL,
                                    diario__professordiario__ativo=True,
                                )
                                .exclude(diario__segundo_semestre=True)
                                .exists()
                                or horario_aula.horarioauladiarioespecial_set.filter(
                                    dia_semana=dia_semana[0],
                                    diario_especial__ano_letivo=self.pit.ano_letivo,
                                    diario_especial__periodo_letivo=self.pit.periodo_letivo,
                                    diario_especial__professores=self.pit.professor,
                                ).exists()
                                or horario_aula.horarioaulaatividadedocente_set.exclude(atividade_docente__pk=self.pk)
                                .filter(
                                    dia_semana=dia_semana[0],
                                    atividade_docente__pit__ano_letivo=self.pit.ano_letivo,
                                    atividade_docente__pit__periodo_letivo=self.pit.periodo_letivo,
                                    atividade_docente__pit__professor=self.pit.professor,
                                )
                                .exists()
                            )
                        else:
                            desabilitado = (
                                horario_aula.horarioauladiario_set.filter(
                                    dia_semana=dia_semana[0],
                                    diario__ano_letivo=self.pit.ano_letivo,
                                    diario__periodo_letivo=self.pit.periodo_letivo,
                                    diario__professordiario__professor=self.pit.professor,
                                    diario__professordiario__ativo=True,
                                ).exists()
                                or horario_aula.horarioauladiario_set.filter(
                                    dia_semana=dia_semana[0],
                                    diario__ano_letivo=self.pit.ano_letivo,
                                    diario__professordiario__professor=self.pit.professor,
                                    diario__turma__curso_campus__periodicidade=CursoCampus.PERIODICIDADE_ANUAL,
                                    diario__professordiario__ativo=True,
                                )
                                .exclude(diario__segundo_semestre=False)
                                .exists()
                                or horario_aula.horarioauladiarioespecial_set.filter(
                                    dia_semana=dia_semana[0],
                                    diario_especial__ano_letivo=self.pit.ano_letivo,
                                    diario_especial__periodo_letivo=self.pit.periodo_letivo,
                                    diario_especial__professores=self.pit.professor,
                                ).exists()
                                or horario_aula.horarioaulaatividadedocente_set.exclude(atividade_docente__pk=self.pk)
                                .filter(
                                    dia_semana=dia_semana[0],
                                    atividade_docente__pit__ano_letivo=self.pit.ano_letivo,
                                    atividade_docente__pit__periodo_letivo=self.pit.periodo_letivo,
                                    atividade_docente__pit__professor=self.pit.professor,
                                )
                                .exists()
                            )

                        marcado = qs.count()
                        if qs.exists():
                            qs = qs[0]
                        else:
                            qs = None
                        horario_aula.dias_semana.append({'numero': numero, 'nome': nome, 'marcado': marcado, 'desabilitado': desabilitado})
                    turno.horarios_aula.append(horario_aula)
            return turnos
        else:
            return Turno.objects.all()

    @staticmethod
    def get_pendentes(user):
        if not user.has_perm('comum.is_diretor_academico'):
            return AtividadeDocente.objects.none()
        diretor_academico = user.get_relacionamento()
        pessoas_subordinadas = Servidor.objects.filter(
            Q(setor_exercicio=diretor_academico.setor_exercicio) | Q(setor_lotacao=diretor_academico.setor_lotacao)
        ).values_list('pessoa_fisica_id', flat=True)

        qs = AtividadeDocente.objects.filter(
            pit__professor__vinculo__ativo=True, deferida__isnull=True, pit__professor__vinculo__pessoa_id__in=pessoas_subordinadas
        )
        qs = qs.filter(Q(pit__ano_letivo__ano__gt=2017) | Q(pit__ano_letivo__ano=2017, pit__periodo_letivo=2))
        return qs.distinct()

    def save(self, *args, **kwargs):
        if self.periodicidade == 'Eventual':
            self.ch_aula_efetiva = self.ch_aula * self.qtd_dias / 100.0
        else:
            self.ch_aula_efetiva = self.ch_aula
        super().save(*args, **kwargs)


class HorarioAulaAtividadeDocente(LogModel):
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

    atividade_docente = models.ForeignKeyPlus('pit_rit.AtividadeDocente', on_delete=models.CASCADE)
    dia_semana = models.PositiveIntegerField(choices=DIA_SEMANA_CHOICES)
    horario_aula = models.ForeignKeyPlus('edu.HorarioAula', on_delete=models.CASCADE)

    class Meta:
        verbose_name = 'Horário de Aula na Atividade Docente'
        verbose_name_plural = 'Horários das Aulas na Atividade Docente'

    def __str__(self):
        return str(self.pk)

    def get_atividade_docente(self):
        return self.atividade_docente

    @staticmethod
    def get_dias_semana_seg_a_sex():
        dias_semana = []
        for dia in HorarioAulaAtividadeDocente.DIA_SEMANA_CHOICES:
            if dia[0] < 6:
                dias_semana.append(dia)
        return dias_semana
