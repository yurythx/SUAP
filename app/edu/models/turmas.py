import datetime

from comum.models import Configuracao
from decimal import Decimal
from django.apps import apps
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from djtools.db import models
from edu import perms
from edu.managers import TurmaLocalManager, TurmaManager
from edu.models.cadastros_gerais import PERIODO_LETIVO_CHOICES, HorarioAula, HorarioAulaDiario, SituacaoMatricula, SituacaoMatriculaPeriodo, Turno
from edu.models.historico import MatriculaPeriodo
from rh.models import PessoaFisica
from edu.models.logs import LogModel


class Turma(LogModel):
    SEARCH_FIELDS = ['codigo', 'descricao']

    # Manager
    objects = TurmaManager()
    locals = TurmaLocalManager()
    # Fields
    codigo = models.CharFieldPlus(verbose_name='Código')
    descricao = models.CharFieldPlus(verbose_name='Descrição', max_length=300)
    ano_letivo = models.ForeignKeyPlus('comum.Ano', verbose_name='Ano Letivo', related_name='turma_por_ano_letivo_set', on_delete=models.CASCADE)
    periodo_letivo = models.PositiveIntegerField(verbose_name='Período Letivo', choices=PERIODO_LETIVO_CHOICES)
    periodo_matriz = models.PositiveIntegerField(verbose_name='Período Turma')
    turno = models.ForeignKeyPlus('edu.Turno', verbose_name='Turno', on_delete=models.CASCADE)
    curso_campus = models.ForeignKeyPlus('edu.CursoCampus', verbose_name='Curso')
    matriz = models.ForeignKeyPlus('edu.Matriz', null=True)
    sequencial = models.PositiveIntegerField(default=1)
    calendario_academico = models.ForeignKeyPlus('edu.CalendarioAcademico', null=True)
    quantidade_vagas = models.PositiveIntegerField('Quantidade de Vagas', default=0)
    polo = models.ForeignKeyPlus('edu.Polo', null=True, verbose_name='Polo EAD', blank=True, on_delete=models.CASCADE)
    convenio = models.ForeignKeyPlus('edu.Convenio', null=True, blank=True, verbose_name='Convênio')
    sigla = models.CharFieldPlus(default='', null=True, blank=True)
    codigo_educacenso = models.CharFieldPlus('Código EDUCACENSO', null=True, blank=True)
    # plano de retomada de aulas em virtude da pandemia (COVID19)
    pertence_ao_plano_retomada = models.BooleanField(
        verbose_name='Plano de Retomada', default=False, help_text='Adicionada ao plano de retomada de aulas em virtude da pandemia (COVID19)'
    )

    class Meta:
        verbose_name = 'Turma'
        verbose_name_plural = 'Turmas'

        permissions = (('gerar_turmas', 'Gerar Turmas'),)
        ordering = ('descricao',)

    def tem_integracao_com_moodle(self):
        return self.diario_set.filter(integracao_com_moodle=True).exists()

    def transferir(self, matriculas_periodo, turma_destino, commit=False):
        from edu.models import MatriculaDiario

        diarios = []

        for diario_origem in self.diario_set.all():
            qs_diario_destino = turma_destino.diario_set.filter(componente_curricular__componente=diario_origem.componente_curricular.componente)
            diario_destino = qs_diario_destino.exists() and qs_diario_destino[0] or None
            diarios.append((diario_origem, diario_destino))

        if commit:
            for matricula_periodo in MatriculaPeriodo.objects.filter(id__in=matriculas_periodo):
                for diario_origem, diario_destino in diarios:
                    if diario_destino:
                        for matricula_diario in MatriculaDiario.objects.filter(matricula_periodo=matricula_periodo, diario=diario_origem):
                            matricula_diario.transferir(diario_destino)
                matricula_periodo.turma = turma_destino
                matricula_periodo.save()

        return diarios

    def get_alunos_relacionados(self):
        qs = MatriculaPeriodo.objects.all()
        qs = qs.filter(matriculadiario__diario__turma=self) | qs.filter(turma=self)
        return qs.distinct().order_by('aluno__pessoa_fisica__nome', 'aluno__pk').select_related('aluno__pessoa_fisica')

    def get_alunos_matriculados(self):
        return self.matriculaperiodo_set.order_by('aluno__pessoa_fisica__nome', 'aluno_id').select_related('aluno__pessoa_fisica')

    def get_alunos_matriculados_diarios(self):
        from edu.models import MatriculaDiario

        return (
            MatriculaPeriodo.objects.filter(matriculadiario__diario__turma_id=self.id)
            .exclude(turma_id=self.id)
            .exclude(matriculadiario__situacao=MatriculaDiario.SITUACAO_TRANSFERIDO)
            .order_by('aluno__pessoa_fisica__nome', 'aluno_id')
            .select_related('aluno__pessoa_fisica')
            .distinct()
        )

    def get_qtd_alunos_ativos(self):
        result = 0
        situacoes_inativas = (
            SituacaoMatriculaPeriodo.CANCELADA,
            SituacaoMatriculaPeriodo.CANCELAMENTO_COMPULSORIO,
            SituacaoMatriculaPeriodo.CANCELAMENTO_POR_DESLIGAMENTO,
            SituacaoMatriculaPeriodo.CANCELAMENTO_POR_DUPLICIDADE,
            SituacaoMatriculaPeriodo.TRANCADA,
            SituacaoMatriculaPeriodo.TRANCADA_VOLUNTARIAMENTE,
            SituacaoMatriculaPeriodo.TRANSF_CURSO,
        )
        result = self.get_alunos_matriculados().exclude(situacao__in=situacoes_inativas).count()
        result += self.get_alunos_matriculados_diarios().exclude(situacao__in=situacoes_inativas).count()
        return result

    def get_alunos_apto_matricula(self, turno=None, ignorar_matriculados=True, apenas_ingressantes=False):
        turno = turno or self.turno
        qs = MatriculaPeriodo.objects.filter(
            aluno__situacao__id__in=[
                SituacaoMatricula.MATRICULADO,
                SituacaoMatricula.MATRICULA_VINCULO_INSTITUCIONAL,
                SituacaoMatricula.TRANCADO,
                SituacaoMatricula.TRANCADO_VOLUNTARIAMENTE,
                SituacaoMatricula.INTERCAMBIO,
            ],
            situacao__id__in=[SituacaoMatriculaPeriodo.MATRICULADO, SituacaoMatriculaPeriodo.EM_ABERTO],
            ano_letivo=self.ano_letivo,
            periodo_letivo=self.periodo_letivo,
            aluno__periodo_atual=self.periodo_matriz,
            aluno__turno=turno,
            aluno__curso_campus=self.curso_campus,
            aluno__matriz__isnull=False,
        )
        if ignorar_matriculados:
            qs = qs.filter(turma__isnull=True)

        if apenas_ingressantes:
            qs = qs.filter(
                aluno__ano_letivo=self.ano_letivo,
                aluno__periodo_letivo=self.periodo_letivo,
                aluno__data_integralizacao__isnull=True,
                aluno__periodo_atual=1,
            )
        return qs

    @transaction.atomic
    def matricular_alunos(self, matriculas_periodo):
        """Matricula os períodos letivos recebidos na turma.

        Atualiza a situação dos períodos para "Matriculado", cria matrículas
        em diários para componentes não cumpridos que o aluno pode cursar e
        altera a situação do aluno para "Matriculado" com a data de início
        do ciclo quando aplicável.

        Args:
            matriculas_periodo: ``QuerySet`` de ``MatriculaPeriodo`` a serem
                matriculados na turma.
        """
        from edu.models import MatriculaDiario

        matriculas_periodo.update(turma_id=self.id, situacao_id=SituacaoMatriculaPeriodo.MATRICULADO)
        for matricula_periodo in matriculas_periodo:
            diarios = (
                self.diario_set.exclude(componente_curricular__componente_id__in=matricula_periodo.aluno.get_ids_componentes_cumpridos())
                .order_by('componente_curricular__componente_id')
                .distinct('componente_curricular__componente_id')
            )
            for diario in diarios:
                if matricula_periodo.aluno.pode_ser_matriculado_no_diario(diario)[0]:
                    MatriculaDiario.objects.get_or_create(matricula_periodo_id=matricula_periodo.id, diario_id=diario.id)

            aluno = matricula_periodo.aluno
            situacao_alterada = False
            if aluno.situacao_id != SituacaoMatricula.MATRICULADO:
                aluno.situacao_id = SituacaoMatricula.MATRICULADO
                situacao_alterada = True

            if situacao_alterada or aluno.data_inicio_ciclo is None:
                aluno.save(sync_user=False)

    @transaction.atomic
    def remover_alunos(self, matriculas_periodo, user):
        """Remove os períodos letivos da turma e atualiza as situações.

        Para cada período que pode ser removido, exclui as matrículas em
        diários ativas, redefine a situação para "Em Aberto" se não houver
        mais matrículas, remove a referência à turma e atualiza a situação
        do aluno. Retorna a lista de alunos removidos.

        Args:
            matriculas_periodo: ``QuerySet`` de ``MatriculaPeriodo`` a remover.
            user: usuário que solicitou a remoção.

        Returns:
            lista de ``Aluno`` cujos períodos foram removidos da turma.
        """
        from edu.models import EstruturaCurso, MatriculaDiario

        alunos_removidos = []
        for matricula_periodo in matriculas_periodo:
            if matricula_periodo.pode_remover_da_turma(user):
                if matricula_periodo.aluno.matriz.estrutura.tipo_avaliacao != EstruturaCurso.TIPO_AVALIACAO_CREDITO:
                    for md in matricula_periodo.matriculadiario_set.filter(diario__turma_id=self.id, situacao=MatriculaDiario.SITUACAO_CURSANDO):
                        if md.pode_ser_excluido_do_diario(user):
                            md.delete()

                if matricula_periodo.situacao_id != SituacaoMatriculaPeriodo.EM_ABERTO and not matricula_periodo.matriculadiario_set.exists():
                    matricula_periodo.situacao_id = SituacaoMatriculaPeriodo.EM_ABERTO

                matricula_periodo.turma = None
                matricula_periodo.save()
                matricula_periodo.aluno.atualizar_situacao('Remoção de Turma')
                alunos_removidos.append(matricula_periodo.aluno)

        return alunos_removidos

    def get_ext_combo_template(self):
        out = [f'{self}']
        out.append(f'<span class="disabled">{self.descricao}</span>')
        template = """
        <div style="overflow: hidden">
            <div style="float: left">
                {}
            </div>
        </div>
        """.format('<br/>'.join(out))
        return template

    def get_absolute_url(self):
        return f'/edu/turma/{self.pk:d}/'

    def get_calendario_academico(self):
        if self.diario_set.exists():
            return self.diario_set.all()[0].calendario_academico
        else:
            return None

    def pode_ser_excluido(self):
        from edu.models import MatriculaDiario

        return not (MatriculaPeriodo.objects.filter(turma=self).exists() or MatriculaDiario.objects.filter(diario__turma=self).exists())

    def pode_gerar_diario(self):
        return self.curso_campus.is_anual() and self.diario_set.filter(componente_curricular__qtd_avaliacoes=2).exists()

    @staticmethod
    @transaction.atomic
    def gerar_turmas(
        ano_letivo,
        periodo_letivo,
        turnos_dict,
        numero_vagas_dict,
        numero_turmas_dict,
        curso_campus,
        matriz,
        horario_campus,
        calendario_academico,
        componentes,
        pertence_ao_plano_retomada,
        polo,
        commit,
    ):
        from edu.models import Diario

        todas_turmas = []
        lista_diarios_geral = []

        periodos = []
        for periodo_matriz in list(numero_turmas_dict.keys()):
            if numero_turmas_dict[periodo_matriz]:
                periodos.append(periodo_matriz)

        sid = transaction.savepoint()

        for periodo_matriz in periodos:
            turma_params = {
                'ano_letivo': ano_letivo,
                'periodo_letivo': periodo_letivo,
                'periodo_matriz': periodo_matriz,
                'turno': turnos_dict[periodo_matriz],
                'curso_campus': curso_campus,
                'matriz': matriz,
            }
            if polo:
                turma_params.update(polo=polo)
            qs_turma = Turma.objects.filter(**turma_params)
            ultimo_sequencial = qs_turma.exists() and qs_turma.order_by('-sequencial')[0].sequencial or 0

            numero_turmas = numero_turmas_dict[periodo_matriz]

            turmas = []
            for turma in qs_turma.filter(calendario_academico=calendario_academico):
                turma.criada = False
                turmas.append(turma)
                todas_turmas.append(turma)

            for _i in range(len(turmas), numero_turmas):
                ultimo_sequencial += 1
                turma_params.update(
                    calendario_academico=calendario_academico,
                    sequencial=ultimo_sequencial,
                    quantidade_vagas=numero_vagas_dict[periodo_matriz],
                    pertence_ao_plano_retomada=pertence_ao_plano_retomada,
                )
                turma = Turma.objects.create(**turma_params)
                turma.criada = True
                turmas.append(turma)
                todas_turmas.append(turma)

            lista_diarios = []

            for turma in turmas:
                turma.diarios = []
                for componente_curricular in componentes.filter(periodo_letivo=periodo_matriz) | componentes.filter(periodo_letivo__isnull=True):
                    dict_diario = {
                        'turma': turma,
                        'componente_curricular': componente_curricular,
                        'percentual_minimo_ch': 100,
                        'ano_letivo': turma.ano_letivo,
                        'periodo_letivo': periodo_letivo,
                        'horario_campus': horario_campus,
                        'turno': turma.turno,
                        'estrutura_curso': turma.matriz.estrutura,
                        'calendario_academico': calendario_academico,
                    }
                    diario_set = Diario.locals.filter(**dict_diario)
                    if diario_set.count() > 0:
                        diario = diario_set[0]
                        diario.criado = False
                    else:
                        dict_diario.update(quantidade_vagas=numero_vagas_dict[periodo_matriz])
                        dict_diario.update(segundo_semestre=componente_curricular.segundo_semestre)
                        diario = Diario(**dict_diario)
                        diario.criado = True
                        lista_diarios.append(diario)
                    turma.diarios.append(diario)

                lista_diarios_geral += lista_diarios

        if commit:
            for turma in todas_turmas:
                for diario in turma.diarios:
                    diario.save()
            transaction.savepoint_commit(sid)
        else:
            transaction.savepoint_rollback(sid)

        return todas_turmas

    def get_horarios(self, semestre='1'):
        turnos = Turno.objects.all()
        turnos.vazio = True
        for turno in turnos:
            turno.vazio = True
            horarios = HorarioAula.objects.filter(horarioauladiario__diario__in=self.diario_set.all(), turno=turno).distinct()
            if horarios:
                turno.vazio = False
                turnos.vazio = False
            turno.horariosaulas = horarios
            diarios = self.diario_set.order_by('componente_curricular__componente')
            # excluíndo os diários semestrais em cursos anuais
            if semestre == '1':
                diarios = diarios.exclude(segundo_semestre=True)
            else:
                diarios = diarios.exclude(segundo_semestre=False, componente_curricular__qtd_avaliacoes=2)
            dias_semana = [[1, 'Segunda'], [2, 'Terça'], [3, 'Quarta'], [4, 'Quinta'], [5, 'Sexta'], [6, 'Sábado'], [7, 'Domingo']]
            for dia_semana in dias_semana:
                dia_semana.append(HorarioAulaDiario.objects.filter(dia_semana=dia_semana[0], diario__in=diarios))
            turno.dias_semana = dias_semana
        return turnos

    def save(self, *args, **kwargs):
        if self.id is None or self.codigo is None:
            self.codigo = f'{self.ano_letivo.ano}{self.periodo_letivo}.{self.periodo_matriz}.{self.curso_campus.codigo}.{self.matriz_id}.{self.sequencial}{self.turno.descricao[0]}'
            if self.polo_id and Configuracao.get_valor_por_chave('edu', 'permite_gerar_turma_polo'):
                self.codigo = f'{self.codigo}-{self.polo.sigla}'
        self.descricao = f'{self.curso_campus.descricao_historico}, {self.curso_campus.modalidade.descricao}, {self.periodo_matriz}º Período, Matriz {self.matriz_id}, Turno {self.turno.descricao} ({self.ano_letivo.ano})'
        from edu.models import Diario

        for diario in Diario.objects.filter(turma_id=self.pk):
            diario.calendario_academico = self.calendario_academico
            diario.save()
        super(self.__class__, self).save(*args, **kwargs)

    def delete(self):
        self.matriculaperiodo_set.update(turma=None)
        super().delete()

    def get_diarios_pendentes(self):
        diarios_pendentes = []
        from edu.models import Diario

        for diario in Diario.objects.filter(turma_id=self.pk):
            pendencia = diario.pendente()
            if pendencia:
                diarios_pendentes.append([diario, pendencia])
        return diarios_pendentes

    def get_matriculas_aptas_adicao_turma(self, diario):
        qs_maticula_periodo = self.matriculaperiodo_set.filter(situacao=SituacaoMatriculaPeriodo.MATRICULADO).exclude(matriculadiario__diario=diario)
        ids_alunos_aptos = []
        for maticula_periodo in qs_maticula_periodo:
            if maticula_periodo.aluno.pode_ser_matriculado_no_diario(diario)[0]:
                ids_alunos_aptos.append(maticula_periodo.aluno_id)
        return self.matriculaperiodo_set.filter(aluno_id__in=ids_alunos_aptos)

    def can_change(self, user):
        return perms.realizar_procedimentos_academicos(user, self.curso_campus)


