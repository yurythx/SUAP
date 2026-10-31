import datetime
import math
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.db.models.aggregates import Avg, Sum

from comum.models import Configuracao, ReservaSala, SolicitacaoReservaSala
from comum.utils import tl
from djtools.db import models
from djtools.templatetags.filters import format_
from djtools.utils import mask_nota, running_tests, send_mail, send_notification, somar_dias
from edu import managers, perms
from edu.managers import DiarioLocalManager, DiarioManager
from edu.models.cadastros_gerais import (
    PERIODO_LETIVO_CHOICES,
    HorarioAula,
    HorarioAulaDiario,
    NivelEnsino,
    SituacaoMatriculaPeriodo,
    TipoProfessorDiario,
    Turno,
)
from edu.models.historico import FrequenciaPraticaProfissional, MatriculaDiario, MatriculaPeriodo
from edu.models.logs import LogModel
from edu.models.plano_ensino import PlanoEnsino
from edu.models.polos import Polo
from edu.models.professores import Professor


class ObservacaoDiario(LogModel):
    observacao = models.TextField('Observação do Diário')
    diario = models.ForeignKeyPlus('edu.Diario', verbose_name='Diário')
    data = models.DateFieldPlus(verbose_name='Data')
    usuario = models.ForeignKeyPlus('comum.User', verbose_name='Usuário')

    class Meta:
        permissions = (('adm_delete_observacaodiario', 'Pode deletar observações de outros usuários'),)


