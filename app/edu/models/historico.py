from __future__ import annotations

from collections.abc import Iterable
import copy
import datetime
from decimal import Decimal

from django.apps import apps
from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F, Q
from django.db.models.aggregates import Avg, Max, Sum
from django.db.models.functions import Coalesce

from comum.models import Ano, Configuracao
from comum.utils import tl
from djtools.db import models
from djtools.templatetags.filters.utils import format_iterable
from djtools.utils import mask_nota, nota_to_float, send_notification, mask_ch_componente
from edu import perms
from edu import managers
from edu.models.cadastros_gerais import Modalidade, NivelEnsino, SituacaoMatriculaPeriodo
from edu.models.logs import LogModel
from edu.models.procedimentos import ProcedimentoMatricula


class MatriculaPeriodoManager(models.Manager):
    def com_fechamento_pendente(self, ano_letivo, periodo_letivo, diretorias=()):
        from edu.models.diretorias import CalendarioAcademico

        calendarios = CalendarioAcademico.objects.filter(
            data_fechamento_periodo__lt=datetime.datetime.now(), ano_letivo_id=ano_letivo.id, periodo_letivo=periodo_letivo
        )
        if diretorias:
            calendarios = calendarios.filter(diretoria__in=diretorias)
        turmas_ids = list(calendarios.distinct().values_list('turma__id', flat=True))

        pks = MatriculaPeriodo.objects.filter(
            ano_letivo_id=ano_letivo.id,
            periodo_letivo=periodo_letivo,
            situacao=SituacaoMatriculaPeriodo.MATRICULADO,
            matriculadiario__diario__turma_id__in=turmas_ids,
        ).values_list('pk', flat=True)

        return MatriculaPeriodo.objects.filter(pk__in=pks)


