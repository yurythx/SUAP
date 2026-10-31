from __future__ import annotations

import datetime
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q, Sum, Value
from django.db.models.functions import Concat

from comum.models import Configuracao, User, UsuarioGrupoSetor
from comum.utils import get_uo, tl
from djtools.db import models
from djtools.templatetags.filters import format_iterable
from djtools.utils import send_mail, send_notification, somar_dias, mask_ch_componente
from edu.managers import AbonoFaltaManager, ConfiguracaoPedidoMatriculaManager, FiltroDiretoriaManager
from edu.models.cadastros_gerais import (
    PERIODO_LETIVO_CHOICES,
    HorarioAula,
    HorarioAulaDiario,
    InstituicaoEnsinoSuperior,
    SituacaoMatricula,
    SituacaoMatriculaPeriodo,
    Turno,
)
from edu.models.logs import LogModel
from edu.models.projeto_final import ProjetoFinal


class ConfiguracaoPedidoMatricula(LogModel):
    SEARCH_FIELDS = ('descricao',)
    id = models.AutoField(verbose_name='Código', primary_key=True)
    descricao = models.CharFieldPlus('Descrição')
    ano_letivo = models.ForeignKeyPlus('comum.Ano', verbose_name='Ano Letivo', on_delete=models.CASCADE)
    periodo_letivo = models.PositiveIntegerField('Período Letivo', choices=PERIODO_LETIVO_CHOICES)
    data_inicio = models.DateFieldPlus('Data de Início')
    data_fim = models.DateFieldPlus('Data de Fim')
    cursos = models.ManyToManyFieldPlus('edu.CursoCampus', blank=False)
    turmas = models.ManyToManyFieldPlus('edu.Turma', blank=True)
    diarios = models.ManyToManyFieldPlus('edu.Diario', blank=True)
    alunos = models.ManyToManyFieldPlus('edu.Aluno', blank=True)
    diretorias = models.ManyToManyField('edu.Diretoria')

    turmas_ofertadas = models.ManyToManyFieldPlus(
        'edu.Turma', related_name='ofertaturma_set', blank=True, help_text='Turmas que participarão do processo de renovação de matrícula.'
    )
    diarios_ofertados = models.ManyToManyFieldPlus(
        'edu.Diario', related_name='ofertadiario_set', blank=True, help_text='Diários que participarão do processo de renovação de matrícula.'
    )

    impedir_troca_turma = models.BooleanField(
        verbose_name='Impedir troca de turma',
        default=False,
        help_text='Marque essa opção para impedir que alunos do regime seriado possam trocar de turma dentro do seu respectivo turno.',
    )
    restringir_por_curso = models.BooleanField(
        verbose_name='Restringir por curso',
        default=False,
        help_text='Marque essa opção para impedir que os alunos se matriculem em disciplinas de outros cursos.',
    )
    requer_atualizacao_dados = models.BooleanField(
        verbose_name='Requerer atualização do cadastro',
        default=False,
        help_text='Marque essa opção para que o aluno atualize seus dados cadastrais no ato do pedido de matrícula.',
    )
    requer_atualizacao_caracterizacao = models.BooleanField(
        verbose_name='Requerer atualização da caracterização social',
        default=False,
        help_text='Marque essa opção para que o aluno atualize seus dados da caracterização social no ato do pedido de matrícula.',
    )
    requer_autorizacao_carteira_estudantil = models.BooleanField(
        verbose_name='Requerer autorização para emissão da carteira de estudante',
        default=False,
        help_text='Marque essa opção para que o aluno autorize a utilização dos seus dados pessoais para emissão da carteira de estudante digital',
    )
    permite_cancelamento_matricula_diario = models.BooleanField(
        verbose_name='Permitir o cancelamento de matrículas em diário já deferidas',
        default=False,
        help_text='Marque essa opção caso o aluno possa solicitar o cancelamento de matrículas em diários nos quais ele já se encontra matriculado.',
    )
    permite_requerimento_matricula_diario = models.BooleanField(
        verbose_name='Permitir o "requerimento" de matrículas em diário extracurriculares',
        default=False,
        help_text='Marque essa opção caso o aluno possa requerer matrícula em diários de disciplinas extracurriculares (necessário a aprovação do coordenador do curso).',
    )
    permite_solicitacao_disciplinas_eletivas = models.BooleanField(
        verbose_name='Permitir a "solicitação" de matrículas em diário extracurriculares',
        default=False,
        help_text='Marque essa opção caso o aluno possa solicitar matrícula em diários de disciplinas extracurriculares mesmo sem previsão de CH de disciplinas eletivas na matriz.',
    )
    restringir_disciplinas_eletivas_mesmo_curso = models.BooleanField(
        verbose_name='Restringir por curso',
        default=False,
        help_text='Marque essa opção para restringir a listagem de diários de disciplinas extracurriculares a somente componentes eletivos de outras matrizes do mesmo curso.',
    )
    permite_requerimento_quebra_de_requisito = models.BooleanField(
        verbose_name='Permitir o requerimento de matrículas com quebra de requisitos',
        default=False,
        help_text='Marque essa opção caso o aluno possa requerer matrícula em diários de disciplinas cujos pré e có-requisitos não foram cumpridos (requer aprovação do coordenador do curso).',
    )
    permite_requerimento_ultrapassar_ch_maxima = models.BooleanField(
        verbose_name='Permitir o requerimento de matrículas que ultrapassem a carga horária máxima do aluno no período',
        default=False,
        help_text='Marque essa opção caso o aluno possa requerer matrícula em diários mesmo quando a inclusão da disciplina exceda a carga horária máxima permitida para o aluno no período (requer aprovação do coordenador do curso).',
    )
    restringir_por_convenio = models.BooleanField(
        verbose_name='Restringir turma por convênio',
        default=False,
        help_text='Marque essa opção para impedir que os alunos se matriculem em turmas de convênios diferentes do dele.',
    )
    data_limite_requerimentos_especiais = models.DateFieldPlus(verbose_name='Data limite para submissão pelo aluno', null=True, blank=True)

    # Managers
    objects = models.Manager()
    locals = ConfiguracaoPedidoMatriculaManager()

    class Meta:
        verbose_name = 'Renovação de Matrícula'
        verbose_name_plural = 'Renovações de Matrícula'

    def get_diarios(self):
        from edu.models import Diario

        qs = getattr(self, '_diarios', None)
        if qs is None:
            qs = Diario.objects.filter(
                turma__ano_letivo=self.ano_letivo, turma__periodo_letivo=self.periodo_letivo, turma__curso_campus__in=self.get_cursos()
            )
            if self.turmas_ofertadas.exists():
                qs = qs.filter(turma__in=self.turmas_ofertadas.values_list('pk', flat=True))
            if self.diarios_ofertados.exists():
                qs = qs.filter(pk__in=self.diarios_ofertados.values_list('pk', flat=True))
            self._diarios = qs
        return qs

    def get_diarios_sem_horarios(self, curso=None, turma=None):
        from edu.models import ComponenteCurricular

        qs = self.get_diarios()
        qs = qs.exclude(horarioauladiario__isnull=False)
        qs = qs.exclude(
            componente_curricular__tipo__in=[
                ComponenteCurricular.TIPO_PRATICA_PROFISSIONAL,
                ComponenteCurricular.TIPO_TRABALHO_CONCLUSAO_CURSO,
                ComponenteCurricular.TIPO_SEMINARIO,
            ]
        )

        # excluindo diarios do turno EAD
        qs = qs.exclude(turno__descricao='EAD')

        if curso:
            qs = qs.filter(turma__curso_campus=curso)

        if turma:
            qs = qs.filter(turma=turma)

        return qs.order_by('turma__curso_campus__codigo', 'componente_curricular__optativo', 'componente_curricular__periodo_letivo')

    def get_absolute_url(self):
        return f'/edu/configuracao_pedido_matricula/{self.pk:d}/'

    def __str__(self):
        return f'{self.descricao} ({self.ano_letivo}.{self.periodo_letivo})'

    def cancelar(self):
        pedidomatricula = PedidoMatricula.objects.filter(configuracao_pedido_matricula=self)
        if not pedidomatricula.exists():
            raise ValidationError('Não há pedidos de matrícula.')
        pedidomatriculadiario = PedidoMatriculaDiario.objects.filter(pedido_matricula__in=pedidomatricula)
        if not pedidomatriculadiario.exists():
            raise ValidationError('Não há pedidos de matrícula com diários.')
        pedidomatriculadiario.update(deferido=False, data_processamento=datetime.date.today(), motivo=PedidoMatriculaDiario.MOTIVO_CANCELADO)

    def desfazer_cancelamento(self):
        PedidoMatriculaDiario.objects.filter(pedido_matricula__configuracao_pedido_matricula=self).update(
            deferido=False, data_processamento=None, motivo=None
        )

    def possui_pedido_diario(self):
        return PedidoMatriculaDiario.objects.filter(pedido_matricula__configuracao_pedido_matricula=self).exists()

    def is_cancelado(self):
        return PedidoMatriculaDiario.objects.filter(
            pedido_matricula__configuracao_pedido_matricula=self, motivo=PedidoMatriculaDiario.MOTIVO_CANCELADO
        ).exists()

    def pode_ser_alterado(self):
        return self.data_fim >= datetime.date.today()

    def pode_processar(self):
        return self.data_fim < datetime.date.today() and not self.is_processado()

    def is_processado(self):
        if self.id is None:
            return False
        if not self.pedidomatricula_set.exists():
            return False
        possui_pedido_processado = self.pedidomatricula_set.filter(
            Q(pedidomatriculadiario__data_processamento__isnull=False) | Q(motivo_impedimento_matricula_vinculo__isnull=False)
        ).exists()

        if not possui_pedido_processado:
            ids_pedidos_nao_processados = self.pedidomatricula_set.filter(pedidomatriculadiario__data_processamento__isnull=True).values_list(
                'pk', flat=True
            )
            possui_pedido_processado = (
                not self.pedidomatricula_set.filter(id__in=ids_pedidos_nao_processados)
                .exclude(matricula_periodo__procedimentomatricula__tipo=ProcedimentoMatricula.MATRICULA_VINCULO)
                .exists()
            )

        return possui_pedido_processado

    def get_qtd_matriculas_vinculo(self):
        try:
            if (
                self.pedidomatricula_set.filter(pedidomatriculadiario__isnull=True)[0].matricula_periodo.situacao.pk
                == SituacaoMatriculaPeriodo.MATRICULADO
            ):
                return self.pedidomatricula_set.filter(pedidomatriculadiario__isnull=True).count()
        except Exception:
            pass
        return 0

    def get_matriculas_diario_deferidas(self):
        return PedidoMatriculaDiario.objects.filter(
            pedido_matricula__configuracao_pedido_matricula=self, deferido=True, data_processamento__isnull=False
        )

    def get_matriculas_diario_indeferidas(self):
        return PedidoMatriculaDiario.objects.filter(
            pedido_matricula__configuracao_pedido_matricula=self, deferido=False, data_processamento__isnull=False
        )

    def pode_ser_excluido(self):
        return not (self.get_qtd_matriculas_vinculo() or self.get_matriculas_diario_deferidas() or self.get_matriculas_diario_indeferidas())

    def get_cursos(self):
        from edu.models.cursos import CursoCampus

        qs = getattr(self, '_cursos', None)
        if qs is None:
            ids = []
            ids.extend(self.cursos.values_list('id', flat=True))
            ids.extend(
                self.pedidomatricula_set.exclude(matricula_periodo__aluno__curso_campus__in=ids)
                .values_list('matricula_periodo__aluno__curso_campus', flat=True)
                .order_by('matricula_periodo__aluno__curso_campus')
                .distinct()
            )
            qs = CursoCampus.objects.filter(id__in=set(ids))
            self._cursos = qs
        return qs

    def get_monitoramento_cursos(self):
        lista = []
        for curso_campus in self.get_cursos():
            # quantidade de alunos
            curso_campus.qtd_alunos_aptos = self.get_alunos_aptos(curso_campus).count()
            curso_campus.qtd_alunos_participantes = self.get_alunos_participantes(curso_campus).count()
            curso_campus.qtd_alunos_nao_participantes = self.get_alunos_nao_participantes(curso_campus).count()
            percentual_alunos_participantes = (
                round(curso_campus.qtd_alunos_participantes * 100.0 / float(curso_campus.qtd_alunos_aptos), 2) if curso_campus.qtd_alunos_aptos else 0
            )
            curso_campus.percentual_alunos_participantes = percentual_alunos_participantes > 100 and 100 or percentual_alunos_participantes
            lista.append(curso_campus)
        return lista

    def get_alunos_aptos(self, curso=None):
        from edu.models.historico import MatriculaPeriodo

        id_curso = curso and curso.id or 'all'
        qs_aptos = getattr(self, f'_alunos_aptos_{id_curso}', None)
        if qs_aptos is None:
            qs_aptos = MatriculaPeriodo.objects.filter(
                aluno__matriz__isnull=False,
                ano_letivo=self.ano_letivo,
                periodo_letivo=self.periodo_letivo,
                situacao__id__in=[
                    SituacaoMatriculaPeriodo.MATRICULADO,
                    SituacaoMatriculaPeriodo.EM_ABERTO,
                    SituacaoMatriculaPeriodo.MATRICULA_VINCULO_INSTITUCIONAL,
                ],
                aluno__curso_campus__in=self.cursos.values_list('id', flat=True),
            )
            restringir_por_tuma = self.turmas.exists()
            restringir_por_diario = self.diarios.exists()
            restringir_por_aluno = self.alunos.exists()
            if restringir_por_tuma or restringir_por_diario or restringir_por_aluno:
                turmas = self.turmas.filter(curso_campus=curso) if curso else self.turmas
                qs_aptos_turma = (
                    qs_aptos.filter(aluno__in=turmas.values_list('diario__matriculadiario__matricula_periodo__aluno', flat=True))
                    if restringir_por_tuma
                    else MatriculaPeriodo.objects.none()
                )
                diarios = self.diarios.filter(turma__curso_campus=curso) if curso else self.diarios
                qs_aptos_diario = (
                    qs_aptos.filter(aluno__in=diarios.values_list('matriculadiario__matricula_periodo__aluno', flat=True))
                    if restringir_por_diario
                    else MatriculaPeriodo.objects.none()
                )
                alunos = self.alunos.filter(curso_campus=curso) if curso else self.alunos
                qs_aptos_aluno = (
                    qs_aptos.filter(aluno__in=alunos.values_list('id', flat=True)) if restringir_por_aluno else MatriculaPeriodo.objects.none()
                )
                qs_aptos = qs_aptos.exclude(aluno__ano_letivo=self.ano_letivo, aluno__periodo_letivo=self.periodo_letivo)
                if curso:
                    qs_aptos = qs_aptos.filter(aluno__curso_campus=curso)
                qs_aptos = qs_aptos_turma | qs_aptos_diario | qs_aptos_aluno
            else:
                qs_aptos = qs_aptos.exclude(aluno__ano_letivo=self.ano_letivo, aluno__periodo_letivo=self.periodo_letivo)
                if curso:
                    qs_aptos = qs_aptos.filter(aluno__curso_campus=curso).exclude(
                        aluno__ano_letivo=self.ano_letivo, aluno__periodo_letivo=self.periodo_letivo
                    )
            qs_aptos = qs_aptos.order_by('aluno__pessoa_fisica__nome')
            setattr(self, f'_alunos_aptos_{id_curso}', qs_aptos)
        return qs_aptos

    def get_alunos_participantes(self, curso=None):
        from edu.models import MatriculaPeriodo

        qs_participantes = MatriculaPeriodo.objects.filter(pedidomatricula__configuracao_pedido_matricula=self)
        if curso:
            qs_participantes = qs_participantes.filter(aluno__curso_campus=curso)
        return qs_participantes.order_by('aluno__pessoa_fisica__nome').distinct()

    def get_alunos_nao_participantes(self, curso):
        return self.get_alunos_aptos(curso).exclude(id__in=self.get_alunos_participantes(curso).values_list('id', flat=True))

    def pode_ter_curso_removido(self, curso_campus):
        qs1 = self.pedidomatricula_set.filter(configuracao_pedido_matricula=self, turma__curso_campus=curso_campus)
        qs2 = PedidoMatriculaDiario.objects.filter(pedido_matricula__configuracao_pedido_matricula=self, diario__turma__curso_campus=curso_campus)
        return not qs1.exists() and not qs2.exists()

    def enviar_emails_alunos(self):
        titulo = '[SUAP] Pedidos de Matrícula Cancelados'
        texto = (
            '<h1>Ensino</h1>'
            '<h2>Pedidos de Matrícula Cancelados</h2>'
            f'<p>Seus pedidos de matrícula para o período {self.ano_letivo.ano}.{self.periodo_letivo} foram cancelados devido a revogação do período de matrícula.</p>'
            '<p>Em breve comunicaremos um novo período. Pedimos desculpa pelos transtornos.</p>'
        )
        emails_destino = []
        for pedido_matricula in self.pedidomatricula_set.all():
            aluno_pm = pedido_matricula.matricula_periodo.aluno
            email = aluno_pm.email_pessoal
            email_notificacao = aluno_pm.email_notificacao

            if email:
                emails_destino.append(email)
            if email_notificacao:
                emails_destino.append(email_notificacao)

        send_mail(titulo, texto, settings.DEFAULT_FROM_EMAIL, emails_destino)

    def get_diarios_quantitativos(self, id_diario=None, curso=None, turma=None):
        from edu.models import ComponenteCurricular, Diario

        if id_diario:
            qs_diarios = Diario.objects.filter(id=id_diario)
        else:
            qs_diarios = self.get_diarios()
            qs_diarios_com_pratica_profissional = qs_diarios.filter(
                componente_curricular__tipo__in=[
                    ComponenteCurricular.TIPO_PRATICA_PROFISSIONAL,
                    ComponenteCurricular.TIPO_TRABALHO_CONCLUSAO_CURSO,
                    ComponenteCurricular.TIPO_SEMINARIO,
                ]
            )
            qs_diarios = (
                qs_diarios.filter(horarioauladiario__isnull=False) | qs_diarios.filter(turno__descricao='EAD') | qs_diarios_com_pratica_profissional
            )
            qs_diarios = qs_diarios.distinct().order_by('turma__curso_campus')

        if curso:
            qs_diarios = qs_diarios.filter(turma__curso_campus=curso)

        if turma:
            qs_diarios = qs_diarios.filter(turma=turma)

        lista_diarios_quantitativos = []
        for diario in qs_diarios:
            qs_pedidos_matricula_diario = PedidoMatriculaDiario.objects.filter(pedido_matricula__configuracao_pedido_matricula=self, diario=diario)
            qtd_matriculados = diario.matriculadiario_set.all().count()
            restantes = diario.quantidade_vagas - qtd_matriculados
            if restantes >= 0:
                restantes = f'<span class="status status-success">{restantes}</span>'
            else:
                restantes = f'<span class="status status-error">{restantes}</span>'
            diario_list = []
            diario_list.append(f'{diario.turma.curso_campus.codigo}')
            diario_list.append(f'<a href="/edu/diario/{diario.id}/" target="_blank">{diario.id}</a>')
            diario_list.append(diario.componente_curricular)
            diario_list.append(diario.quantidade_vagas)
            diario_list.append(qtd_matriculados)
            diario_list.append(qs_pedidos_matricula_diario.count())
            diario_list.append(qs_pedidos_matricula_diario.filter(deferido=True).count())
            diario_list.append(qs_pedidos_matricula_diario.filter(deferido=False, data_processamento__isnull=False).count())
            diario_list.append(restantes)
            diario_list.append(
                f'<ul class="action-bar"><li><a class="btn default popup" href="/edu/visualizar_alunos_pedido_diario/{self.id:d}/{diario.id}/">Ver solicitantes</a></li><li><a class="btn" href="/edu/imprimir_pedido_diario_pdf/{self.id}/{diario.id}/">Imprimir</a></li></ul>'
            )
            diario_list.append(diario.id)
            lista_diarios_quantitativos.append(diario_list)
        return lista_diarios_quantitativos

    def replicar(
        self,
        descricao,
        data_inicio,
        data_fim,
        impedir_troca_turma,
        restringir_por_curso,
        requer_atualizacao_dados,
        requer_atualizacao_caracterizacao,
        permite_cancelamento_matricula_diario,
        permite_requerimento_matricula_diario,
        permite_requerimento_quebra_de_requisito,
        permite_requerimento_ultrapassar_ch_maxima,
        data_limite_requerimentos_especiais,
    ):
        cursos = list(self.cursos.all())
        turmas = list(self.turmas.all())
        diarios = list(self.diarios.all())
        alunos = list(self.alunos.all())
        diretorias = list(self.diretorias.all())
        self.id = None
        self.descricao = descricao
        self.ano_letivo = self.ano_letivo
        self.periodo_letivo = self.periodo_letivo
        self.data_inicio = data_inicio
        self.data_fim = data_fim
        self.impedir_troca_turma = impedir_troca_turma
        self.restringir_por_curso = restringir_por_curso
        self.requer_atualizacao_dados = requer_atualizacao_dados
        self.requer_atualizacao_caracterizacao = requer_atualizacao_caracterizacao
        self.permite_cancelamento_matricula_diario = permite_cancelamento_matricula_diario
        self.permite_requerimento_matricula_diario = permite_requerimento_matricula_diario
        self.permite_requerimento_quebra_de_requisito = permite_requerimento_quebra_de_requisito
        self.permite_requerimento_ultrapassar_ch_maxima = permite_requerimento_ultrapassar_ch_maxima
        self.data_limite_requerimentos_especiais = data_limite_requerimentos_especiais
        self.clean()
        self.save()
        for curso_campus in cursos:
            self.cursos.add(curso_campus)
        for turma in turmas:
            self.turmas.add(turma)
        for diario in diarios:
            self.diarios.add(diario)
        for aluno in alunos:
            self.alunos.add(aluno)
        for diretoria in diretorias:
            self.diretorias.add(diretoria)
        self.save()

        # validando se existe um curso em outra configuracao no periodo escolhido
        for curso in cursos:
            qs = curso.configuracaopedidomatricula_set.filter(ano_letivo=self.ano_letivo, periodo_letivo=self.periodo_letivo).exclude(pk=self.pk)
            if qs.filter(data_inicio__lte=self.data_inicio, data_fim__gte=self.data_inicio) or qs.filter(
                data_inicio__lte=self.data_fim, data_fim__gte=self.data_fim
            ):
                self.delete()
                raise ValidationError(
                    f'Existe uma configuração cadastrada para o curso ({curso}) no período inserido que impede o cadastro neste intervalo de datas.'
                )

        return self

    def get_status(self):
        if self.is_cancelado():
            return ('Cancelada', 'status-error')
        elif self.is_processado():
            return ('Processada', 'status-success')
        else:
            hoje = datetime.date.today()
            if self.data_inicio > hoje:
                return ('Aguardando início', 'status-info')
            elif self.data_inicio < somar_dias(hoje, 1) and self.data_fim >= hoje:
                return ('Em andamento', 'status-alert')
            elif not self.pedidomatricula_set.exists():
                return ('Sem pedidos de matrícula', 'status-alert')
            else:
                return ('Aguardando processamento', 'status-alert')