class Diario(LogModel):
    SEARCH_FIELDS = ['search_fields_optimized']

    SITUACAO_ABERTO = 1
    SITUACAO_FECHADO = 2
    SITUACAO_CHOICES = [[SITUACAO_ABERTO, 'Aberto'], [SITUACAO_FECHADO, 'Fechado']]

    POSSE_REGISTRO_ESCOLAR = 0
    POSSE_PROFESSOR = 1
    POSSE_CHOICES = [[POSSE_PROFESSOR, 'Professor'], [POSSE_REGISTRO_ESCOLAR, 'Registro Escolar']]

    ETAPA_1 = 1
    ETAPA_2 = 2
    ETAPA_3 = 3
    ETAPA_4 = 4
    ETAPA_5 = 5
    ETAPA_CHOICES = [[ETAPA_1, 'Etapa 1'], [ETAPA_2, 'Etapa 2'], [ETAPA_3, 'Etapa 3'], [ETAPA_4, 'Etapa 4'], [ETAPA_5, 'Etapa Final']]

    # Manager
    objects = DiarioManager()
    locals = DiarioLocalManager()
    # Fields
    id = models.AutoField(verbose_name='Código', primary_key=True)
    turma = models.ForeignKeyPlus('edu.Turma', verbose_name='Turma', on_delete=models.CASCADE)
    componente_curricular = models.ForeignKeyPlus('edu.ComponenteCurricular', verbose_name='Componente', null=True, on_delete=models.CASCADE)
    percentual_minimo_ch = models.PositiveIntegerField(verbose_name='Percentual Mínimo (Carga Horária)')
    ano_letivo = models.ForeignKeyPlus('comum.Ano', verbose_name='Ano Letivo', related_name='diarios_por_ano_letivo_set', on_delete=models.CASCADE)
    periodo_letivo = models.PositiveIntegerField(verbose_name='Período Letivo', choices=PERIODO_LETIVO_CHOICES)
    quantidade_vagas = models.PositiveIntegerField(verbose_name='Quantidade de Vagas', default=0)
    situacao = models.PositiveIntegerField(verbose_name='Situação', choices=SITUACAO_CHOICES, default=SITUACAO_ABERTO)
    horario_campus = models.ForeignKeyPlus('edu.HorarioCampus', verbose_name='Horário do Campus', on_delete=models.CASCADE)
    turno = models.ForeignKeyPlus('edu.Turno', verbose_name='Turno', on_delete=models.CASCADE)
    estrutura_curso = models.ForeignKeyPlus('edu.EstruturaCurso', verbose_name='Estrutura de Curso', on_delete=models.CASCADE)
    calendario_academico = models.ForeignKeyPlus('edu.CalendarioAcademico', verbose_name='Calendário Acadêmico', on_delete=models.CASCADE)

    local_aula = models.ForeignKeyPlus('comum.Sala', verbose_name='Sala de aula', null=True)
    local_laboratorio = models.ForeignKeyPlus('comum.Sala', verbose_name='Laboratório', null=True, related_name='locallaboratorio_set')
    locais_aula_secundarios = models.ManyToManyFieldPlus(
        'comum.Sala', verbose_name='Locais de aula secundários', blank=True, related_name='locais_aula_secundarios'
    )

    descricao_dinamica = models.CharFieldPlus('Descrição Dinâmica', null=True, blank=True)
    segundo_semestre = models.BooleanField('Segundo Semestre', default=False)
    integracao_com_moodle = models.BooleanField('Integração com o Moodle', default=False)
    url_moodle = models.CharFieldPlus('URL do Moodle', null=True, blank=True)
    url_ambiente_virtual = models.CharFieldPlus(
        'URL do Ambiente Virtual',
        null=True,
        blank=True,
        help_text='Endereço da plataforma através da qual o professor poderá interagir com seus alunos durante a realização das aulas ou em atividades programadas',
    )
    ignorar_choque_horario_renovacao_matricula = models.BooleanField('Ignorar Choque de Horário na Renovação de Matrícula', default=False)
    posse_etapa_1 = models.PositiveIntegerField(choices=POSSE_CHOICES, default=POSSE_PROFESSOR)
    posse_etapa_2 = models.PositiveIntegerField(choices=POSSE_CHOICES, default=POSSE_PROFESSOR)
    posse_etapa_3 = models.PositiveIntegerField(choices=POSSE_CHOICES, default=POSSE_PROFESSOR)
    posse_etapa_4 = models.PositiveIntegerField(choices=POSSE_CHOICES, default=POSSE_PROFESSOR)
    posse_etapa_5 = models.PositiveIntegerField(choices=POSSE_CHOICES, default=POSSE_PROFESSOR)

    entregue_fisicamente = models.BooleanField(verbose_name='Entregue Fisicamente', null=True)

    possui_segunda_oferta = models.BooleanField('Possui segunda oferta', default=False)
    diario_primeira_oferta = models.ForeignKeyPlus('edu.Diario', verbose_name='Diário primeira oferta', null=True, blank=True)

    search_fields_optimized = models.UnaccentField(max_length=1000, db_index=True)

    class Meta:
        verbose_name = 'Diário'
        verbose_name_plural = 'Diários'

        permissions = (
            ('reabrir_diario', 'Pode reabrir Diário'),
            ('lancar_nota_diario', 'Pode lançar nota em Diário'),
            ('mudar_posse_diario', 'Pode mudar posse de Diário'),
            ('emitir_boletins', 'Pode emitir boletins de Diário'),
        )

    EXT_COMBO_RELATED = {
        'select_related': [
            'componente_curricular',
            'componente_curricular__componente',
            'componente_curricular__componente__nivel_ensino',
            'turma',
            'calendario_academico',
            'horario_campus',
            'turno',
        ],
        'prefetch_related': [],
    }

    def __str__(self):
        componente = f'{self.componente_curricular.componente.sigla} - {self.componente_curricular.componente.descricao} {self.get_descricao_dinamica()} - {self.componente_curricular.componente.nivel_ensino!s} [{self.componente_curricular.componente.get_ch_hora_relogio()} h/{self.componente_curricular.componente.get_ch_hora_aula()} Aulas]'
        if self.id:
            descricao = f'{self.id} - {componente}'
        else:
            descricao = str(self.componente_curricular)
        return descricao

    def get_descricao_resumida(self):
        return f'{self.pk} - {self.componente_curricular.componente.sigla} - {self.componente_curricular.componente.descricao}{self.get_descricao_dinamica()}'

    def get_frequencias_pratica_profissional(self):
        return FrequenciaPraticaProfissional.objects.filter(matricula_diario__diario=self)

    def get_resumo_ch_prevista(self):
        resumo = []
        for professor_diario in self.get_professores():
            resumo.append(professor_diario.get_resumo_ch_prevista())
        return ' | '.join(resumo)

    def get_itens_avaliacao(self):
        return ItemConfiguracaoAvaliacao.objects.filter(configuracao_avaliacao__diario=self)

    def get_ocorrencias(self):
        return OcorrenciaDiario.objects.filter(professor_diario__diario=self)

    def is_semestral_segundo_semestre(self):
        return self.segundo_semestre and self.is_semestral_em_calendario_anual()

    def get_inicio_etapa_1(self):
        inicio_etapa = self.calendario_academico.data_inicio_etapa_1
        if self.is_semestral_segundo_semestre():
            inicio_etapa = self.calendario_academico.data_inicio_etapa_3
        return inicio_etapa

    def get_fim_etapa_1(self):
        fim_etapa = self.calendario_academico.data_fim_etapa_1
        if self.is_semestral_segundo_semestre():
            fim_etapa = self.calendario_academico.data_fim_etapa_3
        if self.componente_curricular.qtd_avaliacoes == 1 and self.calendario_academico.qtd_etapas == 2:
            fim_etapa = self.calendario_academico.data_fim_etapa_2
        return fim_etapa

    def get_inicio_etapa_2(self):
        inicio_etapa = self.calendario_academico.data_inicio_etapa_2
        if self.is_semestral_segundo_semestre():
            inicio_etapa = self.calendario_academico.data_inicio_etapa_4
        return inicio_etapa

    def get_fim_etapa_2(self):
        fim_etapa = self.calendario_academico.data_fim_etapa_2
        if self.is_semestral_segundo_semestre():
            fim_etapa = self.calendario_academico.data_fim_etapa_4
        return fim_etapa

    def get_inicio_etapa_3(self):
        return self.calendario_academico.data_inicio_etapa_3

    def get_fim_etapa_3(self):
        return self.calendario_academico.data_fim_etapa_3

    def get_inicio_etapa_4(self):
        return self.calendario_academico.data_inicio_etapa_4

    def get_fim_etapa_4(self):
        return self.calendario_academico.data_fim_etapa_4

    def get_inicio_etapa_final(self):
        inicio_etapa = self.calendario_academico.data_inicio_prova_final or self.calendario_academico.get_data_fim_utlima_etapa()
        if not self.segundo_semestre and self.is_semestral_em_calendario_anual():
            inicio_etapa = self.calendario_academico.data_fim_etapa_2 + timedelta(1)
        return inicio_etapa

    def get_fim_etapa_final(self):
        fim_etapa = self.calendario_academico.data_fim_prova_final
        if not self.segundo_semestre and self.is_semestral_em_calendario_anual():
            fim_etapa = self.calendario_academico.data_inicio_etapa_3 - timedelta(1)
        elif not self.calendario_academico.data_fim_prova_final:
            fim_etapa = self.calendario_academico.data_fechamento_periodo
        return fim_etapa

    def get_numero_primeira_etapa(self):
        result = '1'
        if self.is_semestral_segundo_semestre():
            result = '3'
        return result

    def get_numero_segunda_etapa(self):
        result = '2'
        if self.is_semestral_segundo_semestre():
            result = '4'
        return result

    def get_label_etapa(self, etapa):
        if etapa == 1:
            return self.get_numero_primeira_etapa()
        elif etapa == 2:
            return self.get_numero_segunda_etapa()
        elif etapa == 5:
            return 'Final'
        else:
            return etapa

    def is_anual(self):
        return self.calendario_academico.qtd_etapas == 4

    def is_semestral(self):
        return self.calendario_academico.qtd_etapas == 2

    def is_semestral_em_calendario_anual(self):
        return self.is_anual() and self.componente_curricular.is_semestral()

    def get_periodicidade(self):
        result = 'Livre'
        if self.is_semestral_em_calendario_anual():
            result = 'Anual (2° semestre)' if self.is_semestral_segundo_semestre() else 'Anual (1° semestre)'
        elif self.is_anual():
            result = 'Anual'
        elif self.is_semestral():
            result = 'Semestral'
        return result

    def possui_aluno_periodo_fechado(self):
        situacoes = [
            MatriculaDiario.SITUACAO_APROVADO,
            MatriculaDiario.SITUACAO_REPROVADO,
            MatriculaDiario.SITUACAO_PENDENTE,
            MatriculaDiario.SITUACAO_APROVADO_REPROVADO_MODULO,
        ]
        return self.matriculadiario_set.filter(situacao__in=situacoes).exists()

    def possui_configuracao_avaliacao_inconsistente(self):
        if self.componente_curricular.qtd_avaliacoes == 0:
            return False
        etapas = list(range(1, self.componente_curricular.qtd_avaliacoes + 1))
        etapas = [*etapas, 5]
        return any(not self.configuracaoavaliacao_set.filter(etapa=etapa).exists() for etapa in etapas)

    def get_horarios_com_choque(self, verificar_apenas_existencia=False):
        qs_matriculas_periodos = MatriculaPeriodo.objects.filter(
            matriculadiario__diario=self, matriculadiario__situacao=MatriculaDiario.SITUACAO_CURSANDO
        )
        ids_matriculas_periodos = qs_matriculas_periodos.distinct().values_list('id', flat=True)
        semestre_oposto = not self.segundo_semestre
        horarios_choque = {}
        for horario_aula_diario in self.horarioauladiario_set.exclude(diario__segundo_semestre=semestre_oposto):
            qs_horarios_com_choque = (
                HorarioAulaDiario.objects.filter(
                    dia_semana=horario_aula_diario.dia_semana,
                    horario_aula=horario_aula_diario.horario_aula,
                    diario__matriculadiario__matricula_periodo__id__in=ids_matriculas_periodos,
                )
                .exclude(id=horario_aula_diario.id)
                .exclude(diario__segundo_semestre=semestre_oposto)
                .distinct()
            )
            if verificar_apenas_existencia:
                return qs_horarios_com_choque

            horarios_com_choque = []
            for horario_aula_diario_choque in qs_horarios_com_choque:
                horario_aula_diario_choque.matriculas_periodos = (
                    qs_matriculas_periodos.filter(matriculadiario__diario__horarioauladiario=horario_aula_diario_choque)
                    .distinct()
                    .order_by('aluno__pessoa_fisica__nome')
                )
                horarios_com_choque.append(horario_aula_diario_choque)
            if horarios_com_choque:
                horarios_choque.update({horario_aula_diario: horarios_com_choque})
        return horarios_choque

    def pode_ser_dividido_ao_meio(self):
        return not NotaAvaliacao.objects.filter(matricula_diario__diario=self, nota__isnull=False).exists()

    @transaction.atomic
    def gerar_configuracoes_avaliacao(self):
        etapas = list(range(1, self.componente_curricular.qtd_avaliacoes + 1))
        if etapas:
            for etapa in [*etapas, 5]:
                if not self.configuracaoavaliacao_set.filter(etapa=etapa).exists():
                    configuracao_avaliacao = self.gerar_configuracao_avaliacao(etapa)

                    for matricula_diario in self.matriculadiario_set.all():
                        matricula_diario.criar_registros_notas_etapa(etapa, configuracao_avaliacao.itemconfiguracaoavaliacao_set.all())

    def get_qtd_alunos_matriculados(self):
        return self.matriculadiario_set.count()

    def get_qtd_alunos_cursando(self):
        return self.matriculadiario_set.filter(situacao=MatriculaDiario.SITUACAO_CURSANDO).count()

    @transaction.atomic
    def dividir(self, professor=None, matriculas_diario=None):
        itens_configuracao_avaliacao_dict, novo_diario = self.iniciar_divisao_diario(professor)

        # dividindo o diário ao meio caso os alunos não teham sido especificados
        if not matriculas_diario:
            matriculas_diario = self.matriculadiario_set.all()[self.matriculadiario_set.count() / 2 :]

        self.finalizar_divisao_diario(itens_configuracao_avaliacao_dict, matriculas_diario, novo_diario)
        return novo_diario

    @transaction.atomic
    def dividir_reprovados_dependentes(self, professor=None):
        itens_configuracao_avaliacao_dict, novo_diario = self.iniciar_divisao_diario(professor)
        ids = (
            NotaAvaliacao.objects.filter(matricula_diario__diario=self, nota__isnull=False)
            .values_list('matricula_diario', flat=True)
            .order_by('matricula_diario')
            .distinct()
        )
        matriculas_diario_reprovados = []
        for matricula_diario in self.matriculadiario_set.exclude(id__in=ids):
            if matricula_diario.esteve_reprovado():
                matriculas_diario_reprovados.append(matricula_diario)

        self.finalizar_divisao_diario(itens_configuracao_avaliacao_dict, matriculas_diario_reprovados, novo_diario)
        return novo_diario

    @transaction.atomic
    def replicar(self):
        _, novo_diario = self.iniciar_divisao_diario(None)
        novo_diario.local_aula = None
        novo_diario.local_laboratorio = None
        novo_diario.save()
        return novo_diario

    @transaction.atomic
    def iniciar_divisao_diario(self, professor):
        novo_diario = Diario.objects.get(pk=self.pk)
        # criando um novo diário igual ao anterior
        novo_diario.pk = None
        novo_diario.dividindo = True
        novo_diario.save()
        # definindo o novo professor
        if professor:
            professor_diario = ProfessorDiario()
            professor_diario.professor = professor
            professor_diario.diario = novo_diario
            professor_diario.tipo = TipoProfessorDiario.objects.get(pk=1)
            professor_diario.percentual_ch = 100

            if novo_diario.componente_curricular:
                qtd_avaliacoes = novo_diario.componente_curricular.qtd_avaliacoes
                professor_diario.data_inicio_etapa_1 = novo_diario.get_inicio_etapa_1()
                professor_diario.data_fim_etapa_1 = self.flexibilizar_data(novo_diario.get_fim_etapa_1())

            if qtd_avaliacoes >= 2:
                professor_diario.data_inicio_etapa_2 = novo_diario.get_inicio_etapa_2()
                professor_diario.data_fim_etapa_2 = self.flexibilizar_data(novo_diario.get_fim_etapa_2())

            if qtd_avaliacoes >= 4:
                professor_diario.data_inicio_etapa_3 = novo_diario.get_inicio_etapa_3()
                professor_diario.data_fim_etapa_3 = self.flexibilizar_data(novo_diario.get_fim_etapa_3())
                professor_diario.data_inicio_etapa_4 = novo_diario.get_inicio_etapa_4()
                professor_diario.data_fim_etapa_4 = self.flexibilizar_data(novo_diario.get_fim_etapa_4())

            if qtd_avaliacoes > 0:
                professor_diario.data_inicio_etapa_final = novo_diario.get_inicio_etapa_final()
                professor_diario.data_fim_etapa_final = self.flexibilizar_data(novo_diario.get_fim_etapa_final())

            professor_diario.save()

        itens_configuracao_avaliacao_dict = {}
        # replicando as configurações de avaliação baseado no diário anterior
        for configuracao_avaliacao in ConfiguracaoAvaliacao.objects.filter(diario=self):
            nova_configuracao = ConfiguracaoAvaliacao.objects.get(pk=configuracao_avaliacao.pk)
            nova_configuracao.id = None
            nova_configuracao.diario = novo_diario
            nova_configuracao.save()
            # replicando também os itens de configuração
            for item_configuracao_avaliacao in configuracao_avaliacao.itemconfiguracaoavaliacao_set.all():
                novo_item_configuracao_avaliacao = ItemConfiguracaoAvaliacao.objects.get(pk=item_configuracao_avaliacao.pk)
                novo_item_configuracao_avaliacao.id = None
                novo_item_configuracao_avaliacao.configuracao_avaliacao = nova_configuracao
                novo_item_configuracao_avaliacao.save()
                itens_configuracao_avaliacao_dict[item_configuracao_avaliacao.pk] = novo_item_configuracao_avaliacao

        return itens_configuracao_avaliacao_dict, novo_diario

    def flexibilizar_data(self, data):
        if not data:
            return None
        return somar_dias(data, 7)

    def finalizar_divisao_diario(self, itens_configuracao_avaliacao_dict, matriculas_diario, novo_diario):
        # transferindo os alunos par ao novo diário
        for matricula_diario in matriculas_diario:
            # excluindo as faltas do diário antigo
            matricula_diario.falta_set.all().delete()

            matricula_diario.diario = novo_diario
            # alterando a referencia para os novos itens de configuração criados anteriormente
            for nota_avaliacao in matricula_diario.notaavaliacao_set.all():
                nota_avaliacao.item_configuracao_avaliacao = itens_configuracao_avaliacao_dict[nota_avaliacao.item_configuracao_avaliacao.id]
                nota_avaliacao.save()

            matricula_diario.save()

    def configuracao_avaliacao_1(self):
        try:
            try:
                return self._configuracao_avaliacao_1
            except AttributeError:
                self._configuracao_avaliacao_1 = self.configuracaoavaliacao_set.get(etapa=1)
                return self._configuracao_avaliacao_1
        except ConfiguracaoAvaliacao.DoesNotExist:
            return None

    def configuracao_avaliacao_2(self):
        try:
            try:
                return self._configuracao_avaliacao_2
            except Exception:
                self._configuracao_avaliacao_2 = self.configuracaoavaliacao_set.get(etapa=2)
                return self._configuracao_avaliacao_2
        except ConfiguracaoAvaliacao.DoesNotExist:
            return None

    def configuracao_avaliacao_3(self):
        try:
            try:
                return self._configuracao_avaliacao_3
            except Exception:
                self._configuracao_avaliacao_3 = self.configuracaoavaliacao_set.get(etapa=3)
                return self._configuracao_avaliacao_3
        except ConfiguracaoAvaliacao.DoesNotExist:
            return None

    def configuracao_avaliacao_4(self):
        try:
            try:
                return self._configuracao_avaliacao_4
            except Exception:
                self._configuracao_avaliacao_4 = self.configuracaoavaliacao_set.get(etapa=4)
                return self._configuracao_avaliacao_4
        except ConfiguracaoAvaliacao.DoesNotExist:
            return None

    def configuracao_avaliacao_5(self):
        try:
            try:
                return self._configuracao_avaliacao_5
            except Exception:
                self._configuracao_avaliacao_5 = self.configuracaoavaliacao_set.get(etapa=5)
                return self._configuracao_avaliacao_5
        except ConfiguracaoAvaliacao.DoesNotExist:
            return None

    def get_polos(self):
        ids = self.matriculadiario_set.values_list('matricula_periodo__aluno__polo__id', flat=True)
        qs = Polo.objects.filter(id__in=ids)
        return qs

    def get_matriculas_diario(self):
        matriculas_diario = self.matriculadiario_set.all()
        if not running_tests():
            matriculas_diario = matriculas_diario.order_by('matricula_periodo__aluno__pessoa_fisica__nome')
        return matriculas_diario

    def get_matriculas_diario_por_polo(self, pk=None):
        lista = []
        polos = self.get_polos()
        if pk:
            polos = polos.filter(pk=pk)
        for polo in polos:
            matriculas_diario = self.matriculadiario_set.filter(matricula_periodo__aluno__polo=polo)
            if not running_tests():
                matriculas_diario = matriculas_diario.order_by('matricula_periodo__aluno__pessoa_fisica__nome')
            lista.append(matriculas_diario)

        qs = self.matriculadiario_set.filter(matricula_periodo__aluno__polo__isnull=True)
        if qs.exists():
            if not running_tests():
                qs = qs.order_by('matricula_periodo__aluno__pessoa_fisica__nome')
            lista.append(qs)

        return lista

    def get_descricao_dinamica(self):
        if self.componente_curricular.is_dinamico and self.descricao_dinamica:
            return f' ({self.descricao_dinamica})'
        return ''

    def get_qtd_pedidos_nao_processados(self):
        return self.pedidomatriculadiario_set.filter(data_processamento__isnull=True).count()

    def get_sigla(self):
        if self.id:
            return f'({self.id}) {self.componente_curricular.componente.sigla}'
        else:
            return self.componente_curricular.componente.sigla

    def get_professor_principal(self):
        return self.get_professores().first()

    def get_professores(self):
        return self.professordiario_set.all().select_related('professor__vinculo__pessoa').order_by('tipo_id', 'id')

    def get_professores_display(self):
        return Professor.objects.filter(pk__in=self.get_professores().values_list('professor_id', flat=True))

    def get_nomes_professores(self, excluir_tutores=False):
        lista_nomes = []
        qs = self.get_professores()
        if excluir_tutores:
            qs = qs.exclude(tipo__descricao='Tutor')
        for professordiario in qs:
            lista_nomes.append(format(professordiario.professor.vinculo.pessoa.nome_usual))

        return ', '.join(lista_nomes)

    def get_alunos_ativos(self):
        return self.matriculadiario_set.exclude(
            situacao__in=(
                MatriculaDiario.SITUACAO_CANCELADO,
                MatriculaDiario.SITUACAO_DISPENSADO,
                MatriculaDiario.SITUACAO_TRANCADO,
                MatriculaDiario.SITUACAO_TRANSFERIDO,
            )
        )

    def get_quantidade_alunos_ativos(self):
        return self.get_alunos_ativos().count()

    def get_absolute_url(self):
        return f'/edu/diario/{self.pk:d}/'

    def is_professor_diario(self, user):
        return self.get_professores().filter(professor__vinculo__user_id=user.id).exists()

    def is_ultima_etapa_posse_professor(self):
        qtd_total_etapas = self.componente_curricular.qtd_avaliacoes + 1
        qtd_etapas_entregues = 0
        for etapa in [*list(range(1, self.componente_curricular.qtd_avaliacoes + 1)), 5]:
            if getattr(self, f'posse_etapa_{etapa}') == Diario.POSSE_REGISTRO_ESCOLAR:
                qtd_etapas_entregues += 1
        return qtd_etapas_entregues == qtd_total_etapas - 1

    def entregar_etapa(self, etapa):
        setattr(self, f'posse_etapa_{etapa}', Diario.POSSE_REGISTRO_ESCOLAR)
        self.save()

    def pode_ser_excluido(self):
        return not self.matriculadiario_set.exists()

    def pode_ser_entregue_sem_nota(self):
        return datetime.date.today() > self.get_fim_etapa_final() and (
            self.componente_curricular.pode_fechar_pendencia or self.componente_curricular.qtd_avaliacoes == 0
        )

    def pode_ser_entregue_com_pedencia(self):
        return datetime.date.today() > self.get_fim_etapa_final() and self.componente_curricular.pode_fechar_pendencia

    def entregar_etapa_como_professor(self, etapa, entregar_nota_vazia=False):
        etapa = int(etapa)

        inativos = [MatriculaDiario.SITUACAO_CANCELADO, MatriculaDiario.SITUACAO_TRANSFERIDO, MatriculaDiario.SITUACAO_TRANCADO]
        if (
            etapa == 1
            and self.componente_curricular.qtd_avaliacoes > 0
            and self.matriculadiario_set.exclude(situacao__in=inativos)
            .filter(matricula_periodo__situacao=SituacaoMatriculaPeriodo.MATRICULADO, nota_1__isnull=True)
            .exists()
            and not (self.pode_ser_entregue_sem_nota() or entregar_nota_vazia)
        ):
            raise Exception('A etapa só pode ser entregue quando todas as notas forem lançadas.')
        if (
            etapa == 2
            and self.matriculadiario_set.exclude(situacao__in=inativos)
            .filter(matricula_periodo__situacao=SituacaoMatriculaPeriodo.MATRICULADO, nota_2__isnull=True)
            .exists()
            and not (self.pode_ser_entregue_sem_nota() or entregar_nota_vazia)
        ):
            raise Exception('A etapa só pode ser entregue quando todas as notas forem lançadas.')
        if (
            etapa == 3
            and self.matriculadiario_set.exclude(situacao__in=inativos)
            .filter(matricula_periodo__situacao=SituacaoMatriculaPeriodo.MATRICULADO, nota_3__isnull=True)
            .exists()
            and not (self.pode_ser_entregue_sem_nota() or entregar_nota_vazia)
        ):
            raise Exception('A etapa só pode ser entregue quando todas as notas forem lançadas.')
        if (
            etapa == 4
            and self.matriculadiario_set.exclude(situacao__in=inativos)
            .filter(matricula_periodo__situacao=SituacaoMatriculaPeriodo.MATRICULADO, nota_4__isnull=True)
            .exists()
            and not (self.pode_ser_entregue_sem_nota() or entregar_nota_vazia)
        ):
            raise Exception('A etapa só pode ser entregue quando todas as notas forem lançadas.')
        if etapa != 5 and not self.get_aulas(etapa) and not self.estrutura_curso.pode_entregar_etapa_sem_aula:
            raise Exception('Etapas sem aulas cadastradas não podem ser entregues.')
        if etapa == self.componente_curricular.qtd_avaliacoes:
            if not self.cumpriu_carga_horaria_minina():
                raise Exception(f'A carga horária mínima ({self.get_carga_horaria_minima()} aulas) ainda não foi registrada.')
            if not self.cumpriu_aulas_ead():
                raise Exception(f'A quantidade exigida de aulas EAD ({self.componente_curricular.qtd_aulas_ead} aulas) ainda não foi registrada.')

        if (
            etapa != 5
            and self.is_ultima_etapa_posse_professor()
            and self.matriculadiario_set.filter(prova_final_pendente=True, nota_final__isnull=True).exists()
        ):
            raise Exception(
                'Esta etapa não pode ser entregue, pois há aluno(s) com nota insuficiente para aprovação. Solicite o relançamento da etapa final.'
            )

        for matricula_diario in self.matriculadiario_set.filter(situacao=MatriculaDiario.SITUACAO_CURSANDO):
            if etapa == 5 and not matricula_diario.is_em_prova_final():  # não calcula média da nota_final de aluno aprovado ou reprovado direto
                matricula_diario.registrar_nota_etapa(etapa, False)
            elif (etapa == 5 and matricula_diario.is_em_prova_final()) or (
                entregar_nota_vazia and not matricula_diario.diario.componente_curricular.pode_fechar_pendencia
            ):
                matricula_diario.registrar_nota_etapa(etapa, True)
            else:
                matricula_diario.registrar_nota_etapa(etapa, False)
        for matricula_diario in self.matriculadiario_set.exclude(situacao=MatriculaDiario.SITUACAO_CURSANDO):
            matricula_diario.registrar_nota_etapa(etapa, False)
        self.entregar_etapa(etapa)

        if self.componente_curricular.qtd_avaliacoes == 0:
            self.entregar_etapa(5)
        elif etapa == self.componente_curricular.qtd_avaliacoes and not self.is_lancamento_conceito():
            entregar_etapa_final = True
            for matricula_diario in self.matriculadiario_set.all():
                if matricula_diario.is_em_prova_final():
                    entregar_etapa_final = False
                    break
            if entregar_etapa_final:
                self.entregar_etapa(5)

    def em_posse_do_registro(self, etapa=None):
        retorno = True
        if etapa:
            retorno = getattr(self, f'posse_etapa_{etapa}') == Diario.POSSE_REGISTRO_ESCOLAR
        else:
            for etapa in [*list(range(1, self.componente_curricular.qtd_avaliacoes + 1)), 5]:
                retorno = retorno and getattr(self, f'posse_etapa_{etapa}') == Diario.POSSE_REGISTRO_ESCOLAR
        return retorno

    def get_lista_etapas(self):
        if self.componente_curricular.qtd_avaliacoes == 0:
            return [1]
        return list(range(1, self.componente_curricular.qtd_avaliacoes + 1))

    def etapas_anteriores_entegues(self, etapa):
        for num_etapa in [*self.get_lista_etapas(), 5]:
            if num_etapa < etapa:
                if getattr(self, f'posse_etapa_{num_etapa}') != Diario.POSSE_REGISTRO_ESCOLAR:
                    return False
        return True

    def get_num_etapa_posse_professor(self):
        for num_etapa in [*self.get_lista_etapas(), 5]:
            if getattr(self, f'posse_etapa_{num_etapa}') != Diario.POSSE_REGISTRO_ESCOLAR:
                return num_etapa
        return 1

    def etapa_1_em_posse_do_registro(self):
        return self.posse_etapa_1 == Diario.POSSE_REGISTRO_ESCOLAR

    def etapa_2_em_posse_do_registro(self):
        return self.posse_etapa_2 == Diario.POSSE_REGISTRO_ESCOLAR

    def etapa_3_em_posse_do_registro(self):
        return self.posse_etapa_3 == Diario.POSSE_REGISTRO_ESCOLAR

    def etapa_4_em_posse_do_registro(self):
        return self.posse_etapa_4 == Diario.POSSE_REGISTRO_ESCOLAR

    def etapa_5_em_posse_do_registro(self):
        return self.posse_etapa_5 == Diario.POSSE_REGISTRO_ESCOLAR

    def etapa_1_em_atraso(self):
        return not self.etapa_1_em_posse_do_registro() and datetime.date.today() > self.get_fim_etapa_1()

    def etapa_2_em_atraso(self):
        fim_etapa = self.get_fim_etapa_2()
        return not self.etapa_2_em_posse_do_registro() and fim_etapa and datetime.date.today() > fim_etapa

    def etapa_3_em_atraso(self):
        fim_etapa = self.get_fim_etapa_3()
        return not self.etapa_3_em_posse_do_registro() and fim_etapa and datetime.date.today() > fim_etapa

    def etapa_4_em_atraso(self):
        fim_etapa = self.get_fim_etapa_4()
        return not self.etapa_4_em_posse_do_registro() and fim_etapa and datetime.date.today() > fim_etapa

    def etapa_5_em_atraso(self):
        return not self.etapa_5_em_posse_do_registro() and datetime.date.today() > self.get_fim_etapa_final()

    def get_aulas(self, etapa=None):
        qs = Aula.objects.filter(professor_diario__diario=self).order_by('-data', '-id').select_related('professor_diario')
        if etapa:
            return qs.filter(etapa=etapa)
        return qs

    def get_horas_aulas_etapa_1(self):
        return self.get_horas_aulas(1)

    def get_horas_aulas_etapa_2(self):
        return self.get_horas_aulas(2)

    def get_horas_aulas_etapa_3(self):
        return self.get_horas_aulas(3)

    def get_horas_aulas_etapa_4(self):
        return self.get_horas_aulas(4)

    def get_horas_aulas_etapa_5(self):
        return self.get_horas_aulas(5)

    def get_horas_aulas(self, etapa=None):
        return self.get_aulas(etapa).aggregate(Sum('quantidade')).get('quantidade__sum') or 0

    def get_carga_horaria_minima(self):
        return round(self.get_carga_horaria_presencial() * self.percentual_minimo_ch * Decimal('0.01'))

    def get_carga_horaria(self):
        return self.componente_curricular.componente.get_ch_hora_aula()

    def get_carga_horaria_presencial(self, relogio=False):
        # se relogio for False, retornar quantidade de aulas (h/a). Se for True, retorna em horas relógio (h/r).
        if self.componente_curricular.matriz.estrutura.limitar_ch_por_tipo_aula:
            ch = 0
            ch += self.get_carga_horaria_maxima_teorica(relogio=relogio)
            ch += self.get_carga_horaria_maxima_pratica(relogio=relogio)
            ch += self.get_carga_horaria_maxima_extensao(relogio=relogio)
            ch += self.get_carga_horaria_maxima_pcc(relogio=relogio)
            ch += self.get_carga_horaria_maxima_visita_tecnica(relogio=relogio)
            return ch
        else:
            fator_conversao = 1 if relogio else self.componente_curricular.componente.get_fator_conversao_hora_aula()
            result = self.componente_curricular.get_ch_presencial() * fator_conversao
            return result if settings.COMPONENTE_CH_DECIMAL and relogio else round(result)

    def get_carga_horaria_maxima_teorica(self, relogio=False):
        fator_conversao = 1 if relogio else self.componente_curricular.componente.get_fator_conversao_hora_aula()
        if self.componente_curricular.matriz.estrutura.limitar_ch_por_tipo_aula:
            return round(self.componente_curricular.get_ch_presencial() * fator_conversao)
        return None

    def get_carga_horaria_maxima_pratica(self, relogio=False):
        fator_conversao = 1 if relogio else self.componente_curricular.componente.get_fator_conversao_hora_aula()
        if self.componente_curricular.matriz.estrutura.limitar_ch_por_tipo_aula:
            return round(self.componente_curricular.get_ch_pratica() * fator_conversao)
        return None

    def get_carga_horaria_maxima_extensao(self, relogio=False):
        fator_conversao = 1 if relogio else self.componente_curricular.componente.get_fator_conversao_hora_aula()
        if self.componente_curricular.matriz.estrutura.limitar_ch_por_tipo_aula:
            return round(self.componente_curricular.get_ch_extensao() * fator_conversao)
        return None

    def get_carga_horaria_maxima_pcc(self, relogio=False):
        fator_conversao = 1 if relogio else self.componente_curricular.componente.get_fator_conversao_hora_aula()
        if self.componente_curricular.matriz.estrutura.limitar_ch_por_tipo_aula:
            return round(self.componente_curricular.get_ch_pcc() * fator_conversao)
        return None

    def get_carga_horaria_maxima_visita_tecnica(self, relogio=False):
        fator_conversao = 1 if relogio else self.componente_curricular.componente.get_fator_conversao_hora_aula()
        if self.componente_curricular.matriz.estrutura.limitar_ch_por_tipo_aula:
            return round(self.componente_curricular.get_ch_visita_tecnica() * fator_conversao)
        return None

    def get_carga_horaria_maxima_ead(self):
        if self.componente_curricular.percentual_maximo_ead:
            return Decimal(round(self.get_carga_horaria_presencial() * self.componente_curricular.percentual_maximo_ead / 100))
        return self.componente_curricular.qtd_aulas_ead

    def get_carga_horaria_relogio(self):
        return self.componente_curricular.componente.get_ch_hora_relogio()

    def get_carga_horaria_cumprida_por_tipo(self, tipo, relogio=False):
        fator_conversao = self.componente_curricular.componente.get_fator_conversao_hora_aula() if relogio else 1
        qs = Aula.objects.filter(professor_diario__diario=self, data__lte=datetime.date.today(), tipo=tipo)
        return int((qs.aggregate(Sum('quantidade')).get('quantidade__sum') or 0) / fator_conversao)

    def get_carga_horaria_ead_disponivel(self):
        if self.componente_curricular.possui_ch_ead():
            qtd_registrada = Aula.objects.filter(professor_diario__diario=self, ead=True).aggregate(Sum('quantidade')).get('quantidade__sum') or 0
            return max(self.get_carga_horaria_maxima_ead() - qtd_registrada, 0)
        return 0

    def get_carga_horaria_cumprida(self):
        return (
            self.get_carga_horaria_teorica_contabilizada()
            + self.get_carga_horaria_pratica_contabilizada()
            + self.get_carga_horaria_extensao_contabilizada()
            + self.get_carga_horaria_pcc_contabilizada()
            + self.get_carga_horaria_visita_tecnica_contabilizada()
        )

    def get_carga_horaria_teorica_ministrada(self, relogio=False):
        return self.get_carga_horaria_cumprida_por_tipo(Aula.AULA, relogio=relogio)

    def get_carga_horaria_teorica_contabilizada(self, relogio=False):
        maxima = self.get_carga_horaria_maxima_teorica(relogio=relogio)
        if maxima is None or maxima > 0:
            ch = self.get_carga_horaria_teorica_ministrada(relogio=relogio)
            return ch if maxima is None or ch < maxima else maxima
        return 0

    def get_carga_horaria_pratica_ministrada(self, relogio=False):
        return self.get_carga_horaria_cumprida_por_tipo(Aula.PRATICA, relogio=relogio)

    def get_carga_horaria_pratica_contabilizada(self, relogio=False):
        maxima = self.get_carga_horaria_maxima_pratica(relogio=relogio)
        if maxima is None or maxima > 0:
            ch = self.get_carga_horaria_pratica_ministrada(relogio=relogio)
            return ch if maxima is None or ch < maxima else maxima
        return 0

    def get_carga_horaria_extensao_ministrada(self, relogio=False):
        return self.get_carga_horaria_cumprida_por_tipo(Aula.EXTENSAO, relogio=relogio)

    def get_carga_horaria_extensao_contabilizada(self, relogio=False):
        maxima = self.get_carga_horaria_maxima_extensao(relogio=relogio)
        if maxima is None or maxima > 0:
            ch = self.get_carga_horaria_extensao_ministrada(relogio=relogio)
            return ch if maxima is None or ch < maxima else maxima
        return 0

    def get_carga_horaria_pcc_ministrada(self, relogio=False):
        return self.get_carga_horaria_cumprida_por_tipo(Aula.PRATICA_COMO_COMPONENTE_CURRICULAR, relogio=relogio)

    def get_carga_horaria_pcc_contabilizada(self, relogio=False):
        maxima = self.get_carga_horaria_maxima_pcc(relogio=relogio)
        if maxima is None or maxima > 0:
            ch = self.get_carga_horaria_pcc_ministrada(relogio=relogio)
            return ch if maxima is None or ch < maxima else maxima
        return 0

    def get_carga_horaria_relogio_pcc_contabilizada(self):
        return self.get_carga_horaria_pcc_contabilizada(relogio=True)

    def get_carga_horaria_visita_tecnica_ministrada(self, relogio=False):
        return self.get_carga_horaria_cumprida_por_tipo(Aula.VISITA_TECNICA, relogio=relogio)

    def get_carga_horaria_visita_tecnica_contabilizada(self, relogio=False):
        maxima = self.get_carga_horaria_maxima_visita_tecnica(relogio=relogio)
        if maxima is None or maxima > 0:
            ch = self.get_carga_horaria_visita_tecnica_ministrada(relogio=relogio)
            return ch if maxima is None or ch < maxima else maxima
        return 0

    def get_carga_horaria_relogio_visita_tecnica_contabilizada(self):
        return self.get_carga_horaria_visita_tecnica_contabilizada(relogio=True)

    def get_percentual_carga_horaria_cumprida(self, adicional=0):
        if self.get_carga_horaria_presencial():
            percentual = int((100 * (self.get_carga_horaria_cumprida() + adicional)) / self.get_carga_horaria_presencial())
            return percentual > 100 and 100 or percentual
        else:
            return 100

    def cumpriu_carga_horaria_minina(self):
        return self.get_percentual_carga_horaria_cumprida() >= self.percentual_minimo_ch

    def cumpriu_aulas_ead(self):
        if self.componente_curricular.qtd_aulas_ead:
            aulas_ead = Aula.objects.filter(professor_diario__diario=self, ead=True).aggregate(Sum('quantidade')).get('quantidade__sum') or 0
            return aulas_ead == self.componente_curricular.qtd_aulas_ead
        return True

    def is_aberto(self):
        return self.situacao == Diario.SITUACAO_ABERTO

    def is_lancamento_conceito(self):
        return self.componente_curricular.avaliacao_por_conceito and self.componente_curricular.matriz.estrutura.is_lancamento_conceito()

    def fechar(self):
        if self.situacao != Diario.SITUACAO_FECHADO and not self.matriculadiario_set.filter(situacao=MatriculaDiario.SITUACAO_CURSANDO).exists():
            self.situacao = Diario.SITUACAO_FECHADO
            self.posse_etapa_1 = Diario.POSSE_REGISTRO_ESCOLAR
            self.posse_etapa_2 = Diario.POSSE_REGISTRO_ESCOLAR
            self.posse_etapa_3 = Diario.POSSE_REGISTRO_ESCOLAR
            self.posse_etapa_4 = Diario.POSSE_REGISTRO_ESCOLAR
            self.posse_etapa_5 = Diario.POSSE_REGISTRO_ESCOLAR
            self.save()

    def abrir(self):
        if self.situacao != Diario.SITUACAO_ABERTO:
            self.situacao = Diario.SITUACAO_ABERTO
            self.save()

    def is_carga_horaria_minima_cumprida(self):
        return self.get_percentual_carga_horaria_cumprida() >= 90

    def get_aulas_etapa_1(self):
        return self.get_aulas(1)

    def get_aulas_etapa_2(self):
        return self.get_aulas(2)

    def get_aulas_etapa_3(self):
        return self.get_aulas(3)

    def get_aulas_etapa_4(self):
        return self.get_aulas(4)

    def get_aulas_etapa_5(self):
        return self.get_aulas(5)

    def get_horario_aulas(self):
        output = []
        turnos_ids = self.horarioauladiario_set.all().values_list('horario_aula__turno', flat=True).distinct()
        for turno in Turno.objects.filter(id__in=turnos_ids):
            dias_semana = (
                self.horarioauladiario_set.filter(horario_aula__turno=turno).order_by('dia_semana').values_list('dia_semana', flat=True).distinct()
            )
            for dia_semana in dias_semana:
                if output:
                    output.append(' / ')
                numeros = []
                for numero in (
                    self.horarioauladiario_set.filter(horario_aula__turno=turno, dia_semana=dia_semana)
                    .values_list('horario_aula__numero', flat=True)
                    .distinct()
                ):
                    if numero not in numeros:
                        numeros.append(str(numero))
                numeros.sort()
                output.append('{}{}{}'.format(dia_semana + 1, turno.descricao[0], ''.join(numeros)))
        return ''.join(output)

    @transaction.atomic
    def processar_horarios(self, dados):
        self.horarioauladiario_set.all().delete()
        for horario in dados.POST.getlist('horario'):
            horario_aula_pk, dia_semana = horario.split(';')
            horario_aula = HorarioAula.objects.get(pk=horario_aula_pk)
            HorarioAulaDiario.objects.create(diario=self, dia_semana=dia_semana, horario_aula=horario_aula)

    def get_horarios_aula_por_turno(self):
        turnos_ids = self.horario_campus.horarioaula_set.values_list('turno_id', flat=True).distinct()
        dias_semana = HorarioAulaDiario.DIA_SEMANA_CHOICES
        turnos = Turno.objects.filter(id__in=turnos_ids).order_by('-id')
        for turno in turnos:
            turno.horarios_aula = []
            turno.dias_semana = dias_semana
            for horario_aula in turno.horarioaula_set.filter(horario_campus=self.horario_campus):
                horario_aula.dias_semana = []
                for dia_semana in dias_semana:
                    numero_semama = dia_semana[0]
                    marcado = False
                    horarios = []
                    descricao = ''
                    qs = self.horarioauladiario_set.filter(dia_semana=numero_semama, horario_aula=horario_aula)
                    marcado = qs.count()
                    if marcado:
                        descricao = f'{qs[0].diario.componente_curricular.componente.descricao_historico}{qs[0].diario.get_descricao_dinamica()}'
                        horarios.append(['diario', qs[0].diario.pk, descricao, qs[0].diario.componente_curricular.componente.sigla])
                    horario_aula.dias_semana.append({'numero': numero_semama, 'marcado': marcado, 'conflito': False, 'horarios': horarios})
                turno.horarios_aula.append(horario_aula)
        return turnos

    @transaction.atomic
    def processar_notas(self, dados):
        etapas = []
        matriculas_diario_pk = []
        emails = []
        for key in list(dados.keys()):
            if ';' in key:
                etapa, matricula_diario_pk, item_configuracao_avaliacao = key.split(';')
                if etapa not in etapas:
                    etapas.append(etapa)
                if matricula_diario_pk not in matriculas_diario_pk:
                    matriculas_diario_pk.append(matricula_diario_pk)
                nota = dados[key].strip()
                if nota == '0':
                    nota = 0
                elif nota == '':
                    nota = None
                else:
                    nota = int(nota)
                NotaAvaliacao.objects.filter(
                    matricula_diario__id=matricula_diario_pk, item_configuracao_avaliacao=item_configuracao_avaliacao
                ).update(nota=nota)
                matriculadiario = MatriculaDiario.objects.get(id=matricula_diario_pk)
                if nota is not None and matriculadiario.matricula_periodo.aluno.email_notificacao:
                    emails.append(matriculadiario.matricula_periodo.aluno.email_notificacao)

        if emails:
            disciplina = self.componente_curricular.componente.descricao
            mensagem = f"""
Caro(a) aluno(a),

Informamos que foi realizado lançamento de nota na disciplina {disciplina}.

            """

            subject = f'[SUAP] Lançamento de Nota - {disciplina}'
            body = mensagem
            from_email = settings.DEFAULT_FROM_EMAIL
            send_mail(subject, body, from_email, [], bcc=emails, fail_silently=True)

        for etapa in etapas:
            for matricula_diario in MatriculaDiario.objects.filter(id__in=matriculas_diario_pk):
                matricula_diario.registrar_nota_etapa(etapa)

    def get_media_notas_by_etapa(self, etapa):
        avg = 'nota_{}'.format(etapa == 5 and 'final' or etapa)
        avg = MatriculaDiario.objects.filter(diario=self).aggregate(Avg(avg))[f'{avg}__avg']
        if avg:
            return round(avg, 0)
        else:
            return 0

    def get_media_medias(self):
        soma = 0
        qs_matriculas_diario = MatriculaDiario.objects.filter(diario=self)
        for matricula_diario in qs_matriculas_diario:
            soma += matricula_diario.get_media_disciplina() or 0
        return round(soma / qs_matriculas_diario.count(), 0)

    def get_media_medias_finais(self):
        soma = 0
        qs_matriculas_diario = MatriculaDiario.objects.filter(diario=self)
        for matricula_diario in qs_matriculas_diario:
            soma += matricula_diario.get_media_final_disciplina() or 0
        return round(soma / qs_matriculas_diario.count(), 0)

    @staticmethod
    def get_diarios_choque_horario(ids_diarios, diario_pivot=None):
        if diario_pivot:
            ids_diarios.append(diario_pivot.pk)

        horarios_diario = HorarioAulaDiario.objects.filter(diario__id__in=ids_diarios).values_list('dia_semana', 'horario_aula')
        horarios = []
        for horario_diario in horarios_diario:
            horarios.append(f'{horario_diario[0]}/{horario_diario[1]}')

        diarios_com_choque = []
        for horario in horarios:
            if horarios.count(horario) > 1:
                horario = horario.split('/')
                qs = Diario.objects.filter(id__in=ids_diarios, horarioauladiario__dia_semana=horario[0], horarioauladiario__horario_aula=horario[1])
                for diario in qs:
                    qs2 = (
                        Diario.objects.filter(
                            calendario_academico__data_inicio__range=(
                                diario.calendario_academico.data_inicio,
                                diario.calendario_academico.data_fechamento_periodo,
                            ),
                            id__in=diario_pivot and [diario_pivot.pk] or ids_diarios,
                            horarioauladiario__dia_semana=horario[0],
                            horarioauladiario__horario_aula=horario[1],
                        )
                        .exclude(ignorar_choque_horario_renovacao_matricula=True)
                        .exclude(id=diario.pk)
                    )
                    if diario.is_semestral_em_calendario_anual():
                        qs2 = qs2.exclude(segundo_semestre=not diario.segundo_semestre)
                    if qs2.exists():
                        if diario not in diarios_com_choque:
                            diarios_com_choque.append(diario)
        return diarios_com_choque

    def get_qtd_vagas_restante(self):
        return self.quantidade_vagas - self.matriculadiario_set.all().count()

    def get_etapas(self):
        etapas = {}
        etapas.update(
            {1: {'posse': self.em_posse_do_registro(1), 'configuracao_avaliacao': self.configuracao_avaliacao_1, 'numero_etapa_exibicao': 1}}
        )
        etapas.update(
            {2: {'posse': self.em_posse_do_registro(2), 'configuracao_avaliacao': self.configuracao_avaliacao_2, 'numero_etapa_exibicao': 2}}
        )
        etapas.update(
            {3: {'posse': self.em_posse_do_registro(3), 'configuracao_avaliacao': self.configuracao_avaliacao_3, 'numero_etapa_exibicao': 3}}
        )
        etapas.update(
            {4: {'posse': self.em_posse_do_registro(4), 'configuracao_avaliacao': self.configuracao_avaliacao_4, 'numero_etapa_exibicao': 4}}
        )
        etapas.update(
            {5: {'posse': self.em_posse_do_registro(5), 'configuracao_avaliacao': self.configuracao_avaliacao_5, 'numero_etapa_exibicao': 'Final'}}
        )
        return etapas

    def _get_search_fields_optimized_content_to_save(self):
        if self.id is None:
            return f'{self.componente_curricular.componente.descricao}{self.componente_curricular.componente.sigla}'
        return '{}{}{}{}'.format(
            self.id,
            self.componente_curricular.componente.descricao,
            self.componente_curricular.componente.sigla,
            ''.join(self.professordiario_set.values_list('professor__vinculo__pessoa__nome', flat=True)),
        )

    @transaction.atomic
    def save(self, *args, **kwargs):
        pk = self.pk
        qtd_etapas = self.componente_curricular.qtd_avaliacoes
        if not pk:
            if qtd_etapas <= 2:
                self.posse_etapa_4 = Diario.POSSE_REGISTRO_ESCOLAR
                self.posse_etapa_3 = Diario.POSSE_REGISTRO_ESCOLAR
            if qtd_etapas < 2:
                self.posse_etapa_2 = Diario.POSSE_REGISTRO_ESCOLAR
        else:
            if self.segundo_semestre != Diario.objects.get(pk=pk).segundo_semestre:
                for professor_diario in self.get_professores():
                    professor_diario.atualizar_data_posse()
        super().save(*args, **kwargs)
        if self.turma.curso_campus.plano_ensino and not self.planoensino_set.exists():
            PlanoEnsino.objects.create(
                diario=self, coordenador_curso=self.turma.curso_campus.coordenador, ementa=self.componente_curricular.ementa or ''
            )

        etapas = list(range(1, self.componente_curricular.qtd_avaliacoes + 1))
        etapas = etapas and [*etapas, 5] or []

        for etapa in etapas:
            attr = f'configuracao_avaliacao_{etapa}'
            if not pk and not getattr(self, attr)() and not hasattr(self, 'dividindo'):
                self.gerar_configuracao_avaliacao(etapa)
        # Salvando novamente para colocar o id no search_fields_optimized. Aqui a linha JÁ
        # existe, então os argumentos da chamada original não podem ser repassados:
        # `objects.create()`/`get_or_create()` passam `force_insert=True`, e reinserir o mesmo
        # pk estoura `IntegrityError: duplicate key value violates unique constraint`. Um
        # `update_fields` do chamador também impediria a gravação do próprio campo que esta
        # segunda chamada existe para atualizar.
        super().save(force_insert=False, using=kwargs.get('using'))

    def gerar_configuracao_avaliacao(self, etapa):
        configuracao_avaliacao = ConfiguracaoAvaliacao.objects.get(pk=1)
        item_configuracao_avaliacao = configuracao_avaliacao.itemconfiguracaoavaliacao_set.first()
        configuracao_avaliacao.pk = None
        configuracao_avaliacao.diario = self
        configuracao_avaliacao.etapa = etapa

        if self.is_lancamento_conceito():
            configuracao_avaliacao.forma_calculo = ConfiguracaoAvaliacao.FORMA_CALCULO_AVALIACAO_CONCEITO

        configuracao_avaliacao.save()

        item_configuracao_avaliacao.pk = None
        item_configuracao_avaliacao.configuracao_avaliacao = configuracao_avaliacao
        item_configuracao_avaliacao.save()

        # gera items de configuração de recuperação
        if etapa != 5 and self.estrutura_curso.permite_recuperacao_etapa:
            item_configuracao_avaliacao_recuperacao = configuracao_avaliacao.itemconfiguracaoavaliacao_set.first()
            item_configuracao_avaliacao_recuperacao.pk = None
            item_configuracao_avaliacao_recuperacao.sigla = 'REC'
            item_configuracao_avaliacao_recuperacao.descricao = 'Recuperação'
            item_configuracao_avaliacao_recuperacao.configuracao_avaliacao = configuracao_avaliacao
            item_configuracao_avaliacao_recuperacao.tipo = ItemConfiguracaoAvaliacao.TIPO_RECUPERACAO
            item_configuracao_avaliacao_recuperacao.save()

        # segunda avaliação obrigatória da etapa para lançamento por conceito
        if etapa != 5 and self.is_lancamento_conceito():
            item_configuracao_avaliacao2 = configuracao_avaliacao.itemconfiguracaoavaliacao_set.first()
            item_configuracao_avaliacao2.pk = None
            item_configuracao_avaliacao2.configuracao_avaliacao = configuracao_avaliacao
            item_configuracao_avaliacao2.sigla = 'A2'
            item_configuracao_avaliacao2.save()

        elif etapa != 5 and self.utiliza_nota_atitudinal():
            configuracao_avaliacao.forma_calculo = ConfiguracaoAvaliacao.FORMA_CALCULO_MEDIA_ATITUDINAL
            configuracao_avaliacao.save()

            item_configuracao_avaliacao2 = configuracao_avaliacao.itemconfiguracaoavaliacao_set.first()
            item_configuracao_avaliacao2.pk = None
            item_configuracao_avaliacao2.configuracao_avaliacao = configuracao_avaliacao
            item_configuracao_avaliacao2.tipo = ItemConfiguracaoAvaliacao.TIPO_ATITUDINAL
            item_configuracao_avaliacao2.sigla = 'AT'
            item_configuracao_avaliacao2.descrição = 'Atitudinal'
            item_configuracao_avaliacao2.save()

        return configuracao_avaliacao

    def utiliza_nota_atitudinal(self):
        return self.turma.matriz.nivel_ensino_id == NivelEnsino.MEDIO and Configuracao.get_valor_por_chave('edu', 'nota_atitudinal')

    @transaction.atomic
    def delete(self, *args, **kwargs):
        if self.pode_ser_excluido():
            # verifica configuração da reserva de sala
            if self.is_reserva_sala_habilitada():
                # cancela as reservas antes de apagar o diário
                self.cancelar_reservas_de_sala()
            if self.diario_primeira_oferta_id:
                Diario.objects.filter(id=self.diario_primeira_oferta_id).update(possui_segunda_oferta=False)
            if self.planoensino_set.exists():
                self.planoensino_set.all().delete()
            super().delete(*args, **kwargs)
        else:
            raise Exception('Este diário não pode ser excluído.')

    @transaction.atomic
    def transferir(self, matriculas_diario, diario_destino):
        matriculas_diario = self.matriculadiario_set.filter(pk__in=matriculas_diario)
        for matricula_diario in matriculas_diario:
            matricula_diario.transferir(diario_destino)

    def get_locais_aula(self):
        locais = []
        if self.local_aula:
            locais.append(self.local_aula)
        if self.local_laboratorio:
            locais.append(self.local_laboratorio)
        locais.extend(list(self.locais_aula_secundarios.all()))
        return locais

    def pendente(self):
        hoje = datetime.date.today()
        qtd_avaliacoes = self.componente_curricular.qtd_avaliacoes
        is_conceito = self.is_lancamento_conceito()
        nota_conceito = is_conceito and 'Conceito' or 'Nota'
        try:
            e1 = qtd_avaliacoes > 0 and self.calendario_academico.data_inicio_etapa_1 < hoje
            e2 = qtd_avaliacoes > 1 and self.calendario_academico.data_inicio_etapa_2 < hoje
            e3 = qtd_avaliacoes > 2 and self.calendario_academico.data_inicio_etapa_3 < hoje
            e4 = qtd_avaliacoes > 3 and self.calendario_academico.data_inicio_etapa_4 < hoje
            e5 = is_conceito and self.calendario_academico.data_inicio_prova_final < hoje
        except TypeError:
            return 'Calendário acadêmico incompatível com a quantidade de etapas do diário.'
        qs = MatriculaDiario.objects.filter(diario=self).filter(situacao=MatriculaDiario.SITUACAO_CURSANDO)
        if e1 and qs.filter(nota_1__isnull=True).exists():
            return f'{nota_conceito} pendente de lançamento na Etapa 1.'
        if e2 and qs.filter(nota_2__isnull=True).exists():
            return f'{nota_conceito} pendente de lançamento na Etapa 2.'
        if e3 and qs.filter(nota_3__isnull=True).exists():
            return f'{nota_conceito} pendente de lançamento na Etapa 3.'
        if e4 and qs.filter(nota_4__isnull=True).exists():
            return f'{nota_conceito} pendente de lançamento na Etapa 4.'
        if e5 and qs.filter(nota_final__isnull=True).exists():
            return f'{nota_conceito} final pendente de lançamento.'
        if self.calendario_academico.data_fim < hoje:
            if not self.cumpriu_carga_horaria_minina():
                return 'CH mínima não cumprida.'
            if not self.cumpriu_aulas_ead():
                return 'Aulas EAD não cumpridas.'

        return False

    def get_periodo_letivo(self):
        return 1 if self.turma.curso_campus.is_anual() else self.periodo_letivo

    def can_change(self, user):
        return perms.realizar_procedimentos_academicos(user, self.turma.curso_campus)

    def pode_avaliar_atividade_extensao(self, user) -> bool:
        if self.em_posse_do_registro():
            return self.can_change(user)
        return self.is_professor_diario(user)

    def pode_reservar_sala(self):
        return (
            self.is_reserva_sala_habilitada
            and (self.local_aula or self.local_laboratorio or self.locais_aula_secundarios.exists())
            and self.horarioauladiario_set.exists()
        )

    def tem_sala_reservada(self):
        return self.horarioauladiario_set.filter(sala__isnull=False).exists()

    def is_reserva_sala_habilitada(self):
        return Configuracao.get_valor_por_chave('edu', 'reservar_sala_no_diario')

    def gerar_justificativa_reserva_sala(self):
        return f'Diário ({self.id}) - {self.componente_curricular.componente.sigla} - {self.componente_curricular.componente.descricao}'

    def cancelar_reservas_de_sala(self):
        with transaction.atomic():
            # é necessário percorrer cada horário para obter a sala de cada um
            for h in self.horarioauladiario_set.all():
                qs_solicitacao = SolicitacaoReservaSala.objects.filter(sala=h.sala, justificativa=self.gerar_justificativa_reserva_sala())
                for s in qs_solicitacao:
                    # é necessário percorrer as reservas de cada solicitação para cancelar todas
                    qs_reservas = ReservaSala.objects.filter(solicitacao=s)
                    for r in qs_reservas:
                        r.cancelar(notificar=False)
                    # muda a situação da solicitação para excluida
                    s.status = SolicitacaoReservaSala.STATUS_EXCLUIDA
                    s.save()
                # remove a sala do horario
                h.sala = None
                h.save()

    def get_horarios_por_dia_semana(self):
        # retornando os horários de aula do diário por dia da semana
        dias_semana = {}
        for horario in HorarioAulaDiario.objects.filter(diario=self):
            if horario.dia_semana not in dias_semana:
                dias_semana[horario.dia_semana] = [horario]
            else:
                dias_semana[horario.dia_semana].append(horario)
        return dias_semana

    def possui_suspensao_aberta(self):
        return self.suspensaodiario_set.filter(Q(fim__isnull=True) | Q(fim__gt=datetime.date.today())).exists()

    def get_suspensao_vigente(self):
        return self.suspensaodiario_set.filter(Q(fim__isnull=True) | Q(fim__gte=datetime.date.today())).last()

    def estah_suspenso(self):
        return self.possui_suspensao_aberta() and self.get_suspensao_vigente().inicio <= datetime.date.today()

    def suspender(self, inicio, justificativa, motivo, notificar=True):
        """
        Suspende o diário para efeitos do Programa Pé de Meia
        """
        if not self.possui_suspensao_aberta():
            suspensao_diario = SuspensaoDiario.objects.create(diario=self, inicio=inicio, justificativa=justificativa, motivo=motivo)
            if suspensao_diario:
                professores_vinculados = [professordiario.professor.vinculo for professordiario in self.get_professores()]
                if notificar:
                    texto = (
                        f'<h2>Suspensão do Diário {self}</h2>'
                        f'<p>A suspensão  será iniciada em {inicio.strftime("%d/%m/%Y")}.</p>'
                        f"<p class='more-info'>Para mais informações, acesse: <a href='{self.get_absolute_url()}?tab=ocorrencias'>{self}/</a></p>"
                    )
                    send_notification('[SUAP] Suspensão de Diário', texto, settings.DEFAULT_FROM_EMAIL, professores_vinculados, fail_silently=True)

    def encerrar_suspensao(self, fim, notificar=True):
        """
        Encerra a suspensão do diário para efeitos do Programa Pé de Meia
        """
        if self.possui_suspensao_aberta():
            SuspensaoDiario.objects.filter(diario=self).update(fim=fim)
            professores_vinculados = [professordiario.professor.vinculo for professordiario in self.get_professores()]
            if notificar:
                texto = (
                    f'<h2>Encerramento de Suspensão do Diário {self}</h2>'
                    f'<p>A suspensão  será encerrada em {fim.strftime("%d/%m/%Y")}.</p>'
                    f"<p class='more-info'>Para mais informações, acesse: <a href='{self.get_absolute_url()}?tab=ocorrencias'>{self}/</a></p>"
                )
                send_notification(
                    '[SUAP] Encerramento de Suspensão de Diário', texto, settings.DEFAULT_FROM_EMAIL, professores_vinculados, fail_silently=True
                )