class MatriculaPeriodo(LogModel):
    SEARCH_FIELDS = ['aluno__pessoa_fisica__nome_registro', 'aluno__pessoa_fisica__nome_social', 'aluno__matricula']
    SITUACAO_PEDEMEIA_EM_ANDAMENTO = 0
    SITUACAO_PEDEMEIA_CHOICES = [
        [0, 'Em andamento'],
        [1, 'Informação incorreta'],
        [2, 'Transferência para outra unidade escolar dentro da mesma rede'],
        [3, 'Transferência para outra unidade escolar em outra rede pública'],
        [4, 'Transferência para outra unidade escolar em outra rede privada'],
        [5, 'Transferência para outra rede não identificada'],
        [6, 'Evasão'],
        [7, 'Abandono'],
        [8, 'Óbito informado'],
        [9, 'Reclassificação'],
        [10, 'Aprovado'],
        [11, 'Concluinte'],
        [12, 'Reprovado'],
        [13, 'Conclusão confirmada'],
        [19, 'Concluinte Encceja + 400h'],
        [20, 'Confirmação de Conclusão Encceja + 400h'],
        [21, 'Transferência entre modalidades de ensino'],
        [22, 'Trancamento de matrícula em curso técnico'],
        [25, 'Concluinte EMR / EJA com programa e/ou prova estadual de aceleração'],
        [26, 'Conclusão Confirmada EMR / EJA com programa e/ou prova estadual de aceleração'],
        [27, 'Concluinte EMR / EJA com ENEM'],
        [28, 'Conclusão Confirmada EMR / EJA com ENEM'],
        [29, 'Concluinte EMR / EJA com ENCCEJA'],
        [30, 'Conclusão Confirmada EMR / EJA com ENCCEJA'],
    ]

    aluno = models.ForeignKeyPlus('edu.Aluno')
    ano_letivo = models.ForeignKeyPlus('comum.Ano', verbose_name='Ano Letivo', on_delete=models.CASCADE)
    periodo_letivo = models.PositiveIntegerField('Período Letivo', db_index=True)
    periodo_matriz = models.PositiveIntegerField('Período Matriz', null=True)
    turma = models.ForeignKeyPlus('edu.Turma', null=True, on_delete=models.SET_NULL)
    situacao = models.ForeignKeyPlus('edu.SituacaoMatriculaPeriodo', verbose_name='Situação', on_delete=models.CASCADE)
    excluida = models.BooleanField('Excluída do Q-Acadêmico', default=False)
    codigo_turma_qacademico = models.CharField('Código da Turma do Q-Acadêmico', max_length=255, null=True)
    cursou_acc_qacademico = models.BooleanField(verbose_name='Curso Atividade Complementar no Q-Acadêmico', default=False)
    gerada_suap = models.BooleanField('Matrícula-Período Gerada pelo SUAP', default=False)
    codigo_educacenso = models.CharFieldPlus('Código EDUCACENSO', null=True, blank=True)
    codigo_sgp = models.IntegerField(null=True, db_index=True, blank=True)
    percentual_ch_cumprida = models.DecimalFieldPlus('C.H. Cumprida (%)', null=True)
    periodo_integralizado_ensino_medio = models.BooleanField(verbose_name='Período integralizado para Ensino Médio', default=False)

    data_matricula_periodo = models.DateFieldPlus(verbose_name='Data da Matrícula no Período', null=True, blank=True)
    data_situacao_periodo = models.DateFieldPlus(verbose_name='Data da Situação no Período', null=True, blank=True)
    calendario_academico = models.ForeignKeyPlus('edu.CalendarioAcademico', verbose_name='Calendário Acadêmico', null=True, blank=True)
    situacao_pedemeia = models.IntegerField(verbose_name='Situação Pé-de-Meia', null=True, blank=True, choices=SITUACAO_PEDEMEIA_CHOICES)

    objects = MatriculaPeriodoManager()

    class Meta:
        ordering = ('ano_letivo__ano', 'periodo_letivo')
        verbose_name = 'Matrícula em Período'
        verbose_name_plural = 'Matrículas em Período'
        unique_together = (('ano_letivo', 'periodo_letivo', 'aluno'),)

    def __str__(self):
        return f'{self.aluno!s} - {self.periodo_matriz}º Período ({self.ano_letivo.ano}.{self.periodo_letivo})'

    def get_ira(self):
        if self.situacao.pk == SituacaoMatriculaPeriodo.MATRICULADO:
            return '-'
        return mask_nota(self.aluno.calcular_indice_rendimento(matriculaperiodo=self))

    def em_horario_de_aula(self, dia_semana, hora='00:00'):
        from edu.models import HorarioAulaDiario

        for horario in HorarioAulaDiario.objects.filter(diario__matriculadiario__matricula_periodo=self, dia_semana=dia_semana):
            if horario.engloba_hora(hora):
                return True
        return False

    def get_horarios_com_choque(self):
        from edu.models import HorarioAulaDiario

        qs_horarios_aula_diario = HorarioAulaDiario.objects.filter(
            diario__matriculadiario__matricula_periodo=self, diario__matriculadiario__situacao=MatriculaDiario.SITUACAO_CURSANDO
        ).distinct()
        horarios_choque = {}
        for horario_aula_diario in qs_horarios_aula_diario:
            qs_horarios_choque = qs_horarios_aula_diario.filter(
                dia_semana=horario_aula_diario.dia_semana, horario_aula=horario_aula_diario.horario_aula
            )
            qs_horarios_choque = qs_horarios_choque.exclude(id=horario_aula_diario.id)
            ids_horarios_ja_inseridos = [x.id for x in list(horarios_choque.keys())]
            qs_horarios_choque = qs_horarios_choque.exclude(id__in=ids_horarios_ja_inseridos)
            if qs_horarios_choque.exists():
                horarios_choque.update({horario_aula_diario: qs_horarios_choque})
        return horarios_choque

    def get_matricula_periodo_subsequente(self):
        from edu.models import CursoCampus

        if self.aluno.curso_campus.periodicidade == CursoCampus.PERIODICIDADE_ANUAL:
            ano_letivo = Ano.objects.get_or_create(ano=self.ano_letivo.ano + 1)[0]
            periodo_letivo = self.periodo_letivo
        else:
            if self.periodo_letivo == 2:
                ano_letivo = Ano.objects.get_or_create(ano=self.ano_letivo.ano + 1)[0]
                periodo_letivo = 1
            else:
                ano_letivo = self.ano_letivo
                periodo_letivo = 2
        return self.aluno.matriculaperiodo_set.filter(ano_letivo=ano_letivo, periodo_letivo=periodo_letivo).first()

    def get_estatisticas_boletim(self, etapa):
        from edu.models.diarios import ConfiguracaoAvaliacao

        series = []
        for matricula_diario in self.matriculadiario_set.all():
            nota_aluno = 0
            media_turma = 0
            adicionar = True
            if etapa > 5:
                if (
                    ConfiguracaoAvaliacao.objects.filter(diario=matricula_diario.diario, autopublicar=False).exists()
                    and not matricula_diario.diario.em_posse_do_registro()
                ):
                    adicionar = False
            else:
                configuracao_avaliacao = getattr(matricula_diario.diario, f'configuracao_avaliacao_{etapa > 4 and 5 or etapa}')()
                if configuracao_avaliacao and not configuracao_avaliacao.autopublicar and not matricula_diario.diario.em_posse_do_registro(etapa):
                    adicionar = False

            if adicionar:
                if etapa == 6:
                    nota_aluno = nota_to_float(matricula_diario.get_media_disciplina())
                    media_turma = nota_to_float(matricula_diario.diario.get_media_medias())
                elif etapa == 7:
                    nota_aluno = nota_to_float(matricula_diario.get_media_final_disciplina())
                    media_turma = nota_to_float(matricula_diario.diario.get_media_medias_finais())
                else:
                    nota_aluno = nota_to_float(matricula_diario.get_nota_by_etapa(etapa))
                    media_turma = nota_to_float(matricula_diario.diario.get_media_notas_by_etapa(etapa))

            series.append([matricula_diario.diario.componente_curricular.componente.descricao, nota_aluno, media_turma])
        return series

    def adicionar_registro_historico(self, matricula_periodo):
        for matricula_diario in self.matriculadiario_set.filter(situacao__in=[MatriculaDiario.SITUACAO_APROVADO]):
            matricula_diario.adicionar_registro_historico(matricula_periodo)

        situacoes_clonar_matriculadiario_resumida = [
            MatriculaDiario.SITUACAO_APROVADO,
            MatriculaDiario.SITUACAO_CERTIFICACAO_CONHECIMENTO,
            MatriculaDiario.SITUACAO_APROVEITAMENTO_ESTUDO,
        ]
        for matricula_diario_resumida in self.matriculadiarioresumida_set.filter(situacao__in=situacoes_clonar_matriculadiario_resumida):
            matricula_diario_resumida.clonar(matricula_periodo)

        for aproveitamento_estudo in self.aproveitamentoestudo_set.all():
            aproveitamento_estudo.adicionar_registro_historico(matricula_periodo)

        for certificacao_conhecimento in self.certificacaoconhecimento_set.all():
            certificacao_conhecimento.adicionar_registro_historico(matricula_periodo)

        for registro_historico in self.registrohistorico_set.all():
            registro_historico.adicionar_registro_historico(matricula_periodo)

    def adicionar_atividades_pratica_profissional(self, matricula_periodo):
        from edu.models import AtividadePraticaProfissional

        mesmo_curso = matricula_periodo.aluno.curso_campus.codigo_sistec == self.aluno.curso_campus.codigo_sistec
        qs = self.atividadepraticaprofissional_set.all()
        if not mesmo_curso:
            qs = qs.exclude(situacao=AtividadePraticaProfissional.INDEFERIDA)
        for atividade in qs:
            nova_atividade = copy.copy(atividade)
            nova_atividade.id = None
            nova_atividade.pk = None
            nova_atividade.matricula_periodo = matricula_periodo
            if not mesmo_curso and atividade.situacao in [AtividadePraticaProfissional.CONCLUIDA, AtividadePraticaProfissional.DESCONSIDERADA]:
                nova_atividade.situacao = AtividadePraticaProfissional.AGUARDANDO_REAVALIACAO
            nova_atividade.save()

    def get_codigo_turma(self):
        return self.turma and self.turma.codigo or self.codigo_turma_qacademico

    def get_numero_certificacoes(self):
        from edu.models import CertificacaoConhecimento

        return CertificacaoConhecimento.objects.filter(matricula_periodo=self).count()

    def excluir_proxima_matricula_periodo(self, somente_em_aberto=True):
        if self.aluno.matriculaperiodo_set.filter(id__gt=self.pk).count() == 1:
            if somente_em_aberto:
                qs = self.aluno.matriculaperiodo_set.filter(id__gt=self.pk, situacao=SituacaoMatriculaPeriodo.EM_ABERTO)
            else:
                qs = self.aluno.matriculaperiodo_set.filter(id__gt=self.pk)
            # não excluir caso haja alguma informação relacionada
            for mp in qs:
                if not mp.possui_dados_relacionados():
                    mp.delete()

    def possui_dados_relacionados(self):
        if self.projetofinal_set.exists():
            return True
        if self.pedidomatricula_set.exists():
            return True
        if self.procedimentomatricula_set.exists():
            return True
        if self.matriculadiario_set.exists():
            return True
        if self.certificacaoconhecimento_set.exists():
            return True
        return bool(self.aproveitamentoestudo_set.exists())

    def instanciar_proxima_matricula_periodo(self):
        from edu.models import CursoCampus

        if self.aluno.curso_campus.periodicidade == CursoCampus.PERIODICIDADE_ANUAL:
            ano_letivo = Ano.objects.get_or_create(ano=self.ano_letivo.ano + 1)[0]
            periodo_letivo = self.periodo_letivo
        else:
            if self.periodo_letivo == 2:
                ano_letivo = Ano.objects.get_or_create(ano=self.ano_letivo.ano + 1)[0]
                periodo_letivo = 1
            else:
                ano_letivo = self.ano_letivo
                periodo_letivo = 2

        matricula_periodo = MatriculaPeriodo.objects.filter(aluno=self.aluno, ano_letivo=ano_letivo, periodo_letivo=periodo_letivo).first()
        if matricula_periodo is None:
            matricula_periodo = MatriculaPeriodo()
            matricula_periodo.aluno = self.aluno
            matricula_periodo.ano_letivo = ano_letivo
            matricula_periodo.periodo_letivo = periodo_letivo
            matricula_periodo.situacao = SituacaoMatriculaPeriodo.objects.get(pk=SituacaoMatriculaPeriodo.EM_ABERTO)
            matricula_periodo.turma = None

        matricula_periodo.periodo_matriz = self.get_proximo_periodo_matriz(self.periodo_matriz)
        matricula_periodo.save()

    def get_proximo_periodo_matriz(self, periodo_atual):
        if self.situacao_id in [SituacaoMatriculaPeriodo.APROVADO, SituacaoMatriculaPeriodo.DEPENDENCIA, SituacaoMatriculaPeriodo.PERIODO_FECHADO]:
            return self.calcular_periodo_matriz(periodo_atual)
        return periodo_atual

    def calcular_periodo_matriz(self, periodo_matriz):
        from edu.models import EstruturaCurso

        if (
            self.aluno.is_credito()
            or self.matriculadiario_set.filter(situacao=MatriculaDiario.SITUACAO_APROVADO).exists()
            or self.registrohistorico_set.filter(situacao=MatriculaDiario.SITUACAO_APROVADO).exists()
        ):
            periodo_matriz += 1
        if periodo_matriz > self.aluno.matriz.qtd_periodos_letivos and self.aluno.matriz.estrutura.tipo_avaliacao in [
            EstruturaCurso.TIPO_AVALIACAO_SERIADO,
            EstruturaCurso.TIPO_AVALIACAO_MODULAR,
        ]:
            periodo_matriz = self.aluno.matriz.qtd_periodos_letivos
        return periodo_matriz

    def qtd_reprovacoes(self, modulo=None):
        ids_situacoes = (MatriculaDiario.SITUACAO_REPROVADO, MatriculaDiario.SITUACAO_REPROVADO_POR_FALTA)
        qs = self.matriculadiario_set.filter(situacao__in=ids_situacoes, matricula_periodo=self)
        if modulo:
            qs = qs.filter(diario__componente_curricular__tipo_modulo=modulo)
        return qs.count()

    def is_cancelado(self):
        from edu.models import SituacaoMatricula

        return self.aluno.situacao.pk in (
            SituacaoMatricula.CANCELADO,
            SituacaoMatricula.CANCELAMENTO_COMPULSORIO,
            SituacaoMatricula.CANCELAMENTO_POR_DUPLICIDADE,
            SituacaoMatricula.CANCELAMENTO_POR_DESLIGAMENTO,
            SituacaoMatricula.EVASAO,
            SituacaoMatricula.TRANSFERIDO_EXTERNO,
            SituacaoMatricula.JUBILADO,
        )

    def is_matriculado(self):
        return self.aluno.is_matriculado()

    def is_matricula_vinculo(self):
        return self.situacao.pk == SituacaoMatriculaPeriodo.MATRICULA_VINCULO_INSTITUCIONAL

    def is_ativo(self):
        from edu.models import SituacaoMatricula

        return self.aluno.situacao.pk == SituacaoMatricula.MATRICULADO or self.aluno.situacao.pk == SituacaoMatricula.CONCLUDENTE

    def is_aberto(self):
        return self.situacao_id == SituacaoMatriculaPeriodo.EM_ABERTO

    def pode_remover_da_turma(self, user):
        from edu.models import SituacaoMatricula

        SITUACOES_MATRICULA_PERIODO_PARA_EXCLUSAO = [SituacaoMatriculaPeriodo.MATRICULADO, SituacaoMatriculaPeriodo.EM_ABERTO]
        SITUACOES_MATRICULA_PARA_EXCLUSAO = [SituacaoMatricula.MATRICULADO]
        if user.has_perm('edu.delete_matriculadiario_cancelada_trancada'):
            SITUACOES_MATRICULA_PERIODO_PARA_EXCLUSAO.extend(SituacaoMatriculaPeriodo.SITUACOES_INATIVAS_PARA_EXCLUSAO_DIARIO)
            SITUACOES_MATRICULA_PARA_EXCLUSAO.extend(SituacaoMatricula.SITUACOES_INATIVAS_PARA_EXCLUSAO_TURMA)
        result = self.aluno.situacao.pk in SITUACOES_MATRICULA_PARA_EXCLUSAO and self.situacao.pk in SITUACOES_MATRICULA_PERIODO_PARA_EXCLUSAO
        if result:
            result = (
                user.has_group('Administrador Acadêmico')
                or user.is_superuser
                or not self.possui_nota_lancada_na_turma()
                and not self.possui_falta_lancada_na_turma()
            )
        return result

    def pode_matricular_diario(self):
        return (self.aluno.iniciou_suap() or self.aluno.integralizou_suap()) and self.situacao.pk in [
            SituacaoMatriculaPeriodo.MATRICULADO,
            SituacaoMatriculaPeriodo.EM_ABERTO,
        ]

    def pode_realizar_procedimento_matricula(self):
        return self.is_matriculado() or self.is_matricula_vinculo() or self.is_aberto()

    def pode_integralizar_fase_escolar(self):
        from edu.models.arquivos import TipoAlunoArquivo

        is_tecnico_integrado = self.aluno.curso_campus.modalidade_id in (Modalidade.INTEGRADO, Modalidade.INTEGRADO_EJA, Modalidade.FIC_INTEGRADO_EJA)
        # aluno SUAP
        if self.aluno.matriz_id:
            possui_pendencia = self.aluno.comp_obrigatorios_pendentes or self.aluno.comp_optativos_pendentes or self.aluno.seminarios_pendentes
            pode_realizar_procedimento = self.pode_realizar_procedimento_matricula()
        else:
            # aluno Q-Acadêmico
            possui_pendencia = False
            pode_realizar_procedimento = True
        hoje = datetime.datetime.now().date()
        pode_integralizar = (
            is_tecnico_integrado
            and pode_realizar_procedimento
            and self.aluno.alunoarquivo_set.filter(
                tipo__nome=TipoAlunoArquivo.COMPROVANTE_APROVACAO_PROCESSO_SELETIVO, validado=True, data_expiracao__gte=hoje
            ).exists()
            and not possui_pendencia
        )
        return pode_integralizar

    def pode_realizar_transferencia(self):
        from edu.models import SituacaoMatricula

        situacao_matricula = self.aluno.situacao.ativo or self.aluno.situacao.pk in [
            SituacaoMatricula.TRANCADO,
            SituacaoMatricula.TRANCADO_VOLUNTARIAMENTE,
        ]
        situacao_periodo = self.situacao.id in [
            SituacaoMatriculaPeriodo.MATRICULADO,
            SituacaoMatriculaPeriodo.EM_ABERTO,
            SituacaoMatriculaPeriodo.MATRICULA_VINCULO_INSTITUCIONAL,
        ]
        return situacao_matricula and situacao_periodo

    @transaction.atomic
    def realizar_procedimento_matricula(self, procedimento, situacao_matricula, situacao_matricula_periodo, situacao_matricula_diario):
        if (
            self.aluno.matriz_id
            and self.aluno.matriz.is_regime_modular()
            and procedimento.tipo
            in [
                ProcedimentoMatricula.TRANCAMENTO_COMPULSORIO,
                ProcedimentoMatricula.TRANCAMENTO_VOLUNTARIO,
            ]
        ):
            # plano de retomada de aulas em virtude da pandemia (COVID19)
            if not self.matriculadiario_set.filter(diario__turma__pertence_ao_plano_retomada=True).exists():
                raise ValidationError('Não é possível realizar o trancamento de um aluno do regime modular.')

        mps = MatriculaPeriodo.objects.filter(
            aluno=self.aluno, situacao__id__in=[SituacaoMatriculaPeriodo.EM_ABERTO, SituacaoMatriculaPeriodo.MATRICULADO]
        ).exclude(pk=self.pk)
        if mps.exists():
            raise ValidationError('É necessário fechar os períodos anteriores antes de realizar o procedimento.')

        procedimento.save()
        self.aluno.situacao = situacao_matricula
        self.aluno.save()
        self.situacao = situacao_matricula_periodo
        self.save()
        self.matriculadiario_set.filter(situacao=MatriculaDiario.SITUACAO_CURSANDO).update(situacao=situacao_matricula_diario)

        if procedimento.tipo in ProcedimentoMatricula.TIPOS_CANCELAMENTO_VINCULO:
            self.indeferir_requerimentos_automatizados_pendentes(procedimento)

        if self.aluno.candidato_vaga_id:
            from processo_seletivo.models import CandidatoVaga

            if procedimento.tipo in (
                ProcedimentoMatricula.CANCELAMENTO_COMPULSORIO,
                ProcedimentoMatricula.CANCELAMENTO_VOLUNTARIO,
                ProcedimentoMatricula.CANCELAMENTO_POR_DESLIGAMENTO,
                ProcedimentoMatricula.CANCELAMENTO_POR_DUPLICIDADE,
            ):
                self.aluno.candidato_vaga.situacao = CandidatoVaga.MATRICULA_CANCELADA
            if procedimento.tipo in (
                ProcedimentoMatricula.TRANSFERENCIA_EXTERNA,
                ProcedimentoMatricula.TRANSFERENCIA_INTERCAMPUS,
                ProcedimentoMatricula.TRANSFERENCIA_CURSO,
            ):
                self.aluno.candidato_vaga.situacao = CandidatoVaga.TRANSFERIDO
            if procedimento.tipo == ProcedimentoMatricula.EVASAO:
                self.aluno.candidato_vaga.situacao = CandidatoVaga.EVADIDO
            # alterar a situação do candidato apenas se o procedimento estiver sendo realizado no período de ingresso
            if self.id == self.aluno.matriculaperiodo_set.order_by('id').values_list('id', flat=True).first():
                self.aluno.candidato_vaga.save()

    def indeferir_requerimentos_automatizados_pendentes(
        self,
        procedimento: ProcedimentoMatricula,
        notificar: bool = True,
    ) -> None:
        from edu.models.procedimentos import Requerimento

        tipos_ignorados = (
            Requerimento.MATRICULA_QUEBRA_REQUISITO,
            Requerimento.MATRICULA_QUEBRA_CH_MAX,
        )
        tipos_alvo = [choice[0] for choice in Requerimento.TIPO_AUTOMATIZADO_CHOICES if choice[0] not in tipos_ignorados]

        requerimentos_pendentes = Requerimento.objects.filter(
            aluno_id=self.aluno.id,
            tipo__in=tipos_alvo,
            deferido__isnull=True,
        ).exclude(situacao=Requerimento.SITUACAO_ARQUIVADO)

        observacao = (
            f'Requerimento indeferido automaticamente devido ao procedimento de {procedimento.tipo} ({self.ano_letivo}.{self.periodo_letivo}).'
        )

        for requerimento in requerimentos_pendentes:
            requerimento.observacao = observacao
            requerimento.indeferir(notificar=notificar)

    @transaction.atomic
    def reintegrar_aluno(self, procedimento, ano_letivo, periodo_letivo):
        aluno = self.aluno
        aluno.situacao = aluno.get_ultimo_procedimento_matricula().situacao_matricula_anterior
        aluno.save()

        matricula_periodo = MatriculaPeriodo()
        matricula_periodo.aluno = aluno
        matricula_periodo.ano_letivo = ano_letivo
        matricula_periodo.periodo_letivo = periodo_letivo
        matricula_periodo.periodo_matriz = aluno.periodo_atual or 1
        matricula_periodo.turma = None
        matricula_periodo.situacao = SituacaoMatriculaPeriodo.objects.get(pk=SituacaoMatriculaPeriodo.EM_ABERTO)
        matricula_periodo.save()

        procedimento.matricula_periodo = matricula_periodo
        procedimento.save()

    def get_matriculas_diario(self, incluir_matriculas_diario_resumidas=False):
        qs_matriculas_diario = self.matriculadiario_set.all().order_by('diario__componente_curricular__componente__descricao_historico')
        if incluir_matriculas_diario_resumidas:
            return list(qs_matriculas_diario) + list(self.get_matriculas_diario_resumidas())
        else:
            return qs_matriculas_diario

    def get_matriculas_diario_resumidas(self):
        return self.matriculadiarioresumida_set.all()

    def get_matriculas_diario_ativas(self, modulo=None):
        ids = []
        ids.append(MatriculaDiario.SITUACAO_TRANCADO)
        ids.append(MatriculaDiario.SITUACAO_CANCELADO)
        ids.append(MatriculaDiario.SITUACAO_DISPENSADO)
        ids.append(MatriculaDiario.SITUACAO_TRANSFERIDO)
        qs = self.matriculadiario_set.select_related('diario__componente_curricular__componente_curricular_associado').exclude(situacao__in=ids)
        if modulo:
            qs = qs.filter(diario__componente_curricular__tipo_modulo=modulo)
        return qs

    def possui_nota_lancada_na_turma(self):
        return self.possui_nota_lancada(self.turma)

    def possui_nota_lancada(self, turma=None):
        qs = self.matriculadiario_set.exclude(situacao=MatriculaDiario.SITUACAO_TRANSFERIDO)
        if turma:
            qs = qs.filter(diario__turma=turma)

        qs1 = qs.filter(nota_1__isnull=False)
        qs2 = qs.filter(nota_2__isnull=False)
        qs3 = qs.filter(nota_3__isnull=False)
        qs4 = qs.filter(nota_4__isnull=False)
        qs5 = qs.filter(nota_final__isnull=False)
        return qs1.exists() or qs2.exists() or qs3.exists() or qs4.exists() or qs5.exists()

    def possui_falta_lancada_na_turma(self):
        return self.possui_falta_lancada(self.turma)

    def possui_falta_lancada(self, turma=None):
        from edu.models.diarios import Falta

        qs = Falta.objects.exclude(matricula_diario__situacao=MatriculaDiario.SITUACAO_TRANSFERIDO).filter(matricula_diario__matricula_periodo=self)
        if turma:
            qs = qs.filter(matricula_diario__diario__turma=turma)
        return qs.exists()

    def get_aluno(self):
        return self.aluno

    def get_media_na_etapa(self, etapa):
        avg = 'nota_{}'.format(etapa == 5 and 'final' or etapa)
        return self.matriculadiario_set.all().aggregate(Avg(avg))[f'{avg}__avg']

    def get_media_na_primeira_etapa(self):
        return self.get_media_na_etapa(1)

    def get_media_na_segunda_etapa(self):
        return self.get_media_na_etapa(2)

    def get_media_na_terceira_etapa(self):
        return self.get_media_na_etapa(3)

    def get_media_na_quarta_etapa(self):
        return self.get_media_na_etapa(4)

    def get_media_na_etapa_final(self):
        return self.get_media_na_etapa(5)

    def get_media_final_periodo(self):
        total = count = 0
        for md in self.matriculadiario_set.all().iterator():
            media = md.get_media_final_disciplina()
            if media is not None:
                total += media
                count += 1

        for mdr in self.get_matriculas_diario_resumidas().iterator():
            media = mdr.get_media_final_disciplina()
            if media is not None:
                total += media
                count += 1

        media_final = total / count if count else 0
        return mask_nota(media_final)

    def get_calendario_academico(self):
        if self.turma:
            return self.turma.get_calendario_academico()
        elif self.matriculadiario_set.exists():
            return self.matriculadiario_set.all()[0].diario.turma.get_calendario_academico()
        return None

    def get_situacao_periodo(self):
        if self.situacao.pk == SituacaoMatriculaPeriodo.MATRICULADO:
            return {'rotulo': self.situacao.descricao, 'status': 'info', 'constant': SituacaoMatriculaPeriodo.MATRICULADO}
        elif self.situacao.pk == SituacaoMatriculaPeriodo.APROVADO:
            return {'rotulo': self.situacao.descricao, 'status': 'success', 'constant': SituacaoMatriculaPeriodo.APROVADO}
        elif self.situacao.pk == SituacaoMatriculaPeriodo.REPROVADO:
            return {'rotulo': self.situacao.descricao, 'status': 'error', 'constant': SituacaoMatriculaPeriodo.REPROVADO}
        elif self.situacao.pk == SituacaoMatriculaPeriodo.REPROVADO_POR_FALTA:
            return {'rotulo': self.situacao.descricao, 'status': 'info', 'constant': SituacaoMatriculaPeriodo.REPROVADO_POR_FALTA}

    def get_carga_horaria(self):
        situacoes_inativas = [
            MatriculaDiario.SITUACAO_CANCELADO,
            MatriculaDiario.SITUACAO_DISPENSADO,
            MatriculaDiario.SITUACAO_TRANCADO,
            MatriculaDiario.SITUACAO_TRANSFERIDO,
        ]
        qs = self.get_matriculas_diario().exclude(situacao__in=situacoes_inativas)
        aulas = qs.aggregate(quantidade=Sum('diario__componente_curricular__componente__ch_hora_aula')).get('quantidade') or 0
        if settings.COMPONENTE_CH_DECIMAL:
            aulas = round(aulas / 100)
        return aulas

    def get_carga_horaria_cumprida(self):
        from edu.models.diarios import Aula

        situacoes_inativas = [
            MatriculaDiario.SITUACAO_CANCELADO,
            MatriculaDiario.SITUACAO_DISPENSADO,
            MatriculaDiario.SITUACAO_TRANCADO,
            MatriculaDiario.SITUACAO_TRANSFERIDO,
        ]
        qs = Aula.objects.filter(
            professor_diario__diario__matriculadiario__in=self.matriculadiario_set.exclude(situacao__in=situacoes_inativas).values_list(
                'pk', flat=True
            ),
            data__lte=datetime.date.today(),
        )
        return qs.aggregate(Sum('quantidade')).get('quantidade__sum') or 0

    def get_total_faltas(self):
        from edu.models.diarios import Falta

        situacoes_inativas = [
            MatriculaDiario.SITUACAO_CANCELADO,
            MatriculaDiario.SITUACAO_DISPENSADO,
            MatriculaDiario.SITUACAO_TRANCADO,
            MatriculaDiario.SITUACAO_TRANSFERIDO,
        ]
        # UC28-RN5 - Durante o caso de uso de fechamento de período só serão computadas as faltas que não tiverem o estado de abonada.
        qs = (
            Falta.objects.filter(contabilizar=True, matricula_diario__matricula_periodo=self)
            .exclude(matricula_diario__situacao__in=situacoes_inativas)
            .filter(Q(matricula_diario__data_matricula__isnull=True) | Q(aula__data__gte=F('matricula_diario__data_matricula')))
        )
        return qs.aggregate(Sum('quantidade')).get('quantidade__sum') or 0

    def get_carga_horaria_frequentada(self):
        return self.get_carga_horaria_cumprida() - self.get_total_faltas()

    def get_percentual_carga_horaria_frequentada(self):
        if self.situacao_id != SituacaoMatriculaPeriodo.MATRICULA_VINCULO_INSTITUCIONAL:
            carga_horaria_cumprida = self.get_carga_horaria_cumprida()
            if carga_horaria_cumprida:
                return (self.get_carga_horaria_frequentada() * 100) / carga_horaria_cumprida
            return 100
        return 0

    def get_percentual_frequencia_periodo(self):
        """Calcula o percentual de frequência do período letivo.

        Para alunos PROITEC retorna 100% se aprovado ou 0% caso contrário.
        Para os demais, soma a carga horária frequentada dividida pela
        carga horária total dos registros de histórico, diários resumidos,
        certificações de conhecimento e aproveitamentos de estudo,
        considerando o fator hora-aula quando aplicável.

        Returns:
            percentual de frequência como ``Decimal``, ``'-'`` se o aluno
            não possuir matriz, ou ``'0'``/``'100'`` para alunos PROITEC.
        """
        if self.aluno.matriz:
            if self.aluno.is_proitec():
                return self.situacao_id == SituacaoMatriculaPeriodo.APROVADO and '100' or '0'
            else:
                situacoes_inativas = [
                    MatriculaDiario.SITUACAO_CANCELADO,
                    MatriculaDiario.SITUACAO_DISPENSADO,
                    MatriculaDiario.SITUACAO_TRANCADO,
                    MatriculaDiario.SITUACAO_TRANSFERIDO,
                ]
                ch_total = 0
                ch_frequencia = 0
                for rh in (
                    RegistroHistorico.objects.filter(matricula_periodo_id=self.id)
                    .exclude(situacao__in=situacoes_inativas)
                    .values('frequencia', 'componente__ch_hora_relogio')
                ):
                    frequencia_aluno = rh['frequencia']
                    ch_disciplina = rh['componente__ch_hora_relogio'] or 0
                    if ch_disciplina and frequencia_aluno is not None:
                        ch_disciplina = mask_ch_componente(ch_disciplina)
                        ch_frequencia += frequencia_aluno * ch_disciplina / 100
                        ch_total += ch_disciplina

                for rh in (
                    MatriculaDiarioResumida.objects.filter(matricula_periodo_id=self.id)
                    .exclude(situacao__in=situacoes_inativas)
                    .values('frequencia', 'equivalencia_componente__carga_horaria')
                ):
                    frequencia_aluno = rh['frequencia']
                    ch_disciplina = rh['equivalencia_componente__carga_horaria'] or 0
                    if ch_disciplina and frequencia_aluno is not None:
                        ch_disciplina = mask_ch_componente(ch_disciplina)
                        ch_frequencia += frequencia_aluno * ch_disciplina / 100
                        ch_total += ch_disciplina

                for cc in CertificacaoConhecimento.objects.filter(matricula_periodo_id=self.id).values(
                    'ausente', 'componente_curricular__componente__ch_hora_relogio'
                ):
                    frequencia_aluno = not cc['ausente'] and 100 or 0
                    ch_disciplina = cc['componente_curricular__componente__ch_hora_relogio'] or 0
                    if ch_disciplina:
                        ch_frequencia += frequencia_aluno
                        ch_total += mask_ch_componente(ch_disciplina)

                for ae in AproveitamentoEstudo.objects.filter(matricula_periodo_id=self.id).values(
                    'frequencia', 'componente_curricular__componente__ch_hora_relogio'
                ):
                    frequencia_aluno = ae['frequencia']
                    ch_disciplina = ae['componente_curricular__componente__ch_hora_relogio'] or 0
                    if ch_disciplina and frequencia_aluno is not None:
                        ch_disciplina = mask_ch_componente(ch_disciplina)
                        ch_frequencia += frequencia_aluno * ch_disciplina / 100
                        ch_total += ch_disciplina

                cc = self.aluno.matriz.componentecurricular_set.filter(componente__ch_hora_relogio__gt=0, componente__ch_hora_aula__gt=0).first()
                if cc:
                    ch_relogio = cc.componente.get_ch_hora_relogio()
                    ch_aula = cc.componente.get_ch_hora_aula()
                    fator_hora_aula = ch_relogio / ch_aula if ch_aula else Decimal(0)
                    ch_frequencia += self.get_carga_horaria_frequentada() * fator_hora_aula
                    ch_total += self.get_carga_horaria_cumprida() * fator_hora_aula

                return ch_frequencia / ch_total * 100 if ch_total else 0
        else:
            return '-'

    def frequentou_carga_horaria_minima(self):
        return self.get_percentual_carga_horaria_frequentada() >= self.aluno.matriz.estrutura.percentual_frequencia

    def pode_fechar_periodo_letivo(self, modulo=None):
        qs = self.matriculadiario_set.all()
        if modulo:
            qs = qs.filter(diario__componente_curricular__tipo_modulo=modulo)
        return all(matricula_diario.pode_fechar_periodo_letivo() for matricula_diario in qs)

    def evadir(self, motivo_evasao):
        from edu.models import SituacaoMatricula

        if self.aluno.integralizou_ensino_medio:
            self.integralizar_ensino_medio('Evasão')
            return

        procedimento = ProcedimentoMatricula()
        procedimento.tipo = ProcedimentoMatricula.EVASAO
        procedimento.situacao_matricula_anterior = self.aluno.situacao
        procedimento.matricula_periodo = self
        procedimento.motivo = motivo_evasao
        procedimento.data = datetime.datetime.now()

        self.realizar_procedimento_matricula(
            procedimento,
            SituacaoMatricula.objects.get(id=SituacaoMatricula.EVASAO),
            SituacaoMatriculaPeriodo.objects.get(id=SituacaoMatriculaPeriodo.EVASAO),
            MatriculaDiario.SITUACAO_CANCELADO,
        )

    def integralizar_ensino_medio(self, motivo):
        from edu.models import SituacaoMatricula

        procedimento = ProcedimentoMatricula()
        procedimento.tipo = ProcedimentoMatricula.INTEGRALIZAR_ENSINO_MEDIO
        procedimento.situacao_matricula_anterior = self.aluno.situacao
        procedimento.matricula_periodo = self
        procedimento.motivo = motivo
        procedimento.data = datetime.datetime.now()

        self.realizar_procedimento_matricula(
            procedimento,
            SituacaoMatricula.objects.get(id=SituacaoMatricula.INTEGRALIZADO_ENSINO_MEDIO),
            SituacaoMatriculaPeriodo.objects.get(id=SituacaoMatriculaPeriodo.INTEGRALIZADO_ENSINO_MEDIO),
            MatriculaDiario.SITUACAO_CANCELADO,
        )

    def matricula_vinculo(self):
        from edu.models import SituacaoMatricula

        if not ProcedimentoMatricula.objects.filter(matricula_periodo=self, tipo=ProcedimentoMatricula.MATRICULA_VINCULO).exists():
            procedimento = ProcedimentoMatricula()
            procedimento.tipo = ProcedimentoMatricula.MATRICULA_VINCULO
            procedimento.situacao_matricula_anterior = self.aluno.situacao
            procedimento.matricula_periodo = self
            procedimento.motivo = 'Ausência de turma/diário'
            procedimento.data = datetime.datetime.now()
            self.realizar_procedimento_matricula(
                procedimento,
                SituacaoMatricula.objects.get(id=SituacaoMatricula.MATRICULA_VINCULO_INSTITUCIONAL),
                SituacaoMatriculaPeriodo.objects.get(id=SituacaoMatriculaPeriodo.MATRICULA_VINCULO_INSTITUCIONAL),
                MatriculaDiario.SITUACAO_CANCELADO,
            )

    def get_percentual_frequencia_minimo(self):
        percentual_frequencia_minimo = self.aluno.matriz.estrutura.percentual_frequencia
        # plano de retomada de aulas em virtude da pandemia (COVID19)
        if self.matriculadiario_set.filter(diario__turma__pertence_ao_plano_retomada=True).exists():
            percentual_frequencia_minimo = 0
        return percentual_frequencia_minimo

    def fechar_periodo_letivo(self, forcar_fechamento=False, modulo=None):
        from edu.models import EstruturaCurso, HistoricoSituacaoMatriculaPeriodo, SituacaoMatricula

        if self.pode_fechar_periodo_letivo(modulo) or forcar_fechamento:
            qs = self.matriculadiario_set.all()
            if modulo:
                qs = qs.filter(diario__componente_curricular__tipo_modulo=modulo)
            for matricula_diario in qs:
                matricula_diario.fechar_periodo_letivo(forcar_fechamento)

            estrutura = self.aluno.matriz.estrutura
            # FIC
            todos_modulos_fechados = True
            if estrutura.tipo_avaliacao == EstruturaCurso.TIPO_AVALIACAO_FIC:
                if MatriculaDiario.objects.filter(matricula_periodo=self, situacao=MatriculaDiario.SITUACAO_CURSANDO).exists():
                    self.situacao = SituacaoMatriculaPeriodo.objects.get(id=SituacaoMatriculaPeriodo.MATRICULADO)
                elif MatriculaDiario.objects.filter(matricula_periodo=self, situacao=MatriculaDiario.SITUACAO_REPROVADO_POR_FALTA).exists():
                    self.situacao = SituacaoMatriculaPeriodo.objects.get(id=SituacaoMatriculaPeriodo.REPROVADO_POR_FALTA)
                elif MatriculaDiario.objects.filter(matricula_periodo=self, situacao=MatriculaDiario.SITUACAO_REPROVADO).exists():
                    self.situacao = SituacaoMatriculaPeriodo.objects.get(id=SituacaoMatriculaPeriodo.REPROVADO)
                elif MatriculaDiario.objects.filter(matricula_periodo=self).exclude(situacao=MatriculaDiario.SITUACAO_APROVADO).exists():
                    self.situacao = SituacaoMatriculaPeriodo.objects.get(id=SituacaoMatriculaPeriodo.FECHADO_COM_PENDENCIA)
                else:
                    self.situacao = SituacaoMatriculaPeriodo.objects.get(id=SituacaoMatriculaPeriodo.APROVADO)

            # Seriado
            elif estrutura.tipo_avaliacao == EstruturaCurso.TIPO_AVALIACAO_SERIADO:
                if self.qtd_reprovacoes() > estrutura.limite_reprovacao:
                    if estrutura.reprova_todas_disciplinas:
                        MatriculaDiario.objects.filter(matricula_periodo=self, situacao=MatriculaDiario.SITUACAO_APROVADO).update(
                            situacao=MatriculaDiario.SITUACAO_APROVADO_REPROVADO_MODULO
                        )
                    self.situacao = SituacaoMatriculaPeriodo.objects.get(id=SituacaoMatriculaPeriodo.REPROVADO)
                elif 0 < self.qtd_reprovacoes() <= estrutura.limite_reprovacao:
                    self.situacao = SituacaoMatriculaPeriodo.objects.get(id=SituacaoMatriculaPeriodo.DEPENDENCIA)
                elif MatriculaDiario.objects.filter(matricula_periodo=self, situacao=MatriculaDiario.SITUACAO_PENDENTE).exists():
                    self.situacao = SituacaoMatriculaPeriodo.objects.get(id=SituacaoMatriculaPeriodo.APROVADO)
                else:
                    self.situacao = SituacaoMatriculaPeriodo.objects.get(id=SituacaoMatriculaPeriodo.APROVADO)

            # Modular
            elif estrutura.tipo_avaliacao == EstruturaCurso.TIPO_AVALIACAO_MODULAR:
                modulos = [modulo] if modulo else self.aluno.matriz.componentecurricular_set.values_list('tipo_modulo', flat=True).distinct()
                for mod in set(modulos):
                    if estrutura.reprova_todas_disciplinas and self.qtd_reprovacoes(mod) > 0:
                        MatriculaDiario.objects.filter(
                            matricula_periodo=self, situacao=MatriculaDiario.SITUACAO_APROVADO, diario__componente_curricular__tipo_modulo=modulo
                        ).update(situacao=MatriculaDiario.SITUACAO_APROVADO_REPROVADO_MODULO)
                todos_modulos_fechados = not self.matriculadiario_set.filter(situacao=MatriculaDiario.SITUACAO_CURSANDO).exists()
                if todos_modulos_fechados:
                    if self.matriculadiario_set.count() == self.matriculadiario_set.filter(situacao=MatriculaDiario.SITUACAO_APROVADO).count():
                        # todas as disciplinas aprovadas
                        self.situacao = SituacaoMatriculaPeriodo.objects.get(id=SituacaoMatriculaPeriodo.APROVADO)
                    elif self.matriculadiario_set.filter(situacao=MatriculaDiario.SITUACAO_REPROVADO).exists() and all(
                        self.matriculadiario_set.filter(diario__componente_curricular__tipo_modulo=mod)
                        .filter(situacao=MatriculaDiario.SITUACAO_REPROVADO)
                        .exists()
                        for mod in self.aluno.matriz.componentecurricular_set.values_list('tipo_modulo', flat=True).distinct()
                    ):
                        # aluno possui pelo menos uma reprovação em cada módulo do período
                        self.situacao = SituacaoMatriculaPeriodo.objects.get(id=SituacaoMatriculaPeriodo.REPROVADO)
                    else:
                        self.situacao = SituacaoMatriculaPeriodo.objects.get(id=SituacaoMatriculaPeriodo.DEPENDENCIA)

            # Crédito
            elif estrutura.tipo_avaliacao == EstruturaCurso.TIPO_AVALIACAO_CREDITO:
                if MatriculaDiario.objects.filter(matricula_periodo=self, situacao=MatriculaDiario.SITUACAO_PENDENTE).exists():
                    self.situacao = SituacaoMatriculaPeriodo.objects.get(id=SituacaoMatriculaPeriodo.FECHADO_COM_PENDENCIA)
                else:
                    self.situacao = SituacaoMatriculaPeriodo.objects.get(id=SituacaoMatriculaPeriodo.PERIODO_FECHADO)

            # Caso o aluno não tenha atindigo o percentual mínino de frequência no período, a situação dele no período
            # será "Reprovado por Falta" e a situação em todos os diários aprovados será "Aprovado/Reprovado no Módulo)
            if (
                not estrutura.reprovacao_por_falta_disciplina
                and self.get_percentual_carga_horaria_frequentada() < self.get_percentual_frequencia_minimo()
            ):
                self.situacao = SituacaoMatriculaPeriodo.objects.get(id=SituacaoMatriculaPeriodo.REPROVADO_POR_FALTA)
                MatriculaDiario.objects.filter(matricula_periodo=self, situacao=MatriculaDiario.SITUACAO_APROVADO).update(
                    situacao=MatriculaDiario.SITUACAO_APROVADO_REPROVADO_MODULO
                )

            qs_historico = HistoricoSituacaoMatriculaPeriodo.objects.filter(matricula_periodo=self).order_by('-id')
            if qs_historico and qs_historico[0].situacao != self.situacao:
                HistoricoSituacaoMatriculaPeriodo.objects.create(matricula_periodo=self, situacao=self.situacao, data=datetime.datetime.now())

            self.save()
            self.aluno.identificar_registros_equivalencia(gerar=True)
            self.aluno.atualizar_situacao('Fechamento de Módulo' if modulo else 'Fechamento de Período')

            if (
                todos_modulos_fechados
                and self.aluno.situacao_id == SituacaoMatricula.MATRICULADO
                and (not self.aluno.curso_campus.is_fic() or self.aluno.matriz.is_regime_modular())
            ):
                self.instanciar_proxima_matricula_periodo()
                self.aluno.atualizar_periodo_referencia()

            if (
                self.aluno.situacao_id == SituacaoMatricula.MATRICULADO
                and self.aluno.get_ultima_matricula_periodo().situacao_id == SituacaoMatriculaPeriodo.EM_ABERTO
            ):
                motivo = self.aluno.deve_ser_jubilado()
                if motivo:
                    self.aluno.jubilar(motivo, True)

            from edu.models import RegistroConvocacaoENADE

            qs_convocacao = RegistroConvocacaoENADE.objects.filter(aluno_id=self.aluno_id, possivel_integralizado=True, situacao__isnull=True)
            if qs_convocacao.exists():
                convocacao = qs_convocacao[0]
                percentual_minimo_concluintes = convocacao.convocacao_enade.modalidadeconvocacaoenade_set.filter(
                    modalidade_id=self.aluno.curso_campus.modalidade_id
                )[0].percentual_minimo_concluintes
                if self.aluno.percentual_ch_cumprida < percentual_minimo_concluintes:
                    coordenadores = [self.aluno.curso_campus.coordenador, self.aluno.curso_campus.coordenador_2]
                    titulo = '[SUAP] Aluno não integralizado convocado para o ENADE'
                    texto = f'<h2>Convocação {convocacao.convocacao_enade.descricao}</h2><p>Atenção, {self.aluno} foi convocado como possível integralizado, mas não atingiu o percentual mínimo no fechamento do período letivo {self.ano_letivo.ano}/{self.periodo_letivo}.</p>'
                    send_notification(titulo, texto, settings.DEFAULT_FROM_EMAIL, coordenadores, fail_silently=True)

    def abrir_periodo_letivo(self, modulo=None):
        from edu.models import HistoricoSituacaoMatriculaPeriodo, SituacaoMatricula

        ids = []
        ids.append(SituacaoMatriculaPeriodo.CANCELADA)
        ids.append(SituacaoMatriculaPeriodo.CANCELAMENTO_COMPULSORIO)
        ids.append(SituacaoMatriculaPeriodo.CANCELAMENTO_POR_DUPLICIDADE)
        ids.append(SituacaoMatriculaPeriodo.CANCELAMENTO_POR_DESLIGAMENTO)
        ids.append(SituacaoMatriculaPeriodo.TRANCADA)
        ids.append(SituacaoMatriculaPeriodo.TRANCADA_VOLUNTARIAMENTE)
        ids.append(SituacaoMatriculaPeriodo.EVASAO)
        ids.append(SituacaoMatriculaPeriodo.JUBILADO)
        ids.append(SituacaoMatriculaPeriodo.INTERCAMBIO)
        if self.situacao_id in ids:
            return
        self.get_matriculas_diario_ativas(modulo).update(situacao=MatriculaDiario.SITUACAO_CURSANDO)
        self.situacao = SituacaoMatriculaPeriodo.objects.get(id=SituacaoMatriculaPeriodo.MATRICULADO)
        qs_historico = HistoricoSituacaoMatriculaPeriodo.objects.filter(matricula_periodo=self).order_by('-id')
        if qs_historico and qs_historico[0].situacao != self.situacao:
            HistoricoSituacaoMatriculaPeriodo.objects.create(matricula_periodo=self, situacao=self.situacao, data=datetime.datetime.now())
        self.save()
        self.excluir_proxima_matricula_periodo()

        self.aluno.situacao = SituacaoMatricula.objects.get(id=SituacaoMatricula.MATRICULADO)
        self.aluno.save()
        msg = 'Módulo' if modulo else 'Período'
        self.aluno.atualizar_situacao(f'Reabertura de {msg}')

    def get_historico(self):
        return self.historicosituacaomatriculaperiodo_set.order_by('data')

    def get_historico_invertido(self):
        return self.historicosituacaomatriculaperiodo_set.order_by('-data')

    def get_historico_no_periodo_referencia(self):
        try:
            from gestao.models import PeriodoReferencia

            registro = self.get_historico_invertido().filter(data__lte=PeriodoReferencia.get_data_limite())[0]
            return (registro.situacao, registro.data)
        except Exception:
            return None

    def get_horarios_aula_por_horario_campus(self, periodo):
        from edu.models import HorarioCampus
        from edu.models.diarios import Diario

        horario_campus_ids = Diario.objects.filter(professordiario__professor=self, periodo_letivo=periodo).values_list(
            'horario_campus__id', flat=True
        )
        horarios_campus = []
        for horario_campus in HorarioCampus.objects.filter(id__in=horario_campus_ids):
            horario_campus.turnos = self.get_horarios_aula_por_turno(periodo, horario_campus)
            horarios_campus.append(horario_campus)
        return horarios_campus

    def get_horarios_aula_por_turno(self):
        from edu.models import HorarioAulaDiario, HorarioCampus, Turno
        from edu.models.diarios import Diario

        dias_semana = HorarioAulaDiario.DIA_SEMANA_CHOICES
        horarios_campus_ids = Diario.objects.filter(matriculadiario__matricula_periodo=self).values_list('horario_campus__id', flat=True)
        turnos_ids = HorarioCampus.objects.filter(id__in=horarios_campus_ids).values_list('horarioaula__turno__id', flat=True)
        turnos = Turno.objects.filter(id__in=turnos_ids).order_by('-id')
        for turno in turnos:
            turno.horarios_aula = []
            turno.dias_semana = dias_semana
            for horario_aula in turno.horarioaula_set.filter(horario_campus__id__in=horarios_campus_ids).order_by('-id').order_by('inicio'):
                horario_aula.dias_semana = []
                for dia_semana in dias_semana:
                    numero = dia_semana[0]
                    nome = dia_semana[1]
                    marcado = False
                    sigla = ''
                    qs = HorarioAulaDiario.objects.filter(
                        # diario__matriculadiario__situacao=MatriculaDiario.SITUACAO_CURSANDO,
                        diario__matriculadiario__matricula_periodo=self,
                        dia_semana=dia_semana[0],
                        horario_aula=horario_aula,
                    )
                    if qs.exists():
                        marcado = True
                        tuples = qs.values_list(
                            'diario__componente_curricular__componente__sigla', 'diario__componente_curricular__componente__descricao_historico'
                        )
                        sigla = tuples[0]
                    else:
                        qs = None
                    if qs and (qs.filter(diario__segundo_semestre=True).count() > 1 or qs.filter(diario__segundo_semestre=False).count() > 1):
                        qs.conflito = True
                    horario_aula.dias_semana.append({'numero': numero, 'nome': nome, 'marcado': marcado, 'sigla': sigla, 'horarios_aula_diario': qs})
                turno.horarios_aula.append(horario_aula)
        return turnos

    def get_horarios_aula_atividade_por_turno(self) -> models.QuerySet:
        from edu.models import Diario, HorarioAtividadeExtra, HorarioAulaDiario, HorarioCampus, Turno

        dias_semana = HorarioAulaDiario.DIA_SEMANA_CHOICES
        horarios_campus_ids = Diario.objects.filter(matriculadiario__matricula_periodo=self).values_list('horario_campus__id', flat=True)
        turnos_ids = HorarioCampus.objects.filter(id__in=horarios_campus_ids).values_list('horarioaula__turno__id', flat=True)
        turnos = Turno.objects.filter(id__in=turnos_ids).order_by('-id')
        ignorar_diarios_com_ids = list(
            self.matriculadiario_set.filter(
                situacao__in=[
                    MatriculaDiario.SITUACAO_TRANCADO,
                    MatriculaDiario.SITUACAO_CANCELADO,
                    MatriculaDiario.SITUACAO_TRANSFERIDO,
                ]
            ).values_list('diario', flat=True)
        )
        turnos.vazio = True
        for turno in turnos:
            turno.horarios_aula = []
            turno.dias_semana = dias_semana
            turno.vazio = True
            for horario_aula in turno.horarioaula_set.filter(horario_campus__id__in=horarios_campus_ids).order_by('-id').order_by('inicio'):
                horario_aula.dias_semana = []
                for dia_semana in dias_semana:
                    numero_semama = dia_semana[0]
                    marcado = False
                    horarios = []
                    conflito = False
                    qs_horarios_aula_diario = HorarioAulaDiario.objects.filter(
                        # diario__matriculadiario__situacao=MatriculaDiario.SITUACAO_CURSANDO,
                        diario__matriculadiario__matricula_periodo=self,
                        dia_semana=numero_semama,
                        horario_aula=horario_aula,
                    ).exclude(diario__in=ignorar_diarios_com_ids)
                    tem_diario = qs_horarios_aula_diario.exists()
                    if tem_diario:
                        marcado = True
                        turno.vazio = False
                        turnos.vazio = False
                        for h_aula in qs_horarios_aula_diario.select_related('diario__componente_curricular__componente'):
                            semestre = (
                                h_aula.diario.segundo_semestre and '2° semestre' or '1° semestre'
                                if h_aula.diario.is_semestral_em_calendario_anual()
                                else None
                            )
                            descricao = (
                                f'{h_aula.diario.componente_curricular.componente.descricao_historico}{h_aula.diario.get_descricao_dinamica()}'
                            )
                            horarios.append(
                                [
                                    'diario',
                                    h_aula.diario.pk,
                                    descricao,
                                    h_aula.diario.componente_curricular.componente.sigla,
                                    h_aula.diario.get_professores(),
                                    h_aula.sala,
                                    semestre,
                                ]
                            )
                        if (
                            qs_horarios_aula_diario.filter(diario__segundo_semestre=True).count() > 1
                            or qs_horarios_aula_diario.filter(diario__segundo_semestre=False).count() > 1
                        ):
                            conflito = True

                    qs_atividade = HorarioAtividadeExtra.objects.filter(matricula_periodo=self, dia_semana=numero_semama, horario_aula=horario_aula)
                    tem_atividade = qs_atividade.exists()
                    if tem_atividade:
                        marcado = True
                        turno.vazio = False
                        turnos.vazio = False
                        for atividade in qs_atividade:
                            horarios.append(['atividade', atividade.pk, atividade.get_tipo_atividade_display(), atividade.descricao_atividade])
                    if tem_atividade and tem_diario:
                        conflito = True

                    horario_aula.dias_semana.append({'numero': numero_semama, 'marcado': marcado, 'conflito': conflito, 'horarios': horarios})
                turno.horarios_aula.append(horario_aula)
        return turnos

    def get_qtd_aulas(self, qs_aulas, mes, ano, excluir_situacoes_inativas=True):
        qs = qs_aulas.filter(data__year=ano, data__month=mes, data__lte=datetime.date.today())
        if excluir_situacoes_inativas:
            situacoes_inativas = [
                MatriculaDiario.SITUACAO_CANCELADO,
                MatriculaDiario.SITUACAO_DISPENSADO,
                MatriculaDiario.SITUACAO_TRANCADO,
                MatriculaDiario.SITUACAO_TRANSFERIDO,
            ]
            qs = qs.filter(
                professor_diario__diario__matriculadiario__in=self.matriculadiario_set.exclude(situacao__in=situacoes_inativas).values_list(
                    'pk', flat=True
                )
            )
        soma = 0
        pks = []
        for pk, quantidade in qs.values_list('pk', 'quantidade'):
            soma += quantidade
            pks.append(pk)
        return soma, pks

    def get_qtd_faltas(self, pks, qs_faltas, abonada=None):
        qs = qs_faltas.filter(aula_id__in=pks)
        if abonada:
            qs = qs.filter(contabilizar=False)
        return qs.aggregate(total=Sum('quantidade'))['total'] or 0

    # Relatório Educacenso
    def get_rendimento(self):
        if self.situacao.pk in [
            SituacaoMatriculaPeriodo.TRANCADA,
            SituacaoMatriculaPeriodo.AFASTADO,
            SituacaoMatriculaPeriodo.DEPENDENCIA,
            SituacaoMatriculaPeriodo.APROVADO,
            SituacaoMatriculaPeriodo.ESTAGIO_MONOGRAFIA,
            SituacaoMatriculaPeriodo.PERIODO_FECHADO,
            SituacaoMatriculaPeriodo.FECHADO_COM_PENDENCIA,
            SituacaoMatriculaPeriodo.APROVEITA_MODULO,
            SituacaoMatriculaPeriodo.INTERCAMBIO,
            SituacaoMatriculaPeriodo.MATRICULA_VINCULO_INSTITUCIONAL,
        ]:
            return 'Aprovado'
        if self.situacao.pk in [SituacaoMatriculaPeriodo.REPROVADO, SituacaoMatriculaPeriodo.REPROVADO_POR_FALTA]:
            return 'Reprovado'
        if self.situacao.pk in [SituacaoMatriculaPeriodo.TRANSF_TURNO, SituacaoMatriculaPeriodo.TRANSF_CURSO]:
            academico_nome_sistema = Configuracao.get_valor_por_chave('edu', 'academico_nome_sistema') or 'Q-Acadêmico'
            return f'Verificar no {academico_nome_sistema}'
        return None

    def get_movimento(self):
        if self.situacao.pk in [SituacaoMatriculaPeriodo.TRANSF_EXTERNA, SituacaoMatriculaPeriodo.TRANSF_INSTITUICAO]:
            return 'Transferido'
        if self.situacao.pk in [
            SituacaoMatriculaPeriodo.CANCELADA,
            SituacaoMatriculaPeriodo.JUBILADO,
            SituacaoMatriculaPeriodo.EVASAO,
            SituacaoMatriculaPeriodo.CANCELAMENTO_COMPULSORIO,
            SituacaoMatriculaPeriodo.CANCELAMENTO_POR_DUPLICIDADE,
            SituacaoMatriculaPeriodo.CANCELAMENTO_POR_DESLIGAMENTO,
        ]:
            return 'Deixou de Frequentar'
        if self.situacao.pk in [SituacaoMatriculaPeriodo.TRANSF_TURNO, SituacaoMatriculaPeriodo.TRANSF_CURSO]:
            academico_nome_sistema = Configuracao.get_valor_por_chave('edu', 'academico_nome_sistema') or 'Q-Acadêmico'
            return f'Verificar no {academico_nome_sistema}'
        return None

    def get_concluinte(self):
        from edu.models import SituacaoMatricula

        if self.aluno.situacao.pk in [
            SituacaoMatricula.AGUARDANDO_COLACAO_DE_GRAU,
            SituacaoMatricula.EGRESSO,
            SituacaoMatricula.FORMADO,
            SituacaoMatricula.CONCLUIDO,
        ]:
            return True
        if self.situacao.pk in [
            SituacaoMatriculaPeriodo.TRANCADA,
            SituacaoMatriculaPeriodo.AFASTADO,
            SituacaoMatriculaPeriodo.DEPENDENCIA,
            SituacaoMatriculaPeriodo.FECHADO_COM_PENDENCIA,
            SituacaoMatriculaPeriodo.INTERCAMBIO,
            SituacaoMatriculaPeriodo.MATRICULA_VINCULO_INSTITUCIONAL,
        ]:
            return False
        if self.situacao.pk in [
            SituacaoMatriculaPeriodo.APROVADO,
            SituacaoMatriculaPeriodo.ESTAGIO_MONOGRAFIA,
            SituacaoMatriculaPeriodo.PERIODO_FECHADO,
        ]:
            return self.aluno.situacao.pk in [SituacaoMatricula.CONCLUIDO, SituacaoMatricula.FORMADO]
        if self.situacao.pk in [SituacaoMatriculaPeriodo.TRANSF_TURNO, SituacaoMatriculaPeriodo.TRANSF_CURSO]:
            academico_nome_sistema = Configuracao.get_valor_por_chave('edu', 'academico_nome_sistema') or 'Q-Acadêmico'
            return f'Verificar no {academico_nome_sistema}'
        return None

    # Relatório Censup
    def get_situacao_censup(self):
        from edu.models import SituacaoMatricula

        if self.aluno.situacao.pk in [
            SituacaoMatricula.AGUARDANDO_COLACAO_DE_GRAU,
            SituacaoMatricula.EGRESSO,
            SituacaoMatricula.FORMADO,
            SituacaoMatricula.CONCLUIDO,
        ]:
            return 'Formado'
        if self.situacao.pk in [
            SituacaoMatriculaPeriodo.TRANCADA,
            SituacaoMatriculaPeriodo.TRANCADA_VOLUNTARIAMENTE,
            SituacaoMatriculaPeriodo.AFASTADO,
            SituacaoMatriculaPeriodo.INTERCAMBIO,
        ]:
            return 'Matrícula Trancada'
        if self.situacao.pk in [SituacaoMatriculaPeriodo.TRANSF_INSTITUICAO, SituacaoMatriculaPeriodo.TRANSF_CURSO]:
            return 'Transferido para outro curso da mesma IES'
        if self.situacao.pk in [
            SituacaoMatriculaPeriodo.CANCELADA,
            SituacaoMatriculaPeriodo.TRANSF_EXTERNA,
            SituacaoMatriculaPeriodo.JUBILADO,
            SituacaoMatriculaPeriodo.EVASAO,
            SituacaoMatriculaPeriodo.CANCELAMENTO_COMPULSORIO,
            SituacaoMatriculaPeriodo.CANCELAMENTO_POR_DUPLICIDADE,
            SituacaoMatriculaPeriodo.CANCELAMENTO_POR_DESLIGAMENTO,
        ]:
            return 'Desvinculado do Curso'
        if self.situacao.pk in [
            SituacaoMatriculaPeriodo.APROVADO,
            SituacaoMatriculaPeriodo.ESTAGIO_MONOGRAFIA,
            SituacaoMatriculaPeriodo.PERIODO_FECHADO,
        ]:
            return (self.aluno.situacao.pk in [SituacaoMatricula.CONCLUIDO, SituacaoMatricula.FORMADO]) and 'Formado' or 'Cursando'
        if self.situacao.pk in [
            SituacaoMatriculaPeriodo.TRANSF_TURNO,
            SituacaoMatriculaPeriodo.DEPENDENCIA,
            SituacaoMatriculaPeriodo.REPROVADO,
            SituacaoMatriculaPeriodo.REPROVADO_POR_FALTA,
            SituacaoMatriculaPeriodo.FECHADO_COM_PENDENCIA,
            SituacaoMatriculaPeriodo.APROVEITA_MODULO,
            SituacaoMatriculaPeriodo.MATRICULA_VINCULO_INSTITUCIONAL,
            SituacaoMatriculaPeriodo.PERIODO_FECHADO,
            SituacaoMatriculaPeriodo.EM_ABERTO,
            SituacaoMatriculaPeriodo.MATRICULADO,
        ]:
            return 'Cursando'
        return None

    def atingiu_qtd_maxima_disciplinas(self):
        from edu.models.cursos import EstruturaCurso

        atingiu_max_disciplinas = False
        estrutura = self.aluno.matriz.estrutura
        qtd_componentes_periodo_referencia = self.aluno.matriz.componentecurricular_set.filter(periodo_letivo=self.aluno.periodo_atual).count()

        if estrutura.numero_disciplinas_superior_periodo and estrutura.tipo_avaliacao == EstruturaCurso.TIPO_AVALIACAO_CREDITO:
            if (
                qtd_componentes_periodo_referencia + estrutura.numero_disciplinas_superior_periodo
                <= self.matriculadiario_set.filter(situacao=MatriculaDiario.SITUACAO_CURSANDO).count()
            ):
                atingiu_max_disciplinas = True
        return atingiu_max_disciplinas

    def atingiu_ch_maxima_disciplinas(self, diario):
        from edu.models.cursos import EstruturaCurso

        estrutura = self.aluno.matriz.estrutura
        if estrutura.ch_maxima_disciplinas and estrutura.tipo_avaliacao == EstruturaCurso.TIPO_AVALIACAO_CREDITO:
            ch_cursando = (
                self.matriculadiario_set.filter(situacao=MatriculaDiario.SITUACAO_CURSANDO)
                .aggregate(qtd=Sum('diario__componente_curricular__componente__ch_hora_relogio'))
                .get('qtd')
                or 0
            )
            ch_total = ch_cursando + diario.componente_curricular.componente.ch_hora_relogio
            if mask_ch_componente(ch_total) > estrutura.ch_maxima_disciplinas:
                return True
        return False

    def utiliza_nota_atitudinal(self):
        return self.aluno.matriz.nivel_ensino_id == NivelEnsino.MEDIO and Configuracao.get_valor_por_chave('edu', 'nota_atitudinal')

    def get_participacoes(self):
        if 'ae' in settings.INSTALLED_APPS:
            calendario = self.get_calendario_academico()
            if calendario:
                data_inicio = calendario.data_inicio
                data_fim = calendario.data_fim
                if data_inicio and data_fim:
                    Participacao = apps.get_model('ae', 'Participacao')
                    participacao_aberta = Participacao.objects.filter(aluno=self.aluno).filter(
                        Q(data_inicio__lte=data_inicio), Q(data_termino__gte=data_fim) | Q(data_termino__isnull=True)
                    )
                    texto = []
                    if participacao_aberta.exists():
                        for participacao in participacao_aberta:
                            texto.append(participacao.programa.tipo_programa.titulo)
                        return format_iterable(texto)
        return '-'