class PedidoMatricula(LogModel):
    matricula_periodo = models.ForeignKeyPlus('edu.MatriculaPeriodo')
    configuracao_pedido_matricula = models.ForeignKeyPlus('edu.ConfiguracaoPedidoMatricula')
    turma = models.ForeignKeyPlus('edu.Turma', null=True)
    autorizacao_carteira_estudantil = models.BooleanField(
        default=False,
        verbose_name='Autorização para Emissão da Carteira de Estudante',
        help_text='Autorizo o envio dos meus dados pessoais para o Sistema Brasileiro de Educação (SEB) para fins de emissão da carteira de estudante digital',
    )
    matriculas_diario_canceladas = models.ManyToManyFieldPlus('edu.matriculadiario', verbose_name='Matrículas em Diário Canceladas')
    requerimentos_matricula_disciplina = models.ManyToManyFieldPlus(
        'edu.RequerimentoMatriculaDisciplina', verbose_name='Requerimentos de Matrículas em Disciplina'
    )
    requerimentos_matricula_quebra_de_requisito = models.ManyToManyFieldPlus(
        'edu.RequerimentoMatriculaQuebraRequisito', verbose_name='Requerimentos de matrículas em disciplina por quebra de requisito'
    )
    requerimentos_matricula_com_aumento_ch = models.ManyToManyFieldPlus(
        'edu.RequerimentoMatriculaComAumentoDeCH', verbose_name='Requerimentos de matrículas em disciplina com aumento de carga horária'
    )
    motivo_impedimento_matricula_vinculo = models.TextField(
        'Motivo do impedimento', null=True, help_text='Motivo do impedimento da realização do procedimento de matrícula vínculo institucional.'
    )

    class Meta:
        verbose_name = 'Pedido de Matrícula'
        verbose_name_plural = 'Pedidos de Matrícula'
        permissions = (('pode_quebrar_quantidade_minima', 'Pode quebrar quantidade mínima de disciplinas exigidas para matrícula'),)

    def get_turnos_horarios(self):
        ids_diarios = self.pedidomatriculadiario_set.all().values_list('diario__id', flat=True)
        qs_turnos = Turno.objects.filter(horarioaula__horarioauladiario__diario__id__in=ids_diarios).distinct()
        turnos = []
        for turno in qs_turnos:
            turno.horarios_aula = HorarioAula.objects.filter(
                turno=turno, horario_campus__id__in=self.pedidomatriculadiario_set.all().values_list('diario__horario_campus__id', flat=True)
            )
            turnos.append(turno)
        return turnos

    def get_horarios(self):
        from edu.models.diarios import Diario

        turnos = Turno.objects.all()
        diarios_pks = self.pedidomatriculadiario_set.all().values_list('diario__pk', flat=True)
        diarios = Diario.objects.filter(pk__in=diarios_pks).order_by('componente_curricular__componente')
        turnos.vazio = True
        for turno in turnos:
            turno.vazio = True
            horarios = HorarioAula.objects.filter(horarioauladiario__diario__in=diarios, turno=turno).distinct()
            if horarios:
                turno.vazio = False
                turnos.vazio = False
            turno.horariosaulas = horarios
            dias_semana = [[1, 'Segunda'], [2, 'Terça'], [3, 'Quarta'], [4, 'Quinta'], [5, 'Sexta'], [6, 'Sábado'], [7, 'Domingo']]
            for dia_semana in dias_semana:
                dia_semana.append(HorarioAulaDiario.objects.filter(dia_semana=dia_semana[0], diario__in=diarios))
            turno.dias_semana = dias_semana
        return turnos

    def matricular_na_turma(self):
        # alterando situacao da matrícula período para MATRICULADO e setando a turma
        matricula_periodo = self.matricula_periodo
        matricula_periodo.situacao = SituacaoMatriculaPeriodo.objects.get(pk=SituacaoMatriculaPeriodo.MATRICULADO)
        matricula_periodo.turma = self.turma
        matricula_periodo.save()

        # alterando a situação do aluno para MATRICULADO
        aluno = matricula_periodo.aluno
        aluno.situacao = SituacaoMatricula.objects.get(pk=SituacaoMatricula.MATRICULADO)

        aluno.save()

    def __str__(self):
        if self.turma:
            return f'Pedido de matrícula do aluno {self.matricula_periodo.aluno.matricula} na turma {self.turma.codigo}'
        return f'Pedido de matrícula do aluno {self.matricula_periodo.aluno.matricula}'

    @property
    def carga_horaria_total(self):
        from edu.models import Componente, MatriculaDiario

        ids_componentes_pedidosmatriculadiario = list(
            self.pedidomatriculadiario_set.values_list('diario__componente_curricular__componente_id', flat=True)
        )

        ids_componentes_matriculados = list(
            self.matricula_periodo.get_matriculas_diario()
            .exclude(situacao=MatriculaDiario.SITUACAO_CANCELADO)
            .values_list('diario__componente_curricular__componente_id', flat=True)
        )

        ch_total = (
            Componente.objects.only('pk', 'ch_hora_relogio')
            .filter(pk__in=set(ids_componentes_pedidosmatriculadiario + ids_componentes_matriculados))
            .aggregate(ch_total=Sum('ch_hora_relogio'))
            .get('ch_total')
            or 0
        )

        return ch_total