class ProfessorDiario(LogModel):
    SEARCH_FIELDS = ['professor__vinculo__pessoa__pessoa_fisica__search_fields_optimized']

    # Managers
    objects = models.Manager()
    locals = managers.ProfessorDiarioLocalManager()

    diario = models.ForeignKeyPlus('edu.Diario', verbose_name='Diário')
    professor = models.ForeignKeyPlus('edu.Professor', verbose_name='Professor')
    tipo = models.ForeignKeyPlus('edu.TipoProfessorDiario', verbose_name='Tipo', on_delete=models.CASCADE)

    data_inicio_etapa_1 = models.DateFieldPlus(
        verbose_name='Data de Início', help_text='Início da posse do diário para a 1ª etapa', null=True, blank=True
    )
    data_fim_etapa_1 = models.DateFieldPlus(
        verbose_name='Data de Encerramento', help_text='Encerramento da posse incluindo 5 dias de tolerância', null=True, blank=True
    )

    data_inicio_etapa_2 = models.DateFieldPlus(
        verbose_name='Data de Início', help_text='Início da posse do diário para a 2ª etapa', null=True, blank=True
    )
    data_fim_etapa_2 = models.DateFieldPlus(
        verbose_name='Data de Encerramento', help_text='Encerramento da posse incluindo 5 dias de tolerância', null=True, blank=True
    )

    data_inicio_etapa_3 = models.DateFieldPlus(
        verbose_name='Data de Início', help_text='Início da posse do diário para a 3ª etapa', null=True, blank=True
    )
    data_fim_etapa_3 = models.DateFieldPlus(
        verbose_name='Data de Encerramento', help_text='Encerramento da posse incluindo 5 dias de tolerância', null=True, blank=True
    )

    data_inicio_etapa_4 = models.DateFieldPlus(
        verbose_name='Data de Início', help_text='Início da posse do diário para a 4ª etapa', null=True, blank=True
    )
    data_fim_etapa_4 = models.DateFieldPlus(
        verbose_name='Data de Encerramento', help_text='Encerramento da posse incluindo 5 dias de tolerância', null=True, blank=True
    )

    data_inicio_etapa_final = models.DateFieldPlus(
        verbose_name='Data de Início', help_text='Início da posse do diário para a etapa final', null=True, blank=True
    )
    data_fim_etapa_final = models.DateFieldPlus(
        verbose_name='Data de Encerramento', help_text='Encerramento da posse incluindo 5 dias de tolerância', null=True, blank=True
    )
    ativo = models.BooleanField(verbose_name='Ativo', default=True)
    financiamento_externo = models.BooleanField(
        verbose_name='Financiamento Externo',
        default=False,
        help_text='Vínculo com financiamento extraorçamentário (Bolsa, PRONATEC, Mulheres Mil, ETEC, UAB, etc.)',
    )
    percentual_ch = models.PositiveSmallIntegerField(
        verbose_name='Percentual da Carga Horária',
        null=True,
        help_text='Valor entre 0 e 100 correspondente ao percentual da carga horária ministrada pelo professor.',
    )
    periodo_letivo_ch = models.IntegerField(
        verbose_name='Período letivo da carga horária',
        null=True,
        blank=True,
        choices=settings.PERIODO_LETIVO_CHOICES,
        help_text='Informar caso o percentual da carga horária ministrada se refira a apenas um período letivo.',
    )

    # Hints for autocomplete/display: preload professor and diario related fields
    EXT_COMBO_RELATED = {
        'select_related': ['professor', 'diario', 'diario__componente_curricular__componente', 'professor__vinculo__pessoa'],
        'prefetch_related': [],
    }

    class Meta:
        verbose_name = 'Vínculo de Professor em Diário'
        verbose_name_plural = 'Vínculos de Professor em Diário'
        constraints = [models.UniqueConstraint(fields=['diario', 'professor'], name='edu_professordiario_diario_professor_uniq')]

    def __str__(self):
        return f'Vínculo do professor {self.professor.vinculo.pessoa.nome_usual} no diário {self.diario.pk}'

    def is_mesmo_campus_do_curso(self):
        return self.professor.get_uo() == self.diario.horario_campus.uo

    def can_delete(self, user=None):
        return not self.aula_set.exists() and not self.is_rit_publicado()

    def atualizar_data_posse(self):
        qtd_etapas = self.diario.componente_curricular.qtd_avaliacoes
        if qtd_etapas >= 1:
            self.data_inicio_etapa_1 = self.diario.get_inicio_etapa_1()
            if self.diario.get_fim_etapa_1():
                self.data_fim_etapa_1 = somar_dias(self.diario.get_fim_etapa_1(), 7)
            else:
                self.data_fim_etapa_1 = self.diario.get_fim_etapa_1()

        if qtd_etapas >= 2:
            self.data_inicio_etapa_2 = self.diario.get_inicio_etapa_2()
            if self.diario.get_fim_etapa_2():
                self.data_fim_etapa_2 = somar_dias(self.diario.get_fim_etapa_2(), 7)
            else:
                self.data_fim_etapa_2 = self.diario.get_fim_etapa_2()

        if qtd_etapas >= 3:
            self.data_inicio_etapa_3 = self.diario.get_inicio_etapa_3()
            if self.diario.get_fim_etapa_3():
                self.data_fim_etapa_3 = somar_dias(self.diario.get_fim_etapa_3(), 7)
            else:
                self.data_fim_etapa_3 = self.diario.get_fim_etapa_3()

            self.data_inicio_etapa_4 = self.diario.get_inicio_etapa_4()
            if self.diario.get_fim_etapa_4():
                self.data_fim_etapa_4 = somar_dias(self.diario.get_fim_etapa_4(), 7)
            else:
                self.data_fim_etapa_4 = self.diario.get_fim_etapa_4()

        self.data_inicio_etapa_final = self.diario.get_inicio_etapa_final()
        self.data_fim_etapa_final = somar_dias(self.diario.get_fim_etapa_final(), 7)
        self.save()

    def save(self, *args, **kwargs):
        super().save()
        grupo = Group.objects.get(name='Professor')
        self.professor.vinculo.user.groups.add(grupo)
        self.professor.cursos_lecionados.add(self.diario.turma.curso_campus)
        Diario.objects.filter(pk=self.diario_id).update(search_fields_optimized=self.diario._get_search_fields_optimized_content_to_save())

    def delete(self, *args, **kwargs):
        if self.professor.professordiario_set.filter(diario__turma__curso_campus=self.diario.turma.curso_campus).count() == 1:
            self.professor.cursos_lecionados.remove(self.diario.turma.curso_campus)

        super().delete(*args, **kwargs)

    def get_percentual_ch(self, periodo_letivo=None):
        if self.percentual_ch is None:
            return 0
        if periodo_letivo is None or self.periodo_letivo_ch is None or self.periodo_letivo_ch == periodo_letivo:
            return self.percentual_ch
        return 0

    def get_carga_horaria_ministrada(self):
        if hasattr(self, '_carga_horaria_ministrada'):
            return self._carga_horaria_ministrada
        today = datetime.date.today()
        qs = Aula.objects.filter(data__lte=today).filter(Q(professor_diario=self) | Q(outros_professor_diario=self)).distinct()
        return qs.aggregate(Sum('quantidade')).get('quantidade__sum') or 0

    def get_percentual_ch_ministrada(self, ano_novo_calculo=2023):
        if self.diario.ano_letivo.ano < ano_novo_calculo:
            return self.get_percentual_ch()
        else:
            total = self.diario.componente_curricular.componente.get_ch_hora_aula()
            ministrada = self.get_carga_horaria_ministrada()
            return total and int(ministrada * 100 / total) or 0

    def get_qtd_creditos_efetiva(self, periodo_letivo):
        cc = self.diario.componente_curricular
        if self.diario.is_semestral_em_calendario_anual() and self.diario.segundo_semestre != cc.segundo_semestre:
            # inverte período letivo devido a alternância de semestre no diário
            ch_componente = cc.get_ch_semanal(1 if periodo_letivo == 2 else 2)
        elif self.diario.is_anual():
            ch_componente = cc.get_ch_semanal(periodo_letivo)
        else:
            ch_componente = cc.get_ch_semanal(None)
        return math.ceil(ch_componente * (self.get_percentual_ch(periodo_letivo=periodo_letivo) / 100.0))

    def get_periodo_posse(self):
        periodo = []
        vetor = []
        inicio = None
        fim = None

        if self.diario.componente_curricular.qtd_avaliacoes == 0:
            periodo.append((self.data_inicio_etapa_1, self.data_fim_etapa_1))

        vetor.append([self.data_inicio_etapa_1, self.data_fim_etapa_1])
        if self.diario.componente_curricular.qtd_avaliacoes == 2:
            vetor.append([self.data_inicio_etapa_2, self.data_fim_etapa_2])
        if self.diario.componente_curricular.qtd_avaliacoes == 4:
            vetor.append([self.data_inicio_etapa_2, self.data_fim_etapa_2])
            vetor.append([self.data_inicio_etapa_3, self.data_fim_etapa_3])
            vetor.append([self.data_inicio_etapa_4, self.data_fim_etapa_4])
        vetor.append([self.data_inicio_etapa_final, self.data_fim_etapa_final])

        for elem in vetor:
            if not inicio and elem[0]:
                inicio = elem[0]
                fim = elem[1]
            elif inicio and elem[0]:
                fim = elem[1]
            elif inicio and not elem[0]:
                periodo.append((inicio, fim))
                inicio = None
                fim = None
        if inicio:
            periodo.append((inicio, fim))

        return periodo

    def is_rit_publicado(self, vinculo=None, diario=None, periodo_letivo_ch=None, financiamento_externo=None) -> bool:
        if financiamento_externo is None:
            financiamento_externo = self.financiamento_externo

        if financiamento_externo:
            return False

        if vinculo and diario:
            d = diario
            p_ch = periodo_letivo_ch
            prof_filter = {'professor__vinculo_id': vinculo.id, 'ano_letivo_id': d.ano_letivo.id}
        else:
            d = self.diario
            p_ch = self.periodo_letivo_ch
            prof_filter = {'professor_id': self.professor_id, 'ano_letivo_id': d.ano_letivo_id}

        periodo = 2 if d.is_semestral_segundo_semestre() else (p_ch or d.periodo_letivo)

        model_classes = []
        if 'pit_rit_v3' in settings.INSTALLED_APPS:
            from pit_rit_v3.models import PlanoIndividualTrabalhoV3

            model_classes.append(PlanoIndividualTrabalhoV3)
        if 'pit_rit_v2' in settings.INSTALLED_APPS:
            from pit_rit_v2.models import PlanoIndividualTrabalhoV2

            model_classes.append(PlanoIndividualTrabalhoV2)

        return any(model_cls.objects.filter(publicado=True, periodo_letivo=periodo, **prof_filter).exists() for model_cls in model_classes)

    def get_resumo_ch_prevista(self):
        if self.periodo_letivo_ch:
            periodo_letivo_ch = f'{self.diario.ano_letivo}.{self.periodo_letivo_ch}'
        else:
            periodo_letivo_ch = f'{self.diario.ano_letivo}'
        return f'{self.professor.get_matricula()}/{periodo_letivo_ch}: {self.percentual_ch or 0}%'

    def get_diarios_choque_horario(self):
        diarios = []
        qs = (
            ProfessorDiario.objects.filter(
                professor=self.professor, diario__ano_letivo=self.diario.ano_letivo, diario__periodo_letivo=self.diario.periodo_letivo
            )
            .exclude(pk=self.pk)
            .exclude(diario__ignorar_choque_horario_renovacao_matricula=True)
        )
        horarios = set(self.diario.horarioauladiario_set.values_list('dia_semana', 'horario_aula'))
        for professor_diario in qs:
            outros_horarios = set(professor_diario.diario.horarioauladiario_set.values_list('dia_semana', 'horario_aula'))
            if horarios & outros_horarios:
                diarios.append(professor_diario.diario.id)
        return diarios


