"""
TODO:
    - ae.Inscricao
        > Rever os atributos booleanos
        > Retirar inscrições duplicadas, programa e aluno devem ser únicos;
        > Adicionar no Meta: unique_together = (programa, aluno);
        > Matar get_subinstance
    - ae.CategoraAlimentacoa
        > Buscar CategoraAlimentacoa.descricao e mudar para CategoraAlimentacoa.nome
    - ae.OfertaAlimentacao
        > Mudar estah_configurado para que 0 seja uma situação de não configurado.
        > Replicar para as demais ofertas dos outros programas.

views:
    - detalhar_programa
        > Adicionar um form para categoria

Templates:
    - Remover:
        > adicionar_participacao.html
"""

import datetime
from datetime import date, timedelta
from decimal import Decimal

from dateutil.relativedelta import relativedelta
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import connection, transaction
from django.db.models import F, Q
from django.db.models.aggregates import Count
from django.db.models.signals import post_save
from django.dispatch.dispatcher import receiver
from django.utils.datastructures import OrderedSet
from django.utils.safestring import mark_safe

from comum.models import Configuracao, Raca, Vinculo
from comum.utils import get_uo
from djtools.choices import DiaSemanaChoices
from djtools.db import models
from djtools.templatetags.filters import format_
from djtools.utils import existe_conflito_entre_intervalos, mask_cpf, somar_dias, normalizar_nome_proprio
from edu.models import Aluno, LogModel
from rh.models import Servidor, Setor, UnidadeOrganizacional


@receiver(post_save, sender=Aluno)
def alunos_post_save(sender, instance, **kwargs):
    if not instance.situacao.ativo:
        inscricoes = Inscricao.objects.filter(aluno=instance, ativa=True)
        if inscricoes:
            for inscricao in inscricoes:
                inscricao.ativa = False
                inscricao.save()
        participacoes = Participacao.objects.filter(aluno=instance)
        participacoes = participacoes.filter(Q(data_termino__isnull=True) | Q(data_termino__gte=datetime.date.today()))
        if participacoes:
            for participacao in participacoes:
                participacao.data_termino = datetime.date.today()
                participacao.motivo_termino = 'Aluno com matrícula inativa na instituição.'
                participacao.save()


def atualizar_config_refeicao(sender, **kwargs):
    from ae.views import remover_cache_config_refeicao

    """
    Atualiza a "cache" da configuração de refeição depois de mudado o agendamento de refeição
    """
    instance = kwargs['instance']
    uo = None
    if isinstance(instance, AgendamentoRefeicao | HistoricoFaltasAlimentacao):
        uo = instance.programa.instituicao
    elif isinstance(instance, ParticipacaoAlimentacao):
        uo = instance.participacao.programa.instituicao

    remover_cache_config_refeicao(uo)


class TurnoChoices:
    MANHA = 'manha'
    TARDE = 'tarde'
    NOITE = 'noite'
    MANHA_TARDE = 'manha_tarde'
    MANHA_NOITE = 'manha_noite'
    TARDE_NOITE = 'tarde_noite'
    MANHA_TARDE_NOITE = 'manha_tarde_noite'

    TURNO_CHOICES = (
        (MANHA, 'Manhã'),
        (TARDE, 'Tarde'),
        (NOITE, 'Noite'),
        (MANHA_TARDE, 'Manhã e tarde'),
        (MANHA_NOITE, 'Manhã e noite'),
        (TARDE_NOITE, 'Tarde e noite'),
    )


class PassesChoices:
    INTERMUNICIPAL = 'INT'
    MUNICIPAL = 'MUN'

    PASSES_CHOICES = ((INTERMUNICIPAL, 'Intermunicipal'), (MUNICIPAL, 'Municipal'))


# -----------------------------------------------------------------------------
# Cadastros básicos -----------------------------------------------------------
# -----------------------------------------------------------------------------
class CategoriaAlimentacao(models.ModelPlus):
    nome = models.CharField('Nome', max_length=50)
    descricao = models.CharField('Descrição', max_length=50)

    class Meta:
        ordering = ['nome']
        verbose_name = 'Categoria de Alunos para Alimentação'
        verbose_name_plural = 'Categorias de Alunos para Alimentação'

    def __str__(self):
        return self.nome


class DemandaAlunoManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset()


class DemandaAlunoAtivasManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(ativa=True)


class DemandaAluno(models.ModelPlus):
    """
    Demandas do aluno. Ex: xerox, alimentação, transporte, etc
    """

    ALMOCO = 1
    JANTAR = 2
    FARDAMENTO = 3
    MATERIAL_DIDATICO = 4
    CONSULTA_ODONTOLOGICA = 5
    EXAME = 6
    MEDICAMENTO = 7
    OCULOS = 8
    ATENDIMENTO_ALUNO = 9
    ATENDIMENTO_PAIS = 10
    VISITA = 11
    CAFE = 19

    INSTITUCIONAL = 'Institucional'
    PARCERIAS = 'Parcerias'
    SEM_CUSTEIO = 'Sem custeio'

    CUSTEIO_CHOICES = (
        (INSTITUCIONAL, 'Institucional'),
        (PARCERIAS, 'Parcerias'),
        (SEM_CUSTEIO, 'Sem custeio'),
        ('Institucional + FNDE', 'Institucional + FNDE'),
        ('FNDE', 'FNDE'),
    )

    REFEICOES_CHOICES = ((CAFE, 'Café da manhã'), (ALMOCO, 'Almoço'), (JANTAR, 'Jantar'))

    TODAS_REFEICOES_CHOICES = (('', 'Todos'), (CAFE, 'Café da manhã'), (ALMOCO, 'Almoço'), (JANTAR, 'Jantar'))

    objects = DemandaAlunoManager()
    ativas = DemandaAlunoAtivasManager()

    nome = models.CharFieldPlus()
    descricao = models.TextField('Descrição')
    custeio = models.CharField('Custeio', choices=CUSTEIO_CHOICES, max_length=50, null=True, blank=True)
    ativa = models.BooleanField('Ativa', default=True)
    atualizado_por = models.ForeignKeyPlus(
        'comum.Vinculo', null=True, verbose_name='Atualizado Por', related_name='demandaaluno_atualizado_por', on_delete=models.CASCADE
    )
    atualizado_em = models.DateTimeFieldPlus('Atualizado em', null=True)
    eh_kit_alimentacao = models.BooleanField('É kit de alimentos', default=False)

    class Meta:
        ordering = ('nome',)
        unique_together = ('nome', 'descricao')
        verbose_name = 'Tipo de Atendimento'
        verbose_name_plural = 'Tipos de Atendimentos'

    def __str__(self):
        nome = self.nome
        if self.custeio and self.custeio != DemandaAluno.SEM_CUSTEIO:
            nome += f' ({self.custeio})'
        return nome


class CategoriaBolsa(models.ModelPlus):
    TIPO_EXTENSAO = 'extensão'
    TIPO_INICIACAO_CIENTIFICA = 'iniciação científica'
    TIPO_CHOICES = ((TIPO_EXTENSAO, 'Extensão'), (TIPO_INICIACAO_CIENTIFICA, 'Iniciação Científica'))
    nome = models.CharFieldPlus('Nome', unique=True)
    descricao = models.CharFieldPlus('Descrição', blank=True)
    tipo_bolsa = models.CharFieldPlus('Tipo de Bolsa', blank=True, unique=True, choices=TIPO_CHOICES, null=True)
    vinculo_programa = models.BooleanField('Vínculo a Programa', default=False)
    ativa = models.BooleanField('Ativa', default=True)

    class Meta:
        ordering = ('nome',)
        verbose_name = 'Categoria de Bolsa'
        verbose_name_plural = 'Categorias de Bolsas'

    def __str__(self):
        return self.nome


# -----------------------------------------------------------------------------
# Principais modelos ----------------------------------------------------------
# -----------------------------------------------------------------------------


class Programa(models.ModelPlus):
    """
    Programas ofertados pelo Serviço Social.
    ---
    Cada tipo de programa terá formulários com questões específicas.
    """

    TIPO_ALIMENTACAO = 'ALM'
    TIPO_TRANSPORTE = 'PAS'
    TIPO_TRABALHO = 'TRB'
    TIPO_IDIOMA = 'IDM'
    TIPO_GENERICO = 'GEN'

    TIPO_CHOICES = (
        (TIPO_ALIMENTACAO, 'Alimentação Estudantil'),
        (TIPO_TRANSPORTE, 'Auxílio Transporte'),
        (TIPO_TRABALHO, 'Apoio à Formação Estudantil'),
        (TIPO_IDIOMA, 'Curso de Idiomas'),
    )

    tipo = models.CharFieldPlus('Tipo', choices=TIPO_CHOICES, null=True, blank=True)
    descricao = models.TextField('Descrição')
    instituicao = models.ForeignKeyPlus(UnidadeOrganizacional, verbose_name='Campus', related_name='programas_sediados', on_delete=models.CASCADE)
    demandas = models.ManyToManyField('ae.DemandaAluno', verbose_name='Atendimentos Incluídos')
    titulo = models.CharField('Título', max_length=255, null=True, blank=True)
    impedir_solicitacao_beneficio = models.BooleanField('Impedir que aluno solicite benefício?', default=False)
    publico_alvo = models.ManyToManyField('rh.UnidadeOrganizacional', verbose_name='Público-Alvo')
    tipo_programa = models.ForeignKeyPlus('ae.TipoPrograma', verbose_name='Tipo de Programa', null=True, on_delete=models.CASCADE)
    exige_comprovante_pagamento = models.BooleanField(
        'Exige Comprovante de Pagamento?', default=False, help_text='Este comprovante será solicitado mensalmente aos participantes deste programa.'
    )
    exige_folha_frequencia = models.BooleanField(
        'Exige Folha de Frequência?', default=False, help_text='Este comprovante será solicitado mensalmente aos participantes deste programa.'
    )
    data_inicio_alteracoes = models.DateTimeFieldPlus(
        'Data de Início', null=True, blank=True, help_text='Data de início do período de solicitações de alteração de dias/refeições.'
    )
    data_fim_alteracoes = models.DateTimeFieldPlus(
        'Data de Fim', null=True, blank=True, help_text='Data de fim do período de solicitações de alteração de dias/refeições.'
    )
    qtd_faltas_bloqueio_alimentacao = models.IntegerFieldPlus(
        'Quantidade de faltas para suspender participação',
        default=3,
        blank=True,
        help_text='Informe a quantidade de faltas sem justificativa, no mesmo mês, que irá suspender a participação do aluno no programa de alimentação.',
    )

    class Meta:
        verbose_name = 'Programa'
        verbose_name_plural = 'Programas'
        ordering = ('tipo_programa__titulo', 'instituicao')
        permissions = (
            ('pode_abrir_inscricao_todos', 'Pode abrir Período de Inscrição para qualquer campus'),
            ('pode_abrir_inscricao_do_campus', 'Pode abrir Período de Inscrição para próprio campus'),
            ('pode_detalhar_programa_todos', 'Pode ver detalhamento de todos os Programas'),
            ('pode_detalhar_programa_do_campus', 'Pode ver detalhamento de Programas do próprio campus'),
            ('pode_ver_menu_agendamentos', 'Pode ver Agendamentos'),
            ('pode_ver_periodo_inscricao', 'Pode ver Período de Inscrição'),
            ('pode_ver_lista_dos_alunos', 'Pode ver Relatório de Lista dos Alunos'),
            ('pode_ver_lista_dos_alunos_campus', 'Pode ver Relatório de Lista dos Alunos do próprio campus'),
            ('pode_ver_relatorio_semanal', 'Pode ver Relatório Semanal de Alimentação'),
            ('pode_ver_relatorios_todos', 'Pode ver Relatórios de Programas de todos os campi'),
            ('pode_ver_relatorios_campus', 'Pode ver Relatórios de Programas do próprio campus'),
            ('pode_ver_relatorios_controle_refeicoes', 'Pode ver Relatórios de Controle de Refeições'),
            ('pode_ver_listas_todos', 'Pode ver listas de todos os campi'),
            ('pode_ver_listas_campus', 'Pode ver listas do próprio campus'),
        )

    def __str__(self):
        return f'{self.tipo_programa.titulo} ({self.instituicao})'

    def get_absolute_url(self):
        return f'/ae/programa/{self.id}/'

    def get_tipo(self):
        if self.tipo_programa:
            return self.tipo_programa.sigla
        return None

    def get_inscricoes_ativas(self):
        return self.inscricao_set.filter(ativa=True)

    def get_participacoes_abertas(self):
        return Participacao.abertas.filter(programa=self).order_by('aluno__pessoa_fisica__nome')

    def get_participacoes_futuras(self):
        return Participacao.futuras.filter(programa=self).order_by('aluno__pessoa_fisica__nome')

    def estah_configurado(self):
        if self.tipo == self.TIPO_ALIMENTACAO:
            oferta = OfertaAlimentacao.objects.filter(campus=self.instituicao)
            if oferta.exists():
                if not oferta[0].estah_configurada():
                    return False
        elif self.tipo == self.TIPO_IDIOMA:
            return OfertaTurma.objects.filter(campus=self.instituicao).exists()
        elif self.tipo == self.TIPO_TRABALHO:
            return OfertaBolsa.objects.filter(campus=self.instituicao).exists()
        return True

    def get_atendimentos(self):
        ids = self.demandas.values_list('id', flat=True)
        return DemandaAlunoAtendida.objects.filter(demanda__id__in=ids)

    def get_atendimento(self, aluno, tipo_refeicao, ref):
        return aluno.demandaalunoatendida_set.filter(
            campus=self.instituicao,
            demanda=tipo_refeicao,
            data__gte=datetime.datetime(ref.year, ref.month, ref.day, 0, 0, 0),
            data__lte=datetime.datetime(ref.year, ref.month, ref.day, 23, 59, 59),
        ).exists()

    def get_ultimos_atendimentos(self):
        return self.get_atendimentos().order_by('-data')[:15]

    def tem_valor_financeiro(self):
        return RespostaParticipacao.objects.filter(
            participacao__programa=self, pergunta__eh_info_financeira=True, pergunta__tipo_resposta=PerguntaParticipacao.NUMERO
        ).exists()

    def get_disponibilidade(self, inicio=None):
        if self.tipo == self.TIPO_ALIMENTACAO:
            uo = self.instituicao
            if OfertaAlimentacao.objects.filter(campus=uo, dia_inicio=inicio).exists():
                oferta_alimentacao = OfertaAlimentacao.objects.filter(campus=self.instituicao, dia_inicio=inicio).last()
                todos_participantes = ParticipacaoAlimentacao.objects.filter(participacao__programa=self).filter(
                    Q(participacao__data_termino__isnull=True) | Q(participacao__data_termino__gte=datetime.date.today())
                )
                qs = todos_participantes.filter(suspensa=False)

                data_ter = inicio + timedelta(1)
                data_qua = inicio + timedelta(2)
                data_qui = inicio + timedelta(3)
                data_sex = inicio + timedelta(4)
                agendamento_semanal = AgendamentoRefeicao.objects.filter(programa=self, cancelado=False)
                agend_seg = agendamento_semanal.filter(data__date=inicio)
                agend_ter = agendamento_semanal.filter(data__date=data_ter)
                agend_qua = agendamento_semanal.filter(data__date=data_qua)
                agend_qui = agendamento_semanal.filter(data__date=data_qui)
                agend_sex = agendamento_semanal.filter(data__date=data_sex)

                faltas = HistoricoFaltasAlimentacao.objects.filter(participacao__programa=self)

                falta_seg = faltas.filter(data=inicio, justificativa__isnull=False)
                falta_ter = faltas.filter(data=data_ter, justificativa__isnull=False)
                falta_qua = faltas.filter(data=data_qua, justificativa__isnull=False)
                falta_qui = faltas.filter(data=data_qui, justificativa__isnull=False)
                falta_sex = faltas.filter(data=data_sex, justificativa__isnull=False)

                cafe_ofertado = [
                    oferta_alimentacao.cafe_seg,
                    oferta_alimentacao.cafe_ter,
                    oferta_alimentacao.cafe_qua,
                    oferta_alimentacao.cafe_qui,
                    oferta_alimentacao.cafe_sex,
                ]

                cafe_seg_todos_participantes = (
                    todos_participantes.filter(participacao__data_inicio__lte=inicio)
                    .values('solicitacao_atendida_cafe__seg')
                    .filter(solicitacao_atendida_cafe__seg=True)
                    .count()
                )
                cafe_seg_participante = (
                    qs.exclude(participacao__id__in=falta_seg.filter(tipo_refeicao=TipoRefeicao.TIPO_CAFE).values_list('participacao', flat=True))
                    .values('solicitacao_atendida_cafe__seg')
                    .filter(solicitacao_atendida_cafe__seg=True, participacao__data_inicio__lte=inicio)
                    .count()
                )
                cafe_seg_agendado = agend_seg.filter(tipo_refeicao=AgendamentoRefeicao.TIPO_CAFE).count()

                cafe_ter_todos_participantes = (
                    todos_participantes.filter(participacao__data_inicio__lte=data_ter)
                    .values('solicitacao_atendida_cafe__ter')
                    .filter(solicitacao_atendida_cafe__ter=True)
                    .count()
                )
                cafe_ter_participante = (
                    qs.exclude(participacao__id__in=falta_ter.filter(tipo_refeicao=TipoRefeicao.TIPO_CAFE).values_list('participacao', flat=True))
                    .values('solicitacao_atendida_cafe__ter')
                    .filter(solicitacao_atendida_cafe__ter=True, participacao__data_inicio__lte=data_ter)
                    .count()
                )
                cafe_ter_agendado = agend_ter.filter(tipo_refeicao=AgendamentoRefeicao.TIPO_CAFE).count()

                cafe_qua_todos_participantes = (
                    todos_participantes.filter(participacao__data_inicio__lte=data_qua)
                    .values('solicitacao_atendida_cafe__qua')
                    .filter(solicitacao_atendida_cafe__qua=True)
                    .count()
                )
                cafe_qua_participante = (
                    qs.exclude(participacao__id__in=falta_qua.filter(tipo_refeicao=TipoRefeicao.TIPO_CAFE).values_list('participacao', flat=True))
                    .values('solicitacao_atendida_cafe__qua')
                    .filter(solicitacao_atendida_cafe__qua=True, participacao__data_inicio__lte=data_qua)
                    .count()
                )
                cafe_qua_agendado = agend_qua.filter(tipo_refeicao=AgendamentoRefeicao.TIPO_CAFE).count()

                cafe_qui_todos_participantes = (
                    todos_participantes.filter(participacao__data_inicio__lte=data_qui)
                    .values('solicitacao_atendida_cafe__qui')
                    .filter(solicitacao_atendida_cafe__qui=True)
                    .count()
                )
                cafe_qui_participante = (
                    qs.exclude(participacao__id__in=falta_qui.filter(tipo_refeicao=TipoRefeicao.TIPO_CAFE).values_list('participacao', flat=True))
                    .values('solicitacao_atendida_cafe__qui')
                    .filter(solicitacao_atendida_cafe__qui=True, participacao__data_inicio__lte=data_qui)
                    .count()
                )
                cafe_qui_agendado = agend_qui.filter(tipo_refeicao=AgendamentoRefeicao.TIPO_CAFE).count()

                cafe_sex_todos_participantes = (
                    todos_participantes.filter(participacao__data_inicio__lte=data_sex)
                    .values('solicitacao_atendida_cafe__sex')
                    .filter(solicitacao_atendida_cafe__sex=True)
                    .count()
                )
                cafe_sex_participante = (
                    qs.exclude(participacao__id__in=falta_sex.filter(tipo_refeicao=TipoRefeicao.TIPO_CAFE).values_list('participacao', flat=True))
                    .values('solicitacao_atendida_cafe__sex')
                    .filter(solicitacao_atendida_cafe__sex=True, participacao__data_inicio__lte=data_sex)
                    .count()
                )
                cafe_sex_agendado = agend_sex.filter(tipo_refeicao=AgendamentoRefeicao.TIPO_CAFE).count()

                cafe_concedido = [
                    cafe_seg_participante + cafe_seg_agendado,
                    cafe_ter_participante + cafe_ter_agendado,
                    cafe_qua_participante + cafe_qua_agendado,
                    cafe_qui_participante + cafe_qui_agendado,
                    cafe_sex_participante + cafe_sex_agendado,
                ]

                cafe_concedido_participante = [
                    cafe_seg_participante,
                    cafe_ter_participante,
                    cafe_qua_participante,
                    cafe_qui_participante,
                    cafe_sex_participante,
                ]

                cafe_todos_participantes = [
                    cafe_seg_todos_participantes,
                    cafe_ter_todos_participantes,
                    cafe_qua_todos_participantes,
                    cafe_qui_todos_participantes,
                    cafe_sex_todos_participantes,
                ]

                cafe_concedido_agendado = [cafe_seg_agendado, cafe_ter_agendado, cafe_qua_agendado, cafe_qui_agendado, cafe_sex_agendado]

                almoco_ofertado = [
                    oferta_alimentacao.almoco_seg,
                    oferta_alimentacao.almoco_ter,
                    oferta_alimentacao.almoco_qua,
                    oferta_alimentacao.almoco_qui,
                    oferta_alimentacao.almoco_sex,
                ]

                almoco_seg_todos_participantes = (
                    todos_participantes.filter(participacao__data_inicio__lte=inicio)
                    .values('solicitacao_atendida_almoco__seg')
                    .filter(solicitacao_atendida_almoco__seg=True)
                    .count()
                )
                almoco_seg_participante = (
                    qs.exclude(participacao__id__in=falta_seg.filter(tipo_refeicao=TipoRefeicao.TIPO_ALMOCO).values_list('participacao', flat=True))
                    .values('solicitacao_atendida_almoco__seg')
                    .filter(solicitacao_atendida_almoco__seg=True, participacao__data_inicio__lte=inicio)
                    .count()
                )
                almoco_seg_agendado = agend_seg.filter(tipo_refeicao=AgendamentoRefeicao.TIPO_ALMOCO).count()

                almoco_ter_todos_participantes = (
                    todos_participantes.filter(participacao__data_inicio__lte=data_ter)
                    .values('solicitacao_atendida_almoco__ter')
                    .filter(solicitacao_atendida_almoco__ter=True)
                    .count()
                )
                almoco_ter_participante = (
                    qs.exclude(participacao__id__in=falta_ter.filter(tipo_refeicao=TipoRefeicao.TIPO_ALMOCO).values_list('participacao', flat=True))
                    .values('solicitacao_atendida_almoco__ter')
                    .filter(solicitacao_atendida_almoco__ter=True, participacao__data_inicio__lte=data_ter)
                    .count()
                )
                almoco_ter_agendado = agend_ter.filter(tipo_refeicao=AgendamentoRefeicao.TIPO_ALMOCO).count()

                almoco_qua_todos_participantes = (
                    todos_participantes.filter(participacao__data_inicio__lte=data_qua)
                    .values('solicitacao_atendida_almoco__qua')
                    .filter(solicitacao_atendida_almoco__qua=True)
                    .count()
                )
                almoco_qua_participante = (
                    qs.exclude(participacao__id__in=falta_qua.filter(tipo_refeicao=TipoRefeicao.TIPO_ALMOCO).values_list('participacao', flat=True))
                    .values('solicitacao_atendida_almoco__qua')
                    .filter(solicitacao_atendida_almoco__qua=True, participacao__data_inicio__lte=data_qua)
                    .count()
                )
                almoco_qua_agendado = agend_qua.filter(tipo_refeicao=AgendamentoRefeicao.TIPO_ALMOCO).count()

                almoco_qui_todos_participantes = (
                    todos_participantes.filter(participacao__data_inicio__lte=data_qui)
                    .values('solicitacao_atendida_almoco__qui')
                    .filter(solicitacao_atendida_almoco__qui=True)
                    .count()
                )
                almoco_qui_participante = (
                    qs.exclude(participacao__id__in=falta_qui.filter(tipo_refeicao=TipoRefeicao.TIPO_ALMOCO).values_list('participacao', flat=True))
                    .values('solicitacao_atendida_almoco__qui')
                    .filter(solicitacao_atendida_almoco__qui=True, participacao__data_inicio__lte=data_qui)
                    .count()
                )
                almoco_qui_agendado = agend_qui.filter(tipo_refeicao=AgendamentoRefeicao.TIPO_ALMOCO).count()

                almoco_sex_todos_participantes = (
                    todos_participantes.filter(participacao__data_inicio__lte=data_sex)
                    .values('solicitacao_atendida_almoco__sex')
                    .filter(solicitacao_atendida_almoco__sex=True)
                    .count()
                )
                almoco_sex_participante = (
                    qs.exclude(participacao__id__in=falta_sex.filter(tipo_refeicao=TipoRefeicao.TIPO_ALMOCO).values_list('participacao', flat=True))
                    .values('solicitacao_atendida_almoco__sex')
                    .filter(solicitacao_atendida_almoco__sex=True, participacao__data_inicio__lte=data_sex)
                    .count()
                )
                almoco_sex_agendado = agend_sex.filter(tipo_refeicao=AgendamentoRefeicao.TIPO_ALMOCO).count()

                almoco_concedido = [
                    almoco_seg_participante + almoco_seg_agendado,
                    almoco_ter_participante + almoco_ter_agendado,
                    almoco_qua_participante + almoco_qua_agendado,
                    almoco_qui_participante + almoco_qui_agendado,
                    almoco_sex_participante + almoco_sex_agendado,
                ]

                almoco_concedido_participante = [
                    almoco_seg_participante,
                    almoco_ter_participante,
                    almoco_qua_participante,
                    almoco_qui_participante,
                    almoco_sex_participante,
                ]

                almoco_concedido_todos_participantes = [
                    almoco_seg_todos_participantes,
                    almoco_ter_todos_participantes,
                    almoco_qua_todos_participantes,
                    almoco_qui_todos_participantes,
                    almoco_sex_todos_participantes,
                ]

                almoco_concedido_agendado = [almoco_seg_agendado, almoco_ter_agendado, almoco_qua_agendado, almoco_qui_agendado, almoco_sex_agendado]

                janta_ofertada = [
                    oferta_alimentacao.janta_seg,
                    oferta_alimentacao.janta_ter,
                    oferta_alimentacao.janta_qua,
                    oferta_alimentacao.janta_qui,
                    oferta_alimentacao.janta_sex,
                ]

                jantar_seg_todos_participantes = (
                    todos_participantes.filter(participacao__data_inicio__lte=inicio)
                    .values('solicitacao_atendida_janta__seg')
                    .filter(solicitacao_atendida_janta__seg=True)
                    .count()
                )
                jantar_seg_participante = (
                    qs.exclude(participacao__id__in=falta_seg.filter(tipo_refeicao=TipoRefeicao.TIPO_JANTAR).values_list('participacao', flat=True))
                    .values('solicitacao_atendida_janta__seg')
                    .filter(solicitacao_atendida_janta__seg=True, participacao__data_inicio__lte=inicio)
                    .count()
                )
                jantar_seg_agendado = agend_seg.filter(tipo_refeicao=AgendamentoRefeicao.TIPO_JANTAR).count()

                jantar_ter_todos_participantes = (
                    todos_participantes.filter(participacao__data_inicio__lte=data_ter)
                    .values('solicitacao_atendida_janta__ter')
                    .filter(solicitacao_atendida_janta__ter=True)
                    .count()
                )
                jantar_ter_participante = (
                    qs.exclude(participacao__id__in=falta_ter.filter(tipo_refeicao=TipoRefeicao.TIPO_JANTAR).values_list('participacao', flat=True))
                    .values('solicitacao_atendida_janta__ter')
                    .filter(solicitacao_atendida_janta__ter=True, participacao__data_inicio__lte=data_ter)
                    .count()
                )
                jantar_ter_agendado = agend_ter.filter(tipo_refeicao=AgendamentoRefeicao.TIPO_JANTAR).count()

                jantar_qua_todos_participantes = (
                    todos_participantes.filter(participacao__data_inicio__lte=data_qua)
                    .values('solicitacao_atendida_janta__qua')
                    .filter(solicitacao_atendida_janta__qua=True)
                    .count()
                )
                jantar_qua_participante = (
                    qs.exclude(participacao__id__in=falta_qua.filter(tipo_refeicao=TipoRefeicao.TIPO_JANTAR).values_list('participacao', flat=True))
                    .values('solicitacao_atendida_janta__qua')
                    .filter(solicitacao_atendida_janta__qua=True, participacao__data_inicio__lte=data_qua)
                    .count()
                )
                jantar_qua_agendado = agend_qua.filter(tipo_refeicao=AgendamentoRefeicao.TIPO_JANTAR).count()

                jantar_qui_todos_participantes = (
                    todos_participantes.filter(participacao__data_inicio__lte=data_qui)
                    .values('solicitacao_atendida_janta__qui')
                    .filter(solicitacao_atendida_janta__qui=True)
                    .count()
                )
                jantar_qui_participante = (
                    qs.exclude(participacao__id__in=falta_qui.filter(tipo_refeicao=TipoRefeicao.TIPO_JANTAR).values_list('participacao', flat=True))
                    .values('solicitacao_atendida_janta__qui')
                    .filter(solicitacao_atendida_janta__qui=True, participacao__data_inicio__lte=data_qui)
                    .count()
                )
                jantar_qui_agendado = agend_qui.filter(tipo_refeicao=AgendamentoRefeicao.TIPO_JANTAR).count()

                jantar_sex_todos_participantes = (
                    todos_participantes.filter(participacao__data_inicio__lte=data_sex)
                    .values('solicitacao_atendida_janta__sex')
                    .filter(solicitacao_atendida_janta__sex=True)
                    .count()
                )
                jantar_sex_participante = (
                    qs.exclude(participacao__id__in=falta_sex.filter(tipo_refeicao=TipoRefeicao.TIPO_JANTAR).values_list('participacao', flat=True))
                    .values('solicitacao_atendida_janta__sex')
                    .filter(solicitacao_atendida_janta__sex=True, participacao__data_inicio__lte=data_sex)
                    .count()
                )
                jantar_sex_agendado = agend_sex.filter(tipo_refeicao=AgendamentoRefeicao.TIPO_JANTAR).count()

                janta_concedida = [
                    jantar_seg_participante + jantar_seg_agendado,
                    jantar_ter_participante + jantar_ter_agendado,
                    jantar_qua_participante + jantar_qua_agendado,
                    jantar_qui_participante + jantar_qui_agendado,
                    jantar_sex_participante + jantar_sex_agendado,
                ]

                jantar_concedido_participante = [
                    jantar_seg_participante,
                    jantar_ter_participante,
                    jantar_qua_participante,
                    jantar_qui_participante,
                    jantar_sex_participante,
                ]

                jantar_concedido_todos_participantes = [
                    jantar_seg_todos_participantes,
                    jantar_ter_todos_participantes,
                    jantar_qua_todos_participantes,
                    jantar_qui_todos_participantes,
                    jantar_sex_todos_participantes,
                ]

                jantar_concedido_agendado = [jantar_seg_agendado, jantar_ter_agendado, jantar_qua_agendado, jantar_qui_agendado, jantar_sex_agendado]

                ofertas = {
                    'cafe': {
                        'oferta': cafe_ofertado,
                        'demanda': cafe_concedido,
                        'total_participantes': cafe_todos_participantes,
                        'participantes': cafe_concedido_participante,
                        'agendamentos': cafe_concedido_agendado,
                    },
                    'almoco': {
                        'oferta': almoco_ofertado,
                        'demanda': almoco_concedido,
                        'total_participantes': almoco_concedido_todos_participantes,
                        'participantes': almoco_concedido_participante,
                        'agendamentos': almoco_concedido_agendado,
                    },
                    'jantar': {
                        'oferta': janta_ofertada,
                        'demanda': janta_concedida,
                        'total_participantes': jantar_concedido_todos_participantes,
                        'participantes': jantar_concedido_participante,
                        'agendamentos': jantar_concedido_agendado,
                    },
                }

                return ofertas
            else:
                return False

        elif self.tipo == self.TIPO_IDIOMA:
            participacoes = ParticipacaoIdioma.objects.filter(participacao__programa__instituicao=self.instituicao).order_by('idioma__descricao')
            participacoes = participacoes.filter(
                Q(participacao__data_termino__isnull=True) | Q(participacao__data_termino__gte=datetime.date.today())
            )

            ofertas = []
            for idioma in Idioma.objects.all():
                vagas_ocupadas = participacoes.filter(idioma=idioma).count()
                if vagas_ocupadas > 0:
                    oferta = {'id': f'{idioma.id:d}', 'idioma': f'{idioma.descricao}', 'numero_vagas_ocupadas': vagas_ocupadas}
                    ofertas.append(oferta)
            return ofertas
        elif self.tipo == self.TIPO_TRABALHO:
            bolsas = OfertaBolsa.objects.filter(ativa=True, disponivel=True, campus=self.instituicao).order_by('setor__sigla')

            ofertas = []
            for bolsa in bolsas:
                ofertas.append({'setor': f'{bolsa.setor}', 'turno': bolsa.get_turno_display(), 'funcao': bolsa.descricao_funcao})

            return ofertas
        elif self.tipo == self.TIPO_TRANSPORTE:
            ofertas = OfertaPasse.objects.filter(campus=self.instituicao)
            inscricoes = ParticipacaoPasseEstudantil.objects.filter(participacao__programa=self)
            inscricoes = inscricoes.filter(Q(participacao__data_termino__isnull=True) | Q(participacao__data_termino__gte=datetime.date.today()))
            valor_concedido = 0
            valor = 0

            for oferta in ofertas:
                valor += oferta.valor_passe

            for inscricao in inscricoes:
                valor_concedido += Decimal(inscricao.valor_concedido or '0')

            ano = date.today().year
            campus = self.instituicao
            data_inicio = date(ano, 1, 1)
            data_termino = date(ano, 12, 31)
            TWOPLACES = Decimal(10) ** -2
            SEARCH_QUERY_OFERTA = Q(campus=campus) & (
                Q(data_inicio__gte=date(ano, 1, 1), data_termino__lte=date(ano, 12, 31))
                | Q(data_inicio__lte=date(ano, 1, 1), data_termino__gte=date(ano, 12, 31))
                | Q(data_inicio__lte=date(ano, 1, 1), data_termino__gte=date(ano, 1, 1), data_termino__lte=date(ano, 12, 31))
                | Q(data_inicio__gte=date(ano, 1, 1), data_inicio__lte=date(ano, 12, 31), data_termino__gte=date(ano, 12, 31))
            )
            relatorio_passe = []
            valor_total_passe = OfertaPasse.objects.filter(SEARCH_QUERY_OFERTA)
            sigla_campus = UnidadeOrganizacional.objects.suap().get(id=campus.id).sigla
            for periodo_passe in valor_total_passe:
                total_gasto = 0
                somatorio = 0
                mes = 1
                ano = datetime.datetime.now().year
                programa = Programa.objects.get(tipo=Programa.TIPO_TRANSPORTE, instituicao=campus)
                while mes <= periodo_passe.data_termino.month:
                    data_inicio = datetime.datetime(ano, int(mes), 1).date()
                    if int(mes) == 12:
                        data_termino = datetime.datetime(ano + 1, 1, 1).date()
                    else:
                        data_termino = datetime.datetime(ano, int(mes) + 1, 1).date()

                    participantes = Participacao.objects.filter(
                        participacaopasseestudantil__isnull=False, participacaopasseestudantil__valor_concedido__isnull=False
                    )

                    participantes = participantes.filter(aluno__curso_campus__diretoria__setor__uo=programa.instituicao).order_by(
                        'aluno', 'data_inicio'
                    )
                    participantes = participantes.filter(
                        Q(data_termino__gt=data_inicio, data_inicio__lt=data_termino) | Q(data_termino__isnull=True, data_inicio__lt=data_termino)
                    )

                    if participantes:
                        dias_do_mes = 22
                        dias_abonados_geral = DatasRecessoFerias.objects.filter(
                            data__gte=data_inicio, data__lt=data_termino, campus=programa.instituicao
                        ).exclude(data__week_day__in=[1, 7])
                        for item in participantes:
                            dias_abonados = dias_abonados_geral.filter(data__gte=item.data_inicio)
                            diferenca = None
                            if item.data_termino:
                                dias_abonados = dias_abonados.filter(data__lt=item.data_termino)
                            qtd_dias_abonados = dias_abonados.count()
                            valor = item.sub_instance().valor_concedido
                            if valor:
                                if item.data_inicio > data_inicio and item.data_inicio.month == int(mes):
                                    fromdate = item.data_inicio
                                    todate = data_termino
                                    daygenerator = (fromdate + timedelta(x + 1) for x in range((todate - fromdate).days))
                                    diferenca = sum(1 for day in daygenerator if day.weekday() < 5)

                                    if diferenca > dias_do_mes:
                                        diferenca_em_dias = dias_do_mes - qtd_dias_abonados
                                    else:
                                        diferenca_em_dias = diferenca - qtd_dias_abonados
                                    if diferenca_em_dias < 0:
                                        diferenca_em_dias = 0
                                    valor = Decimal((valor / dias_do_mes) * diferenca_em_dias).quantize(Decimal(10) ** -2)
                                if item.data_termino and item.data_termino < data_termino and item.data_termino.month == int(mes):
                                    fromdate = data_inicio
                                    todate = item.data_termino
                                    daygenerator = (fromdate + timedelta(x + 1) for x in range((todate - fromdate).days))
                                    diferenca = sum(1 for day in daygenerator if day.weekday() < 5)
                                    if diferenca > dias_do_mes:
                                        diferenca_em_dias = dias_do_mes - qtd_dias_abonados
                                    else:
                                        diferenca_em_dias = diferenca - qtd_dias_abonados
                                    if diferenca_em_dias < 0:
                                        diferenca_em_dias = 0
                                    valor = Decimal((valor / dias_do_mes) * diferenca_em_dias).quantize(Decimal(10) ** -2)
                                if not diferenca:
                                    if qtd_dias_abonados > dias_do_mes:
                                        qtd_dias_abonados = dias_do_mes
                                    valor = ((dias_do_mes - qtd_dias_abonados) * valor) / dias_do_mes
                                if mes <= datetime.datetime.now().month:
                                    total_gasto += valor
                                somatorio += valor
                    mes += 1
                if somatorio:
                    saldo = Decimal(periodo_passe.valor_passe).quantize(TWOPLACES) - Decimal(total_gasto).quantize(TWOPLACES)
                else:
                    saldo = periodo_passe.valor_passe

                relatorio_passe.append(
                    {
                        'campus': sigla_campus,
                        'data_inicio': periodo_passe.data_inicio,
                        'data_termino': periodo_passe.data_termino,
                        'planejado': periodo_passe.valor_passe,
                        'gasto': total_gasto,
                        'somatorio': somatorio,
                        'saldo': saldo,
                    }
                )
            return relatorio_passe
        return None

    def em_fase_alteracao(self):
        agora = datetime.datetime.now()
        return self.data_inicio_alteracoes and self.data_fim_alteracoes and agora > self.data_inicio_alteracoes and agora < self.data_fim_alteracoes

    # ------------------------
    class SemanaQtds:
        seg: int = 0
        ter: int = 0
        qua: int = 0
        qui: int = 0
        sex: int = 0
        sab: int = 0
        dom: int = 0

        def get_qtd_from_date(self, data_ref: date):
            dia_semana = data_ref.weekday()
            qtd = 0
            if dia_semana == 0:
                qtd = self.seg
            elif dia_semana == 1:
                qtd = self.ter
            elif dia_semana == 2:
                qtd = self.qua
            elif dia_semana == 3:
                qtd = self.qui
            elif dia_semana == 4:
                qtd = self.sex
            elif dia_semana == 5:
                qtd = self.sab
            elif dia_semana == 6:
                qtd = self.dom
            return qtd

    class RefeicaoOfertas:
        cafe: Programa.SemanaQtds
        almoco: Programa.SemanaQtds
        jantar: Programa.SemanaQtds

        def __init__(self):
            self.cafe = Programa.SemanaQtds()
            self.almoco = Programa.SemanaQtds()
            self.jantar = Programa.SemanaQtds()

    def get_disponibilidade_refeicao_ofertas(self, data_inicio: date | None = None, dia_solicitacao: str | None = None) -> Programa.RefeicaoOfertas:
        ofertas = Programa.RefeicaoOfertas()
        if data_inicio.weekday() != 0:
            data_inicio = data_inicio - relativedelta(days=data_inicio.weekday())
        refeicoes_disponiveis = self.get_disponibilidade(inicio=data_inicio)

        if refeicoes_disponiveis:
            for turno in ['cafe', 'almoco', 'jantar']:
                getattr(ofertas, turno).seg = refeicoes_disponiveis[turno]['oferta'][0]
                getattr(ofertas, turno).ter = refeicoes_disponiveis[turno]['oferta'][1]
                getattr(ofertas, turno).qua = refeicoes_disponiveis[turno]['oferta'][2]
                getattr(ofertas, turno).qui = refeicoes_disponiveis[turno]['oferta'][3]
                getattr(ofertas, turno).sex = refeicoes_disponiveis[turno]['oferta'][4]
        return ofertas