class PedidoMatriculaDiario(LogModel):
    MOTIVO_PERIODIZADO = 1
    MOTIVO_IRA = 2
    MOTIVO_PERIODO_IRA = 3
    MOTIVO_CANCELADO = 4
    MOTIVO_MATRICULA_INATIVA = 5

    MOTIVO_CHOICES = [
        [MOTIVO_PERIODIZADO, 'Periodizado'],
        [MOTIVO_IRA, 'I.R.A.'],
        [MOTIVO_PERIODO_IRA, 'Período/I.R.A.'],
        [MOTIVO_CANCELADO, 'Cancelado pela Diretoria'],
        [MOTIVO_MATRICULA_INATIVA, 'Matrícula Inativa'],
    ]

    pedido_matricula = models.ForeignKeyPlus('edu.PedidoMatricula')
    diario = models.ForeignKeyPlus('edu.Diario')
    deferido = models.BooleanField(default=False)
    data_processamento = models.DateField(null=True, verbose_name='Data de Processamento')
    motivo = models.PositiveIntegerField(choices=MOTIVO_CHOICES, null=True)

    class Meta:
        verbose_name = 'Pedido de Matrícula'
        verbose_name_plural = 'Pedidos de Matrícula'

    def __str__(self):
        return f'Pedido de matrícula do aluno {self.pedido_matricula.matricula_periodo.aluno.matricula} no diário {self.diario.pk}'

    def get_matricula_diario(self):
        from edu.models.historico import MatriculaDiario

        qs = MatriculaDiario.objects.filter(matricula_periodo=self.pedido_matricula.matricula_periodo, diario=self.diario)
        return qs.exists() and qs[0] or None

    def matricular_no_diario(self, motivo):
        from edu.models.diarios import MatriculaDiario

        # alterando situacao da matrícula período para MATRICULADO
        matricula_periodo = self.pedido_matricula.matricula_periodo
        matricula_periodo.situacao = SituacaoMatriculaPeriodo.objects.get(pk=SituacaoMatriculaPeriodo.MATRICULADO)
        matricula_periodo.save()

        # alterando a situação do aluno para MATRICULADO
        aluno = matricula_periodo.aluno
        aluno.situacao = SituacaoMatricula.objects.get(pk=SituacaoMatricula.MATRICULADO)
        aluno.save()

        # instanciando a matrícula diário para o diário solicitado
        if not MatriculaDiario.objects.filter(matricula_periodo=matricula_periodo, diario=self.diario).exists():
            matricula_diario = MatriculaDiario()
            matricula_diario.diario = self.diario
            matricula_diario.matricula_periodo = matricula_periodo
            matricula_diario.situacao = MatriculaDiario.SITUACAO_CURSANDO
            matricula_diario.save()

        # deferindo o pedido de matrícula em diário
        self.deferido = True
        self.data_processamento = datetime.date.today()
        self.motivo = motivo
        self.save()

    def indeferir(self, motivo):
        # indeferindo o pedido de matrícula em diário
        self.deferido = False
        self.data_processamento = datetime.date.today()
        self.motivo = motivo
        self.save()


class MotivoAusenciaEscolar(LogModel):
    descricao = models.CharField(verbose_name='Descrição')
    possui_previsao_normativa = models.BooleanField(verbose_name='Possui Previsão Normativa', default=False)
    reposicao_obrigatoria = models.BooleanField(verbose_name='Reposição Obrigatória', default=False)
    prazo_maximo_apresentar_justificativa = models.IntegerField(verbose_name='Prazo Máximo para Apresentar Justificativa', null=True, blank=True)
    ativo = models.BooleanField(verbose_name='Ativo', default=False)

    class Meta:
        verbose_name = 'Motivo para Ausência Escolar'
        verbose_name_plural = 'Motivos para Ausência Escolar'


class AbonoFaltas(LogModel):
    aluno = models.ForeignKeyPlus('edu.Aluno', null=False)
    data_solicitacao = models.DateFieldPlus('Data da Solicitação', null=True, blank=True)
    data_inicio = models.DateFieldPlus('Data de Início')
    quantidade_dias = models.IntegerField(verbose_name='Quantidade de Dias', blank=False, null=False, default=0)
    data_fim = models.DateFieldPlus('Data de Fim', blank=True, null=False)
    motivo_ausencia_escolar = models.ForeignKey(MotivoAusenciaEscolar, verbose_name='Motivo', on_delete=models.CASCADE, null=True)
    justificativa = models.TextField('Informação Complementar', null=False, blank=True)
    anexo = models.FileFieldPlus('Anexo', upload_to='edu/abono_faltas/', null=True, blank=False, filetypes=['pdf', 'jpeg', 'jpg', 'png'])
    responsavel_abono = models.ForeignKeyPlus('comum.User', verbose_name='Responsável', null=True)
    deferido = models.BooleanField(verbose_name='Deferido', null=True, default=True)
    data_avaliacao = models.DateFieldPlus(verbose_name='Data da Avaliação', null=True, blank=True)
    observacao_avaliacao = models.TextField(verbose_name='Observação da Avaliação', null=True, blank=True)
    contabilizar_falta = models.BooleanField(
        verbose_name='Contabilizar Falta',
        default=False,
        help_text='Marque essa opção caso as faltas no período informado devam ser contabilizadas apesar do cadastro da justificativa.',
    )
    diarios = models.ManyToManyFieldPlus('edu.diario', verbose_name='Diários', blank=True)

    # Managers
    objects = models.Manager()
    locals = AbonoFaltaManager('aluno__curso_campus__diretoria')

    fieldsets = (('Dados gerais', {'fields': (('data_inicio', 'data_fim'), 'justificativa', 'anexo')}),)

    class Meta:
        verbose_name = 'Justificativa de Falta'
        verbose_name_plural = 'Justificativas de Faltas'

    def get_nome_arquivo(self):
        return self.anexo.name.split('/')[-1]

    def __str__(self):
        return f'Justificativa de Falta - {self.aluno.get_nome_social_composto()}'

    def clean(self):
        if self.quantidade_dias and self.quantidade_dias > 0 and self.data_fim is None and self.data_inicio:
            self.data_fim = somar_dias(self.data_inicio, self.quantidade_dias - 1)

        # UC28-RN2 - A Data de Fim deve ser maior que a Data de Início.
        if self.data_inicio and self.data_fim and self.data_fim < self.data_inicio:
            raise ValidationError('A data inicial não pode ser maior que a data final.')

        if self.data_inicio and self.data_fim and self.aluno_id:
            if self.deferido is None or self.deferido:
                if (
                    AbonoFaltas.objects.filter(aluno_id=self.aluno_id, data_inicio__lte=self.data_fim, data_fim__gte=self.data_inicio)
                    .exclude(pk=self.pk)
                    .exclude(deferido=False)
                    .exists()
                ):
                    raise ValidationError('Já existe uma justificativa deferida ou aguardando avaliação envolvendo o período informado.')

            from edu.models import MatriculaPeriodo, SituacaoMatriculaPeriodo

            qs_matricula_periodos = (
                MatriculaPeriodo.objects.filter(
                    aluno_id=self.aluno_id,
                    matriculadiario__falta__aula__data__gte=self.data_inicio,
                    matriculadiario__falta__aula__data__lte=self.data_fim,
                )
                .exclude(situacao=SituacaoMatriculaPeriodo.MATRICULADO)
                .distinct()
            )
            if qs_matricula_periodos.exists():
                str_mp_fechados = ', '.join(f'{mp.ano_letivo} / {mp.periodo_letivo}' for mp in qs_matricula_periodos)
                raise ValidationError(f'No intervalo informado existem períodos já fechados: {str_mp_fechados}.')

    def __recuperar_faltas_periodo(self, periodo_inicial, periodo_final):
        from edu.models.diarios import Falta

        faltas = Falta.objects.filter(
            aula__data__gte=periodo_inicial, aula__data__lte=periodo_final, matricula_diario__matricula_periodo__aluno=self.aluno
        )
        if self.diarios.exists():
            faltas = faltas.filter(matricula_diario__diario__in=self.diarios.values_list('pk', flat=True))
        return faltas

    def __desabona_faltas(self):
        abono_atual = AbonoFaltas.objects.get(pk=self.pk)
        faltas = self.__recuperar_faltas_periodo(abono_atual.data_inicio, abono_atual.data_fim)
        for falta in faltas:
            falta.contabilizar = True
            falta.abono_faltas = None
            falta.save()

    def get_itens_configuracao_avaliacao_periodo(self):
        from edu.models.diarios import ItemConfiguracaoAvaliacao

        qs = ItemConfiguracaoAvaliacao.objects.filter(
            data__gte=self.data_inicio,
            data__lte=self.data_fim,
            configuracao_avaliacao__diario__matriculadiario__matricula_periodo__aluno=self.aluno_id,
        )
        if self.diarios.exists():
            qs = qs.filter(configuracao_avaliacao__diario__in=self.diarios.values_list('pk', flat=True))

        return qs

    def desfazer_deferimento_solicitacoes_reposicao(self) -> None:
        self.solicitacaoreposicaoatividade_set.filter(deferida=True).update(
            deferida=None,
            data_reposicao=None,
            avaliador=None,
            observacao=None,
        )

    @transaction.atomic
    def cancelar_deferimento(self) -> None:
        self.responsavel_abono = None
        self.deferido = None
        self.observacao_avaliacao = None
        self.data_avaliacao = None
        self.save()
        self.desfazer_deferimento_solicitacoes_reposicao()

    def checar_solicitacoes_reposicao_atividade(self) -> None:
        SITUACAO_CURSANDO = 1
        qs = self.get_itens_configuracao_avaliacao_periodo().filter(
            configuracao_avaliacao__diario__matriculadiario__situacao=SITUACAO_CURSANDO,
            configuracao_avaliacao__diario__matriculadiario__matricula_periodo__aluno=self.aluno_id,
        )
        if self.deferido:
            deferida = True if self.motivo_ausencia_escolar and self.motivo_ausencia_escolar.reposicao_obrigatoria else None
            # avaliar as solicitações adicionadas manualmente pelo aluno
            SolicitacaoReposicaoAtividade.objects.filter(abono_faltas=self).filter(deferida__isnull=True).update(deferida=deferida)
            for item_configuracao_avaliacao_id in qs.values_list('pk', flat=True):
                SolicitacaoReposicaoAtividade.objects.get_or_create(
                    abono_faltas=self,
                    item_configuracao_avaliacao_id=item_configuracao_avaliacao_id,
                    defaults={'deferida': deferida, 'data_reposicao': None},
                )
        else:
            self.desfazer_deferimento_solicitacoes_reposicao()

    def deve_abonar_faltas(self):
        if self.deferido:
            return (
                self.motivo_ausencia_escolar_id is None or self.motivo_ausencia_escolar_id and self.motivo_ausencia_escolar.possui_previsao_normativa
            )
        return False

    def save(self, *args, **kwargs):
        pk = self.pk
        if self.quantidade_dias > 0 and self.data_fim is None:
            self.data_fim = somar_dias(self.data_inicio, self.quantidade_dias - 1)

        # UC28-RN3 - Ao cadastrar um abono, todas as faltas cadastradas do aluno entre a Data de Início e a Data de Fim tem seu estado alterado para abonada.
        if self.pk:
            self.__desabona_faltas()

        super().save(*args, **kwargs)
        if pk is None:
            self.checar_solicitacoes_reposicao_atividade()

    def processar(self):
        faltas = self.__recuperar_faltas_periodo(self.data_inicio, self.data_fim)
        if self.deve_abonar_faltas():
            faltas.update(contabilizar=False)
        for falta in faltas:
            falta.abono_faltas = self
            falta.save()

    def delete(self, *args, **kwargs):
        # UC28-RN4 - Ao excluir um abono, todas as faltas cadastradas do aluno entre a Data de Início e a Data de Fim tem seu estado alterado para não abonada.
        self.__desabona_faltas()
        super().delete(*args, **kwargs)

    def get_absolute_url(self):
        return f'/edu/abonofaltas/{self.pk:d}/'

    def abono_a_criterio_do_docente(self) -> bool:
        return bool(self.deferido and self.motivo_ausencia_escolar and not self.motivo_ausencia_escolar.possui_previsao_normativa)

    def get_status(self) -> str:
        if self.deferido is None:
            return 'Aguardando avaliação'
        if not self.deferido:
            return 'Indeferida'
        return 'Deferida'