class MatriculaDiario(LogModel):
    SITUACAO_CURSANDO = 1
    SITUACAO_APROVADO = 2
    SITUACAO_REPROVADO = 3
    SITUACAO_PROVA_FINAL = 4
    SITUACAO_REPROVADO_POR_FALTA = 5
    SITUACAO_REPROVADO_EXTENSAO = 23
    SITUACAO_TRANCADO = 6
    SITUACAO_CANCELADO = 7
    SITUACAO_DISPENSADO = 8
    SITUACAO_PENDENTE = 9
    SITUACAO_APROVADO_REPROVADO_MODULO = 10

    SITUACAO_APROVEITAMENTO_ESTUDO = 11
    SITUACAO_CERTIFICACAO_CONHECIMENTO = 12

    SITUACAO_TRANSFERIDO = 13

    SITUACAO_CHOICES = [
        [SITUACAO_CURSANDO, 'Cursando'],
        [SITUACAO_APROVADO, 'Aprovado'],
        [SITUACAO_REPROVADO, 'Reprovado'],
        [SITUACAO_PROVA_FINAL, 'Prova Final'],
        [SITUACAO_REPROVADO_POR_FALTA, 'Reprovado por falta'],
        [SITUACAO_REPROVADO_EXTENSAO, 'Reprovado por Atividade de Extensão'],
        [SITUACAO_TRANCADO, 'Trancado'],
        [SITUACAO_CANCELADO, 'Cancelado'],
        [SITUACAO_DISPENSADO, 'Dispensado'],
        [SITUACAO_PENDENTE, 'Pendente'],
        [SITUACAO_APROVADO_REPROVADO_MODULO, 'Aprovado/Reprovado no Módulo'],
        [SITUACAO_TRANSFERIDO, 'Transferido'],
    ]

    # Managers
    objects = models.Manager()
    locals = managers.MatriculaDiarioLocalManager()
    # Fields
    matricula_periodo = models.ForeignKeyPlus('edu.MatriculaPeriodo')
    diario = models.ForeignKeyPlus('edu.Diario')
    data_matricula = models.DateField(verbose_name='Data da Matrícula', null=True, auto_now_add=True)

    nota_1 = models.NotaField(verbose_name='N1', null=True)
    nota_2 = models.NotaField(verbose_name='N2', null=True)
    nota_3 = models.NotaField(verbose_name='N3', null=True)
    nota_4 = models.NotaField(verbose_name='N4', null=True)

    # notas parciais tratam das notas sem levar em consideração recuperação
    nota_parcial_1 = models.NotaField(verbose_name='NP1', null=True)
    nota_parcial_2 = models.NotaField(verbose_name='NP2', null=True)
    nota_parcial_3 = models.NotaField(verbose_name='NP3', null=True)
    nota_parcial_4 = models.NotaField(verbose_name='NP4', null=True)

    nota_final = models.NotaField(verbose_name='NAF', null=True)
    situacao = models.PositiveIntegerField(choices=SITUACAO_CHOICES, default=SITUACAO_CURSANDO, verbose_name='Situação')

    prova_final_pendente = models.BooleanField(verbose_name='Pendente de Prova Final', default=False, null=False)

    SEARCH_FIELDS = [
        'matricula_periodo__aluno__matricula',
        'matricula_periodo__aluno__pessoa_fisica__nome',
        'diario__componente_curricular__componente__sigla',
        'diario__id',
        'diario__componente_curricular__componente__descricao',
    ]

    class Meta:
        verbose_name = 'Matrícula em Diário'
        verbose_name_plural = 'Matrículas em Diário'
        ordering = ('matricula_periodo__aluno__pessoa_fisica__nome',)
        indexes = [models.Index(fields=['matricula_periodo'], name='edu_matriculadiario_indexes')]
        permissions = (('delete_matriculadiario_cancelada_trancada', 'Pode excluir do diário aluno com matrícula período cancelada ou trancada'),)

    def is_situacao_ativa(self):
        return self.situacao not in (MatriculaDiario.SITUACAO_TRANCADO, MatriculaDiario.SITUACAO_CANCELADO)

    def get_ch_atividade_extensao_cumprida(self):
        return self.vinculacaoatividadeextensao_set.filter(homologada=True).aggregate(Sum('carga_horaria')).get('carga_horaria__sum') or 0

    # plano de retomada de aulas em virtude da pandemia (COVID19)
    def deve_ser_ignorada_no_calculo_do_ira(self):
        # as reprovações durante a pandemia não afetam o cálculo do IRA
        return self.diario.turma.pertence_ao_plano_retomada and self.situacao in (
            MatriculaDiario.SITUACAO_REPROVADO,
            MatriculaDiario.SITUACAO_REPROVADO_POR_FALTA,
        )

    def get_ext_combo_template(self):
        return f'<p>Aluno: {self.matricula_periodo.aluno} </p><p>Diário: {self.diario}</p><p>Situação: {self.get_situacao_display()}</p>'

    def get_nomes_professores(self, excluir_tutores=False):
        lista = []
        qs = self.diario.professordiario_set.all()
        if excluir_tutores:
            qs = qs.exclude(tipo__descricao='Tutor')
        for professor_diario in qs:
            lista.append(professor_diario.professor.vinculo.pessoa.nome)
        return ', '.join(lista)

    def get_titulacoes_professores(self, excluir_tutores=False):
        lista = []
        qs = self.diario.professordiario_set.all()
        if excluir_tutores:
            qs = qs.exclude(tipo__descricao='Tutor')
        for professor_diario in qs:
            titulacao = professor_diario.professor.get_titulacao() or '-'
            lista.append(titulacao)
        return ', '.join(lista)

    def get_situacao_boletim_class(self):
        if self.situacao in [
            MatriculaDiario.SITUACAO_APROVADO,
            MatriculaDiario.SITUACAO_APROVEITAMENTO_ESTUDO,
            MatriculaDiario.SITUACAO_CERTIFICACAO_CONHECIMENTO,
        ]:
            return 'success'
        elif self.situacao in [
            MatriculaDiario.SITUACAO_REPROVADO,
            MatriculaDiario.SITUACAO_REPROVADO_POR_FALTA,
            MatriculaDiario.SITUACAO_REPROVADO_EXTENSAO,
        ]:
            return 'danger'
        else:
            return ''

    def get_ch_total(self):
        return self.diario.componente_curricular.componente.get_ch_hora_relogio()

    def habilitada(self):
        return self.situacao not in [
            MatriculaDiario.SITUACAO_TRANCADO,
            MatriculaDiario.SITUACAO_TRANSFERIDO,
            MatriculaDiario.SITUACAO_CANCELADO,
            MatriculaDiario.SITUACAO_PENDENTE,
        ]

    def pode_registrar_nota(self, etapa, user):
        pode_registrar_nota = False
        # se a situação do aluno no diário for "Cursando"
        if self.is_cursando():
            qs_professor_diario = self.diario.professordiario_set.filter(professor__vinculo__user=user)

            if perms.realizar_procedimentos_academicos(user, self.diario.turma.curso_campus) and self.diario.em_posse_do_registro(etapa):
                pode_registrar_nota = True

            elif qs_professor_diario.exists() and not self.diario.em_posse_do_registro(etapa):
                unico_professor = self.diario.professordiario_set.filter(ativo=True).count() == 1
                if unico_professor or self.diario.estrutura_curso.pode_lancar_nota_fora_do_prazo:
                    pode_registrar_nota = True
                else:
                    data_atual = datetime.date.today()
                    etapa_string = etapa == 5 and 'final' or str(etapa)
                    professor_diario = qs_professor_diario[0]
                    data_inicio_etapa = getattr(professor_diario, f'data_inicio_etapa_{etapa_string}', None)
                    data_fim_etapa = getattr(professor_diario, f'data_fim_etapa_{etapa_string}', None)
                    if data_inicio_etapa and data_fim_etapa and data_inicio_etapa <= data_atual <= data_fim_etapa:
                        pode_registrar_nota = True
        return pode_registrar_nota

    def pode_ser_excluido_do_diario(self, user):
        pode_excluir_cancelado = (
            self.matricula_periodo.situacao.pk in SituacaoMatriculaPeriodo.SITUACOES_INATIVAS_PARA_EXCLUSAO_DIARIO
            and user.has_perm('edu.delete_matriculadiario_cancelada_trancada')
        )
        pode_excluir_matriculado = self.matricula_periodo.situacao.pk == SituacaoMatriculaPeriodo.MATRICULADO and user.has_perm(
            'edu.delete_matriculadiario'
        )

        if pode_excluir_cancelado or pode_excluir_matriculado:
            qs_periodo_posterior = MatriculaPeriodo.objects.filter(
                aluno=self.matricula_periodo.aluno, ano_letivo__ano__gt=self.matricula_periodo.ano_letivo.ano
            ).exclude(situacao__id=SituacaoMatriculaPeriodo.EM_ABERTO)
            if self.matricula_periodo.periodo_letivo == 1:
                qs_periodo_posterior = qs_periodo_posterior | MatriculaPeriodo.objects.filter(
                    aluno=self.matricula_periodo.aluno, ano_letivo__ano=self.matricula_periodo.ano_letivo.ano, periodo_letivo=2
                ).exclude(situacao__id=SituacaoMatriculaPeriodo.EM_ABERTO)
            return not qs_periodo_posterior.exists()
        return False

    def adicionar_registro_historico(self, matriculado_periodo):
        from edu.models import RegistroHistorico

        professor_principal = self.diario.get_professor_principal()
        professor = professor_principal.professor if professor_principal else None

        registro_historico = RegistroHistorico()
        registro_historico.matricula_periodo = matriculado_periodo
        registro_historico.componente = self.diario.componente_curricular.componente
        registro_historico.codigo_diario = self.diario.id
        registro_historico.codigo_turma = self.diario.turma.codigo
        registro_historico.frequencia = self.get_percentual_carga_horaria_frequentada()
        registro_historico.situacao = self.situacao
        registro_historico.codigo_professor = professor and professor.id or 0
        registro_historico.nome_professor = professor and professor.vinculo.pessoa.nome or ''
        registro_historico.titularidade_professor = professor and professor.get_titulacao() or ''
        nota = self.get_media_final_disciplina()
        if self.diario.componente_curricular.avaliacao_por_conceito:
            registro_historico.conceito = self.matricula_periodo.aluno.matriz.estrutura.get_conceito(nota)
        else:
            registro_historico.media_final_disciplina = nota

        registro_historico.save()

    def get_notas_etapa(self, etapa):
        from edu.models.diarios import ItemConfiguracaoAvaliacao, NotaAvaliacao

        return (
            NotaAvaliacao.objects.filter(matricula_diario=self, item_configuracao_avaliacao__configuracao_avaliacao__etapa=etapa)
            .exclude(item_configuracao_avaliacao__tipo=ItemConfiguracaoAvaliacao.TIPO_RECUPERACAO)
            .order_by('item_configuracao_avaliacao_id')
            .select_related('item_configuracao_avaliacao', 'matricula_diario', 'item_configuracao_avaliacao__configuracao_avaliacao')
        )

    def get_nota_recuperacao_etapa(self, etapa):
        from edu.models.diarios import ItemConfiguracaoAvaliacao, NotaAvaliacao

        return (
            NotaAvaliacao.objects.filter(
                matricula_diario=self,
                item_configuracao_avaliacao__configuracao_avaliacao__etapa=etapa,
                item_configuracao_avaliacao__tipo=ItemConfiguracaoAvaliacao.TIPO_RECUPERACAO,
            )
            .select_related('item_configuracao_avaliacao', 'matricula_diario', 'item_configuracao_avaliacao__configuracao_avaliacao')
            .first()
        )

    def get_notas_etapa_1(self):
        return self.get_notas_etapa(1)

    def get_notas_etapa_2(self):
        return self.get_notas_etapa(2)

    def get_notas_etapa_3(self):
        return self.get_notas_etapa(3)

    def get_notas_etapa_4(self):
        return self.get_notas_etapa(4)

    def get_notas_etapa_5(self):
        return self.get_notas_etapa(5)

    def save(self, *args, **kwargs):
        from edu.models import EstagioDocente

        pk = self.pk
        super().save(*args, **kwargs)
        if not pk:
            self.criar_registros_notas()
        if self.diario.componente_curricular.is_seminario_estagio_docente and not self.estagiodocente_set.exists():
            EstagioDocente.objects.create(matricula_diario=self)

        self.registrar_atividade_extensao()

    def gera_registro_atividade_extensao(self, componente_curricular):
        from edu.models.cursos import ComponenteCurricular

        cc_associado = componente_curricular.componente_curricular_associado if componente_curricular.componente_curricular_associado_id else None

        if componente_curricular.tipo == ComponenteCurricular.TIPO_ATIVIDADE_EXTENSAO or (
            cc_associado and cc_associado.tipo == ComponenteCurricular.TIPO_ATIVIDADE_EXTENSAO
        ):
            return True

        if componente_curricular.matriz and componente_curricular.matriz.requer_vinculacao_extensao_diarios:
            return False

        return componente_curricular.get_ch_extensao_exigida() > 0

    def registrar_atividade_extensao(self):
        componente_curricular = self.diario.componente_curricular
        if not self.gera_registro_atividade_extensao(componente_curricular):
            return
        AtividadeCurricularExtensao = apps.get_model('edu', 'AtividadeCurricularExtensao')
        if self.situacao in [MatriculaDiario.SITUACAO_APROVADO, MatriculaDiario.SITUACAO_CURSANDO]:
            ch_extensao = componente_curricular.get_ch_extensao_a_registrar()
            AtividadeCurricularExtensao.registrar(
                self.matricula_periodo.aluno,
                type(self),
                self.pk,
                ch_extensao,
                componente_curricular.componente.descricao_historico,
                self.situacao != MatriculaDiario.SITUACAO_CURSANDO,
                self.situacao == MatriculaDiario.SITUACAO_APROVADO,
                self.matricula_periodo,
            )
        else:
            AtividadeCurricularExtensao.registrar(
                self.matricula_periodo.aluno,
                type(self),
                self.pk,
                0,
                None,
            )

    def delete(self, *args, **kwargs):
        """Remove a matrícula no diário com as limpezas necessárias.

        Se for a última matrícula em diário do período, redefine a situação do
        período para "Em Aberto" e remove a turma. Registra a exclusão na
        extensão curricular quando aplicável. Por fim, chama o ``delete`` da
        superclasse.

        Args:
            *args: argumentos posicionais para o ``delete`` da superclasse.
            **kwargs: argumentos nomeados para o ``delete`` da superclasse.
        """
        if not MatriculaDiario.objects.filter(matricula_periodo=self.matricula_periodo).exclude(pk=self.pk).exists():
            self.matricula_periodo.situacao_id = SituacaoMatriculaPeriodo.EM_ABERTO
            self.matricula_periodo.turma = None
            self.matricula_periodo.save()

        if self.gera_registro_atividade_extensao(self.diario.componente_curricular):
            AtividadeCurricularExtensao = apps.get_model('edu', 'AtividadeCurricularExtensao')
            AtividadeCurricularExtensao.registrar(self.matricula_periodo.aluno, type(self), self.pk, 0, None)
        super().delete(*args, **kwargs)

    def criar_registros_notas(self):
        from edu.models.diarios import ConfiguracaoAvaliacao, ItemConfiguracaoAvaliacao

        etapas = list(range(1, self.diario.componente_curricular.qtd_avaliacoes + 1))
        etapas = etapas and [*etapas, 5] or []
        for etapa in etapas:
            if not self.notaavaliacao_set.filter(item_configuracao_avaliacao__configuracao_avaliacao__etapa=etapa).exists():
                configuracao_avaliacao, _ = ConfiguracaoAvaliacao.objects.get_or_create(diario=self.diario, etapa=etapa)
                if not configuracao_avaliacao.itemconfiguracaoavaliacao_set.exists():
                    item_configuracao_avaliacao = ItemConfiguracaoAvaliacao.objects.create(
                        configuracao_avaliacao=configuracao_avaliacao, sigla=f'A{etapa}'
                    )
                    for matricula_diario in self.diario.matriculadiario_set.all():
                        matricula_diario.criar_registros_notas_etapa(etapa, [item_configuracao_avaliacao])
                self.criar_registros_notas_etapa(etapa, configuracao_avaliacao.itemconfiguracaoavaliacao_set.all())

    def criar_registros_notas_etapa(self, etapa, itens_configuracao_avaliacao):
        from edu.models.diarios import NotaAvaliacao

        for item_configuracao_avaliacao in itens_configuracao_avaliacao:
            qs = NotaAvaliacao.objects.filter(matricula_diario=self, item_configuracao_avaliacao=item_configuracao_avaliacao)
            if not qs.exists():
                NotaAvaliacao.objects.create(matricula_diario=self, item_configuracao_avaliacao=item_configuracao_avaliacao, nota=None)
        self.registrar_nota_etapa(etapa)

    def registrar_nota_etapa(self, etapa, considerar_nota_vazia=False):
        from edu.models.diarios import ConfiguracaoAvaliacao, ItemConfiguracaoAvaliacao, NotaAvaliacao

        if self.diario.is_lancamento_conceito():
            return

        if not self.diario.componente_curricular.qtd_avaliacoes:
            return
        qs = NotaAvaliacao.objects.filter(matricula_diario=self, item_configuracao_avaliacao__configuracao_avaliacao__etapa=etapa)
        id_configuracao_avaliacao = qs.values_list('item_configuracao_avaliacao__configuracao_avaliacao', flat=True).first()
        configuracao_avaliacao = ConfiguracaoAvaliacao.objects.filter(pk=id_configuracao_avaliacao).first()
        # se a forma de cálculo for a maior nota ou soma simples
        if configuracao_avaliacao and configuracao_avaliacao.forma_calculo in (
            ConfiguracaoAvaliacao.FORMA_CALCULO_MAIOR_NOTA,
            ConfiguracaoAvaliacao.FORMA_CALCULO_SOMA_SIMPLES,
        ):
            # pelo menos uma nota deve ter sido lançada
            notas_foram_lancadas = (
                qs.filter(nota__isnull=False).exclude(item_configuracao_avaliacao__tipo=ItemConfiguracaoAvaliacao.TIPO_RECUPERACAO).exists()
            )
        else:
            # senão todas as notas devem ter sido lançadas
            notas_foram_lancadas = (
                not qs.filter(nota__isnull=True).exclude(item_configuracao_avaliacao__tipo=ItemConfiguracaoAvaliacao.TIPO_RECUPERACAO).exists()
            )
        if not notas_foram_lancadas and not considerar_nota_vazia:
            resultado = None
        else:
            if self.diario.estrutura_curso.permite_recuperacao_etapa:
                qs_sem_recuperacao = qs.exclude(item_configuracao_avaliacao__tipo=ItemConfiguracaoAvaliacao.TIPO_RECUPERACAO)
                resultado_sem_recuperacao = self.calcular_media_etapa(qs_sem_recuperacao, etapa)
                attr_sem_recuperacao = 'nota_parcial_{}'.format(int(etapa) == 5 and 'final' or etapa)
                setattr(self, attr_sem_recuperacao, resultado_sem_recuperacao)

                qs_somente_recuperacao = qs.filter(item_configuracao_avaliacao__tipo=ItemConfiguracaoAvaliacao.TIPO_RECUPERACAO)
                resultado = self.calcular_media_etapa_com_recuperacao(qs_somente_recuperacao, resultado_sem_recuperacao)

            else:
                resultado = self.calcular_media_etapa(qs, etapa)
        attr = 'nota_{}'.format(int(etapa) == 5 and 'final' or etapa)
        setattr(self, attr, resultado)

        self.prova_final_pendente = self.is_em_prova_final() and not self.realizou_avaliacao_final()

        super().save()

    def calcular_media_etapa(self, notas_avaliacao, etapa):
        from edu.models.diarios import ConfiguracaoAvaliacao

        nota_avaliacao1 = notas_avaliacao.first()
        forma_calculo = False
        if nota_avaliacao1:
            configuracao_avaliacao = nota_avaliacao1.item_configuracao_avaliacao.configuracao_avaliacao
            forma_calculo = configuracao_avaliacao.forma_calculo

            if configuracao_avaliacao.maior_nota:
                notas_avaliacao = notas_avaliacao.exclude(id=notas_avaliacao.order_by(Coalesce('nota', 0).desc())[0].id)

            if configuracao_avaliacao.menor_nota:
                notas_avaliacao = notas_avaliacao.exclude(id=notas_avaliacao.order_by(Coalesce('nota', 0).asc())[0].id)

        # Cálculos
        media_etapa = None
        if forma_calculo == ConfiguracaoAvaliacao.FORMA_CALCULO_MEDIA_PONDERADA:
            soma = 0
            soma_pesos = 0
            for nota_avaliacao in notas_avaliacao:
                if nota_avaliacao.nota is None:
                    nota_avaliacao.nota = 0
                soma += nota_avaliacao.nota * nota_avaliacao.item_configuracao_avaliacao.peso
                soma_pesos += nota_avaliacao.item_configuracao_avaliacao.peso
            if soma is not None and soma_pesos > 0:
                media_etapa = float(soma) / soma_pesos

        if forma_calculo == ConfiguracaoAvaliacao.FORMA_CALCULO_MAIOR_NOTA:
            media_etapa = notas_avaliacao.aggregate(Max('nota')).get('nota__max')

        if forma_calculo == ConfiguracaoAvaliacao.FORMA_CALCULO_SOMA_SIMPLES:
            media_etapa = notas_avaliacao.aggregate(Sum('nota')).get('nota__sum')

        if forma_calculo == ConfiguracaoAvaliacao.FORMA_CALCULO_MEDIA_ARITMETICA:
            soma_notas = notas_avaliacao.aggregate(Sum('nota')).get('nota__sum')
            if soma_notas is not None:
                media_etapa = float(soma_notas) / notas_avaliacao.count()

        if forma_calculo == ConfiguracaoAvaliacao.FORMA_CALCULO_SOMA_DIVISOR:
            soma_notas = notas_avaliacao.aggregate(Sum('nota')).get('nota__sum')
            if soma_notas is not None:
                media_etapa = float(soma_notas) / configuracao_avaliacao.divisor

        if forma_calculo == ConfiguracaoAvaliacao.FORMA_CALCULO_MEDIA_ATITUDINAL:
            avaliacoes = self.get_nota_sem_atitudinal(etapa)
            atitudinal = self.get_nota_atitudinal(etapa)
            if avaliacoes is not None and atitudinal is not None:
                media_etapa = avaliacoes + atitudinal

        if forma_calculo == ConfiguracaoAvaliacao.FORMA_CALCULO_AVALIACAO_CONCEITO and etapa == 5:
            media_etapa = notas_avaliacao.first().nota

        if media_etapa is not None:
            return round(media_etapa)
        else:
            return 0

    def calcular_media_etapa_com_recuperacao(self, notas_avaliacao_recuperacao, media_etapa):
        # utilizar nota de recuperação
        nota_recuperacao = notas_avaliacao_recuperacao.first()
        if nota_recuperacao and nota_recuperacao.nota:
            if nota_recuperacao.nota > media_etapa:
                media_etapa = nota_recuperacao.nota

        if media_etapa is not None:
            return round(media_etapa)
        else:
            return 0

    def get_sigla_componente(self):
        return self.diario.componente_curricular.componente.sigla

    def get_periodo_matriz(self):
        return self.diario.componente_curricular.periodo_letivo

    def get_descricao_componente(self):
        return f'{self.diario.componente_curricular.componente.descricao_historico}{self.diario.get_descricao_dinamica()}'

    def get_codigo_turma(self):
        return self.diario.turma.codigo

    def get_carga_horaria(self):
        return self.diario.get_carga_horaria_relogio()

    def get_aluno(self):
        return self.matricula_periodo.aluno

    def get_diario(self):
        return self.diario

    def cancelar(self, commit=True, diarios_ignorados=None):
        from edu.models import ComponenteCurricular, EstruturaCurso

        # plano de retomada de aulas em virtude da pandemia (COVID19)
        if self.matricula_periodo.aluno.matriz.is_regime_modular() and not self.diario.turma.pertence_ao_plano_retomada:
            raise ValidationError('Não é possível cancelar a matrícula no diário de um aluno do regime modular.')

        if self.situacao == MatriculaDiario.SITUACAO_CANCELADO:
            return

        if not self.situacao == MatriculaDiario.SITUACAO_CURSANDO:
            raise ValidationError('A situação do aluno no diário deve ser "Cursando".')

        if (
            not self.matricula_periodo.aluno.matriz.estrutura.tipo_avaliacao == EstruturaCurso.TIPO_AVALIACAO_CREDITO
            and not self.diario.turma.pertence_ao_plano_retomada
        ):
            raise ValidationError('O regime de avaliação do aluno deve ser "Crédito".')

        if self.diario.componente_curricular.matriz.id != self.matricula_periodo.aluno.matriz.id:
            componente_curricular = ComponenteCurricular.objects.filter(
                matriz_id=self.matricula_periodo.aluno.matriz.id, componente_id=self.diario.componente_curricular.componente.id
            ).first()
        else:
            componente_curricular = self.diario.componente_curricular
        if componente_curricular and componente_curricular.periodo_letivo == 1 and not self.diario.turma.pertence_ao_plano_retomada:
            raise ValidationError('Matrículas em diários do primeiro período não podem ser canceladas.')

        ultima_matricula_periodo = self.matricula_periodo.aluno.get_ultima_matricula_periodo()

        estrutura = ultima_matricula_periodo.aluno.matriz.estrutura
        qtd_cancelamentos = MatriculaDiario.objects.filter(
            matricula_periodo__aluno_id=self.matricula_periodo.aluno.id,
            diario__componente_curricular__componente=self.diario.componente_curricular.componente,
            situacao=MatriculaDiario.SITUACAO_CANCELADO,
        ).count()

        if estrutura.numero_max_cancelamento_disciplina:
            if qtd_cancelamentos >= estrutura.numero_max_cancelamento_disciplina:
                raise ValidationError('Não é possível realizar o cancelamento, pois atingiu-se o número máximo de cancelamentos desta disciplina.')

        if estrutura.qtd_minima_disciplinas or estrutura.ch_minima_disciplinas:
            possui_qtd_minima = (
                estrutura.qtd_minima_disciplinas
                >= ultima_matricula_periodo.matriculadiario_set.filter(situacao=MatriculaDiario.SITUACAO_CURSANDO).count()
                if estrutura.qtd_minima_disciplinas
                else True
            )
            possui_ch_minima = (
                estrutura.ch_minima_disciplinas
                >= ultima_matricula_periodo.matriculadiario_set.filter(situacao=MatriculaDiario.SITUACAO_CURSANDO)
                .aggregate(Sum('diario__componente_curricular__componente__ch_hora_relogio'))
                .get('diario__componente_curricular__componente__ch_hora_relogio__sum')
                or 0
                if estrutura.ch_minima_disciplinas
                else True
            )
            if possui_qtd_minima and possui_ch_minima:
                optativa = self.diario.componente_curricular.optativo
                if optativa:
                    cumpre_optativas = self.matricula_periodo.aluno.completou_ch_componentes_regulares_optativos()
                    if not cumpre_optativas:
                        ch_cursando = (
                            self.matricula_periodo.aluno.get_ch_componentes_regulares_optativos_cursando()
                            - self.diario.componente_curricular.componente.ch_hora_relogio
                        )
                        ch_pendente = self.matricula_periodo.aluno.get_ch_componentes_regulares_optativos_pendente()
                        cumpre_optativas = ch_cursando >= ch_pendente
                if not (optativa and cumpre_optativas):
                    if not self.diario.turma.pertence_ao_plano_retomada:
                        raise ValidationError('Não é possível realizar o cancelamento, pois atingiu-se o número mínimo de disciplinas por período.')

        if not self.pode_cancelar():
            if not self.diario.turma.pertence_ao_plano_retomada:
                raise ValidationError('Componente já cancelado anteriormente.', 'error')

        co_requisitos = ComponenteCurricular.objects.filter(co_requisitos__in={self.diario.componente_curricular})
        if co_requisitos.exists():
            matricula = MatriculaDiario.objects.filter(
                situacao=MatriculaDiario.SITUACAO_CURSANDO,
                diario__componente_curricular__in=co_requisitos,
                matricula_periodo__aluno=self.matricula_periodo.aluno,
            )
            if diarios_ignorados:
                matricula = matricula.exclude(diario__in=diarios_ignorados)
            if matricula.exists():
                raise ValidationError('Não é possível realizar o cancelamento, pois a disciplina é co-requisito.')

        if commit:
            self.situacao = MatriculaDiario.SITUACAO_CANCELADO
            self.save()

    def set_faltas(self, aulas):
        from edu.models.diarios import Falta

        self.faltas = []
        for aula in aulas:
            falta = Falta.objects.filter(matricula_diario=self, aula=aula).order_by('-id').first()
            if falta is None:
                falta = Falta()
                falta.matricula_diario = self
                falta.aula = aula
                falta.quantidade = 0
            self.faltas.append(falta)

    def is_carga_horaria_diario_fechada(self):
        return self.diario.get_carga_horaria_cumprida() >= self.diario.get_carga_horaria_minima()

    def is_aprovado_por_frequencia(self):
        FREQUENCIA_PADRAO = 75
        percentual_frequencia_minimo = self.matricula_periodo.aluno.matriz.estrutura.percentual_frequencia or FREQUENCIA_PADRAO
        # plano de retomada de aulas em virtude da pandemia (COVID19)
        if self.diario.turma.pertence_ao_plano_retomada:
            percentual_frequencia_minimo = 0
        return self.get_percentual_carga_horaria_frequentada() >= percentual_frequencia_minimo

    def get_situacao_frequencia(self):
        if self.is_carga_horaria_diario_fechada():
            if self.is_aprovado_por_frequencia():
                return {'rotulo': 'Aprovado', 'status': 'success'}
            else:
                return {'rotulo': 'Reprovado', 'status': 'error'}
        else:
            return {'rotulo': 'Cursando', 'status': 'info'}

    def get_situacao_diario_boletim(self):
        situacao = self.get_situacao_diario()
        if self.situacao == MatriculaDiario.SITUACAO_CURSANDO:
            if situacao['rotulo'] == 'Pendente':
                situacao['rotulo'] = 'Cursando'
        return situacao

    def _get_componente_curricular_para_situacao(self, matriz):
        if matriz and matriz.id == self.diario.componente_curricular.matriz_id:
            return self.diario.componente_curricular, matriz
        if matriz:
            cc = (
                matriz.componentecurricular_set.select_related('componente_curricular_associado')
                .filter(componente_id=self.diario.componente_curricular.componente_id)
                .first()
            )
            if cc is not None:
                return cc, matriz
        return self.diario.componente_curricular, self.diario.componente_curricular.matriz

    def _calcular_reprova_extensao(self, matriz, componente_curricular) -> tuple[int, bool]:
        if not (matriz and matriz.requer_vinculacao_extensao_diarios):
            return 0, False
        ch_exigida = componente_curricular.get_ch_extensao_exigida() or 0
        return ch_exigida, ch_exigida > 0

    def get_situacao_diario(self, ignorar_fechamento_carga_horaria=False, zerar_avaliacoes_nao_realizadas=False):
        """
        Este método retorna um dicionário contendo:
            a) uma descrição amigável para a situação computada
            b) o status, que corresonde a uma classe css utilizada no template
            c) a constante do choice definido para o field 'situacao' da classe
        """
        from edu.models import EstruturaCurso

        # Se o período já estiver fechado para o aluno, a situação é computada a partir do atributo 'situção' da classe
        if self.matricula_periodo.situacao_id != SituacaoMatriculaPeriodo.MATRICULADO:
            if self.situacao == MatriculaDiario.SITUACAO_APROVADO:
                return {'rotulo': 'Aprovado', 'status': 'success', 'constant': MatriculaDiario.SITUACAO_APROVADO}
            elif self.situacao == MatriculaDiario.SITUACAO_REPROVADO:
                return {'rotulo': 'Reprovado', 'status': 'error', 'constant': MatriculaDiario.SITUACAO_REPROVADO}
            elif self.situacao == MatriculaDiario.SITUACAO_REPROVADO_POR_FALTA:
                return {'rotulo': 'Reprov. por Falta', 'status': 'error', 'constant': MatriculaDiario.SITUACAO_REPROVADO_POR_FALTA}
            elif self.situacao == MatriculaDiario.SITUACAO_PENDENTE:
                return {'rotulo': 'Pendente', 'status': 'info', 'constant': MatriculaDiario.SITUACAO_PENDENTE}
            elif self.situacao == MatriculaDiario.SITUACAO_APROVADO_REPROVADO_MODULO:
                return {'rotulo': 'Aprovado / Reprovado no Módulo', 'status': 'error', 'constant': MatriculaDiario.SITUACAO_APROVADO_REPROVADO_MODULO}

        # Caso contrário, a situação é computada em tempo de execução a partir das notas da avaliações e da frequência

        nota_1 = self.nota_1
        nota_2 = self.nota_2
        nota_3 = self.nota_3
        nota_4 = self.nota_4
        nota_final = self.nota_final

        # Se o parâmetro 'zerar_avaliacoes_nao_realizadas' for verdadeiro, é necessário identificar as notas que estão nulas para que depois sejam substituídas novamente
        if zerar_avaliacoes_nao_realizadas:
            if not self.nota_1:
                self.nota_1 = 0
            if not self.nota_2:
                self.nota_2 = 0
            if not self.nota_3:
                self.nota_3 = 0
            if not self.nota_4:
                self.nota_4 = 0
            if self.is_em_prova_final():
                if not self.nota_final:
                    self.nota_final = 0

        componente_curricular, matriz = self._get_componente_curricular_para_situacao(self.matricula_periodo.aluno.matriz)
        ch_extensao_exigida, reprova_extensao = self._calcular_reprova_extensao(matriz, componente_curricular)

        # o período do aluno está aberto
        if self.situacao == MatriculaDiario.SITUACAO_CURSANDO:
            is_curso_tecnico = self.diario.turma.curso_campus.modalidade_id in (
                Modalidade.INTEGRADO,
                Modalidade.INTEGRADO_EJA,
                Modalidade.FIC_INTEGRADO_EJA,
                Modalidade.SUBSEQUENTE,
            )
            # se todas as aulas já foram registradas
            if ignorar_fechamento_carga_horaria or self.is_carga_horaria_diario_fechada() or (self.is_em_dependencia() and is_curso_tecnico):
                # caso a avaliação seja por conceito
                if self.diario.estrutura_curso.is_lancamento_conceito():
                    if self.diario.componente_curricular.qtd_avaliacoes > 0:
                        reprovado_por_conceito = (
                            self.nota_final is not None
                            and self.nota_final < self.matricula_periodo.aluno.matriz.estrutura.get_nota_minima_aprovacao_conceito()
                        )
                        if self.nota_final is None:
                            d = {'rotulo': 'Cursando', 'status': 'info', 'constant': MatriculaDiario.SITUACAO_CURSANDO}
                        elif reprovado_por_conceito:
                            d = {'rotulo': 'Reprovado', 'status': 'error', 'constant': MatriculaDiario.SITUACAO_REPROVADO}
                        elif (
                            not reprovado_por_conceito
                            and self.diario.estrutura_curso.reprovacao_por_falta_disciplina
                            and not self.is_aprovado_por_frequencia()
                        ):
                            d = {'rotulo': 'Reprov. por Falta', 'status': 'error', 'constant': MatriculaDiario.SITUACAO_REPROVADO_POR_FALTA}
                        else:
                            d = {'rotulo': 'Aprovado', 'status': 'success', 'constant': MatriculaDiario.SITUACAO_APROVADO}
                    else:
                        # se o componente não requer nota, mas ainda não completou CH mínima
                        if not self.is_carga_horaria_diario_fechada():
                            d = {'rotulo': 'Cursando', 'status': 'info', 'constant': MatriculaDiario.SITUACAO_CURSANDO}
                        # se atingiu o percentual mínimo de frequência na disciplina
                        elif self.is_aprovado_por_frequencia():
                            if not reprova_extensao or self.get_ch_atividade_extensao_cumprida() >= ch_extensao_exigida:
                                d = {'rotulo': 'Aprovado', 'status': 'success', 'constant': MatriculaDiario.SITUACAO_APROVADO}
                            else:
                                d = {'rotulo': 'Reprov. Extensão', 'status': 'error', 'constant': MatriculaDiario.SITUACAO_REPROVADO_EXTENSAO}
                        else:
                            d = {'rotulo': 'Reprov. por Falta', 'status': 'error', 'constant': MatriculaDiario.SITUACAO_REPROVADO}
                # caso a avaliação seja por nota
                elif self.diario.estrutura_curso.criterio_avaliacao == EstruturaCurso.CRITERIO_AVALIACAO_NOTA:
                    # se o componente requer nota
                    if self.diario.componente_curricular.qtd_avaliacoes > 0:
                        # se todas as notas tiverem sido lançadas
                        if self.realizou_todas_avaliacoes():
                            if matriz.estrutura.reprovacao_por_falta_disciplina and not self.is_aprovado_por_frequencia():
                                d = {'rotulo': 'Reprov. por Falta', 'status': 'error', 'constant': MatriculaDiario.SITUACAO_REPROVADO_POR_FALTA}
                            else:
                                if self.is_aprovado_por_nota():
                                    if not reprova_extensao or self.get_ch_atividade_extensao_cumprida() >= ch_extensao_exigida:
                                        d = {'rotulo': 'Aprovado', 'status': 'success', 'constant': MatriculaDiario.SITUACAO_APROVADO}
                                    else:
                                        d = {'rotulo': 'Reprov. Extensão', 'status': 'error', 'constant': MatriculaDiario.SITUACAO_REPROVADO_EXTENSAO}
                                else:
                                    d = {'rotulo': 'Reprovado', 'status': 'error', 'constant': MatriculaDiario.SITUACAO_REPROVADO}
                        # alguma nota está faltando
                        else:
                            # se alguma nota está faltando e não for uma das notas das etapas regulares, é da etapa final
                            if self.realizou_todas_avaliacoes_regulares():
                                d = {'rotulo': 'Prova Final', 'status': 'alert', 'constant': MatriculaDiario.SITUACAO_PROVA_FINAL}
                            # alguma nota das estas regulares não foram entregues
                            else:
                                # se o diário puder ser entregue sem nota
                                if componente_curricular.pode_fechar_pendencia:
                                    # se o diário puder se entregue sem nota e as aulas tiverem sido lançadas
                                    d = {'rotulo': 'Pendente', 'status': 'info', 'constant': MatriculaDiario.SITUACAO_PENDENTE}
                                # o diário não pode ser entregue sem que todas as notas das etapas regulares tenham sido registradas
                                else:
                                    d = {'rotulo': 'Cursando', 'status': 'info', 'constant': MatriculaDiario.SITUACAO_CURSANDO}
                    # o componente não requer nota e a avaliação é por nota
                    else:
                        # se o componente não requer nota, mas ainda não completou CH mínima
                        if not self.is_carga_horaria_diario_fechada():
                            d = {'rotulo': 'Cursando', 'status': 'info', 'constant': MatriculaDiario.SITUACAO_CURSANDO}
                        # se atingiu o percentual mínimo de frequência na disciplina
                        elif self.is_aprovado_por_frequencia():
                            if not reprova_extensao or self.get_ch_atividade_extensao_cumprida() >= ch_extensao_exigida:
                                d = {'rotulo': 'Aprovado', 'status': 'success', 'constant': MatriculaDiario.SITUACAO_APROVADO}
                            else:
                                d = {'rotulo': 'Reprov. Extensão', 'status': 'error', 'constant': MatriculaDiario.SITUACAO_REPROVADO_EXTENSAO}
                        else:
                            d = {'rotulo': 'Reprov. por Falta', 'status': 'error', 'constant': MatriculaDiario.SITUACAO_REPROVADO}
                # avaliação por frequência
                else:
                    # se atingiu o percentual mínimo de frequência na disciplina
                    if self.is_aprovado_por_frequencia():
                        if not reprova_extensao or self.get_ch_atividade_extensao_cumprida() >= ch_extensao_exigida:
                            d = {'rotulo': 'Aprovado', 'status': 'success', 'constant': MatriculaDiario.SITUACAO_APROVADO}
                        else:
                            d = {'rotulo': 'Reprov. Extensão', 'status': 'error', 'constant': MatriculaDiario.SITUACAO_REPROVADO_EXTENSAO}
                    # não atingiu o percentual mínimo de frequência na disciplina
                    else:
                        d = {'rotulo': 'Reprov. por Falta', 'status': 'error', 'constant': MatriculaDiario.SITUACAO_REPROVADO_POR_FALTA}
            # todas as aulas ainda não foram registradas
            else:
                if self.diario.pode_ser_entregue_com_pedencia():
                    # se o diário puder se entregue sem nota e as aulas não tiverem sido lançadas
                    d = {'rotulo': 'Pendente', 'status': 'info', 'constant': MatriculaDiario.SITUACAO_PENDENTE}
                else:
                    status = 'info'
                    d = {'rotulo': 'Cursando', 'status': status, 'constant': MatriculaDiario.SITUACAO_CURSANDO}
        # o período do aluno está fechado
        else:
            if self.situacao == MatriculaDiario.SITUACAO_APROVADO:
                status = 'success'
            elif (
                self.situacao == MatriculaDiario.SITUACAO_REPROVADO
                or self.situacao == MatriculaDiario.SITUACAO_REPROVADO_POR_FALTA
                or self.situacao == MatriculaDiario.SITUACAO_APROVADO_REPROVADO_MODULO
                or self.situacao == MatriculaDiario.SITUACAO_CANCELADO
            ):
                status = 'error'
            elif self.situacao == MatriculaDiario.SITUACAO_TRANCADO or self.situacao == MatriculaDiario.SITUACAO_TRANSFERIDO:
                status = 'alert'
            elif self.situacao == MatriculaDiario.SITUACAO_PENDENTE:
                status = 'info'
            else:
                status = 'alert'
            d = {'rotulo': self.get_situacao_display(), 'status': status, 'constant': self.situacao}

        # Substituindo as notas nulas caso as notas tenham sido zeradas anteriormente
        if zerar_avaliacoes_nao_realizadas:
            self.nota_1 = nota_1
            self.nota_2 = nota_2
            self.nota_3 = nota_3
            self.nota_4 = nota_4
            self.nota_final = nota_final

        return d

    def get_situacao_diario_resumida(self, ignorar_fechamento_carga_horaria=False, zerar_avaliacoes_nao_realizadas=False):
        d = self.get_situacao_diario(ignorar_fechamento_carga_horaria, zerar_avaliacoes_nao_realizadas)
        if d['rotulo'] == 'Aprovado':
            d['rotulo'] = 'APR'
        elif d['rotulo'] == 'Reprovado':
            d['rotulo'] = 'REP'
        elif d['rotulo'] == 'Reprov. por Falta':
            d['rotulo'] = 'RF'
        elif d['rotulo'] == 'Prova Final':
            d['rotulo'] = 'PF'
        elif d['rotulo'] == 'Cursando':
            d['rotulo'] = 'CUR'
        elif d['rotulo'] == 'Trancado':
            d['rotulo'] = 'TRA'
        elif d['rotulo'] == 'Cancelado':
            d['rotulo'] = 'CAN'
        elif d['rotulo'] == 'Transferido':
            d['rotulo'] = 'TRF'
        else:
            d['rotulo'] = 'OUT'
        return d

    def get_situacao_forcada_diario(self):
        """
        Este método retorna um dicionário contendo:
            a) uma descrição amigável para a situação computada
            b) o status, que corresonde a uma classe css utilizada no template
            c) a constante do choice definido para o field 'situacao' da classe

        A situação do diário é calculada não importando se a carga horária tenha sido cumprida ou não.
        Caso as notas das etapas estejam nulas, elas serão definidas como 'zero'.
        Este método é utilizado no processo de fechamento de período.
        """
        return self.get_situacao_diario(ignorar_fechamento_carga_horaria=True, zerar_avaliacoes_nao_realizadas=True)

    def get_situacao_registrada_diario(self):
        """
        Este método retorna um dicionário contendo:
            a) uma descrição amigável para a situação computada
            b) o status, que corresonde a uma classe css utilizada no template
            c) a constante do choice definido para o field 'situacao' da classe

        A situação do diário não é calculada a partir das notas das avaliações e frequência, mas sim do valor atual do atributo 'situacao'.
        Caso deseje saber a situação do diário baseada nas notas e na frequência, o método 'self.get_situacao_diario()' deve ser utilizado.
        """
        if self.situacao == MatriculaDiario.SITUACAO_CURSANDO:
            return {'rotulo': 'Cursando', 'status': 'info', 'constant': MatriculaDiario.SITUACAO_CURSANDO}
        elif self.situacao == MatriculaDiario.SITUACAO_PROVA_FINAL:
            return {'rotulo': 'Prova Final', 'status': 'alert', 'constant': MatriculaDiario.SITUACAO_PROVA_FINAL}
        elif self.situacao == MatriculaDiario.SITUACAO_APROVADO:
            return {'rotulo': 'Aprovado', 'status': 'success', 'constant': MatriculaDiario.SITUACAO_APROVADO}
        elif self.situacao == MatriculaDiario.SITUACAO_REPROVADO:
            return {'rotulo': 'Reprovado', 'status': 'error', 'constant': MatriculaDiario.SITUACAO_REPROVADO}
        elif self.situacao == MatriculaDiario.SITUACAO_REPROVADO_POR_FALTA:
            return {'rotulo': 'Reprov. por Falta', 'status': 'error', 'constant': MatriculaDiario.SITUACAO_REPROVADO_POR_FALTA}
        elif self.situacao == MatriculaDiario.SITUACAO_TRANCADO:
            return {'rotulo': 'Trancado', 'status': 'alert', 'constant': MatriculaDiario.SITUACAO_TRANCADO}
        elif self.situacao == MatriculaDiario.SITUACAO_TRANSFERIDO:
            return {'rotulo': 'Transferido', 'status': 'alert', 'constant': MatriculaDiario.SITUACAO_TRANSFERIDO}
        elif self.situacao == MatriculaDiario.SITUACAO_CANCELADO:
            return {'rotulo': 'Cancelado', 'status': 'alert', 'constant': MatriculaDiario.SITUACAO_CANCELADO}
        elif self.situacao == MatriculaDiario.SITUACAO_PENDENTE:
            return {'rotulo': 'Pendente', 'status': 'info', 'constant': MatriculaDiario.SITUACAO_PENDENTE}
        elif self.situacao == MatriculaDiario.SITUACAO_APROVADO_REPROVADO_MODULO:
            return {'rotulo': 'Aprovado/Reprovado no Módulo', 'status': 'error', 'constant': MatriculaDiario.SITUACAO_APROVADO_REPROVADO_MODULO}

    def pode_fechar_periodo_letivo(self):
        """
        Este método retorna verdadeiro apenas se a situação no diário computada em tempo de execução for diferente de cursando ou em prova final.
        """
        situacao = self.get_situacao_diario()['constant']
        return situacao != MatriculaDiario.SITUACAO_CURSANDO and situacao != MatriculaDiario.SITUACAO_PROVA_FINAL

    def fechar_periodo_letivo(self, forcar_fechamento):
        """
        Este método calcula a situação do diário no momento da execução e atualiza o objeto.
        Caso o parâmetro 'forcar_fechamento' for verdadeiro, a situação é computada ignorando o cumprimento da carga horária do diário e o provimento
        das notas por parte do professor/secretaria.
        """
        if forcar_fechamento:
            self.situacao = self.get_situacao_forcada_diario()['constant']
        else:
            self.situacao = self.get_situacao_diario()['constant']

        self.save()

    def is_cursando(self):
        """
        Este método retorna verdadeiro caso o período não tenha sido fechado para o aluno.
        Quando o período está fechado, a situação do diário não pode ser 'cursando' e nem 'em prova final', ou seja,
        só pode ser 'aprovado', 'reprovado' ou 'reprovado por falta'.
        """
        return self.situacao == MatriculaDiario.SITUACAO_CURSANDO or self.situacao == MatriculaDiario.SITUACAO_PROVA_FINAL

    def is_cancelado(self):
        return self.situacao == MatriculaDiario.SITUACAO_CANCELADO

    def exibe_no_boletim(self):
        return self.situacao != MatriculaDiario.SITUACAO_TRANSFERIDO

    def esteve_reprovado(self):
        from edu.models import Componente, EstruturaCurso

        aluno = self.get_aluno()
        componente_curricular = self.diario.componente_curricular

        matriculas_diario = MatriculaDiario.objects.filter(
            diario__componente_curricular__componente_id=componente_curricular.componente.pk,
            matricula_periodo__aluno=aluno,
            situacao__in=[MatriculaDiario.SITUACAO_REPROVADO, MatriculaDiario.SITUACAO_REPROVADO_POR_FALTA],
        ).exclude(id=self.id)

        matriculas_diario_resumidas = MatriculaDiarioResumida.objects.filter(
            equivalencia_componente__componente=componente_curricular.componente,
            matricula_periodo__aluno=aluno,
            situacao__in=[MatriculaDiario.SITUACAO_REPROVADO, MatriculaDiario.SITUACAO_REPROVADO_POR_FALTA],
        )

        # Se o componente em curso não pertencer a matriz do aluno, pode se tratar de uma disciplina equivalente
        matriculas_diario_equivalentes = MatriculaDiario.objects.none()
        if self.diario.estrutura_curso.tipo_avaliacao in [EstruturaCurso.TIPO_AVALIACAO_SERIADO, EstruturaCurso.TIPO_AVALIACAO_MODULAR]:
            if self.diario.componente_curricular.matriz_id != self.matricula_periodo.aluno.matriz_id:
                ids_equivalentes = Componente.get_ids_componentes_equivalentes(
                    self.diario.componente_curricular.componente_id, self.diario.componente_curricular.matriz_id
                )
                matriculas_diario_equivalentes = MatriculaDiario.objects.filter(
                    diario__componente_curricular__matriz_id=self.matricula_periodo.aluno.matriz_id,
                    diario__componente_curricular__componente_id__in=ids_equivalentes,
                    matricula_periodo__aluno=aluno,
                    situacao__in=[MatriculaDiario.SITUACAO_REPROVADO, MatriculaDiario.SITUACAO_REPROVADO_POR_FALTA],
                )

        return matriculas_diario.exists() or matriculas_diario_resumidas.exists() or matriculas_diario_equivalentes.exists()

    def get_diario_dependencia(self):
        from edu.models.cursos import CursoCampus

        if self.diario.turma.curso_campus.periodicidade == CursoCampus.PERIODICIDADE_ANUAL:
            ano_letivo = Ano.objects.get_or_create(ano=self.diario.ano_letivo.ano + 1)[0]
            periodo_letivo = self.diario.periodo_letivo
        else:
            if self.diario.periodo_letivo == 2:
                ano_letivo = Ano.objects.get_or_create(ano=self.diario.ano_letivo.ano + 1)[0]
                periodo_letivo = 1
            else:
                ano_letivo = self.diario.ano_letivo
                periodo_letivo = 2
        ids = self.get_ids_equivalentes()
        ids.append(self.diario.componente_curricular.componente_id)
        qs = MatriculaDiario.objects.filter(
            matricula_periodo__aluno_id=self.matricula_periodo.aluno_id,
            diario__ano_letivo=ano_letivo,
            diario__periodo_letivo=periodo_letivo,
            diario__componente_curricular__componente__in=ids,
        )
        return qs.values_list('diario', flat=True).first()

    def is_em_dependencia(self):
        from edu.models import EstruturaCurso

        if (
            self.diario.estrutura_curso.tipo_avaliacao in [EstruturaCurso.TIPO_AVALIACAO_SERIADO, EstruturaCurso.TIPO_AVALIACAO_MODULAR]
            and self.is_cursando()
        ):
            aluno = self.get_aluno()
            componente_curricular = self.diario.componente_curricular

            matriculas_diario = MatriculaDiario.objects.filter(
                matricula_periodo__aluno=aluno,
                matricula_periodo__situacao_id=SituacaoMatriculaPeriodo.DEPENDENCIA,
                diario__componente_curricular__componente_id=componente_curricular.componente.pk,
                situacao=MatriculaDiario.SITUACAO_REPROVADO,
            ).exclude(id=self.id)

            matriculas_diario_resumidas = MatriculaDiarioResumida.objects.filter(
                matricula_periodo__aluno=aluno,
                matricula_periodo__situacao_id=SituacaoMatriculaPeriodo.DEPENDENCIA,
                equivalencia_componente__componente=componente_curricular.componente,
                situacao=MatriculaDiario.SITUACAO_REPROVADO,
            )

            # Se o componente em curso não pertencer a matriz do aluno, pode se tratar de uma disciplina equivalente
            matriculas_diario_equivalentes = MatriculaDiario.objects.none()
            if self.diario.componente_curricular.matriz_id != self.matricula_periodo.aluno.matriz_id:
                matriculas_diario_equivalentes = MatriculaDiario.objects.filter(
                    diario__componente_curricular__matriz_id=self.matricula_periodo.aluno.matriz_id,
                    diario__componente_curricular__componente_id__in=self.get_ids_equivalentes(),
                    matricula_periodo__aluno=aluno,
                    matricula_periodo__situacao_id=SituacaoMatriculaPeriodo.DEPENDENCIA,
                    situacao=MatriculaDiario.SITUACAO_REPROVADO,
                )

            return matriculas_diario.exists() or matriculas_diario_resumidas.exists() or matriculas_diario_equivalentes.exists()
        return False

    def get_ids_equivalentes(self):
        from edu.models import Componente

        componente_id = self.diario.componente_curricular.componente_id
        matriz_id = self.diario.componente_curricular.matriz_id
        key = f'ids-equivalentes-{componente_id}-{matriz_id}'
        ids = cache.get(key)
        if ids is None:
            ids = Componente.get_ids_componentes_equivalentes(componente_id, matriz_id)
            cache.set(key, ids)
        return ids

    def is_reprovado_direto(self):
        """
        Este método retorna verdadeiro caso o aluno tenha realizado todas as avaliações regulares e tenha sido aprovado.
        """
        if self.realizou_todas_avaliacoes_regulares():
            if self.get_media_disciplina() < self.matricula_periodo.aluno.matriz.estrutura.media_evitar_reprovacao_direta:
                return True
        return False

    def get_situacao_nota(self):
        """
        Este método retorna um dicionário contendo:
            a) uma descrição amigável para a situação computada
            b) o status, que corresonde a uma classe css utilizada no template
            c) a constante do choice definido para o field 'situacao' da classe

        A situação deve ser computada conforme a seguir:
            Se o critério de avaliacão do curso for por frequência, a situação será 'Aprovado'
            Senão,
                Se o aluno realizou todas as avaliações regulares
                    Se o aluno estiver aprovado direto, a situação será 'Aprovado'
                    Senão, se estiver reprovado direto, a situação será 'Reprovado'
                    Senão, se realizou a avaliação final
                        Se estiver aprovado em prova final, a situação será 'Aprovado'
                        Senão a situação será 'Reprovado'
                    Senão, a situação será 'Prova Final'
                Senão, a situação será 'Pendente'
        """
        from edu.models import EstruturaCurso

        if self.diario.estrutura_curso.is_lancamento_conceito():
            if self.nota_final is None or not self.is_carga_horaria_diario_fechada():
                return {'rotulo': 'Cursando', 'status': 'info', 'constant': MatriculaDiario.SITUACAO_CURSANDO}
            else:
                if self.nota_final < self.matricula_periodo.aluno.matriz.estrutura.get_nota_minima_aprovacao_conceito():
                    return {'rotulo': 'Reprovado', 'status': 'error', 'constant': MatriculaDiario.SITUACAO_REPROVADO}
                else:
                    return {'rotulo': 'Aprovado', 'status': 'success', 'constant': MatriculaDiario.SITUACAO_APROVADO}
        else:
            if self.diario.estrutura_curso.criterio_avaliacao == EstruturaCurso.CRITERIO_AVALIACAO_FREQUENCIA:
                return {'rotulo': 'Aprovado', 'status': 'success', 'constant': MatriculaDiario.SITUACAO_APROVADO}
            else:
                if self.realizou_todas_avaliacoes_regulares():
                    if self.is_aprovado_sem_prova_final():
                        return {'rotulo': 'Aprovado', 'status': 'success', 'constant': MatriculaDiario.SITUACAO_APROVADO}
                    elif self.is_reprovado_direto():
                        return {'rotulo': 'Reprovado', 'status': 'error', 'constant': MatriculaDiario.SITUACAO_REPROVADO}
                    else:
                        if self.realizou_avaliacao_final():
                            if self.is_aprovado_em_prova_final():
                                return {'rotulo': 'Aprovado', 'status': 'success', 'constant': MatriculaDiario.SITUACAO_APROVADO}
                            else:
                                return {'rotulo': 'Reprovado', 'status': 'error', 'constant': MatriculaDiario.SITUACAO_REPROVADO}
                        else:
                            return {'rotulo': 'Prova Final', 'status': 'alert', 'constant': MatriculaDiario.SITUACAO_PROVA_FINAL}
                else:
                    return {'rotulo': 'Cursando', 'status': 'info', 'constant': MatriculaDiario.SITUACAO_CURSANDO}

    def realizou_todas_avaliacoes_regulares(self):
        """
        Este método retorna verdadeiro se todas as avaliações (não importando a avaliação final), possuir um valor diferente de nulo.
        """
        qtd_avaliacoes = self.diario.componente_curricular.qtd_avaliacoes
        if qtd_avaliacoes == 0:
            return True
        # avaliação por conceito não exige todas as avaliações.
        elif self.diario.is_lancamento_conceito():
            return False
        elif qtd_avaliacoes == 1:
            return self.nota_1 is not None
        elif qtd_avaliacoes == 2:
            return self.nota_1 is not None and self.nota_2 is not None
        elif qtd_avaliacoes == 4:
            return self.nota_1 is not None and self.nota_2 is not None and self.nota_3 is not None and self.nota_4 is not None
        return False

    def realizou_todas_avaliacoes(self):
        """
        Este método retorna verdadeiro se todas as avaliações, que necessitam ser feitas, possuir um valor diferente de nulo.
        O valor da avaliação só precisa ser observado se, e somente se, o aluno estiver em prova final.
        """
        if self.realizou_todas_avaliacoes_regulares():
            if self.is_em_prova_final():
                return self.realizou_avaliacao_final()
            return True
        return False

    def is_aprovado_sem_prova_final(self):
        """
        Este método retorna verdadeiro caso o aluno tenha alcançado a média através das avaliações regulares, ou seja, sem prova final.
        Caso o componente não possua avaliações, o método deverá retornar verdadeiro.
        """
        if self.realizou_todas_avaliacoes_regulares():
            if self.diario.componente_curricular.qtd_avaliacoes == 0:
                return True
            else:
                return self.get_media_disciplina() >= self.matricula_periodo.aluno.matriz.estrutura.media_aprovacao_sem_prova_final
        return False

    def realizou_avaliacao_final(self):
        """
        Este método retorna verdadeiro caso o valor da nota final seja diferente de nulo.
        """
        return self.nota_final is not None

    def is_em_prova_final(self):
        """
        Este método retorna verdadeiro se o aluno realizou todas as avaliações regulares e:
            a) Não esteja reprovado direto
            b) Não tenha sido aprovado direto
        """
        if self.realizou_todas_avaliacoes_regulares():
            return not self.is_reprovado_direto() and not self.is_aprovado_sem_prova_final()
        return False

    def is_aprovado_em_prova_final(self):
        """
        Este método retorna verdadeiro se o aluno tiver atingido a média após realizar a avaliação final.
        É importante que ele seja chamado caso a condição definida em 'self.is_em_prova_final()' seja satisfeita
        """
        media_final_disciplina = self.get_media_final_disciplina()
        # plano de retomada de aulas em virtude da pandemia (COVID19)
        if self.diario.turma.pertence_ao_plano_retomada:
            media_aprovacao_avaliacao_final = 50
        else:
            media_aprovacao_avaliacao_final = self.matricula_periodo.aluno.matriz.estrutura.media_aprovacao_avaliacao_final
        if media_final_disciplina is not None and media_aprovacao_avaliacao_final is not None:
            return self.is_em_prova_final() and media_final_disciplina >= media_aprovacao_avaliacao_final
        return False

    def is_aprovado_por_nota(self):
        """
        Este método retorna verdadeiro caso o aluno tenha sido aprovado direto ou na prova final.
        """
        return self.is_aprovado_sem_prova_final() or self.is_aprovado_em_prova_final()

    def is_aprovado(self):
        """
        Este método retorna verdadeiro caso o aluno tenha sido aprovado por nota e por frequência
        """
        return self.is_aprovado_por_nota() and self.is_aprovado_por_frequencia()

    def get_media_disciplina(self):
        """
        Este método retorna a média da disciplina, sem a avaliação final, de acordo com o tipo e avaliação do curso.
        Até o momento, apenas cursos FIC foram implementados.
        """
        media_disciplina = 0
        qtd_avaliacoes = self.diario.componente_curricular.qtd_avaliacoes

        # a média da disciplina deve retonar None caso alguma das notas esperadas não tenha sido registrada
        if qtd_avaliacoes > 0:
            if self.nota_1 is None:
                return None
        if qtd_avaliacoes > 1:
            if self.nota_2 is None:
                return None
        if qtd_avaliacoes > 2:
            if self.nota_3 is None:
                return None
        if qtd_avaliacoes > 3:
            if self.nota_4 is None:
                return None

        PESO_1, PESO_2 = self.get_pesos_calculo_media()

        if qtd_avaliacoes == 1:
            return self.get_nota_1()
        elif qtd_avaliacoes == 2:
            divisor = PESO_1 + PESO_2
            return round((PESO_1 * self.get_nota_1() + PESO_2 * self.get_nota_2()) / float(divisor))
        elif qtd_avaliacoes == 3:
            # Não existe no IFRN. Está sendo utilizada a média aritmética entre as 3 anotas.
            return round((self.get_nota_1() + self.get_nota_2() + self.get_nota_3()) / 3)
        elif qtd_avaliacoes == 4:
            divisor = 2 * (PESO_1 + PESO_2)
            return round(
                (PESO_1 * self.get_nota_1() + PESO_1 * self.get_nota_2() + PESO_2 * self.get_nota_3() + PESO_2 * self.get_nota_4()) / float(divisor)
            )
        return media_disciplina

    def get_pesos_calculo_media(self):
        from edu.models.cursos import EstruturaCurso

        if self.diario.estrutura_curso.calculo_media_final == EstruturaCurso.MEDIA_FINAL_PONDERADA:
            PESO_1 = 2
            PESO_2 = 3
        else:
            PESO_1 = PESO_2 = 1
        return PESO_1, PESO_2

    def get_nota_sem_atitudinal(self, etapa):
        from edu.models.diarios import ItemConfiguracaoAvaliacao, NotaAvaliacao

        qs_notas = NotaAvaliacao.objects.filter(matricula_diario=self, item_configuracao_avaliacao__configuracao_avaliacao__etapa=etapa).exclude(
            item_configuracao_avaliacao__tipo=ItemConfiguracaoAvaliacao.TIPO_ATITUDINAL
        )
        soma_notas = qs_notas.aggregate(Sum('nota')).get('nota__sum')
        if soma_notas is not None:
            # aplicado peso de 80% no cálculo de média aritmética para etapa que não seja a final
            peso = etapa != 5 and 0.8 or 1
            return round((float(soma_notas) / qs_notas.count()) * peso)

    def get_nota_atitudinal(self, etapa):
        from edu.models.diarios import ItemConfiguracaoAvaliacao, NotaAvaliacao

        if self.diario.utiliza_nota_atitudinal():
            if etapa == 5:
                # ignorar nota atitudinal em etapa final
                return 0
            atitudinal = NotaAvaliacao.objects.filter(
                matricula_diario=self,
                item_configuracao_avaliacao__configuracao_avaliacao__etapa=etapa,
                item_configuracao_avaliacao__tipo=ItemConfiguracaoAvaliacao.TIPO_ATITUDINAL,
            ).first()
            if atitudinal and atitudinal.nota is not None:
                # aplicado peso de 20%
                return round(atitudinal.nota * 0.2)

    def is_nota_visivel(self, etapa):
        from edu.models import Diario

        posse = getattr(self.diario, f'posse_etapa_{etapa}')
        if posse == Diario.POSSE_REGISTRO_ESCOLAR:
            return True
        config = getattr(self.diario, f'configuracao_avaliacao_{etapa}')
        return config() and config().autopublicar

    def get_nota_boletim(self, etapa, ignora_autopublicacao=False):
        if ignora_autopublicacao or self.is_nota_visivel(etapa):
            if int(etapa) == 5:
                nota = self.nota_final
            else:
                nota = getattr(self, f'nota_{etapa}')

            estrutura = self.diario.estrutura_curso
            if estrutura.is_lancamento_conceito():
                return estrutura.get_conceito(nota)
            else:
                return mask_nota(nota)
        return None

    def get_recuperacao_boletim(self, etapa, ignora_autopublicacao=False):
        from edu.models.diarios import ItemConfiguracaoAvaliacao, NotaAvaliacao

        if ignora_autopublicacao or self.is_nota_visivel(etapa):
            nota_avaliacao = NotaAvaliacao.objects.filter(
                matricula_diario=self,
                item_configuracao_avaliacao__configuracao_avaliacao__etapa=etapa,
                item_configuracao_avaliacao__tipo=ItemConfiguracaoAvaliacao.TIPO_RECUPERACAO,
            ).first()
            return nota_avaliacao.nota if nota_avaliacao else None
        return None

    def get_nota_parcial_boletim(self, etapa, ignora_autopublicacao=False):
        if ignora_autopublicacao or self.is_nota_visivel(etapa):
            if int(etapa) == 5:
                nota = None
            else:
                nota = getattr(self, f'nota_parcial_{etapa}')

            estrutura = self.diario.estrutura_curso
            if estrutura.is_lancamento_conceito():
                return estrutura.get_conceito(nota)
            else:
                return mask_nota(nota)
        return None

    def get_nota_1(self):
        """
        Este método retorna a nota da avaliação 1 caso ela esteja registrada ou zero, caso contrário.
        """
        return self.nota_1 or 0

    def get_nota_2(self):
        """
        Este método retorna a nota da avaliação 2 caso ela esteja registrada ou zero, caso contrário.
        """
        return self.nota_2 or 0

    def get_nota_3(self):
        """
        Este método retorna a nota da avaliação 3 caso ela esteja registrada ou zero, caso contrário.
        """
        return self.nota_3 or 0

    def get_nota_4(self):
        """
        Este método retorna a nota da avaliação 4 caso ela esteja registrada ou zero, caso contrário.
        """
        return self.nota_4 or 0

    def get_nota_final(self):
        """
        Este método retorna a nota da avaliação final caso ela esteja registrada ou zero, caso contrário.
        """
        return self.nota_final or 0

    def get_media_disciplina_boletim(self):
        from edu.models import ConfiguracaoAvaliacao

        qs = ConfiguracaoAvaliacao.objects.filter(diario=self.diario, autopublicar=False)
        if self.diario.em_posse_do_registro() or not qs.exists():
            return mask_nota(self.get_media_disciplina())
        return None

    def get_media_final_disciplina_boletim(self):
        from edu.models import ConfiguracaoAvaliacao

        qs = ConfiguracaoAvaliacao.objects.filter(diario=self.diario, autopublicar=False).exclude(etapa=5)
        if self.diario.em_posse_do_registro() or not qs.exists():
            return self.get_media_final_disciplina_exibicao()
        return None

    def get_media_final_disciplina_exibicao(self):
        estrutura = self.diario.estrutura_curso
        if estrutura.is_lancamento_conceito():
            return estrutura.get_conceito(self.nota_final)
        else:
            nota = self.get_media_final_disciplina()
            if nota and self.diario.componente_curricular.avaliacao_por_conceito:
                return self.matricula_periodo.aluno.matriz.estrutura.get_conceito(nota)
            else:
                return mask_nota(nota)

    def get_media_final_disciplina(self):
        """
        Este método retorna a média da disciplina, incluindo a avaliação final, de acordo com o tipo e avaliação do curso.
        Até o momento, apenas cursos FIC foram implementados.

        O cálculo da média final da disciplina deve ser a maior nota dentre as notas listadas a seguir, conforme a Organização Didática (Página 61):

        a) Para componentes de uma avaliação
            1. Nota da primeira avaliação
            2. Nota da avaliação final
        b) Para componentes de duas avaliações
            1. Média aritimética entre a média da disciplina e a nota final
            2. Média ponderada entre a nota da primeira avaliação e a nota final com pesos 2 e 3 respectivamente.
            3. Média ponderada entre a nota final e a nota da segunda avaliação com pesos 2 e 3 respectivamente.
        c) Para componentes de quatro avaliações
            1. Média aritimética entre a média da disciplina e a nota final
            2. Média ponderada entre a nota final e as notas da segunda, terceira e quarta etapas com pesos 2, 2, 3 e 3 respectivamente.
            3. Média ponderada entre a nota da primeira etapa, a nota final e as notas da terceira e quarta etapas com pesos 2, 2, 3 e 3 respectivamente.
            4. Média ponderada entre as notas da primeira e segunda etapas, nota final e quarta etapa com pesos 2, 2, 3 e 3 respectivamente.
            5. Média ponderada entre as notas da primeira, segunda e terceira etapas e da nota final com pesos 2, 2, 3 e 3 respectivamente.
        """
        qtd_avaliacoes = self.diario.componente_curricular.qtd_avaliacoes

        # a média final da disciplina deve retonar None caso alguma das notas esperadas não tenha sido registrada
        if not qtd_avaliacoes:
            return None

        if self.diario.estrutura_curso.is_lancamento_conceito():
            return self.nota_final

        if qtd_avaliacoes > 0:
            if self.nota_1 is None:
                return None
        if qtd_avaliacoes > 1:
            if self.nota_2 is None:
                return None
        if qtd_avaliacoes > 2:
            if self.nota_3 is None:
                return None
        if qtd_avaliacoes > 3:
            if self.nota_4 is None:
                return None

        if self.is_em_prova_final():
            if self.nota_final is None:
                return None

            PESO_1, PESO_2 = self.get_pesos_calculo_media()

            notas = []
            if qtd_avaliacoes == 1:
                notas.append(self.get_nota_1())
                notas.append(self.get_nota_final())
            elif qtd_avaliacoes == 2:
                divisor = PESO_1 + PESO_2
                notas.append(round((self.get_media_disciplina() + self.get_nota_final()) / float(2)))
                notas.append(round((PESO_1 * self.get_nota_final() + PESO_2 * self.get_nota_2()) / float(divisor)))
                notas.append(round((PESO_1 * self.get_nota_1() + PESO_2 * self.get_nota_final()) / float(divisor)))
            elif qtd_avaliacoes == 3:
                notas.append(self.get_media_disciplina())
                notas.append(self.get_nota_final())
            elif qtd_avaliacoes == 4:
                divisor = 2 * (PESO_1 + PESO_2)
                notas.append(round((self.get_media_disciplina() + self.get_nota_final()) / float(2)))
                notas.append(
                    round(
                        (PESO_1 * self.get_nota_final() + PESO_1 * self.get_nota_2() + PESO_2 * self.get_nota_3() + PESO_2 * self.get_nota_4())
                        / float(divisor)
                    )
                )
                notas.append(
                    round(
                        (PESO_1 * self.get_nota_1() + PESO_1 * self.get_nota_final() + PESO_2 * self.get_nota_3() + PESO_2 * self.get_nota_4())
                        / float(divisor)
                    )
                )
                notas.append(
                    round(
                        (PESO_1 * self.get_nota_1() + PESO_1 * self.get_nota_2() + PESO_2 * self.get_nota_final() + PESO_2 * self.get_nota_4())
                        / float(divisor)
                    )
                )
                notas.append(
                    round(
                        (PESO_1 * self.get_nota_1() + PESO_1 * self.get_nota_2() + PESO_2 * self.get_nota_3() + PESO_2 * self.get_nota_final())
                        / float(divisor)
                    )
                )

            notas.append(Decimal('0'))
            return max(notas)
        return self.get_media_disciplina()

    def __str__(self):
        """
        Este método retorna uma string contendo a representação dos objetos dessa classe.
        """
        return f'({self.diario.pk}) Aluno {self.matricula_periodo.aluno.matricula} no diário {self.diario.componente_curricular.componente.sigla} {self.diario.componente_curricular.componente.descricao} em {self.matricula_periodo.ano_letivo.ano}.{self.matricula_periodo.periodo_letivo}'

    def get_numero_faltas(self, etapa=None):
        """
        Este método retorna o número de faltas para a etapa informada.
        O total de faltas em todas as etapas é rotornado caso nenhuma etapa seja informada.
        """
        from edu.models import Falta

        qs = Falta.objects.filter(contabilizar=True, matricula_diario=self)
        if self.data_matricula:
            qs = qs.filter(aula__data__gte=self.data_matricula)
        if etapa:
            qs = qs.filter(aula__etapa=etapa)
        return qs.aggregate(Sum('quantidade')).get('quantidade__sum') or 0

    def get_numero_faltas_primeira_etapa(self):
        """
        Este método retorna o número de faltas na primeira etapa.
        """
        return self.get_numero_faltas(1)

    def get_numero_faltas_segunda_etapa(self):
        """
        Este método retorna o número de faltas na segunda etapa.
        """
        return self.get_numero_faltas(2)

    def get_numero_faltas_terceira_etapa(self):
        """
        Este método retorna o número de faltas na terceira etapa.
        """
        return self.get_numero_faltas(3)

    def get_numero_faltas_quarta_etapa(self):
        """
        Este método retorna o número de faltas na quarta etapa.
        """
        return self.get_numero_faltas(4)

    def get_percentual_carga_horaria_frequentada(self, etapa=None):
        """
        Este método retorna o percentual de frequência baseado no número de faltas, conforme descrito a seguir.
        Caso nenhuma aula tenha sido registrada, este método dever retornar 100%.
        """
        faltas = self.get_numero_faltas(etapa)
        if etapa:
            from edu.models.diarios import Aula

            ch_cumprida = (
                Aula.objects.filter(etapa=etapa, professor_diario__diario_id=self.diario_id, data__lte=datetime.date.today())
                .aggregate(Sum('quantidade'))
                .get('quantidade__sum')
                or 0
            )
        else:
            ch_cumprida = self.diario.get_carga_horaria_cumprida()
        if faltas and ch_cumprida:
            return round(100 - (faltas * 100) / ch_cumprida)
        return 100

    def is_componente_integralizado(self):
        return self.situacao in (
            MatriculaDiario.SITUACAO_APROVADO,
            MatriculaDiario.SITUACAO_APROVEITAMENTO_ESTUDO,
            MatriculaDiario.SITUACAO_DISPENSADO,
            MatriculaDiario.SITUACAO_CERTIFICACAO_CONHECIMENTO,
        )

    def get_nota_by_etapa(self, etapa):
        nota = 'nota_{}'.format(etapa == 5 and 'final' or etapa)
        return self.__getattribute__(nota)

    def transferir(self, diario):
        if MatriculaDiario.objects.filter(diario_id=diario.id, matricula_periodo_id=self.matricula_periodo_id).exists():
            raise ValidationError(
                f'Não foi possível realizar a transferência de {self.matricula_periodo.aluno}, pois ele já está matriculado no diário {diario}.'
            )

        self.situacao = self.SITUACAO_TRANSFERIDO

        nova_matricula_diario = MatriculaDiario()
        nova_matricula_diario.diario = diario
        nova_matricula_diario.matricula_periodo = self.matricula_periodo

        nova_matricula_diario.save()

        for etapa in range(1, 6):
            if getattr(self, 'nota_{}'.format(etapa == 5 and 'final' or etapa)) is not None:
                self.transferir_nota(nova_matricula_diario, etapa)

        self.save()

    def transferir_nota(self, nova_matricula_diario, etapa):
        from edu.models import ConfiguracaoAvaliacao

        MULTIPLICADOR_DECIMAL = 1
        if settings.NOTA_DECIMAL:
            MULTIPLICADOR_DECIMAL = settings.CASA_DECIMAL == 1 and 10 or 100

        nota_etapa = getattr(self, 'nota_{}'.format(etapa == 5 and 'final' or etapa))
        configuracao_avaliacao = ConfiguracaoAvaliacao.objects.get(diario=nova_matricula_diario.diario, etapa=etapa)
        if configuracao_avaliacao.forma_calculo == ConfiguracaoAvaliacao.FORMA_CALCULO_SOMA_SIMPLES:
            notas = nova_matricula_diario.get_notas_etapa(etapa)
            for nota in notas:
                if nota_etapa >= nota.item_configuracao_avaliacao.nota_maxima * MULTIPLICADOR_DECIMAL:
                    nota.nota = nota.item_configuracao_avaliacao.nota_maxima * MULTIPLICADOR_DECIMAL
                    nota_etapa -= nota.item_configuracao_avaliacao.nota_maxima * MULTIPLICADOR_DECIMAL
                    nota.save()
                else:
                    nota.nota = nota_etapa
                    nota_etapa = 0
                    nota.save()
        if configuracao_avaliacao.forma_calculo in [
            ConfiguracaoAvaliacao.FORMA_CALCULO_MEDIA_ARITMETICA,
            ConfiguracaoAvaliacao.FORMA_CALCULO_SOMA_DIVISOR,
            ConfiguracaoAvaliacao.FORMA_CALCULO_MEDIA_PONDERADA,
            ConfiguracaoAvaliacao.FORMA_CALCULO_MAIOR_NOTA,
        ]:
            notas = nova_matricula_diario.get_notas_etapa(etapa)
            for nota in notas:
                nota.nota = nota_etapa
                nota.save()
        nova_matricula_diario.registrar_nota_etapa(f'{etapa}')

    def pode_cancelar(self):
        return (
            not MatriculaDiario.objects.filter(
                diario__componente_curricular=self.diario.componente_curricular,
                matricula_periodo__aluno=self.matricula_periodo.aluno,
                situacao=self.SITUACAO_CANCELADO,
            )
            .exclude(diario__turma__pertence_ao_plano_retomada=True)
            .exclude(pk=self.pk)
            .exists()
        )

    def tem_nota_lancada(self):
        from edu.models import NotaAvaliacao

        return NotaAvaliacao.objects.filter(matricula_diario=self).exclude(nota=None).exists()

    def tem_falta(self):
        self.falta_set.exists()

    def can_delete(self, user=None):
        return not self.tem_nota_lancada() and not self.tem_falta()


