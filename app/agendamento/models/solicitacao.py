import calendar
from datetime import datetime, timedelta

#
from django.utils.safestring import mark_safe
from django_fsm import FSMIntegerField, transition
from model_utils.models import TimeStampedModel

# Local module imports
from agendamento.managers import SolicitacaoAgendamentoManager
from agendamento.status import AgendamentoStatus, SolicitacaoAgendamentoStatus

#
from djtools.db import models
from djtools.db.models import CurrentUserField
from djtools.utils import adicionar_mes, daterange, get_datetime_now

from .base import SolicitacaoMeta


class Recorrencia(TimeStampedModel):
    ##
    data_inicio = models.DateFieldPlus('Data de Início')
    hora_inicio = models.TimeFieldPlus('Hora de Início')
    data_fim = models.DateFieldPlus('Data de Fim')
    hora_fim = models.TimeFieldPlus('Hora de Fim')

    #
    recorrencia_segunda = models.BooleanField('Segunda', default=False)
    recorrencia_terca = models.BooleanField('Terça', default=False)
    recorrencia_quarta = models.BooleanField('Quarta', default=False)
    recorrencia_quinta = models.BooleanField('Quinta', default=False)
    recorrencia_sexta = models.BooleanField('Sexta', default=False)
    recorrencia_sabado = models.BooleanField('Sábado', default=False)
    recorrencia_domingo = models.BooleanField('Domingo', default=False)

    class Meta:
        abstract = True

    def get_periodo(self):
        datas = '{} a {}'.format(self.data_inicio.strftime('%d/%m/%Y'), self.data_fim.strftime('%d/%m/%Y'))
        horario = '{} - {}'.format(self.hora_inicio.strftime('%H:%M'), self.hora_fim.strftime('%H:%M'))
        if self.data_fim == self.data_inicio:
            datas = self.data_inicio.strftime('%d/%m/%Y')
        return f'{datas} | Horário: {horario}'

    def get_recorrencias(self):
        recorrencias = []
        if self.recorrencia_segunda:
            recorrencias.append('segunda')
        if self.recorrencia_terca:
            recorrencias.append('terca')
        if self.recorrencia_quarta:
            recorrencias.append('quarta')
        if self.recorrencia_quinta:
            recorrencias.append('quinta')
        if self.recorrencia_sexta:
            recorrencias.append('sexta')
        if self.recorrencia_sabado:
            recorrencias.append('sabado')
        if self.recorrencia_domingo:
            recorrencias.append('domingo')
        return ', '.join(recorrencias)

    def pode_ver(self):
        return True

    def get_data_hora_inicio(self, data=None):
        if not data:
            data = self.data_inicio
        return datetime.combine(data, self.hora_inicio)

    def get_data_hora_fim(self, data=None):
        if not data:
            data = self.data_fim
        return datetime.combine(data, self.hora_fim)

    def get_datas_solicitadas(self):
        """
        Retorna datas solicitadas em datetime como uma lista de tuplas, cada tupla contem o datetime inicio e o fim
        """
        primeira_data_adicionada = None
        qtd_dias_mes = []
        datas_solicitadas = []
        for index, data in enumerate(daterange(self.data_inicio, self.data_fim)):
            if datas_solicitadas:
                primeira_data_adicionada = datas_solicitadas[0][0].date()
            # pegar a quantidade do mês e decrementar
            qtd_dias = calendar.monthrange(data.year, data.month)[1]
            if [data.month, qtd_dias] not in qtd_dias_mes:
                qtd_dias_mes.append([data.month, qtd_dias])
            #
            quantidade_mes = 0
            for _mes, dias in qtd_dias_mes:
                if index - dias >= 0:
                    index -= dias
                    quantidade_mes += 1
                else:
                    break
            #
            if not primeira_data_adicionada or adicionar_mes(primeira_data_adicionada, quantidade_mes) <= data < adicionar_mes(
                primeira_data_adicionada, quantidade_mes
            ) + timedelta(7):
                #
                self.__adicionar_dia_recorrencia(datas_solicitadas, data)
        #
        return datas_solicitadas

    def __adicionar_dia_recorrencia(self, datas_solicitadas, data):
        """
        Adicionar a data na lista de datas_solicitadas com base na recorrencia
        """
        # data.weekday() = Monday is 0 and Sunday is 6
        SEGUNDA = 0
        TERCA = 1
        QUARTA = 2
        QUINTA = 3
        SEXTA = 4
        SABADO = 5
        DOMINGO = 6

        if self.recorrencia_segunda and data.weekday() == SEGUNDA:
            datas_solicitadas.append([self.get_data_hora_inicio(data), self.get_data_hora_fim(data)])
        if self.recorrencia_terca and data.weekday() == TERCA:
            datas_solicitadas.append([self.get_data_hora_inicio(data), self.get_data_hora_fim(data)])
        if self.recorrencia_quarta and data.weekday() == QUARTA:
            datas_solicitadas.append([self.get_data_hora_inicio(data), self.get_data_hora_fim(data)])
        if self.recorrencia_quinta and data.weekday() == QUINTA:
            datas_solicitadas.append([self.get_data_hora_inicio(data), self.get_data_hora_fim(data)])
        if self.recorrencia_sexta and data.weekday() == SEXTA:
            datas_solicitadas.append([self.get_data_hora_inicio(data), self.get_data_hora_fim(data)])
        if self.recorrencia_sabado and data.weekday() == SABADO:
            datas_solicitadas.append([self.get_data_hora_inicio(data), self.get_data_hora_fim(data)])
        if self.recorrencia_domingo and data.weekday() == DOMINGO:
            datas_solicitadas.append([self.get_data_hora_inicio(data), self.get_data_hora_fim(data)])