class TurmaMinicurso(LogModel):
    descricao = models.CharFieldPlus('Descrição')
    turno = models.ForeignKeyPlus('edu.Turno', verbose_name='Turno', null=True, blank=False)
    ano_letivo = models.ForeignKeyPlus('comum.Ano', verbose_name='Ano Letivo', on_delete=models.CASCADE)
    periodo_letivo = models.PositiveIntegerField('Período Letivo', choices=PERIODO_LETIVO_CHOICES)
    data_inicio = models.DateFieldPlus('Data de Início', null=False, blank=False)
    data_fim = models.DateFieldPlus('Data de Fim', null=False, blank=False)
    minicurso = models.ForeignKeyPlus('edu.Minicurso', null=False, blank=False, on_delete=models.CASCADE)
    gerar_matricula = models.BooleanField('Gerar Matrícula', default=False)

    # Turmas autoinstrucionais
    modelo_padrao = models.BooleanField(verbose_name='Modelo padrão', default=True)
    nota_minima = models.IntegerField(
        verbose_name='Nota mínima', null=True, blank=True, help_text='Informar caso a nota deva ser utilizada na definição da situação final.'
    )
    completude_minima = models.IntegerField(
        verbose_name='Completude mínima',
        null=True,
        blank=True,
        help_text='Informar caso o percentual de completude deva ser utilizado na definição da situação final.',
    )
    integracao_com_moodle = models.BooleanField('Integração com o Moodle', default=False)
    url_moodle = models.CharFieldPlus('URL do Moodle', null=True, blank=True)
    url_ambiente_virtual = models.CharFieldPlus(
        'URL do Ambiente Virtual',
        null=True,
        blank=True,
        help_text='Endereço da plataforma através da qual o professor poderá interagir com seus alunos durante a realização das aulas ou em atividades programadas',
    )

    autoinscricional = models.BooleanField(verbose_name='Autoinscricional', default=False)
    # Registrições da Autoinscrição (Nacionalidade)
    autoinscricao_brasileiros = models.BooleanField(verbose_name='Brasileiros', default=False)
    autoinscricao_estrangeiros = models.BooleanField(verbose_name='Estrangeiros', default=False)
    # Registrições da Autoinscrição (Funcionário/Servidor)
    autoinscricao_tae = models.BooleanField(verbose_name='Técnicos-Administrativos', default=False)
    autoinscricao_docente = models.BooleanField(verbose_name='Docentes', default=False)
    autoinscricao_prestadores = models.BooleanField(verbose_name='Prestadores de Serviço', default=False)
    # Registrições da Autoinscrição (Ensino)
    autoinscricao_alunos = models.BooleanField(verbose_name='Alunos', default=False)
    autoinscricao_nivel_ensino = models.ManyToManyFieldPlus('edu.nivelensino', verbose_name='Níveis de Ensino', blank=True)
    autoinscricao_modalidades = models.ManyToManyFieldPlus('edu.modalidade', verbose_name='Modalidades', blank=True)
    autoinscricao_campi = models.ManyToManyFieldPlus('rh.unidadeorganizacional', verbose_name='Campi', blank=True)
    autoinscricao_cursos = models.ManyToManyFieldPlus('edu.cursocampus', verbose_name='Cursos', blank=True, related_name='r1')

    class Meta:
        verbose_name = 'Turma do Minicurso'
        verbose_name_plural = 'Turmas do Minicurso'

    def __str__(self):
        return f'{self.pk} - {self.descricao} ({self.minicurso.codigo.replace("-", "")})'

    def save(self, *args, **kwargs):
        pk = self.pk
        super().save(*args, **kwargs)
        if pk:
            for participante in self.participanteturmaminicurso_set.all():
                if participante.aluno.turno_id != self.turno_id:
                    participante.aluno.turno = self.turno
                    participante.aluno.save(sync_user=self.gerar_matricula)
                if not self.gerar_matricula:
                    participante.aluno.revogar_acesso()

    def clean(self):
        if self.data_inicio and self.data_fim and self.data_inicio > self.data_fim:
            raise ValidationError({'data_inicio': 'A data de início deve ser maior ou igual a data de fim.'})
        ch_total = 0
        if self.pk:
            for professor_minicurso in self.professorminicurso_set.all():
                ch_total += professor_minicurso.carga_horaria or 0
            if ch_total > self.minicurso.ch_total:
                raise ValidationError(f'A soma das cargas-horárias dos professores não pode ultrapassar {self.minicurso.ch_total}h.')

    def get_absolute_url(self, param=None):
        url = f'/edu/turma_minicurso/{self.pk}/'
        if param:
            url = f'{url}?{param}'
        return url

    @transaction.atomic
    def adicionar_novo_aluno(
        self, pessoa_fisica: PessoaFisica, matricula_periodo_origem: MatriculaPeriodo | None = None
    ) -> ParticipanteTurmaMinicurso:
        from edu.models import Aluno

        participante = ParticipanteTurmaMinicurso.objects.filter(aluno__pessoa_fisica__cpf=pessoa_fisica.cpf, turma=self).first()
        if participante:
            return participante

        aluno = Aluno()
        aluno.pessoa_fisica = pessoa_fisica
        aluno.curso_campus = self.minicurso
        aluno.ano_letivo = self.ano_letivo
        aluno.periodo_letivo = self.periodo_letivo
        matricula_periodo = MatriculaPeriodo()
        if datetime.datetime.today().date() >= self.data_fim and self.nota_minima is None and self.completude_minima is None:
            aluno.situacao_id = SituacaoMatricula.CONCLUIDO
            matricula_periodo.situacao_id = SituacaoMatriculaPeriodo.APROVADO
        else:
            aluno.situacao_id = SituacaoMatricula.MATRICULADO
            matricula_periodo.situacao_id = SituacaoMatriculaPeriodo.MATRICULADO
        aluno.dt_conclusao_curso = self.data_fim
        aluno.data_inicio_ciclo = self.data_inicio
        aluno.data_prevista_termino_ciclo = self.data_fim
        aluno.turno = self.turno
        criar_usuario = self.gerar_matricula and aluno.situacao_id == SituacaoMatricula.MATRICULADO
        aluno.matricula = self.gerar_matricula_aluno()
        aluno.save(sync_user=criar_usuario)
        matricula_periodo.aluno = aluno
        matricula_periodo.ano_letivo = self.ano_letivo
        matricula_periodo.periodo_letivo = self.periodo_letivo
        matricula_periodo.save()
        participante = ParticipanteTurmaMinicurso.objects.create(aluno=aluno, turma=self)

        from edu.models.atividades import AtividadePraticaProfissional

        if (
            matricula_periodo_origem
            and self.minicurso.tipo_curso_autoinstrucional
            and AtividadePraticaProfissional.pode_registrar(matricula_periodo_origem.aluno, int(self.minicurso.tipo_curso_autoinstrucional or 0))
        ):
            if aluno.situacao_id == SituacaoMatricula.CONCLUIDO:
                AtividadePraticaProfissional.registrar_inicio_e_conclusao(
                    int(self.minicurso.tipo_curso_autoinstrucional),
                    participante.id,
                    type(participante),
                    matricula_periodo_origem.id,
                    self.minicurso.ch_total,
                    f'/edu/turma_minicurso/{self.id}/',
                    f'Matrícula em {self.minicurso.descricao}',
                    participante.nota,
                )
            else:
                AtividadePraticaProfissional.registrar_inicio(
                    int(self.minicurso.tipo_curso_autoinstrucional),
                    participante.id,
                    type(participante),
                    matricula_periodo_origem.id,
                    f'/edu/turma_minicurso/{self.id}/',
                    f'Matrícula em {self.minicurso.descricao}',
                )
        return participante

    def gerar_matricula_aluno(self):
        from edu.models import Aluno

        ano_e_periodo = f'{self.ano_letivo.ano}{self.periodo_letivo}'
        sigla_campus = self.minicurso.diretoria.setor.uo.sigla
        codigo_minicurso = self.minicurso.codigo.split('.')[0]
        participantes_da_turma = Aluno.objects.filter(
            participanteturmaminicurso__turma__minicurso=self.minicurso, ano_letivo__ano=self.ano_letivo.ano, periodo_letivo=self.periodo_letivo
        ).order_by('-matricula')
        maior_matricula = participantes_da_turma.exists() and participantes_da_turma[0].matricula or 0
        if not maior_matricula:
            codigo_aluno = '0001'
        else:
            maior_codigo = maior_matricula[len(maior_matricula) - 4 : len(maior_matricula)]
            codigo_aluno = str(int(maior_codigo) + 1).zfill(4)
        return f'{ano_e_periodo}{sigla_campus}{codigo_minicurso}{codigo_aluno}'

    def aprovar(self, participantes):
        for participante in participantes:
            participante.aluno.matriculaperiodo_set.all().update(situacao=SituacaoMatriculaPeriodo.objects.get(pk=SituacaoMatriculaPeriodo.APROVADO))
            participante.aluno.situacao = SituacaoMatricula.objects.get(pk=SituacaoMatricula.CONCLUIDO)
            participante.aluno.save(sync_user=False)
            participante.aluno.revogar_acesso()
            participante.concluir_atividade_pratica_profissional()

    def reprovar(self, participantes):
        for participante in participantes:
            participante.aluno.matriculaperiodo_set.all().update(situacao=SituacaoMatriculaPeriodo.objects.get(pk=SituacaoMatriculaPeriodo.REPROVADO))
            participante.aluno.situacao = SituacaoMatricula.objects.get(pk=SituacaoMatricula.NAO_CONCLUIDO)
            participante.aluno.save(sync_user=False)
            participante.aluno.revogar_acesso()
            participante.concluir_atividade_pratica_profissional()

    def is_aprovado_por_nota(self, nota):
        return self.nota_minima is None or (int(nota) >= self.nota_minima if nota is not None else False)

    def is_aprovado_por_completudo(self, completude):
        return self.completude_minima is None or (int(completude) >= self.completude_minima if completude is not None else False)