class InscricaoAtivaManager(models.Manager):
    def get_queryset(self):
        query_set = super().get_queryset()
        return query_set.filter(ativa=True)


class Inscricao(models.ModelPlus):
    """
    Inscrição de aluno em um programa
    """

    PENDENTE_DOCUMENTACAO = 'Pendente de documentação'
    INDEFERIDO = 'Indeferido'
    DEFERIDO = 'Deferido'
    DEFERIDO_SEM_RECURSO = 'Deferido, mas sem recurso disponível'
    SEM_PARECER = 'Sem parecer'
    # exigidas juntas pelo botão "Efetuar Inscrição" e pela view inscricao_identificacao (só Assistente Social)
    PERMS_EFETUAR_INSCRICAO = ('ae.add_inscricao', 'ae.pode_ver_motivo_solicitacao')
    SITUACAO_PARECER_CHOICES = (
        ('Deferido', 'Deferido'),
        (DEFERIDO_SEM_RECURSO, DEFERIDO_SEM_RECURSO),
        (PENDENTE_DOCUMENTACAO, PENDENTE_DOCUMENTACAO),
        (INDEFERIDO, INDEFERIDO),
        (SEM_PARECER, SEM_PARECER),
        ('Pendência corrigida para nova análise', 'Pendência corrigida para nova análise'),
    )

    SITUACAO_PARECER_FORM_CHOICES = (
        ('', '--------------'),
        (DEFERIDO, DEFERIDO),
        ('Deferido, mas sem recurso disponível', 'Deferido, mas sem recurso disponível'),
        (PENDENTE_DOCUMENTACAO, PENDENTE_DOCUMENTACAO),
        ('Indeferido', 'Indeferido'),
    )

    VALIDADO = 'Validado'
    INVALIDADO = 'Invalidado'
    PENDENTE = 'Pendente'
    VALIDACAO_CHOICES = (
        (PENDENTE, PENDENTE),
        (VALIDADO, VALIDADO),
        (INVALIDADO, INVALIDADO),
    )

    programa = models.ForeignKeyPlus(Programa, verbose_name='Programa', on_delete=models.CASCADE)
    aluno = models.ForeignKeyPlus('edu.Aluno', verbose_name='Aluno', on_delete=models.CASCADE)
    data_cadastro = models.DateTimeField('Data')
    motivo = models.TextField('Motivo da Solicitação')
    ativa = models.BooleanField('Ativa', default=False)
    documentada = models.BooleanField('Doc. Entregue', default=False)
    data_documentacao = models.DateTimeField('Data de Entrega da Documentação', null=True)
    prioritaria = models.BooleanField('Prioritária', default=False)
    parecer = models.CharField('Parecer da Inscrição', max_length=1000, null=True, blank=True)
    parecer_autor_vinculo = models.ForeignKeyPlus(
        'comum.Vinculo',
        verbose_name='Autor do Parecer',
        related_name='ae_autor_parecer_inscricao_vinculo',
        null=True,
        blank=True,
        on_delete=models.CASCADE,
    )
    parecer_data = models.DateTimeFieldPlus('Data do Parecer', null=True, blank=True)
    situacao_parecer = models.CharFieldPlus('Situação do Parecer', choices=SITUACAO_PARECER_CHOICES, max_length=50, default='Sem parecer')
    periodo_inscricao = models.ForeignKeyPlus(
        'ae.PeriodoInscricao', verbose_name='Período de Inscrição', on_delete=models.CASCADE, null=True, blank=True
    )
    selecionada = models.BooleanField('Selecionada', default=False)
    atualizado_por = models.ForeignKeyPlus(
        'comum.Vinculo', null=True, verbose_name='Atualizado Por', related_name='inscricao_atualizado_por', on_delete=models.CASCADE
    )
    atualizado_em = models.DateTimeFieldPlus('Atualizado em', null=True)
    entrega_doc_atualizada_por = models.ForeignKeyPlus(
        'comum.Vinculo',
        null=True,
        verbose_name='Situação da Documentação Atualizada Por',
        related_name='inscricao_documentacao_atualizado_por',
        on_delete=models.CASCADE,
    )
    entrega_doc_atualizada_em = models.DateTimeFieldPlus('Situação da Documentação Atualizada em', null=True)
    pendente_assinatura = models.BooleanField('Pendente de Assinatura', default=False)
    id_documento_termo_compromisso = models.PositiveIntegerField(verbose_name='ID do Documento do Termo de Compromisso', null=True)
    termo_compromisso_digitalizado = models.PrivateFileField(
        verbose_name='Termo de Compromisso Digitalizado', max_length=255, null=True, blank=True, upload_to='ae/inscricao/documentos'
    )
    validacao_termo_compromisso = models.CharFieldPlus(
        'Validação do Termo de Compromisso', max_length=50, default='Pendente', choices=VALIDACAO_CHOICES
    )
    justificativa_validacao = models.TextField('Justificativa da Validação', null=True, blank=True)
    termo_avaliado_em = models.DateTimeFieldPlus('Termo de Compromisso avaliado em', null=True)
    termo_avaliado_por = models.ForeignKeyPlus(
        'comum.Vinculo',
        null=True,
        verbose_name='Termo de Compromisso avaliado por',
        related_name='inscricao_termo_compromisso_avaliado_por',
        on_delete=models.CASCADE,
    )
    resposta_aluno = models.TextField('Resposta ao aluno', null=True, blank=True)
    bolsas_internas_externas = models.ManyToManyFieldPlus('ae.TipoBolsa', verbose_name='Bolsas')
    # CadÚnico
    data_hora_consulta_cadunico = models.DateTimeFieldPlus(null=True)
    info_cadunico = models.JSONField(null=True)

    objects = models.Manager()
    ativas = InscricaoAtivaManager()

    class Meta:
        verbose_name = 'Inscrição'
        verbose_name_plural = 'Inscrições'
        ordering = ['-data_cadastro']
        permissions = (
            ('pode_ver_inscricao', 'Pode visualizar Inscrição'),
            ('pode_ver_comprovante_inscricao', 'Pode ver Comprovante de Inscrição'),
            ('pode_ver_motivo_solicitacao', 'Pode ver o Motivo da Solicitação'),
            ('pode_ver_relatorio_inscricao_todos', 'Pode ver Relatórios de todas as Inscrições'),
        )

    def __str__(self):
        return f'{self.aluno.matricula} - {self.programa.get_tipo()}'

    def get_absolute_url(self):
        return f'/ae/inscricao/{self.pk}'

    @transaction.atomic
    def sub_instance(self):
        if self.programa.get_tipo() == Programa.TIPO_ALIMENTACAO:
            try:
                return InscricaoAlimentacao.objects.get(pk=self.pk)
            except Exception:
                # Cria a sub classe, no caso das inscrições que foram importadas
                solicitacao_cafe = SolicitacaoAlimentacao.objects.create()
                solicitacao_almoco = SolicitacaoAlimentacao.objects.create()
                solicitacao_janta = SolicitacaoAlimentacao.objects.create()
                cur = connection.cursor()
                sql = (
                    'INSERT INTO ae_inscricaoalimentacao (inscricao_ptr_id, solicitacao_cafe_id, solicitacao_almoco_id, solicitacao_janta_id) '
                    f'values ({self.id:d}, {solicitacao_cafe.id:d}, {solicitacao_almoco.id:d}, {solicitacao_janta.id:d})'
                )
                cur.execute(sql)
                connection._commit()
                return InscricaoAlimentacao.objects.get(pk=self.pk)

        if self.programa.get_tipo() == Programa.TIPO_TRABALHO:
            try:
                return InscricaoTrabalho.objects.get(pk=self.pk)
            except Exception:
                # Cria a sub classe, no caso das inscrições que foram importadas
                cur = connection.cursor()
                sql = f"INSERT INTO ae_inscricaotrabalho (inscricao_ptr_id, turno, habilidades) values ({self.id:d}, '', '')"
                cur.execute(sql)
                connection._commit()
                return InscricaoTrabalho.objects.get(pk=self.pk)

        if self.programa.get_tipo() == Programa.TIPO_TRANSPORTE:
            try:
                return InscricaoPasseEstudantil.objects.get(pk=self.pk)
            except Exception:
                # Cria a sub classe, no caso das inscrições que foram importadas
                cur = connection.cursor()
                sql = f"INSERT INTO ae_inscricaopasseestudantil (inscricao_ptr_id, tipo_passe) values ({self.id:d}, '')"
                cur.execute(sql)
                connection._commit()
                return InscricaoPasseEstudantil.objects.get(pk=self.pk)

        if self.programa.get_tipo() == Programa.TIPO_IDIOMA:
            try:
                return InscricaoIdioma.objects.get(pk=self.pk)
            except Exception:
                # Cria a sub classe, no caso das inscrições que foram importadas
                cur = connection.cursor()
                sql = f'INSERT INTO ae_inscricaoidioma (inscricao_ptr_id, primeira_opcao_id, segunda_opcao_id) values ({self.id:d}, 1, 1)'
                cur.execute(sql)
                connection._commit()
                return InscricaoIdioma.objects.get(pk=self.pk)

        return None

    def get_ultima_participacao(self):
        return self.get_participacao_aberta() or self.participacao_set.order_by('-data_termino').latest('data_termino')

    def get_participacao_aberta(self):
        hoje = date.today()
        participacao_aberta = (
            Participacao.objects.filter(aluno=self.aluno, programa=self.programa)
            .filter(Q(data_inicio__lte=hoje), Q(data_termino__isnull=True) | Q(data_termino__gte=hoje))
            .select_related('aluno')
            .only('data_inicio', 'data_termino', 'programa', 'aluno')
            .first()
        )
        return participacao_aberta

    def get_respostas_inscricao(self):
        return RespostaInscricaoPrograma.objects.filter(inscricao=self).order_by('pergunta__ordem', 'id').distinct('pergunta__ordem')

    def get_respostas_inscricao_para_analise(self):
        return (
            RespostaInscricaoPrograma.objects.filter(inscricao=self, pergunta__deve_compor_analise=True)
            .order_by('pergunta__ordem', 'id')
            .distinct('pergunta__ordem')
        )

    def tem_documento_pendente_correcao(self):
        return (
            self.situacao_parecer == Inscricao.PENDENTE_DOCUMENTACAO
            and DocumentoInscricaoAluno.objects.filter(
                pendente=True, pendencia_corrigida=False, aluno=self.aluno, prazo_correcao__gte=datetime.datetime.now()
            ).exists()
        )

    def pendente_de_assinatura(self):
        return self.situacao_parecer == Inscricao.DEFERIDO and self.pendente_assinatura

    @property
    def possui_parecer(self) -> bool:
        return self.situacao_parecer != Inscricao.SEM_PARECER

    def salvar_parecer(self, request, situacao, parecer=None):
        vinculo = request.user.get_vinculo()
        agora = datetime.datetime.now()
        self.situacao_parecer = situacao
        self.parecer = parecer
        self.parecer_autor_vinculo = vinculo
        self.parecer_data = agora
        if self.programa.tipo_programa.id_modelo_termo_compromisso:
            self.pendente_assinatura = True
        self.save()
        HistoricoAlteracaoParecer.objects.create(
            inscricao=self, situacao_parecer=self.situacao_parecer, parecer=self.parecer, cadastrado_em=agora, cadastrado_por=vinculo
        )
        if self.situacao_parecer == Inscricao.PENDENTE_DOCUMENTACAO:
            Inscricao.ativas.filter(aluno=self.aluno).update(situacao_parecer=Inscricao.PENDENTE_DOCUMENTACAO)
        else:
            DocumentoInscricaoAluno.objects.filter(aluno=self.aluno).update(pendente=False)
        return


class InscricaoAlimentacao(Inscricao):
    """
    Inscrição de aluno em um programa de alimentacao
    """

    solicitacao_cafe = models.ForeignKeyPlus(
        'ae.SolicitacaoAlimentacao', on_delete=models.CASCADE, verbose_name='Solicitação de Café', related_name='solicitacao_cafe'
    )
    solicitacao_almoco = models.ForeignKeyPlus(
        'ae.SolicitacaoAlimentacao', on_delete=models.CASCADE, verbose_name='Solicitação de Almoço', related_name='solicitacao_almoco'
    )
    solicitacao_janta = models.ForeignKeyPlus(
        'ae.SolicitacaoAlimentacao', on_delete=models.CASCADE, verbose_name='Solicitação de Jantar', related_name='solicitacao_janta'
    )
    motivo_atendimento = models.ForeignKeyPlus(
        'ae.MotivoSolicitacaoRefeicao', verbose_name='Motivo da Inscrição', on_delete=models.SET_NULL, null=True
    )

    class Meta:
        verbose_name = 'Inscrição em Alimentação Estudantil'
        verbose_name_plural = 'Inscrições em Alimentação Estudantil'

    def get_total_refeicoes_por_dia(self):
        solicitacoes = SolicitacaoAlimentacao.objects.filter(id__in=[self.solicitacao_almoco.id, self.solicitacao_janta.id, self.solicitacao_cafe.id])
        return [
            solicitacoes.filter(seg=True).count(),
            solicitacoes.filter(ter=True).count(),
            solicitacoes.filter(qua=True).count(),
            solicitacoes.filter(qui=True).count(),
            solicitacoes.filter(sex=True).count(),
        ]

    def get_seg(self):
        texto = []
        if self.solicitacao_cafe.seg:
            texto.append('1C')
        if self.solicitacao_almoco.seg:
            texto.append('1A')
        if self.solicitacao_janta.seg:
            texto.append('1J')
        return ', '.join(texto)

    def get_ter(self):
        texto = []
        if self.solicitacao_cafe.ter:
            texto.append('1C')
        if self.solicitacao_almoco.ter:
            texto.append('1A')
        if self.solicitacao_janta.ter:
            texto.append('1J')
        return ', '.join(texto)

    def get_qua(self):
        texto = []
        if self.solicitacao_cafe.qua:
            texto.append('1C')
        if self.solicitacao_almoco.qua:
            texto.append('1A')
        if self.solicitacao_janta.qua:
            texto.append('1J')
        return ' '.join(texto)

    def get_qui(self):
        texto = []
        if self.solicitacao_cafe.qui:
            texto.append('1C')
        if self.solicitacao_almoco.qui:
            texto.append('1A')
        if self.solicitacao_janta.qui:
            texto.append('1J')
        return ' '.join(texto)

    def get_sex(self):
        texto = []
        if self.solicitacao_cafe.sex:
            texto.append('1C')
        if self.solicitacao_almoco.sex:
            texto.append('1A')
        if self.solicitacao_janta.sex:
            texto.append('1J')
        return ' '.join(texto)

    def get_por_semana(self):
        texto = []
        cafe = alm = jan = 0
        da_seg = self.get_seg()
        if '1C' in da_seg:
            cafe += 1
        if '1A' in da_seg:
            alm += 1
        if '1J' in da_seg:
            jan += 1
        da_ter = self.get_ter()
        if '1C' in da_ter:
            cafe += 1
        if '1A' in da_ter:
            alm += 1
        if '1J' in da_ter:
            jan += 1
        da_qua = self.get_qua()
        if '1C' in da_qua:
            cafe += 1
        if '1A' in da_qua:
            alm += 1
        if '1J' in da_qua:
            jan += 1
        da_qui = self.get_qui()
        if '1C' in da_qui:
            cafe += 1
        if '1A' in da_qui:
            alm += 1
        if '1J' in da_qui:
            jan += 1
        da_sex = self.get_sex()
        if '1C' in da_sex:
            cafe += 1
        if '1A' in da_sex:
            alm += 1
        if '1J' in da_sex:
            jan += 1

        if cafe:
            texto.append(f'{cafe}C')
        if alm:
            texto.append(f'{alm}A')
        if jan:
            texto.append(f'{jan}J')
        return ' '.join(texto)


class InscricaoIdioma(Inscricao):
    """
    Inscrição de aluno em um programa de alimentacao
    """

    primeira_opcao = models.ForeignKeyPlus('OfertaTurma', on_delete=models.CASCADE, related_name='primeira_opcao', verbose_name='Primeira Opção')
    segunda_opcao = models.ForeignKeyPlus('OfertaTurma', on_delete=models.CASCADE, related_name='segunda_opcao', verbose_name='Segunda Opção')

    class Meta:
        verbose_name = 'Inscrição em Curso de Idiomas'
        verbose_name_plural = 'Inscrições em Curso de Idiomas'


class InscricaoTrabalho(Inscricao):
    setor_preferencia = models.ForeignKeyPlus(Setor, null=True, blank=True, verbose_name='Setor de Preferência', on_delete=models.CASCADE)
    turno = models.CharFieldPlus(choices=TurnoChoices.TURNO_CHOICES)
    habilidades = models.TextField('Habilidades')
    dados_bancarios = models.OneToOneField('ae.DadosBancarios', verbose_name='Dados Bancários', null=True, on_delete=models.CASCADE)
    bolsas = models.ManyToManyFieldPlus('ae.TipoBolsa', verbose_name='Bolsas')

    class Meta:
        verbose_name = 'Inscrição em Apoio à Formação Estudantil'
        verbose_name_plural = 'Inscrições em Apoio à Formação Estudantil'


class InscricaoPasseEstudantil(Inscricao):
    OFERTA_IRREGULAR = 'Sim, mas a oferta é irregular'
    OFERTA_CHOICES = (
        ('Sim, todo o trajeto', 'Sim, todo o trajeto'),
        ('Sim, apenas parte do trajeto', 'Sim, apenas parte do trajeto'),
        (OFERTA_IRREGULAR, OFERTA_IRREGULAR),
        ('Não', 'Não'),
    )
    tipo_passe = models.CharField(max_length=3, choices=PassesChoices.PASSES_CHOICES, verbose_name='Tipo de Passe')
    dados_bancarios = models.OneToOneField('ae.DadosBancarios', verbose_name='Dados Bancários', null=True, on_delete=models.CASCADE)
    valor_transporte = models.DecimalFieldPlus(
        'Valor gasto com transporte por dia',
        help_text='Se utiliza meio de transporte (ônibus, mototáxi, transporte locado), especifique o valor gasto.',
        null=True,
    )
    trajeto = models.TextField('Descrição do trajeto', null=True)
    oferta_transporte_gratuito = models.CharFieldPlus(
        'A prefeitura do seu município oferta o transporte escolar gratuito?', choices=OFERTA_CHOICES, null=True, max_length=50
    )
    oferta_transporte_gratuito_descricao = models.CharFieldPlus('Qual a irregularidade?', null=True, max_length=5000)

    class Meta:
        verbose_name = 'Inscrição em Auxílio Transporte'
        verbose_name_plural = 'Inscrições em Auxílio Transporte'