class SolicitacaoReposicaoAtividade(LogModel):
    abono_faltas = models.ForeignKey(AbonoFaltas, verbose_name='Justificativa de Falta', on_delete=models.CASCADE)
    item_configuracao_avaliacao = models.ForeignKey(
        'edu.itemconfiguracaoavaliacao', verbose_name='Item de Configuração de Avaliação', on_delete=models.CASCADE
    )
    avaliador = models.ForeignKeyPlus('comum.user', verbose_name='Avaliador', on_delete=models.CASCADE, null=True)
    deferida = models.BooleanField(verbose_name='Deferida', null=True)
    data_reposicao = models.DateFieldPlus(verbose_name='Data da Reposição', null=True, blank=True)
    observacao = models.TextField(verbose_name='Observação', null=True, blank=True)

    class Meta:
        verbose_name = 'Solicitação de reposição de atividade'
        verbose_name_plural = 'Solicitações de reposição de atividade'


class ProcedimentoMatricula(LogModel):
    INTERCAMBIO = 'Intercâmbio'
    TRANCAMENTO_COMPULSORIO = 'Trancamento Compulsório'
    TRANCAMENTO_VOLUNTARIO = 'Trancamento Voluntário'
    CANCELAMENTO_COMPULSORIO = 'Cancelamento Compulsório'
    CANCELAMENTO_VOLUNTARIO = 'Cancelamento Voluntário'
    CANCELAMENTO_POR_DUPLICIDADE = 'Cancelamento por Duplicidade'
    CANCELAMENTO_POR_DESLIGAMENTO = 'Cancelamento por Desligamento'
    EVASAO = 'Evasão'
    JUBILAMENTO = 'Jubilamento'
    REINTEGRACAO = 'Reintegração'
    TRANSFERENCIA_INTERCAMPUS = 'Transferência Intercampus'
    TRANSFERENCIA_CURSO = 'Transferência de Curso'
    TRANSFERENCIA_EXTERNA = 'Transferência Externa'
    MATRICULA_VINCULO = 'Matrícula Vínculo'
    INTEGRALIZAR_ENSINO_MEDIO = 'Integralização Fase Escolar'

    TIPO_CHOICES = [
        (INTERCAMBIO, INTERCAMBIO),
        (TRANCAMENTO_COMPULSORIO, TRANCAMENTO_COMPULSORIO),
        (TRANCAMENTO_VOLUNTARIO, TRANCAMENTO_VOLUNTARIO),
        (CANCELAMENTO_COMPULSORIO, CANCELAMENTO_COMPULSORIO),
        (CANCELAMENTO_VOLUNTARIO, CANCELAMENTO_VOLUNTARIO),
        (CANCELAMENTO_POR_DUPLICIDADE, CANCELAMENTO_POR_DUPLICIDADE),
        (CANCELAMENTO_POR_DESLIGAMENTO, CANCELAMENTO_POR_DESLIGAMENTO),
        (EVASAO, EVASAO),
        (JUBILAMENTO, JUBILAMENTO),
        (TRANSFERENCIA_INTERCAMPUS, TRANSFERENCIA_INTERCAMPUS),
        (TRANSFERENCIA_CURSO, TRANSFERENCIA_CURSO),
        (MATRICULA_VINCULO, MATRICULA_VINCULO),
        (INTEGRALIZAR_ENSINO_MEDIO, INTEGRALIZAR_ENSINO_MEDIO),
    ]

    TIPOS_CANCELAMENTO_VINCULO = (
        CANCELAMENTO_COMPULSORIO,
        CANCELAMENTO_VOLUNTARIO,
        CANCELAMENTO_POR_DUPLICIDADE,
        CANCELAMENTO_POR_DESLIGAMENTO,
        EVASAO,
        JUBILAMENTO,
    )

    tipo = models.CharFieldPlus(choices=TIPO_CHOICES)
    situacao_matricula_anterior = models.ForeignKeyPlus(
        'edu.SituacaoMatricula', related_name='situacaomatriculaanterior', verbose_name='Situação de Matrícula Anterior'
    )
    matricula_periodo = models.ForeignKeyPlus('edu.MatriculaPeriodo', verbose_name='Matrícula Período')
    motivo = models.TextField('Motivo')
    processo = models.ForeignKeyPlus('protocolo.Processo', null=True, blank=True)
    data = models.DateFieldPlus('Data')
    user = models.CurrentUserField()
    nova_matricula = models.CharFieldPlus(blank=True)
    identificador_externo = models.IntegerField(
        verbose_name='Identificador Externo',
        null=True,
        blank=True,
        help_text='Identificador do registro em sistema legado em caso de migração',
        db_index=True,
    )

    class Meta:
        verbose_name = 'Procedimento de Matrícula'
        verbose_name_plural = 'Procedimentos de Matrícula'

    def save(self, *args, **kwargs):
        importacao = kwargs.pop('importacao', False)
        if (
            not importacao
            and self.matricula_periodo.aluno.matriz_id
            and self.matricula_periodo.aluno.matriz.is_regime_modular()
            and self.tipo
            in [
                ProcedimentoMatricula.TRANCAMENTO_COMPULSORIO,
                ProcedimentoMatricula.TRANCAMENTO_VOLUNTARIO,
            ]
        ):
            # plano de retomada de aulas em virtude da pandemia (COVID19)
            if not self.matricula_periodo.matriculadiario_set.filter(diario__turma__pertence_ao_plano_retomada=True).exists():
                raise ValidationError('Não é possível realizar o trancamento de um aluno do regime modular.')

        super().save(*args, **kwargs)
        if not importacao and self.tipo in [
            ProcedimentoMatricula.TRANCAMENTO_COMPULSORIO,
            ProcedimentoMatricula.TRANCAMENTO_VOLUNTARIO,
            ProcedimentoMatricula.INTERCAMBIO,
            ProcedimentoMatricula.MATRICULA_VINCULO,
        ]:
            self.matricula_periodo.instanciar_proxima_matricula_periodo()

    def get_aluno(self):
        from edu.models.alunos import Aluno

        qs_aluno = Aluno.objects.filter(matricula=self.nova_matricula)
        return self.nova_matricula and qs_aluno.exists() and qs_aluno[0] or None

    def pode_ser_desfeito(self):
        if self.tipo == ProcedimentoMatricula.CANCELAMENTO_COMPULSORIO:
            # cancelamento de matrícula oriunda de transferência não pode ser desfeita
            if ProcedimentoMatricula.objects.filter(
                matricula_periodo__aluno__pessoa_fisica__cpf=self.matricula_periodo.aluno.pessoa_fisica.cpf,
                nova_matricula=self.matricula_periodo.aluno.matricula,
            ).exists():
                return False
        if self.tipo == ProcedimentoMatricula.MATRICULA_VINCULO:
            # não pode desfazer se houver TCC vinculado ao período
            if ProjetoFinal.objects.filter(matricula_periodo_id=self.matricula_periodo.id).exists():
                return False
            if self.matricula_periodo.aluno.atividadecomplementar_set.filter(
                ano_letivo_id=self.matricula_periodo.ano_letivo.id, periodo_letivo=self.matricula_periodo.periodo_letivo
            ).exists():
                return False
            if self.matricula_periodo.aluno.atividadeaprofundamento_set.filter(
                ano_letivo_id=self.matricula_periodo.ano_letivo.id, periodo_letivo=self.matricula_periodo.periodo_letivo
            ).exists():
                return False
        mps = self.matricula_periodo.aluno.get_matriculas_periodo()
        eh_ultimo_procedimento = self.matricula_periodo.aluno.get_ultimo_procedimento_matricula() == self
        eh_ultima_matricula_periodo = self.matricula_periodo == mps[0] or (
            self.matricula_periodo == mps[1] and mps[0].situacao.pk == SituacaoMatriculaPeriodo.EM_ABERTO
        )
        return eh_ultima_matricula_periodo and eh_ultimo_procedimento

    def get_situacao_esperada_periodo_letivo(self):
        mapeamento = {
            'Intercâmbio': SituacaoMatriculaPeriodo.TRANCADA_VOLUNTARIAMENTE,
            'Trancamento Compulsório': SituacaoMatriculaPeriodo.TRANCADA,
            'Trancamento Voluntário': SituacaoMatriculaPeriodo.TRANCADA_VOLUNTARIAMENTE,
            'Cancelamento Compulsório': SituacaoMatriculaPeriodo.CANCELADA,
            'Cancelamento Voluntário': SituacaoMatriculaPeriodo.CANCELAMENTO_COMPULSORIO,
            'Cancelamento por Duplicidade': SituacaoMatriculaPeriodo.CANCELAMENTO_COMPULSORIO,
            'Cancelamento por Desligamento': SituacaoMatriculaPeriodo.CANCELAMENTO_COMPULSORIO,
            'Evasão': SituacaoMatriculaPeriodo.EVASAO,
            'Jubilamento': SituacaoMatriculaPeriodo.JUBILADO,
            'Reintegração': SituacaoMatriculaPeriodo.EM_ABERTO,
            'Transferência Intercampus': SituacaoMatriculaPeriodo.TRANSF_INSTITUICAO,
            'Transferência de Curso': SituacaoMatriculaPeriodo.TRANSF_CURSO,
            'Transferência Externa': SituacaoMatriculaPeriodo.TRANSF_EXTERNA,
            'Matrícula Vínculo': SituacaoMatriculaPeriodo.MATRICULA_VINCULO_INSTITUCIONAL,
            'Integralização Fase Escolar': SituacaoMatriculaPeriodo.MATRICULADO,
        }
        return mapeamento[self.tipo]

    @transaction.atomic
    def desfazer(self):
        from edu.models.alunos import Aluno, MatriculaDiario, MatriculaPeriodo

        if self.pode_ser_desfeito():
            if self.tipo == ProcedimentoMatricula.REINTEGRACAO:
                self.matricula_periodo.aluno.situacao = self.situacao_matricula_anterior
                self.matricula_periodo.aluno.save()
                self.matricula_periodo.delete()
            else:
                if self.tipo in [
                    ProcedimentoMatricula.TRANCAMENTO_COMPULSORIO,
                    ProcedimentoMatricula.TRANCAMENTO_VOLUNTARIO,
                    ProcedimentoMatricula.MATRICULA_VINCULO,
                ]:
                    MatriculaPeriodo.objects.filter(
                        aluno=self.matricula_periodo.aluno,
                        ano_letivo__gte=self.matricula_periodo.ano_letivo,
                        situacao=SituacaoMatriculaPeriodo.EM_ABERTO,
                    ).delete()

                if self.tipo in [
                    ProcedimentoMatricula.TRANSFERENCIA_INTERCAMPUS,
                    ProcedimentoMatricula.TRANSFERENCIA_CURSO,
                    ProcedimentoMatricula.TRANCAMENTO_VOLUNTARIO,
                    ProcedimentoMatricula.TRANSFERENCIA_EXTERNA,
                    ProcedimentoMatricula.TRANCAMENTO_COMPULSORIO,
                ]:
                    # só é possível desfazer uma transferência se a nova matrícula estiver cancelada
                    novo_aluno = Aluno.objects.filter(matricula=self.nova_matricula).first()
                    if novo_aluno and novo_aluno.situacao_id != SituacaoMatricula.CANCELAMENTO_COMPULSORIO:
                        raise ValidationError(
                            f'Realize o cancelamento compulsório da matrícula "{novo_aluno.matricula}" para poder proceder com esse procemento.'
                        )

                    if novo_aluno and self.tipo == ProcedimentoMatricula.TRANSFERENCIA_CURSO:
                        self.matricula_periodo.aluno.codigo_sistec = novo_aluno.codigo_sistec
                        self.matricula_periodo.aluno.data_inicio_ciclo = novo_aluno.data_inicio_ciclo
                        Aluno.objects.filter(matricula=self.nova_matricula).update(codigo_sistec=None, data_inicio_ciclo=None)

                    if self.matricula_periodo.matriculadiario_set.filter(situacao=MatriculaDiario.SITUACAO_CANCELADO).exists():
                        self.matricula_periodo.matriculadiario_set.filter(situacao=MatriculaDiario.SITUACAO_CANCELADO).update(
                            situacao=MatriculaDiario.SITUACAO_CURSANDO
                        )

                self.matricula_periodo.aluno.situacao = self.situacao_matricula_anterior
                self.matricula_periodo.aluno.save()

                if self.tipo == ProcedimentoMatricula.EVASAO or self.tipo == ProcedimentoMatricula.MATRICULA_VINCULO:
                    self.matricula_periodo.situacao = SituacaoMatriculaPeriodo.objects.get(pk=SituacaoMatriculaPeriodo.EM_ABERTO)
                else:
                    self.matricula_periodo.situacao = SituacaoMatriculaPeriodo.objects.get(pk=SituacaoMatriculaPeriodo.MATRICULADO)

                is_tipo_cancelamento = self.tipo in [
                    ProcedimentoMatricula.CANCELAMENTO_COMPULSORIO,
                    ProcedimentoMatricula.CANCELAMENTO_VOLUNTARIO,
                    ProcedimentoMatricula.CANCELAMENTO_POR_DESLIGAMENTO,
                    ProcedimentoMatricula.EVASAO,
                    ProcedimentoMatricula.JUBILAMENTO,
                ]
                is_tipo_trancamento = self.tipo in [
                    ProcedimentoMatricula.INTERCAMBIO,
                    ProcedimentoMatricula.TRANCAMENTO_COMPULSORIO,
                    ProcedimentoMatricula.TRANCAMENTO_VOLUNTARIO,
                ]

                if is_tipo_cancelamento and self.matricula_periodo.matriculadiario_set.filter(situacao=MatriculaDiario.SITUACAO_CANCELADO).exists():
                    self.matricula_periodo.matriculadiario_set.filter(situacao=MatriculaDiario.SITUACAO_CANCELADO).update(
                        situacao=MatriculaDiario.SITUACAO_CURSANDO
                    )
                    self.matricula_periodo.situacao = SituacaoMatriculaPeriodo.objects.get(pk=SituacaoMatriculaPeriodo.MATRICULADO)
                elif is_tipo_trancamento and self.matricula_periodo.matriculadiario_set.filter(situacao=MatriculaDiario.SITUACAO_TRANCADO).exists():
                    self.matricula_periodo.matriculadiario_set.filter(situacao=MatriculaDiario.SITUACAO_TRANCADO).update(
                        situacao=MatriculaDiario.SITUACAO_CURSANDO
                    )
                    self.matricula_periodo.situacao = SituacaoMatriculaPeriodo.objects.get(pk=SituacaoMatriculaPeriodo.MATRICULADO)

                is_cursando_diario = self.matricula_periodo.matriculadiario_set.filter(situacao=MatriculaDiario.SITUACAO_CURSANDO)
                if not is_cursando_diario:
                    self.matricula_periodo.situacao = SituacaoMatriculaPeriodo.objects.get(pk=SituacaoMatriculaPeriodo.EM_ABERTO)

                self.matricula_periodo.save()
                self.matricula_periodo.excluir_proxima_matricula_periodo()

            if self.matricula_periodo.aluno.candidato_vaga_id and self.matricula_periodo.aluno.matriculaperiodo_set.count() == 1:
                from processo_seletivo.models import CandidatoVaga

                if self.tipo in (
                    ProcedimentoMatricula.CANCELAMENTO_COMPULSORIO,
                    ProcedimentoMatricula.CANCELAMENTO_VOLUNTARIO,
                    ProcedimentoMatricula.EVASAO,
                ):
                    candidato_vaga = self.matricula_periodo.aluno.candidato_vaga
                    if candidato_vaga and CandidatoVaga.objects.filter(
                        id=candidato_vaga.id,
                        convocacao__isnull=False,
                        eliminado=False,
                        situacao__in=[CandidatoVaga.MATRICULA_CANCELADA, CandidatoVaga.EVADIDO, CandidatoVaga.TRANSFERIDO],
                    ):
                        if candidato_vaga.vaga is None:
                            vagas_disponiveis = candidato_vaga.oferta_vaga.get_vagas_disponiveis()
                            candidato_vaga.vaga = len(vagas_disponiveis) > 0 and vagas_disponiveis[0] or None
                        if candidato_vaga.vaga is None:
                            raise ValidationError('Não é possível desfazer este procedimento. Não há oferta de vaga disponível.')
                        candidato_vaga.situacao = CandidatoVaga.MATRICULADO
                        candidato_vaga.save()
            self.matricula_periodo.aluno.revogar_registros_nada_consta_avaliados()
            self.delete()
        else:
            raise ValidationError('Não é possível desfazer este procedimento.')


