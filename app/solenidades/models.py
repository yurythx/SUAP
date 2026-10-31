from datetime import date, datetime, timedelta

from dateutil.relativedelta import relativedelta
from django.conf import settings

from djtools.db import models
from djtools.html.calendarios import CalendarioPlus
from djtools.templatetags.filters.utils import format_datetime
from djtools.utils import send_notification


class AgendamentoSolenidade(models.ModelPlus):
    data = models.DateFieldPlus('Data')
    hora_inicio = models.TimeFieldPlus('Hora de Início')
    local = models.CharFieldPlus(verbose_name='Local')
    descricao = models.TextField('Descrição')
    representante = models.ForeignKeyPlus('rh.Servidor', null=True)
    solicitante = models.ForeignKeyPlus('comum.Vinculo', null=True, related_name='solicitante_agendamento_solenidade')
    data_solicitacao = models.DateTimeFieldPlus('Data da Solicitação', auto_now_add=True)
    cancelada = models.BooleanField('Cancelada', default=False)
    responsavel = models.ForeignKeyPlus('comum.Vinculo', null=True, related_name='responsavel_agendamento_solenidade')
    data_avaliacao = models.DateTimeFieldPlus('Data da Solicitação', null=True)
    deferida = models.BooleanField('Avaliada', null=True)

    class Meta:
        verbose_name = 'Agendamento de Solenidade'
        verbose_name_plural = 'Agendamento de Solenidades'
        ordering = ['data', 'hora_inicio']

    def get_data_hora_inicio(self):
        return datetime.combine(self.data, self.hora_inicio)

    def get_status(self):
        if self.deferida is True:
            return 'Deferida'
        elif self.deferida is False:
            return 'Indeferida'
        return None

    def enviar_notificacao_status(self):
        titulo = '[SUAP] Solicitação de Agendamento de Solenidade'
        texto = (
            '<h1><strong>Solicitação de agendamento de solenidade</strong></h1>'
            f'<p>A sua solicitação de agendamento de solenidade foi: <strong>{self.get_status()}</strong>.</p>'
            '<strong>Dados da Solicitação:</strong>'
            '<ul>'
            f'    <li><strong>Data</strong>: {format_datetime(self.data)}</li>'
            f'    <li><strong>Hora de início</strong>: {self.hora_inicio}</li>'
            f'    <li><strong>Local</strong>: {self.local}</li>'
            f'    <li><strong>Descrição</strong>: {self.descricao}</li>'
            '</ul>'
        )
        send_notification(titulo, texto, settings.DEFAULT_FROM_EMAIL, [self.solicitante])

    def enviar_notificacao_deferimento(self):
        titulo = '[SUAP] Agendamento de Solenidade'
        texto = (
            '<h1><strong>Agendamento de solenidade</strong></h1>'
            f'<p>Você tem uma solenidade agendada como Reitor/Representante.</p>'
            '<strong>Dados do agendamento:</strong>'
            '<ul>'
            f'    <li><strong>Data</strong>: {format_datetime(self.data)}</li>'
            f'    <li><strong>Hora de início</strong>: {self.hora_inicio}</li>'
            f'    <li><strong>Local</strong>: {self.local}</li>'
            f'    <li><strong>Descrição</strong>: {self.descricao}</li>'
            '</ul>'
        )
        send_notification(titulo, texto, settings.DEFAULT_FROM_EMAIL, [self.representante.get_vinculo()])

    def enviar_notificacao_mudanca_representante(self, representante_antigo, novo_representante):
        titulo = '[SUAP] Cancelamento de Agendamento de Solenidade'
        texto = (
            '<h1><strong>Cancelamento de agendamento de solenidade</strong></h1>'
            f'<p>Você foi desvinculado de solenidade agendada como Reitor/Representante.</p>'
            '<strong>Dados do agendamento:</strong>'
            '<ul>'
            f'    <li><strong>Data</strong>: {format_datetime(self.data)}</li>'
            f'    <li><strong>Hora de início</strong>: {self.hora_inicio}</li>'
            f'    <li><strong>Local</strong>: {self.local}</li>'
            f'    <li><strong>Descrição</strong>: {self.descricao}</li>'
            '</ul>'
        )
        send_notification(titulo, texto, settings.DEFAULT_FROM_EMAIL, [representante_antigo.get_vinculo()])

        self.enviar_notificacao_deferimento()

    @classmethod
    def programacao_atual(cls, agendamento_atual=None):
        def _get_descricao(agendamento, justificativa):
            hora_inicio = 'Início às {}'.format(agendamento.hora_inicio.strftime('%H:%M'))
            descricao = '<a href="/solenidades/ver_agendamento/{id}/"><strong>{horario}</strong> {justificativa}</a>'
            return descricao.format(id=agendamento.id, horario=hora_inicio, justificativa=justificativa)

        def _add_dia_cal(cal, agendamento, agenda_data, css, title):
            descricao = _get_descricao(agendamento, title)
            cal.adicionar_evento_calendario(agenda_data, agenda_data, descricao, css, title)

        def _add_agendamento_calendario(cal, agendamento):
            agenda_data = agendamento.data
            if agendamento.deferida:
                css = 'success'
                title = f'Agendada para <strong>{agendamento.representante}</strong> em <strong>{agendamento.local}</strong>'
            else:
                css = 'alert'
                title = f'Solicitada para <strong>{agendamento.local}</strong>'

            if agendamento_atual == agendamento:
                css = 'info'

            _add_dia_cal(cal, agendamento, agenda_data, css, title)

        # a partir do mês corrente
        data_agora = datetime.now()
        ano_corrente = data_agora.year
        mes_corrente = data_agora.month
        # ------------
        # até o mês do último agendamento que 'caia' pelo menos dentro do mês corrente

        qs_agendamento = cls.objects.exclude(deferida=False, cancelada=True)

        cal_meses = []

        cal = CalendarioPlus()
        cal.mostrar_mes_e_ano = True

        if qs_agendamento.exists():
            # pega data_fim do último agendamento
            data_fim = qs_agendamento.latest('data').data
            # o último agendamento deve 'cair' pelo menos dentro do mês corrente
            # (mes agenda >= mes corrente E ano agenda >= ano corrente) OU (ano agenda > ano corrente)
            # ex:
            #    mes/ano corrente = 10/2013
            #    mes/ano solicitacao   = 01/2014
            #    ** o mes da solicitacao é menor que o mês corrente (o teste (mes solicitacao >= mes corrente E ano solicitacao >= ano corrente) FALHA!!)
            #    ** porém, ano solicitacao é maior (por isso da necessidade do teste (ano solicitacao > ano corrente)
            if (data_fim.month >= mes_corrente and data_fim.year == ano_corrente) or (data_fim.year > ano_corrente):
                ultimo_ano = data_fim.year
                ultimo_mes = data_fim.month
                mes = mes_corrente  # inicializa mês
                for ano in range(ano_corrente, ultimo_ano + 1):
                    mes_final = 12  # por padrão
                    if ano == ultimo_ano:
                        mes_final = ultimo_mes
                    for imes in range(mes, mes_final + 1):
                        # Adição das agendamento
                        data_inicial = date(ano, imes, 1)
                        data_final = date(ano, imes, 1) + relativedelta(months=+1) - timedelta(1)
                        queryset_agendamento = qs_agendamento.filter(data__range=[data_inicial, data_final])
                        for agendamento in queryset_agendamento:
                            _add_agendamento_calendario(cal, agendamento)

                        cal_meses.append(cal.formato_mes(int(ano), int(imes)))
                        # -------------------
                    mes = 1  # reinicia mês (o ano subsequente deve começar por janeiro)

        if not cal_meses:
            ano = data_agora.year
            mes = data_agora.strftime('%m')
            cal_meses.append(cal.formato_mes(int(ano), int(mes)))

        return cal_meses  # lista de calendários formato mês

    def get_absolute_url(self):
        return f'/solenidades/ver_agendamento/{self.id}/'