class DadosBancarios(models.ModelPlus):
    BANCO_BB = 'BANCO DO BRASIL'
    BANCO_CEF = 'CAIXA ECONÔMICA'
    BRADESCO = 'BRADESCO'
    ITAU = 'ITAU'
    SANTANDER = 'SANTANDER'
    NORDESTE = 'BANCO DO NORDESTE'

    BANCO_CHOICES = (
        (BANCO_BB, '001 - Banco do Brasil'),
        (BANCO_CEF, '104 - Caixa Econômica'),
        (BRADESCO, '237 - Bradesco'),
        (ITAU, '341- Itaú'),
        (SANTANDER, '033 - Santander'),
        (NORDESTE, '004 - Banco do Nordeste'),
    )

    TIPOCONTA_CONTACORRENTE = 'Conta Corrente'
    TIPOCONTA_POUPANCA = 'Conta Poupança'

    TIPOCONTA_CHOICES = ((TIPOCONTA_CONTACORRENTE, 'Conta Corrente'), (TIPOCONTA_POUPANCA, 'Conta Poupança'))

    banco = models.CharField('Banco', max_length=50, choices=BANCO_CHOICES, null=True)
    instituicao = models.ForeignKeyPlus('rh.Banco', verbose_name='Banco', null=True, on_delete=models.SET_NULL)
    numero_agencia = models.CharField('Número da Agência', max_length=50, null=True, help_text='Ex: 3293-X')
    tipo_conta = models.CharField('Tipo da Conta', max_length=50, choices=TIPOCONTA_CHOICES, null=True)
    numero_conta = models.CharField('Número da Conta', max_length=50, null=True, help_text='Ex: 23384-6')
    operacao = models.CharField('Operação', max_length=50, null=True, blank=True)

    aluno = models.ForeignKeyPlus('edu.Aluno')
    prioritario_servico_social = models.BooleanField('Prioritário para Serviço Social', default=False)
    atualizado_por = models.ForeignKeyPlus(
        'comum.Vinculo', null=True, verbose_name='Atualizado Por', related_name='dadosbancarios_atualizado_por', on_delete=models.CASCADE
    )
    atualizado_em = models.DateTimeFieldPlus('Atualizado em', null=True)

    class Meta:
        verbose_name = 'Dados Bancários'
        verbose_name_plural = 'Dados Bancários'


class ParticipacoesAbertasManager(models.Manager):
    def get_queryset(self):
        hoje = date.today()
        return super().get_queryset().filter(Q(data_inicio__lte=hoje), Q(data_termino__gte=hoje) | Q(data_termino__isnull=True))


class ParticipacoesFuturasManager(models.Manager):
    def get_queryset(self):
        hoje = date.today()
        return super().get_queryset().filter(Q(data_inicio__gt=hoje), Q(data_termino__gte=hoje) | Q(data_termino__isnull=True))


class Participacao(models.ModelPlus):
    """
    É a concretização de participação de uma inscrição.
    O aluno não poderá participar de mais de um programa do mesmo tipo ao mesmo tempo.
    """

    programa = models.ForeignKeyPlus('ae.Programa', verbose_name='Programa', null=True, blank=True, on_delete=models.CASCADE)
    aluno = models.ForeignKeyPlus('edu.Aluno', verbose_name='Aluno', null=True, blank=True, on_delete=models.CASCADE)
    # depois de alterado tudo remover o atributo abaixo ou não
    inscricao = models.ForeignKeyPlus('ae.Inscricao', verbose_name='Inscrição', on_delete=models.CASCADE)
    data_inicio = models.DateField('Data de Início')
    data_termino = models.DateField('Data de Saída', null=True, blank=True)
    observacao = models.TextField('Observação', blank=True)
    motivo_termino = models.TextField('Motivo de Saída', blank=True)
    motivo_entrada = models.TextField('Motivo de Entrada', blank=True)
    atualizado_por = models.ForeignKeyPlus(
        'comum.Vinculo', null=True, verbose_name='Atualizado Por', related_name='participacao_atualizado_por', on_delete=models.CASCADE
    )
    atualizado_em = models.DateTimeFieldPlus('Atualizado em', null=True)
    finalizado_por = models.ForeignKeyPlus(
        'comum.Vinculo', null=True, verbose_name='Finalizado Por', related_name='participacao_finalizado_por', on_delete=models.CASCADE
    )
    finalizado_em = models.DateTimeFieldPlus('Finalizado em', null=True)
    cadastrado_por = models.CurrentUserField(verbose_name='Cadastrado Por', null=True, blank=True)
    cadastrado_em = models.DateTimeField('Data de Cadastro', auto_now_add=True, null=True, blank=True)

    # Managers
    objects = models.Manager()
    abertas = ParticipacoesAbertasManager()
    futuras = ParticipacoesFuturasManager()

    class Meta:
        verbose_name = 'Participação'
        verbose_name_plural = 'Participações'
        permissions = (
            ('pode_revogar_participacao', 'Pode finalizar participação de qualquer programa'),
            ('pode_ver_motivo_termino', 'Pode ver Motivo de Saída'),
            ('pode_editar_participacao', 'Pode editar Participação'),
            ('pode_ver_relatorio_participacao_todos', 'Pode ver Relatórios de Participação de todos os campi'),
            ('pode_ver_relatorio_participacao_do_campus', 'Pode ver Relatórios de participação do próprio campus'),
            ('pode_ver_motivo_entrada', 'Pode ver Motivo de Entrada'),
        )
        ordering = ['-data_inicio']

    def sub_instance(self):
        tipo = self.programa.get_tipo()

        if tipo == Programa.TIPO_ALIMENTACAO:
            try:
                return self.participacaoalimentacao
            except ParticipacaoAlimentacao.DoesNotExist:
                cafe = SolicitacaoAlimentacao()
                cafe.save()
                almoco = SolicitacaoAlimentacao()
                almoco.seg = True
                almoco.save()
                janta = SolicitacaoAlimentacao()
                janta.save()

                correcao_alimentacao = ParticipacaoAlimentacao.objects.create(
                    participacao=self,
                    solicitacao_atendida_cafe=cafe,
                    solicitacao_atendida_almoco=almoco,
                    solicitacao_atendida_janta=janta,
                    categoria=CategoriaAlimentacao.objects.get(pk=3),
                )
                return correcao_alimentacao

        elif tipo == Programa.TIPO_IDIOMA:
            try:
                return self.participacaoidioma
            except ParticipacaoIdioma.DoesNotExist:
                turmas = OfertaTurma.objects.filter(campus=self.aluno.curso_campus.diretoria.setor.uo)
                if turmas.exists():
                    turma = turmas[0]
                else:
                    turma = None
                correcao_idioma = ParticipacaoIdioma.objects.create(participacao=self, turma_selecionada=turma)
                return correcao_idioma

        elif tipo == Programa.TIPO_TRANSPORTE:
            try:
                return self.participacaopasseestudantil
            except ParticipacaoPasseEstudantil.DoesNotExist:
                correcao_passe = ParticipacaoPasseEstudantil.objects.create(
                    participacao=self, valor_concedido=Decimal('0.0'), tipo_passe_concedido=PassesChoices.MUNICIPAL
                )
                return correcao_passe

        elif tipo == Programa.TIPO_TRABALHO:
            try:
                return self.participacaotrabalho
            except ParticipacaoTrabalho.DoesNotExist:
                campus_aluno = self.aluno.curso_campus.diretoria.setor.uo
                setor_aluno = self.aluno.curso_campus.diretoria.setor
                bolsas = OfertaBolsa.objects.filter(campus=campus_aluno)
                if bolsas.exists():
                    bolsa = bolsas[0]
                else:
                    bolsa = OfertaBolsa.objects.create(
                        campus=campus_aluno, setor=setor_aluno, turno=TurnoChoices.MANHA, descricao_funcao='Alimentação'
                    )
                correcao_trabalho = ParticipacaoTrabalho.objects.create(participacao=self, bolsa_concedida=bolsa)

                return correcao_trabalho
        else:
            return self

    def get_respostas(self):
        return RespostaParticipacao.objects.filter(participacao=self)

    def save(self, *args, **kargs):
        super().save(*args, **kargs)

        if self.data_termino:
            self.inscricao.save()
            participacao = self.sub_instance()
            hoje = date.today()
            if self.programa.get_tipo() == Programa.TIPO_TRABALHO and self.data_termino:
                data_de_termino = self.data_termino
                if type(self.data_termino) is datetime.datetime:
                    data_de_termino = self.data_termino.date()
                if data_de_termino < hoje and hasattr(participacao, 'bolsa_concedida'):
                    participacao.bolsa_concedida.disponivel = True
                    participacao.bolsa_concedida.save()

    @classmethod
    def get_conflitos(cls, user, tamanho, campus=None):
        programas = Programa.objects.all()
        if user.groups.filter(name='Coordenador de Atividades Estudantis Sistêmico').exists():
            if campus:
                programas = programas.filter(instituicao=campus)
        else:
            uo = get_uo(user)
            programas = programas.filter(instituicao=uo)

        contador = 0
        participacoes_conflitantes = {}
        for programa in programas:
            inconsistencias = (
                Participacao.objects.only('aluno', 'data_termino', 'data_inicio', 'programa')
                .exclude(data_termino__isnull=True)
                .filter(data_termino__lte=F('data_inicio'), programa=programa)
            )
            if inconsistencias.exists():
                for participacao in inconsistencias:
                    participacoes_conflitantes[participacao.aluno_id] = participacao
                    contador += 1
                    if contador == tamanho and tamanho:
                        return list(participacoes_conflitantes.values())
            else:
                # ids dos alunos que tem mais de uma participação
                alunos_ids = (
                    Participacao.objects.filter(programa=programa)
                    .values('aluno__id')
                    .annotate(count=Count('aluno__id'))
                    .filter(count__gt=1)
                    .values_list('aluno__id', flat=True)
                )
                if alunos_ids:
                    hoje = datetime.date.today()
                    participacoes = (
                        Participacao.objects.filter(aluno__id__in=alunos_ids)
                        .select_related('aluno')
                        .only('aluno', 'data_inicio', 'data_termino', 'programa')
                        .order_by('-id')
                    )
                    for participacao in participacoes:
                        for p in participacoes.filter(aluno=participacao.aluno_id, programa=participacao.programa_id).exclude(pk=participacao.pk):
                            data_termino1 = participacao.data_termino or hoje
                            data_termino2 = p.data_termino or hoje
                            if contador == tamanho and tamanho:
                                return list(participacoes_conflitantes.values())

                            if (
                                data_termino1 > participacao.data_inicio
                                and p.data_inicio < data_termino2
                                and existe_conflito_entre_intervalos([participacao.data_inicio, data_termino1, p.data_inicio, data_termino2])
                            ):
                                if p.aluno_id not in participacoes_conflitantes:
                                    participacoes_conflitantes[p.aluno_id] = p
                                    contador += 1
                                    break

        # retorna a lista das participações com conflito
        return list(participacoes_conflitantes.values())

    def tem_conflito(self):
        for p in Participacao.objects.filter(aluno=self.aluno_id, programa_id=self.programa.id).exclude(pk=self.pk):
            data_termino1 = self.data_termino or datetime.date.today()
            data_termino2 = p.data_termino or datetime.date.today()
            if existe_conflito_entre_intervalos([self.data_inicio, data_termino1, p.data_inicio, data_termino2]):
                return True

    def part_alim_suspensa(self):
        if ParticipacaoAlimentacao.objects.filter(participacao=self).exists():
            return ParticipacaoAlimentacao.objects.filter(participacao=self)[0].suspensa
        return False

    def faltas_justificadas(self):
        if HistoricoFaltasAlimentacao.objects.filter(participacao=self, justificativa__isnull=False).exists():
            return HistoricoFaltasAlimentacao.objects.filter(participacao=self, justificativa__isnull=False)
        return False

    def tem_pendencias(self):
        pendencias = ''

        if not self.aluno.situacao.ativo:
            pendencias += '<p class="checklist error">Matrícula inativa na instituição.</p>'
        if not Inscricao.objects.filter(aluno=self.aluno, programa=self.programa, ativa=True).exists():
            pendencias += '<p class="checklist error">Inscrição inativa no programa.</p>'
        if not Caracterizacao.objects.filter(aluno=self.aluno).exists():
            pendencias += '<p class="checklist error">Não realizou a Caracterização.</p>'
        if not self.aluno.documentada:
            if (
                self.aluno.data_documentacao
                and DocumentoInscricaoAluno.objects.filter(aluno=self.aluno, data_cadastro__gt=self.aluno.data_documentacao).exists()
            ):
                pendencias += '<p class="checklist error">Documentação não foi entregue e há documentos novos.</p>'
            else:
                pendencias += '<p class="checklist error">Documentação não foi entregue, mas não há documentos novos.</p>'
        if self.part_alim_suspensa():
            pendencias += '<p class="checklist error">Participação suspensa: três faltas no mesmo mês.</p>'
        if self.programa.get_tipo() in [Programa.TIPO_TRANSPORTE, Programa.TIPO_TRABALHO]:
            dados = DadosBancarios.objects.filter(aluno=self.aluno)
            if not dados.exists():
                pendencias += f'<p class="checklist error"><a href="/edu/aluno/{self.aluno.matricula}/?tab=dados_bancarios">Sem dados bancários cadastrados.</a></p>'
            elif dados.count() > 1 and not dados.filter(prioritario_servico_social=True).exists():
                pendencias += f'<p class="checklist error"><a href="/edu/aluno/{self.aluno.matricula}/?tab=dados_bancarios">Sem indicação da conta bancária prioritária.</a></p>'
        return pendencias

    def exibir_atualizacao(self):
        if not self.cadastrado_em:
            return True
        return bool(
            self.cadastrado_em and self.atualizado_em and self.cadastrado_em.replace(microsecond=0) != self.atualizado_em.replace(microsecond=0)
        )


class ParticipacaoAlimentacao(models.ModelPlus):
    participacao = models.OneToOneField('ae.Participacao', verbose_name='Participação', on_delete=models.CASCADE)
    solicitacao_atendida_cafe = models.OneToOneField(
        'ae.SolicitacaoAlimentacao',
        verbose_name='Solicitação Atendida de Café da manhã',
        on_delete=models.CASCADE,
        related_name='participacao_alimentacao_cafe',
        null=True,
    )
    solicitacao_atendida_almoco = models.OneToOneField(
        'ae.SolicitacaoAlimentacao',
        verbose_name='Solicitação Atendida de Almoço',
        on_delete=models.CASCADE,
        related_name='participacao_alimentacao_almoco',
        null=True,
    )
    solicitacao_atendida_janta = models.OneToOneField(
        'ae.SolicitacaoAlimentacao',
        verbose_name='Solicitação Atendida de Jantar',
        on_delete=models.CASCADE,
        related_name='participacao_alimentacao_janta',
        null=True,
    )
    categoria = models.ForeignKeyPlus('ae.CategoriaAlimentacao', verbose_name='Categoria', null=True, on_delete=models.CASCADE)
    suspensa = models.BooleanField('Suspensa', default=False)
    suspensa_em = models.DateField('Data da Suspensão', null=True, blank=True)
    liberar_em = models.DateField('Data da Liberação', null=True, blank=True)
    liberado_por_vinculo = models.ForeignKeyPlus('comum.Vinculo', verbose_name='Responsável pela Liberação', on_delete=models.CASCADE, null=True)
    motivo_atendimento = models.ForeignKeyPlus(
        'ae.MotivoSolicitacaoRefeicao', verbose_name='Motivo do Atendimento', on_delete=models.SET_NULL, null=True
    )
    qtd_faltas_alimentacao = models.IntegerFieldPlus('Quantidade de faltas atuais', default=0)

    class Meta:
        permissions = (('pode_revogar_participacaoalimentacao', 'Pode fechar participação'),)

    def obter_proximo_dia_e_refeicoes(self):
        """
        Retorna uma tupla: (data, [lista_de_refeicoes])
        Exemplo de retorno: (datetime.date(2026, 9, 22), ['café', 'almoço'])
        Caso não haja refeições, retorna (None, [])
        """
        hoje = datetime.date.today()

        # Mapeamento do weekday do Python (0=Segunda, ..., 6=Domingo) para os atributos do modelo
        DIAS_SEMANA_MAP = {
            0: 'seg',
            1: 'ter',
            2: 'qua',
            3: 'qui',
            4: 'sex',
            5: 'sab',
            6: 'dom',
        }

        # Mapeia o nome legível da refeição para o objeto de solicitação correspondente
        mapa_refeicoes = {
            'café': self.solicitacao_atendida_cafe,
            'almoço': self.solicitacao_atendida_almoco,
            'jantar': self.solicitacao_atendida_janta,
        }

        # Procura nos próximos 7 dias (começando por hoje)
        for offset in range(7):
            data_candidata = hoje + datetime.timedelta(days=offset)

            datas_liberadas = DatasLiberadasFaltasAlimentacao.objects.filter(campus=self.participacao.programa.instituicao)
            if (
                datas_liberadas.filter(data=data_candidata).exists()
                or datas_liberadas.filter(recorrente=True, data__day=data_candidata.day, data__month=data_candidata.month).exists()
            ):
                continue

            campo_dia = DIAS_SEMANA_MAP[data_candidata.weekday()]

            refeicoes_do_dia = []

            # Verifica para cada tipo de refeição se o booleano do dia está True
            for tipo_refeicao, solicitacao in mapa_refeicoes.items():
                if solicitacao and getattr(solicitacao, campo_dia, False):
                    refeicoes_do_dia.append(tipo_refeicao)

            # Se encontrou ao menos uma refeição nesse dia, retorna a data e as refeições
            if refeicoes_do_dia:
                return data_candidata, refeicoes_do_dia

        return None, []


models.signals.post_save.connect(atualizar_config_refeicao, sender=ParticipacaoAlimentacao)


class ParticipacaoIdioma(models.ModelPlus):
    participacao = models.OneToOneField('ae.Participacao', verbose_name='Participação', on_delete=models.CASCADE)
    turma_selecionada = models.ForeignKeyPlus('OfertaTurma', verbose_name='Turma Selecionada', null=True, blank=True, on_delete=models.CASCADE)
    idioma = models.ForeignKeyPlus('Idioma', verbose_name='Idioma', null=True, blank=True, on_delete=models.CASCADE)


class ParticipacaoTrabalho(models.ModelPlus):
    participacao = models.OneToOneField('ae.Participacao', verbose_name='Participação', on_delete=models.CASCADE)
    bolsa_concedida = models.ForeignKeyPlus('ae.OfertaBolsa', verbose_name='Bolsa Concedida', null=True, on_delete=models.CASCADE)
    pendente_ciencia = models.BooleanField('Pendente de Ciência', default=False)
    ciencia_em = models.DateTimeFieldPlus('Ciência em', null=True)
    ciencia_por = models.ForeignKeyPlus(Vinculo, verbose_name='Ciência por', null=True)

    @transaction.atomic
    def save(self, *args, **kwargs):
        old = None
        if self.pk:
            old = ParticipacaoTrabalho.objects.get(pk=self.pk)
            if old.bolsa_concedida != self.bolsa_concedida and old.bolsa_concedida is not None:
                old.bolsa_concedida.disponivel = True
                old.bolsa_concedida.save()
        super().save(*args, **kwargs)
        self.bolsa_concedida.disponivel = False
        self.bolsa_concedida.save()

    @transaction.atomic
    def delete(self, *args, **kwargs):
        self.bolsa_concedida.disponivel = True
        self.bolsa_concedida.save()
        super().delete(*args, **kwargs)


class ParticipacaoPasseEstudantil(models.ModelPlus):
    participacao = models.OneToOneField('ae.Participacao', verbose_name='Participação', on_delete=models.CASCADE)
    valor_concedido = models.DecimalFieldPlus('Valor Concedido (R$)', null=True, blank=True)
    tipo_passe_concedido = models.CharField(
        max_length=3, choices=PassesChoices.PASSES_CHOICES, verbose_name='Tipo de Passe Concedido', null=True, blank=True
    )


class DemandaAlunoAtendida(models.ModelPlus):
    """
    Uma demanda que foi utilizada pelo aluno.
    O aluno pode ou não ter a demanda atendida por meio de um programa,
    por isso ``programa`` pode ser nulo.
    O aluno obrigatoriamente deve ter inscrição em qualquer programa para ter
    uma demanda atendida.
    """

    responsavel_vinculo = models.ForeignKeyPlus('comum.Vinculo', null=True, blank=True, verbose_name='Responsável', on_delete=models.CASCADE)
    demanda = models.ForeignKeyPlus('ae.DemandaAluno', verbose_name='Tipo de Atendimento', on_delete=models.CASCADE)
    programa = models.ForeignKeyPlus('ae.Programa', verbose_name='Programa', null=True, blank=True, on_delete=models.CASCADE)
    aluno = models.ForeignKeyPlus('edu.Aluno', verbose_name='Aluno', on_delete=models.CASCADE)
    data = models.DateTimeField('Atendimento', null=True)
    quantidade = models.FloatField('Quantidade', default=1)
    valor = models.DecimalFieldPlus(
        'Valor', null=True, blank=True, help_text='Não é necessário ser preenchido para atendimentos vinculados às refeições'
    )
    observacao = models.TextField('Observação', blank=True)
    campus = models.ForeignKeyPlus('rh.UnidadeOrganizacional', verbose_name='Campus', on_delete=models.CASCADE)
    terminal = models.ForeignKeyPlus('ponto.Maquina', verbose_name='Terminal', on_delete=models.CASCADE, blank=True, null=True)
    data_registro = models.DateTimeField('Data de Registro', auto_now_add=True, null=True, blank=True)
    arquivo = models.PrivateFileField(verbose_name='Arquivo', max_length=255, null=True, blank=True, upload_to='ae/demandaalunoatendida')
    cadastrado_por = models.CurrentUserField(verbose_name='Cadastrado Por', null=True, blank=True)

    class Meta:
        verbose_name = 'Atendimento Individual'
        verbose_name_plural = 'Atendimentos Individuais'
        unique_together = ('aluno', 'demanda', 'data')
        permissions = (
            ('pode_ver_demanda_aluno_atendida', 'Pode ver Demanda Aluno Atendida'),
            ('pode_ver_relatorio_atendimento_todos', 'Pode ver Relatórios de Atendimentos de todos os campi'),
            ('pode_ver_relatorio_atendimento_do_campus', 'Pode ver Relatórios de Atendimentos do próprio campus'),
        )

    def __str__(self):
        return f'{self.demanda}'

    @transaction.atomic
    def save(self, *args, **kwargs):
        if not self.pk and not self.campus_id:
            self.campus = self.responsavel_vinculo.setor.uo
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return f'/ae/atendimento/{self.id}/'

    def get_cadastrado_por(self):
        return self.cadastrado_por or self.responsavel_vinculo and self.responsavel_vinculo.user or ''


class TipoAtendimentoSetor(models.ModelPlus):
    nome = models.CharFieldPlus('Nome', max_length=255, unique=True)
    descricao = models.TextField('Descrição')

    class Meta:
        verbose_name = 'Tipo de Auxílio'
        verbose_name_plural = 'Tipos de Auxílios'

    def __str__(self):
        return self.nome


class AtendimentoSetor(models.ModelPlus):
    campus = models.ForeignKeyPlus(UnidadeOrganizacional, verbose_name='Campus', on_delete=models.CASCADE)
    tipoatendimentosetor = models.ForeignKeyPlus('ae.TipoAtendimentoSetor', verbose_name='Tipo de Auxílio', on_delete=models.CASCADE)
    data = models.DateTimeField('Data de Início')
    data_termino = models.DateTimeField('Data de Fim', null=True, blank=True)
    valor = models.DecimalFieldPlus('Valor Total Utilizado', null=True, blank=True)
    setor = models.ForeignKeyPlus(Setor, verbose_name='Setor', null=True, blank=True, on_delete=models.CASCADE)
    observacao = models.TextField('Observação', blank=True)
    alunos = models.ManyToManyField('edu.Aluno', verbose_name='Alunos')
    numero_processo = models.CharFieldPlus('Número do Processo', max_length=255, blank=True)
    atualizado_por = models.ForeignKeyPlus(
        'comum.Vinculo', null=True, verbose_name='Atualizado Por', related_name='atendimentosetor_atualizado_por', on_delete=models.CASCADE
    )
    atualizado_em = models.DateTimeFieldPlus('Atualizado em', null=True)

    class Meta:
        verbose_name = 'Auxílio'
        verbose_name_plural = 'Auxílios'
        permissions = (
            ('pode_visualizar_auxilios', 'Pode ver Relatórios de Auxílios'),
            ('pode_visualizar_auxilios_campus', 'Pode ver Relatórios de Auxílios do próprio campus'),
        )

    def __str__(self):
        return '{} em {}'.format(self.tipoatendimentosetor, self.data.strftime('%d/%m/%Y %H:%M'))


class AgendamentoRefeicao(models.ModelPlus):
    TIPO_CAFE = 'CAF'
    TIPO_ALMOCO = 'ALM'
    TIPO_JANTAR = 'JAN'

    TIPO_CHOICES = ((TIPO_CAFE, 'Café da manhã'), (TIPO_ALMOCO, 'Almoço'), (TIPO_JANTAR, 'Jantar'))

    programa = models.ForeignKeyPlus(Programa, verbose_name='Programa', on_delete=models.CASCADE)
    aluno = models.ForeignKeyPlus('edu.Aluno', verbose_name='Aluno', on_delete=models.CASCADE)
    data = models.DateTimeFieldPlus()
    tipo_refeicao = models.CharField('Tipo de Refeição', max_length=3, choices=TIPO_CHOICES)
    atualizado_por = models.ForeignKeyPlus(
        'comum.Vinculo', null=True, verbose_name='Atualizado Por', related_name='agendamentorefeicao_atualizado_por', on_delete=models.CASCADE
    )
    atualizado_em = models.DateTimeFieldPlus('Atualizado em', null=True)
    cancelado = models.BooleanField('Cancelado', default=False)
    cancelado_por = models.ForeignKeyPlus(
        'comum.Vinculo', null=True, verbose_name='Cancelado Por', related_name='agendamentorefeicao_cancelado_por', on_delete=models.CASCADE
    )
    cancelado_em = models.DateTimeFieldPlus('Cancelado em', null=True)
    motivo_atendimento = models.ForeignKeyPlus(
        'ae.MotivoSolicitacaoRefeicao', verbose_name='Motivo do Agendamento', on_delete=models.SET_NULL, null=True
    )

    class Meta:
        verbose_name = 'Agendamento de Refeições'
        verbose_name_plural = 'Agendamentos de Refeições'


models.signals.post_save.connect(atualizar_config_refeicao, sender=AgendamentoRefeicao)


class DadosFincanceiros(models.ModelPlus):
    """
    Dados Financeiros, feita pelo setor de AE com base na documentação recebida
    do aluno.
    """

    aluno = models.OneToOneField('edu.Aluno', on_delete=models.CASCADE)
    despesa_agua = models.DecimalFieldPlus(default=0)
    despesa_energia = models.DecimalFieldPlus(default=0)
    despesa_telefone = models.DecimalFieldPlus(default=0)
    despesa_aluguel = models.DecimalFieldPlus(default=0)
    despesa_condominio = models.DecimalFieldPlus(default=0)
    despesa_financiamento_casa = models.DecimalFieldPlus(default=0)
    despesa_outras = models.DecimalFieldPlus(default=0)
    remuneracao_aluno = models.DecimalFieldPlus(default=0)
    remuneracao_pai = models.DecimalFieldPlus(default=0)
    remuneracao_mae = models.DecimalFieldPlus(default=0)
    remuneracao_tios = models.DecimalFieldPlus(default=0)
    remuneracao_avos = models.DecimalFieldPlus(default=0)
    remuneracao_parentes = models.DecimalFieldPlus(default=0)
    remuneracao_outros = models.DecimalFieldPlus(default=0)
    observacao = models.TextField('Observação', blank=True)

    class Meta:
        verbose_name = 'Dados Financeiros'
        verbose_name_plural = 'Dados Financeiros'

    def save(self, *args, **kwargs):
        """
        Assegura que os campos de despesa sejam negativos
        """
        campos_despesa = [
            'despesa_agua',
            'despesa_energia',
            'despesa_telefone',
            'despesa_aluguel',
            'despesa_condominio',
            'despesa_financiamento_casa',
        ]
        for campo_despesa in campos_despesa:
            valor_despesa = getattr(self, campo_despesa)
            if valor_despesa > 0:
                setattr(self, campo_despesa, -valor_despesa)
        super().save(*args, **kwargs)


class OfertaAlimentacao(models.ModelPlus):
    campus = models.ForeignKeyPlus(
        UnidadeOrganizacional, on_delete=models.CASCADE, verbose_name='Campus', related_name='configuracao_alimentacao_set'
    )
    dia_inicio = models.DateFieldPlus('Segunda-feira do Início da Oferta', null=True)
    dia_termino = models.DateFieldPlus('Sexta-feira do Término da Oferta', null=True)

    cafe_seg = models.PositiveIntegerField('Café da manhã/Segunda', null=False, default=0)
    cafe_ter = models.PositiveIntegerField('Café da manhã/Terça', null=False, default=0)
    cafe_qua = models.PositiveIntegerField('Café da manhã/Quarta', null=False, default=0)
    cafe_qui = models.PositiveIntegerField('Café da manhã/Quinta', null=False, default=0)
    cafe_sex = models.PositiveIntegerField('Café da manhã/Sexta', null=False, default=0)

    almoco_seg = models.PositiveIntegerField('Almoço/Segunda', null=False, default=0)
    almoco_ter = models.PositiveIntegerField('Almoço/Terça', null=False, default=0)
    almoco_qua = models.PositiveIntegerField('Almoço/Quarta', null=False, default=0)
    almoco_qui = models.PositiveIntegerField('Almoço/Quinta', null=False, default=0)
    almoco_sex = models.PositiveIntegerField('Almoço/Sexta', null=False, default=0)

    janta_seg = models.PositiveIntegerField('Jantar/Segunda', null=False, default=0)
    janta_ter = models.PositiveIntegerField('Jantar/Terça', null=False, default=0)
    janta_qua = models.PositiveIntegerField('Jantar/Quarta', null=False, default=0)
    janta_qui = models.PositiveIntegerField('Jantar/Quinta', null=False, default=0)
    janta_sex = models.PositiveIntegerField('Jantar/Sexta', null=False, default=0)
    atualizado_por = models.ForeignKeyPlus(
        'comum.Vinculo', null=True, verbose_name='Atualizado Por', related_name='ofertaalimentacao_atualizado_por', on_delete=models.CASCADE
    )
    atualizado_em = models.DateTimeFieldPlus('Atualizado em', null=True)
    situacao_ocasional = models.TextField('Situação ocasional', null=True, blank=True)
    arquivo_situacao_ocasional = models.PrivateFileField(
        verbose_name='Situação ocasional (evidências)', max_length=255, upload_to='ae/inscricao/documentos', null=True, blank=True
    )

    class Meta:
        verbose_name = 'Oferta de Refeições'
        verbose_name_plural = 'Ofertas de Refeições'
        permissions = (
            ('pode_gerenciar_ofertaalimentacao_todos', 'Pode gerenciar Oferta de Alimentação para todos os campi'),
            ('pode_gerenciar_ofertaalimentacao_do_campus', 'Pode gerenciar Oferta de Alimentação do próprio campus'),
            ('pode_ver_relatorio_diario_refeicao', 'Pode ver relatório diário de refeição'),
        )

    def __str__(self):
        return str(self.campus)

    def estah_configurada(self):
        """
        TODO:
            Seguir o algoritimo para condições negativas:
                - Verificar se existe algum atributo None
                - Verificar se todos os atributos são zero
        """
        return all(
            [
                self.cafe_seg is not None,
                self.cafe_ter is not None,
                self.cafe_qua is not None,
                self.cafe_qui is not None,
                self.cafe_sex is not None,
                self.almoco_seg is not None,
                self.almoco_ter is not None,
                self.almoco_qua is not None,
                self.almoco_qui is not None,
                self.almoco_sex is not None,
                self.janta_seg is not None,
                self.janta_ter is not None,
                self.janta_ter is not None,
                self.janta_qui is not None,
                self.janta_sex is not None,
            ]
        )