class ParticipanteTurmaMinicurso(LogModel):
    aluno = models.ForeignKeyPlus('edu.Aluno', verbose_name='Aluno')
    turma = models.ForeignKeyPlus('edu.TurmaMinicurso', verbose_name='Turma do Minicurso')
    nota = models.IntegerField(verbose_name='Nota', null=True, blank=True)
    completude = models.IntegerField(verbose_name='Completude', null=True, blank=True)

    def processar_resultado(self):
        situacao = SituacaoMatricula.MATRICULADO
        aprovado_nota = self.turma.is_aprovado_por_nota(self.nota)
        aprovado_completude = self.turma.is_aprovado_por_completudo(self.completude)

        if self.turma.nota_minima and self.turma.completude_minima:
            if self.nota is None or self.completude is None:
                situacao = SituacaoMatricula.MATRICULADO
            elif aprovado_nota and aprovado_completude:
                situacao = SituacaoMatricula.CONCLUIDO
            else:
                situacao = SituacaoMatricula.NAO_CONCLUIDO
        elif self.turma.nota_minima:
            if self.nota is None:
                situacao = SituacaoMatricula.MATRICULADO
            elif aprovado_nota:
                situacao = SituacaoMatricula.CONCLUIDO
            else:
                situacao = SituacaoMatricula.NAO_CONCLUIDO
        elif self.turma.completude_minima:
            if self.completude is None:
                situacao = SituacaoMatricula.MATRICULADO
            elif aprovado_completude:
                situacao = SituacaoMatricula.CONCLUIDO
            else:
                situacao = SituacaoMatricula.NAO_CONCLUIDO
        else:
            situacao = SituacaoMatricula.CONCLUIDO
        self.aluno.situacao_id = situacao
        if situacao != SituacaoMatricula.NAO_CONCLUIDO or datetime.date.today() > self.turma.data_fim:
            self.aluno.save(sync_user=False)

        self.concluir_atividade_pratica_profissional()

    @transaction.atomic
    def delete(self, *args, **kwargs):
        self.aluno.delete()
        if self.turma.minicurso.tipo_curso_autoinstrucional:
            from edu.models.atividades import AtividadePraticaProfissional

            AtividadePraticaProfissional.remover_registro(self.id, type(self))
        super().delete(*args, **kwargs)

    def concluir_atividade_pratica_profissional(self):
        from edu.models.atividades import AtividadePraticaProfissional

        if self.turma.minicurso.tipo_curso_autoinstrucional:
            if self.aluno.situacao_id == SituacaoMatricula.CONCLUIDO:
                atividade = AtividadePraticaProfissional.get(self.id, type(self))
                if atividade:
                    AtividadePraticaProfissional.registrar_conclusao(atividade, self.turma.minicurso.ch_total, self.nota)
            elif self.aluno.situacao_id == SituacaoMatricula.NAO_CONCLUIDO:
                AtividadePraticaProfissional.remover_registro(self.id, type(self))

    def possui_pendencia_vinculo_pratica_profissional(self):
        if not self.turma.minicurso.tipo_curso_autoinstrucional:
            return False
        if self.aluno.situacao_id != SituacaoMatricula.CONCLUIDO:
            return False
        from edu.models.atividades import AtividadePraticaProfissional

        return AtividadePraticaProfissional.get(self.id, type(self)) is None


