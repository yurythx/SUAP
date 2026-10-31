from django.urls import reverse

#
from agendamento.models import Agendamento
from agendamento.status import AgendamentoStatus
from djtools.db import models
from labvirtual.services import VMWareHorizonService

#
#
from .vdi import DesktopPool, VDIServer


class AgendamentoLabVirtual(Agendamento):
    solicitacao = models.ForeignKey('labvirtual.SolicitacaoLabVirtual', null=False, blank=False, on_delete=models.CASCADE)
    laboratorio = models.ForeignKey(DesktopPool, null=False, blank=False, on_delete=models.CASCADE)

    class Meta:
        verbose_name = 'Agendamento de Laboratório Virtual'
        verbose_name_plural = 'Agendamentos de Laboratórios Virtuais'

    @property
    def diario(self):
        return self.solicitacao.diario

    def get_absolute_url(self):
        return reverse('labvirtual:agendamento_labvirtual', kwargs={'pk': self.pk})

    #
    def possui_permissao(self):
        return True

    @property
    def api(self) -> VMWareHorizonService:
        return VDIServer.get_active_endpoint()

    def _adicionar_users(self, users):
        ad_users = self.api.get_ad_users_or_groups(users, group_only=False)
        self.api.assign_user_or_group_ids_to_desktop_pool(ad_users, self.laboratorio.desktop_pool_id)

    def _remover_users(self, users):
        ad_users = self.api.get_ad_users_or_groups(users, group_only=False)
        self.api.remove_user_or_group_ids_from_desktop_pool(ad_users, self.laboratorio.desktop_pool_id)

    def adicionar_membros(self, membros):
        if self.ativo:
            users = [membro.user.username for membro in membros if membro not in self.solicitacao.membros.all()]
            self._adicionar_users(users)

    def remover_membros(self, membros):
        if self.ativo:
            users = [membro.user.username for membro in membros if membro not in self.solicitacao.membros.all()]
            self._remover_users(users)

    #

    def ativar(self):
        users = [membro.user.username for membro in self.solicitacao.membros.all()]
        self._adicionar_users(users)
        super().ativar()

    def enviar_notificacao(self, msg='A sua sessão vai expirar em 5 minutos. Salve o seu trabalho.'):
        self.api.send_message_to_desktop_pool(self.laboratorio.desktop_pool_id, msg)

    def inativar(self):
        users = [membro.user.username for membro in self.solicitacao.membros.all()]
        self._remover_users(users)
        self.api.disconnect_sessions_from_desktop_pool(self.laboratorio.desktop_pool_id)
        super().inativar()

    def _finalizar_solicitacao(self):
        qs = AgendamentoLabVirtual.objects.filter(solicitacao=self.solicitacao)
        agendamentos = qs.exclude(id=self.id, status=AgendamentoStatus.STATUS_FINALIZADO)
        if not agendamentos.exists():
            self.solicitacao.finalizar()
            self.solicitacao.save()

    #
