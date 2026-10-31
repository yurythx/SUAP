import operator
from functools import reduce

from django.db.models import Q
from django.urls import reverse

from agendamento.calendario import programacao_atual

#
from agendamento.models import SolicitacaoAgendamento
from comum.models import Vinculo

#
from djtools.db import models
from djtools.utils import get_datetime_now
from edu.models import Diario

#
from labvirtual.helpers import extrair_vinculos_do_diario
from labvirtual.perms import pode_gerenciar_solicitacao_labvirtual

from ..services import VMWareHorizonService
from .agendamento import AgendamentoLabVirtual
from .vdi import DesktopPool, VDIServer


class SolicitacaoLabVirtual(SolicitacaoAgendamento):
    laboratorio = models.ForeignKeyPlus(DesktopPool, verbose_name='Laboratório Físico', on_delete=models.CASCADE)
    diario = models.ForeignKeyPlus(Diario, null=True, blank=True, verbose_name='Diário', on_delete=models.CASCADE)
    membros = models.ManyToManyFieldPlus(Vinculo, verbose_name='Membros', related_name='%(app_label)s_%(class)s_membros')

    class Meta:
        verbose_name = 'Solicitação de Agendamento'
        verbose_name_plural = 'Solicitações de Agendamento'
        permissions = (('pode_avaliar_solicitacao_labvirtual', 'Pode avaliar solicitação reserva de Laboratório Virtual'),)

    class AgendamentoMeta:
        agendamento_model = AgendamentoLabVirtual
        reserva_model = DesktopPool
        reserva_field = 'laboratorio'

    @property
    def capacidade(self):
        return self.laboratorio.capacidade()

    @property
    def api(self) -> VMWareHorizonService:
        return VDIServer.get_active_endpoint()

    def get_absolute_url(self):
        return reverse('labvirtual:solicitacao_agendamento', kwargs={'pk': self.pk})

    def programacao(self, exibir_pendentes=True):
        return programacao_laboratorio(laboratorio=self.laboratorio, exibir_pendentes=exibir_pendentes)

    def tem_permissao_avaliar(self, user):
        tem_permissao = user.has_perm('labvirtual.pode_avalicar_solicitacao_labvirtual')
        return tem_permissao or pode_gerenciar_solicitacao_labvirtual(user, self.laboratorio)

    def pode_editar_membros(self):
        hoje = get_datetime_now()
        return not (self.finalizada or self.cancelada) and self.deferida and self.data_hora_fim > hoje

    def get_membros_status(self):
        membros_ativos = self.laboratorio.get_membros_ativos()
        membros = {}
        for vinculo in self.membros.all():
            username = vinculo.user.username
            membros[username] = {
                'id': vinculo.id,
                'matricula': username,
                'nome': vinculo.relacionamento,
                'tipo': vinculo.get_relacionamento_title(),
                'status': membros in membros_ativos,
            }
        return membros

    def deferir(self):
        membros = list(extrair_vinculos_do_diario(self.diario))
        membros.append(self.solicitante.get_vinculo())
        self.membros.set(membros)
        super().deferir()

    def cancelar(self):
        if self.pode_cancelar():
            super().cancelar()

    def finalizar(self):
        if self.pode_finalizar():
            super().finalizar()

    def adicionar_membro(self, membro):
        self.membros.add(membro)
        agendamento = self.get_agendamento_ativo()
        if agendamento:
            agendamento.adicionar_membros([membro])

    def remover_membro(self, membro):
        self.membros.remove(membro)
        agendamento = self.get_agendamento_ativo()
        if agendamento:
            agendamento.remover_membros([membro])

    def existem_vagas(self):
        return self.membros.count() < self.capacidade

    def pode_adicionar_membro(self):
        return self.pode_editar_membros() and self.existem_vagas()

    def eh_membro(self, vinculo):
        return self.membros.filter(id=vinculo.id).exists()


def programacao_laboratorio(laboratorio, solicitacao_atual=None, exibir_pendentes=True):
    if exibir_pendentes:
        qs_solicitacoes = SolicitacaoLabVirtual.objects.pendentes().filter(laboratorio=laboratorio)
    else:
        qs_solicitacoes = SolicitacaoLabVirtual.objects.none()
    #
    qs_reservas = AgendamentoLabVirtual.objects.filter(solicitacao__laboratorio=laboratorio)
    return programacao_atual(solicitacao_atual, qs_solicitacoes, qs_reservas)


def reservas_laboratorio(laboratorio, data_inicio, data_fim):
    """
    Retornas reservas (provinientes de uma solicitações atendidas ou de uma indisponibilização)
    que conflitam com os parâmetros passados
    """
    reservas = SolicitacaoLabVirtual.objects.deferidas().filter(laboratorio=laboratorio)
    q_filters = [
        # Remove as reservas que a data_fim vem antes da data_inicio da pesquisa
        Q(data_fim__lt=data_inicio) | Q(data_fim=data_inicio, hora_fim__lt=data_inicio.time()),
        Q(hora_fim__lt=data_inicio.time()),
        # Remove as reservas que a data_inicio vem depois da data_fim da pesquisa
        Q(data_inicio__gt=data_fim) | Q(data_inicio=data_fim, hora_inicio__gt=data_fim.time()),
        Q(hora_inicio__gt=data_fim.time()),
    ]
    reservas = reservas.exclude(reduce(operator.or_, q_filters))
    return reservas
