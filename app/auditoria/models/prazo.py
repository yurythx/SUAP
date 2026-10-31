from django.apps import apps
from django.db.models.query import QuerySet
from django.utils.safestring import mark_safe
from django_fsm import FSMIntegerField, transition

from djtools.db import models, transaction

from .providencia import SolicitacaoProvidencia


class ProrrogacaoPrazoQueryset(QuerySet):
    def get_model(self):
        return apps.get_model('auditoria', 'ProrrogacaoPrazo')

    def em_analise(self):
        return self.filter(status=StatusProrrogacao.PENDENTE)

    def indeferidas(self):
        return self.filter(status=StatusProrrogacao.REJEITADA)

    def deferidas(self):
        return self.filter(status=StatusProrrogacao.APROVADA)


class ProrrogacaoPrazoManager(models.Manager):
    def get_queryset(self):
        return ProrrogacaoPrazoQueryset(self.model, using=self._db)

    def em_analise(self):
        return self.get_queryset().em_analise()

    def indeferidas(self):
        return self.get_queryset().indeferidas()

    def deferidas(self):
        return self.get_queryset().deferidas()


class StatusProrrogacao(models.IntegerChoices):
    PENDENTE = 1, 'Pendente'
    APROVADA = 2, 'Aprovada'
    REJEITADA = 3, 'Rejeitada'


class ProrrogacaoPrazo(models.Model):
    manifestacao = models.OneToOneField('auditoria.Manifestacao', on_delete=models.CASCADE, related_name='prorrogacao')
    posicionamento = models.OneToOneField('auditoria.Posicionamento', on_delete=models.CASCADE, related_name='prorrogacao', null=True, blank=True)
    prazo_solicitado = models.DateFieldPlus(verbose_name='Prazo Solicitado')
    prazo = models.DateFieldPlus(
        verbose_name='Prazo Aceito', null=True, blank=True
    )  # Nova data aceita pelo auditor, pode ser diferente da solicitada
    criado_em = models.DateTimeFieldPlus(auto_now_add=True)
    status = FSMIntegerField(default=StatusProrrogacao.PENDENTE, choices=StatusProrrogacao.choices, protected=True)

    @property
    def deferida(self):
        return self.status == StatusProrrogacao.APROVADA

    @property
    def indeferida(self):
        return self.status != StatusProrrogacao.REJEITADA

    @property
    def pendente(self):
        return self.status != StatusProrrogacao.PENDENTE

    @property
    def solicitacao_providencia(self) -> SolicitacaoProvidencia:
        return self.manifestacao.solicitacao_providencia

    def get_formated_status(self):
        status = self.get_status_display()
        if self.deferida:
            retorno = f'<span class="status status-success">{status}</span>'
        elif self.pendente:
            retorno = f'<span class="status status-alter">{status}</span>'
        else:
            retorno = f'<span class="status status-error">{status}</span>'
        return mark_safe(retorno)

    def has_changed(self, field_name):
        """
        Método auxiliar para detectar mudanças no campo especificado por field_name
        """
        if not self.pk:
            return False
        old_instance = self.__class__._default_manager.select_for_update().get(pk=self.pk)
        old_value = getattr(old_instance, field_name)
        return getattr(self, field_name) != old_value

    @transition(field=status, source=StatusProrrogacao.PENDENTE, target=StatusProrrogacao.APROVADA)
    def deferir(self, posicionamento, nova_data=None):
        self.posicionamento = posicionamento
        self.prazo = nova_data or self.prazo_solicitado

    @transition(field=status, source=StatusProrrogacao.PENDENTE, target=StatusProrrogacao.REJEITADA)
    def indeferir(self, posicionamento):
        self.posicionamento = posicionamento

    def notify_manifestacao(self, publicado_por=None, reabrir=True):
        """
        Notifica a manifestação associada sobre a prorrogação de prazo.
        """
        self.posicionamento.notify_manifestacao(publicado_por=publicado_por, reabrir=reabrir)

    @transaction.atomic()
    def save(self, *args, **kwargs):
        has_changed = self.has_changed('status')
        super().save(*args, **kwargs)
        if has_changed and self.deferida:
            self.solicitacao_providencia.prorrogar_prazo(self)
            self.notify_manifestacao(publicado_por=self.posicionamento.publicado_por, reabrir=self.deferida)
