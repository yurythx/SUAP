from collections import OrderedDict

from django.apps import apps
from django.contrib.contenttypes.fields import GenericRelation
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse_lazy
from django_fsm import FSMIntegerField, transition

from comum.models import Ano
from djtools.db import models, transaction
from djtools.utils import get_datetime_now
from rh.models import Setor

from ..papeis import eh_auditor_chefe, sou_chefe_auditoria_hoje
from .documento import Documento, DocumentoManager, DocumentoQueryset
from .nucleo import NucleoAuditoria
from .relatorio import Relatorio


class RecomendacaoStatus:
    """
    Situação das recomendações:
    Registrada: Recomendação inserida via Monitor, mas ainda sem informação de encaminhamento ao gestor.
                Pode ser excluída ou alterada até o momento de registro do envio.
    Monitorando: Recomendação encaminhada ao gestor e pendente de providências.
    Atendida:   Recomendação que teve posicionamento da CGU favorável à manifestação do gestor.
    Não Atendida: Recomendações que deixaram de ser monitoradas pela CGU, apesar de continuarem passíveis de implementação pelo gestor.
    Cancelada:   Recomendação cancelada pela CGU.
    Consolidada: Recomendações de uma mesma UG, de conteúdos idênticos, agrupadas com a finalidade de racionalizar os trabalhos de monitoramento.
    """

    REGISTRADA = 0
    EM_MONITORAMENTO = 1
    PARCIALMENTE_ATENDIDA = 2
    ATENDIDA = 3
    NAO_ATENDIDA = 4
    CANCELADA = 5
    EXPIRADA = 6
    CONSOLIDADA = 7

    CHOICES = {
        REGISTRADA: 'Registrada',
        EM_MONITORAMENTO: 'Em monitoramento',
        PARCIALMENTE_ATENDIDA: 'Parcialmente atendida',
        ATENDIDA: 'Atendida',
        NAO_ATENDIDA: 'Não atendida',
        CANCELADA: 'Cancelada',
        EXPIRADA: 'Expirada',
        CONSOLIDADA: 'Consolidada',
    }

    @staticmethod
    def get_status_description(status_code):
        # Return the description for the status code with a default of None if not found
        return RecomendacaoStatus.CHOICES.get(status_code, None)

    SITUACOES_FINAIS = [ATENDIDA, NAO_ATENDIDA]
    SITUACOES_INATIVAS = [CANCELADA, EXPIRADA, CONSOLIDADA]
    SITUACOES_EM_EXECUCAO = [EM_MONITORAMENTO, PARCIALMENTE_ATENDIDA]

    SITUACOES_FLUXO = OrderedDict()
    SITUACOES_FLUXO[REGISTRADA] = [CHOICES[REGISTRADA], 'info']
    SITUACOES_FLUXO[EM_MONITORAMENTO] = [CHOICES[EM_MONITORAMENTO], 'alert']
    SITUACOES_FLUXO[PARCIALMENTE_ATENDIDA] = [CHOICES[PARCIALMENTE_ATENDIDA], 'alert']
    SITUACOES_FLUXO[ATENDIDA] = [CHOICES[ATENDIDA], 'success']

    @staticmethod
    def get_fluxo(status):
        fluxo = list(RecomendacaoStatus.SITUACOES_FLUXO.items())
        if status == RecomendacaoStatus.NAO_ATENDIDA:
            item = [RecomendacaoStatus.CHOICES[status], 'alert']
            fluxo[RecomendacaoStatus.ATENDIDA] = (status, item)
        return fluxo

    @staticmethod
    def get_display_and_class(status):
        """
        Retorna um par (display, classe) para o status informado.
        """
        if status in RecomendacaoStatus.SITUACOES_FLUXO:
            # Se o status estiver no dicionário de fluxo, retorna o display e a classe correspondentes
            # ao status
            return RecomendacaoStatus.SITUACOES_FLUXO[status]

        if status in RecomendacaoStatus.SITUACOES_INATIVAS:
            return RecomendacaoStatus.CHOICES[status], 'alert'

        return (status, 'default')


class StatusQuerySet(models.QuerySet):
    def iniciadas(self):
        return self.exclude(status=RecomendacaoStatus.REGISTRADA)

    def em_monitoramento(self):
        return self.filter(status=RecomendacaoStatus.EM_MONITORAMENTO)

    def a_monitorar(self):
        return self.filter(status=RecomendacaoStatus.REGISTRADA)

    def em_execucao(self):
        return self.filter(status__in=RecomendacaoStatus.SITUACOES_EM_EXECUCAO)