class Requerimento(models.ModelPlus):
    SITUACAO_EM_ANDAMENTO = 'Em Andamento'
    SITUACAO_ARQUIVADO = 'Arquivado'

    MUDANCA_TURNO = 1  # Mudança de Turno
    MUDANCA_CURSO = 2  # Mudança de Curso
    MUDANCA_TURMA = 3  # Mudança de Turma

    JUSTIFICATIVA_FALTA = 5  # Justificativa de Falta

    LANCAMENTO = 6  # Lançamento ou Revisão de Faltas/Notas/Situação
    RENOVACAO_MATRICULA = 7  # Renovação / Reabertura de Matrícula

    TRANCAMENTO_MATRICULA = 8  # Trancamento de Matrícula
    CANCELAMENTO_MATRICULA = 9  # Cancelamento de Matrícula

    AFASTAMENTO = 10  # Afastamento

    LICENCA = 11  # Licença
    ATENDIMENTO_DOMICILIAR = 12  # Atendimento Domiciliar
    DISPENSA_ATIVIDADE = 13  # Dispensa de Atividades
    INCLUSAO_REMOCAO_DISCIPLINA = 14  # Inclusão/Remoção de Disciplinas
    ADEQUACAO_HORARIO = 15  # Adequação de Horários
    ESTUDO_INDIVIDUALIZADO = 16  # Estudo Individualizado

    REALIZACAO_PROVA = 17  # Realização de Trabalhos/Provas

    APROVEITAMENTO_ESTUDO = 18  # Aproveitamento de Estudos
    CERTIFICACAO_CONHECIMENTO = 19  # Certificação de Conhecimentos

    TRANCAMENTO_DISCIPLINA = 20  # Trancamento de Disciplina
    MATRICULA_DISCIPLINA = 21

    MATRICULA_QUEBRA_REQUISITO = 22  # Matrícula em Disciplina com Quebra de Requisito
    MATRICULA_QUEBRA_CH_MAX = 23  # Matrícula em Disciplina com Aumento de Carga Horária

    OUTRO = 100  # Outro

    TIPO_CHOICES = [
        [MUDANCA_TURNO, 'Mudança de Turno'],
        [MUDANCA_CURSO, 'Mudança de Curso'],
        [MUDANCA_TURMA, 'Mudança de Turma'],
        [JUSTIFICATIVA_FALTA, 'Justificativa de Falta'],
        [LANCAMENTO, 'Lançamento ou Revisão de Faltas/Notas/Situação'],
        [RENOVACAO_MATRICULA, 'Renovação / Reabertura de Matrícula'],
        [TRANCAMENTO_MATRICULA, 'Trancamento de Matrícula'],
        [TRANCAMENTO_DISCIPLINA, 'Cancelamento de Disciplina'],
        [MATRICULA_DISCIPLINA, 'Matrícula em Disciplina'],
        [CANCELAMENTO_MATRICULA, 'Cancelamento de Matrícula'],
        [AFASTAMENTO, 'Afastamento'],
        [LICENCA, 'Licença'],
        [ATENDIMENTO_DOMICILIAR, 'Atendimento Domiciliar'],
        [DISPENSA_ATIVIDADE, 'Dispensa de Atividades'],
        [INCLUSAO_REMOCAO_DISCIPLINA, 'Inclusão/Remoção de Disciplinas'],
        [ADEQUACAO_HORARIO, 'Adequação de Horários'],
        [ESTUDO_INDIVIDUALIZADO, 'Estudo Individualizado'],
        [REALIZACAO_PROVA, 'Realização de Trabalhos/Provas'],
        [APROVEITAMENTO_ESTUDO, 'Aproveitamento de Estudos'],
        [CERTIFICACAO_CONHECIMENTO, 'Certificação de Conhecimentos'],
        [MATRICULA_QUEBRA_REQUISITO, 'Matrícula em Disciplina com Quebra de Requisito'],
        [MATRICULA_QUEBRA_CH_MAX, 'Matrícula em Disciplina com Aumento de Carga Horária'],
        [OUTRO, 'Outro'],
    ]

    TIPO_AUTOMATIZADO_CHOICES = [
        [JUSTIFICATIVA_FALTA, 'Justificativa de Falta'],
        [TRANCAMENTO_MATRICULA, 'Trancamento de Matrícula'],
        [REALIZACAO_PROVA, 'Realização de Trabalhos/Provas'],
        [APROVEITAMENTO_ESTUDO, 'Aproveitamento de Estudos'],
        [TRANCAMENTO_DISCIPLINA, 'Cancelamento de Disciplina'],
        [MATRICULA_DISCIPLINA, 'Matrícula em Disciplina'],
        [MATRICULA_QUEBRA_REQUISITO, 'Matrícula em Disciplina com Quebra de Requisito'],
        [MATRICULA_QUEBRA_CH_MAX, 'Matrícula em Disciplina com Aumento de Carga Horária'],
    ]

    id = models.AutoField(verbose_name='Código', primary_key=True)

    aluno = models.ForeignKeyPlus('edu.Aluno', verbose_name='Aluno')
    tipo = models.IntegerField(verbose_name='Tipo', choices=TIPO_CHOICES)
    data = models.DateField(verbose_name='Data')
    localizacao = models.CharField(verbose_name='Localização', null=True, blank=True, max_length=255)

    turno = models.ForeignKeyPlus(Turno, verbose_name='Turno', null=True, blank=True, on_delete=models.CASCADE)
    curso_campus = models.ForeignKeyPlus('edu.CursoCampus', verbose_name='Curso', null=True, blank=True)
    turma = models.ForeignKeyPlus('edu.Turma', verbose_name='Turma', null=True, blank=True, on_delete=models.CASCADE)
    diario = models.ForeignKeyPlus('edu.Diario', verbose_name='Diário', null=True, blank=True, on_delete=models.CASCADE)

    inicio = models.DateField(verbose_name='Início', null=True, blank=True)
    termino = models.DateField(verbose_name='Término', null=True, blank=True)

    descricao = models.TextField(verbose_name='Descrição/Justificativa', null=True, blank=True)
    anexo = models.FileFieldPlus(verbose_name='Anexo', null=True, blank=True, upload_to='requerimentos')

    situacao = models.CharField(
        verbose_name='Situação',
        null=True,
        blank=True,
        max_length=255,
        choices=[[SITUACAO_EM_ANDAMENTO, 'Em Andamento'], [SITUACAO_ARQUIVADO, 'Arquivado']],
    )
    observacao = models.TextField(verbose_name='Observação', null=True, blank=True)

    deferido = models.BooleanField(verbose_name='Deferido', null=True)
    atendente = models.ForeignKeyPlus('comum.User', null=True, verbose_name='Atendente')

    objects = models.Manager()
    locals = FiltroDiretoriaManager('aluno__curso_campus__diretoria')

    class Meta:
        verbose_name = 'Requerimento'
        verbose_name_plural = 'Requerimentos'

        permissions = [
            ('pode_indeferir_em_lote', 'Pode indeferir requerimentos em lote'),
        ]

    def __str__(self):
        return f'Requerimento #{self.pk}'

    def get_absolute_url(self):
        return f'/edu/requerimento/{self.pk}/'

    def get_view_url(self):
        if self.tipo == Requerimento.APROVEITAMENTO_ESTUDO and self.sub_instance() != self:
            return f'/edu/requerimento_aproveitamento_estudo/{self.pk}/'
        return f'/edu/requerimento/{self.pk}/'

    def pode_ser_executado_automaticamente(self):
        return any(self.tipo == choice[0] for choice in Requerimento.TIPO_AUTOMATIZADO_CHOICES)

    def pode_ser_encaminhado(self):
        return self.tipo == Requerimento.APROVEITAMENTO_ESTUDO

    def pode_ser_avaliado(self):
        return self.avaliacaorequerimento_set.filter(deferido__isnull=True).exists()

    def avaliacao_foi_deferida(self):
        if self.avaliacaorequerimento_set.filter(deferido=False).exists():
            return False
        qtd = self.avaliacaorequerimento_set.count()
        if qtd and qtd == self.avaliacaorequerimento_set.filter(deferido=True).count():
            return True
        return None

    def indeferir(self, atendente: User | None = None, notificar: bool = True) -> None:
        self.situacao = Requerimento.SITUACAO_ARQUIVADO
        self.deferido = False
        self.atendente = atendente
        self.termino = datetime.date.today()
        self.save()
        if self.tipo == Requerimento.APROVEITAMENTO_ESTUDO:
            self.indeferir_solicitacoes_aproveitamento_pendentes()
        if notificar:
            transaction.on_commit(self.enviar_email)

    def indeferir_solicitacoes_aproveitamento_pendentes(self) -> int:
        solicitacoes_pendentes = SolicitacaoAproveitamentoEstudo.objects.filter(
            requerimento_id=self.pk,
            situacao__in=[
                SolicitacaoAproveitamentoEstudo.SITUACAO_CADASTRADA,
                SolicitacaoAproveitamentoEstudo.SITUACAO_SOLICITADA,
                SolicitacaoAproveitamentoEstudo.SITUACAO_EM_ANALISE,
            ],
        )
        if not self.observacao or not self.observacao.strip():
            return solicitacoes_pendentes.update(situacao=SolicitacaoAproveitamentoEstudo.SITUACAO_INDEFERIDA)

        filtro_sem_obs = Q(observacao__isnull=True) | Q(observacao='') | Q(observacao__regex=r'^\s*$')
        atualizadas_sem_obs = solicitacoes_pendentes.filter(filtro_sem_obs).update(
            situacao=SolicitacaoAproveitamentoEstudo.SITUACAO_INDEFERIDA,
            observacao=self.observacao,
        )
        atualizadas_com_obs = solicitacoes_pendentes.exclude(filtro_sem_obs).update(
            situacao=SolicitacaoAproveitamentoEstudo.SITUACAO_INDEFERIDA,
            observacao=Concat('observacao', Value('\n\n'), Value(self.observacao)),
        )
        return atualizadas_sem_obs + atualizadas_com_obs

    def processar(self, atendente):
        if self.tipo == Requerimento.TRANCAMENTO_MATRICULA:
            from edu.models.historico import MatriculaDiario

            matricula_periodo = self.aluno.get_ultima_matricula_periodo()
            situacao_matricula = SituacaoMatricula.objects.get(pk=SituacaoMatricula.TRANCADO_VOLUNTARIAMENTE)
            situacao_matricula_periodo = SituacaoMatriculaPeriodo.objects.get(pk=SituacaoMatriculaPeriodo.TRANCADA_VOLUNTARIAMENTE)
            procedimento = ProcedimentoMatricula(
                tipo=ProcedimentoMatricula.TRANCAMENTO_VOLUNTARIO,
                matricula_periodo=matricula_periodo,
                data=datetime.date.today(),
                motivo=self.descricao,
                situacao_matricula_anterior=self.aluno.situacao,
            )
            matricula_periodo.realizar_procedimento_matricula(
                procedimento, situacao_matricula, situacao_matricula_periodo, MatriculaDiario.SITUACAO_TRANCADO
            )
        self.situacao = Requerimento.SITUACAO_ARQUIVADO
        self.deferido = True
        self.atendente = atendente
        self.termino = datetime.date.today()
        self.observacao = 'Processamento realizado'
        self.save()
        self.enviar_email()

    def can_change(self, user):
        return not self.pode_ser_executado_automaticamente() and not self.pode_ser_encaminhado()

    def save(self, *args, **kwargs):
        if self.pk is None:
            if self.tipo != Requerimento.APROVEITAMENTO_ESTUDO:
                self.situacao = 'Em Andamento'
        super().save(*args, **kwargs)

    def sub_instance(self):
        requerimento = None
        if self.tipo == Requerimento.TRANCAMENTO_DISCIPLINA:
            requerimento = RequerimentoCancelamentoDisciplina.objects.filter(pk=self.pk).first()
        elif self.tipo == Requerimento.MATRICULA_DISCIPLINA:
            requerimento = RequerimentoMatriculaDisciplina.objects.filter(pk=self.pk).first()
        elif self.tipo == Requerimento.MATRICULA_QUEBRA_REQUISITO:
            requerimento = RequerimentoMatriculaQuebraRequisito.objects.filter(pk=self.pk).first()
        elif self.tipo == Requerimento.MATRICULA_QUEBRA_CH_MAX:
            requerimento = RequerimentoMatriculaComAumentoDeCH.objects.filter(pk=self.pk).first()
        elif self.tipo == Requerimento.APROVEITAMENTO_ESTUDO:
            requerimento = RequerimentoAproveitamentoEstudo.objects.filter(pk=self.pk).first()
        return requerimento or self

    def enviar_email(self):
        from edu.models import Aluno, Mensagem

        deferimento = self.get_situacao_avaliacao()
        assunto = f'Requerimento - {self.get_tipo_display()}'
        conteudo = """
Caro(a) aluno(a),

Informamos que houve movimentação no seu requerimento para {}. Para mais informações procure a secretaria acadêmica ou acesso o SUAP.

Situação: {}.
Deferimento: {}.
Observação: {}.

""".format(self.get_tipo_display(), self.situacao, deferimento, self.observacao or '')
        if self.atendente:
            mensagem = Mensagem()
            mensagem.remetente = self.atendente
            mensagem.assunto = assunto
            mensagem.conteudo = conteudo
            mensagem.via_suap = True
            mensagem.via_email = True
            mensagem.save()
            mensagem.destinatarios.add(self.aluno.get_user())
            mensagem.save()
            mensagem.enviar_emails(Aluno.objects.filter(pk=self.aluno.pk), copia_para_remetente=False)
        else:
            send_notification(assunto, conteudo, settings.DEFAULT_FROM_EMAIL, [self.aluno.get_vinculo()], fail_silently=True)

    def get_detalhamento(self):
        detalhamento = []
        subinstance = self.sub_instance()
        if self.tipo == Requerimento.REALIZACAO_PROVA:
            detalhamento.append(('Diário', self.diario))
        if self.tipo == Requerimento.TRANCAMENTO_MATRICULA:
            detalhamento.append(('Curso', self.aluno.curso_campus.descricao_historico))
        else:
            detalhamento = subinstance.get_detalhamento() if subinstance != self else []
        return detalhamento

    def get_atendentes_possiveis(self):
        # usuários sistêmicos são ignorados neste método
        from comum.models import User

        if self.pode_ser_executado_automaticamente() or self.pode_ser_encaminhado():
            return User.objects.none()

        users_ids = set()
        grupos_secretaria = [
            'Secretário Acadêmico',
            'Auxiliar de Secretaria Acadêmica',
            'Estagiário',
        ]
        ids_secretaria = list(
            UsuarioGrupoSetor.objects.filter(
                usuario_grupo__group__name__in=grupos_secretaria, setor_id=self.aluno.curso_campus.diretoria.setor_id
            ).values_list('usuario_grupo__user_id', flat=True)
        )
        if ids_secretaria:
            users_ids.update(ids_secretaria)

        return User.objects.filter(id__in=users_ids)

    @staticmethod
    def get_queryset(user):
        qs_coordenador = Requerimento.objects.none()
        qs_secretaria = Requerimento.objects.none()
        qs_professor = Requerimento.objects.none()
        qs_aluno = Requerimento.objects.none()
        qs_avaliador = Requerimento.objects.none()
        if user and not user.is_anonymous:
            vinculo = user.get_vinculo()
            if user.eh_aluno:
                qs_aluno = Requerimento.objects.filter(aluno__matricula=user.username)
            else:
                if user.has_group_cached('Coordenador de Curso'):
                    qs_coordenador = Requerimento.objects.filter(
                        tipo__in=[
                            Requerimento.MATRICULA_DISCIPLINA,
                            Requerimento.REALIZACAO_PROVA,
                            Requerimento.MATRICULA_QUEBRA_REQUISITO,
                            Requerimento.MATRICULA_QUEBRA_CH_MAX,
                        ]
                    )
                    qs_coordenador = (
                        qs_coordenador.filter(diario__turma__curso_campus__coordenador=vinculo)
                        | qs_coordenador.filter(diario__turma__curso_campus__coordenador_2=vinculo)
                        | Requerimento.objects.filter(tipo__in=[Requerimento.APROVEITAMENTO_ESTUDO]).filter(
                            Q(aluno__curso_campus__coordenador=vinculo) | Q(aluno__curso_campus__coordenador_2=vinculo)
                        )
                    )
                if user.has_group_cached('Avaliador de Requerimento'):
                    qs_avaliador = Requerimento.objects.filter(
                        pk__in=(
                            SolicitacaoAproveitamentoEstudo.objects.filter(avaliador__vinculo=vinculo)
                            .values_list('requerimento', flat=True)
                            .distinct()
                        )
                    )
                if user.has_group_cached(
                    (
                        'Administrador Acadêmico',
                        'Auxiliar de Secretaria Acadêmica',
                        'Estagiário',
                        'Estagiário Acadêmico Sistêmico',
                        'Secretário Acadêmico',
                    )
                ):
                    qs_secretaria = Requerimento.locals.all()
                if user.has_group_cached('Professor'):
                    qs_professor = Requerimento.objects.filter(tipo=Requerimento.REALIZACAO_PROVA)
                    qs_professor = qs_professor.filter(diario__professordiario__professor__vinculo__user=user)

        return qs_coordenador | qs_secretaria | qs_professor | qs_aluno | qs_avaliador

    @staticmethod
    def get_aluno_choices():
        ignorar = [choice[0] for choice in Requerimento.TIPO_AUTOMATIZADO_CHOICES]
        return [[x, y] for x, y in Requerimento.TIPO_CHOICES if x in Requerimento.get_tipos_abertos_alunos() and x not in ignorar]

    @staticmethod
    def get_tipos_abertos_alunos():
        return [
            int(token)
            for token in (Configuracao.get_valor_por_chave('edu', 'tipos_requerimentos_abertos_pelos_alunos') or '').replace(' ', '').split(',')
            if token
        ]

    @staticmethod
    def validar_tipos_na_avaliacao_em_lote(queryset):
        tipos_aceitos = dict(Requerimento.TIPO_AUTOMATIZADO_CHOICES).keys()
        tipos_aceitos_display = sorted(dict(Requerimento.TIPO_AUTOMATIZADO_CHOICES).values())
        if queryset.exclude(tipo__in=tipos_aceitos).exists():
            raise ValidationError(
                f'Apenas requerimentos dos seguintes tipos podem ser processados em lote: {format_iterable(tipos_aceitos_display)}.'
            )
        if queryset.values_list('tipo', flat=True).distinct().count() > 1:
            raise ValidationError('O processamento em lote só pode ser realizado com requerimentos do mesmo tipo.')

    def get_situacao_avaliacao(self):
        if self.tipo == Requerimento.APROVEITAMENTO_ESTUDO:
            if self.deferido is not None:
                return 'Deferida' if self.deferido else 'Indeferida'
            elif self.inicio is None:
                return 'Não iniciada'
            elif self.termino and self.deferido is None:
                qs = self.sub_instance().solicitacaoaproveitamentoestudo_set
                total = qs.count()
                deferido = qs.filter(parecer__deferido=True).count()
                if deferido:
                    return 'Deferida parcialmente' if deferido < total else 'Deferida'
                else:
                    return 'Aguardando avaliação'
            else:
                return 'Aguardando avaliação'
        elif self.deferido is None:
            return 'Aguardando avaliação' if self.inicio else 'Não iniciada'
        return 'Deferida' if self.deferido else 'Indeferida'

    def is_arquivado(self):
        return self.situacao == Requerimento.SITUACAO_ARQUIVADO

    def desarquivar(self) -> None:
        self.situacao = Requerimento.SITUACAO_EM_ANDAMENTO
        self.termino = None
        self.deferido = None
        self.save()
        if self.tipo == Requerimento.APROVEITAMENTO_ESTUDO:
            solicitacoes_nao_finalizadas = SolicitacaoAproveitamentoEstudo.objects.filter(
                Q(parecer__isnull=True) | Q(parecer__apto=False),
                requerimento_id=self.pk,
                situacao=SolicitacaoAproveitamentoEstudo.SITUACAO_INDEFERIDA,
            )
            solicitacoes_nao_finalizadas.filter(avaliador__isnull=False).update(
                situacao=SolicitacaoAproveitamentoEstudo.SITUACAO_EM_ANALISE,
            )
            solicitacoes_nao_finalizadas.filter(avaliador__isnull=True).update(
                situacao=SolicitacaoAproveitamentoEstudo.SITUACAO_SOLICITADA,
            )