class FrequenciaPraticaProfissional(LogModel):
    MESES = ['janeiro', 'fevereiro', 'março', 'abril', 'maio', 'junho', 'julho', 'agosto', 'setembro', 'outubro', 'novembro', 'dezembro']
    matricula_diario = models.ForeignKeyPlus(MatriculaDiario, verbose_name='Aluno', on_delete=models.CASCADE)
    mes = models.IntegerField(verbose_name='Mês', choices=[[i + 1, mes] for i, mes in enumerate(MESES)])
    ch_esperada = models.IntegerField(verbose_name='C.H. Esperada')
    ch_frequentada = models.IntegerField(verbose_name='C.H. Frequentada')

    class Meta:
        verbose_name = 'Frequência da Prática Profissional'
        verbose_name_plural = 'Frequências da Prática Profissional'

    def get_percentual(self):
        return int(self.ch_frequentada / self.ch_esperada * 100) if self.ch_esperada else 0


class VinculacaoAtividadeExtensao(LogModel):
    carga_horaria = models.IntegerField(verbose_name='Carga Horária')
    matricula_diario = models.ForeignKeyPlus(MatriculaDiario, verbose_name='Matrícula Diário')
    atividade_extensao = models.ForeignKeyPlus('edu.AtividadeCurricularExtensao', verbose_name='Matrícula Diário')
    data_homologacao = models.DateTimeFieldPlus(verbose_name='Data da Homologação', null=True)
    responsavel_homologacao = models.ForeignKeyPlus('comum.user', verbose_name='Responsável pela Homologação', null=True)
    homologada = models.BooleanField(verbose_name='Homologada', null=True)

    class Meta:
        verbose_name = 'Vinculação de Atividade de Extensão'
        verbose_name_plural = 'Vinculações de Atividades de Extensão'

    def __str__(self):
        return f'{self.atividade_extensao} - {self.atividade_extensao.get_tipo()} - {self.carga_horaria} hora(s)'

    def get_codigo_situacao(self) -> str:
        if self.homologada is None:
            return '0'
        return '1' if self.homologada else '2'

    def get_ch_vinculada_outros(self, incluir_pendentes: bool = False) -> int:
        """Retorna a soma da carga horária de outras vinculações para a mesma matrícula de diário."""
        qs = self.matricula_diario.vinculacaoatividadeextensao_set.exclude(pk=self.pk)
        if not incluir_pendentes:
            qs = qs.filter(homologada=True)
        else:
            qs = qs.exclude(homologada=False)
        return qs.aggregate(Sum('carga_horaria')).get('carga_horaria__sum') or 0

    @classmethod
    def get_totais_ch_por_matricula_diario(
        cls,
        matriculas_diario_ids: Iterable[int],
        excluir_atividade=None,
        incluir_pendentes: bool = False,
    ) -> dict[int, int]:
        """Retorna um mapeamento {matricula_diario_id: total_ch} em uma única consulta agregada."""
        qs = cls.objects.filter(matricula_diario_id__in=matriculas_diario_ids)
        if excluir_atividade:
            qs = qs.exclude(atividade_extensao=excluir_atividade)
        if not incluir_pendentes:
            qs = qs.filter(homologada=True)
        else:
            qs = qs.exclude(homologada=False)
        totais = qs.values('matricula_diario_id').annotate(total=Sum('carga_horaria'))
        return {item['matricula_diario_id']: item['total'] for item in totais}


