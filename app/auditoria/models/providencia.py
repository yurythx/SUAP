import typing
from django.apps import apps
from django.db.models.query import QuerySet
from django.urls import reverse_lazy
from django_fsm import FSMIntegerField, transition

from comum.models import User, Vinculo
from djtools.db import models, transaction
from djtools.templatetags.filters.utils import format_profile
from djtools.utils import get_datetime_now
from rh.models import Setor, mark_safe

from ..papeis import eh_auditor, eh_auditor_chefe, tenho_poder_de_chefe

if typing.TYPE_CHECKING:
    from .monitoramento import Monitoramento


class SolicitacaoProvidenciaStatus(models.IntegerChoices):
    STATUS_ESPERANDO = 1, 'Aguardando ciência'
    STATUS_CIENTE = 2, 'Ciente'
    STATUS_CANCELADA = 3, 'Cancelada'
    STATUS_EXPIRADA = 4, 'Expirada'
    STATUS_FINALIZAR = 5, 'Finalizada'
    STATUS_AGUARDANDO_POSICIONAMENTO = 6, 'Aguardando Posicionamento'


class SolicitacaoProvidenciaQueryset(QuerySet):
    def get_model(self):
        return apps.get_model('auditoria', 'SolicitacaoProvidencia')

    def aguardando_ciencia(self):
        return self.filter(status=SolicitacaoProvidenciaStatus.STATUS_ESPERANDO)

    def aguardando_posicionamento(self):
        return self.filter(status=SolicitacaoProvidenciaStatus.STATUS_AGUARDANDO_POSICIONAMENTO)

    def expiradas(self):
        return self.filter(status=SolicitacaoProvidenciaStatus.STATUS_EXPIRADA)

    def canceladas(self):
        return self.filter(status=SolicitacaoProvidenciaStatus.STATUS_CANCELADA)

    def cientes(self):
        return self.filter(status=SolicitacaoProvidenciaStatus.STATUS_CIENTE)

    def ultima_solicitacao_por(self, object):
        qs = self.filter(monitoramento_id=object.id)
        return qs.order_by('-solicitado_em').first()


class SolicitacaoProvidenciaManager(models.Manager):
    def get_queryset(self):
        return SolicitacaoProvidenciaQueryset(self.model, using=self._db)

    def aguardando_ciencia(self):
        return self.get_queryset().aguardando_ciencia()

    def aguardando_posicionamento(self):
        return self.get_queryset().aguardando_posicionamento()

    def expiradas(self):
        return self.get_queryset().expiradas()

    def canceladas(self):
        return self.get_queryset().canceladas()

    def cientes(self):
        return self.get_queryset().cientes()

    def ultima_solicitacao_por(self, object):
        return self.get_queryset().ultima_solicitacao_por(object)