class OcorrenciaDiario(LogModel):
    professor_diario = models.ForeignKeyPlus(ProfessorDiario, verbose_name='Professor')
    data = models.DateFieldPlus(verbose_name='Data')
    descricao = models.TextField('Descrição')

    class Meta:
        verbose_name = 'Ocorrência'
        verbose_name_plural = 'Ocorrências'

    def __str__(self):
        return f'{self.data} {self.descricao}'


class Aula(LogModel):
    ETAPA_1 = 1
    ETAPA_2 = 2
    ETAPA_3 = 3
    ETAPA_4 = 4
    ETAPA_5 = 5
    ETAPA_CHOICES = [[ETAPA_1, 'Primeira'], [ETAPA_2, 'Segunda'], [ETAPA_3, 'Terceira'], [ETAPA_4, 'Quarta'], [ETAPA_5, 'Final']]
    ETAPA_CHOICES_SEGUNGO_SEMESTRE = [[ETAPA_1, 'Terceira'], [ETAPA_2, 'Quarta']]

    AULA = 1
    PRATICA = 2
    EXTENSAO = 3
    PRATICA_COMO_COMPONENTE_CURRICULAR = 4
    VISITA_TECNICA = 5

    TIPO_CHOICES = [
        [AULA, 'Teórica'],
        [PRATICA, 'Prática'],
        [EXTENSAO, 'Extensão'],
        [PRATICA_COMO_COMPONENTE_CURRICULAR, 'Prática como Componente Curricular'],
        [VISITA_TECNICA, 'Visita Técnica/Aula de Campo'],
    ]

    professor_diario = models.ForeignKeyPlus(ProfessorDiario, verbose_name='Professor')
    etapa = models.PositiveIntegerField(verbose_name='Etapa', default=1, choices=ETAPA_CHOICES)
    quantidade = models.PositiveIntegerField(default=1, help_text='Quantidade de aulas ministradas')
    # plano de retomada de aulas em virtude da pandemia (COVID19)
    url = models.CharFieldPlus(verbose_name='URL da Aula', null=True, blank=True)
    data = models.DateFieldPlus(verbose_name='Data')
    conteudo = models.TextField('Conteúdo')
    tipo = models.PositiveIntegerFieldPlus(verbose_name='Tipo', choices=TIPO_CHOICES, null=True, default=AULA)
    ead = models.BooleanField(verbose_name='EAD', default=False, blank=True)
    outros_professor_diario = models.ManyToManyFieldPlus(
        ProfessorDiario,
        related_name='outros_professor_diario_set',
        verbose_name='Outros Professores',
        help_text='A CH desta aula será compartilhada com os professores selecionados',
        blank=True,
    )
    registro_frequencia_confirmado = models.BooleanField('Registro de Frequência Confirmado?', default=False)

    class Meta:
        verbose_name = 'Aula'
        verbose_name_plural = 'Aulas'
        ordering = ('etapa', 'data')

    def __str__(self):
        return f'Aula do professor {self.professor_diario.professor} no diário {self.professor_diario.diario.pk}'

    def clean(self):
        adicional = self.quantidade
        if self.pk:
            adicional -= Aula.objects.get(pk=self.pk).quantidade
        if self.quantidade < 0:
            raise ValidationError('A quantidade de horas deve ser um número inteiro positivo')
        if (
            self.data
            and hasattr(self, 'professor_diario')
            and (
                self.professor_diario.diario.calendario_academico.get_data_inicio_letivo() > self.data
                or self.data > self.professor_diario.diario.get_fim_etapa_final()
            )
        ):
            raise ValidationError(
                f'As aulas devem estar no intervalo de {format_(self.professor_diario.diario.calendario_academico.get_data_inicio_letivo())} a {format_(self.professor_diario.diario.get_fim_etapa_final())}'
            )
        if not self.professor_diario_id:
            raise ValidationError('A aula precisa estar atribuída a um professor.')
        user = tl.get_user()
        if self.professor_diario.diario.is_professor_diario(user):
            if self.professor_diario.diario.em_posse_do_registro(self.etapa):
                raise ValidationError('A etapa precisa estar em posse do professor.')
            if not self.can_change(user):
                if not self.professor_diario.diario.componente_curricular.matriz.estrutura.pode_lancar_aula_fora_do_prazo:
                    raise ValidationError('Verifique se a data da aula está no período de posse da etapa selecionada.')

    def can_change(self, user):
        if self.is_posse_etapa_professor():
            user = user or tl.get_user()
            etapa = self.etapa == 5 and 'final' or self.etapa
            inicio = getattr(self.professor_diario, f'data_inicio_etapa_{etapa}')
            fim = getattr(self.professor_diario, f'data_fim_etapa_{etapa}')
            if inicio and fim and self.data and self.data >= inicio and self.data <= fim and self.professor_diario.diario.is_professor_diario(user):
                return self.is_professor_aula(user)
        return False

    def pode_visualizar_edicao(self, user):
        if self.is_posse_etapa_professor():
            user = user or tl.get_user()
            etapa = self.etapa == 5 and 'final' or self.etapa
            inicio = getattr(self.professor_diario, f'data_inicio_etapa_{etapa}')
            fim = getattr(self.professor_diario, f'data_fim_etapa_{etapa}')
            if inicio and fim and self.data:
                calendario_alterado = self.id and (self.data < inicio or self.data > fim)
                if (self.data >= inicio and self.data <= fim) or calendario_alterado:
                    return self.professor_diario.diario.is_professor_diario(user) and self.is_professor_aula(user)
        return False

    def pode_registrar_chamada(self, user):
        professordiario = ProfessorDiario.objects.filter(professor__vinculo__user=user, diario_id=self.professor_diario.diario.pk).first()
        if professordiario:
            etapa = self.etapa == 5 and 'final' or self.etapa
            inicio = getattr(professordiario, f'data_inicio_etapa_{etapa}')
            fim = getattr(professordiario, f'data_fim_etapa_{etapa}')
            if professordiario.diario.componente_curricular.matriz.estrutura.pode_lancar_aula_fora_do_prazo:
                return True
            if inicio and fim and self.data and self.data >= inicio and self.data <= fim:
                return True
        return False

    def is_professor_aula(self, user):
        eh_professor = self.professor_diario.professor.vinculo.user == user
        if not eh_professor:
            for professor_diario in self.outros_professor_diario.all():
                if professor_diario.professor.vinculo.user == user:
                    eh_professor = True
                    break
        return eh_professor

    def is_posse_etapa_professor(self):
        return not self.professor_diario.diario.em_posse_do_registro(self.etapa)

    def is_ministrada(self):
        return self.data <= datetime.date.today()

    def get_diario(self):
        return self.professor_diario.diario

    def get_professores(self):
        professores = [
            self.professor_diario.professor.vinculo.pessoa.nome_usual,
        ]
        for professor_diario in self.outros_professor_diario.all():
            professores.append(professor_diario.professor.vinculo.pessoa.nome_usual)
        return professores