class MatriculaDiarioResumida(models.ModelPlus):
    SITUACAO_EXTRA_CHOICES = [
        [MatriculaDiario.SITUACAO_APROVEITAMENTO_ESTUDO, 'Aproveit. Disciplina'],
        [MatriculaDiario.SITUACAO_CERTIFICACAO_CONHECIMENTO, 'Cert. Conhecimento'],
    ]

    matricula_periodo = models.ForeignKeyPlus(MatriculaPeriodo)
    equivalencia_componente = models.ForeignKeyPlus('edu.EquivalenciaComponenteQAcademico')
    media_final_disciplina = models.NotaField(null=True)
    frequencia = models.PositiveIntegerField()
    situacao = models.PositiveIntegerField('Situação', choices=MatriculaDiario.SITUACAO_CHOICES + SITUACAO_EXTRA_CHOICES)
    codigo_turma = models.CharFieldPlus('Código da Turma', null=True)
    codigo_professor = models.PositiveIntegerField('Código do Professor', null=True)
    nome_professor = models.CharFieldPlus('Nome do Professor', null=True)
    titularidade_professor = models.CharFieldPlus('Titularidade do Professor', null=True)
    codigo_diario_pauta = models.CharFieldPlus('Código do Diário/Pauta', null=True)
    conceito = models.CharFieldPlus('Conceito', null=True)

    ch_extensao_cumprida = models.PositiveIntegerField('C.H. de Extensão Cumprida', help_text='Hora-Relógio', default=0)

    class Meta:
        verbose_name = 'Registro de Histórico'
        verbose_name_plural = 'Registros de Histórico'

    def clonar(self, matriculado_periodo):
        matricula_diario_resumida = self
        matricula_diario_resumida.id = None
        matricula_diario_resumida.matricula_periodo = matriculado_periodo
        matricula_diario_resumida.save()

    def __str__(self):
        return f'Registro de histórico do aluno {self.matricula_periodo.aluno.matricula} na disciplina {self.equivalencia_componente}'

    def delete(self, *args, **kwargs):
        self.matricula_periodo.aluno.atualizar_situacao('Reprocessamento do Histórico')
        if perms.realizar_procedimentos_academicos(tl.get_user(), self.matricula_periodo.aluno.curso_campus):
            super().delete(*args, **kwargs)
        else:
            raise Exception('Não é possível excluir a Matrícula Diário Resumida')

    def get_nomes_professores(self, excluir_tutores=False):
        return self.nome_professor or '-'

    def get_titulacoes_professores(self, excluir_tutores=False):
        return self.titularidade_professor or '-'

    def get_ch_total(self):
        return self.equivalencia_componente and self.equivalencia_componente.carga_horaria or 0

    def get_sigla_componente(self):
        if self.equivalencia_componente.componente:
            return self.equivalencia_componente.componente.sigla
        return None

    def get_descricao_componente(self):
        if self.equivalencia_componente.componente:
            return self.equivalencia_componente.componente.descricao_historico
        return None

    def get_periodo_matriz(self):
        from edu.models import ComponenteCurricular

        if self.equivalencia_componente.componente:
            qs_componente_curricular = ComponenteCurricular.objects.filter(
                matriz=self.matricula_periodo.aluno.matriz, componente=self.equivalencia_componente.componente
            )
            if qs_componente_curricular:
                return qs_componente_curricular[0].periodo_letivo
        return None

    def get_codigo_turma(self):
        return self.codigo_turma

    def get_carga_horaria(self):
        if self.equivalencia_componente.componente:
            return self.equivalencia_componente.componente.ch_hora_relogio
        return None

    def get_media_final_disciplina_exibicao(self):
        if self.media_final_disciplina is not None:
            return mask_nota(self.media_final_disciplina)
        else:
            return self.conceito

    def get_media_final_disciplina(self):
        return self.media_final_disciplina

    def get_percentual_carga_horaria_frequentada(self):
        return self.frequencia

    def is_componente_integralizado(self):
        return self.situacao in (
            MatriculaDiario.SITUACAO_APROVADO,
            MatriculaDiario.SITUACAO_APROVEITAMENTO_ESTUDO,
            MatriculaDiario.SITUACAO_DISPENSADO,
            MatriculaDiario.SITUACAO_CERTIFICACAO_CONHECIMENTO,
        )

    def get_codigo_diario(self):
        return self.codigo_diario_pauta