class RequerimentoCancelamentoDisciplina(Requerimento):
    matriculas_diario = models.ManyToManyField('edu.MatriculaDiario', verbose_name='Matrículas em Diário')

    objects = FiltroDiretoriaManager('aluno__curso_campus__diretoria')

    def processar(self, atendente):
        for matricula_diario in self.matriculas_diario.all():
            matricula_diario.cancelar(diarios_ignorados=[md.diario for md in self.matriculas_diario.all() if md.id != matricula_diario.id])
        super().processar(atendente)

    def save(self, *args, **kwargs):
        self.tipo = Requerimento.TRANCAMENTO_DISCIPLINA
        super().save()

    def get_detalhamento(self):
        lista = [str(md.diario.componente_curricular.componente.descricao_historico) for md in self.matriculas_diario.all()]
        return [('Disciplinas', ', '.join(lista))]


class RequerimentoAproveitamentoEstudo(Requerimento):
    QTD_ANOS_APROVEITAMENTO = 12

    interno = models.BooleanField(
        verbose_name='Onde cursou as disciplinas?', default=False, blank=True, choices=[[True, 'Nesta instituição'], [False, 'Outra instituição']]
    )
    instituicao = models.ForeignKeyPlus(
        InstituicaoEnsinoSuperior,
        verbose_name='Instituição',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        help_text='Preenchimento obrigatório',
    )
    historico_escolar = models.FileFieldPlus(
        verbose_name='Histórico', upload_to='requerimentos_historico_escolar', null=True, blank=True, filetypes=['pdf']
    )
    comprovante_reconhecimento_curso = models.FileFieldPlus(
        verbose_name='Comprovante de Reconhecimento de Curso',
        upload_to='requerimentos_comprovante_reconhecimento_curso',
        null=True,
        blank=True,
        help_text='Preenchimento opcional',
        filetypes=['pdf'],
    )

    def save(self, *args, **kwargs):
        self.tipo = Requerimento.APROVEITAMENTO_ESTUDO
        super().save()

    def get_detalhamento(self):
        return [
            ('Disciplinas cursadas nessa instituição', 'Sim' if self.interno else 'Não'),
            ('Quantidade de disciplinas solicitadas', self.solicitacaoaproveitamentoestudo_set.count()),
            ('Quantidade de disciplinas avaliadas', self.solicitacaoaproveitamentoestudo_set.filter(parecer__apto=True).count()),
        ]

    def get_solicitacoes_aproveitamento_interno(self):
        return SolicitacaoAproveitamentoEstudoInterno.objects.filter(requerimento=self).order_by('id')

    def get_solicitacoes_aproveitamento_externo(self):
        return SolicitacaoAproveitamentoEstudoExterno.objects.filter(requerimento=self).order_by('id')

    def atualizar_situacao(self):
        if self.situacao == Requerimento.SITUACAO_ARQUIVADO and self.deferido is False:
            return
        qs = self.solicitacaoaproveitamentoestudo_set
        total = qs.count()
        avaliado = qs.filter(parecer__apto=True).count()
        deferido = qs.filter(parecer__deferido=True).count()
        if total == avaliado:
            self.termino = datetime.date.today()
            self.situacao = Requerimento.SITUACAO_ARQUIVADO
            if deferido == total:
                self.deferido = True
            elif deferido == 0:
                self.deferido = False
            else:
                self.deferido = None
        else:
            self.termino = None
            self.situacao = Requerimento.SITUACAO_EM_ANDAMENTO
            self.deferido = None
        self.save()
        self.enviar_email()

    @staticmethod
    def pode_solicitar_requerimento(matricula_periodo):
        from edu.models.diretorias import CalendarioAcademico

        qs = CalendarioAcademico.objects.filter(
            eh_calendario_referencia=True,
            uo_id=matricula_periodo.aluno.curso_campus.diretoria.setor.uo_id,
            ano_letivo=matricula_periodo.ano_letivo,
        )
        if not qs.exists():
            return False, 'O calendário acadêmico de referência para este período letivo não está configurado.'

        hoje = datetime.date.today()
        if (
            not qs.filter(data_inicio_certificacao__lte=hoje, data_fim_certificacao__gte=hoje).exists()
            and not qs.filter(data_inicio_certificacao2__lte=hoje, data_fim_certificacao2__gte=hoje).exists()
        ):
            return (
                False,
                'O período para solicitação de aproveitamento de estudos não está aberto.',
            )

        return True, ''

    def pode_finalizar_cadastro(self):
        if self.situacao:
            return False, 'Requerimento já avaliado.'
        return self.pode_solicitar_requerimento(self.aluno.get_ultima_matricula_periodo())