class Falta(LogModel):
    matricula_diario = models.ForeignKeyPlus(MatriculaDiario, verbose_name='Aluno')
    aula = models.ForeignKeyPlus(Aula, verbose_name='Aula')
    quantidade = models.IntegerField(default=0)
    abono_faltas = models.ForeignKeyPlus('edu.AbonoFaltas', verbose_name='Abono Faltas', null=True, blank=True)
    contabilizar = models.BooleanField(verbose_name='Contabilizar', default=True)

    class Meta:
        verbose_name = 'Falta'
        verbose_name_plural = 'Faltas'
        unique_together = (('matricula_diario', 'aula'),)

    def __str__(self):
        return f'Falta referente à {self.quantidade} hora(s)/aula(s) do aluno {self.matricula_diario.matricula_periodo.aluno.matricula} na aula {self.aula.pk}'

    def get_aluno(self):
        return self.matricula_diario.matricula_periodo.aluno

    def get_diario(self):
        return self.matricula_diario.diario

    def pode_ser_registrada(self):
        return self.aula.data <= datetime.date.today()

    def is_abonada(self):
        return not self.contabilizar


class MaterialAula(LogModel):
    professor = models.ForeignKeyPlus('edu.Professor', null=False, verbose_name='Professor', on_delete=models.CASCADE)
    descricao = models.CharFieldPlus(width=500, null=False, verbose_name='Descrição')
    data_cadastro = models.DateTimeField(auto_now_add=True, null=False, verbose_name='Data de Cadastro')
    arquivo = models.FileFieldPlus(
        upload_to='edu/material_aula/', null=True, blank=True, verbose_name='Upload do arquivo', can_view='can_view_arquivo_via_portal'
    )
    url = models.CharFieldPlus(width=500, null=True, blank=True, verbose_name='Url do arquivo')
    publico = models.BooleanField(verbose_name='Público', default=False, help_text='Permitir que outros professores visualizem o material')
    exibir_no_portal = models.BooleanField('Exibir este material no portal institucional?', default=False)

    class Meta:
        verbose_name = 'Material de Aula'
        verbose_name_plural = 'Materiais de Aula'
        ordering = ('-data_cadastro',)

    def __str__(self):
        return self.descricao

    def get_absolute_url(self):
        if self.arquivo:
            return self.arquivo.url
        if self.url.startswith('http://') or self.url.startswith('https://') or self.url.startswith('ftp://'):
            return self.url
        else:
            return f'http://{self.url}'

    def get_url_portal(self) -> str | None:
        if self.exibir_no_portal and self.arquivo:
            return f'/djtools/arquivo/edu/materialaula/{self.pk}/arquivo/'
        return None

    def can_view_arquivo_via_portal(self, user) -> bool:
        return bool(self.exibir_no_portal)

    def can_change(self, user):
        return self.professor.vinculo.user == user

    def clone(self, user):
        self.pk = None
        self.professor = Professor.objects.filter(vinculo__user_id=user.id).first()
        if self.professor:
            self.publico = False
            self.save()