class CertificacaoConhecimento(LogModel):
    matricula_periodo = models.ForeignKeyPlus('edu.MatriculaPeriodo', verbose_name='Matrícula Período')
    componente_curricular = models.ForeignKeyPlus('edu.ComponenteCurricular', verbose_name='Componente Curricular')
    data = models.DateFieldPlus('Data')
    nota = models.NotaField('Nota', blank=True, null=True)
    professores = models.ManyToManyFieldPlus(
        'edu.Professor', verbose_name='Professores', blank=True, help_text='Professor(es) da comissão responsável pela certificação.'
    )
    servidores = models.ManyToManyFieldPlus(
        'rh.Servidor', verbose_name='Servidores', blank=True, help_text='Servidor(es) da comissão responsável pela certificação.'
    )
    ausente = models.BooleanField('Ausente', default=False)

    class Meta:
        verbose_name = 'Certificação de Conhecimento'
        verbose_name_plural = 'Certificações de Conhecimento'

    def adicionar_registro_historico(self, matriculado_periodo):
        from edu.models import MatriculaDiario, RegistroHistorico

        registro_historico = RegistroHistorico()
        registro_historico.matricula_periodo = matriculado_periodo
        registro_historico.componente = self.componente_curricular.componente
        registro_historico.media_final_disciplina = self.nota
        registro_historico.situacao = MatriculaDiario.SITUACAO_CERTIFICACAO_CONHECIMENTO
        registro_historico.save()

    def __str__(self):
        return f'Certificação da disciplina {self.componente_curricular.componente.sigla} pelo aluno {self.matricula_periodo.aluno.matricula} '

    def get_absolute_url(self):
        return f'/edu/visualizar/edu/certificacaoconhecimento/{self.pk:d}/'

    def is_aluno_aprovado(self):
        return not self.ausente and self.nota >= self.matricula_periodo.aluno.matriz.estrutura.media_certificacao_conhecimento

    def get_situacao_certificacao(self):
        if self.ausente:
            return 'Ausente Cert. Conhecimento'
        if self.is_aluno_aprovado():
            return 'Cert. Conhecimento'
        return 'Reprovado Cert. Conhecimento'

    def get_media_final_disciplina_exibicao(self):
        estrutura = self.matricula_periodo.aluno.matriz.estrutura
        if estrutura.is_lancamento_conceito():
            return estrutura.get_conceito(self.nota)
        if self.componente_curricular.avaliacao_por_conceito:
            return estrutura.get_conceito(self.nota)
        else:
            return mask_nota(self.nota)

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        ch_extensao = self.componente_curricular.get_ch_extensao_a_registrar()
        if ch_extensao and self.matricula_periodo.aluno.is_aluno_extensao():
            AtividadeCurricularExtensao = apps.get_model('edu', 'AtividadeCurricularExtensao')
            AtividadeCurricularExtensao.registrar(
                self.matricula_periodo.aluno,
                type(self),
                self.pk,
                ch_extensao,
                self.componente_curricular.componente.descricao_historico,
                True,
                self.is_aluno_aprovado(),
            )
        self.matricula_periodo.aluno.atualizar_situacao('Lançamento de Certificação de Conhecimento')

    def delete(self, *args, **kwargs):
        if self.matricula_periodo.aluno.is_aluno_extensao():
            AtividadeCurricularExtensao = apps.get_model('edu', 'AtividadeCurricularExtensao')
            AtividadeCurricularExtensao.registrar(
                self.matricula_periodo.aluno,
                type(self),
                self.pk,
                0,
                None,
            )
        super().delete(*args, **kwargs)
        self.matricula_periodo.aluno.atualizar_situacao('Exclusão de Certificação de Conhecimento')

    def get_aluno(self):
        return self.matricula_periodo.aluno