class OfertaValorRefeicao(models.ModelPlus):
    campus = models.ForeignKeyPlus(UnidadeOrganizacional, verbose_name='Campus', on_delete=models.CASCADE)
    valor = models.DecimalFieldPlus('Valor Unitário (R$)', default=Decimal())
    data_inicio = models.DateField('Data de Início')
    data_termino = models.DateField('Data de Saída')
    atualizado_por = models.ForeignKeyPlus(
        'comum.Vinculo', null=True, verbose_name='Atualizado Por', related_name='ofertavalorrefeicao_atualizado_por', on_delete=models.CASCADE
    )
    atualizado_em = models.DateTimeFieldPlus('Atualizado em', null=True)

    class Meta:
        verbose_name = 'Valor da Refeição'
        verbose_name_plural = 'Valores da Refeições'

    def __str__(self):
        return f'Refeição de R$ {format_(self.valor)} entre {format_(self.data_inicio)} e {format_(self.data_termino)}'


class ValorTotalAuxilios(models.ModelPlus):
    campus = models.ForeignKeyPlus(UnidadeOrganizacional, verbose_name='Campus', on_delete=models.CASCADE)
    tipoatendimentosetor = models.ForeignKeyPlus(TipoAtendimentoSetor, verbose_name='Tipo de Auxílio', on_delete=models.CASCADE)
    valor = models.DecimalFieldPlus('Recurso Planejado (R$)', default=Decimal())
    data_inicio = models.DateField('Data Inicial')
    data_termino = models.DateField('Data Final')

    class Meta:
        verbose_name = 'Recurso Planejado: Auxílios'
        verbose_name_plural = 'Recursos Planejados: Auxílios'
        permissions = (
            ('pode_ver_relatorio_financeiro', 'Pode ver Relatórios Financeiros'),
            ('pode_ver_relatorio_financeiro_todos', 'Pode ver Relatórios Financeiro de todos os campi'),
        )

    def __str__(self):
        return f'Valor de R$ {format_(self.valor)} entre {format_(self.data_inicio)} e {format_(self.data_termino)}'


class ValorTotalBolsas(models.ModelPlus):
    campus = models.ForeignKeyPlus(UnidadeOrganizacional, verbose_name='Campus', on_delete=models.CASCADE)
    categoriabolsa = models.ForeignKeyPlus(CategoriaBolsa, verbose_name='Categoria de Bolsa', on_delete=models.CASCADE)
    valor = models.DecimalFieldPlus('Recurso Planejado (R$)', default=Decimal())
    data_inicio = models.DateField('Data Inicial')
    data_termino = models.DateField('Data Final')

    class Meta:
        verbose_name = 'Recurso Planejado: Bolsas'
        verbose_name_plural = 'Recursos Planejados: Bolsas'
        permissions = (('pode_ver_relatorio_financeiro', 'Pode ver Relatório Financeiro'),)

    def __str__(self):
        return f'Valor de R$ {format_(self.valor)} entre {format_(self.data_inicio)} e {format_(self.data_termino)}'


class OfertaTurma(models.ModelPlus):
    SEMESTRE_PRIMEIRO = 1
    SEMESTRE_SEGUNDO = 2

    SEMESTRE_CHOICES = ((SEMESTRE_PRIMEIRO, SEMESTRE_PRIMEIRO), (SEMESTRE_SEGUNDO, SEMESTRE_SEGUNDO))

    campus = models.ForeignKeyPlus(UnidadeOrganizacional, verbose_name='Campus', on_delete=models.CASCADE)
    turma = models.CharField('Turma', max_length=50, help_text='Ex: 03')
    idioma = models.ForeignKeyPlus('ae.Idioma', verbose_name='Idioma', on_delete=models.CASCADE)
    ano = models.PositiveIntegerField('Ano')
    semestre = models.PositiveIntegerField('Semestre', choices=SEMESTRE_CHOICES)
    dia1 = models.PositiveIntegerField('1º Dia', choices=DiaSemanaChoices.DIAS_RESUMIDO_CHOICES)
    dia2 = models.PositiveIntegerField(
        '2º Dia',
        choices=DiaSemanaChoices.DIAS_RESUMIDO_CHOICES,
        help_text='Selecione o mesmo dia informado acima caso as aulas aconteçam em um único dia',
    )
    horario1 = models.CharField('Horário de Início', max_length=50, help_text='Ex: 07:00')
    horario2 = models.CharField('Horário de Término', max_length=50, help_text='Ex: 09:30')
    professor = models.CharField('Professor(a)', max_length=100)
    ativa = models.BooleanField('Ativa', default=True)
    numero_vagas = models.PositiveIntegerField('Número de Vagas', help_text='Número de vagas informadas pela FUNCERN')
    atualizado_por = models.ForeignKeyPlus(
        'comum.Vinculo', null=True, verbose_name='Atualizado Por', related_name='ofertaturma_atualizado_por', on_delete=models.CASCADE
    )
    atualizado_em = models.DateTimeFieldPlus('Atualizado em', null=True)

    class Meta:
        verbose_name = 'Oferta de Turmas de Idioma'
        verbose_name_plural = 'Ofertas de Turmas de Idioma'

    def __str__(self):
        if self.dia1 == self.dia2:
            return (
                f'Turma {self.turma} | {self.idioma} | {self.get_dia1_display()} das {self.horario1} às {self.horario2} | Prof(a).: {self.professor}'
            )
        else:
            return f'Turma {self.turma} | {self.idioma} | {self.get_dia1_display()}-{self.get_dia2_display()} das {self.horario1} às {self.horario2} | Prof(a).: {self.professor}'


class OfertaBolsa(models.ModelPlus):
    SEARCH_FIELDS = ['descricao_funcao', 'setor__sigla', 'setor__codigo', 'campus__sigla', 'turno']

    campus = models.ForeignKeyPlus(UnidadeOrganizacional, verbose_name='Campus', null=True, on_delete=models.CASCADE)
    setor = models.ForeignKeyPlus(Setor, verbose_name='Setor', on_delete=models.CASCADE)
    turno = models.CharFieldPlus(choices=TurnoChoices.TURNO_CHOICES)
    descricao_funcao = models.CharField('Descrição da Função', max_length=500)
    disponivel = models.BooleanField('Disponível', default=True)
    ativa = models.BooleanField('Ativa', default=True)
    atualizado_por = models.ForeignKeyPlus(
        'comum.Vinculo', null=True, verbose_name='Atualizado Por', related_name='ofertabolsa_atualizado_por', on_delete=models.CASCADE
    )
    atualizado_em = models.DateTimeFieldPlus('Atualizado em', null=True)

    class Meta:
        verbose_name = 'Oferta de Bolsa de Inic. Profissional'
        verbose_name_plural = 'Ofertas de Bolsa de Inic. Profissional'

    def __str__(self):
        if len(self.descricao_funcao) > 20:
            return f'{self.setor} ({self.get_turno_display()}) - {self.descricao_funcao[:20]}...'
        else:
            return f'{self.setor} ({self.get_turno_display()}) - {self.descricao_funcao[:20]}'

    def get_descricao(self):
        return f'{self.setor} ({self.get_turno_display()}) - {self.descricao_funcao}'


class OfertaValorBolsa(models.ModelPlus):
    campus = models.ForeignKeyPlus(UnidadeOrganizacional, verbose_name='Campus', on_delete=models.CASCADE)
    valor = models.DecimalFieldPlus('Valor Mensal da Bolsa (R$)', default=Decimal())
    data_inicio = models.DateField('Data Inicial')
    data_termino = models.DateField('Data Final')
    atualizado_por = models.ForeignKeyPlus(
        'comum.Vinculo', null=True, verbose_name='Atualizado Por', related_name='ofertavalorbolsa_atualizado_por', on_delete=models.CASCADE
    )
    atualizado_em = models.DateTimeFieldPlus('Atualizado em', null=True)

    class Meta:
        verbose_name = 'Valor da Bolsa'
        verbose_name_plural = 'Valores da Bolsa'

    def __str__(self):
        return f'Oferta de R$ {self.valor} entre {self.data_inicio} e {self.data_termino}'


class OfertaPasse(models.ModelPlus):
    campus = models.ForeignKeyPlus(UnidadeOrganizacional, verbose_name='Campus', on_delete=models.CASCADE)
    valor_passe = models.DecimalFieldPlus('Recurso Planejado (R$)', default=Decimal())
    data_inicio = models.DateField('Data Inicial')
    data_termino = models.DateField('Data Final')
    atualizado_por = models.ForeignKeyPlus(
        'comum.Vinculo', null=True, verbose_name='Atualizado Por', related_name='ofertapasse_atualizado_por', on_delete=models.CASCADE
    )
    atualizado_em = models.DateTimeFieldPlus('Atualizado em', null=True)

    class Meta:
        verbose_name = 'Recurso Planejado: Auxílio-Transporte'
        verbose_name_plural = 'Recursos Planejados: Auxílio-Transporte'

    def __str__(self):
        return f'Valor Planejado R$ {self.valor_passe} entre {self.data_inicio} e {self.data_termino}'

    def estah_configurada(self):
        return all([self.valor_passe is not None, self.valor_passe > 0])


class SolicitacaoAlimentacao(models.ModelPlus):
    seg = models.BooleanField(null=False, verbose_name='Segunda', default=False)
    ter = models.BooleanField(null=False, verbose_name='Terça', default=False)
    qua = models.BooleanField(null=False, verbose_name='Quarta', default=False)
    qui = models.BooleanField(null=False, verbose_name='Quinta', default=False)
    sex = models.BooleanField(null=False, verbose_name='Sexta', default=False)
    sab = models.BooleanField(null=False, verbose_name='Sábado', default=False)
    dom = models.BooleanField(null=False, verbose_name='Domingo', default=False)

    class Meta:
        verbose_name = 'Solicitação Alimentação'
        verbose_name_plural = 'Solicitações Alimentação'

    def get_itens_escolhidos(self):
        itens = []
        if self.seg:
            itens.append(str(DiaSemanaChoices.SEGUNDA))
        if self.ter:
            itens.append(str(DiaSemanaChoices.TERCA))
        if self.qua:
            itens.append(str(DiaSemanaChoices.QUARTA))
        if self.qui:
            itens.append(str(DiaSemanaChoices.QUINTA))
        if self.sex:
            itens.append(str(DiaSemanaChoices.SEXTA))
        if self.sab:
            itens.append(str(DiaSemanaChoices.SABADO))
        if self.dom:
            itens.append(str(DiaSemanaChoices.DOMINGO))
        return itens

    def get_choice_list(self):
        """
        Retorna uma lista no estilo:
        [u'Seg', u'Qua']
        Com as escolhas da solicitação
        """
        result_list = []
        if self.seg:
            result_list.append('Seg')
        if self.ter:
            result_list.append('Ter')
        if self.qua:
            result_list.append('Qua')
        if self.qui:
            result_list.append('Qui')
        if self.sex:
            result_list.append('Sex')
        return result_list

    def __str__(self):
        s = ''

        if self.seg:
            s += 'Segunda '

        if self.ter:
            s += 'Terça '

        if self.qua:
            s += 'Quarta '

        if self.qui:
            s += 'Quinta '

        if self.sex:
            s += 'Sexta '

        if self.sab:
            s += 'Sábado '

        if self.dom:
            s += 'Domingo '

        if not s:
            return '-'
        else:
            return s

    def valida(self):
        return self.seg or self.ter or self.qua or self.qui or self.sex or self.sab or self.dom


# -----------------------------------------------------------------------------
# Caracterização --------------------------------------------------------------
# -----------------------------------------------------------------------------
class NecessidadeEspecial(models.ModelPlus):
    descricao = models.CharField('Descrição', max_length=50)

    class Meta:
        verbose_name = 'Necessidade Especial'
        verbose_name_plural = 'Necessidades Especiais'

    def __str__(self):
        return self.descricao


class Idioma(models.ModelPlus):
    descricao = models.CharField('Idioma', max_length=50)
    uso_caracterizacao = models.BooleanField('Usar na caracterização', default=True)

    class Meta:
        ordering = ['descricao']
        verbose_name = 'Idioma'
        verbose_name_plural = 'Idiomas'

    def __str__(self):
        return f'{self.descricao}'


class SituacaoTrabalho(models.ModelPlus):
    descricao = models.CharField(max_length=50, verbose_name='Descrição', help_text='')

    class Meta:
        verbose_name = 'Situação de Trabalho'
        verbose_name_plural = 'Situações de Trabalho'

    def __str__(self):
        return self.descricao


class MeioTransporte(models.ModelPlus):
    descricao = models.CharField(max_length=50, verbose_name='Meio de Transporte', help_text='')

    class Meta:
        verbose_name = 'Meio de Transporte'
        verbose_name_plural = 'Meios de Transporte'

    def __str__(self):
        return self.descricao


class ContribuinteRendaFamiliar(models.ModelPlus):
    descricao = models.CharField(max_length=50, verbose_name='Descrição', help_text='')

    class Meta:
        verbose_name = 'Contribuinte de Renda Familiar'
        verbose_name_plural = 'Contribuintes de Renda Familiar'

    def __str__(self):
        return self.descricao


class CompanhiaDomiciliar(models.ModelPlus):
    descricao = models.CharField(max_length=50, verbose_name='Descrição', help_text='')

    class Meta:
        verbose_name = 'Companhia Domiciliar'
        verbose_name_plural = 'Companhias Domiciliares'

    def __str__(self):
        return self.descricao


class TipoImovelResidencial(models.ModelPlus):
    descricao = models.CharField(max_length=50, verbose_name='Descrição', help_text='')
    ativo = models.BooleanField('Ativo', default=True)

    class Meta:
        verbose_name = 'Tipo de Imóvel Residencial'
        verbose_name_plural = 'Tipos de Imóveis Residenciais'

    def __str__(self):
        return self.descricao


class TipoEscola(models.ModelPlus):
    descricao = models.CharFieldPlus('Descrição')

    def __str__(self):
        return self.descricao


class TipoAreaResidencial(models.ModelPlus):
    descricao = models.CharField(max_length=50, verbose_name='Descrição', help_text='')

    class Meta:
        verbose_name = 'Tipo de Área Residencial'
        verbose_name_plural = 'Tipos de Áreas Residenciais'

    def __str__(self):
        return self.descricao


class TipoServicoSaude(models.ModelPlus):
    descricao = models.CharField('Descrição', max_length=50)

    def __str__(self):
        return self.descricao


class BeneficioGovernoFederal(models.ModelPlus):
    descricao = models.CharField(max_length=100, verbose_name='Descrição', help_text='')
    ativo = models.BooleanField('Ativo', default=True)

    class Meta:
        verbose_name = 'Benefício do Governo Federal'
        verbose_name_plural = 'Benefícios de Governo Federal'

    def __str__(self):
        return self.descricao


class TipoEmprego(models.ModelPlus):
    descricao = models.CharField(max_length=50, verbose_name='Descrição', help_text='')

    class Meta:
        verbose_name = 'Tipo de Emprego'
        verbose_name_plural = 'Tipos de Emprego'

    def __str__(self):
        return self.descricao


class TipoAcessoInternet(models.ModelPlus):
    descricao = models.CharFieldPlus('Descrição')

    def __str__(self):
        return self.descricao


class RazaoAfastamentoEducacional(models.ModelPlus):
    descricao = models.CharFieldPlus(verbose_name='Descrição', help_text='')

    class Meta:
        verbose_name = 'Razão de Afastamento Educacional'
        verbose_name_plural = 'Razões de Afastamentos Educacionais'

    def __str__(self):
        return self.descricao


class EstadoCivil(models.ModelPlus):
    descricao = models.CharFieldPlus(verbose_name='Descrição', help_text='')

    class Meta:
        verbose_name = 'Estado Civil'
        verbose_name_plural = 'Estados Civis'

    def __str__(self):
        return self.descricao


class NivelEscolaridade(models.ModelPlus):
    descricao = models.CharFieldPlus(verbose_name='Descrição', help_text='')

    class Meta:
        verbose_name = 'Nível de Escolaridade'
        verbose_name_plural = 'Níveis de Escolaridade'

    def __str__(self):
        return self.descricao


class HistoricoCaracterizacao(models.ModelPlus):
    """
    Sempre que a caracterização é editada o histórico
    é atualizado.
    """

    raca = models.CharFieldPlus('Etnia/Raça/Cor', blank=True)
    possui_necessidade_especial = models.CharFieldPlus('Possui alguma deficiência/necessidade educacional especial?', blank=True)
    necessidade_especial = models.CharFieldPlus('Deficiências/necessidades educacionais especiais', blank=True)
    estado_civil = models.CharFieldPlus('Estado Civil', blank=True)
    qtd_filhos = models.CharFieldPlus('Quantidade de filhos', blank=True)
    # =====================DADOS EDUCACIONAIS=====================
    aluno_exclusivo_rede_publica = models.CharFieldPlus('Aluno da Rede Pública', blank=True)
    ensino_fundamental_conclusao = models.CharFieldPlus('Ano de Conclusão do Ensino Fundamental', blank=True)
    ensino_medio_conclusao = models.CharFieldPlus('Ano de Conclusão do Ensino Médio', blank=True)
    ficou_tempo_sem_estudar = models.CharFieldPlus('Ausência Escolar', blank=True)
    tempo_sem_estudar = models.CharFieldPlus('Período de Ausência', blank=True)
    razao_ausencia_educacional = models.CharFieldPlus('Motivo da Ausência Escolar', blank=True)
    possui_conhecimento_idiomas = models.CharFieldPlus('Conhecimento em Idiomas', blank=True)
    idiomas_conhecidos = models.CharFieldPlus('Idiomas', blank=True)
    possui_conhecimento_informatica = models.CharFieldPlus('Conhecimento em Informática', blank=True)
    # =============SITUAÇÃO FAMILIAR E SOCIO-ECONÔMICA=============
    trabalho_situacao = models.CharFieldPlus('Situacao de Trabalho', blank=True)
    meio_transporte_utilizado = models.CharFieldPlus('Meio de Transporte', blank=True)
    contribuintes_renda_familiar = models.CharFieldPlus('Contribuintes da Renda Familiar', blank=True)
    responsavel_financeiro = models.CharFieldPlus('Principal responsável pela renda familiar', blank=True)
    responsavel_financeir_trabalho_situacao = models.CharFieldPlus('Situação de Trabalho do Principal Responsável Financeiro', blank=True)
    responsavel_financeiro_nivel_escolaridade = models.CharFieldPlus('Nível de Escolaridade do Principal Responsável Financeiro', blank=True)
    pai_nivel_escolaridade = models.CharFieldPlus('Nível de Escolaridade do Pai', blank=True)
    mae_nivel_escolaridade = models.CharFieldPlus('Nível de Escolaridade da Mãe', blank=True)
    renda_bruta_familiar = models.CharFieldPlus('Renda Bruta Familiar R$', blank=True)
    companhia_domiciliar = models.CharFieldPlus('Com quem mora?', blank=True)
    qtd_pessoas_domicilio = models.CharFieldPlus('Número de pessoas no domicílio', blank=True)
    tipo_imovel_residencial = models.CharFieldPlus('Tipo de Imóvel', blank=True)
    tipo_area_residencial = models.CharFieldPlus('Tipo de Área Residencial', blank=True)
    beneficiario_programa_social = models.CharFieldPlus('Programas Social do Governo Federal', blank=True)
    tipo_servico_saude = models.CharFieldPlus('Serviço de Saúde que você mais utiliza', blank=True)
    escola_ensino_fundamental = models.CharFieldPlus('Escola do Ensino Fundamental', blank=True)
    nome_escola_ensino_fundamental = models.CharFieldPlus('Nome da Escola que fez o Ensino Fundamental', blank=True)
    escola_ensino_medio = models.CharFieldPlus('Escola do Ensino Médio', blank=True)
    nome_escola_ensino_medio = models.CharFieldPlus('Nome da escola que fez o Ensino Médio', blank=True)
    # ===================ACESSO TEC. INFORMAÇÃO===================
    frequencia_acesso_internet = models.CharFieldPlus(blank=True)
    local_acesso_internet = models.CharFieldPlus('Local de Acesso à Internet', blank=True)
    quantidade_computadores = models.CharFieldPlus('Quantidade de Computadores Desktop que possui', blank=True)
    quantidade_notebooks = models.CharFieldPlus('Quantidade de Notebooks que possui', blank=True)
    quantidade_netbooks = models.CharFieldPlus('Quantidade de Netbooks que possui', blank=True)
    quantidade_smartphones = models.CharFieldPlus('Quantidade de Smartphones que possui', blank=True)
    caracterizacao_relacionada = models.ForeignKeyPlus('ae.Caracterizacao', verbose_name='Caracterização', null=True)
    data_cadastro = models.DateTimeFieldPlus('Data de Cadastro', null=True)
    cadastrado_por = models.ForeignKeyPlus(Vinculo, verbose_name='Cadastrado Por', null=True)

    def get_data_cadastro_display(self):
        return self.data_cadastro and '{} '.format(self.data_cadastro.strftime('%d/%m/%Y %H:%M')) or '-'

    def get_cadastrado_por_display(self):
        if self.cadastrado_por:
            return f'{self.cadastrado_por} '
        return '-'