class ParecerAvaliacaoAproveitamentoEstudo(models.ModelPlus):
    descricao = models.CharField(verbose_name='Descrição')
    apto = models.BooleanField(verbose_name='Apto para Avalidar', choices=[[True, 'Sim'], [False, 'Não']])
    deferido = models.BooleanField(verbose_name='Avaliação Deferida', choices=[[True, 'Sim'], [False, 'Não']], null=True, blank=True)

    class Meta:
        verbose_name = 'Parecer de Avaliação de Aproveitamento de Estudo'
        verbose_name_plural = 'Pareceres de Avaliação de Aproveitamento de Estudo'

    def __str__(self):
        return self.descricao


class SolicitacaoAproveitamentoEstudo(models.ModelPlus):
    SITUACAO_CADASTRADA = 1
    SITUACAO_SOLICITADA = 2
    SITUACAO_EM_ANALISE = 3
    SITUACAO_DEFERIDA = 4
    SITUACAO_INDEFERIDA = 5
    SITUACAO_CHOICES = [
        [SITUACAO_CADASTRADA, 'Cadastrada'],
        [SITUACAO_SOLICITADA, 'Solicitada'],
        [SITUACAO_EM_ANALISE, 'Em Análise'],
        [SITUACAO_DEFERIDA, 'Deferida'],
        [SITUACAO_INDEFERIDA, 'Indeferida'],
    ]
    # Dados gerais
    requerimento = models.ForeignKeyPlus(RequerimentoAproveitamentoEstudo, verbose_name='Requerimento')
    componente_curricular = models.ForeignKeyPlus('edu.ComponenteCurricular', verbose_name='Componente Curricular')
    ementa = models.FileFieldPlus(verbose_name='Ementa', upload_to='ementa_requerimento_aproveitamento_estudo', filetypes=['pdf'])

    # Dados da Avaliação
    avaliador = models.ForeignKeyPlus('edu.Professor', verbose_name='Avaliador', null=True, blank=True)
    parecer = models.ForeignKeyPlus(ParecerAvaliacaoAproveitamentoEstudo, verbose_name='Parecer', null=True, blank=True)
    observacao = models.TextField(verbose_name='Observação', null=True, blank=True)
    # Situação
    situacao = models.IntegerField(verbose_name='Situação', choices=SITUACAO_CHOICES, default=SITUACAO_CADASTRADA)

    class Meta:
        verbose_name = 'Solicitação de Aproveitamento de Estudo'
        verbose_name_plural = 'Solicitações de Aproveitamento de Estudo'

    def subinstance(self):
        if self.requerimento.interno:
            return SolicitacaoAproveitamentoEstudoInterno.objects.get(pk=self.pk)
        else:
            return SolicitacaoAproveitamentoEstudoExterno.objects.get(pk=self.pk)

    def get_aproveitamento(self):
        from edu.models.historico import AproveitamentoEstudo

        subinstance = self.subinstance()
        matricula_periodo = self.requerimento.aluno.get_ultima_matricula_periodo()
        return AproveitamentoEstudo.objects.filter(
            matricula_periodo=matricula_periodo,
            componente_curricular=self.componente_curricular,
            escola_origem=subinstance.get_escola(),
            frequencia=subinstance.get_frequencia(),
            nota=subinstance.get_nota(),
            data=self.requerimento.data,
        ).first()

    @transaction.atomic
    def gerar_aproveitamento(self):
        from edu.models.historico import AproveitamentoEstudo, MatriculaDiario

        if self.get_aproveitamento() is None:
            matricula_periodo = self.requerimento.aluno.get_ultima_matricula_periodo()
            aproveitamento = AproveitamentoEstudo.objects.create(
                matricula_periodo=matricula_periodo,
                componente_curricular=self.componente_curricular,
                escola_origem=self.get_escola(),
                frequencia=self.get_frequencia(),
                nota=self.get_nota(),
                data=self.requerimento.data,
            )
            aproveitamento.professores.set([self.get_avaliador()])

            MatriculaDiario.objects.filter(
                situacao=MatriculaDiario.SITUACAO_CURSANDO,
                matricula_periodo=matricula_periodo,
                diario__componente_curricular=self.componente_curricular,
            ).delete()

    def excluir_aproveitamento(self):
        aproveitamento = self.get_aproveitamento()
        if aproveitamento:
            aproveitamento.delete()

    @transaction.atomic
    def cancelar_avaliacao(self):
        self.parecer = None
        self.observacao = None
        self.situacao = SolicitacaoAproveitamentoEstudo.SITUACAO_EM_ANALISE
        self.excluir_aproveitamento()
        self.save()
        self.requerimento.atualizar_situacao()

    def get_escola(self):
        pass

    def get_nota(self):
        pass

    def get_frequencia(self):
        pass

    def get_avaliador(self):
        return self.avaliador

    def is_finalizada(self):
        return self.parecer_id and self.parecer.apto


class SolicitacaoAproveitamentoEstudoInterno(SolicitacaoAproveitamentoEstudo):
    # Dados gerais
    diario_1 = models.ForeignKeyPlus('edu.Diario', verbose_name='Diário')
    ementa_1 = models.FileFieldPlus(verbose_name='Ementa', upload_to='ementa_requerimento_aproveitamento_estudo', filetypes=['pdf'])
    diario_2 = models.ForeignKeyPlus('edu.Diario', verbose_name='Diário', null=True, blank=True, related_name='r1')
    ementa_2 = models.FileFieldPlus(
        verbose_name='Ementa', upload_to='ementa_requerimento_aproveitamento_estudo', null=True, blank=True, filetypes=['pdf']
    )

    class Meta:
        verbose_name = 'Solicitação de Aproveitamento de Estudo Interno'
        verbose_name_plural = 'Solicitações de Aproveitamento de Estudo Interno'

    def get_matriculas_diario(self):
        matriculas_diario = []
        diarios = [self.diario_1]
        if self.diario_2:
            diarios.append(self.diario_2)
        for diario in diarios:
            matriculas_diario.append(
                diario.matriculadiario_set.filter(matricula_periodo__aluno__pessoa_fisica__cpf=self.requerimento.aluno.pessoa_fisica.cpf).first()
            )
        return matriculas_diario

    def get_escola(self):
        return 'Instituto Federal do Rio Grande do Norte'

    def get_nota(self):
        notas = [md.get_media_final_disciplina() or 0 for md in self.get_matriculas_diario()]
        return int(sum(notas) / len(notas))

    def get_frequencia(self):
        frequencias = [md.get_percentual_carga_horaria_frequentada() or 0 for md in self.get_matriculas_diario()]
        return int(sum(frequencias) / len(frequencias))


class SolicitacaoAproveitamentoEstudoExterno(SolicitacaoAproveitamentoEstudo):
    # Dados gerais
    ano_letivo_1 = models.ForeignKey('comum.ano', verbose_name='Ano Cursado', null=True, blank=True, on_delete=models.CASCADE)
    periodo_letivo_1 = models.IntegerField(verbose_name='Período Cursado', choices=PERIODO_LETIVO_CHOICES, blank=True, null=True)
    nome_1 = models.CharField(verbose_name='Nome do Componente')
    nota_1 = models.NotaField('Nota')
    frequencia_1 = models.PositiveIntegerField('Frequência (%)')
    ementa_1 = models.FileFieldPlus(verbose_name='Ementa', upload_to='ementa_requerimento_aproveitamento_estudo', filetypes=['pdf'])

    ano_letivo_2 = models.ForeignKey('comum.ano', verbose_name='Ano Cursado', null=True, blank=True, on_delete=models.CASCADE, related_name='r1')
    periodo_letivo_2 = models.IntegerField(verbose_name='Período Cursado', choices=PERIODO_LETIVO_CHOICES, blank=True, null=True)
    nome_2 = models.CharField(verbose_name='Nome do Componente', null=True, blank=True)
    nota_2 = models.NotaField('Nota', blank=True, null=True)
    frequencia_2 = models.PositiveIntegerField('Frequência (%)', blank=True, null=True)
    ementa_2 = models.FileFieldPlus(
        verbose_name='Ementa', upload_to='ementa_requerimento_aproveitamento_estudo', null=True, blank=True, filetypes=['pdf']
    )

    class Meta:
        verbose_name = 'Solicitação de Aproveitamento de Estudo Externo'
        verbose_name_plural = 'Solicitações de Aproveitamento de Estudo Externo'

    def get_dados(self):
        dados = []
        dados.append(
            {
                'nome': self.nome_1,
                'ano_periodo': f'{self.ano_letivo_1}/{self.periodo_letivo_1}',
                'nota': self.nota_1,
                'frequencia': self.frequencia_1,
                'ementa': self.ementa_1,
            }
        )
        if self.nome_2:
            dados.append(
                {
                    'nome': self.nome_2,
                    'ano_periodo': f'{self.ano_letivo_2}/{self.periodo_letivo_2}',
                    'nota': self.nota_2,
                    'frequencia': self.frequencia_2,
                    'ementa': self.ementa_2,
                }
            )
        return dados

    def get_escola(self):
        return self.requerimento.instituicao.nome

    def get_nota(self):
        notas = [dado['nota'] or 0 for dado in self.get_dados()]
        return int(sum(notas) / len(notas))

    def get_frequencia(self):
        frequencias = [dado['frequencia'] or 0 for dado in self.get_dados()]
        return int(sum(frequencias) / len(frequencias))


class RequerimentoMatriculaDisciplina(Requerimento):
    # objects = FiltroDiretoriaManager('diario__turma__curso_campus__diretoria')

    def processar(self, atendente):
        from edu.models import MatriculaDiario
        from edu.utils import validar_matricula_de_aluno_em_diario

        if self.diario is None:
            raise ValidationError('Este requerimento não possui diário associado.')

        validar_matricula_de_aluno_em_diario(self.aluno, self.diario)

        matricula_periodo = self.aluno.matriculaperiodo_set.get(ano_letivo=self.diario.ano_letivo, periodo_letivo=self.diario.periodo_letivo)
        if not MatriculaDiario.objects.filter(matricula_periodo=matricula_periodo, diario=self.diario).exists():
            matricula_diario = MatriculaDiario()
            matricula_diario.diario = self.diario
            matricula_diario.matricula_periodo = matricula_periodo
            matricula_diario.situacao = MatriculaDiario.SITUACAO_CURSANDO
            matricula_diario.save()
            if matricula_periodo.aluno.situacao.pk != SituacaoMatricula.MATRICULADO:
                matricula_periodo.aluno.situacao = SituacaoMatricula.objects.get(pk=SituacaoMatricula.MATRICULADO)
                matricula_periodo.aluno.save()
            if matricula_periodo.situacao != SituacaoMatriculaPeriodo.MATRICULADO:
                matricula_periodo.situacao = SituacaoMatriculaPeriodo.objects.get(pk=SituacaoMatriculaPeriodo.MATRICULADO)
                matricula_periodo.save()
        super().processar(atendente)

    def save(self, *args, **kwargs):
        self.tipo = Requerimento.MATRICULA_DISCIPLINA
        super().save()

    def get_detalhamento(self):
        return [('Diário', self.diario)]