class AproveitamentoEstudo(LogModel):
    matricula_periodo = models.ForeignKeyPlus('edu.MatriculaPeriodo')
    componente_curricular = models.ForeignKeyPlus('edu.ComponenteCurricular')
    data = models.DateFieldPlus('Data')
    escola_origem = models.CharFieldPlus('Escola de Origem', max_length=255, blank=True, null=True)
    frequencia = models.PositiveIntegerField('Frequência', blank=True, null=True)
    nota = models.NotaField('Nota', blank=False, null=True)
    professores = models.ManyToManyFieldPlus(
        'edu.Professor', verbose_name='Professores', blank=True, help_text='Professor(es) da comissão responsável pelo aproveitamento.'
    )
    servidores = models.ManyToManyFieldPlus(
        'rh.Servidor', verbose_name='Servidores', blank=True, help_text='Servidor(es) da comissão responsável pelo aproveitamento.'
    )

    class Meta:
        verbose_name = 'Aproveitamento de Estudo'
        verbose_name_plural = 'Aproveitamentos de Estudo'

    def __str__(self):
        return f'Aproveitamento da disciplina {self.componente_curricular.componente.sigla} pelo aluno {self.matricula_periodo.aluno.matricula}'

    def get_absolute_url(self):
        return f'/edu/visualizar/edu/certificacaoconhecimento/{self.pk:d}/'

    @transaction.atomic
    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        ch_extensao = self.componente_curricular.get_ch_extensao_a_registrar()
        if ch_extensao and self.matricula_periodo.aluno.is_aluno_extensao():
            AtividadeCurricularExtensao = apps.get_model('edu', 'AtividadeCurricularExtensao')
            AtividadeCurricularExtensao.registrar(
                self.matricula_periodo.aluno,
                type(self),
                self.pk,
                ch_extensao,
                self.componente_curricular.componente.descricao_historico,
                True,
                True,
            )
        self.matricula_periodo.aluno.atualizar_situacao('Lançamento de Aproveitamento de Estudo')

    @transaction.atomic
    def delete(self, *args, **kwargs):
        if self.matricula_periodo.aluno.is_aluno_extensao():
            AtividadeCurricularExtensao = apps.get_model('edu', 'AtividadeCurricularExtensao')
            AtividadeCurricularExtensao.registrar(self.matricula_periodo.aluno, type(self), self.pk, 0, None)
        super().delete(*args, **kwargs)
        self.matricula_periodo.aluno.atualizar_situacao('Exclusão de Aproveitamento de Estudo')

    def adicionar_registro_historico(self, matriculado_periodo):
        from edu.models import MatriculaDiario, RegistroHistorico

        registro_historico = RegistroHistorico()
        registro_historico.matricula_periodo = matriculado_periodo
        registro_historico.componente = self.componente_curricular.componente
        registro_historico.media_final_disciplina = self.nota
        registro_historico.percentual_falta = self.frequencia
        registro_historico.situacao = MatriculaDiario.SITUACAO_APROVEITAMENTO_ESTUDO
        registro_historico.save()

    def get_aluno(self):
        return self.matricula_periodo.aluno

    def get_media_final_disciplina_exibicao(self):
        estrutura = self.matricula_periodo.aluno.matriz.estrutura
        if estrutura.is_lancamento_conceito():
            return estrutura.get_conceito(self.nota)
        elif self.componente_curricular.avaliacao_por_conceito:
            nota = self.nota
            if nota is None or nota < estrutura.media_aprovacao_sem_prova_final:
                nota = self.matricula_periodo.aluno.matriz.estrutura.media_aprovacao_sem_prova_final
            return self.matricula_periodo.aluno.matriz.estrutura.get_conceito(nota)
        else:
            return mask_nota(self.nota)

    @staticmethod
    def validar(mp, componente_curricular, ignorar_prerequisito=False, ignorar_corequisito=False, is_administrador=False):
        from edu.models import ComponenteCurricular, PedidoMatriculaDiario

        if PedidoMatriculaDiario.objects.filter(
            pedido_matricula__matricula_periodo__aluno=mp.aluno,
            data_processamento__isnull=True,
            diario__componente_curricular=componente_curricular,
        ).exists():
            raise ValidationError(
                'Há um pedido de matrícula nessa disciplina. Aguarde o processamento do pedido de matrícula para realizar esse procedimeto.'
            )

        if (
            mp.aluno.matriz.estrutura.percentual_max_aproveitamento
            and not mp.aluno.matriz.estrutura.formas_ingresso_ignoradas_aproveitamento.filter(pk=mp.aluno.forma_ingresso.pk).exists()
        ):
            ch_componentes_aproveitaveis = mp.aluno.matriz.get_ch_certificavel_aproveitavel()
            pode_aproveitar = (
                mp.aluno.get_ch_certificada_ou_aproveitada() + componente_curricular.get_carga_horaria_total()
                <= mp.aluno.matriz.estrutura.percentual_max_aproveitamento * ch_componentes_aproveitaveis / 100
            )
            if not pode_aproveitar:
                raise ValidationError(
                    f'Ao aproveitar essa disciplina, o percentual máximo de carga horária aproveitada/certificada que é de {mp.aluno.matriz.estrutura.percentual_max_aproveitamento}% é estrapolado.'
                )

        pode_cursar, msg = mp.aluno.pode_cursar_componente_curricular(
            componente_curricular, ignorar_prerequisito=ignorar_prerequisito, ignorar_corequisito=ignorar_corequisito
        )
        if not pode_cursar:
            raise ValidationError(f'Essa disciplina não pode ser aproveitada, pois não atende a todos os critérios de co/pré-requisitos: {msg}')

        if mp.aluno.matriz.estrutura.quantidade_max_creditos_aproveitamento:
            pode_aproveitar = (
                mp.aluno.get_creditos_certificados_ou_aproveitados() + componente_curricular.componente.ch_qtd_creditos
                <= mp.aluno.matriz.estrutura.quantidade_max_creditos_aproveitamento
            )
            if not pode_aproveitar:
                raise ValidationError(
                    f'Ao aproveitar essa disciplina, a quantidade máxima de créditos aproveitados/certificados que é de {mp.aluno.matriz.estrutura.quantidade_max_creditos_aproveitamento} será extrapolada.'
                )

        if componente_curricular.tipo in [ComponenteCurricular.TIPO_PRATICA_PROFISSIONAL, ComponenteCurricular.TIPO_TRABALHO_CONCLUSAO_CURSO]:
            if not is_administrador:
                raise ValidationError(
                    'Não é possível fazer aproveitamento de estudos de componentes curriculares de prática profissional ou de trabalho de conclusão de curso.'
                )

        matriculas_periodo = MatriculaPeriodo.objects.filter(aluno=mp.aluno, ano_letivo=mp.ano_letivo, periodo_letivo=mp.periodo_letivo)
        qs1 = MatriculaDiario.objects.filter(
            situacao__in=[MatriculaDiario.SITUACAO_TRANCADO],
            diario__componente_curricular=componente_curricular,
            matricula_periodo__in=matriculas_periodo,
        )
        qs2 = MatriculaDiarioResumida.objects.filter(
            situacao__in=[MatriculaDiario.SITUACAO_TRANCADO],
            equivalencia_componente__componente=componente_curricular.componente,
            matricula_periodo__in=matriculas_periodo,
        )
        if qs1.exists() or qs2.exists():
            raise ValidationError('Não é possível realizar aproveitamento de estudos no período letivo informado, pois o aluno encontra-se trancado.')