class SolicitacaoProvidencia(models.ModelPlus):
    monitoramento = models.ForeignKey('auditoria.Monitoramento', on_delete=models.CASCADE, verbose_name='monitoramento', related_name='solicitacoes')
    #
    modificada_em = models.DateTimeField(auto_now=True, verbose_name='Modificada em')
    # Dados do solicitante
    solicitado_por = models.CurrentUserField(verbose_name='Solicitado por', related_name='%(app_label)s_%(class)s_solicitado_por')
    solicitado_em = models.DateTimeField(auto_now_add=True, verbose_name='Solicitado em')
    motivo = models.TextField(verbose_name='Motivação da Solicitação', blank=False, null=False)

    # Dados do Setor solicitado
    setor = models.ForeignKey(Setor, verbose_name='Setor de Destino', blank=False, null=False, on_delete=models.CASCADE)
    respondido_por = models.ForeignKey(
        Vinculo, related_name='%(app_label)s_%(class)s_respondido_por', blank=True, null=True, on_delete=models.CASCADE
    )

    # Informações sobre o cancelamento/finalizacao
    encerrada_por = models.ForeignKeyPlus(Vinculo, related_name='%(app_label)s_%(class)s_encerrada_por', blank=True, null=True)
    justificativa = models.TextField(verbose_name='Justificativa', blank=True, null=True)

    # Status da ciência
    status = FSMIntegerField(default=SolicitacaoProvidenciaStatus.STATUS_ESPERANDO, choices=SolicitacaoProvidenciaStatus.choices, protected=True)

    # Prazo
    prazo_atendimento = models.DateFieldPlus(verbose_name='Prazo para atendimento')
    ultima_prorrogacao = models.ForeignKey('ProrrogacaoPrazo', on_delete=models.SET_NULL, null=True, blank=True, related_name='+')

    prazo_atual = models.DateFieldPlus(verbose_name='Prazo Atual', null=True, blank=True)

    objects = SolicitacaoProvidenciaManager()

    @property
    def ciente(self):
        return self.status == SolicitacaoProvidenciaStatus.STATUS_CIENTE

    @property
    def esperando(self):
        return self.status == SolicitacaoProvidenciaStatus.STATUS_ESPERANDO

    @property
    def cancelada(self):
        return self.status == SolicitacaoProvidenciaStatus.STATUS_CANCELADA

    @property
    def expirada(self):
        return self.status == SolicitacaoProvidenciaStatus.STATUS_EXPIRADA

    @property
    def aguardando_posicionamento(self):
        return self.status == SolicitacaoProvidenciaStatus.STATUS_AGUARDANDO_POSICIONAMENTO

    @property
    def finalizada(self):
        return self.status == SolicitacaoProvidenciaStatus.STATUS_FINALIZAR

    @property
    def ativa(self):
        return self.status in [
            SolicitacaoProvidenciaStatus.STATUS_ESPERANDO,
            SolicitacaoProvidenciaStatus.STATUS_CIENTE,
            SolicitacaoProvidenciaStatus.STATUS_AGUARDANDO_POSICIONAMENTO,
        ]

    @property
    def data_ciencia(self):
        return self.modificada_em if self.ciente else None

    @property
    def ultima_movimentacao_em(self):
        return self.enviada_em if self.manifestacoes.exists() else self.solicitado_em

    @property
    def status_display(self):
        self.atualizar_solicitacao()
        return self.get_status_display()

    @property
    def referencia(self) -> Monitoramento:
        return self.monitoramento

    def pode_expirar(self):
        return not self.aguardando_posicionamento

    def get_responsaveis_hoje(self):
        responsaveis = self.monitoramento.get_vinculos_chefes()
        return mark_safe(' '.join([format_profile(responsavel) for responsavel in responsaveis]))

    def manifestacoes_do_auditado(self):
        qs = self.manifestacoes.manifestacoes_do_auditado()
        return qs.nao_registradas()

    def manifestacoes_do_auditor(self):
        qs = self.manifestacoes.manifestacoes_auditoria()
        return qs.nao_registradas()

    def ultima_manifestacao(self):
        return self.manifestacoes.order_by('-id').first()

    def get_absolute_url(self):
        return reverse_lazy('auditoria:visualizar_solicitacao_providencia', kwargs={'solicitacao_id': self.pk})

    def pode_editar_como_auditor(self, user):
        return self.referencia.pode_editar(user)

    def pode_editar_como_auditado(self, user):
        sou_chefe = tenho_poder_de_chefe(user, self.setor)
        return sou_chefe and self.referencia.pode_receber_manifestacao()

    def get_prazo_atual(self):
        return self.ultima_prorrogacao.prazo if self.ultima_prorrogacao else self.prazo_atendimento

    def em_prazo_manifestacao(self):
        hoje = get_datetime_now().date()
        return hoje <= self.prazo_atual

    def prorrogar_prazo(self, prorrogacao):
        self.ultima_prorrogacao = prorrogacao
        self.save()

    def pode_visualizar_solicitante(self, user):
        return eh_auditor(user)

    def pode_editar(self, user):
        return (user == self.solicitado_por) or self.pode_editar_como_auditor(user)

    def pode_responder(self, user: User) -> bool:
        return tenho_poder_de_chefe(user, self.setor)

    def pode_remover(self, user):
        return eh_auditor_chefe(user) and not self.manifestacoes_do_auditado().exists()

    def pode_cancelar(self, user):
        if (self.cancelada or self.expirada or self.aguardando_posicionamento) or not self.pode_editar(user):
            return False
        return not self.manifestacoes.enviadas().exists()

    @transition(field=status, source=SolicitacaoProvidenciaStatus.STATUS_ESPERANDO, target=SolicitacaoProvidenciaStatus.STATUS_CIENTE)
    def informar_ciencia(self, user):
        self.respondido_por = user.get_vinculo()

    @transition(
        field=status, source=[SolicitacaoProvidenciaStatus.STATUS_AGUARDANDO_POSICIONAMENTO], target=SolicitacaoProvidenciaStatus.STATUS_CIENTE
    )
    def reabrir_para_ciencia(self):
        pass

    @transition(
        field=status,
        source=[SolicitacaoProvidenciaStatus.STATUS_ESPERANDO, SolicitacaoProvidenciaStatus.STATUS_CIENTE],
        target=SolicitacaoProvidenciaStatus.STATUS_EXPIRADA,
    )
    def expirar(self):
        pass

    @transition(
        field=status,
        source=[
            SolicitacaoProvidenciaStatus.STATUS_CIENTE,
            SolicitacaoProvidenciaStatus.STATUS_AGUARDANDO_POSICIONAMENTO,
            SolicitacaoProvidenciaStatus.STATUS_EXPIRADA,
        ],
        target=SolicitacaoProvidenciaStatus.STATUS_FINALIZAR,
    )
    def finalizar(self, user, justificativa):
        self.encerrada_por = user.get_vinculo()
        self.justificativa = justificativa

    @transition(field=status, source=SolicitacaoProvidenciaStatus.STATUS_CIENTE, target=SolicitacaoProvidenciaStatus.STATUS_AGUARDANDO_POSICIONAMENTO)
    def aguardar_posicionamento(self):
        pass

    @transition(
        field=status,
        source=[
            SolicitacaoProvidenciaStatus.STATUS_ESPERANDO,
            SolicitacaoProvidenciaStatus.STATUS_CIENTE,
            SolicitacaoProvidenciaStatus.STATUS_AGUARDANDO_POSICIONAMENTO,
            SolicitacaoProvidenciaStatus.STATUS_EXPIRADA,
        ],
        target=SolicitacaoProvidenciaStatus.STATUS_CANCELADA,
    )
    def cancelar(self, user, justificativa):
        self.encerrada_por = user.get_vinculo()
        self.justificativa = justificativa

    @transaction.atomic()
    def notificar_acesso(self, user):
        self.atualizar_solicitacao()
        if self.esperando and self.pode_responder(user):
            self.informar_ciencia(user)
            self.save()

    def atualizar_solicitacao(self):
        today = get_datetime_now().date()
        if (self.ciente or self.esperando) and self.prazo_atual < today:
            self.expirar()
            self.save()

    @transaction.atomic()
    def save(self, *args, **kwargs):
        is_new = self.pk is None
        super().save(*args, **kwargs)
        updated = is_new
        if is_new:
            self.prazo_atual = self.prazo_atendimento
            self.referencia.ultima_solicitacao = self
            self.referencia.save()
        else:
            novo_prazo = self.get_prazo_atual()
            if self.prazo_atual != novo_prazo:
                self.prazo_atual = novo_prazo
                updated = True

        if updated:
            super().save(update_fields=['prazo_atual'])
