from datetime import timedelta

from django.db.models.query import QuerySet
from django_fsm import FSMIntegerField, transition

from comum.models import User, Vinculo
from djtools.db import models, transaction
from djtools.utils import get_datetime_now
from rh.models import Setor

from ..papeis import eh_auditor_chefe, tenho_poder_de_chefe


def get_default_ciencia_prazo():
    prazo = get_datetime_now() + timedelta(days=7)
    return prazo.date()


class CienciaStatus(models.IntegerChoices):
    STATUS_ESPERANDO = 1, 'Aguardando ciência'
    STATUS_CIENTE = 2, 'Ciente'
    STATUS_CONSIDERADO_CIENTE = 3, 'Considerado Ciente'
    STATUS_CANCELADA = 4, 'Cancelada'


class SolicitacaoCienciaQueryset(QuerySet):
    def pendentes(self):
        return self.filter(status=CienciaStatus.STATUS_ESPERANDO)

    def consideradas_cientes(self):
        return self.filter(status=CienciaStatus.STATUS_CONSIDERADO_CIENTE)


class SolicitacaoCienciaManager(models.Manager):
    def get_queryset(self):
        return SolicitacaoCienciaQueryset(self.model, using=self._db)

    def pendentes(self):
        return self.get_queryset().pendentes()

    def consideradas_cientes(self):
        return self.get_queryset().consideradas_cientes()


class SolicitacaoCiencia(models.ModelPlus):
    setor = models.ForeignKey(Setor, verbose_name='Setor de Destino', blank=False, null=False, on_delete=models.CASCADE)
    prazo_ciencia = models.DateFieldPlus(verbose_name='Data Limite para Ciência', default=get_default_ciencia_prazo)
    solicitado_por = models.CurrentUserField(verbose_name='Solicitado por', related_name='%(app_label)s_%(class)s_solicitado_por')
    respondido_por = models.ForeignKey(
        Vinculo, related_name='%(app_label)s_%(class)s_respondido_por', blank=True, null=True, on_delete=models.CASCADE
    )
    solicitado_em = models.DateTimeField(auto_now_add=True, verbose_name='Solicitado em')
    modificada_em = models.DateTimeField(auto_now=True, verbose_name='Modificada em')
    # Informações sobre o cancelamento
    cancelada_por = models.ForeignKeyPlus(Vinculo, related_name='%(app_label)s_%(class)s_cancelada_por', blank=True, null=True)
    justificativa_cancelamento = models.TextField(verbose_name='Justificativa do Cancelamento', blank=True, null=True)
    # Status da ciência
    status = FSMIntegerField(default=CienciaStatus.STATUS_ESPERANDO, choices=CienciaStatus.choices, protected=True)

    objects = SolicitacaoCienciaManager()

    class Meta:
        abstract = True

    @property
    def ciente(self):
        return self.status == CienciaStatus.STATUS_CIENTE

    @property
    def considerado_ciente(self):
        return self.status == CienciaStatus.STATUS_CONSIDERADO_CIENTE

    @property
    def expirada(self):
        today = get_datetime_now().date()
        return self.prazo_ciencia < today

    @property
    def esperando(self):
        return self.status == CienciaStatus.STATUS_ESPERANDO

    @property
    def esta_esperando_expirado(self):
        return self.esperando and self.expirada

    @property
    def esta_esperando_nao_expirado(self):
        return self.esperando and not self.expirada

    @property
    def cancelada(self):
        return self.status == CienciaStatus.STATUS_CANCELADA

    @property
    def concluida(self):
        return self.ciente or self.considerado_ciente

    @property
    def data_ciencia(self):
        return self.modificada_em if self.ciente else None

    @transition(field=status, source=CienciaStatus.STATUS_ESPERANDO, target=CienciaStatus.STATUS_CIENTE)
    def informar_ciencia(self, user):
        self.respondido_por = user.get_vinculo()

    @transition(field=status, source=CienciaStatus.STATUS_ESPERANDO, target=CienciaStatus.STATUS_CONSIDERADO_CIENTE)
    def considerar_ciente(self):
        pass

    @transition(field=status, source=[CienciaStatus.STATUS_ESPERANDO, CienciaStatus.STATUS_CIENTE], target=CienciaStatus.STATUS_CANCELADA)
    def cancelar(self, user, justificativa):
        self.cancelada_por = user.get_vinculo()
        self.justificativa_cancelamento = justificativa

    def pode_cancelar(self, user):
        return self.esperando and (user == self.solicitado_por) or eh_auditor_chefe(user)

    def pode_responder(self, user: User) -> bool:
        return tenho_poder_de_chefe(user, self.setor)

    @transaction.atomic()
    def atualizar_ciencia(self):
        if self.esta_esperando_expirado:
            self.considerar_ciente()
            self.save()

    def notificar_acesso(self, user):
        self.atualizar_ciencia()
        with transaction.atomic():
            if self.esperando and self.pode_responder(user):
                self.informar_ciencia(user)
                self.save()
