from django_fsm import FSMIntegerField, transition

from auditoria.papeis import eh_auditor
from comum.models import Vinculo
from djtools.db import models
from djtools.utils import get_datetime_now


class SolicitacaoStatus(models.IntegerChoices):
    STATUS_ESPERANDO = (
        0,
        'Aguardando',
    )
    STATUS_INDEFERIDA = 1, 'Indeferida'
    STATUS_DEFERIDA = 2, 'Deferida'
    STATUS_CANCELADA = 3, 'Cancelada'


class Solicitacao(models.ModelPlus):
    status = FSMIntegerField(default=SolicitacaoStatus.STATUS_ESPERANDO, choices=SolicitacaoStatus.choices, protected=True)
    # Dados da solicitação
    solicitante = models.CurrentUserField(related_name='%(app_label)s_%(class)s_solicitado_por')
    solicitado = models.ForeignKeyPlus('comum.Vinculo', related_name='%(app_label)s_%(class)s_solicitado_ao_vinculo')
    motivo = models.TextField('Motivo da Solicitação', blank=False, null=False)
    data_solicitacao = models.DateTimeField(auto_now_add=True)
    modificada_em = models.DateTimeField(auto_now=True)
    #
    cancelada_por = models.ForeignKeyPlus('comum.Vinculo', related_name='%(app_label)s_%(class)s_cancelada_pelo_vinculo', blank=True, null=True)
    justificativa = models.TextField('Justificativa', blank=True, null=True, help_text='Justificativa do cancelamento ou indeferimento')

    class Meta:
        abstract = True

    def pode_ver(self, user):
        return eh_auditor(user) or self.solicitado == user.get_vinculo()

    def pode_analisar(self, user):
        return self.em_espera() and self.solicitado == user.get_vinculo()

    def pode_cancelar(self, user):
        return self.em_espera() and self.solicitante == user

    def indeferida(self):
        return self.status == SolicitacaoStatus.STATUS_INDEFERIDA

    def deferida(self):
        return self.status == SolicitacaoStatus.STATUS_DEFERIDA

    def em_espera(self):
        return self.status == SolicitacaoStatus.STATUS_ESPERANDO

    def cancelada(self):
        return self.status == SolicitacaoStatus.STATUS_CANCELADA

    def eh_remetente(self, vinculo):
        return self.remetente_vinculo.get_cpf_ou_cnpj() == vinculo.get_cpf_ou_cnpj()

    def eh_solicitado(self, vinculo):
        return self.solicitado.get_cpf_ou_cnpj() == vinculo.get_cpf_ou_cnpj()

    @transition(field=status, source=SolicitacaoStatus.STATUS_ESPERANDO, target=SolicitacaoStatus.STATUS_CANCELADA)
    def cancelar(self, vinculo: Vinculo, justificativa: str):
        self.cancelada_por = vinculo
        self.justificativa = justificativa
        self.data_status = get_datetime_now()

    @transition(field=status, source=SolicitacaoStatus.STATUS_ESPERANDO, target=SolicitacaoStatus.STATUS_DEFERIDA)
    def deferir(self):
        self.data_status = get_datetime_now()

    @transition(field=status, source=SolicitacaoStatus.STATUS_ESPERANDO, target=SolicitacaoStatus.STATUS_INDEFERIDA)
    def indeferir(self):
        self.data_status = get_datetime_now()
