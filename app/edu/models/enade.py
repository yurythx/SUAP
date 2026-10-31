import datetime

from djtools.db import models, transaction
from djtools.templatetags.filters import format_
from djtools.utils import running_tests
from edu.models.cursos import CursoCampus
from edu.models.logs import LogModel
from edu.managers import RegistroConvocacaoENADEManager


class ConvocacaoENADE(LogModel):
    AVALIACAO_TEORICA = '1'
    AVALIACAO_PRATICA = '2'
    TIPO_CONVOCACAO_CHOICES = [
        [AVALIACAO_TEORICA, 'Avaliação teórica'],
        [AVALIACAO_PRATICA, 'Avaliação prática'],
    ]

    tipo_convocacao = models.CharFieldPlus(
        verbose_name='Tipo de convocação', null=False, blank=False, choices=TIPO_CONVOCACAO_CHOICES, default=AVALIACAO_TEORICA
    )
    ano_letivo = models.ForeignKeyPlus('comum.Ano', verbose_name='Ano letivo', null=True, on_delete=models.CASCADE)
    data_inscricao_ingressantes = models.DateFieldPlus(
        'Data limite para inscrição de ingressantes', null=True, blank=True, help_text='Data limite para atualização da lista de ingressantes.'
    )
    data_inscricao = models.DateFieldPlus(
        'Data limite para inscrição de concluintes', null=True, blank=True, help_text='Data limite para atualização da lista de concluintes.'
    )
    data_inicio_inscricao = models.DateFieldPlus(
        'Data de início para inscrição de concluintes',
        null=True,
        blank=True,
        help_text='Quando informada, essa data será utilizada para verificar se o aluno que colou grau no ano seguinte à edição do ENADE deverá realizar novamente o exame como concluinte.',
    )

    situacoes_convocadas = models.ManyToManyFieldPlus('edu.SituacaoMatricula', verbose_name='Situações convocadas', blank=False)
    modalidades_convocadas = models.ManyToManyFieldPlus('edu.Modalidade', verbose_name='Modalidades convocadas', blank=False)
    areas_cursos_formacao_superior = models.ManyToManyFieldPlus(
        'edu.AreaCursoFormacaoSuperior', verbose_name='Áreas de cursos de formação superior', blank=False
    )
    cursos = models.ManyToManyFieldPlus('edu.CursoCampus')
    encerrado = models.BooleanField('Encerrado?', default=False)
    descricao = models.CharFieldPlus(verbose_name='Descrição', null=True, blank=True, max_length=255)
    edital = models.FileFieldPlus(
        'Edital',
        upload_to='edu/convocacao_enade_edital/',
        null=True,
        blank=True,
        check_mimetype=False,
        help_text='Arquivo em PDF referente ao edital de convocação do ENADE.',
        filetypes=['pdf'],
    )

    portaria = models.FileFieldPlus(
        'Portaria',
        upload_to='edu/convocacao_enade_edital/',
        null=True,
        blank=True,
        check_mimetype=False,
        help_text='Arquivo em PDF referente à portaria de convocação do ENADE.',
        filetypes=['pdf'],
    )

    # Atributos abaixo não devem ser utilizados. Mantidos apenas para preservar dados legados.
    data_prova = models.DateFieldPlus('Data de realização da prova', null=True, blank=True)
    percentual_minimo_ingressantes = models.PositiveIntegerField('Percentual mínimo (%) para ingressantes', null=True)
    percentual_maximo_ingressantes = models.PositiveIntegerField('Percentual máximo (%) para ingressantes', null=True)
    percentual_minimo_concluintes = models.PositiveIntegerField('Percentual mínimo (%) para concluintes', null=True)
    percentual_maximo_concluintes = models.PositiveIntegerField('Percentual máximo (%) para concluintes', null=True)

    class Meta:
        verbose_name = 'Convocação do ENADE'
        verbose_name_plural = 'Convocações do ENADE'

    def __str__(self):
        return f'Convocação {self.ano_letivo}: {format_(self.descricao)} ({self.get_tipo_convocacao_display()})'

    def save(self, *args, **kwargs):
        return super().save(*args, **kwargs)

    def get_absolute_url(self):
        return f'/edu/convocacao_enade/{self.pk}/'

    def get_pk_cursos_nao_convocados(self):
        return (
            CursoCampus.objects.filter(exige_enade=True, ativo=True)
            .exclude(id__in=self.cursos.values_list('pk', flat=True))
            .values_list('id', flat=True)
            .distinct()
        )

    @staticmethod
    def get_ano_ultima_avaliacao_teorica():
        convocacao = (
            ConvocacaoENADE.objects.filter(tipo_convocacao=ConvocacaoENADE.AVALIACAO_TEORICA)
            .select_related('ano_letivo')
            .only('ano_letivo__ano')
            .order_by('-ano_letivo__ano')
            .first()
        )
        return convocacao.ano_letivo.ano if convocacao else None

    def is_avaliacao_teorica(self):
        return self.tipo_convocacao == ConvocacaoENADE.AVALIACAO_TEORICA

    def is_possivel_concluinte(self, aluno):
        if not self.is_avaliacao_teorica() or aluno.curso_campus is None:
            return False

        if PossivelIntegralizado.objects.filter(convocacao_enade_id=self.id, aluno_id=aluno.id).exists():
            return False

        periodos_pendentes = aluno.matriz.qtd_periodos_letivos - aluno.periodo_atual
        if periodos_pendentes == 0:
            return True

        if periodos_pendentes > 0:
            mp = aluno.get_ultima_matricula_periodo()
            calendario = mp and mp.get_calendario_academico()
            data_fechamento_periodo_atual = calendario and calendario.data_fechamento_periodo
            if data_fechamento_periodo_atual:
                previsao_conclusao = None
                if aluno.curso_campus.periodicidade == CursoCampus.PERIODICIDADE_SEMESTRAL:
                    previsao_conclusao = data_fechamento_periodo_atual + datetime.timedelta(days=(365 * periodos_pendentes) // 2)
                elif aluno.curso_campus.periodicidade == CursoCampus.PERIODICIDADE_ANUAL:
                    previsao_conclusao = data_fechamento_periodo_atual + datetime.timedelta(days=365 * periodos_pendentes)
                if previsao_conclusao:
                    data_limite = (
                        self.modalidadeconvocacaoenade_set.filter(modalidade_id=aluno.curso_campus.modalidade_id).first().data_limite_conclusao
                    )
                    return previsao_conclusao <= data_limite
        return False

    def is_possivel_integralizado(self, aluno):
        if not self.is_avaliacao_teorica() or aluno.curso_campus is None:
            return False
        if PossivelConcluinte.objects.filter(convocacao_enade_id=self.id, aluno_id=aluno.id).exists():
            return False

        configuracao = self.modalidadeconvocacaoenade_set.filter(modalidade_id=aluno.curso_campus.modalidade_id).first()
        data_limite = configuracao.data_limite_integralizacao_concluinte
        if data_limite:
            matricula_diario = aluno.get_ultima_matricula_periodo().matriculadiario_set.all().first()
            if (
                matricula_diario
                and matricula_diario.diario
                and matricula_diario.diario.calendario_academico
                and matricula_diario.diario.calendario_academico.data_fim
                and matricula_diario.diario.calendario_academico.data_fim < data_limite
            ):
                return aluno.get_percentual_carga_horaria_cumprida(previsao=True) >= configuracao.percentual_minimo_concluintes

        return False

    def pode_processar_lista_convocados(self, user):
        if not user.has_perm('edu.add_convocacaoenade'):
            return False
        hoje = datetime.date.today()
        if self.is_avaliacao_teorica():
            result = (
                not self.modalidadeconvocacaoenade_set.exclude(percentual_minimo_ingressantes__isnull=False)
                .exclude(percentual_maximo_ingressantes__isnull=False)
                .exclude(percentual_minimo_concluintes__isnull=False)
                .exclude(percentual_maximo_concluintes__isnull=False)
                .exists()
            )
        else:
            result = self.periodoconvocacaoregencia_set.filter(data_inicio__lte=hoje, data_fim__gte=hoje).exists()

        if running_tests():
            return result

        return result and self.pode_editar_criterios(user)

    def pode_editar_criterios(self, user):
        if not user.has_perm('edu.add_convocacaoenade'):
            return False
        if self.data_inscricao or self.data_inscricao_ingressantes:
            hoje = datetime.date.today()
            return any(dt_limite >= hoje for dt_limite in [self.data_inscricao, self.data_inscricao_ingressantes] if dt_limite is not None)
        return True


class ModalidadeConvocacaoENADE(LogModel):
    convocacao_enade = models.ForeignKeyPlus('edu.ConvocacaoENADE', verbose_name='Convocação ENADE', null=False, blank=False)
    modalidade = models.ForeignKeyPlus('edu.Modalidade', verbose_name='Modalidade', null=False, blank=False)

    # Ingressantes
    percentual_minimo_ingressantes = models.PositiveIntegerField('Percentual mínimo (%) para ingressantes', null=True)
    percentual_maximo_ingressantes = models.PositiveIntegerField('Percentual máximo (%) para ingressantes', null=True)

    # Concluintes
    percentual_minimo_concluintes = models.PositiveIntegerField('Percentual mínimo (%) para concluintes', null=True)
    percentual_maximo_concluintes = models.PositiveIntegerField('Percentual máximo (%) para concluintes', null=True)
    data_limite_conclusao = models.DateFieldPlus(
        'Data limite para conclusão de curso',
        null=True,
        blank=False,
        help_text='Data limite para conclusão de possíveis concluintes. Somente para convocações de avaliação teórica.',
    )
    data_limite_integralizacao_concluinte = models.DateFieldPlus(
        'Data limite para integralização de concluinte',
        null=True,
        blank=False,
        help_text='Data limite para o aluno atingir percentual requerido para convocação como concluinte. Somente para convocações de avaliação teórica.',
    )
    data_prova = models.DateFieldPlus('Data de realização da prova', null=True, blank=True)

    class Meta:
        verbose_name = 'Modalidade da convocação ENADE'
        verbose_name_plural = 'Modalidades das convocações ENADE'

    def get_cursos(self):
        return self.convocacao_enade.cursos.filter(modalidade_id=self.modalidade_id)

    def get_convocados(self, periodo=None):
        result = []
        for curso in self.get_cursos():
            # Inicia a base da queryset
            base_queryset = self.convocacao_enade.registroconvocacaoenade_set.filter(aluno__curso_campus_id=curso.id)

            if self.convocacao_enade.is_avaliacao_teorica():
                total_ingressantes = base_queryset.filter(tipo_convocacao=RegistroConvocacaoENADE.TIPO_CONVOCACAO_INGRESSANTE).count()
                total_concluintes = base_queryset.filter(
                    tipo_convocacao=RegistroConvocacaoENADE.TIPO_CONVOCACAO_CONCLUINTE, possivel_concluinte=False, possivel_integralizado=False
                ).count()
                total_possiveis_concluintes = base_queryset.filter(
                    tipo_convocacao=RegistroConvocacaoENADE.TIPO_CONVOCACAO_CONCLUINTE, possivel_concluinte=True
                ).count()
                total_possiveis_integralizados = base_queryset.filter(
                    tipo_convocacao=RegistroConvocacaoENADE.TIPO_CONVOCACAO_CONCLUINTE, possivel_integralizado=True
                ).count()
                total_concluintes_ap = 0
            else:
                total_ingressantes = 0
                total_concluintes = 0
                total_possiveis_concluintes = 0
                total_possiveis_integralizados = 0
                total_concluintes_ap = base_queryset.filter(
                    periodo_convocacao_regencia=periodo, tipo_convocacao=RegistroConvocacaoENADE.TIPO_CONVOCACAO_CONCLUINTE_AP
                ).count()

            total_alunos = (
                total_ingressantes + total_concluintes + total_possiveis_concluintes + total_possiveis_integralizados + total_concluintes_ap
            )
            result.append(
                {
                    'curso': curso,
                    'total_ingressantes': total_ingressantes,
                    'total_concluintes': total_concluintes,
                    'total_possiveis_concluintes': total_possiveis_concluintes,
                    'total_possiveis_integralizados': total_possiveis_integralizados,
                    'total_concluintes_ap': total_concluintes_ap,
                    'total_alunos': total_alunos,
                }
            )
        return result

    def get_possiveis_concluintes(self):
        result = []
        if self.convocacao_enade.is_avaliacao_teorica():
            for curso in self.get_cursos():
                qs = self.convocacao_enade.possivelconcluinte_set.filter(aluno__curso_campus_id=curso.id)
                total_convocados = qs.filter(convocado=True).count()
                total_nao_convocados = qs.filter(convocado=False).count()
                total_alunos = total_convocados + total_nao_convocados
                result.append(
                    {'curso': curso, 'total_convocados': total_convocados, 'total_nao_convocados': total_nao_convocados, 'total_alunos': total_alunos}
                )
        return result

    def get_possiveis_integralizados(self):
        result = []
        if self.convocacao_enade.is_avaliacao_teorica():
            for curso in self.get_cursos():
                qs = self.convocacao_enade.possivelintegralizado_set.filter(aluno__curso_campus_id=curso.id)
                total_convocados = qs.filter(convocado=True).count()
                total_nao_convocados = qs.filter(convocado=False).count()
                total_alunos = total_convocados + total_nao_convocados
                result.append(
                    {'curso': curso, 'total_convocados': total_convocados, 'total_nao_convocados': total_nao_convocados, 'total_alunos': total_alunos}
                )
        return result


class RegistroConvocacaoENADE(LogModel):
    SITUACAO_PRESENTE = 1
    SITUACAO_DISPENSADO = 2
    SITUACAO_AUSENTE = 3
    SITUACAO_CHOICES = ((SITUACAO_PRESENTE, 'Regular'), (SITUACAO_DISPENSADO, 'Dispensado'), (SITUACAO_AUSENTE, 'Irregular'))

    TIPO_CONVOCACAO_INGRESSANTE = 1
    TIPO_CONVOCACAO_CONCLUINTE = 2
    TIPO_CONVOCACAO_CONCLUINTE_AP = 3
    TIPO_CONVOCACAO_CHOICES = (
        (TIPO_CONVOCACAO_INGRESSANTE, 'Ingressante'),
        (TIPO_CONVOCACAO_CONCLUINTE, 'Concluinte'),
        (TIPO_CONVOCACAO_CONCLUINTE_AP, 'Concluinte AP'),
    )

    aluno = models.ForeignKeyPlus('edu.Aluno')
    convocacao_enade = models.ForeignKeyPlus('edu.ConvocacaoENADE', null=True)
    situacao = models.PositiveIntegerField('Situação', null=True, choices=SITUACAO_CHOICES)
    percentual_ch_cumprida = models.DecimalFieldPlus('CH cumprida', null=True)
    justificativa_dispensa = models.ForeignKeyPlus('edu.JustificativaDispensaENADE', null=True, blank=True, verbose_name='Justificativa de Dispensa')
    tipo_convocacao = models.PositiveIntegerField('Tipo da Convocação', null=True, choices=TIPO_CONVOCACAO_CHOICES)
    possivel_concluinte = models.BooleanField('É possível concluinte', default=False)
    possivel_integralizado = models.BooleanField('É possível integralizado', default=False)
    periodo_convocacao_regencia = models.ForeignKeyPlus('edu.PeriodoConvocacaoRegencia', null=True)
    estagio_docente = models.ForeignKeyPlus('edu.EstagioDocente', null=True)

    objects = RegistroConvocacaoENADEManager()

    class Meta:
        ordering = ('aluno__curso_campus', 'aluno__pessoa_fisica__nome')

    def remover_situacao(self):
        self.situacao = None
        self.justificativa_dispensa = None
        self.save()

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self.aluno.atualizar_situacao('Lançamento do ENADE')

    def delete(self, *args, **kwargs):
        super().delete(*args, **kwargs)
        self.aluno.atualizar_situacao('Exclusão de Lançamento do ENADE')

    def get_situacao_para_diploma_digital(self):
        ID_REGISTRO_INGRESSANTE_PARTICIPANTE = 5
        MOTIVOS_DISPENSA_RAP = [
            'Estudante não habilitado ao Enade em razão do calendário do ciclo avaliativo',
            'Estudante não habilitado ao Enade em razão da natureza do projeto pedagógico do curso',
        ]

        if self.situacao is None:
            raise Exception('Aluno possui registro ENADE sem situação informada.')

        if self.situacao == RegistroConvocacaoENADE.SITUACAO_DISPENSADO and self.justificativa_dispensa is None:
            raise Exception('Aluno foi dispensado sem informar a justificativa de dispensa.')

        if self.tipo_convocacao == RegistroConvocacaoENADE.TIPO_CONVOCACAO_INGRESSANTE:
            condicao = 'Ingressante'
        else:
            condicao = 'Concluinte'
        if self.situacao == RegistroConvocacaoENADE.SITUACAO_PRESENTE or self.justificativa_dispensa.id == ID_REGISTRO_INGRESSANTE_PARTICIPANTE:
            return {
                'SituacaoENADE': {
                    'Habilitado': {
                        'Condicao': condicao,
                        'Edicao': str(self.convocacao_enade.ano_letivo.ano),
                    }
                }
            }
        else:
            if self.justificativa_dispensa.descricao in MOTIVOS_DISPENSA_RAP:
                return {
                    'SituacaoENADE': {
                        'NaoHabilitado': {
                            'Condicao': condicao,
                            'Edicao': str(self.convocacao_enade.ano_letivo.ano),
                            'Motivo': self.justificativa_dispensa.descricao,
                        }
                    }
                }
            else:
                return {
                    'SituacaoENADE': {
                        'NaoHabilitado': {
                            'Condicao': condicao,
                            'Edicao': str(self.convocacao_enade.ano_letivo.ano),
                            'OutroMotivo': self.justificativa_dispensa.descricao,
                        }
                    }
                }

    def get_data_prova(self):
        if self.convocacao_enade is None:
            return None
        modalidade_convocacao = (
            self.convocacao_enade.modalidadeconvocacaoenade_set.filter(modalidade_id=self.aluno.curso_campus.modalidade_id).only('data_prova').first()
        )
        if modalidade_convocacao:
            return modalidade_convocacao.data_prova
        return self.convocacao_enade.data_prova

    def get_ano_semestre_conclusao_curso(self):
        ano = self.aluno.ano_conclusao
        semestre = 1
        if ano is None:
            if self.aluno.ano_let_prev_conclusao is None:
                self.aluno.save(sync_user=False)
            ano = self.aluno.ano_let_prev_conclusao

        ano_enade = self.convocacao_enade.ano_letivo.ano
        if ano is None or ano <= ano_enade:
            ano = ano_enade
            semestre = 2
        return ano, semestre


class PossivelConcluinte(LogModel):
    aluno = models.ForeignKeyPlus('edu.Aluno')
    convocacao_enade = models.ForeignKeyPlus('edu.ConvocacaoENADE')
    convocado = models.BooleanField('Convocado', default=False)

    class Meta:
        verbose_name = 'Possivel concluinte'
        verbose_name_plural = 'Possíveis concluintes'

    @transaction.atomic
    def convocar(self):
        if not self.convocacao_enade.registroconvocacaoenade_set.filter(aluno_id=self.aluno.id).exists():
            registro = RegistroConvocacaoENADE()
            registro.aluno_id = self.aluno_id
            registro.convocacao_enade_id = self.convocacao_enade_id
            registro.percentual_ch_cumprida = self.aluno.get_percentual_carga_horaria_cumprida()
            registro.tipo_convocacao = RegistroConvocacaoENADE.TIPO_CONVOCACAO_CONCLUINTE
            registro.possivel_concluinte = True
            registro.save()
        self.convocado = True
        self.save()


class PossivelIntegralizado(LogModel):
    aluno = models.ForeignKeyPlus('edu.Aluno')
    convocacao_enade = models.ForeignKeyPlus('edu.ConvocacaoENADE')
    convocado = models.BooleanField('Convocado', default=False)
    percentual_ch_prevista = models.DecimalFieldPlus('CH prevista', null=True)
    ch_periodo = models.IntegerFieldPlus(verbose_name='CH no período')
    ch_cumprida = models.IntegerFieldPlus(verbose_name='CH cumprida')

    class Meta:
        verbose_name = 'Possível integralizado'
        verbose_name_plural = 'Possíveis integralizados'

    @transaction.atomic
    def convocar(self):
        if not self.convocacao_enade.registroconvocacaoenade_set.filter(aluno_id=self.aluno.id).exists():
            registro = RegistroConvocacaoENADE()
            registro.aluno_id = self.aluno_id
            registro.convocacao_enade_id = self.convocacao_enade_id
            registro.percentual_ch_cumprida = self.aluno.get_percentual_carga_horaria_cumprida()
            registro.tipo_convocacao = RegistroConvocacaoENADE.TIPO_CONVOCACAO_CONCLUINTE
            registro.possivel_integralizado = True
            registro.save()
        self.convocado = True
        self.save()


class PeriodoConvocacaoRegencia(LogModel):
    SEARCH_FIELDS = ['data_inicio', 'data_fim']
    convocacao_enade = models.ForeignKeyPlus('edu.ConvocacaoENADE')
    data_inicio = models.DateFieldPlus('Data inicial', null=False, blank=False)
    data_fim = models.DateFieldPlus('Data final', null=False, blank=False)

    class Meta:
        verbose_name = 'Período de convocação de regência'
        verbose_name_plural = 'Períodos de convocação de regência'

    def __str__(self):
        return f'{self.data_inicio.strftime("%d/%m/%Y")} a {self.data_fim.strftime("%d/%m/%Y")}'

    def can_delete(self, user):
        return (
            user.has_perm('edu.delete_periodoconvocacaoregencia')
            and not self.convocacao_enade.registroconvocacaoenade_set.filter(periodo_convocacao_regencia_id=self.id).exists()
        )

    def get_total_convocados(self):
        return RegistroConvocacaoENADE.objects.filter(convocacao_enade_id=self.convocacao_enade.id, periodo_convocacao_regencia_id=self.id).count()