class MaterialDiario(LogModel):
    material_aula = models.ForeignKeyPlus('edu.MaterialAula', null=False, verbose_name='Material de Aula', on_delete=models.CASCADE)
    professor_diario = models.ForeignKeyPlus('edu.ProfessorDiario', null=False, verbose_name='Professor Diário', on_delete=models.CASCADE)
    data_vinculacao = models.DateField('Data de Vinculação', null=True, default=datetime.date.today)

    class Meta:
        verbose_name = 'Vínculo de Material em Diário'
        verbose_name_plural = 'Vínculos de Material em Diário'


class ConfiguracaoAvaliacao(LogModel):
    FORMA_CALCULO_SOMA_SIMPLES = 1
    FORMA_CALCULO_MEDIA_ARITMETICA = 2
    FORMA_CALCULO_MEDIA_PONDERADA = 3
    FORMA_CALCULO_MAIOR_NOTA = 4
    FORMA_CALCULO_SOMA_DIVISOR = 5
    FORMA_CALCULO_MEDIA_ATITUDINAL = 6
    FORMA_CALCULO_AVALIACAO_CONCEITO = 7
    FORMA_CALCULO_CHOICES = [
        [FORMA_CALCULO_MAIOR_NOTA, 'Maior Nota'],
        [FORMA_CALCULO_MEDIA_ARITMETICA, 'Média Aritmética'],
        [FORMA_CALCULO_MEDIA_PONDERADA, 'Média Ponderada'],
        [FORMA_CALCULO_SOMA_DIVISOR, 'Soma com Divisor Informado'],
        [FORMA_CALCULO_SOMA_SIMPLES, 'Soma Simples'],
        [FORMA_CALCULO_MEDIA_ATITUDINAL, 'Média Atitudinal'],
        [FORMA_CALCULO_AVALIACAO_CONCEITO, 'Avaliação por Conceito'],
    ]

    diario = models.ForeignKeyPlus(Diario, verbose_name='Professor', null=True)
    etapa = models.IntegerField('Etapa', null=True)
    forma_calculo = models.IntegerField(choices=FORMA_CALCULO_CHOICES, default=FORMA_CALCULO_MEDIA_ARITMETICA, verbose_name='Forma de Cálculo')
    divisor = models.PositiveIntegerField('Divisor', null=True, blank=True)
    maior_nota = models.BooleanField('Ignorar Maior Nota', default=False)
    menor_nota = models.BooleanField('Ignorar Menor Nota', default=False)
    autopublicar = models.BooleanField(
        'Autopublicar Notas', default=True, help_text='As notas das avaliacões serão exibidas aos alunos a medida que forem lançadas.'
    )
    observacao = models.TextField('Observação', null=True, blank=True)

    class Meta:
        verbose_name = 'Configuração de Avaliação'
        verbose_name_plural = 'Configurações de Avaliação'

    def __str__(self):
        lista = []
        for item in self.itemconfiguracaoavaliacao_set.all().order_by('data', 'tipo'):
            if self.forma_calculo == ConfiguracaoAvaliacao.FORMA_CALCULO_AVALIACAO_CONCEITO:
                lista.append(f'{item.sigla}')
            elif item.peso:
                lista.append(f'{item.sigla} - {item.nota_maxima} [{item.peso}]')
            else:
                lista.append(f'{item.sigla} - {item.nota_maxima}')
        return '{} ({})'.format(self.get_forma_calculo_display(), ' | '.join(lista))

    def get_absolute_url(self):
        return f'/edu/configuracao_avaliacao/{self.pk:d}/'