class StatusManager(models.Manager):
    def get_queryset(self):
        return StatusQuerySet(self.model, using=self._db)

    def iniciadas(self):
        return self.get_queryset().iniciadas()

    def em_monitoramento(self):
        return self.get_queryset().em_monitoramento()

    def a_monitorar(self):
        return self.get_queryset().a_monitorar()

    def em_execucao(self):
        return self.get_queryset().em_execucao()


class RecomendacaoStatusMixin(models.ModelPlus):
    status = FSMIntegerField(
        default=RecomendacaoStatus.REGISTRADA, choices=RecomendacaoStatus.CHOICES.items(), protected=True, verbose_name='Situação'
    )
    #
    data_inicio = models.DateTimeField(verbose_name='Data de início do monitoramento', null=True, blank=True)
    data_conclusao = models.DateTimeField(verbose_name='Data de finalização do monitoramento', null=True, blank=True)

    objects = StatusManager()

    class Meta:
        abstract = True

    @property
    def registrada(self):
        return self.status == RecomendacaoStatus.REGISTRADA

    @property
    def em_monitoramento(self):
        return self.status == RecomendacaoStatus.EM_MONITORAMENTO

    @property
    def atendida(self):
        return self.status == RecomendacaoStatus.ATENDIDA

    @property
    def parcialmente_atendida(self):
        return self.status == RecomendacaoStatus.PARCIALMENTE_ATENDIDA

    @property
    def nao_atendida(self):
        return self.status == RecomendacaoStatus.NAO_ATENDIDA

    @property
    def cancelada(self):
        return self.status == RecomendacaoStatus.CANCELADA

    @property
    def consolidada(self):
        return self.status == RecomendacaoStatus.CONSOLIDADA

    @property
    def expirada(self):
        return self.status == RecomendacaoStatus.EXPIRADA

    @property
    def em_execucao(self):
        return self.status in RecomendacaoStatus.SITUACOES_EM_EXECUCAO

    @property
    def ativa(self):
        return self.status in [RecomendacaoStatus.REGISTRADA, RecomendacaoStatus.EM_MONITORAMENTO, RecomendacaoStatus.PARCIALMENTE_ATENDIDA]

    @property
    def inativa(self):
        return self.status in RecomendacaoStatus.SITUACOES_INATIVAS

    def verificar_expiracao_por_data(self, data_limite):
        if get_datetime_now().date() > data_limite:
            status = [
                RecomendacaoStatus.REGISTRADA,
                RecomendacaoStatus.EM_MONITORAMENTO,
                RecomendacaoStatus.PARCIALMENTE_ATENDIDA,
                RecomendacaoStatus.EXPIRADA,
            ]
            return self.status in status
        return False

    def pode_editar(self, user):
        raise NotImplementedError

    def get_progresso(self):
        ativos = self.monitoramentos.ativos().count()
        concluidos = self.monitoramentos.concluidos_ou_finalizados().count()
        if ativos:
            return float(concluidos * 100) / float(ativos)
        return 0

    @transition(
        field=status,
        source=[RecomendacaoStatus.REGISTRADA, RecomendacaoStatus.EXPIRADA],
        target=RecomendacaoStatus.REGISTRADA,
        permission=lambda instance, user: instance.pode_editar(user),
    )
    def registar(self):
        pass

    @transition(
        field=status,
        source=[RecomendacaoStatus.REGISTRADA, RecomendacaoStatus.EM_MONITORAMENTO],
        target=RecomendacaoStatus.EM_MONITORAMENTO,
        permission=lambda instance, user: instance.pode_editar(user),
    )
    def iniciar_monitoramento(self):
        self.data_inicio = get_datetime_now()

    @transition(
        field=status,
        source=[RecomendacaoStatus.EXPIRADA, RecomendacaoStatus.CANCELADA],
        target=RecomendacaoStatus.EM_MONITORAMENTO,
        permission=lambda instance, user: instance.pode_editar(user),
    )
    def reiniciar_monitoramento(self):
        for monitoramento in self.monitoramentos.cancelados():
            monitoramento.reiniciar()
            monitoramento.save()

    @transition(field=status, source=[RecomendacaoStatus.EM_MONITORAMENTO], target=RecomendacaoStatus.PARCIALMENTE_ATENDIDA)
    def marcar_como_parcialmente_atentida(self):
        pass

    @transition(
        field=status, source=[RecomendacaoStatus.EM_MONITORAMENTO, RecomendacaoStatus.PARCIALMENTE_ATENDIDA], target=RecomendacaoStatus.ATENDIDA
    )
    def marcar_como_atendida(self):
        self.data_finalizacao = get_datetime_now()

    @transition(
        field=status,
        source=[RecomendacaoStatus.EM_MONITORAMENTO, RecomendacaoStatus.PARCIALMENTE_ATENDIDA],
        target=RecomendacaoStatus.NAO_ATENDIDA,
    )
    def marcar_como_nao_atendida(self):
        self.data_finalizacao = get_datetime_now()

    @transition(field=status, source=[RecomendacaoStatus.REGISTRADA, RecomendacaoStatus.EM_MONITORAMENTO], target=RecomendacaoStatus.CONSOLIDADA)
    def consolidar(self):
        pass

    @transition(field=status, source=[RecomendacaoStatus.REGISTRADA, RecomendacaoStatus.EM_MONITORAMENTO], target=RecomendacaoStatus.CANCELADA)
    def cancelar(self):
        self.data_finalizacao = get_datetime_now()

    @transition(
        field=status,
        source=[
            RecomendacaoStatus.REGISTRADA,
            RecomendacaoStatus.EM_MONITORAMENTO,
            RecomendacaoStatus.PARCIALMENTE_ATENDIDA,
            RecomendacaoStatus.EXPIRADA,
        ],
        target=RecomendacaoStatus.EXPIRADA,
    )
    def expirar(self):
        pass

    def get_transition_to(self, user, target):
        transitions = list(self.get_available_user_status_transitions(user))
        for state_transition in transitions:
            if state_transition.target == target:
                transition_function = getattr(self, state_transition.name, None)
                return (state_transition.name, transition_function)
        return None

    def get_etapas(self, user):
        etapas = []
        for state_transition in self.get_available_user_status_transitions(user):
            if state_transition.target not in RecomendacaoStatus.SITUACOES_INATIVAS:
                etapas.append((state_transition.target, RecomendacaoStatus.CHOICES[state_transition.target]))
        return etapas


