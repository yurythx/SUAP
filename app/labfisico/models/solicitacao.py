import operator
from functools import reduce

from django.conf import settings
from django.db.models import Q
from django.urls import reverse

from agendamento.calendario import programacao_atual
from agendamento.models import SolicitacaoAgendamento
from comum.models import Vinculo
from djtools.db import models
from djtools.utils import get_datetime_now
from edu.models import Diario
from edu.models.alunos import Aluno
from labfisico.perms import pode_gerenciar_solicitacao_labfisico

from .agendamento import AgendamentoLabFisico
from .guacamole import GuacamoleConnectionGroup, remover_guacamole_user_from, remover_laboratorio_guacamole, sincronizar_laboratorio_guacamole

if 'ldap_backend' in settings.INSTALLED_APPS:
    from ldap_backend.models import LdapGroup
    from ldap_backend.services import adicionar_membros_ldap_group, remover_membero_ldap_group
    from ldap_backend.utils import extract_cn_from_ldap_user


class SolicitacaoLabFisico(SolicitacaoAgendamento):
    laboratorio = models.ForeignKeyPlus(GuacamoleConnectionGroup, verbose_name='Laboratório Físico', on_delete=models.CASCADE)
    diario = models.ForeignKeyPlus(Diario, null=True, blank=True, verbose_name='Diário', on_delete=models.CASCADE)
    # membros do grupo
    membros = models.ManyToManyFieldPlus(Vinculo, verbose_name='Membros', related_name='%(app_label)s_%(class)s_membros')

    class Meta:
        verbose_name = 'Solicitação de Agendamento'
        verbose_name_plural = 'Solicitações de Agendamento'
        permissions = (('pode_avaliar_solicitacao_labfisico', 'Pode avaliar solicitação reserva de Laboratório Físico'),)

    class AgendamentoMeta:
        agendamento_model = AgendamentoLabFisico
        reserva_model = GuacamoleConnectionGroup
        reserva_field = 'laboratorio'

    @property
    def grupo_guacamole(self):
        return f'{self.laboratorio.connection_group_name}_{self.pk}'

    @property
    def ldap_group_name(self):
        return self.laboratorio.connection_group_name

    @property
    def capacidade(self):
        return self.laboratorio.connections_count()

    def __str__(self) -> str:
        return f'#{self.pk}'

    def get_absolute_url(self):
        return reverse('labfisico:solicitacao_agendamento', kwargs={'pk': self.pk})

    def eh_membro(self, username):
        return self.membros.filter(user__username=username).exists()

    def lotado(self):
        return self.membros.count() >= self.capacidade

    def existem_vagas(self):
        return self.membros.count() < self.capacidade

    def get_alunos(self):
        alunos = [membro for membro in self.membros if membro.eh_aluno()]
        return Aluno.objects.filter(vinculo__in=alunos)

    def get_membros(self):
        return self.membros.all()

    def get_ldap_group(self):
        return self.laboratorio.ldap_group()

    def programacao(self, exibir_pendentes=True):
        return programacao_laboratorio(laboratorio=self.laboratorio, exibir_pendentes=exibir_pendentes)

    def tem_permissao_avaliar(self, user):
        tem_permissao = user.has_perm('labfisico.pode_avalicar_solicitacao_labfisico')
        return tem_permissao or pode_gerenciar_solicitacao_labfisico(user, self.laboratorio)

    def pode_editar_membro(self):
        hoje = get_datetime_now()
        return not (self.finalizada or self.cancelada or self.indeferida) and self.data_hora_fim > hoje

    def pode_adicionar_membro(self):
        return self.pode_editar_membro() and self.existem_vagas()

    def pode_deferir(self):
        if self.laboratorio.is_sync_ldap():
            return super().pode_deferir()
        return False

    def pode_avaliar(self, user):
        if super().pode_avaliar():
            return user.has_perm('labfisico.pode_avaliar_solicitacao_labfisico')
        return False

    def deferir(self):
        ldap_group = self.laboratorio.ldap_group()
        if ldap_group:
            usuarios = [membro.user.username for membro in self.membros.all()]
            adicionar_membros_ldap_group(ldap_group, usuarios)
            sincronizar_laboratorio_guacamole(self.grupo_guacamole, usuarios)
            super().deferir()
        else:
            raise Exception('AD não sincronizado.')

    def cancelar(self):
        if self.pode_cancelar():
            self._cleanup()
            super().cancelar()

    def _cleanup(self):
        self._remover_ldap_group()
        remover_laboratorio_guacamole(self.grupo_guacamole)

    def _remover_ldap_group(self):
        LdapGroup.objects.filter(sAMAccountName=self.ldap_group_name).delete()

    def finalizar(self):
        if self.pode_finalizar():
            self._cleanup()
            super().finalizar()

    def adicionar_membro(self, membro):
        if self.existem_vagas():
            ldap_group = self.laboratorio.ldap_group()
            vinculo = Vinculo.objects.get(user__username=membro)
            adicionar_membros_ldap_group(ldap_group, [membro])
            sincronizar_laboratorio_guacamole(self.grupo_guacamole, [membro])
            self.membros.add(vinculo)
            return True
        return False

    def remover_membro(self, membro):
        ldap_group = self.laboratorio.ldap_group()
        vinculo = Vinculo.objects.get(user__username=membro)
        remover_membero_ldap_group(ldap_group, [membro])
        remover_guacamole_user_from(self.grupo_guacamole, [membro])
        self.membros.remove(vinculo)
        #
        participacoes = SolicitacaoLabFisico.objects.deferidas().filter(membros__id=membro.id).exclude(id=self.id)
        if not participacoes.exists():
            remover_membero_ldap_group(ldap_group, membro)
        #

    #
    def get_alunos_no_diario(self):
        return self.diario.get_alunos_ativos() if self.diario else []

    def matriculas_no_diario(self):
        if self.diario:
            alunos = self.diario.get_alunos_ativos()
            return alunos.values_list('matricula_periodo__aluno__matricula', flat=True)
        return []

    def matriculas_no_ldap(self):
        group_ldap = self.laboratorio.ldap_group()
        if group_ldap:
            return [extract_cn_from_ldap_user(member) for member in group_ldap.member]
        return []

    def get_alunos_status(self):
        matriculas = self.matriculas_no_ldap()
        alunos = {}
        for membro in self.membros.all():
            if membro.eh_aluno():
                username = membro.user.username
                alunos[username] = {'matricula': username, 'nome': membro.relacionamento, 'status': username in matriculas}
        return alunos

    def get_membros_status(self):
        matriculas = self.matriculas_no_ldap()
        membros = {}
        for vinculo in self.membros.all():
            username = vinculo.user.username
            membros[username] = {
                'id': vinculo.id,
                'matricula': username,
                'nome': vinculo.relacionamento,
                'tipo': vinculo.get_relacionamento_title(),
                'status': username in matriculas,
            }
        return membros

    def delete(self, *args, **kwargs):
        #
        remover_laboratorio_guacamole(self.grupo_guacamole)
        return super().delete(*args, **kwargs)


def programacao_laboratorio(laboratorio, solicitacao_atual=None, exibir_pendentes=True):
    if exibir_pendentes:
        qs_solicitacoes = SolicitacaoLabFisico.objects.pendentes().filter(laboratorio=laboratorio)
    else:
        qs_solicitacoes = SolicitacaoLabFisico.objects.none()
    #
    qs_reservas = AgendamentoLabFisico.objects.filter(solicitacao__laboratorio=laboratorio)
    return programacao_atual(solicitacao_atual, qs_solicitacoes, qs_reservas)


def reservas_laboratorio(laboratorio, data_inicio, data_fim):
    """
    Retornas reservas (provinientes de uma solicitações atendidas ou de uma indisponibilização)
    que conflitam com os parâmetros passados
    """
    reservas = SolicitacaoLabFisico.objects.deferidas().filter(laboratorio=laboratorio)
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