class Caracterizacao(models.ModelPlus):
    """
    Dados Socioeconômicos
    É a caracterização feita pelo aluno, mas o setor AE pode mudar algumas
    informações.
    """

    aluno = models.OneToOneField('edu.Aluno', verbose_name='Aluno', on_delete=models.CASCADE)
    raca = models.ForeignKeyPlus(
        'comum.Raca', verbose_name='Etnia/Raça/Cor', help_text='Como você se considera quanto a sua questão racial?', on_delete=models.CASCADE
    )
    possui_necessidade_especial = models.BooleanField(
        verbose_name='Você é uma pessoa com deficiência/necessidade educacional especial?', default=False
    )
    necessidade_especial = models.ManyToManyField(
        'ae.NecessidadeEspecial',
        verbose_name='Especifique as deficiências/necessidades educacionais especiais',
        help_text='Informe as deficiências/necessidades educacionais especiais caso tenha marcado a opção anterior.',
    )
    estado_civil = models.ForeignKeyPlus('ae.EstadoCivil', related_name='alunos', verbose_name='Estado Civil', help_text='', on_delete=models.CASCADE)
    qtd_filhos = models.PositiveIntegerField(null=True, default=0, verbose_name='Quantidade de Filhos')

    # Dados educacionais
    aluno_exclusivo_rede_publica = models.BooleanField(
        verbose_name='Aluno da Rede Pública',
        help_text='Marque caso possua histórico escolar integral a partir do 6° ano do Ensino Fundamental até o 3° ano do Ensino Médio exclusivamente em escola da rede pública do país.',
        default=False,
    )
    ensino_fundamental_conclusao = models.PositiveIntegerField(
        verbose_name='Ano de conclusão do Ensino Fundamental', help_text='Ano em que terminou o Ensino Fundamental.'
    )
    ensino_medio_conclusao = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name='Ano de conclusão do Ensino Médio',
        help_text='Ano em que terminou o Ensino Médio, caso já o tenha terminado.',
    )
    ficou_tempo_sem_estudar = models.BooleanField(
        verbose_name='Ausência Escolar', help_text='Marque caso tenha permanecido algum tempo sem estudar.', null=True, blank=True
    )
    tempo_sem_estudar = models.PositiveIntegerField(
        null=True, verbose_name='Período de Ausência', help_text='Informe quantos anos ficou sem estudar caso tenha marcado a opção anterior.'
    )
    razao_ausencia_educacional = models.ForeignKeyPlus(
        'ae.RazaoAfastamentoEducacional',
        null=True,
        verbose_name='Motivo da Ausência Escolar',
        help_text='Informe o motivo pelo qual você ficou sem estudar caso tenha marcado a opção anterior.',
        on_delete=models.CASCADE,
    )
    possui_conhecimento_idiomas = models.BooleanField(
        verbose_name='Conhecimento em Idiomas', help_text='Marque caso possua conhecimento em outros idiomas.', null=True, blank=True
    )
    idiomas_conhecidos = models.ManyToManyField(
        'ae.Idioma', verbose_name='Idiomas', help_text='Informe os idiomas sobre os quais você tem conhecimento caso tenha marcado a opção anterior.'
    )
    possui_conhecimento_informatica = models.BooleanField(
        verbose_name='Conhecimento em Informática', help_text='Marque caso possua conhecimento em informática.', null=True, blank=True
    )
    escola_ensino_fundamental = models.ForeignKeyPlus(
        'ae.TipoEscola', null=True, verbose_name='Tipo de escola que cursou o Ensino Fundamental', on_delete=models.CASCADE
    )
    nome_escola_ensino_fundamental = models.CharFieldPlus('Nome da escola que fez o Ensino Fundamental', null=True)
    escola_ensino_medio = models.ForeignKeyPlus(
        'ae.TipoEscola',
        null=True,
        verbose_name='Tipo de escola que cursou o Ensino Médio',
        related_name='escola_ensino_medio',
        on_delete=models.CASCADE,
    )
    nome_escola_ensino_medio = models.CharFieldPlus('Nome da escola que fez o Ensino Médio', null=True)

    # Situação familiar e socio-econômica
    trabalho_situacao = models.ForeignKeyPlus(
        'ae.SituacaoTrabalho',
        verbose_name='Situação de Trabalho',
        help_text='Situação em que você se encontra no mercado de trabalho.',
        null=True,
        on_delete=models.CASCADE,
    )
    meio_transporte_utilizado = models.ManyToManyField(
        'ae.MeioTransporte', verbose_name='Meio de Transporte', help_text='Meio de transporte que você utiliza/utilizará para se deslocar.'
    )
    contribuintes_renda_familiar = models.ManyToManyField(
        'ae.ContribuinteRendaFamiliar', verbose_name='Contribuintes da Renda Familiar', help_text='Pessoas que contribuem para rendar familiar.'
    )
    responsavel_financeiro = models.ForeignKeyPlus(
        'ae.ContribuinteRendaFamiliar',
        verbose_name='Principal responsável pela renda familiar',
        help_text='Pessoa responsável pela renda familiar',
        related_name='responsavel_financeiro',
        on_delete=models.CASCADE,
    )
    responsavel_financeir_trabalho_situacao = models.ForeignKeyPlus(
        'ae.SituacaoTrabalho',
        related_name='responsavel_financeiro',
        verbose_name='Situação de Trabalho do Principal Responsável Financeiro',
        help_text='Situação em que seu pai se encontra no mercado de trabalho.',
        on_delete=models.CASCADE,
    )
    responsavel_financeiro_nivel_escolaridade = models.ForeignKeyPlus(
        'ae.NivelEscolaridade',
        related_name='responsavel_financeiro',
        verbose_name='Nível de Escolaridade do Principal Responsável Financeiro',
        help_text='',
        on_delete=models.CASCADE,
    )
    pai_nivel_escolaridade = models.ForeignKeyPlus(
        'ae.NivelEscolaridade', related_name='pai', verbose_name='Nível de escolaridade do pai', help_text='', on_delete=models.CASCADE
    )
    mae_nivel_escolaridade = models.ForeignKeyPlus(
        'ae.NivelEscolaridade', related_name='mae', verbose_name='Nível de escolaridade da mãe', help_text='', on_delete=models.CASCADE
    )
    renda_bruta_familiar = models.DecimalFieldPlus(
        verbose_name='Renda Bruta Familiar R$', help_text='Considerar a soma de todos os rendimentos mensais da família sem os descontos.'
    )
    companhia_domiciliar = models.ForeignKeyPlus(
        'ae.CompanhiaDomiciliar', verbose_name='Com quem mora?', help_text='Com que você mora?', on_delete=models.CASCADE
    )
    qtd_pessoas_domicilio = models.PositiveIntegerField(
        verbose_name='Número de pessoas no domicílio', help_text='Número de pessoas que moram na sua residência (incluindo você).'
    )
    tipo_imovel_residencial = models.ForeignKeyPlus(
        'ae.TipoImovelResidencial', verbose_name='Tipo de Imóvel', help_text='Tipo do imóvel no qual você reside.', on_delete=models.CASCADE
    )
    tipo_area_residencial = models.ForeignKeyPlus(
        'ae.TipoAreaResidencial',
        verbose_name='Tipo de Área Residencial',
        help_text='Tipo da área residencial em que o imóvel que você reside se localiza.',
        on_delete=models.CASCADE,
    )
    beneficiario_programa_social = models.ManyToManyField(
        'ae.BeneficioGovernoFederal',
        verbose_name='Programas Social do Governo Federal',
        help_text='Informe os programas do governo federal dos quais você ou algum membro de sua família seja beneficiário.',
    )
    tipo_servico_saude = models.ForeignKeyPlus(
        'ae.TipoServicoSaude', null=True, verbose_name='Serviço de Saúde que você mais utiliza', on_delete=models.CASCADE
    )

    # Acesso às tecnologias da informação
    frequencia_acesso_internet = models.ForeignKeyPlus(
        'ae.TipoAcessoInternet', null=True, verbose_name='Frequência de Acesso à Internet', on_delete=models.CASCADE
    )
    local_acesso_internet = models.CharFieldPlus('Local de Acesso à Internet', null=True)
    quantidade_computadores = models.PositiveIntegerField('Quantidade de Computadores Desktop que possui', null=True)
    quantidade_notebooks = models.PositiveIntegerField('Quantidade de Notebooks que possui', null=True)
    quantidade_netbooks = models.PositiveIntegerField('Quantidade de Netbooks que possui', null=True)
    quantidade_smartphones = models.PositiveIntegerField('Quantidade de Smartphones que possui', null=True)

    historico_caracterizacao = models.ForeignKeyPlus('ae.HistoricoCaracterizacao', null=True)
    renda_per_capita = models.DecimalFieldPlus('Renda per Capita', null=True, blank=True)
    data_cadastro = models.DateTimeField('Data de Cadastro', null=True)
    data_ultima_atualizacao = models.DateTimeField('Data da Última Atualização', null=True)

    class Meta:
        permissions = (
            ('pode_ver_relatorio_caracterizacao_todos', 'Pode ver Relatórios de Caraterização Socioeconômica de todos os campi'),
            ('pode_ver_relatorio_caracterizacao_do_campus', 'Pode ver Relatórios de Caraterização Socioeconômica do próprio campus'),
            ('pode_ver_relatorio_caracterizacao_consolidado', 'Pode ver Relatórios Consolidados de Caraterização Socioeconômica do próprio campus'),
            ('pode_importar_caracterizacao', 'Pode importar caracterização'),
            ('save_caracterizacao_todos', 'Ver relatório alunos sem caracterização todos'),
            ('save_caracterizacao_do_campus', 'Ver relatório alunos sem caracterização campus'),
        )

    def __str__(self):
        return f'Caracterização: {self.aluno}'

    def tem_historico(self):
        return HistoricoCaracterizacao.objects.filter(caracterizacao_relacionada=self).count()

    def get_campos_alterados(self):
        # os campos que existem para serem verificados no histórico
        CAMPOS_NORMAIS_CARACTERIZACAO = [
            'raca',
            'possui_necessidade_especial',
            'estado_civil',
            'qtd_filhos',
            'aluno_exclusivo_rede_publica',
            'ensino_fundamental_conclusao',
            'ensino_medio_conclusao',
            'ficou_tempo_sem_estudar',
            'tempo_sem_estudar',
            'razao_ausencia_educacional',
            'possui_conhecimento_idiomas',
            'possui_conhecimento_informatica',
            'trabalho_situacao',
            'responsavel_financeiro',
            'responsavel_financeir_trabalho_situacao',
            'responsavel_financeiro_nivel_escolaridade',
            'pai_nivel_escolaridade',
            'mae_nivel_escolaridade',
            'renda_bruta_familiar',
            'companhia_domiciliar',
            'qtd_pessoas_domicilio',
            'tipo_imovel_residencial',
            'tipo_area_residencial',
            'tipo_servico_saude',
            'escola_ensino_fundamental',
            'nome_escola_ensino_fundamental',
            'escola_ensino_medio',
            'nome_escola_ensino_medio',
            'frequencia_acesso_internet',
            'local_acesso_internet',
            'quantidade_computadores',
            'quantidade_notebooks',
            'quantidade_netbooks',
            'quantidade_smartphones',
        ]
        # o mesmo só que para campos que sejam many_to_many
        # CAMPOS_MANY_TO_MANY = ['necessidade_especial', 'idiomas_conhecidos', 'meio_transporte_utilizado', 'contribuintes_renda_familiar',
        #                         'beneficiario_programa_social']
        # campos que foram alterados
        CAMPOS_RETORNO = []  # campo, antigo_valor
        old_obj = Caracterizacao.objects.get(pk=self.pk)
        for campo in CAMPOS_NORMAIS_CARACTERIZACAO:
            old_campo = getattr(old_obj, campo, None)
            if getattr(self, campo, None) != old_campo:
                CAMPOS_RETORNO.append([campo, old_campo])
        return CAMPOS_RETORNO

    def save(self, *args, **kwargs):
        self.data_ultima_atualizacao = datetime.datetime.now()
        if self.pk is not None:
            if self.historico_caracterizacao:
                h_c = HistoricoCaracterizacao.objects.filter(caracterizacao_relacionada=self)[0]
                h_c.id = None
            else:
                h_c = HistoricoCaracterizacao()
            h_c.data_cadastro = datetime.datetime.now()
            h_c.cadastrado_por = self.informado_por
            h_c.save()
            self.historico_caracterizacao = h_c
            _now = datetime.date.today()
            for c_a in self.get_campos_alterados():
                STRING_HISTORICO = '({} em {})'.format(c_a[1] if c_a[1] is not None else 'Opção vazia', _now.strftime('%d/%m/%Y'))
                setattr(self.historico_caracterizacao, c_a[0], str(STRING_HISTORICO))
            self.historico_caracterizacao.caracterizacao_relacionada = self
            self.historico_caracterizacao.save()
        if not self.historico_caracterizacao:
            self.data_cadastro = datetime.datetime.now()
        if self.qtd_pessoas_domicilio:
            valor_salario_minimo = Decimal(Configuracao.get_valor_por_chave('comum', 'salario_minimo'))

            numero_salarios = 0
            if Decimal(valor_salario_minimo) > 0 and Decimal(self.qtd_pessoas_domicilio) > 0:
                numero_salarios = (Decimal(self.renda_bruta_familiar) / Decimal(self.qtd_pessoas_domicilio)) / Decimal(valor_salario_minimo)

            historico_renda = HistoricoRendaFamiliar.objects.filter(aluno__id=self.aluno.pk).order_by('-data').order_by('-id')

            if not historico_renda or round(historico_renda[0].numero_salarios, 2) != round(numero_salarios, 2):
                historico = HistoricoRendaFamiliar()
                historico.numero_salarios = round(numero_salarios, 2)
                historico.aluno = self.aluno
                historico.data = datetime.datetime.today()
                historico.save()
                self.renda_per_capita = numero_salarios

        super().save(*args, **kwargs)

    def get_faixa_etaria(self):
        hoje = datetime.datetime.now()
        dt = self.aluno.pessoa_fisica.nascimento_data
        if dt:
            if dt >= (hoje - relativedelta(years=14)).date():
                return 'Até 14 anos'
            elif dt <= (hoje - relativedelta(years=15)).date() and dt >= (hoje - relativedelta(years=17)).date():
                return 'Entre 15 e 17 anos'
            elif dt <= (hoje - relativedelta(years=18)).date() and dt >= (hoje - relativedelta(years=29)).date():
                return 'Entre 18 e 29 anos'
            elif dt <= (hoje - relativedelta(years=30)).date() and dt >= (hoje - relativedelta(years=49)).date():
                return 'Entre 30 e 49 anos'
            elif dt <= (hoje - relativedelta(years=50)).date():
                return 'Acima de 50 anos'
        return 'Não informado'

    def get_faixa_renda_per_capita(self):
        if self.qtd_pessoas_domicilio > 0:
            sm = Decimal(Configuracao.get_valor_por_chave('comum', 'salario_minimo'))
            renda = self.renda_bruta_familiar / self.qtd_pessoas_domicilio
            if renda <= sm / 4:
                return '<= 0,25 Salário-Mínimo'
            elif renda <= sm / 2:
                return '> 0,25 e <= 0,5 Salário-Mínimo'
            elif renda <= sm:
                return '> 0,5 e <= 1 Salário-Mínimo'
            elif renda <= Decimal('1.5') * sm:
                return '> 1 e <= 1,5 Salário-Mínimo'
            else:
                return '> 1,5 Salário-Mínimo'
        return 'Não informado'

    @classmethod
    @transaction.atomic()
    def importar_caracterizacao(cls, dados_ws):
        class EntidadeId:
            def __init__(self, model_cls, valor_default=None):
                values = list(model_cls.objects.values_list('id', 'descricao'))
                self.mapa_por_id = dict(values)  # id: descricao
                self.mapa_por_descricao = dict(zip(self.mapa_por_id.values(), self.mapa_por_id.keys(), strict=False))  # descricao: id
                self.valor_default = valor_default

            def get_id(self, id_ou_descricao):
                if id_ou_descricao and id_ou_descricao.isdigit() and id_ou_descricao in self.mapa_por_id:
                    return id_ou_descricao
                return self.mapa_por_descricao.get(id_ou_descricao, self.valor_default)

        def _filter(model_cls, id_ou_descricao):
            if id_ou_descricao.isdigit():
                filter_kw = {'id': id_ou_descricao}
            else:
                filter_kw = {'descricao': id_ou_descricao}
            return model_cls.objects.filter(**filter_kw).first()

        _raca = EntidadeId(Raca, Raca.objects.get(descricao='Não declarado').id)
        _estadocivil = EntidadeId(EstadoCivil, EstadoCivil.objects.get(descricao='Não declarado').id)
        _situacaotrabalho = EntidadeId(SituacaoTrabalho, SituacaoTrabalho.objects.get(descricao='N\xe3o informado').id)
        _contribuinterendafamiliar = EntidadeId(ContribuinteRendaFamiliar, ContribuinteRendaFamiliar.objects.get(descricao='Não informado').id)
        _nivelescolaridade = EntidadeId(NivelEscolaridade, NivelEscolaridade.objects.get(descricao='Não conhece').id)
        _companhiadomiciliar = EntidadeId(CompanhiaDomiciliar, CompanhiaDomiciliar.objects.get(descricao='Não informado').id)
        _tipoimovelresidencial = EntidadeId(TipoImovelResidencial, TipoImovelResidencial.objects.get(descricao='Não informado').id)
        _tipoarearesidencial = EntidadeId(TipoAreaResidencial, TipoAreaResidencial.objects.get(descricao='Não informado').id)
        _tipoescola = EntidadeId(TipoEscola)

        numero_importado = 0
        numero_recebido = len(dados_ws['edital']['caracterizacoes']['caracterizacao'])
        todos_alunos = Aluno.objects.filter(caracterizacao__isnull=True, situacao__ativo=True)

        for dados in dados_ws['edital']['caracterizacoes']['caracterizacao']:
            alunos = todos_alunos.filter(pessoa_fisica__cpf=mask_cpf(dados['cpf']))
            if not alunos.exists():
                continue
            dict_aluno = {
                'mae_nivel_escolaridade_id': _nivelescolaridade.valor_default,
                'pai_nivel_escolaridade_id': _nivelescolaridade.valor_default,
                'tipo_imovel_residencial_id': _tipoimovelresidencial.valor_default,
                'tipo_area_residencial_id': _tipoarearesidencial.valor_default,
            }

            dict_aluno['raca_id'] = _raca.get_id(dados.get('etnia'))
            dict_aluno['estado_civil_id'] = _estadocivil.get_id(dados.get('estado_civil'))
            dict_aluno['qtd_filhos'] = dados.get('numero_filhos') or 0
            if dict_aluno['qtd_filhos'] == 'None':
                dict_aluno['qtd_filhos'] = 0
            if dados['socio_economica']['escolaridade']:
                dict_aluno['mae_nivel_escolaridade_id'] = _nivelescolaridade.get_id(dados['socio_economica']['escolaridade'].get('mae'))
                dict_aluno['pai_nivel_escolaridade_id'] = _nivelescolaridade.get_id(dados['socio_economica']['escolaridade'].get('pai'))
            dict_aluno['trabalho_situacao_id'] = _situacaotrabalho.get_id(dados['socio_economica'].get('trabalho_situacao'))
            dict_aluno['companhia_domiciliar_id'] = _companhiadomiciliar.get_id(dados['socio_economica'].get('companhia_domiciliar'))
            dict_aluno['qtd_pessoas_domicilio'] = dados['socio_economica'].get('qtd_moradores_domicilio') or 0
            dict_aluno['responsavel_financeiro_id'] = _contribuinterendafamiliar.get_id(dados['socio_economica']['renda_familiar'].get('responsavel'))
            dict_aluno['responsavel_financeir_trabalho_situacao_id'] = _situacaotrabalho.get_id(
                dados['socio_economica']['renda_familiar'].get('trabalho_responsavel')
            )
            dict_aluno['responsavel_financeiro_nivel_escolaridade_id'] = _nivelescolaridade.get_id(
                dados['socio_economica']['renda_familiar'].get('escolaridade_responsavel')
            )
            dict_aluno['renda_bruta_familiar'] = dados['socio_economica']['renda_familiar'].get('renda_bruta') or 0
            if dados.get('ensino_fundamental'):
                dict_aluno['ensino_fundamental_conclusao'] = dados['ensino_fundamental'].get('ano_conclusao') or 0
                dict_aluno['nome_escola_ensino_fundamental'] = dados['ensino_fundamental'].get('nome_escola') or ''
                if dados['ensino_fundamental'].get('tipo_escola'):
                    dict_aluno['escola_ensino_fundamental_id'] = _tipoescola.get_id(dados['ensino_fundamental'].get('tipo_escola'))
                dict_aluno['aluno_exclusivo_rede_publica'] = False
                if 'ensino_fundamental' in dados and dados['ensino_fundamental'] == 'Sim':  # TODO: Isso faz sentido???
                    dict_aluno['aluno_exclusivo_rede_publica'] = True
            else:
                dict_aluno['ensino_fundamental_conclusao'] = 0
            if dados.get('ensino_medio'):
                dict_aluno['ensino_medio_conclusao'] = dados['ensino_medio'].get('ano_conclusao') or 0
                dict_aluno['nome_escola_ensino_medio'] = dados['ensino_medio'].get('nome_escola') or ''
                if dados['ensino_medio'].get('tipo_escola'):
                    dict_aluno['escola_ensino_medio_id'] = _tipoescola.get_id(dados['ensino_medio'].get('tipo_escola'))
            if dados.get('ausencia_escolar'):
                dict_aluno['ficou_tempo_sem_estudar'] = True
                dict_aluno['tempo_sem_estudar'] = dados['ausencia_escolar'].get('tempo_sem_estudar', '')
                if RazaoAfastamentoEducacional.objects.filter(id=dados['ausencia_escolar'].get('motivo')):
                    dict_aluno['razao_ausencia_educacional'] = RazaoAfastamentoEducacional.objects.get(id=dados['ausencia_escolar'].get('motivo'))
            else:
                dict_aluno['ficou_tempo_sem_estudar'] = False
            if dados['socio_economica']['imovel']:
                dict_aluno['tipo_imovel_residencial_id'] = _tipoimovelresidencial.get_id(dados['socio_economica']['imovel'].get('tipo'))
                dict_aluno['tipo_area_residencial_id'] = _tipoarearesidencial.get_id(dados['socio_economica']['imovel'].get('area_residencial'))

            if dados.get('conhecimento_idioma', False):
                dict_aluno['possui_conhecimento_idiomas'] = True
            else:
                dict_aluno['possui_conhecimento_idiomas'] = False
            dict_aluno['possui_conhecimento_informatica'] = None
            if 'conhecimento_informatica' in dados:
                dict_aluno['possui_conhecimento_informatica'] = dados['conhecimento_informatica'] == 'Sim'
            if dados.get('acesso_tecnologia', False):
                dict_aluno['local_acesso_internet'] = dados['acesso_tecnologia'].get('local_acesso_internet')
                dict_aluno['frequencia_acesso_internet'] = TipoAcessoInternet.objects.get(
                    descricao=dados['acesso_tecnologia'].get('frequencia_acesso_internet')
                )
                dict_aluno['quantidade_computadores'] = 0
                dict_aluno['quantidade_notebooks'] = 0
                dict_aluno['quantidade_netbooks'] = 0
                dict_aluno['quantidade_smartphones'] = 0
                if dados['acesso_tecnologia'].get('quantidade_computadores') and dados['acesso_tecnologia'].get('quantidade_computadores') != 'None':
                    dict_aluno['quantidade_computadores'] = dados['acesso_tecnologia'].get('quantidade_computadores')
                if dados['acesso_tecnologia'].get('quantidade_notebooks') and dados['acesso_tecnologia'].get('quantidade_notebooks') != 'None':
                    dict_aluno['quantidade_notebooks'] = dados['acesso_tecnologia'].get('quantidade_notebooks')
                if dados['acesso_tecnologia'].get('quantidade_netbooks') and dados['acesso_tecnologia'].get('quantidade_netbooks') != 'None':
                    dict_aluno['quantidade_netbooks'] = dados['acesso_tecnologia'].get('quantidade_netbooks')
                if dados['acesso_tecnologia'].get('quantidade_smartphones') and dados['acesso_tecnologia'].get('quantidade_smartphones') != 'None':
                    dict_aluno['quantidade_smartphones'] = dados['acesso_tecnologia'].get('quantidade_smartphones')
            dict_aluno['possui_necessidade_especial'] = False
            if 'necessidade_especial' in dados:
                dict_aluno['possui_necessidade_especial'] = True
            for aluno in alunos:
                caracterizacao = Caracterizacao.objects.create(aluno=aluno, data_cadastro=datetime.datetime.now(), **dict_aluno)
                if dados.get('conhecimento_idioma', False):
                    if isinstance(dados['conhecimento_idioma']['idioma'], list):
                        for idioma in dados['conhecimento_idioma']['idioma']:
                            if idioma is not None:
                                add_idioma = Idioma.objects.filter(id=idioma)
                                if add_idioma.exists():
                                    caracterizacao.idiomas_conhecidos.add(add_idioma[0])
                    else:
                        if dados['conhecimento_idioma']['idioma'] is not None:
                            add_idioma = Idioma.objects.filter(id=dados['conhecimento_idioma']['idioma'])
                            if add_idioma.exists():
                                caracterizacao.idiomas_conhecidos.add(add_idioma[0])
                if dados['socio_economica'].get('meio_transporte'):
                    if isinstance(dados['socio_economica']['meio_transporte']['nome'], list):
                        for transporte in dados['socio_economica']['meio_transporte']['nome']:
                            if transporte is not None:
                                add_transporte = MeioTransporte.objects.filter(id=transporte)
                                if add_transporte.exists():
                                    caracterizacao.meio_transporte_utilizado.add(add_transporte[0])
                    else:
                        if dados['socio_economica']['meio_transporte']['nome'] is not None:
                            val = dados['socio_economica']['meio_transporte']['nome']
                            meio_transporte = _filter(MeioTransporte, val)
                            if meio_transporte:
                                caracterizacao.meio_transporte_utilizado.add(meio_transporte)
                if dados['socio_economica'].get('programas_sociais', False):
                    if isinstance(dados['socio_economica']['programas_sociais']['programa'], list):
                        for programa in dados['socio_economica']['programas_sociais']['programa']:
                            if programa is not None:
                                beneficio = _filter(BeneficioGovernoFederal, programa)
                                if beneficio:
                                    caracterizacao.beneficiario_programa_social.add(beneficio)
                    else:
                        if dados['socio_economica']['programas_sociais']['programa'] is not None:
                            val = dados['socio_economica']['programas_sociais']['programa']
                            beneficio = _filter(BeneficioGovernoFederal, val)
                            if beneficio:
                                caracterizacao.beneficiario_programa_social.add(beneficio)
                if dados['socio_economica']['renda_familiar'].get('contribuintes', False):
                    if isinstance(dados['socio_economica']['renda_familiar']['contribuintes']['contribuinte'], list):
                        for contribuinte in dados['socio_economica']['renda_familiar']['contribuintes']['contribuinte']:
                            if contribuinte is not None:
                                add_contribuinte = ContribuinteRendaFamiliar.objects.filter(id=contribuinte)
                                if add_contribuinte.exists():
                                    caracterizacao.contribuintes_renda_familiar.add(add_contribuinte[0])
                    else:
                        if dados['socio_economica']['renda_familiar']['contribuintes']['contribuinte'] is not None:
                            val = dados['socio_economica']['renda_familiar']['contribuintes']['contribuinte']
                            contribuinte = _filter(ContribuinteRendaFamiliar, val)
                            if contribuinte:
                                caracterizacao.contribuintes_renda_familiar.add(contribuinte)
                if dados.get('necessidades_especiais', False) and dados.get('necessidades_especiais').get('necessidade_especial'):
                    necessidades = dados.get('necessidades_especiais').get('necessidade_especial')
                    if isinstance(necessidades, list):
                        for necessidade_dict in necessidades:
                            for necessidade, valor in list(necessidade_dict.items()):
                                if necessidade is not None and necessidade == 'codigo':
                                    add_necessidade = NecessidadeEspecial.objects.filter(id=valor).first()
                                    if add_necessidade:
                                        caracterizacao.necessidade_especial.add(add_necessidade)
                    elif isinstance(necessidades, dict):
                        for necessidade, valor in list(necessidades.items()):
                            if necessidade is not None and necessidade == 'codigo':
                                add_necessidade = NecessidadeEspecial.objects.filter(id=valor).first()
                                if add_necessidade:
                                    caracterizacao.necessidade_especial.add(add_necessidade)
            numero_importado += 1
        return numero_recebido, numero_importado


class IntegranteFamiliarCaracterizacao(models.ModelPlus):
    """
    Este modelo caracteriza os integrantes da família de um aluno com
    a caracterização de inscrição ('ae.models.InscricaoCaracterizacao').
    """

    inscricao_caracterizacao = models.ForeignKeyPlus(
        'ae.InscricaoCaracterizacao', verbose_name='Inscrição da Caracterização', on_delete=models.CASCADE, null=True
    )
    nome = models.CharFieldPlus('Nome')
    idade = models.IntegerField('Idade', null=True)
    parentesco = models.CharFieldPlus('Parentesco')
    estado_civil = models.ForeignKeyPlus('ae.EstadoCivil', verbose_name='Estado civil')
    situacao_trabalho = models.ForeignKeyPlus('ae.SituacaoTrabalho', verbose_name='Situação de trabalho')
    remuneracao = models.DecimalFieldPlus('Remuneração', null=True)
    ultima_remuneracao = models.DecimalFieldPlus('Última Remuneração', null=True)
    data = models.DateTimeField('Data', auto_now=True, null=True)
    data_nascimento = models.DateFieldPlus('Data de Nascimento', null=True)
    aluno = models.ForeignKeyPlus('edu.Aluno', verbose_name='Aluno', on_delete=models.CASCADE, null=True)
    id_inscricao = models.CharFieldPlus('Id da Inscrição', max_length=255, null=True, blank=True)
    possui_doenca_cronica = models.BooleanField('Possui doença(s) crônica(s)?', null=True)
    possui_deficiencia = models.BooleanField('Possui deficiência(s)?', null=True)
    possui_despesa_medicamento = models.BooleanField('Possui despesas contínuas com medicamentos e/ou tratamento de saúde?', null=True)

    def save(self, *args, **kargs):
        if self.inscricao_caracterizacao:
            self.aluno = self.inscricao_caracterizacao.aluno
            self.id_inscricao = self.inscricao_caracterizacao_id
        super().save(*args, **kargs)

    def __str__(self):
        return self.nome

    def get_idade(self):
        idade = ''
        if self.data_nascimento:
            idade = relativedelta(datetime.datetime.now().date(), self.data_nascimento)
            idade = idade.years
        return f'{idade} anos'

    def get_valor_remuneracao(self):
        if self.remuneracao:
            valor_remuneracao = self.remuneracao
        else:
            valor_remuneracao = self.ultima_remuneracao
        return f'R$ {valor_remuneracao}'


class InscricaoCaracterizacao(models.ModelPlus):
    NUNCA_MOREI = 'Não, nunca morei'
    MORO = 'Sim, moro atualmente'
    JA_MOREI_E_ADOTADO = 'Sim, já morei e FUI adotado antes de sair'
    JA_MOREI_NAO_ADOTADO = 'Sim, já morei e NÃO FUI adotado antes de sair'
    MOROU_ORFANATO_CHOICES = (
        (NUNCA_MOREI, NUNCA_MOREI),
        (MORO, MORO),
        (JA_MOREI_E_ADOTADO, JA_MOREI_E_ADOTADO),
        (JA_MOREI_NAO_ADOTADO, JA_MOREI_NAO_ADOTADO),
    )

    aluno = models.ForeignKeyPlus('edu.Aluno', verbose_name='Aluno', on_delete=models.CASCADE)
    moradia_responsavel_financeiro = models.ForeignKeyPlus(
        'ae.TipoImovelResidencial', verbose_name='Situação de moradia do principal responsável financeiro', on_delete=models.SET_NULL, null=True
    )
    moradia_especificacao = models.CharFieldPlus(
        'Situação de moradia', help_text='Somente preencha este campo caso, na opção anterior, tenha marcado "Outro".', null=True
    )
    familiar_doente_cronico = models.BooleanField(
        'Algum membro da sua família tem doença crônica e/ou faz uso contínuo de medicamentos?', default=False
    )
    familiar_doente_cronico_nome = models.CharFieldPlus(
        'Familiar(es) com doença(s) crônica(s)', help_text='Especifique o nome do(s) familiar(es) e respectiva(s) doença(s) crônica(s)', null=True
    )
    valor_transporte = models.DecimalFieldPlus(
        'Valor gasto com transporte',
        null=True,
        help_text='Se utiliza meio de transporte (ônibus, mototáxi, transporte locado), especifique o valor gasto.',
    )
    remuneracao_trabalho = models.DecimalFieldPlus('Remuneração de trabalho', help_text='Especifique o valor da sua remuneração de trabalho.')
    rendimento_mesada = models.DecimalFieldPlus('Redimento de Mesada', null=True, help_text='Especifique o valor que recebe de mesada.')
    rendimento_aux_parentes = models.DecimalFieldPlus(
        'Rendimento de auxílio de parentes', null=True, help_text='Especifique o valor que recebe de auxílio de parentes.'
    )
    rendimento_aluguel = models.DecimalFieldPlus(
        'Rendimento de aluguel(is)', null=True, help_text='Especifique o valor que recebe de rendimentos de aluguel(is).'
    )
    rendimento_outro = models.DecimalFieldPlus('Outros rendimentos', null=True, help_text='Caso tenha outro redimento, especifique-o.')
    informacoes_complementares = models.CharFieldPlus(
        'Informações complementares',
        help_text='Se achar necessário, relate alguma situação familiar especial, não contemplada no questionário, \
    a qual você julga importante para fundamentar a análise de sua situação econômica.',
        null=True,
    )
    data = models.DateTimeField('Data', auto_now=True)

    estudou_com_bolsa_integral = models.BooleanField(
        'Estudou em escola particular com bolsa de estudo integral',
        null=True,
    )
    comprovante_estudou_com_bolsa_integral = models.PrivateFileField(
        verbose_name='Comprovante bolsa integral', max_length=255, null=True, upload_to='ae/inscricao/documentos'
    )
    recebe_acompanhamento_napne = models.BooleanField(
        'Recebe acompanhamento pedagógico específico pelo NAPNE',
        null=True,
    )
    morou_em_orfanato = models.CharFieldPlus(
        'Você mora ou já morou em abrigo institucional (orfanato)?', null=True, max_length=50, choices=MOROU_ORFANATO_CHOICES
    )
    comprovante_orfanato = models.PrivateFileField(
        verbose_name='Documentação comprobatória conforme edital',
        blank=True,
        help_text='Anexar declaração da instituição.',
        max_length=255,
        null=True,
        upload_to='ae/inscricao/documentos',
    )

    eh_quilombola = models.BooleanField(
        'Você reside ou é oriundo de comunidades tradicionais, quilombola ou indígena?',
        null=True,
    )
    eh_refugiado = models.BooleanField(
        'Você veio para o país refugiado?',
        null=True,
    )
    comprovante_refugiado = models.PrivateFileField(
        verbose_name='Comprovante',
        help_text='Anexar declaração específica para esse caso constante nos anexos do edital.',
        max_length=255,
        null=True,
        blank=True,
        upload_to='ae/inscricao/documentos',
    )


class HistoricoRendaFamiliar(models.ModelPlus):
    aluno = models.ForeignKeyPlus('edu.Aluno', verbose_name='Aluno', on_delete=models.CASCADE)
    data = models.DateField(auto_now=True)
    numero_salarios = models.DecimalFieldPlus()


class ParticipacoesBolsasFuturasManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(data_inicio__gt=datetime.date.today())


class ParticipacoesBolsasAbertasManager(models.Manager):
    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .filter(Q(data_inicio__lte=datetime.date.today()) & (Q(data_termino__isnull=True) | Q(data_termino__gte=datetime.date.today())))
        )


class ParticipacoesBolsasFechadasManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(data_termino__lt=datetime.date.today())


class ParticipacaoBolsa(LogModel):
    aluno = models.ForeignKeyPlus('edu.Aluno', verbose_name='Aluno', on_delete=models.CASCADE)
    categoria = models.ForeignKeyPlus(CategoriaBolsa, verbose_name='Categoria da Bolsa', on_delete=models.CASCADE)
    setor = models.ForeignKeyPlus(Setor, verbose_name='Setor', null=True, on_delete=models.CASCADE)
    data_inicio = models.DateField('Data de Início')
    data_termino = models.DateField('Data de Saída', null=True)
    aluno_participante_projeto = models.ForeignKeyPlus(
        'projetos.Participacao', verbose_name='Aluno Participante do Projeto', null=True, on_delete=models.CASCADE
    )

    # Managers
    objects = models.Manager()
    futuras = ParticipacoesBolsasFuturasManager()
    abertas = ParticipacoesBolsasAbertasManager()
    fechadas = ParticipacoesBolsasFechadasManager()

    class Meta:
        verbose_name = 'Participação de Bolsa'
        verbose_name_plural = 'Participações de Bolsas'

        permissions = (('pode_ver_lista_bolsas_todos', 'Pode ver Relatórios de Participações em Bolsas'),)

    def eh_pesquisa(self):
        return self.bolsas.exists()

    def projeto_pesquisa(self):
        return self.bolsas.all()[0].projeto


