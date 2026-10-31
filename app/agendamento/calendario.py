from datetime import date, datetime

from dateutil.relativedelta import relativedelta

from djtools.html.calendarios import CalendarioPlus


def definir_data_fim(qs_solicitacoes, qs_reservas):
    # pega data_fim do último agendamento
    if not qs_solicitacoes:
        data_fim = qs_reservas.latest('solicitacao__data_fim').data_fim
    elif not qs_reservas:
        data_fim = qs_solicitacoes.latest('data_fim').data_fim
    else:
        data_fim_solicitacao = qs_solicitacoes.latest('data_fim').data_fim
        data_fim_reserva = qs_reservas.latest('solicitacao__data_fim').data_fim
        data_fim = data_fim_solicitacao
        if data_fim_reserva > data_fim_solicitacao:
            data_fim = data_fim_reserva
        #
    return data_fim


def adicionar_solicitoes(cal, qs_solicitacoes, solicitacao_atual, ano, mes):
    for solicitacao in qs_solicitacoes:
        for [agenda_data_inicio, agenda_data_fim] in solicitacao.get_datas_solicitadas():
            solicitacao_conflito = solicitacao.tem_conflito_reservas()
            if agenda_data_inicio.year == ano and agenda_data_inicio.month == mes:
                title = f'Solicitação de {solicitacao.solicitante.get_relacionamento()}'
                if solicitacao_conflito:
                    css = 'error' if (solicitacao_atual == solicitacao) else 'conflito'
                else:
                    css = 'info' if (solicitacao_atual == solicitacao) else 'alert'
                #
                horario = '{} às {}'.format(agenda_data_inicio.strftime('%H:%M'), agenda_data_fim.strftime('%H:%M'))
                descricao = solicitacao.get_descricao(horario)
                cal.adicionar_evento_calendario(agenda_data_inicio, agenda_data_fim, descricao, css, title)
    #
    return cal


def adicionar_reservas(cal, qs_reservas, solicitacao_atual, ano, mes):
    data_inicial = date(ano, mes, 0o1)
    data_final = date(ano, mes, 0o1) + relativedelta(months=+1)
    qs_reservas_inicio = qs_reservas.filter(solicitacao__data_inicio__range=[data_inicial, data_final])
    qs_reservas_fim = qs_reservas.filter(solicitacao__data_fim__range=[data_inicial, data_final])
    queryset_reservas = qs_reservas_inicio | qs_reservas_fim
    for reserva in queryset_reservas:
        agenda_data_inicio = reserva.data_hora_inicio
        agenda_data_fim = reserva.data_hora_fim
        #
        solicitacao = reserva.solicitacao
        css = 'evento' if (solicitacao_atual and solicitacao == solicitacao_atual) else 'success'
        title = f'Agendada para {solicitacao.solicitante.get_relacionamento()}'
        horario = '{} às {}'.format(agenda_data_inicio.strftime('%H:%M'), agenda_data_fim.strftime('%H:%M'))
        descricao = solicitacao.get_descricao(horario)
        cal.adicionar_evento_calendario(agenda_data_inicio, agenda_data_fim, descricao, css, title)
    #
    return cal


def montar_calendario(solicitacao_atual, qs_solicitacoes, qs_reservas, data_agora, data_fim):
    cal = CalendarioPlus()
    cal.mostrar_mes_e_ano = True
    #
    ano_corrente = data_agora.year
    mes_corrente = data_agora.month
    #
    ultimo_ano = data_fim.year
    ultimo_mes = data_fim.month

    mes = mes_corrente  # inicializa mês
    cal_meses = []
    for ano in range(ano_corrente, ultimo_ano + 1):
        mes_final = ultimo_mes if ano == ultimo_ano else 12
        #
        for imes in range(mes, mes_final + 1):
            cal = adicionar_solicitoes(cal, qs_solicitacoes, solicitacao_atual, ano, imes)
            cal = adicionar_reservas(cal, qs_reservas, solicitacao_atual, ano, imes)
            cal_meses.append(cal.formato_mes(ano, imes))
        #
        mes = 1  # reinicia mês (o ano subsequente deve começar por janeiro)

    #
    return cal_meses


def programacao_atual(solicitacao_atual, qs_solicitacoes=None, qs_reservas=None):
    # a partir do mês corrente
    data_agora = datetime.now()
    ano_corrente = data_agora.year
    mes_corrente = data_agora.month
    cal_meses = []
    # ------------
    # até o mês do último agendamento que 'caia' pelo menos dentro do mês corrente
    if qs_solicitacoes or qs_reservas:
        # pega data_fim do último agendamento
        data_fim = definir_data_fim(qs_solicitacoes, qs_reservas)
        #
        if (data_fim.year == ano_corrente and data_fim.month >= mes_corrente) or (data_fim.year > ano_corrente):
            cal_meses = montar_calendario(solicitacao_atual, qs_solicitacoes, qs_reservas, data_agora, data_fim)
    #
    return cal_meses