class ItemConfiguracaoAvaliacao(LogModel):
    TIPO_TRABALHO = 1
    TIPO_SEMINARIO = 2
    TIPO_TESTE = 3
    TIPO_PROVA = 4
    TIPO_ATIVIDADE = 5
    TIPO_EXERCICIO = 6
    TIPO_ATITUDINAL = 7
    TIPO_RECUPERACAO = 8
    TIPO_CHOICES = [
        [TIPO_PROVA, 'Prova'],
        [TIPO_SEMINARIO, 'Seminário'],
        [TIPO_TRABALHO, 'Trabalho'],
        [TIPO_TESTE, 'Teste'],
        [TIPO_ATIVIDADE, 'Atividade'],
        [TIPO_EXERCICIO, 'Exercício'],
        [TIPO_ATITUDINAL, 'Atitudinal'],
    ]

    configuracao_avaliacao = models.ForeignKeyPlus(ConfiguracaoAvaliacao, verbose_name='Configuração da Avaliação')
    tipo = models.IntegerField(choices=TIPO_CHOICES, verbose_name='Tipo da Avaliação', default=TIPO_PROVA)
    sigla = models.CharFieldPlus('Sigla', width=50)
    descricao = models.CharFieldPlus('Descrição', default='')
    data = models.DateFieldPlus('Data da Avaliação', null=True, blank=True)
    nota_maxima = models.PositiveIntegerField('Nota Máxima', default=settings.NOTA_DECIMAL and 10 or 100)
    peso = models.IntegerField('Peso', null=True, blank=True)

    class Meta:
        verbose_name = 'Item de Configuração de Avaliação'
        verbose_name_plural = 'Itens de Configuração de Avaliação'

    def __str__(self):
        return f'{self.get_tipo_display()} {self.sigla} na configuracao #{self.configuracao_avaliacao.pk}'

    def clean(self):
        configuracao_avaliacao = self.configuracao_avaliacao
        if configuracao_avaliacao.forma_calculo == ConfiguracaoAvaliacao.FORMA_CALCULO_MEDIA_PONDERADA and self.peso and self.peso < 0:
            raise ValidationError('Deve ser informado o peso de cada item devido à forma de cálculo escolhida.')

    def get_qtd_avaliacoes_concorrentes(self):
        if self.data:
            qs_itens_avaliacao = ItemConfiguracaoAvaliacao.objects.exclude(pk=self.pk).filter(
                configuracao_avaliacao__diario__turma=self.configuracao_avaliacao.diario.turma_id, data=self.data
            )
            return qs_itens_avaliacao.count()
        return 0

    def get_descricao_etapa(self):
        if self.configuracao_avaliacao.etapa == 5:
            return 'Etapa Final'
        else:
            return f'Etapa {self.configuracao_avaliacao.etapa}'

    def get_tipo_display(self):
        for tipo, descricao in self.TIPO_CHOICES:
            if self.tipo == tipo:
                return descricao
        if self.tipo == self.TIPO_RECUPERACAO:
            return 'Recuperação'