class TipoRefeicao:
    TIPO_CAFE = '1'
    TIPO_ALMOCO = '2'
    TIPO_JANTAR = '3'

    TIPOS = ((TIPO_ALMOCO, 'Almoço'), (TIPO_JANTAR, 'Jantar'), (TIPO_CAFE, 'Café da manhã'))

    HOJE = '1'
    AMANHA = '2'

    DIAS = ((AMANHA, 'Amanhã'), (HOJE, 'Hoje'))


class SolicitacaoRefeicaoAluno(models.ModelPlus):
    aluno = models.ForeignKeyPlus('edu.Aluno', on_delete=models.CASCADE)
    data_solicitacao = models.DateTimeFieldPlus()
    data_auxilio = models.DateTimeFieldPlus()
    tipo_refeicao = models.CharField('Tipo de Refeição', max_length=1, choices=TipoRefeicao.TIPOS)
    motivo_solicitacao = models.CharFieldPlus('Motivo da Solicitação', max_length=500)
    programa = models.ForeignKeyPlus(Programa, on_delete=models.CASCADE)
    deferida = models.BooleanField(verbose_name='Deferida', null=True, blank=True)
    avaliador_vinculo = models.ForeignKeyPlus('comum.Vinculo', null=True, blank=True, verbose_name='Avaliador', on_delete=models.CASCADE)
    ativa = models.BooleanField('Ativa', default=True)
    agendamento = models.OneToOneField('ae.AgendamentoRefeicao', verbose_name='Agendamento', null=True, on_delete=models.SET_NULL)

    class Meta:
        verbose_name = 'Solicitação de Refeições'
        verbose_name_plural = 'Solicitações de Refeições'

    def pode_cancelar_solicitacao(self):
        horario_permitido = HorarioJustificativaFalta.objects.filter(uo=self.programa.instituicao, tipo_refeicao=self.tipo_refeicao)[0]
        # Se solicitação FOI AVALIADA e foi INDEFERIDA
        if self.deferida is False:
            return False
        if horario_permitido.dia_inicio == horario_permitido.dia_fim:
            if horario_permitido.dia_inicio == HorarioJustificativaFalta.MESMO_DIA:
                if self.data_auxilio.date() == date.today() and datetime.datetime.now().time() < horario_permitido.hora_fim:
                    return True
            else:
                if self.data_auxilio.date() > date.today() and datetime.datetime.now().time() < horario_permitido.hora_fim:
                    return True
        else:
            if (
                self.data_auxilio.date() > date.today()
                or self.data_auxilio.date() == date.today()
                and datetime.datetime.now().time() < horario_permitido.hora_fim
            ):
                return True
        return False

    def get_participacao_alimentacao(self):
        participacoes_alimentacao = Participacao.objects.filter(aluno=self.aluno, programa__tipo_programa__sigla=Programa.TIPO_ALIMENTACAO)
        if participacoes_alimentacao.exists():
            participacao_ativa = participacoes_alimentacao.filter(Q(data_termino__gte=date.today()) | Q(data_termino__isnull=True))
            if participacao_ativa.exists():
                return participacao_ativa[0]
        return False

    def get_renda(self):
        if (
            hasattr(self.aluno, 'caracterizacao')
            and self.aluno.caracterizacao.renda_bruta_familiar
            and self.aluno.caracterizacao.qtd_pessoas_domicilio
        ):
            return Decimal(self.aluno.caracterizacao.renda_bruta_familiar) / Decimal(self.aluno.caracterizacao.qtd_pessoas_domicilio)
        return Decimal(0)

    def get_renda_atualizada_em(self):
        if hasattr(self.aluno, 'caracterizacao') and self.aluno.caracterizacao.data_ultima_atualizacao:
            return self.aluno.caracterizacao.data_ultima_atualizacao.strftime('%d/%m/%Y')
        return None

    def get_solicitacoes_deferidas_esta_semana(self):
        hoje = date.today()
        inicio_semana = hoje - timedelta(hoje.weekday())
        fim_semana = inicio_semana + timedelta(4)
        return SolicitacaoRefeicaoAluno.objects.filter(
            aluno=self.aluno, deferida=True, data_solicitacao__lt=fim_semana, data_solicitacao__gt=inicio_semana
        ).count()

    def get_faltas_no_ultimo_mes(self):
        hoje = date.today()
        trinta_dias = hoje - timedelta(30)
        return HistoricoFaltasAlimentacao.objects.filter(aluno=self.aluno, justificativa__isnull=True, data__lt=hoje, data__gt=trinta_dias).count()

    @property
    def inscricao(self):
        inscricao = Inscricao.objects.filter(aluno=self.aluno, programa=self.programa).first()
        return inscricao


class HorarioSolicitacaoRefeicao(models.ModelPlus):
    DIA_ANTERIOR = '1'
    MESMO_DIA = '2'

    DIA_CHOICES = ((DIA_ANTERIOR, 'Dia anterior'), (MESMO_DIA, 'Mesmo dia'))

    uo = models.ForeignKeyPlus('rh.UnidadeOrganizacional', verbose_name='Campus', on_delete=models.CASCADE)
    tipo_refeicao = models.CharField('Tipo de Refeição', max_length=1, choices=TipoRefeicao.TIPOS)
    hora_inicio = models.TimeFieldPlus('Hora do Início')
    dia_inicio = models.CharField('Dia de Início', max_length=1, choices=DIA_CHOICES)
    hora_fim = models.TimeFieldPlus('Hora do Término')
    dia_fim = models.CharField('Dia de Término', max_length=1, choices=DIA_CHOICES)
    atualizado_por = models.ForeignKeyPlus(
        'comum.Vinculo', null=True, verbose_name='Atualizado Por', related_name='horariosolicitacaorefeicao_atualizado_por', on_delete=models.CASCADE
    )
    atualizado_em = models.DateTimeFieldPlus('Atualizado em', null=True)

    class Meta:
        ordering = ['tipo_refeicao']
        unique_together = ('uo', 'tipo_refeicao')
        verbose_name = 'Horário de Solicitações de Refeição'
        verbose_name_plural = 'Horários de Solicitações de Refeição'

    def __str__(self):
        return 'Horário de Solicitação de Refeição'


class HorarioJustificativaFalta(models.ModelPlus):
    DIA_ANTERIOR = '1'
    MESMO_DIA = '2'

    DIA_CHOICES = ((DIA_ANTERIOR, 'Dia anterior'), (MESMO_DIA, 'Mesmo dia'))

    uo = models.ForeignKeyPlus('rh.UnidadeOrganizacional', verbose_name='Campus', on_delete=models.CASCADE)
    tipo_refeicao = models.CharField('Tipo de Refeição', max_length=1, choices=TipoRefeicao.TIPOS)
    hora_inicio = models.TimeFieldPlus('Hora do Início')
    dia_inicio = models.CharField('Dia de Início', max_length=1, choices=DIA_CHOICES)
    hora_fim = models.TimeFieldPlus('Hora do Término')
    dia_fim = models.CharField('Dia de Término', max_length=1, choices=DIA_CHOICES)
    atualizado_por = models.ForeignKeyPlus(
        'comum.Vinculo', null=True, verbose_name='Atualizado Por', related_name='horariojustificativafalta_atualizado_por', on_delete=models.CASCADE
    )
    atualizado_em = models.DateTimeFieldPlus('Atualizado em', null=True)

    class Meta:
        ordering = ['tipo_refeicao']
        unique_together = ('uo', 'tipo_refeicao')
        verbose_name = 'Horário de Justificativas de Falta'
        verbose_name_plural = 'Horários de Justificativas de Falta'

    def __str__(self):
        return 'Horário de Justificativa de Falta'


class HistoricoFaltasAlimentacao(models.ModelPlus):
    aluno = models.ForeignKeyPlus('edu.Aluno', on_delete=models.CASCADE)
    participacao = models.ForeignKeyPlus('ae.Participacao', verbose_name='Participação', null=True, blank=True, on_delete=models.CASCADE)
    programa = models.ForeignKeyPlus('ae.Programa', verbose_name='Programa', null=True, blank=True, on_delete=models.CASCADE)
    tipo_refeicao = models.CharField('Tipo de Refeição', max_length=1, choices=TipoRefeicao.TIPOS)
    data = models.DateField('Data da Refeição')
    justificativa = models.CharField('Justificativa', max_length=500, null=True, blank=True)
    justificada_em = models.DateTimeField('Data da Justificativa', null=True, blank=True)
    justificada_por_vinculo = models.ForeignKeyPlus(
        'comum.Vinculo', verbose_name='Responsável pela Justificativa', null=True, blank=True, on_delete=models.CASCADE
    )
    cancelada = models.BooleanField('Cancelada', default=False)

    class Meta:
        verbose_name = 'Histórico de Faltas'
        verbose_name_plural = 'Históricos de Faltas'


models.signals.post_save.connect(atualizar_config_refeicao, sender=HistoricoFaltasAlimentacao)


class HistoricoSuspensoesAlimentacao(models.ModelPlus):
    participacao = models.ForeignKeyPlus('ae.Participacao', verbose_name='Participação', on_delete=models.CASCADE)
    data_inicio = models.DateTimeField('Data de Início da Suspensão')
    data_termino = models.DateTimeField('Data de Término da Suspensão')
    liberado_por_vinculo = models.ForeignKeyPlus('comum.Vinculo', verbose_name='Responsável pela Liberação', on_delete=models.CASCADE, null=True)

    class Meta:
        verbose_name = 'Histórico de Liberações de Suspensões'
        verbose_name_plural = 'Históricos de Liberações de Suspensões'


class DatasLiberadasFaltasAlimentacao(models.ModelPlus):
    data = models.DateField()
    recorrente = models.BooleanField(default=False, help_text='Selecione para as datas que serão abonadas todos os anos, como feriados nacionais.')
    campus = models.ForeignKeyPlus('rh.UnidadeOrganizacional', on_delete=models.CASCADE)
    cadastrado_por = models.CurrentUserField(verbose_name='Cadastrado Por', null=True, blank=True)
    cadastrado_em = models.DateTimeField('Data de Cadastro', auto_now_add=True, null=True, blank=True)
    atualizado_por_vinculo = models.ForeignKeyPlus(
        'comum.Vinculo', null=True, verbose_name='Atualizado Por', related_name='datasliberadas_atualizado_por', on_delete=models.CASCADE
    )
    atualizado_em = models.DateTimeField('Atualizado em', null=True, blank=True)

    class Meta:
        unique_together = ('data', 'campus')
        verbose_name = 'Liberação de Registros de Faltas'
        verbose_name_plural = 'Liberações de Registros de Faltas'


class TipoAtividadeDiversa(models.ModelPlus):
    nome = models.CharField(max_length=255, unique=True)

    class Meta:
        ordering = ('nome',)
        verbose_name = 'Tipo de Atividade Diversa'
        verbose_name_plural = 'Tipos de Atividades Diversas'

    def __str__(self):
        return self.nome


class AtividadeDiversa(models.ModelPlus):
    tipo = models.ForeignKeyPlus(TipoAtividadeDiversa, verbose_name='Tipo', on_delete=models.CASCADE)
    campus = models.ForeignKeyPlus(UnidadeOrganizacional, verbose_name='Campus', on_delete=models.CASCADE)
    data_inicio = models.DateTimeFieldPlus('Data de Início')
    data_termino = models.DateTimeFieldPlus('Data de Término', null=True, blank=True)
    observacao = models.TextField('Observação')
    servidores_envolvidos = models.ManyToManyField(Servidor, verbose_name='Servidores Envolvidos')
    cadastrado_por = models.CurrentUserField(verbose_name='Cadastrado Por')
    atualizado_por_vinculo = models.ForeignKeyPlus(
        'comum.Vinculo', null=True, verbose_name='Atualizado Por', related_name='atividadediversa_atualizado_por_vinculo', on_delete=models.CASCADE
    )
    atualizado_em = models.DateTimeFieldPlus('Atualizado em', null=True)
    cancelada = models.BooleanField('Cancelada', default=False)
    cancelada_em = models.DateTimeFieldPlus('Cancelada em', null=True, blank=True)
    cancelada_por_vinculo = models.ForeignKeyPlus(
        'comum.Vinculo', null=True, verbose_name='Cancelada Por', related_name='atividade_diversa_cancelada_por_vinculo', on_delete=models.CASCADE
    )

    class Meta:
        verbose_name = 'Atividade Diversa'
        verbose_name_plural = 'Atividades Diversas'

    def __str__(self):
        return f'{self.tipo} em {self.data_inicio}'

    def get_absolute_url(self):
        return f'/ae/atividadediversa/{self.id}/'


class AcaoEducativa(models.ModelPlus):
    titulo = models.CharField('Título', max_length=255)
    campus = models.ForeignKeyPlus(UnidadeOrganizacional, verbose_name='Campus', on_delete=models.CASCADE)
    data_inicio = models.DateTimeFieldPlus('Data de Início')
    data_termino = models.DateTimeFieldPlus('Data de Término', null=True, blank=True)
    descricao = models.TextField('Descrição')
    servidores_envolvidos = models.ManyToManyField(Servidor, verbose_name='Servidores Envolvidos')
    cadastrado_por = models.CurrentUserField(verbose_name='Cadastrado Por')
    atualizado_por_vinculo = models.ForeignKeyPlus(
        'comum.Vinculo', null=True, verbose_name='Atualizado Por', related_name='acao_educativa_atualizado_por_vinculo', on_delete=models.CASCADE
    )
    atualizado_em = models.DateTimeFieldPlus('Atualizado em', null=True)
    cancelada = models.BooleanField('Cancelada', default=False)
    cancelada_em = models.DateTimeFieldPlus('Cancelada em', null=True, blank=True)
    cancelada_por_vinculo = models.ForeignKeyPlus(
        'comum.Vinculo', null=True, verbose_name='Cancelada Por', related_name='acao_educativa_cancelada_por_vinculo', on_delete=models.CASCADE
    )

    class Meta:
        verbose_name = 'Ação Educativa'
        verbose_name_plural = 'Ações Educativas'

    def __str__(self):
        return f'{self.titulo} em {self.data_inicio}'

    def get_absolute_url(self):
        return f'/ae/acaoeducativa/{self.id}/'


class Edital(models.ModelPlus):
    descricao = models.CharFieldPlus('Descrição', max_length=5000)
    tipo_programa = models.ManyToManyFieldPlus('ae.TipoPrograma', verbose_name='Tipos de Programa')
    link_edital = models.CharFieldPlus('Link para o Edital', null=True, blank=True, max_length=1000)
    ativo = models.BooleanField('Ativo', default=True)

    class Meta:
        verbose_name = 'Edital da Assistência Estudantil'
        verbose_name_plural = 'Editais da Assistência Estudantil'

    def __str__(self):
        return self.descricao


class PeriodoInscricao(models.ModelPlus):
    SEARCH_FIELDS = [
        'edital__descricao',
        'campus__sigla',
    ]
    edital = models.ForeignKeyPlus(Edital, verbose_name='Edital', on_delete=models.CASCADE)
    campus = models.ForeignKeyPlus(UnidadeOrganizacional, verbose_name='Campus', on_delete=models.CASCADE)
    programa = models.ManyToManyFieldPlus(Programa, verbose_name='Programas Vinculados')
    data_inicio = models.DateTimeFieldPlus('Data de Início das Inscrições')
    data_termino = models.DateTimeFieldPlus('Data de Término das Inscrições')
    apenas_participantes = models.BooleanField('Apenas participantes dos programas podem se inscrever', default=False)
    data_resultado = models.DateTimeFieldPlus('Data do Resultado', null=True, blank=True)

    class Meta:
        verbose_name = 'Período de Inscrição'
        verbose_name_plural = 'Períodos de Inscrição'

    def __str__(self):
        return f'{format_(self.data_inicio.date())} a {format_(self.data_termino.date())} - {self.edital.descricao} - {self.campus.sigla}'

    def estah_aberto(self):
        agora = datetime.datetime.now()
        return self.data_inicio <= agora <= self.data_termino


class MotivoSolicitacaoRefeicao(models.ModelPlus):
    descricao = models.CharFieldPlus('Descrição', max_length=2000)
    ativo = models.BooleanField('Ativo', default=True)
    exibir_adicionar_participacao = models.BooleanField('Exibir em adicionar participação de Alimentação', default=True)
    exibir_inscricao_programa = models.BooleanField('Exibir na inscrição para o programa de Alimentação', default=True)
    exibir_solicitacao_refeicao = models.BooleanField('Exibir na solicitação de refeição', default=True)
    exibir_agendamento_refeicao = models.BooleanField('Exibir no agendamento de refeição', default=True)

    class Meta:
        verbose_name = 'Motivo de Atendimentos de Refeições'
        verbose_name_plural = 'Motivos de Atendimentos de Refeições'

    def __str__(self):
        return self.descricao


class DocumentoInscricaoAluno(models.Model):
    RG = 'RG'
    CPF = 'CPF'
    COMPROVANTE_RENDA = 'Comprovante de Renda'
    COMPROVANTE_RESIDENCIA = 'Comprovante de Residência'
    DOCUMENTO_COMPLEMENTAR = 'Documento Complementar'
    DECLARACAO_PREFEITURA = 'Declaração da Prefeitura'

    TIPO_ARQUIVO_CHOICES = (
        (RG, RG),
        (CPF, CPF),
        (COMPROVANTE_RENDA, COMPROVANTE_RENDA),
        (COMPROVANTE_RESIDENCIA, COMPROVANTE_RESIDENCIA),
        (DOCUMENTO_COMPLEMENTAR, DOCUMENTO_COMPLEMENTAR),
        (DECLARACAO_PREFEITURA, DECLARACAO_PREFEITURA),
    )

    TIPO_ARQUIVO_PENDENCIAS_CHOICES = (
        (COMPROVANTE_RENDA, COMPROVANTE_RENDA),
        (COMPROVANTE_RESIDENCIA, COMPROVANTE_RESIDENCIA),
        (DOCUMENTO_COMPLEMENTAR, DOCUMENTO_COMPLEMENTAR),
        (DECLARACAO_PREFEITURA, DECLARACAO_PREFEITURA),
    )

    aluno = models.ForeignKeyPlus('edu.Aluno', verbose_name='Aluno', on_delete=models.CASCADE)
    tipo_arquivo = models.CharField(verbose_name='Tipo do Arquivo', choices=TIPO_ARQUIVO_CHOICES, max_length=500)
    arquivo = models.PrivateFileField(verbose_name='Arquivo', max_length=255, upload_to='ae/inscricao/documentos')
    integrante_familiar = models.ForeignKeyPlus(
        'ae.IntegranteFamiliarCaracterizacao', verbose_name='Integrante Familiar', null=True, blank=True, on_delete=models.CASCADE
    )
    data_cadastro = models.DateTimeField('Data', auto_now_add=True, null=True, blank=True)
    cadastrado_por_vinculo = models.ForeignKeyPlus('comum.Vinculo', verbose_name='Responsável pela Cadastro', on_delete=models.CASCADE, null=True)
    pendente = models.BooleanField('Pendente', default=False)
    obs_pendencia = models.TextField('Observações', null=True, blank=True)
    prazo_correcao = models.DateTimeFieldPlus('Prazo para correção', null=True)
    pendencia_cadastrada_por = models.ForeignKeyPlus(
        'comum.Vinculo', verbose_name='Pendência cadastrada por', on_delete=models.CASCADE, null=True, related_name='documentoinscricao_pendencia_por'
    )
    pendencia_cadastrada_em = models.DateTimeFieldPlus('Pendência cadastrada em', null=True)
    pendencia_corrigida = models.BooleanField('Pendência Corrigida', default=False)
    pendencia_corrigida_em = models.DateTimeFieldPlus('Pendência corrigida em', null=True)
    pendencia_corrigida_por = models.ForeignKeyPlus(
        'comum.Vinculo',
        verbose_name='Pendência corrigida por',
        on_delete=models.CASCADE,
        null=True,
        related_name='documentoinscricao_pendencia_corrigida_por',
    )
    inscricao_caracterizacao = models.ForeignKeyPlus(
        'ae.InscricaoCaracterizacao', verbose_name='Dados gerais da inscrição', null=True, blank=True, on_delete=models.SET_NULL
    )
    inscricao = models.ForeignKeyPlus('ae.Inscricao', verbose_name='Inscrição', null=True, blank=True, on_delete=models.SET_NULL)
    validado = models.BooleanField('Validado', null=True)
    avaliado_em = models.DateTimeFieldPlus('Avaliado em', null=True)
    avaliado_por = models.ForeignKeyPlus(
        'comum.Vinculo',
        verbose_name='Avaliado por',
        on_delete=models.CASCADE,
        null=True,
        related_name='documentoinscricao_avaliado_por',
    )

    class Meta:
        verbose_name = 'Documentos da Inscrição do Aluno'
        verbose_name_plural = 'Documentos das Inscrições dos Alunos'

    def get_situacao(self):
        prazo_expiracao = Configuracao.get_valor_por_chave('ae', 'prazo_expiracao_documentacao')
        total_dias = prazo_expiracao and int(prazo_expiracao) or 365
        data_para_expiracao = somar_dias(datetime.datetime.now(), -total_dias)
        a_expirar = date.today() + relativedelta(months=-9)
        if self.data_cadastro.date() < data_para_expiracao.date():
            return '<span class="status status-error">Expirada</span>'
        elif self.data_cadastro.date() < a_expirar:
            return '<span class="status status-alert">A expirar</span>'
        else:
            return '<span class="status status-success">Ativa</span>'

    def eh_ativa(self):
        prazo_expiracao = Configuracao.get_valor_por_chave('ae', 'prazo_expiracao_documentacao')
        total_dias = prazo_expiracao and int(prazo_expiracao) or 365
        data_para_expiracao = somar_dias(datetime.datetime.now(), -total_dias)
        return self.data_cadastro.date() > data_para_expiracao.date()

    def __str__(self):
        return f'{self.tipo_arquivo} - {self.aluno!s}'

    def get_pendencia(self):
        if self.pendente:
            texto = '<dl>'
            if self.obs_pendencia:
                texto += f'<dt>Observações:</dt><dd>{self.obs_pendencia}</dd>'
            texto += f'<dt>Prazo:</dt><dd>Até {self.prazo_correcao.strftime("%d/%m/%Y %H:%M")}</dd>'
            texto += (
                f'<dt>Cadastrado por:</dt><dd>{self.pendencia_cadastrada_por.user} em {self.pendencia_cadastrada_em.strftime("%d/%m/%Y %H:%M")}</dd>'
            )
            texto += '</dl>'
            return texto
        return '-'

    def pode_editar(self):
        return self.pendente and self.eh_ativa() and not self.pendencia_corrigida and self.prazo_correcao > datetime.datetime.now()

    def tem_inscricao_com_pendencia(self):
        return Inscricao.ativas.filter(aluno=self.aluno, situacao_parecer=Inscricao.PENDENTE_DOCUMENTACAO).exists()


class DatasRecessoFerias(models.ModelPlus):
    data = models.DateField()
    campus = models.ForeignKeyPlus('rh.UnidadeOrganizacional', related_name='campus_data_recesso_ferias')
    atualizado_por = models.ForeignKeyPlus(
        'comum.Vinculo', null=True, verbose_name='Atualizado Por', related_name='recessoferias_atualizado_por', on_delete=models.CASCADE
    )
    atualizado_em = models.DateTimeField('Atualizado em', null=True, blank=True)

    class Meta:
        unique_together = ('data', 'campus')
        verbose_name = 'Data de Recesso/Férias'
        verbose_name_plural = 'Datas de Recesso/Férias'

    def __str__(self):
        return 'Datas de Recesso de Férias: {} - {}'.format(self.data.strftime('%d/%m/%Y'), self.campus)


class TipoPrograma(models.ModelPlus):
    titulo = models.CharFieldPlus('Título', max_length=255)
    descricao = models.CharFieldPlus('Descrição', max_length=2000)
    sigla = models.CharFieldPlus('Sigla', max_length=10)
    ativo = models.BooleanField('Ativo', default=True)
    id_modelo_termo_compromisso = models.PositiveIntegerField(verbose_name='ID do Modelo do Termo de Compromisso', null=True)
    modelo_termo_indicado_por = models.ForeignKeyPlus(Vinculo, verbose_name='Modelo indicado por', null=True, on_delete=models.SET_NULL)
    exige_inscricao_alimentacao = models.BooleanField(
        'Exige inscrição prévia no Programa de Alimentação Estudantil?',
        default=False,
        help_text='Marque este campo para obrigar o aluno a se inscrever no Programa de Alimentação Estudantil antes de se inscrever neste Tipo de Programa, caso haja período de inscrição aberto dentro do mesmo edital.',
    )

    class Meta:
        verbose_name = 'Tipo de Programa'
        verbose_name_plural = 'Tipos de Programa'

    def __str__(self):
        return self.titulo


class PerguntaInscricaoPrograma(models.ModelPlus):
    UNICA_ESCOLHA = 'Única Escolha'
    MULTIPLA_ESCOLHA = 'Múltipla Escolha'
    TEXTO = 'Texto'
    PARAGRAFO = 'Parágrafo'
    NUMERO = 'Número'
    SIM_NAO = 'Sim/Não'

    TIPO_RESPOSTA_CHOICES = (
        (TEXTO, TEXTO),
        (PARAGRAFO, PARAGRAFO),
        (NUMERO, NUMERO),
        (SIM_NAO, SIM_NAO),
        (UNICA_ESCOLHA, UNICA_ESCOLHA),
        (MULTIPLA_ESCOLHA, MULTIPLA_ESCOLHA),
    )

    tipo_programa = models.ForeignKeyPlus(
        TipoPrograma, related_name='pergunta_tipoprograma', verbose_name='Tipo do Programa', on_delete=models.CASCADE
    )
    pergunta = models.CharFieldPlus('Pergunta', max_length=2000)
    tipo_resposta = models.CharFieldPlus('Tipo de Resposta', max_length=100, choices=TIPO_RESPOSTA_CHOICES)
    obrigatoria = models.BooleanField('Resposta Obrigatória', default=True)
    ordem = models.IntegerField('Ordem', null=True)
    deve_compor_analise = models.BooleanField('Deve compor a Análise socioecômica?', default=False)
    ativo = models.BooleanField('Ativo', default=True)

    class Meta:
        ordering = ['ordem']
        verbose_name = 'Pergunta da Inscrição'
        verbose_name_plural = 'Perguntas da Inscrição'

    def __str__(self):
        return self.pergunta


class OpcaoRespostaInscricaoPrograma(models.ModelPlus):
    pergunta = models.ForeignKeyPlus(PerguntaInscricaoPrograma, related_name='pergunta_inscricao', verbose_name='Pergunta', on_delete=models.CASCADE)
    valor = models.CharFieldPlus('Opção de Resposta', max_length=200)
    ativo = models.BooleanField('Ativo', default=True)

    class Meta:
        ordering = ['id']
        verbose_name = 'Opção de Resposta da Inscrição'
        verbose_name_plural = 'Opções de Resposta da Inscrição'

    def __str__(self):
        return self.valor


class RespostaInscricaoPrograma(models.ModelPlus):
    inscricao = models.ForeignKeyPlus(Inscricao, related_name='resposta_inscricao', verbose_name='Inscrição', on_delete=models.CASCADE)
    pergunta = models.ForeignKeyPlus(
        PerguntaInscricaoPrograma, related_name='resposta_pergunta_inscricao', verbose_name='Pergunta', on_delete=models.CASCADE
    )
    resposta = models.ForeignKeyPlus(
        OpcaoRespostaInscricaoPrograma, related_name='resposta_escolhida', verbose_name='Resposta', on_delete=models.CASCADE, null=True
    )
    valor_informado = models.TextField('Resposta', null=True, blank=True)

    class Meta:
        verbose_name = 'Resposta da Inscrição'
        verbose_name_plural = 'Respostas da Inscrição'

    def __str__(self):
        return f'Resposta da Pergunta {self.pergunta}'

    def get_resposta(self):
        if self.pergunta.tipo_resposta == PerguntaInscricaoPrograma.MULTIPLA_ESCOLHA:
            return ', '.join(
                RespostaInscricaoPrograma.objects.filter(inscricao=self.inscricao, pergunta=self.pergunta).values_list('resposta__valor', flat=True)
            )
        else:
            return self.resposta or self.valor_informado

    def eh_multipla_escolha(self):
        return self.pergunta.tipo_resposta == PerguntaInscricaoPrograma.MULTIPLA_ESCOLHA


class PerguntaParticipacao(models.ModelPlus):
    UNICA_ESCOLHA = 'Única Escolha'
    MULTIPLA_ESCOLHA = 'Múltipla Escolha'
    TEXTO = 'Texto'
    PARAGRAFO = 'Parágrafo'
    NUMERO = 'Número'
    SIM_NAO = 'Sim/Não'

    TIPO_RESPOSTA_CHOICES = (
        (TEXTO, TEXTO),
        (PARAGRAFO, PARAGRAFO),
        (NUMERO, NUMERO),
        (SIM_NAO, SIM_NAO),
        (UNICA_ESCOLHA, UNICA_ESCOLHA),
        (MULTIPLA_ESCOLHA, MULTIPLA_ESCOLHA),
    )

    tipo_programa = models.ForeignKeyPlus(
        TipoPrograma, related_name='pergunta_part_tipoprograma', verbose_name='Tipo do Programa', on_delete=models.CASCADE
    )
    pergunta = models.CharFieldPlus('Pergunta', max_length=2000)
    tipo_resposta = models.CharFieldPlus('Tipo de Resposta', max_length=100, choices=TIPO_RESPOSTA_CHOICES)
    eh_info_financeira = models.BooleanField('É Informação Financeira?', default=False)
    obrigatoria = models.BooleanField('Resposta Obrigatória', default=True)
    ordem = models.IntegerField('Ordem', null=True)
    ativo = models.BooleanField('Ativo', default=True)

    class Meta:
        ordering = ['id']
        verbose_name = 'Pergunta da Participação'
        verbose_name_plural = 'Perguntas da Participação'

    def __str__(self):
        return self.pergunta

    def clean(self):
        if self.tipo_resposta and self.eh_info_financeira and self.tipo_resposta != PerguntaParticipacao.NUMERO:
            raise ValidationError('Quando a pergunta é sobre informação financeira, o tipo da resposta deve ser "Número".')