class RegistroHistorico(LogModel):
    matricula_periodo = models.ForeignKeyPlus('edu.MatriculaPeriodo')
    componente = models.ForeignKeyPlus('edu.Componente')
    codigo_diario = models.CharFieldPlus(null=True)
    codigo_turma = models.CharFieldPlus(null=True)
    media_final_disciplina = models.NotaField(null=True)
    conceito = models.CharFieldPlus(null=True)
    frequencia = models.PositiveIntegerField(null=True)
    situacao = models.PositiveIntegerField(choices=MatriculaDiario.SITUACAO_CHOICES + MatriculaDiarioResumida.SITUACAO_EXTRA_CHOICES)
    codigo_professor = models.PositiveIntegerField(null=True)
    nome_professor = models.CharFieldPlus(null=True)
    titularidade_professor = models.CharFieldPlus(null=True)

    codigo_professor2 = models.PositiveIntegerField(null=True)
    nome_professor2 = models.CharFieldPlus(null=True)
    titularidade_professor2 = models.CharFieldPlus(null=True)

    outros_professores = models.TextField(
        verbose_name='Outros professores',
        blank=True,
        null=True,
        help_text='Se houver mais de dois professores, informe os adicionais utilizando o seguinte formato: "Nome|Titulação;" — por exemplo: João Maria|Mestre; Maria Silva|Doutora;',
    )

    mobilidade_academica = models.BooleanField('É Mobilidade Acadêmica', default=False)
    identificador_externo = models.IntegerField(
        verbose_name='Identificador Externo',
        null=True,
        blank=True,
        help_text='Identificador do registro em sistema legado em caso de migração',
        db_index=True,
    )

    class Meta:
        verbose_name = 'Registro de Histórico'
        verbose_name_plural = 'Registros de Histórico'

    def __str__(self):
        return f'Registro de histórico do aluno {self.matricula_periodo.aluno.matricula} na disciplina {self.componente.sigla}'

    def clean(self):
        if self.outros_professores:
            titulacoes_validas = {'Graduado', 'Graduada', 'Especialista', 'Mestre', 'Mestra', 'Doutor', 'Doutora', 'Pós-Doutor', 'Pós-Doutora'}

        # Divide por ; e remove espaços extras
        blocos = [bloco.strip() for bloco in self.outros_professores.strip().split(';') if bloco.strip()]

        for bloco in blocos:
            if '|' not in bloco:
                raise ValidationError('O Separador "|" não foi informado no cadastro de outros professores.')  # Falta separador
            nome, titulacao = map(str.strip, bloco.split('|', 1))

            # Verifica se nome e titulação estão preenchidos corretamente
            if not nome or not titulacao:
                raise ValidationError('Nome ou titulação não informados corretamente no cadastro de outros professores.')
            if titulacao not in titulacoes_validas:
                raise ValidationError('Titulação inválida no cadastro de outros professores. As opções válidas são: ' + ', '.join(titulacoes_validas))

        super().clean()

    def adicionar_registro_historico(self, matriculado_periodo):
        registro_historico = self
        registro_historico.id = None
        registro_historico.matricula_periodo = matriculado_periodo
        registro_historico.save()

    def get_media_final_disciplina_exibicao(self, componente_curricular_por_conceito=False):
        if self.conceito:
            return self.conceito
        if self.media_final_disciplina:
            if componente_curricular_por_conceito:
                return self.matricula_periodo.aluno.matriz.estrutura.get_conceito(self.media_final_disciplina)
            else:
                return mask_nota(self.media_final_disciplina)
        return None

    def get_aluno(self):
        return self.matricula_periodo.aluno

    def get_professores_com_titulacao(self):
        result = []
        if self.nome_professor:
            result.append([self.nome_professor, self.titularidade_professor or ''])
        if self.nome_professor2:
            result.append([self.nome_professor2, self.titularidade_professor2 or ''])
        if self.outros_professores:
            for bloco in self.outros_professores.split(';'):
                if '|' in bloco:
                    nome, titulacao = map(str.strip, bloco.split('|', 1))
                    result.append([nome, titulacao])
        return result

    def is_componente_integralizado(self):
        return self.situacao in (
            MatriculaDiario.SITUACAO_DISPENSADO,
            MatriculaDiario.SITUACAO_APROVADO,
            MatriculaDiario.SITUACAO_APROVEITAMENTO_ESTUDO,
            MatriculaDiario.SITUACAO_CERTIFICACAO_CONHECIMENTO,
        )

    def pode_gerenciar_mobilidade_academica(self, user):
        return self.mobilidade_academica and self.get_aluno().pode_gerenciar_mobilidade_academica(user)