class RecomendacaoQuerySet(StatusQuerySet):
    def em_monitoramento(self):
        return self.filter(status=RecomendacaoStatus.EM_MONITORAMENTO)

    def concluidas(self):
        return self.filter(status__in=[RecomendacaoStatus.ATENDIDA, RecomendacaoStatus.NAO_ATENDIDA])


class RecomendacaoManager(StatusManager):
    def get_queryset(self):
        return RecomendacaoQuerySet(self.model, using=self._db)

    def em_monitoramento(self):
        return self.get_queryset().em_monitoramento()

    def concluidas(self):
        return self.get_queryset().concluidas()


class Recomendacao(RecomendacaoStatusMixin):
    SEARCH_FIELDS = ['numero', 'ano', 'identificador']

    # Identificador da recomendação
    numero = models.PositiveIntegerField(verbose_name='Número')
    ano = models.ForeignKeyPlus(Ano, verbose_name='Ano', null=False, blank=False, on_delete=models.CASCADE)

    # Dados do relatório que gerou a recomendação
    relatorio = models.ForeignKey(Relatorio, verbose_name='Relatório', on_delete=models.CASCADE, related_name='recomendacoes')

    # Dados da recomendação
    criada_em = models.DateTimeField(auto_now_add=True, verbose_name='Solicitado em')
    modificada_em = models.DateTimeField(auto_now=True, verbose_name='Modificada em')
    data_limite = models.DateFieldPlus(verbose_name='Data limite', null=True, blank=False)

    # Cancelamento/Consolidacao
    justificativa = models.TextField(verbose_name='Justificativa', null=True, blank=True)
    cancelada_por = models.ForeignKeyPlus(
        'comum.Vinculo', verbose_name='Cancelada por', null=True, related_name='%(app_label)s_%(class)s_cancelada_por'
    )

    # Dados do monitoramento
    monitor = models.ForeignKeyPlus('comum.Vinculo', verbose_name='Monitor', null=False, blank=False, related_name='%(app_label)s_%(class)s_monitor')
    nucleo = models.ForeignKey(NucleoAuditoria, verbose_name='Núcleo Executor', null=False, blank=False, on_delete=models.CASCADE)
    unidades = models.ManyToManyField(Setor, verbose_name='Setores monitorados', related_name='%(app_label)s_%(class)s_unidades')

    # Dados do Revisor
    revisor = models.ForeignKeyPlus('comum.Vinculo', verbose_name='Revisor', null=True, blank=True, related_name='%(app_label)s_%(class)s_revisor')

    comentarios = GenericRelation('auditoria.Comentario', related_query_name='comentarios')

    objects = RecomendacaoManager()

    class Meta:
        verbose_name = 'Recomendação'
        verbose_name_plural = 'Recomendações'
        unique_together = ('numero', 'ano')

    def __str__(self):
        return f'Recomendação {self.identificador}'

    def __repr__(self):
        return f'<Recomendação {self.identificador}: {self.descricao[:20]}...>'

    def get_absolute_url(self):
        return reverse_lazy('auditoria:visualizar_recomendacao', kwargs={'recomendacao_id': self.pk})

    @property
    def identificador(self):
        return f'{self.numero}/{self.ano}'

    @property
    def ano_relatorio(self):
        return self.relatorio.ano

    @property
    def acao(self):
        return self.relatorio.acao.nome

    @property
    def descricao(self):
        ultima_descricao = self.descricoes.first()
        return ultima_descricao.descricao if ultima_descricao else '-'

    def eh_revisor(self, user):
        return self.revisor == user.get_vinculo()

    def pode_editar(self, user):
        return sou_chefe_auditoria_hoje(user) or user.get_vinculo() == self.monitor

    def pode_adicionar_relatorios_auditoria(self, user):
        return self.ativa and self.pode_editar(user)

    def pode_comentar(self, user):
        return self.pode_editar(user) or user.get_vinculo() == self.revisor

    def pode_reiniciar(self, user):
        return self.cancelada and eh_auditor_chefe(user)

    def pode_revisar(self, user):
        """
        Verifica se o usuário pode revisar a descrição da recomendação.
        O usuário pode revisar se for o revisor da recomendação ou se for um auditor chefe.
        """
        return self.pode_editar(user) and self.em_execucao

    def pode_cancelar(self, user):
        if self.em_monitoramento and self.pode_editar(user):
            qs = self.monitoramentos.em_monitoramento().sem_pendencias()
            qs |= self.monitoramentos.registrados() | self.monitoramentos.cancelados()
            return qs.count() == self.monitoramentos.count()
        return False

    def pode_reativar(self, user):
        return self.inativa and eh_auditor_chefe(user)

    def pode_remover(self, user):
        if eh_auditor_chefe(user):
            qs = self.monitoramentos.registrados() | self.monitoramentos.cancelados()
            return qs.count() == self.monitoramentos.count()
        return self.pode_editar(user) and self.registrada

    def pode_iniciar_monitoramento(self, user):
        return self.pode_editar(user) and self.unidades_nao_monitoradas().exists()

    def pode_excluir_unidade(self, unidade):
        return not self.monitoramentos.filter(unidade=unidade).exists()

    def get_historico(self):
        return self.historicorecomendacao_set.all()

    def get_descricoes(self):
        return self.descricoes.all()

    def unidades_monitoradas(self):
        unidades_pks = self.monitoramentos.em_monitoramento().values_list('unidade', flat=True)
        return self.unidades.filter(id__in=unidades_pks)

    def unidades_nao_monitoradas(self):
        unidades_pks = self.monitoramentos.registrados().values_list('unidade', flat=True)
        return self.unidades.filter(id__in=unidades_pks)

    def unidades_com_monitoramento(self):
        unidades_pks = self.monitoramentos.values_list('unidade', flat=True)
        return self.unidades.filter(id__in=unidades_pks)

    def ano_atendimento(self):
        ultimo = self.monitoramentos.concluidos().order_by('data_conclusao').last()
        return ultimo.data_conclusao.year if ultimo else '-'

    def cancelar(self, cancelada_por, justificativa):
        super().cancelar()
        self.cancelada_por = cancelada_por.get_vinculo() if cancelada_por else None
        self.justificativa = justificativa

    def cancelar_monitoramentos(self):
        #
        monitoramentos = self.monitoramentos.em_monitoramento().union(self.monitoramentos.registrados())
        for monitoramento in monitoramentos:
            monitoramento.cancelar(self.cancelada_por.user, self.justificativa)
            monitoramento.save()

    def verificar_expiracao_por_data(self):
        return super().verificar_expiracao_por_data(self.data_limite)

    def _tratar_expiracao(self):
        """
        Marca a recomendação como expirada e salva a alteração.
        """
        pode_expirar = True
        monitoramentos = self.monitoramentos.em_monitoramento()
        for monitoramento in monitoramentos:
            if monitoramento.ultima_solicitacao.aguardando_posicionamento:
                pode_expirar = False
                break
        if pode_expirar:
            self.expirar()
            self.save()

    def _tratar_renovacao_prazo(self):
        if self.monitoramentos.registrados().count() == self.monitoramentos.count():
            self.registar()
        else:
            self.reiniciar_monitoramento()
        self.save()

    def verificar_expiracao(self):
        # Verifica se a recomendação expirou por decurso de prazo
        expirou_por_decurso_razo = self.verificar_expiracao_por_data()
        if expirou_por_decurso_razo and not self.expirada:
            self._tratar_expiracao()
        # Foi dado novo tempo para a recomendação, pois uma nova data limite foi
        # dada após a expiração
        elif not expirou_por_decurso_razo and self.expirada:
            self._tratar_renovacao_prazo()

    def pode_remover_documento(self, user):
        return self.pode_editar(user) and self.registrada

    def adicionar_documento(self, documento, user):
        content_type = ContentType.objects.get_for_model(documento)
        RecomendacaoDocumento.objects.get_or_create(
            recomendacao=self, object_id=documento.id, content_type=content_type, defaults={'incluido_por': user.get_vinculo(), 'object': documento}
        )

    def remover_documento(self, documento, user):
        content_type = ContentType.objects.get_for_model(documento)
        relatorio_documento = RecomendacaoDocumento.objects.filter(content_type=content_type, object_id=documento.id).first()
        if relatorio_documento:
            relatorio_documento.remover_documento(user)
            relatorio_documento.save()

    def has_changed(self, field_name):
        """
        Método auxiliar para detectar mudanças no campo especificado por field_name
        """
        if not self.pk:
            return False
        old_instance = self.__class__._default_manager.get(pk=self.pk)
        old_value = getattr(old_instance, field_name)
        return getattr(self, field_name) != old_value

    def handle_status_monitoramentos(self):
        if self.status in RecomendacaoStatus.SITUACOES_INATIVAS:
            return
        #
        em_monitoramento = self.monitoramentos.em_monitoramento().count()
        cancelados = self.monitoramentos.cancelados().count()
        concluidos = self.monitoramentos.concluidos().count()
        nao_atendidos = self.monitoramentos.finalizados().count()
        total_monitoramentos = self.monitoramentos.count()

        if self.registrada and em_monitoramento > 0:
            self.iniciar_monitoramento()
        elif self.em_monitoramento and cancelados == total_monitoramentos:
            self.cancelar(cancelada_por=None, justificativa='Todos os monitoramentos foram cancelados')
        elif (self.em_monitoramento or self.parcialmente_atendida) and em_monitoramento == 0 and nao_atendidos > 0:
            self.marcar_como_nao_atendida()
        elif (self.em_monitoramento or self.parcialmente_atendida) and (concluidos + cancelados) == total_monitoramentos:
            self.marcar_como_atendida()
        elif self.em_monitoramento and concluidos > 0:
            self.marcar_como_parcialmente_atentida()
        #
        if self.has_changed('status'):
            self.save()

    def beneficios(self):
        return self.monitoramentos.beneficios()

    def gerar_numeracao(self):
        hoje = get_datetime_now().date().year
        self.ano = Ano.objects.filter(ano=hoje).first()
        ultima_recomendacao = Recomendacao.objects.filter(ano=self.ano).order_by('-numero').first()
        self.numero = ultima_recomendacao.numero + 1 if ultima_recomendacao else 1

    def salvar_descricao(self, descricao):
        if self.registrada:
            DescricaoRecomendacao.objects.update_or_create(recomendacao=self, defaults={'descricao': descricao})

    @transaction.atomic()
    def save(self, *args, **kwargs):
        is_insert = not self.pk
        if is_insert:
            self.gerar_numeracao()
        elif self.cancelada and self.has_changed('status'):
            self.cancelar_monitoramentos()
        super().save(*args, **kwargs)


class DescricaoRecomendacao(models.Model):
    recomendacao = models.ForeignKey(Recomendacao, on_delete=models.CASCADE, related_name='descricoes')
    descricao = models.TextField(verbose_name='Descrição')
    cadastrado_por = models.CurrentUserField(verbose_name='Usuário')
    justificativa = models.TextField(null=True, blank=True)
    modificado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-modificado_em']

    def __str__(self):
        return self.descricao


class RecomendacaoDocumentoQueryset(DocumentoQueryset):
    def get_model(self):
        return apps.get_model('auditoria', 'ManifestacaoDocumento')


class RecomendacaoDocumentoManager(DocumentoManager):
    def get_queryset(self):
        return RecomendacaoDocumentoQueryset(self.model, using=self._db)


class RecomendacaoDocumento(Documento):
    recomendacao = models.ForeignKey(Recomendacao, on_delete=models.CASCADE, related_name='documentos')
    objects = RecomendacaoDocumentoManager()

    def __str__(self) -> str:
        return f'{self.object}'

    def pode_remover_documento(self, user):
        return not self.removido and self.recomendacao.pode_remover_documento(user)