class OpcaoRespostaPerguntaParticipacao(models.ModelPlus):
    pergunta = models.ForeignKeyPlus(PerguntaParticipacao, related_name='pergunta_participacao', verbose_name='Pergunta', on_delete=models.CASCADE)
    valor = models.CharFieldPlus('Opção de Resposta', max_length=200)
    ativo = models.BooleanField('Ativo', default=True)

    class Meta:
        ordering = ['id']
        verbose_name = 'Opção de Resposta da Participação'
        verbose_name_plural = 'Opções de Resposta da Participação'

    def __str__(self):
        return self.valor


class RespostaParticipacao(models.ModelPlus):
    participacao = models.ForeignKeyPlus(Participacao, related_name='resposta_participacao', verbose_name='Participação', on_delete=models.CASCADE)
    pergunta = models.ForeignKeyPlus(
        PerguntaParticipacao, related_name='resposta_pergunta_participacao', verbose_name='Pergunta', on_delete=models.CASCADE
    )
    resposta = models.ForeignKeyPlus(
        OpcaoRespostaPerguntaParticipacao,
        related_name='resposta_escolhida_participacao',
        verbose_name='Resposta',
        on_delete=models.CASCADE,
        null=True,
    )
    valor_informado = models.TextField('Resposta', null=True, blank=True)

    class Meta:
        verbose_name = 'Resposta da Participação'
        verbose_name_plural = 'Respostas da Participação'

    def __str__(self):
        return self.resposta

    def eh_multipla_escolha(self):
        return self.pergunta.tipo_resposta == PerguntaParticipacao.MULTIPLA_ESCOLHA


class RelatorioGestao(models.ModelPlus):
    TODAS = 'Todas'
    ATE_MEIO = 'Até ½ SM'
    ENTRE_MEIO_E_UM = 'Entre ½ SM e 1 SM'
    ENTRE_UM_E_UM_MEIO = 'Entre 1 SM e 1 ½ SM'
    MAIOR_QUE_UM_E_MEIO = 'Maior que 1 ½ SM'

    OPCOES = (
        (TODAS, TODAS),
        (ATE_MEIO, ATE_MEIO),
        (ENTRE_MEIO_E_UM, ENTRE_MEIO_E_UM),
        (ENTRE_UM_E_UM_MEIO, ENTRE_UM_E_UM_MEIO),
        (MAIOR_QUE_UM_E_MEIO, MAIOR_QUE_UM_E_MEIO),
    )
    data_processamento = models.DateTimeField('Data de processamento', auto_now=True)
    campus = models.ForeignKeyPlus('rh.UnidadeOrganizacional', verbose_name='Campus', on_delete=models.CASCADE, null=True)
    ano = models.PositiveIntegerField('Ano')
    somente_alunos_ead = models.BooleanField('Exibir somente Alunos EAD')
    renda_per_capita = models.CharFieldPlus('Renda Per Capita', default=TODAS)

    class Meta:
        unique_together = ('campus', 'ano', 'somente_alunos_ead', 'renda_per_capita')


class RelatorioGestaoBase(models.ModelPlus):
    VALOR_MINIMO = MinValueValidator(Decimal('0.00'))
    relatorio = models.ForeignKeyPlus(RelatorioGestao, on_delete=models.CASCADE)
    qtd_janeiro = models.DecimalField(max_digits=10, decimal_places=2, default=0, validators=[VALOR_MINIMO])
    qtd_fevereiro = models.DecimalField(max_digits=10, decimal_places=2, default=0, validators=[VALOR_MINIMO])
    qtd_marco = models.DecimalField(max_digits=10, decimal_places=2, default=0, validators=[VALOR_MINIMO])
    qtd_abril = models.DecimalField(max_digits=10, decimal_places=2, default=0, validators=[VALOR_MINIMO])
    qtd_maio = models.DecimalField(max_digits=10, decimal_places=2, default=0, validators=[VALOR_MINIMO])
    qtd_junho = models.DecimalField(max_digits=10, decimal_places=2, default=0, validators=[VALOR_MINIMO])
    qtd_julho = models.DecimalField(max_digits=10, decimal_places=2, default=0, validators=[VALOR_MINIMO])
    qtd_agosto = models.DecimalField(max_digits=10, decimal_places=2, default=0, validators=[VALOR_MINIMO])
    qtd_setembro = models.DecimalField(max_digits=10, decimal_places=2, default=0, validators=[VALOR_MINIMO])
    qtd_outubro = models.DecimalField(max_digits=10, decimal_places=2, default=0, validators=[VALOR_MINIMO])
    qtd_novembro = models.DecimalField(max_digits=10, decimal_places=2, default=0, validators=[VALOR_MINIMO])
    qtd_dezembro = models.DecimalField(max_digits=10, decimal_places=2, default=0, validators=[VALOR_MINIMO])
    total_1_semestre = models.DecimalField(max_digits=10, decimal_places=2, default=0, validators=[VALOR_MINIMO])
    total_2_semestre = models.DecimalField(max_digits=10, decimal_places=2, default=0, validators=[VALOR_MINIMO])
    total_anual = models.DecimalField(max_digits=10, decimal_places=2, default=0, validators=[VALOR_MINIMO])
    renda_per_capita = models.CharFieldPlus('Renda Per Capita', default=RelatorioGestao.TODAS)

    class Meta:
        ordering = ['id']
        abstract = True


class RelatorioGrafico(models.ModelPlus):
    PIE = 'PieChart'
    GROUPEDCOLUMN = 'GroupedColumnChart'
    BAR = 'BarChart'
    TIPO_CHOICE = ((PIE, PIE), (GROUPEDCOLUMN, GROUPEDCOLUMN), (BAR, BAR))

    ATENDIMENTOS = 'Atendimentos'
    AUXILIOS = 'Auxílios'
    BOLSAS = 'Bolsas'
    PROGRAMAS = 'Programas'
    SAUDE = 'Saúde'
    RESUMO = 'Resumo'
    TIPO_RELATORIO_CHOICE = (
        (ATENDIMENTOS, ATENDIMENTOS),
        (AUXILIOS, AUXILIOS),
        (BOLSAS, BOLSAS),
        (PROGRAMAS, PROGRAMAS),
        (SAUDE, SAUDE),
        (RESUMO, RESUMO),
    )

    nome = models.CharFieldPlus()
    tipo = models.CharFieldPlus(choices=TIPO_CHOICE)
    relatorio = models.ForeignKeyPlus(RelatorioGestao, related_name='graficos', on_delete=models.CASCADE)
    tipo_relatorio = models.CharFieldPlus(choices=TIPO_RELATORIO_CHOICE)

    def get_dados(self):
        if self.tipo in [self.PIE, self.BAR]:
            return self.get_dados_tabelados()
        elif self.tipo == self.GROUPEDCOLUMN:
            return self.get_dados_groupedcolumn()

    def get_dados_tabelados(self):
        return [[label, int(valor)] for label, valor in self.dados.values_list('label', 'valor')]

    def get_dados_groupedcolumn(self):
        from collections import OrderedDict

        retorno = OrderedDict()
        categorias = OrderedSet()
        for label, valor, categoria in self.dados.values_list('label', 'valor', 'categoria'):
            dados = retorno.get(label, [])
            dados.append(int(valor))
            retorno[label] = dados
            categorias.add(categoria)
        return [[key, *valores] for key, valores in list(retorno.items())], categorias


class DadosRelatorioGrafico(models.ModelPlus):
    grafico = models.ForeignKeyPlus(RelatorioGrafico, related_name='dados', on_delete=models.CASCADE)
    label = models.CharFieldPlus()
    valor = models.DecimalField(max_digits=10, decimal_places=2, default=0, validators=[RelatorioGestaoBase.VALOR_MINIMO])
    categoria = models.CharFieldPlus(blank=True)

    class Meta:
        ordering = ['id']


class RelatorioGestaoAtendimentos(RelatorioGestaoBase):
    TOTAL_ATENDIMENTOS = 'Total de Atendimentos'
    ALUNOS_ASSISTIDOS = 'Alunos Assistidos'
    VALORES_GASTOS = 'Valores Gastos'
    AGRUPADOR_CHOICE = ((TOTAL_ATENDIMENTOS, TOTAL_ATENDIMENTOS), (ALUNOS_ASSISTIDOS, ALUNOS_ASSISTIDOS), (VALORES_GASTOS, VALORES_GASTOS))
    agrupador = models.CharFieldPlus(choices=AGRUPADOR_CHOICE)
    tipo = models.CharFieldPlus('Tipo de Atendimento')
    custeio = models.CharFieldPlus('Custeio')


class RelatorioGestaoAuxilios(RelatorioGestaoBase):
    TOTAL_AUXILIOS = 'Total de Auxílios'
    ALUNOS_ASSISTIDOS = 'Alunos Assistidos'
    VALORES_GASTOS = 'Valores Gastos'
    AGRUPADOR_CHOICE = ((TOTAL_AUXILIOS, TOTAL_AUXILIOS), (ALUNOS_ASSISTIDOS, ALUNOS_ASSISTIDOS), (VALORES_GASTOS, VALORES_GASTOS))
    agrupador = models.CharFieldPlus(choices=AGRUPADOR_CHOICE)
    tipo = models.CharFieldPlus('Tipo de Auxílio')


class RelatorioGestaoBolsas(RelatorioGestaoBase):
    TOTAL_BOLSAS = 'Total de Bolsas'
    ALUNOS_ASSISTIDOS = 'Alunos Assistidos'
    VALORES_GASTOS = 'Valores Gastos'
    AGRUPADOR_CHOICE = ((TOTAL_BOLSAS, TOTAL_BOLSAS), (ALUNOS_ASSISTIDOS, ALUNOS_ASSISTIDOS), (VALORES_GASTOS, VALORES_GASTOS))
    agrupador = models.CharFieldPlus(choices=AGRUPADOR_CHOICE)
    categoria = models.CharFieldPlus('Categoria de Bolsa')


class RelatorioGestaoProgramas(RelatorioGestaoBase):
    TOTAL_PARTICIPACOES = 'Total de Participações em Programas'
    ALUNOS_ASSISTIDOS = 'Alunos Assistidos'
    VALORES_GASTOS = 'Valores Gastos'
    AGRUPADOR_CHOICE = ((TOTAL_PARTICIPACOES, TOTAL_PARTICIPACOES), (ALUNOS_ASSISTIDOS, ALUNOS_ASSISTIDOS), (VALORES_GASTOS, VALORES_GASTOS))
    agrupador = models.CharFieldPlus(choices=AGRUPADOR_CHOICE)
    programa = models.CharFieldPlus('Programa')


class RelatorioGestaoSaude(RelatorioGestaoBase):
    TOTAL_ATENDIMENTOS = 'Total de Atendimentos'
    ALUNOS_ASSISTIDOS = 'Alunos Assistidos'
    AGRUPADOR_CHOICE = ((TOTAL_ATENDIMENTOS, TOTAL_ATENDIMENTOS), (ALUNOS_ASSISTIDOS, ALUNOS_ASSISTIDOS))
    agrupador = models.CharFieldPlus(choices=AGRUPADOR_CHOICE)
    tipo_atendimento = models.CharFieldPlus('Tipo de Atendimento')


class RelatorioGestaoResumo(RelatorioGestaoBase):
    ALUNOS_ASSISTIDOS = 'Alunos Assistidos'
    AGRUPADOR_CHOICE = ((ALUNOS_ASSISTIDOS, ALUNOS_ASSISTIDOS),)

    ATENDIMENTOS = 'Atendimentos'
    AUXILIOS = 'Auxílios'
    BOLSAS = 'Bolsas'
    PARTICIPANTES_PROGRAMAS = 'Participantes em Programas'
    ATENDIMENTOS_SAUDE = 'Atendimentos de Saúde'
    TOTAL = 'Total'
    TIPO_CHOICE = (
        (ATENDIMENTOS, ATENDIMENTOS),
        (AUXILIOS, AUXILIOS),
        (BOLSAS, BOLSAS),
        (PARTICIPANTES_PROGRAMAS, PARTICIPANTES_PROGRAMAS),
        (ATENDIMENTOS_SAUDE, ATENDIMENTOS_SAUDE),
        (TOTAL, TOTAL),
    )
    agrupador = models.CharFieldPlus(choices=AGRUPADOR_CHOICE)
    tipo = models.CharFieldPlus(choices=TIPO_CHOICE)


class TipoAuxilioEventual(models.ModelPlus):
    nome = models.CharFieldPlus()
    descricao = models.TextField('Descrição')
    exige_comprovante = models.BooleanField('Exige Documento de Comprovação', default=False)
    prazo_comprovante_utilizacao = models.IntegerFieldPlus(
        'Prazo para comprovação da utilização (em dias)',
        null=True,
        blank=True,
        help_text='Informe o prazo, em dias, a partir do deferimento do auxílio, para que o aluno cadastre o comprovante da utilização do auxílio.',
    )
    ativo = models.BooleanField('Ativo', default=True)
    campi_que_ofertam = models.ManyToManyFieldPlus(UnidadeOrganizacional, verbose_name='Campi que ofertam')

    class Meta:
        ordering = ('nome',)
        unique_together = ('nome', 'descricao')
        verbose_name = 'Tipo de Auxílio Eventual'
        verbose_name_plural = 'Tipos de Auxílios Eventuais'

    def __str__(self):
        return self.nome


class SolicitacaoAuxilioAluno(models.ModelPlus):
    aluno = models.ForeignKeyPlus('edu.Aluno', on_delete=models.CASCADE)
    data_solicitacao = models.DateTimeFieldPlus(verbose_name='Data da Solicitação', auto_now_add=True)
    tipo_auxilio = models.ForeignKeyPlus(TipoAuxilioEventual, verbose_name='Tipo do Auxílio', on_delete=models.CASCADE)
    motivo_solicitacao = models.CharFieldPlus('Motivo da Solicitação', max_length=5000)
    deferida = models.BooleanField(verbose_name='Deferida', null=True, blank=True)
    data_avaliacao = models.DateTimeFieldPlus(verbose_name='Data da Avaliação', null=True)
    parecer_avaliacao = models.CharFieldPlus('Parecer da Avaliação', max_length=5000, null=True)
    avaliador_vinculo = models.ForeignKeyPlus('comum.Vinculo', null=True, blank=True, verbose_name='Avaliador', on_delete=models.CASCADE)
    comprovante = models.PrivateFileField(verbose_name='Comprovantes', max_length=500, upload_to='ae/solicitacoes_auxilios/comprovantes', null=True)
    comprovacao_pendente = models.BooleanField('Comprovação de utilização do auxílio pendente', default=False)
    comprovante_utilizacao = models.PrivateFileField(
        verbose_name='Comprovantes da Utilização do Auxílio', max_length=500, upload_to='ae/solicitacoes_auxilios/comprovantes', null=True
    )
    comprovante_cadastrado_em = models.DateTimeFieldPlus(verbose_name='Comprovante cadastrado em', null=True)
    comprovante_avaliado_por = models.ForeignKeyPlus(
        'comum.Vinculo', null=True, blank=True, verbose_name='Avaliador', related_name='auxilio_comprovante_avaliado_por', on_delete=models.CASCADE
    )
    comprovante_avaliado_em = models.DateTimeFieldPlus(verbose_name='Comprovante avaliado em', null=True)
    comprovacao_validada = models.BooleanField('Comprovação de utilização do auxílio validada', null=True, blank=True)
    parecer_avaliacao_comprovacao = models.CharFieldPlus('Parecer da Avaliação', max_length=5000, null=True, blank=True)

    class Meta:
        verbose_name = 'Solicitação de Auxílios Eventuais'
        verbose_name_plural = 'Solicitações de Auxílios Eventuais'

    def __str__(self):
        return f'{self.aluno} - {self.tipo_auxilio}'


class AuxilioEventual(models.ModelPlus):
    responsavel = models.ForeignKeyPlus('comum.Vinculo', null=True, blank=True, verbose_name='Responsável', on_delete=models.CASCADE)
    tipo_auxilio = models.ForeignKeyPlus('ae.TipoAuxilioEventual', verbose_name='Tipo do Auxílio', on_delete=models.CASCADE)
    aluno = models.ForeignKeyPlus('edu.Aluno', verbose_name='Aluno', on_delete=models.CASCADE)
    data = models.DateTimeField('Atendimento', null=True)
    quantidade = models.FloatField('Quantidade', default=1)
    valor = models.DecimalFieldPlus('Valor', null=True, blank=True)
    observacao = models.TextField('Observação', blank=True)
    campus = models.ForeignKeyPlus('rh.UnidadeOrganizacional', verbose_name='Campus', on_delete=models.CASCADE)
    data_registro = models.DateTimeField('Data de Registro', auto_now_add=True, null=True, blank=True)
    atualizado_em = models.DateTimeField('Atualizado em', null=True, blank=True)
    arquivo = models.PrivateFileField(verbose_name='Arquivo', max_length=255, null=True, blank=True, upload_to='ae/auxilios_eventuais/comprovantes')

    class Meta:
        verbose_name = 'Auxílio Eventual'
        verbose_name_plural = 'Auxílios Eventuais'
        unique_together = ('aluno', 'tipo_auxilio', 'data')

    def __str__(self):
        return f'{self.tipo_auxilio}'


class HistoricoAlteracaoParecer(models.ModelPlus):
    inscricao = models.ForeignKeyPlus(Inscricao, verbose_name='Inscrição', on_delete=models.CASCADE)
    situacao_parecer = models.CharFieldPlus('Situação do Parecer', max_length=50, choices=Inscricao.SITUACAO_PARECER_FORM_CHOICES)
    parecer = models.TextField('Parecer', null=True)
    cadastrado_em = models.DateTimeFieldPlus('Cadastrado em')
    cadastrado_por = models.ForeignKeyPlus(Vinculo, verbose_name='Cadastrado por')
    documento = models.ForeignKeyPlus(DocumentoInscricaoAluno, verbose_name='Documento com pendência', null=True, on_delete=models.SET_NULL)
    obs = models.TextField('Observações', null=True)
    prazo_correcao = models.DateTimeFieldPlus('Prazo para correção', null=True)

    class Meta:
        verbose_name = 'Histórico de Alteração de Parecer'
        verbose_name_plural = 'Histórico de Alterações de Parecer'

    def __str__(self):
        return f'Histórico de Alteração de Parecer - {self.inscricao}'


class HistoricoAlteracaoTermoCompromisso(models.ModelPlus):
    inscricao = models.ForeignKeyPlus(Inscricao, verbose_name='Inscrição', on_delete=models.CASCADE)
    validacao_termo_compromisso = models.CharFieldPlus(
        'Validação do Termo de Compromisso', max_length=50, default='Pendente', choices=Inscricao.VALIDACAO_CHOICES
    )
    justificativa_validacao = models.TextField('Justificativa da Validação', null=True, blank=True)
    cadastrado_em = models.DateTimeFieldPlus('Cadastrado em', null=True)
    cadastrado_por = models.ForeignKeyPlus('comum.Vinculo', null=True, verbose_name='Cadastrado por', on_delete=models.CASCADE)

    class Meta:
        verbose_name = 'Histórico de Alteração do Termo de Compromisso'
        verbose_name_plural = 'Histórico de Alterações do Termo de Compromisso'

    def __str__(self):
        return f'Histórico de Alteração do Termo de Compromisso - {self.inscricao}'


class ComprovanteParticipacao(models.ModelPlus):
    TIPO_PAGAMENTO = 'Comprovante de Pagamento'
    TIPO_FOLHA_FREQUENCIA = 'Folha de Frequência'
    TIPO_CHOICES = (
        (TIPO_PAGAMENTO, TIPO_PAGAMENTO),
        (TIPO_FOLHA_FREQUENCIA, TIPO_FOLHA_FREQUENCIA),
    )
    MES_CHOICES = (
        ('Janeiro', 'Janeiro'),
        ('Fevereiro', 'Fevereiro'),
        ('Março', 'Março'),
        ('Abril', 'Abril'),
        ('Maio', 'Maio'),
        ('Junho', 'Junho'),
        ('Julho', 'Julho'),
        ('Agosto', 'Agosto'),
        ('Setembro', 'Setembro'),
        ('Outubro', 'Outubro'),
        ('Novembro', 'Novembro'),
        ('Dezembro', 'Dezembro'),
    )
    aluno = models.ForeignKeyPlus(Aluno, verbose_name='Aluno', on_delete=models.CASCADE)
    campus = models.ForeignKeyPlus(UnidadeOrganizacional, verbose_name='Campus')
    programa = models.ForeignKeyPlus(Programa, verbose_name='Programa', on_delete=models.CASCADE)
    participacao = models.ForeignKeyPlus(Participacao, verbose_name='Participação', on_delete=models.CASCADE)
    tipo = models.CharFieldPlus('Tipo do Comprovante', max_length=50, choices=TIPO_CHOICES)
    mes = models.CharFieldPlus('Mês', max_length=50, choices=MES_CHOICES)
    ano = models.IntegerFieldPlus(verbose_name='Ano')
    pendente = models.BooleanField('Pendente', default=True)
    cadastrado_em = models.DateTimeFieldPlus('Cadastrado em', null=True)
    valido = models.BooleanField('Válido', default=False)
    avaliado_em = models.DateTimeFieldPlus('Avaliado em', null=True)
    avaliado_por = models.ForeignKeyPlus(Vinculo, verbose_name='Avaliado por', null=True, on_delete=models.SET_NULL)
    justificativa = models.TextField('Justificativa', null=True)
    gerado_em = models.DateTimeFieldPlus('Gerado em', auto_now_add=True)
    arquivo = models.PrivateFileField(verbose_name='Arquivo', max_length=255, null=True, blank=True, upload_to='ae/participacoes/comprovantes')

    class Meta:
        verbose_name = 'Comprovante de Participação'
        verbose_name_plural = 'Comprovantes de Participação'

    def __str__(self):
        return f'Comprovante de Participação - {self.aluno} ({self.mes}/{self.ano})'


class AlteracaoParticipacaoAlimentacao(models.ModelPlus):
    participacao = models.ForeignKeyPlus('ae.Participacao', verbose_name='Participação', on_delete=models.CASCADE)
    campus = models.ForeignKeyPlus(UnidadeOrganizacional, verbose_name='Campus')
    solicitacao_cafe = models.OneToOneField(
        'ae.SolicitacaoAlimentacao',
        verbose_name='Solicitação de Café da manhã',
        on_delete=models.CASCADE,
        related_name='alteracao_alimentacao_cafe',
        null=True,
    )
    solicitacao_almoco = models.OneToOneField(
        'ae.SolicitacaoAlimentacao',
        verbose_name='Solicitação de Almoço',
        on_delete=models.CASCADE,
        related_name='alteracao_alimentacao_almoco',
        null=True,
    )
    solicitacao_jantar = models.OneToOneField(
        'ae.SolicitacaoAlimentacao',
        verbose_name='Solicitação de Jantar',
        on_delete=models.CASCADE,
        related_name='alteracao_alimentacao_janta',
        null=True,
    )
    solicitada_em = models.DateTimeFieldPlus('Data da Solicitação', auto_now_add=True)
    motivo = models.TextField('Motivo da Solicitação')
    deferida = models.BooleanField('Deferida', null=True)
    avaliada_por = models.ForeignKeyPlus(Vinculo, verbose_name='Avaliada por', null=True)
    avaliada_em = models.DateTimeFieldPlus('Avaliada em', null=True)
    justificativa = models.TextField('Justificativa do Indeferimento', null=True)

    class Meta:
        verbose_name = 'Solicitação de Alteração de Participação'
        verbose_name_plural = 'Solicitações de Alteração de Participação'

    def __str__(self):
        return f'Solicitação de Alteração - {self.participacao}'


class HistoricoDocumentoInscricaoAluno(models.Model):
    documento = models.ForeignKeyPlus(DocumentoInscricaoAluno, verbose_name='Documento', on_delete=models.CASCADE)
    arquivo = models.PrivateFileField(verbose_name='Arquivo', max_length=255, upload_to='ae/inscricao/documentos')
    data_cadastro = models.DateTimeField('Data', auto_now_add=True, null=True, blank=True)
    cadastrado_por = models.ForeignKeyPlus('comum.Vinculo', verbose_name='Responsável pela Cadastro', on_delete=models.CASCADE, null=True)
    cadastrado_em = models.DateTimeField('Cadastrado em')

    class Meta:
        verbose_name = 'Histórico de Documentação da Inscrição'
        verbose_name_plural = 'Históricos de Documentação da Inscrição'

    def __str__(self):
        return f'{self.documento} - {self.data_cadastro}'


class CriterioSelecaoPrograma(models.Model):
    criterio = models.CharFieldPlus('Critério', max_length=1000)
    opcao = models.CharFieldPlus('Opção', max_length=1000)
    tipo_programa = models.ManyToManyFieldPlus(TipoPrograma, verbose_name='Tipo do Programa')
    gera_pontuacao = models.BooleanField('Gera pontuação?', default=False)
    pontuacao = models.IntegerField('Pontuação')
    restritivo = models.BooleanField('É restritivo?', default=False)
    cadastrado_por = models.ForeignKeyPlus('comum.Vinculo', verbose_name='Cadastrado', on_delete=models.CASCADE)
    cadastrado_em = models.DateTimeField('Cadastrado em', auto_now_add=True)

    class Meta:
        verbose_name = 'Critério de Seleção de Programa'
        verbose_name_plural = 'Critérios de Seleção de Programa'

    def __str__(self):
        return f'{self.criterio} - {self.opcao} - {self.get_tipos_programas()}'

    def get_tipos_programas(self):
        return ', '.join([tipo.titulo for tipo in self.tipo_programa.all()])


class ParametroSelecaoPrograma(models.Model):
    DIAS_SUGERIDOS_CHOICES = (
        (0, '0'),
        (1, '1'),
        (2, '2'),
        (3, '3'),
        (4, '4'),
        (5, '5'),
        (6, '6'),
        (7, '7'),
        (8, '8'),
        (9, '9'),
        (10, '10'),
        (11, '11'),
        (12, '12'),
        (13, '13'),
        (14, '14'),
        (15, '15'),
    )
    PORCENTAGEM_CHOICES = (
        (0, '0%'),
        (10, '10%'),
        (20, '20%'),
        (30, '30%'),
        (40, '40%'),
        (50, '50%'),
        (60, '60%'),
        (70, '70%'),
        (80, '80%'),
        (90, '90%'),
        (100, '100%'),
    )
    tipo_programa = models.ForeignKeyPlus(TipoPrograma, verbose_name='Tipo do Programa', on_delete=models.CASCADE)
    uo = models.ForeignKeyPlus('rh.UnidadeOrganizacional', verbose_name='Campus', on_delete=models.CASCADE)
    pontuacao_minima = models.PositiveIntegerField('Pontuação')
    cadastrado_por = models.ForeignKeyPlus('comum.Vinculo', verbose_name='Cadastrado', on_delete=models.CASCADE)
    cadastrado_em = models.DateTimeField('Cadastrado em', auto_now_add=True)
    dias_sugeridos = models.IntegerFieldPlus('Refeições sugeridas', null=True, choices=DIAS_SUGERIDOS_CHOICES)
    porcentagem_sugerida = models.IntegerFieldPlus('Porcentagem sugerida', null=True, choices=PORCENTAGEM_CHOICES)

    class Meta:
        verbose_name = 'Parâmetro de Seleção de Programa'
        verbose_name_plural = 'Parâmetros de Seleção de Programa'

    def __str__(self):
        if self.tipo_programa.sigla == Programa.TIPO_ALIMENTACAO:
            return f'{self.tipo_programa} - {self.uo} - Refeições: {self.dias_sugeridos} - Pontuação: {self.pontuacao_minima}'
        return f'{self.tipo_programa} - {self.uo} - Porcentagem sugerida: {self.porcentagem_sugerida} - Pontuação: {self.pontuacao_minima}'