class MonitorMinicurso(LogModel):
    aluno = models.ForeignKeyPlus('edu.Aluno', verbose_name='Aluno')
    turma_minicurso = models.ForeignKeyPlus('edu.TurmaMinicurso', verbose_name='Turma do Minicurso')
    carga_horaria = models.PositiveIntegerField('Carga Horária', null=True)

    class Meta:
        verbose_name = 'Monitor de Minicurso'
        verbose_name_plural = 'Monitores de Minicurso'

    def __str__(self):
        return f'{self.aluno.matricula} - {self.aluno.pessoa_fisica.nome}'

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.aluno.is_aluno_extensao():
            ch = self.carga_horaria * 100 if settings.COMPONENTE_CH_DECIMAL else self.carga_horaria
            AtividadeCurricularExtensao = apps.get_model('edu', 'AtividadeCurricularExtensao')
            AtividadeCurricularExtensao.registrar(self.aluno, type(self), self.pk, ch, self.turma_minicurso.minicurso.descricao_historico, True)

    def delete(self, *args, **kwargs):
        if self.aluno.is_aluno_extensao():
            AtividadeCurricularExtensao = apps.get_model('edu', 'AtividadeCurricularExtensao')
            AtividadeCurricularExtensao.registrar(self.aluno, type(self), self.pk, 0, None)
        super().delete(*args, **kwargs)