class RequerimentoMatriculaQuebraRequisito(Requerimento):
    """
    Define o requerimento de matrícula com quebra de requisito, usado quando o aluno precisa cursar uma disciplina,
    mas não cumpriu os (co)pré-requisitos necessários.

    A implementação atual considera que os requerimentos serão gerados a partir de
    uma Renovação de Matrícula (`ConfiguracaoPedidoMatricula`) e estarão vinculados a ela por um `PedidoMatricula`.
    Portanto, assegure-se de usá-la em contextos em que o aluno possui uma Renovação de Matrícula ativa associada.

    O processamento deste requerimento gera um `PedidoMatriculaDiario`, o qual estará sujeito às regras de prioridade
    do processamento de matrícula (task `processar_pedidos_matricula`).

    Se o requerimento for indeferido, o aluno será impossibilitado de requerer novamente para o mesmo componente
    na mesma Renovação.
    """

    def processar(self, atendente):
        from edu.utils import validar_matricula_de_aluno_em_diario

        if self.diario is None:
            raise ValidationError('Este requerimento não possui diário associado.')

        validar_matricula_de_aluno_em_diario(self.aluno, self.diario, ignorar_quebra_requisito=True)

        matricula_periodo = self.aluno.matriculaperiodo_set.get(ano_letivo=self.diario.ano_letivo, periodo_letivo=self.diario.periodo_letivo)
        configuracao_pedido_matricula_ativa = self.aluno.get_configuracao_pedido_matricula_ativa()
        pedido_matricula = PedidoMatricula.objects.filter(
            matricula_periodo=matricula_periodo,
            configuracao_pedido_matricula=configuracao_pedido_matricula_ativa,
        ).first()

        if (
            configuracao_pedido_matricula_ativa is None
            or pedido_matricula is not None
            and not pedido_matricula.requerimentos_matricula_quebra_de_requisito.filter(pk=self.pk).exists()
        ):
            raise ValidationError(
                'A renovação de matrícula associada a este requerimento já foi encerrada. Não será possível fazer novos pedidos de matrícula.'
            )

        if pedido_matricula and self.aluno.matriz.estrutura.ch_maxima_disciplinas:
            ch_resultante = pedido_matricula.carga_horaria_total + self.diario.componente_curricular.componente.ch_hora_relogio

            if mask_ch_componente(ch_resultante) > self.aluno.matriz.estrutura.ch_maxima_disciplinas:
                raise ValidationError('A inclusão desta matrícula ultrapassa a carga horária máxima do aluno para o período.')

        if pedido_matricula is None:
            pedido_matricula = PedidoMatricula.objects.create(
                matricula_periodo=matricula_periodo, configuracao_pedido_matricula=configuracao_pedido_matricula_ativa
            )

        PedidoMatriculaDiario.objects.create(
            diario=self.diario,
            pedido_matricula=pedido_matricula,
        )

        super().processar(atendente)

    def save(self, *args, **kwargs):
        self.tipo = Requerimento.MATRICULA_QUEBRA_REQUISITO
        super().save()

    def get_detalhamento(self):
        detalhamento = super().get_detalhamento()
        detalhamento.append(('Diário', self.diario))

        pre_requisitos = self.diario.componente_curricular.pre_requisitos.exclude(componente_id__in=self.aluno.get_ids_componentes_cumpridos())
        co_requisitos = self.diario.componente_curricular.co_requisitos.exclude(componente_id__in=self.aluno.get_ids_componentes_cumpridos())
        if pre_requisitos.exists():
            detalhamento.append(('Pré-requisitos', '; '.join([str(pre_req) for pre_req in pre_requisitos.all()])))
        if co_requisitos.exists():
            detalhamento.append(('Co-requisitos', '; '.join([str(co_req) for co_req in co_requisitos.all()])))

        return detalhamento


class RequerimentoMatriculaComAumentoDeCH(Requerimento):
    """
    Define o requerimento de matrícula com aumento de carga horária, usado quando o aluno precisa cursar uma disciplina,
    mas sua inclusão ultrapassaria a carga horária máxima definida na sua matriz.

    A implementação atual considera que os requerimentos serão gerados a partir de
    uma Renovação de Matrícula (`ConfiguracaoPedidoMatricula`) e estarão vinculados a ela por um `PedidoMatricula`.
    Portanto, assegure-se de usá-la em contextos em que o aluno possui uma Renovação de Matrícula ativa associada.

    O processamento deste requerimento gera um `PedidoMatriculaDiario`, o qual estará sujeito às regras de prioridade
    do processamento de matrícula (task `processar_pedidos_matricula`).

    `PedidoMatriculaDiario`s gerados a partir deste tipo de requerimento são ignorados em futuras validações
    de carga horária máxima.

    Se o requerimento for indeferido, o aluno será impossibilitado de repetir o requerimento para o mesmo componente
    na mesma Renovação.
    """

    def processar(self, atendente):
        from edu.utils import validar_matricula_de_aluno_em_diario

        if self.diario is None:
            raise ValidationError('Este requerimento não possui diário associado.')

        validar_matricula_de_aluno_em_diario(self.aluno, self.diario)

        matricula_periodo = self.aluno.matriculaperiodo_set.get(ano_letivo=self.diario.ano_letivo, periodo_letivo=self.diario.periodo_letivo)
        configuracao_pedido_matricula_ativa = self.aluno.get_configuracao_pedido_matricula_ativa()
        pedido_matricula = PedidoMatricula.objects.filter(
            matricula_periodo=matricula_periodo,
            configuracao_pedido_matricula=configuracao_pedido_matricula_ativa,
        ).first()

        if configuracao_pedido_matricula_ativa is None or not pedido_matricula.requerimentos_matricula_com_aumento_ch.filter(pk=self.pk).exists():
            raise ValidationError(
                'A renovação de matrícula associada a este requerimento já foi encerrada. Não será possível fazer novos pedidos de matrícula.'
            )

        if pedido_matricula is None:
            pedido_matricula = PedidoMatricula.objects.create(
                matricula_periodo=matricula_periodo, configuracao_pedido_matricula=configuracao_pedido_matricula_ativa
            )

        PedidoMatriculaDiario.objects.create(
            diario=self.diario,
            pedido_matricula=pedido_matricula,
        )

        super().processar(atendente)

    def save(self, *args, **kwargs):
        self.tipo = Requerimento.MATRICULA_QUEBRA_CH_MAX
        super().save()

    def get_detalhamento(self):
        detalhamento = super().get_detalhamento()
        detalhamento.append(('Diário', self.diario))
        detalhamento.append(('Carga horária máxima permitida', f'{self.aluno.matriz.estrutura.ch_maxima_disciplinas or 0}h'))

        ch_total = self.pedido_matricula.carga_horaria_total if self.pedido_matricula else 0
        detalhamento.append(
            (
                'Carga horária após inclusão da disciplina',
                f'{ch_total + self.diario.componente_curricular.componente.get_ch_hora_relogio()}h',
            )
        )

        return detalhamento

    @property
    def pedido_matricula(self):
        return self.pedidomatricula_set.last()


class AproveitamentoComponente(LogModel):
    class Meta:
        verbose_name = 'Aproveitamento de Componente'
        verbose_name_plural = 'Aproveitamentos de Componente'

    matricula_periodo = models.ForeignKeyPlus('edu.MatriculaPeriodo')
    componente_curricular = models.ForeignKeyPlus('edu.ComponenteCurricular')

    matriculas_diario_resumidas = models.ManyToManyFieldPlus('edu.MatriculaDiarioResumida', related_name='equivalencias_set')
    matriculas_diario = models.ManyToManyFieldPlus('edu.MatriculaDiario', related_name='equivalencias_set')
    registros_historico = models.ManyToManyFieldPlus('edu.RegistroHistorico', related_name='equivalencias_set')
    aproveitamentos_estudo = models.ManyToManyFieldPlus('edu.AproveitamentoEstudo', related_name='equivalencias_set')

    equivalencia_componente = models.ForeignKeyPlus('edu.EquivalenciaComponente', null=True)

    def __str__(self):
        return f'Aproveitamento de Componente #{self.id}'

    def get_observacao_historico(self):
        disciplinas_equivalentes = []
        for matricula_diario_resumida in self.matriculas_diario_resumidas.all():
            disciplinas_equivalentes.append(f'{matricula_diario_resumida.equivalencia_componente}')
        for matricula_diario in self.matriculas_diario.all():
            disciplinas_equivalentes.append(f'{matricula_diario.diario.componente_curricular.componente}')
        for registro_historico in self.registros_historico.all():
            disciplinas_equivalentes.append(f'{registro_historico.componente}')
        sufixo = len(disciplinas_equivalentes) > 1 and 's' or ''
        return 'A disciplina {} - {} ({}H) do projeto do curso foi cursada pela{} disciplina{} equivalente{}: {}'.format(
            self.componente_curricular.componente.sigla,
            self.componente_curricular.componente.descricao_historico,
            self.componente_curricular.componente.get_ch_hora_relogio(),
            sufixo,
            sufixo,
            sufixo,
            ', '.join(disciplinas_equivalentes),
        )


class MedidaDisciplinar(LogModel):
    aluno = models.ForeignKeyPlus('edu.Aluno', null=False, blank=False)
    tipo = models.ForeignKeyPlus('edu.TipoMedidaDisciplinar', null=False, blank=False)
    data_inicio = models.DateFieldPlus(verbose_name='Data de Início', null=False, blank=False)
    data_fim = models.DateFieldPlus(verbose_name='Data de Fim', null=True, blank=True)
    observacao = models.TextField(verbose_name='Observação', null=True, blank=True)

    class Meta:
        verbose_name = 'Medida Disciplinar'
        verbose_name_plural = 'Medidas Disciplinares'

    def __str__(self):
        return f'Medida Disciplinar #{self.id} - {self.aluno}'

    def can_delete(self, user=None):
        if user is None:
            user = tl.get_user()
        if not self.aluno.is_cancelado():
            if user.has_group_cached('Administrador Acadêmico'):
                return True
            elif get_uo():
                return user.has_group_cached('Secretário Acadêmico') and self.aluno.curso_campus.diretoria.setor.uo == get_uo()
        return False


class Premiacao(LogModel):
    aluno = models.ForeignKeyPlus('edu.Aluno', null=False, blank=False)
    tipo = models.ForeignKeyPlus('edu.TipoPremiacao', null=False, blank=False)
    data = models.DateFieldPlus(verbose_name='Data', null=False, blank=False)
    observacao = models.TextField(verbose_name='Observação', null=True, blank=True)

    class Meta:
        verbose_name = 'Premiação'
        verbose_name_plural = 'Premiações'

    def __str__(self):
        return f'Premiação #{self.id} - {self.aluno}'


class ProcedimentoReducaoCH(LogModel):
    NOVO_INGRESSO = '1'
    MUDANCA_MATRIZ = '2'
    ATIVIDADE_COMPLEMENTAR = '3'
    ATIVIDADE_APROFUNDAMENTO = '4'
    PRATICA_PROFISSIONAL = '5'

    TIPO_PROCEDIMENTO_CHOICES = [
        (NOVO_INGRESSO, 'Novo ingresso em mesmo curso'),
        (MUDANCA_MATRIZ, 'Mudança de matriz curricular'),
        (ATIVIDADE_COMPLEMENTAR, 'Alteração de atividade complementar'),
        (ATIVIDADE_APROFUNDAMENTO, 'Alteração de atividade de aprofundamento'),
        (PRATICA_PROFISSIONAL, 'Alteração de prática profissional'),
    ]

    matricula_periodo = models.ForeignKeyPlus('edu.MatriculaPeriodo', null=False, blank=False)
    tipo_procedimento = models.CharFieldPlus(choices=TIPO_PROCEDIMENTO_CHOICES)
    motivo = models.TextField(verbose_name='Motivo', null=False, blank=False)
    informacao_complementar = models.TextField(verbose_name='Informações complementares', null=False, blank=False)
    data = models.DateTimeFieldPlus(verbose_name='Data do procedimento', auto_now_add=True)
    vinculo = models.ForeignKeyPlus(
        'comum.Vinculo',
        verbose_name='Vínculo',
        null=False,
        blank=False,
        help_text='Vínculo do usuário que realizou o procedimento.',
    )
    ch_anterior = models.PositiveIntegerField(
        verbose_name='Carga horária anterior',
        null=False,
        blank=False,
        help_text='Carga horária do curso antes do procedimento.',
    )
    ch_nova = models.PositiveIntegerField(
        verbose_name='Carga horária nova',
        null=False,
        blank=False,
        help_text='Carga horária do curso após o procedimento.',
    )

    class Meta:
        verbose_name = 'Procedimento com redução de carga horária integralizada'
        verbose_name_plural = 'Procedimentos com redução de carga horária integralizada'