class AnaliseInscricao(models.Model):
    ZERO_A_UM = 'De 0 a um salário-mínimo'
    UM_A_DOIS = 'De um salário-mínimo até dois salários-mínimos'
    DOIS_A_TRES = 'De dois salários-mínimos até três salários-mínimos'
    MAIS_DE_TRES = 'Superior a três salários-mínimos'
    RENDA_FAMILIAR_BRUTA_CHOICES = (
        (ZERO_A_UM, ZERO_A_UM),
        (UM_A_DOIS, UM_A_DOIS),
        (DOIS_A_TRES, DOIS_A_TRES),
        (MAIS_DE_TRES, MAIS_DE_TRES),
    )

    ZERO_A_109 = 'De 0 até R$ 109'
    DE_109_A_218 = 'De R$ 109,01 até R$ 218'
    DE_218_A_MEIO_SM = 'De R$ 218,01 até meio salário mínimo'
    SUPERIOR_MEIO_SM = 'Superior a meio salário mínimo'
    ENTRE_MEIO_E_UM_SM = 'Entre meio salário mínimo e 1 salário mínimo'
    ENTRE_UM_E_UM_MEIO_SM = 'Entre 1 salário mínimo e 1 e meio salário mínimo'
    ENTRE_UM_MEIO_E_DOIS_SM = 'Entre 1 e meio salário mínimo e 2 salários mínimos'
    SUPERIOR_2_SM = 'Superior a 2 salários mínimos'
    RENDA_FAMILIAR_PER_CAPITA_CHOICES = (
        (ZERO_A_109, ZERO_A_109),
        (DE_109_A_218, DE_109_A_218),
        (DE_218_A_MEIO_SM, DE_218_A_MEIO_SM),
        (ENTRE_MEIO_E_UM_SM, ENTRE_MEIO_E_UM_SM),
        (ENTRE_UM_E_UM_MEIO_SM, ENTRE_UM_E_UM_MEIO_SM),
        (ENTRE_UM_MEIO_E_DOIS_SM, ENTRE_UM_MEIO_E_DOIS_SM),
        (SUPERIOR_2_SM, SUPERIOR_2_SM),
        (SUPERIOR_MEIO_SM, 'Superior a meio salário mínimo (com base nos dados importados do cadúnico)'),
    )

    class SituacaoAnalise(models.TextChoices):
        NAO_ANALISADO = 'Não analisado', 'Não analisado'
        ANALISADO_PROGRAMA = 'Analisado neste programa', 'Analisado neste programa'
        ANALISADO_TODOS_PROGRAMAS = 'Analisado em todos os programas', 'Analisado em todos os programas'

    edital = models.ForeignKeyPlus(Edital, verbose_name='Edital', on_delete=models.CASCADE)
    programa = models.ForeignKeyPlus(Programa, verbose_name='Programa', on_delete=models.CASCADE)
    tipo_programa = models.ForeignKeyPlus(TipoPrograma, verbose_name='Tipo do Programa', on_delete=models.CASCADE)
    tipo_programa_sigla = models.CharFieldPlus('Sigla do Tipo do Programa', null=True, max_length=50)
    inscricao = models.ForeignKeyPlus('ae.Inscricao', verbose_name='Inscrição', on_delete=models.CASCADE)
    uo = models.ForeignKeyPlus('rh.UnidadeOrganizacional', verbose_name='Campus', on_delete=models.CASCADE)
    aluno = models.ForeignKeyPlus('edu.Aluno', verbose_name='Aluno', on_delete=models.CASCADE)
    identificacao = models.CharFieldPlus('Identificação do aluno', max_length=5000)
    curso = models.CharFieldPlus('Curso', max_length=500)
    situacao = models.CharFieldPlus('Situação', max_length=100)
    turno = models.CharFieldPlus('Turno', max_length=100)
    cidade = models.CharFieldPlus('Cidade', max_length=500)
    situacao_documentacao = models.CharFieldPlus('Situação da documentação', max_length=100)
    documentacao_entregue = models.BooleanField('Documentação entregue', default=False)
    participacoes = models.CharFieldPlus('Participações', max_length=1000)
    renda_bruta = models.CharFieldPlus('Renda Bruta', max_length=100)
    renda_per_capita = models.CharFieldPlus('Renda per capita', max_length=100)
    valor_renda_per_capita = models.DecimalFieldPlus('Valor da Renda per capita', default=0)
    qtd_pessoas = models.CharFieldPlus('Quantidade de pessoas', max_length=100)
    faixa_etaria = models.CharFieldPlus('Faixa etária', max_length=100)
    situacao_trabalho = models.CharFieldPlus('Situação de trabalho', max_length=100)
    zona_domiciliar = models.CharFieldPlus('Tipo de zona domiciliar', max_length=100)
    origem_escolar = models.CharFieldPlus('Origem escolar', max_length=100)
    composicao_maior_60 = models.CharFieldPlus('Há pessoas do núcleo familiar com 60 anos ou mais?', max_length=100)
    composicao_menor_14 = models.CharFieldPlus('Há pessoas do núcleo familiar com idade inferior a 14 anos?', max_length=100)
    composicao_deficiencia = models.CharFieldPlus('Há pessoas do núcleo familiar com deficiência?', max_length=100, null=True)
    doenca_cronica = models.CharFieldPlus('Há pessoas do núcleo familiar com doenças crônicas?', max_length=100)
    despesa_medicamentos = models.CharFieldPlus('Possui despesas contínuas com medicamentos e/ou tratamento de saúde?', max_length=100, null=True)
    recebe_bolsa = models.CharFieldPlus('Recebe bolsas?', max_length=100)
    beneficiario_programa_social = models.CharFieldPlus('Beneficiário de programa social?', max_length=100)
    despesas_basicas_volumosas = models.CharFieldPlus('Despesas básicas volumosas?', max_length=100)
    gasto_transporte = models.DecimalFieldPlus('Valor de custo mensal com transporte', default=0)
    gasto_transporte_sugerido = models.DecimalFieldPlus('Gasto sugerido com transporte', default=0)
    existe_reprovacao = models.CharFieldPlus('Existência de reprovação?', max_length=100)
    cumpriu_toda_ch = models.CharFieldPlus('Cumpriu toda a carga horária de disciplinas?', max_length=100)
    possui_criterio_restritivo = models.BooleanField('Possui critérios restritivos', default=False)
    pontuacoes = models.JSONField()
    pontuacao_criterios = models.PositiveIntegerField('Pontuação dos critérios')
    pontuacao_especificidade = models.PositiveIntegerField('Pontuação de Análise Social por especificidade', default=0)
    pontuacao_especificidade_por = models.ForeignKeyPlus(
        'comum.Vinculo', verbose_name='Informada por', related_name='analise_pontuacao_especificidade', null=True, on_delete=models.SET_NULL
    )
    pontuacao_especificidade_em = models.DateTimeField('Informada em', null=True)
    pontuacao_especificidade_avaliacao = models.TextField('Avaliação', null=True, blank=True)
    pontuacao_total = models.PositiveIntegerField('Pontuação total')
    simulacao_resultado = models.IntegerFieldPlus('Simulação de resultado', null=True)
    simulacao_resultado_texto = models.CharFieldPlus('Simulação de resultado', null=True, max_length=5000)
    simulacao_resultado_por = models.ForeignKeyPlus(
        'comum.Vinculo', verbose_name='Informada por', related_name='analise_pontuacao_simulacao', null=True, on_delete=models.SET_NULL
    )
    simulacao_resultado_em = models.DateTimeField('Informada em', null=True)
    valor_simulacao_resultado = models.DecimalFieldPlus('Valor do Resultado Simulado', default=0)
    gerada_por = models.ForeignKeyPlus('comum.Vinculo', verbose_name='Gerada por', on_delete=models.CASCADE)
    gerada_em = models.DateTimeField('Gerada em', auto_now_add=True)
    observacoes = models.TextField('Observações', null=True)
    observacoes_por = models.ForeignKeyPlus(
        'comum.Vinculo', verbose_name='Observações por', related_name='analise_obs', null=True, on_delete=models.SET_NULL
    )
    observacoes_em = models.DateTimeField('Observações em', null=True)
    refeicao_seg = models.IntegerFieldPlus(null=True)
    refeicao_ter = models.IntegerFieldPlus(null=True)
    refeicao_qua = models.IntegerFieldPlus(null=True)
    refeicao_qui = models.IntegerFieldPlus(null=True)
    refeicao_sex = models.IntegerFieldPlus(null=True)
    total_refeicoes = models.IntegerFieldPlus(null=True)
    banco = models.CharFieldPlus('Banco', max_length=100, null=True)
    agencia = models.CharFieldPlus('Agência', max_length=100, null=True)
    operacao = models.CharFieldPlus('Operação', max_length=100, null=True)
    conta = models.CharFieldPlus('Conta', max_length=100, null=True)
    id_do_aluno = models.CharFieldPlus('ID do Aluno', max_length=20, null=True)
    turno_escolhido = models.CharFieldPlus('Turno escolhido', max_length=50, null=True)
    matricula = models.CharFieldPlus('Matrícula', max_length=50, null=True)
    semestre_atual = models.CharFieldPlus('Semestre/Ano', max_length=50, null=True)
    id_da_participacao_atual = models.CharFieldPlus('ID da participação atual', max_length=20, null=True)
    motivo_atendimento = models.CharFieldPlus('Motivo do Atendimento', max_length=2000, null=True)
    qtd_refeicoes_sugeridas = models.IntegerFieldPlus('Quantidade de refeições sugeridas', null=True)
    gasto_mensal_editado_por = models.ForeignKeyPlus(
        'comum.Vinculo', verbose_name='Gasto mensal editado por', related_name='gasto_mensal_editado_por', null=True, on_delete=models.SET_NULL
    )
    gasto_mensal_editado_em = models.DateTimeField('Gasto mensal editado em', null=True)
    turno_indicado_na_analise = models.CharFieldPlus('Turno escolhido', max_length=50, null=True, choices=TurnoChoices.TURNO_CHOICES)
    turno_indicado_na_analise_por = models.ForeignKeyPlus(
        'comum.Vinculo', verbose_name='Turno indicado por', null=True, on_delete=models.SET_NULL, related_name='turno_indicado_por'
    )
    turno_indicado_na_analise_em = models.DateTimeField('Turno indicado em', null=True)
    situacao_analise = models.CharFieldPlus(
        'Situação da análise', max_length=200, default=SituacaoAnalise.NAO_ANALISADO, choices=SituacaoAnalise.choices
    )

    class Meta:
        verbose_name = 'Análise da Inscrição em Programa'
        verbose_name_plural = 'Análise das Inscrições de Programa'

    def __str__(self):
        return f'{self.programa} - {self.edital} - {self.aluno}'

    def get_sugestoes(self):
        parametro = ParametroSelecaoPrograma.objects.filter(
            uo_id=self.uo_id, tipo_programa_id=self.tipo_programa_id, pontuacao_minima__lte=self.pontuacao_total
        ).order_by('-pontuacao_minima')
        if parametro.exists():
            if self.qtd_refeicoes_sugeridas:
                if self.tipo_programa_sigla == Programa.TIPO_ALIMENTACAO:
                    if self.qtd_refeicoes_sugeridas == parametro[0].dias_sugeridos:
                        return f'Refeições: {self.qtd_refeicoes_sugeridas}'
                    else:
                        return mark_safe('<span class="status status-error">Reprocessar análises</span>')
                else:
                    if self.qtd_refeicoes_sugeridas == parametro[0].porcentagem_sugerida:
                        return f'Porcentagem: {self.qtd_refeicoes_sugeridas}% <br> Total: R$ {self.gasto_transporte_sugerido}'
                    else:
                        return mark_safe('<span class="status status-error">Reprocessar análises</span>')
            else:
                return mark_safe('<span class="status status-error">Reprocessar análises</span>')
        return ''

    def get_simulacao_resultado(self):
        if self.simulacao_resultado or self.simulacao_resultado == 0:
            if self.tipo_programa_sigla == Programa.TIPO_ALIMENTACAO:
                return f'Refeições: {self.simulacao_resultado}'
            else:
                return f'Porcentagem: {self.simulacao_resultado}% <br> Total: R$ {self.valor_simulacao_resultado}'
        elif self.simulacao_resultado_texto:
            if self.tipo_programa_sigla == Programa.TIPO_TRABALHO:
                return f'Setor do bolsista: {self.simulacao_resultado_texto}'
            else:
                return f'R$ {self.simulacao_resultado_texto}'
        return ''

    def get_turno_escolhido(self):
        return self.get_turno_indicado_na_analise_display() or self.turno_escolhido

    def atualizar_pontuacao(self):
        data = {}
        pontuacao_trabalho = 0
        pontuacao_total = 0
        from ae.forms import CriterioSelecaoProgramaForm

        criterios_programa = CriterioSelecaoPrograma.objects.filter(tipo_programa=self.tipo_programa.id)
        criterio_renda = criterios_programa.filter(
            criterio=CriterioSelecaoProgramaForm.RENDA_PER_CAPITA, opcao=self.aluno.caracterizacao.get_faixa_renda_per_capita()
        )
        if criterio_renda.exists():
            criterio_selecionado = criterio_renda.first()
            pontuacao = criterio_selecionado.pontuacao
            pontuacao_total += pontuacao
            data[f'{CriterioSelecaoProgramaForm.RENDA_PER_CAPITA}'] = pontuacao
            if criterio_selecionado.restritivo:
                self.possui_criterio_restritivo = True

        tem_pontuacao_trabalho = None
        self.situacao_trabalho = self.aluno.caracterizacao.responsavel_financeir_trabalho_situacao.descricao
        criterios_programa = CriterioSelecaoPrograma.objects.filter(gera_pontuacao=True, tipo_programa=self.programa.tipo_programa)
        ultima_caracterizacao = InscricaoCaracterizacao.objects.filter(aluno=self.aluno).latest('id')
        if criterios_programa.filter(criterio=CriterioSelecaoProgramaForm.SITUACAO_TRABALHO).exists():
            tem_pontuacao_trabalho = criterios_programa.filter(criterio=CriterioSelecaoProgramaForm.SITUACAO_TRABALHO).order_by('pontuacao')
        if tem_pontuacao_trabalho:
            total_integrantes = 0
            pontuacao_total_dos_integrantes = 0
            integrantes_da_familia = IntegranteFamiliarCaracterizacao.objects.filter(inscricao_caracterizacao=ultima_caracterizacao)
            for criterio_trabalho in tem_pontuacao_trabalho:
                for integrante in integrantes_da_familia:
                    if integrante.situacao_trabalho.descricao == criterio_trabalho.opcao and criterio_trabalho.pontuacao > 0:
                        pontuacao_total_dos_integrantes += criterio_trabalho.pontuacao
                        total_integrantes += 1
                        if criterio_trabalho.restritivo:
                            self.possui_criterio_restritivo = True

                if self.aluno.caracterizacao.trabalho_situacao.descricao == criterio_trabalho.opcao and criterio_trabalho.pontuacao > 0:
                    pontuacao_total_dos_integrantes += criterio_trabalho.pontuacao
                    total_integrantes += 1
            if total_integrantes:
                pontuacao_trabalho = pontuacao_total_dos_integrantes / total_integrantes

        pontuacao_total += pontuacao_trabalho
        data[f'{CriterioSelecaoProgramaForm.SITUACAO_TRABALHO}'] = pontuacao_trabalho

        criterio_escola = criterios_programa.filter(criterio=CriterioSelecaoProgramaForm.ORIGEM_ESCOLAR, opcao=self.origem_escolar)
        if criterio_escola.exists():
            criterio_selecionado = criterio_escola.first()
            pontuacao = criterio_selecionado.pontuacao
            pontuacao_total += pontuacao
            if criterio_selecionado.restritivo:
                self.possui_criterio_restritivo = True
            data[f'{CriterioSelecaoProgramaForm.ORIGEM_ESCOLAR}'] = pontuacao

        criterio_zona = criterios_programa.filter(criterio=CriterioSelecaoProgramaForm.TIPO_ZONA, opcao=self.zona_domiciliar)
        if criterio_zona.exists():
            criterio_selecionado = criterio_zona.first()
            pontuacao = criterio_selecionado.pontuacao
            pontuacao_total += pontuacao
            if criterio_selecionado.restritivo:
                self.possui_criterio_restritivo = True
            data[f'{CriterioSelecaoProgramaForm.TIPO_ZONA}'] = pontuacao

        if self.zona_domiciliar not in ('Comunidade Quilombola', 'Rural', 'Comunidade Indígena') and ultima_caracterizacao.eh_quilombola:
            criterio_zona = criterios_programa.filter(
                criterio=CriterioSelecaoProgramaForm.TIPO_ZONA, opcao__in=['Comunidade Quilombola', 'Rural', 'Comunidade Indígena']
            )
            if criterio_zona.exists():
                criterio_selecionado = criterio_zona.first()
                pontuacao = criterio_selecionado.pontuacao
                pontuacao_total += pontuacao
                if criterio_selecionado.restritivo:
                    self.possui_criterio_restritivo = True
                data[f'{CriterioSelecaoProgramaForm.TIPO_ZONA}'] = pontuacao

        criterio_maior_60 = criterios_programa.filter(criterio=CriterioSelecaoProgramaForm.MAIOR_60, opcao=self.composicao_maior_60)
        if criterio_maior_60.exists():
            criterio_selecionado = criterio_maior_60.first()
            pontuacao = criterio_selecionado.pontuacao
            pontuacao_total += pontuacao
            if criterio_selecionado.restritivo:
                self.possui_criterio_restritivo = True
            data[f'{CriterioSelecaoProgramaForm.MAIOR_60}'] = pontuacao

        criterio_menor_14 = criterios_programa.filter(criterio=CriterioSelecaoProgramaForm.MENOR_14, opcao=self.composicao_menor_14)
        if criterio_menor_14.exists():
            criterio_selecionado = criterio_menor_14.first()
            pontuacao = criterio_selecionado.pontuacao
            pontuacao_total += pontuacao
            if criterio_selecionado.restritivo:
                self.possui_criterio_restritivo = True
            data[f'{CriterioSelecaoProgramaForm.MENOR_14}'] = pontuacao

        criterio_com_deficiencia = criterios_programa.filter(criterio=CriterioSelecaoProgramaForm.COM_DEFICIENCIA, opcao=self.composicao_deficiencia)
        if criterio_com_deficiencia.exists():
            criterio_selecionado = criterio_com_deficiencia.first()
            pontuacao = criterio_selecionado.pontuacao
            pontuacao_total += pontuacao
            if criterio_selecionado.restritivo:
                self.possui_criterio_restritivo = True
            data[f'{CriterioSelecaoProgramaForm.COM_DEFICIENCIA}'] = pontuacao

        doenca_cronica = criterios_programa.filter(criterio=CriterioSelecaoProgramaForm.DOENCA_CRONICA, opcao=self.doenca_cronica)
        if doenca_cronica.exists():
            criterio_selecionado = doenca_cronica.first()
            pontuacao = criterio_selecionado.pontuacao
            pontuacao_total += pontuacao
            if criterio_selecionado.restritivo:
                self.possui_criterio_restritivo = True
            data[f'{CriterioSelecaoProgramaForm.DOENCA_CRONICA}'] = pontuacao

        gasto_medicamento = criterios_programa.filter(criterio=CriterioSelecaoProgramaForm.GASTOS_MEDICAMENTOS, opcao=self.despesa_medicamentos)
        if gasto_medicamento.exists():
            criterio_selecionado = gasto_medicamento.first()
            pontuacao = criterio_selecionado.pontuacao
            pontuacao_total += pontuacao
            if criterio_selecionado.restritivo:
                self.possui_criterio_restritivo = True
            data[f'{CriterioSelecaoProgramaForm.GASTOS_MEDICAMENTOS}'] = pontuacao

        recebe_bolsa = criterios_programa.filter(criterio=CriterioSelecaoProgramaForm.RECEBE_BOLSA, opcao=self.recebe_bolsa)
        if recebe_bolsa.exists():
            criterio_selecionado = recebe_bolsa.first()
            pontuacao = criterio_selecionado.pontuacao
            pontuacao_total += pontuacao
            if criterio_selecionado.restritivo:
                self.possui_criterio_restritivo = True
            data[f'{CriterioSelecaoProgramaForm.RECEBE_BOLSA}'] = pontuacao

        beneficio_programa = criterios_programa.filter(
            criterio=CriterioSelecaoProgramaForm.BENEFICIARIO_PROGRAMA_SOCIAL, opcao=self.beneficiario_programa_social
        )
        if beneficio_programa.exists():
            criterio_selecionado = beneficio_programa.first()
            pontuacao = criterio_selecionado.pontuacao
            pontuacao_total += pontuacao
            if criterio_selecionado.restritivo:
                self.possui_criterio_restritivo = True
            data[f'{CriterioSelecaoProgramaForm.BENEFICIARIO_PROGRAMA_SOCIAL}'] = pontuacao

        despesas_volumosas = criterios_programa.filter(
            criterio=CriterioSelecaoProgramaForm.DESPESAS_BASICAS_VOLUMOSAS, opcao=self.despesas_basicas_volumosas
        )
        if despesas_volumosas.exists():
            criterio_selecionado = despesas_volumosas.first()
            pontuacao = criterio_selecionado.pontuacao
            pontuacao_total += pontuacao
            if criterio_selecionado.restritivo:
                self.possui_criterio_restritivo = True
            data[f'{CriterioSelecaoProgramaForm.DESPESAS_BASICAS_VOLUMOSAS}'] = pontuacao

        bolsa_integral_particular = criterios_programa.filter(criterio=CriterioSelecaoProgramaForm.BOLSA_INTEGRAL_ESCOLA_PART, opcao='Sim')
        if (
            bolsa_integral_particular.exists()
            and DocumentoInscricaoAluno.objects.filter(
                aluno=self.aluno, validado=True, tipo_arquivo='Comprovante de estudo em escola particular com bolsa integral'
            ).exists()
        ):
            criterio_selecionado = bolsa_integral_particular.first()
            pontuacao = criterio_selecionado.pontuacao
            pontuacao_total += pontuacao
            if criterio_selecionado.restritivo:
                self.possui_criterio_restritivo = True
            data[f'{CriterioSelecaoProgramaForm.BOLSA_INTEGRAL_ESCOLA_PART}'] = pontuacao

        particularidades_composicao_familiar = criterios_programa.filter(
            criterio=CriterioSelecaoProgramaForm.RECEBE_ACOMPANHAMENTO_NAPNE, opcao='Sim'
        )
        if (
            particularidades_composicao_familiar.exists()
            and InscricaoCaracterizacao.objects.filter(aluno=self.aluno, recebe_acompanhamento_napne=True).exists()
        ):
            criterio_selecionado = particularidades_composicao_familiar.first()
            pontuacao = criterio_selecionado.pontuacao
            pontuacao_total += pontuacao
            if criterio_selecionado.restritivo:
                self.possui_criterio_restritivo = True
            data[f'{CriterioSelecaoProgramaForm.RECEBE_ACOMPANHAMENTO_NAPNE}'] = pontuacao

        morou_orfanato = criterios_programa.filter(criterio=CriterioSelecaoProgramaForm.MOROU_ORFANATO, opcao=ultima_caracterizacao.morou_em_orfanato)
        if (
            morou_orfanato.exists()
            and DocumentoInscricaoAluno.objects.filter(
                aluno=self.aluno, validado=True, tipo_arquivo='Comprovante de que mora ou morou em abrigo institucional (orfanato)'
            ).exists()
        ):
            criterio_selecionado = morou_orfanato.first()
            pontuacao = criterio_selecionado.pontuacao
            pontuacao_total += pontuacao
            if criterio_selecionado.restritivo:
                self.possui_criterio_restritivo = True
            data[f'{CriterioSelecaoProgramaForm.MOROU_ORFANATO}'] = pontuacao

        if self.aluno.nacionalidade == 'Estrangeira':
            estrageiro_ou_refugiado = criterios_programa.filter(criterio=CriterioSelecaoProgramaForm.ESTRANGEIRO_REFUGIADO, opcao='Sim')
            sm = Decimal(Configuracao.get_valor_por_chave('comum', 'salario_minimo'))
            if estrageiro_ou_refugiado.exists() and (
                (self.aluno.caracterizacao.renda_bruta_familiar < sm)
                or DocumentoInscricaoAluno.objects.filter(
                    aluno=self.aluno, validado=True, tipo_arquivo='Comprovante de vinda para o país como refugiado'
                ).exists()
            ):
                criterio_selecionado = estrageiro_ou_refugiado.first()
                pontuacao = criterio_selecionado.pontuacao
                pontuacao_total += pontuacao
                if criterio_selecionado.restritivo:
                    self.possui_criterio_restritivo = True
                data[f'{CriterioSelecaoProgramaForm.ESTRANGEIRO_REFUGIADO}'] = pontuacao
        if self.aluno.forma_ingresso.is_acao_afirmativa_ou_programa_vagas():
            ingresso_por_cota = criterios_programa.filter(criterio=CriterioSelecaoProgramaForm.INGRESSO_COTA, opcao='Sim')
            if ingresso_por_cota.exists():
                criterio_selecionado = ingresso_por_cota.first()
                pontuacao = criterio_selecionado.pontuacao
                pontuacao_total += pontuacao
                if criterio_selecionado.restritivo:
                    self.possui_criterio_restritivo = True
                data[f'{CriterioSelecaoProgramaForm.INGRESSO_COTA}'] = pontuacao
        import json

        self.pontuacoes = json.dumps(data, ensure_ascii=False)
        self.pontuacao_total = pontuacao_total + self.pontuacao_especificidade
        self.pontuacao_criterios = pontuacao_total
        self.save()

    def get_renda_familiar_bruta_por_faixa(self):
        if self.inscricao.info_cadunico:
            return self.inscricao.info_cadunico['faixaRendaFamiliarTotal']['descricao']
        if self.renda_bruta:
            valor = Decimal(self.renda_bruta)
            sm = Decimal(Configuracao.get_valor_por_chave('comum', 'salario_minimo'))
            if valor <= sm:
                return self.ZERO_A_UM
            elif valor >= Decimal(sm + Decimal('0.01')) and valor <= Decimal(2 * sm):
                return self.UM_A_DOIS
            elif valor >= (Decimal(2 * sm) + Decimal('0.01')) and valor <= Decimal(3 * sm):
                return self.DOIS_A_TRES
            elif valor > Decimal(3 * sm):
                return self.MAIS_DE_TRES
        return self.ZERO_A_UM

    def get_renda_familiar_per_capita_por_faixa(self):
        if self.inscricao.info_cadunico:
            return self.inscricao.info_cadunico['faixaRendaFamiliarPerCapita']['descricao']

        if self.valor_renda_per_capita:
            valor = Decimal(self.valor_renda_per_capita)
            sm = Decimal(Configuracao.get_valor_por_chave('comum', 'salario_minimo'))
            if valor <= 109:
                return self.ZERO_A_109
            elif valor >= Decimal('109.01') and valor < Decimal(218):
                return self.DE_109_A_218
            elif valor >= Decimal('218.01') and valor < Decimal(sm / 2):
                return self.DE_218_A_MEIO_SM
            elif valor >= Decimal(sm / 2) and valor < Decimal(sm):
                return self.ENTRE_MEIO_E_UM_SM
            elif valor >= Decimal(sm) and valor < (Decimal('1.5') * sm):
                return self.ENTRE_UM_E_UM_MEIO_SM
            elif valor >= (Decimal('1.5') * sm) and valor < (Decimal(2) * sm):
                return self.ENTRE_UM_MEIO_E_DOIS_SM
            elif valor >= (Decimal(2) * sm):
                return self.SUPERIOR_2_SM
        return self.ZERO_A_109

    def possui_documento_caracterizacao_pendente_validacao(self):
        return DocumentoInscricaoAluno.objects.exclude(inscricao_caracterizacao=None).filter(aluno=self.aluno, validado=None).exists()

    def tem_bolsa_interna_externa(self):
        return self.inscricao.sub_instance() and self.inscricao.sub_instance().bolsas_internas_externas.exists()

    def quais_bolsas_interna_externa(self):
        return ', '.join([bolsa.descricao for bolsa in self.inscricao.sub_instance().bolsas_internas_externas.all()])

    def foi_analisada(self):
        return self.situacao_analise != AnaliseInscricao.SituacaoAnalise.NAO_ANALISADO

    def get_nome_aluno_sem_matricula(self):
        return f'{normalizar_nome_proprio(self.aluno.get_nome_social_composto())}'


class TipoBolsa(models.ModelPlus):
    descricao = models.CharFieldPlus('Descrição')

    class Meta:
        verbose_name = 'Tipo de Bolsa'
        verbose_name_plural = 'Tipos de Bolsas'

    def __str__(self):
        return self.descricao


class ImportacaoCadunico(models.ModelPlus):
    data_importacao = models.DateFieldPlus(verbose_name='Data da Importação', null=False, blank=False)
    atualizar_todos_alunos = models.BooleanField(
        verbose_name='Atualizar todos os alunos?', help_text='Caso marcado irá atuaizar as informação de todos os alunos matriculados', default=False
    )
    qtde_alunos_cadunico = models.IntegerFieldPlus(verbose_name='Quantidade de alunos com cadastro no CadÚnico', null=True)
    qtde_alunos_nao_cadunico = models.IntegerField(verbose_name='Quantidade de alunos sem cadastro no CadÚnico', null=True)
    execucao_concluida = models.BooleanField(verbose_name='Execução concluída?', default=False)
    usuario_criacao = models.ForeignKeyPlus(Vinculo, verbose_name='Usuário', on_delete=models.CASCADE)
    criado_em = models.DateTimeFieldPlus('Criado em', auto_now_add=True)

    class Meta:
        verbose_name = 'Importacão do CadÚnico'
        verbose_name_plural = 'Importações do CadÚnico'
        ordering = ['-data_importacao']

    def clean(self):
        if self.data_importacao and self.data_importacao < datetime.datetime.now().date():
            raise ValidationError('A data de importação não pode ser anterior à data atual.')

        if ImportacaoCadunico.objects.filter(data_importacao__gte=datetime.datetime.now().date(), execucao_concluida=False).exclude(id=self.pk):
            raise ValidationError('Já existe uma importação cadastrada que ainda não foi concluída.')


class AnaliseInscricaoAlimentacao(models.ModelPlus):
    analise = models.ForeignKeyPlus(AnaliseInscricao, verbose_name='Análise')
    solicitacao_cafe = models.ForeignKeyPlus(
        'ae.SolicitacaoAlimentacao', on_delete=models.CASCADE, verbose_name='Solicitação de Café', related_name='analiseinscricao_cafe'
    )
    solicitacao_almoco = models.ForeignKeyPlus(
        'ae.SolicitacaoAlimentacao', on_delete=models.CASCADE, verbose_name='Solicitação de Almoço', related_name='analiseinscricao_almoco'
    )
    solicitacao_janta = models.ForeignKeyPlus(
        'ae.SolicitacaoAlimentacao', on_delete=models.CASCADE, verbose_name='Solicitação de Jantar', related_name='analiseinscricao_janta'
    )

    class Meta:
        verbose_name = 'Análise da Inscrição em Alimentação Estudantil'
        verbose_name_plural = 'Análises das Inscrições em Alimentação Estudantil'

    def get_seg(self):
        texto = []
        if self.solicitacao_cafe.seg:
            texto.append('1C')
        if self.solicitacao_almoco.seg:
            texto.append('1A')
        if self.solicitacao_janta.seg:
            texto.append('1J')
        return ', '.join(texto)

    def get_ter(self):
        texto = []
        if self.solicitacao_cafe.ter:
            texto.append('1C')
        if self.solicitacao_almoco.ter:
            texto.append('1A')
        if self.solicitacao_janta.ter:
            texto.append('1J')
        return ', '.join(texto)

    def get_qua(self):
        texto = []
        if self.solicitacao_cafe.qua:
            texto.append('1C')
        if self.solicitacao_almoco.qua:
            texto.append('1A')
        if self.solicitacao_janta.qua:
            texto.append('1J')
        return ' '.join(texto)

    def get_qui(self):
        texto = []
        if self.solicitacao_cafe.qui:
            texto.append('1C')
        if self.solicitacao_almoco.qui:
            texto.append('1A')
        if self.solicitacao_janta.qui:
            texto.append('1J')
        return ' '.join(texto)

    def get_sex(self):
        texto = []
        if self.solicitacao_cafe.sex:
            texto.append('1C')
        if self.solicitacao_almoco.sex:
            texto.append('1A')
        if self.solicitacao_janta.sex:
            texto.append('1J')
        return ' '.join(texto)