class ProfessorMinicurso(LogModel):
    professor = models.ForeignKeyPlus('edu.Professor', verbose_name='Professor')
    turma_minicurso = models.ForeignKeyPlus('edu.TurmaMinicurso', verbose_name='Turma do Minicurso')
    carga_horaria = models.PositiveIntegerField('Carga horária', null=True)
    carga_horaria_semanal = models.DecimalFieldPlus('Carga horária Semanal', null=True)  # h/r
    tipo = models.ForeignKeyPlus('edu.TipoProfessorDiario', verbose_name='Tipo', on_delete=models.CASCADE, null=True)

    def __str__(self):
        return f'{self.professor.get_matricula()} - {self.professor.vinculo.pessoa.nome}'

    def save(self, *args, **kwargs):
        self.carga_horaria_semanal = (1.0 * self.carga_horaria or 0) / 20
        super().save(*args, **kwargs)

    def clean(self):
        ch_total = 0
        for professor_minicurso in self.turma_minicurso.professorminicurso_set.exclude(pk=self.pk):
            ch_total += professor_minicurso.carga_horaria or 0
        ch_total += self.carga_horaria or 0
        if ch_total > self.turma_minicurso.minicurso.ch_total:
            raise ValidationError(f'A soma das cargas-horárias dos professores não pode ultrapassar {self.turma_minicurso.minicurso.ch_total}h.')

    def get_carga_horaria_semanal_ha(self):
        carga_horaria_semanal = self.carga_horaria_semanal or 0

        return int(
            Decimal(
                round(
                    self.turma_minicurso.minicurso.tipo_hora_aula
                    and carga_horaria_semanal * 60 / self.turma_minicurso.minicurso.tipo_hora_aula
                    or carga_horaria_semanal,
                    0,
                )
            )
        )

    def get_carga_horaria_ha(self):
        return (
            self.turma_minicurso.minicurso.tipo_hora_aula
            and self.carga_horaria
            and self.carga_horaria * 60 / self.turma_minicurso.minicurso.tipo_hora_aula
            or self.carga_horaria
            or 0
        )