class NotaAvaliacao(LogModel):
    matricula_diario = models.ForeignKeyPlus(MatriculaDiario, verbose_name='Matrícula Diário', on_delete=models.CASCADE)
    item_configuracao_avaliacao = models.ForeignKeyPlus(
        ItemConfiguracaoAvaliacao, verbose_name='Item de Configuração de Avaliação', on_delete=models.CASCADE
    )
    nota = models.NotaField('Nota', null=True)

    class Meta:
        verbose_name = 'Nota de Avaliação'
        verbose_name_plural = 'Notas de Avaliações'
        ordering = ('-id',)

    def __str__(self):
        return 'Nota {} do aluno {} na avaliação {} do diário {}'.format(
            self.nota is None and 'não lançada' or self.nota,
            self.matricula_diario.matricula_periodo.aluno.matricula,
            self.item_configuracao_avaliacao.sigla,
            self.matricula_diario.diario.pk,
        )

    def pode_exibir_nota(self):
        diario_entregue = (
            getattr(
                self.item_configuracao_avaliacao.configuracao_avaliacao.diario,
                f'posse_etapa_{self.item_configuracao_avaliacao.configuracao_avaliacao.etapa}',
            )
            == Diario.POSSE_REGISTRO_ESCOLAR
        )
        return diario_entregue or self.item_configuracao_avaliacao.configuracao_avaliacao.autopublicar

    def get_nota(self):
        estrutura = self.matricula_diario.diario.estrutura_curso
        if estrutura.is_lancamento_conceito():
            nota = estrutura.get_conceito(self.nota)
        else:
            nota = mask_nota(self.nota)
        return nota


class Trabalho(LogModel):
    diario = models.ForeignKeyPlus(Diario, verbose_name='Diário')
    etapa = models.IntegerField(verbose_name='Etapa')

    data_solicitacao = models.DateFieldPlus(verbose_name='Data da Solicitação', auto_now=True)
    data_limite_entrega = models.DateFieldPlus(verbose_name='Data Limite', null=True, blank=True)
    titulo = models.CharFieldPlus(verbose_name='Título')
    descricao = models.TextField(verbose_name='Descrição')
    arquivo = models.FileFieldPlus(verbose_name='Arquivo', upload_to='trabalhos', null=True, blank=True)

    class Meta:
        verbose_name = 'Trabalho'
        verbose_name_plural = 'Trabalhos'
        ordering = ('-id',)

    def __str__(self):
        return self.titulo

    def pode_entregar_trabalho(self):
        return self.data_limite_entrega is None or not (datetime.date.today() > self.data_limite_entrega)

    def can_delete(self, user=None):
        if user is None:
            user = tl.get_user()
        return user.pk in self.diario.get_professores().filter(ativo=True).values_list('professor__vinculo__user_id', flat=True)


class EntregaTrabalho(LogModel):
    trabalho = models.ForeignKeyPlus(Trabalho, verbose_name='Diário', on_delete=models.CASCADE)
    matricula_diario = models.ForeignKeyPlus(MatriculaDiario, verbose_name='Matrícula Diário', on_delete=models.CASCADE)
    comentario = models.TextField(verbose_name='Comentário', blank=True)
    data_entrega = models.DateTimeFieldPlus(verbose_name='Data da Entrega', auto_now=True)
    arquivo = models.FileFieldPlus(verbose_name='Arquivo', upload_to='trabalhos_alunos')

    class Meta:
        verbose_name = 'Trabalho'
        verbose_name_plural = 'Trabalhos'
        ordering = ('-id',)

    def __str__(self):
        return f'Trabalho "{self.trabalho.titulo}" de {self.matricula_diario.matricula_periodo.aluno}'


class TopicoDiscussao(LogModel):
    diario = models.ForeignKeyPlus(Diario, verbose_name='Diário', on_delete=models.CASCADE)
    etapa = models.IntegerField(verbose_name='Etapa')
    data = models.DateTimeFieldPlus(verbose_name='Data', auto_now=True)
    user = models.ForeignKey('comum.User', verbose_name='Usuário', on_delete=models.CASCADE)
    titulo = models.CharFieldPlus(verbose_name='Título')
    descricao = models.TextField(verbose_name='Descrição')

    class Meta:
        verbose_name = 'Tópico'
        verbose_name_plural = 'Tópicos'
        ordering = ('-id',)

    def __str__(self):
        return self.titulo

    def can_delete(self, user=None):
        if user is None:
            user = tl.get_user()
        return user == self.user


class RespostaDiscussao(LogModel):
    topico = models.ForeignKeyPlus(TopicoDiscussao, verbose_name='Tópico')
    data = models.DateTimeFieldPlus(verbose_name='Data', auto_now=True)
    user = models.ForeignKey('comum.User', verbose_name='Usuário', on_delete=models.CASCADE)
    comentario = models.TextField(verbose_name='Comentário')

    class Meta:
        verbose_name = 'Resposta'
        verbose_name_plural = 'Respostas'
        ordering = ('-id',)

    def __str__(self):
        return f'Resposta de "{self.user}" no tópico {self.topico}'

    def can_delete(self, user=None):
        if user is None:
            user = tl.get_user()
        return user == self.user


class JustificativaSuspensaoDiario(LogModel):
    ID_JUSTIFICATIVA_OUTRO = 8

    descricao = models.CharFieldPlus(verbose_name='Descrição')
    codigo_pedemeia = models.PositiveIntegerField(verbose_name='Código no Pé de Meia')
    ativo = models.BooleanField(verbose_name='Ativo', default=True)

    class Meta:
        verbose_name = 'Justificativa para Suspensão de Diário'
        verbose_name_plural = 'Justificativas para Suspensão de Diário'
        ordering = ('id',)


class SuspensaoDiario(LogModel):
    diario = models.ForeignKeyPlus(Diario, verbose_name='Diário', on_delete=models.CASCADE)
    inicio = models.DateFieldPlus(verbose_name='Início')
    fim = models.DateFieldPlus(verbose_name='Fim', null=True)
    motivo = models.TextField(verbose_name='Motivo', null=True, blank=True)
    justificativa = models.ForeignKeyPlus(
        JustificativaSuspensaoDiario,
        verbose_name='Justificativa',
        on_delete=models.CASCADE,
        null=False,
        default=JustificativaSuspensaoDiario.ID_JUSTIFICATIVA_OUTRO,
    )

    class Meta:
        verbose_name = 'Suspensão de Diário'
        verbose_name_plural = 'Suspensões de Diário'
        ordering = ('id',)
