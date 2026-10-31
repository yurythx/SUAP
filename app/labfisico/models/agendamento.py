from django.urls import reverse

#
from agendamento.models import Agendamento
from agendamento.status import AgendamentoStatus
from djtools.db import models

#
from .guacamole import GuacamoleConnectionGroup


class AgendamentoLabFisico(Agendamento):
    solicitacao = models.ForeignKey('labfisico.SolicitacaoLabFisico', null=False, blank=False, on_delete=models.CASCADE)
    laboratorio = models.ForeignKey(GuacamoleConnectionGroup, null=False, blank=False, on_delete=models.CASCADE)

    class Meta:
        verbose_name = 'Agendamento de Laboratório Físico'
        verbose_name_plural = 'Agendamentos de Laboratórios Físicos'

    @property
    def diario(self):
        return self.solicitacao.diario

    def get_ldap_group(self):
        return self.laboratorio.ldap_group()

    def get_guacamole_group(self):
        return self.solicitacao.grupo_guacamole

    def get_absolute_url(self):
        return reverse('labfisico:agendamento_labfisico', kwargs={'pk': self.pk})

    #
    def possui_permissao(self):
        return True

    #
    def ativar(self):
        self.laboratorio.enable_guacamole_connections(user_group=self.get_guacamole_group())
        super().ativar()

    def inativar(self):
        self.laboratorio.disable_guacamole_connections(user_group=self.get_guacamole_group())
        super().inativar()

    def _finalizar_solicitacao(self):
        agendamentos = AgendamentoLabFisico.objects.filter(solicitacao=self.solicitacao)
        if not agendamentos.exclude(id=self.id, status=AgendamentoStatus.STATUS_FINALIZADO).exists():
            self.solicitacao.finalizar()
            self.solicitacao.save()

    #
    def delete(self, *args, **kwargs):
        # Encerra todas as sessões do Guacamole e remove as permissões
        if not self.existe_agendamentos():
            self.finalizar()
        super().delete(*args, **kwargs)