class SolicitacaoAgendamento(Recorrencia, metaclass=SolicitacaoMeta):
    status = FSMIntegerField(
        'Situação', default=SolicitacaoAgendamentoStatus.STATUS_ESPERANDO, choices=SolicitacaoAgendamentoStatus.STATUS_CHOICES, protected=True
    )
    # Dados do solicitante
    solicitante = models.CurrentUserField(related_name='%(app_label)s_%(class)s_solicitado_por')
    # Dados do avaliador
    avaliador = models.CurrentUserField(default=None, related_name='%(app_label)s_%(class)s_avaliado_por')
    data_avaliacao = models.DateTimeFieldPlus('Data da Avaliação', null=True)
    observacao_avaliador = models.TextField('Observação', blank=True)
    #  Dados do Cancelamento
    justificativa_cancelamento = models.TextField('Justificativa do Cancelamento', blank=True)
    cancelada_por = CurrentUserField(default=None)
    data_cancelamento = models.DateTimeFieldPlus('Data da Avaliação', null=True)
    #
    objects = SolicitacaoAgendamentoManager()

    class Meta:
        abstract = True

    @property
    def data_hora_inicio(self):
        return datetime.combine(self.data_inicio, self.hora_inicio)

    @property
    def data_hora_fim(self):
        return datetime.combine(self.data_fim, self.hora_fim)

    @property
    def deferida(self):
        return self.status == SolicitacaoAgendamentoStatus.STATUS_DEFERIDA

    @property
    def indeferida(self):
        return self.status == SolicitacaoAgendamentoStatus.STATUS_INDEFERIDA

    @property
    def pendente(self):
        return self.status == SolicitacaoAgendamentoStatus.STATUS_ESPERANDO

    @property
    def cancelada(self):
        return self.status == SolicitacaoAgendamentoStatus.STATUS_CANCELADA

    @property
    def finalizada(self):
        return self.status == SolicitacaoAgendamentoStatus.STATUS_FINALIZADO

    def get_descricao(self, horario, descricao=None):
        descricao = f'#{self.pk}: {self.solicitante}'
        return f'<p><strong>{horario}</strong> {descricao}</p>'

    def pode_editar(self, user):
        return self.pendente and self.tem_permissao_avaliar(user)

    def pode_avaliar(self):
        return self.pendente

    def pode_deferir(self):
        return (self.pendente and self.data_hora_inicio > datetime.now()) and not self.tem_conflito_reservas()

    def pode_cancelar(self):
        hoje = get_datetime_now()
        return (hoje < self.data_hora_fim and self.deferida) or (hoje > self.data_hora_inicio and self.pendente)

    def pode_finalizar(self):
        hoje = get_datetime_now()
        return (hoje > self.data_hora_fim) and self.deferida

    def get_formated_status(self):
        status = self.get_status_display()
        if self.deferida:
            retorno = f'<span class="status status-success">{status}</span>'
        elif self.pendente:
            retorno = f'<span class="status status-alter">{status}</span>'
        elif self.cancelada:
            retorno = f'<span class="status status-error">{status}</span>'
        else:
            retorno = f'<span class="status status-info">{status}</span>'
        return mark_safe(retorno)

    def get_agendamento_ativo(self):
        status = [AgendamentoStatus.STATUS_ATIVO]
        agendamento_model = SolicitacaoMeta.get_agendamento_model(self)
        return agendamento_model.objects.filter(solicitacao=self, status__in=status).first()

    ###
    @transition(
        field=status,
        source=SolicitacaoAgendamentoStatus.STATUS_ESPERANDO,
        target=SolicitacaoAgendamentoStatus.STATUS_DEFERIDA,
        permission=lambda instance, user: instance.tem_permissao_avaliar(user),
        conditions=[pode_deferir],
    )
    def deferir(self):
        agendamento_model = SolicitacaoMeta.get_agendamento_model(self)
        params = {SolicitacaoMeta.get_reserva_field(self): SolicitacaoMeta.get_reserva(self)}
        #
        for data_hora_inicio, data_hora_fim in self.get_datas_solicitadas():
            agendamento_model.objects.get_or_create(solicitacao=self, data_hora_inicio=data_hora_inicio, data_hora_fim=data_hora_fim, **params)

    @transition(
        field=status,
        source=SolicitacaoAgendamentoStatus.STATUS_ESPERANDO,
        target=SolicitacaoAgendamentoStatus.STATUS_INDEFERIDA,
        permission=lambda instance, user: instance.tem_permissao_avaliar(user),
        conditions=[pode_avaliar],
    )
    def indeferir(self):
        pass

    #
    @transition(
        field=status,
        source=[SolicitacaoAgendamentoStatus.STATUS_DEFERIDA, SolicitacaoAgendamentoStatus.STATUS_ESPERANDO],
        target=SolicitacaoAgendamentoStatus.STATUS_CANCELADA,
        permission=lambda instance, user: instance.tem_permissao_avaliar(user) or instance.solicitante == user,
        conditions=[pode_cancelar],
    )
    def cancelar(self):
        hoje = get_datetime_now()
        agendamento_model = SolicitacaoMeta.get_agendamento_model(self)
        agendamentos = agendamento_model.objects.filter(solicitacao=self).exclude(status=AgendamentoStatus.STATUS_ATIVO)
        agendamentos.filter(data_hora_inicio__gt=hoje).delete()

    #
    @transition(
        field=status,
        source=SolicitacaoAgendamentoStatus.STATUS_DEFERIDA,
        target=SolicitacaoAgendamentoStatus.STATUS_FINALIZADO,
        conditions=[pode_finalizar],
    )
    def finalizar(self):
        self.finalizar_agendamentos()

    #
    def finalizar_agendamentos(self):
        status = [AgendamentoStatus.STATUS_INATIVO]
        agendamento_model = SolicitacaoMeta.get_agendamento_model(self)
        agendamentos = agendamento_model.objects.filter(solicitacao=self, status__in=status)
        for agendamento in agendamentos:
            if agendamento.pode_finalizar():
                agendamento.finalizar()
                agendamento.save()

    def get_reservas(self, data_inicio, data_fim):
        """
        Retornas reservas (provinientes de uma solicitações atendidas ou de uma indisponibilização)
        que conflitam com os parâmetros passados
        """
        import operator
        from functools import reduce

        from django.db.models import Q

        #
        params = {SolicitacaoMeta.get_reserva_field(self): SolicitacaoMeta.get_reserva(self)}
        solicitacao_model = type(self)
        reservas = solicitacao_model.objects.deferidas().filter(**params)
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

    def tem_conflito_reservas(self):
        for [solicitacao_data_inicio, solicitacao_data_fim] in self.get_datas_solicitadas():
            reservas = self.get_reservas(solicitacao_data_inicio, solicitacao_data_fim)
            return reservas.exists()
        return False

    def tem_permissao_avaliar(self, user):
        raise NotImplementedError('O modelo deve implementar o método possui_permissao')
