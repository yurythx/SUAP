from dateutil.relativedelta import relativedelta
from django.db.models.aggregates import Count, Sum

from djtools.templatetags.filters import format_money
from djtools.utils import daterange
from licenca_capacitacao.models import (
    CalculoAquisitivoUsofrutoServidorEdital,
    CalculosGeraisServidorEdital,
    CodigoAfastamentoCapacitacao,
    CodigoAfastamentoNaoContabilizaExercicio,
    EditalLicCapacitacao,
    LicCapacitacaoPorDia,
    PedidoLicCapacitacao,
    PeriodoPedidoLicCapacitacao,
    ServidorComplementar,
    ServidorDataInicioExercicioAjustada,
    SolicitacaoAlteracaoDataInicioExercicio,
)
from rh.models import ServidorAfastamento


def get_datetime_now():
    try:
        from django.utils import timezone

        return timezone.now()
    except ImportError:
        from datetime import datetime

        return datetime.now()


def get_servidor_afastamento_todos_siape_suap(servidor):
    """
    APENAS LICENCA CAPACITACAO
    Retorna todos os afastamentos do servidor
    - CONSIDERANDO PARCELAS JA APROVADAS (EM CARÁTER DEFINITIVO OU DE FORMA PRELIMINAR)
      E AS EFETIVADAS NO SIAPE
    """

    # - SIAPE
    codigos_lc = EditalLicCapacitacao.get_todos_os_codigos_licenca_capacitacao()
    lista_afastamentos_siape = list(
        ServidorAfastamento.objects.filter(servidor=servidor, afastamento__codigo__in=codigos_lc, cancelado=False)
        .extra(select={'tipo': "'SIAPE'"})
        .values_list('data_inicio', 'data_termino')
    )

    # - SUAP - Nao cadastrados no SIAPE E Aprovado de forma definitiva no resultado final
    lista_afastamentos_suap = list(
        PeriodoPedidoLicCapacitacao.objects.filter(
            pedido__servidor=servidor, pedido__cadastrado_no_siape=False, pedido__aprovado_em_definitivo=True, pedido__cancelado_pela_gestao=False
        )
        .extra(select={'tipo': "'SUAP'"})
        .values_list('data_inicio', 'data_termino')
    )

    lista = lista_afastamentos_siape + lista_afastamentos_suap

    return sorted(lista, key=lambda x: x[0])


def get_servidor_afastamento_nao_conta_como_efet_exerc(servidor, di, dt, entre_periodos=False, todos=False):
    # Afastamentos que nao contam como efetivo exercício

    codigos = list(CodigoAfastamentoNaoContabilizaExercicio.objects.all().values_list('codigo__codigo', flat=True))

    if entre_periodos:
        afast = ServidorAfastamento.objects.filter(
            servidor=servidor,
            afastamento__codigo__in=codigos,
            cancelado=False,
        )

        afast = afast.filter(data_inicio__range=[di, dt]) | afast.filter(data_termino__range=[di, dt])

        return afast

    if todos:
        afast = ServidorAfastamento.objects.filter(
            servidor=servidor,
            afastamento__codigo__in=codigos,
            cancelado=False,
        )
        return afast

    return ServidorAfastamento.objects.filter(
        servidor=servidor,
        afastamento__codigo__in=codigos,
        data_inicio__gte=di,
        data_termino__lte=dt,
        cancelado=False,
    )


def get_qtd_dias_servidor_afastamento_nao_conta_como_efet_exerc(servidor, di, dt, calcula_final_real=False):
    afastamentos = get_servidor_afastamento_nao_conta_como_efet_exerc(servidor, di, dt)
    if calcula_final_real:
        afastamentos = get_servidor_afastamento_nao_conta_como_efet_exerc(servidor, None, None, todos=True)

    """
    if afastamentos:
        qtd = 0
        for af in afastamentos:
            qtd += af.get_qtde_dias().days + 1
        return qtd
    return 0
    """

    if afastamentos:
        final_em_na_pratica = None
        qtd = 0
        for afast in afastamentos:
            if calcula_final_real:
                # se ainda iniciou dentro continua contando
                if final_em_na_pratica:
                    if afast.data_inicio in daterange(di, final_em_na_pratica):
                        qtd += afast.get_qtde_dias().days + 1
                    else:
                        break
                else:
                    if afast.data_inicio in daterange(di, dt):
                        qtd += afast.get_qtde_dias().days + 1
                final_em = (di + relativedelta(years=5)) - relativedelta(days=1)
                final_em_na_pratica = final_em + relativedelta(days=qtd)
            else:
                qtd += afast.get_qtde_dias().days + 1
        return qtd
    return 0


def get_servidor_qtd_dias_afastamento_capacitacao(servidor, edital):
    """
    Qtd de dias de AFASTAMENTO CAPACITACAO
    Erasmo na demanda 736:
      Além do '0028', '0061' incluir os códigos 11, 12 e 13 também pois tratam dos
      afastamentos fora do país.
    """

    # Códigos da configuracao
    codigos = list(CodigoAfastamentoCapacitacao.objects.all().values_list('codigo__codigo', flat=True))

    afasts = ServidorAfastamento.objects.filter(servidor=servidor, afastamento__codigo__in=codigos, cancelado=False)
    # if afasts:
    #    return afasts.aggregate(qtd=Sum('quantidade_dias_afastamento'))['qtd'] + 1
    # return 0
    if afasts:
        qtd = 0
        for af in afasts:
            qtd += af.get_qtde_dias().days + 1
        return qtd
    return 0


def get_idade_servidor_inicio_abrangencia_edital(edital, servidor):
    # Idade do servidor
    dt_nascimento = servidor.pessoa_fisica.nascimento_data
    dt_inicio_abrangencia_edital = edital.periodo_abrangencia_inicio
    return relativedelta(dt_inicio_abrangencia_edital, dt_nascimento).years


def get_categoria_servidor_edital(edital, servidor):
    categoria = None
    if servidor.eh_tecnico_administrativo:
        categoria = 'tecnico_administrativo'
    elif servidor.eh_docente:
        categoria = 'docente'
    else:
        s = ServidorComplementar.objects.filter(edital=edital, servidor=servidor)
        if s:
            if s[0].categoria == 'docente':
                categoria = 'docente'
            if s[0].categoria == 'tecnico_administrativo':
                categoria = 'tecnico_administrativo'
    return categoria


def get_todos_periodos_dos_pedidos_do_edital(edital, servidor):
    # Todos as parcelas cadastradas pelo servidor no edital
    return PeriodoPedidoLicCapacitacao.objects.filter(pedido__edital=edital, pedido__servidor=servidor)


def get_todos_periodos_dos_pedidos_nao_cancelados_do_edital(edital, servidor):
    # Todos as parcelas NAO CANCELADAS cadastradas pelo servidor no edital
    return get_todos_periodos_dos_pedidos_do_edital(edital, servidor).exclude(pedido__situacao=PedidoLicCapacitacao.CANCELADO)


def get_todos_periodos_do_pedido(pedido):
    # Todos as parcelas cadastradas pelo servidor em um pedido
    return PeriodoPedidoLicCapacitacao.objects.filter(pedido=pedido).order_by('data_inicio')


def get_qtd_dias_pedido_capacitacao(pedido):
    # Qtd de dias de todas as parcelas cadastradas no pedido
    periodo_pedido = get_todos_periodos_do_pedido(pedido)
    return periodo_pedido.aggregate(qtd=Sum('qtd_dias_total'))['qtd']


def get_inicio_servico_publico(solicitacao_valida, data_ajustada, servidor):
    parametro_inicio_exercicio = None
    data_inicio_servico_publico = None

    # A solicitacao_valida é uma Solicitação que ainda não foi analisada
    if solicitacao_valida:
        # 1
        parametro_inicio_exercicio = CalculosGeraisServidorEdital.INICIO_EXERCICIO_SOLICITADA
        data_inicio_servico_publico = solicitacao_valida[0].data_solicitada
    elif data_ajustada:
        # 2
        parametro_inicio_exercicio = CalculosGeraisServidorEdital.INICIO_EXERCICIO_AJUSTADA_PELA_GESTAO
        data_inicio_servico_publico = data_ajustada
    elif not servidor.data_inicio_servico_publico:
        # 3
        parametro_inicio_exercicio = CalculosGeraisServidorEdital.INICIO_EXERCICIO_INSTITUICAO
        data_inicio_servico_publico = servidor.data_inicio_exercicio_na_instituicao
    elif servidor.data_inicio_servico_publico == servidor.data_inicio_exercicio_na_instituicao:
        # 4
        parametro_inicio_exercicio = CalculosGeraisServidorEdital.INICIO_SERVICO_PUBLICO
        data_inicio_servico_publico = servidor.data_inicio_servico_publico
    elif ((servidor.data_inicio_exercicio_na_instituicao - servidor.data_inicio_servico_publico).days + 1) <= 15:
        # 5
        parametro_inicio_exercicio = CalculosGeraisServidorEdital.INICIO_SERVICO_PUBLICO
        data_inicio_servico_publico = servidor.data_inicio_servico_publico
    else:
        # 6
        parametro_inicio_exercicio = CalculosGeraisServidorEdital.INICIO_EXERCICIO_INSTITUICAO
        data_inicio_servico_publico = servidor.data_inicio_exercicio_na_instituicao

    return parametro_inicio_exercicio, data_inicio_servico_publico


def calcular_periodo_aquisito_usofruto(edital, servidor):
    """
    # Conforme NT 3/2019 - DIGPE/RE/IFRN
    # https://portal.ifrn.edu.br/servidores/edital-licenca-para-capacitacao/edital-no-03-2019-2014-submissao-de-pedidos-de-licenca-para-capacitacao-dos-servidores-do-ifrn/documentos-publicados/nota-tecnica-no-3-2019
    #
    # Art. 3º O PERÍODO AQUISITIVO corresponde a cada quinquênio de efetivo exercício no serviço
    #   público federal. Assim sendo, o servidor só poderá usufruir da licença para capacitação,
    #   por até três meses, após completar cada quinquênio de efetivo exercício.
    #   Parágrafo único. Os 90 (noventa) dias a que o servidor faz jus, a cada período quinquenal,
    #     para licença para capacitação, não são acumuláveis, devendo o início do usufruto
    #     acontecer até o término do quinquênio subsequente, de modo que após iniciado não haja
    #     interrupções.
    #
    # DA APURAÇÃO DO PERÍODO AQUISITIVO
    # Art. 4º Os períodos aquisitivos quinquenais para a licença para capacitação são computados:
    #   I - a partir da data do exercício, após a posse no cargo efetivo, para os servidores
    #      admitidos a partir de 15 de outubro de 1996;
    #   II - para os servidores admitidos anteriormente a 15 de outubro de 1996, é resguardado o
    #      direito ao cômputo do tempo de serviço residual existente em 15 de outubro de 1996,
    #      não utilizado no gozo da licença prêmio por assiduidade, observada a prescrição
    #      quinquenal para o usufruto (art. 7º da Lei nº 9.527, de 10/12/1997).
    #
    # Art. 5º Não são computados como de efetivo exercício: os dias de faltas não justificadas,
    #    bem como os afastamentos e licenças sem remuneração previstos na legislação pertinente do
    #    serviço público federal.
    #
    # Art. 6º A legislação não impõe o cumprimento de cinco anos ininterruptos de efetivo
    #    exercício e nem que seja no mesmo cargo.
    #    § 1º Havendo uma interrupção no exercício, a contagem do tempo do período aquisitivo
    #       para fins da licença para capacitação continuará sendo computada após o retorno do
    #       servidor às suas atividades.
    #
    # Art. 7º Os dias usufruídos para licença para capacitação são considerados como de efetivo
    #    exercício e computados para todos os efeitos legais.

    # ------------------------------------
    # Determinar o inicio do EXERCICIO no servico publico federal
    # ------------------------------------
    # Usa um dos dois campos de servidor
    # - data_inicio_servico_publico
    # - data_inicio_exercicio_na_instituicao
    # Como calcular (conforme DIGPE)
    #   - A regra que eu usei foi essa, por ordem de verificação do sistema:
    #     - 1- Se o servidor já indicou a correção e a COADPE confirmou no sistema,
    #       vale essa informação de data de início de exercício;
    #     - Se não,
    #     - 2- Se o campo do SUAP "DATA_INICIO_SERVICO_PUBLICO" estiver em branco,
    #       vale a data do campo "DATA_INICIO_EXERCICIO_NA_INSTITUICAO";
    #     - Se não,
    #     - 3- Se o campo do SUAP "DATA_INICIO_SERVICO_PUBLICO" é igual ao campo
    #       "DATA_INICIO_EXERCICIO_NA_INSTITUICAO", vale a mesma data;
    #     - Se não,
    #     - 4- Se a data do campo do SUAP "DATA_INICIO_EXERCICIO_NA_INSTITUICAO"
    #       menos (-) a data do campo "DATA_INICIO_SERVICO_PUBLICO" é igual ou
    #       menor (=<) que 15 dias, vale a data do campo "DATA_INICIO_SERVICO_PUBLICO";
    #     - Se não,
    #     - 5- Se a data do campo do SUAP "DATA_INICIO_EXERCICIO_NA_INSTITUICAO"
    #       menos (-) a data do campo "DATA_INICIO_SERVICO_PUBLICO" é maior (>) que 15 dias,
    #       vale a data do campo "DATA_INICIO_EXERCICIO_NA_INSTITUICAO".
    #
    # RESUMO
    # 1 - Busca nas datas ajustadas
    # 2 - Busca na solicitacao de ajuste
    # 3 - Se nao houver DATA_INICIO_SERVICO_PUBLICO fica a DATA_INICIO_EXERCICIO_NA_INSTITUICAO
    # 4 - Se DATA_INICIO_SERVICO_PUBLICO == DATA_INICIO_EXERCICIO_NA_INSTITUICAO
    #     fica a DATA_INICIO_SERVICO_PUBLICO
    # 5 - Se (DATA_INICIO_EXERCICIO_NA_INSTITUICAO - DATA_INICIO_SERVICO_PUBLICO) <= 15
    #     fica a DATA_INICIO_SERVICO_PUBLICO
    # 6 - ELSE fica a DATA_INICIO_EXERCICIO_NA_INSTITUICAO
    """

    parametro_inicio_exercicio = 0

    # Solicitação que ainda não foi analisada
    solicitacao_valida = SolicitacaoAlteracaoDataInicioExercicio.objects.filter(servidor=servidor, edital=edital, situacao__isnull=True)

    # Data já ajustada (cadastrada diretamente pela gestão ou por uma
    #   SolicitacaoAlteracaoDataInicioExercicio já analisada)
    data_ajustada = ServidorDataInicioExercicioAjustada.get_data_ajustada(servidor)

    parametro_inicio_exercicio, data_inicio_servico_publico = get_inicio_servico_publico(solicitacao_valida, data_ajustada, servidor)

    """
    Determinar os dias EXERCICIO do servidor (TEMPO BRUTO) sem contabilizar os descontos
    """
    qtd_dias_exercicio = 0
    if data_inicio_servico_publico:
        qtd_dias_exercicio = get_datetime_now().date() - data_inicio_servico_publico
        qtd_dias_exercicio = qtd_dias_exercicio.days + 1

    """
    Determinar a quantidade de dias de afastamentos e licenças sem remuneração previstos na
      legislação pertinente do serviço público federal
    Será utilizado na contabilização da quantidade de dias de exercício liquido do servidor
    """
    qtd_dias_afastado_com_interrompe_tempo_servico = 0
    if data_inicio_servico_publico:
        afastamentos = get_servidor_afastamento_nao_conta_como_efet_exerc(
            servidor, data_inicio_servico_publico, get_datetime_now(), entre_periodos=True
        )
        for afast in afastamentos:
            # qtd_dias_afastado_com_interrompe_tempo_servico += (afast.data_termino - afast.data_inicio).days
            qtd_dias_afastado_com_interrompe_tempo_servico += afast.quantidade_dias_afastamento + 1

    """
    Determinar a quantidade de dias de efetivo EXERCICIO do servidor (TEMPO LIQUIDO)
    """
    qtd_dias_efetivo_exercicio = qtd_dias_exercicio - qtd_dias_afastado_com_interrompe_tempo_servico

    """
    Salvando os dados do exercicio
    """
    if data_inicio_servico_publico:
        CalculosGeraisServidorEdital.objects.filter(edital=edital, servidor=servidor).delete()
        c_exercicio = CalculosGeraisServidorEdital()
        c_exercicio.servidor = servidor
        c_exercicio.edital = edital
        c_exercicio.inicio_exercicio = data_inicio_servico_publico
        c_exercicio.qtd_dias_exercicio = qtd_dias_exercicio
        c_exercicio.qtd_dias_afast_nao_conta_como_efet_exerc = qtd_dias_afastado_com_interrompe_tempo_servico
        c_exercicio.qtd_dias_efet_exercicio = qtd_dias_efetivo_exercicio
        c_exercicio.qtd_dias_afast_capacitacao = get_servidor_qtd_dias_afastamento_capacitacao(servidor, edital)
        c_exercicio.parametro_inicio_exercicio = parametro_inicio_exercicio
        c_exercicio.idade_servidor_inicio_abrangencia_edital = get_idade_servidor_inicio_abrangencia_edital(edital, servidor)
        c_exercicio.categoria_servidor = get_categoria_servidor_edital(edital, servidor)
        c_exercicio.save()

    """
    Calcula a qtd de dias de cada um dos periodos solicitados (TODOS, inclusive os cancelados)
    """
    todos_periodo = get_todos_periodos_dos_pedidos_do_edital(edital, servidor)
    todos_periodo.update(qtd_dias_total=0)
    for p in todos_periodo:
        p.qtd_dias_total = (p.data_termino - p.data_inicio).days + 1
        p.save()

    """
    Quinquenios
    - Periodo aquisitivo
    Como apurar
    primeiros 5 anos
      inicio_em = inicio_do_exercicio
      final_em = inicio_em + 5 anos
      final_em_na_pratica = final_em + interrupcoes_do_periodo
    proximos 5 anos
      inicio_em = final_em_na_pratica
      final_em = inicio_em + 5 anos
      final_em_na_pratica = final_em + interrupcoes_do_periodo
    FORMA SOLICITADA PELA DIGPE
    - Cômputo dos períodos aquisitivos, conforme exemplo abaixo:
      - Período 1
        - Início 16/02/2012
        - Término em 15/02/2017
      - Período 2
        - Início em 16/02/2017
        - Término em 15/02/2022
      - Os interstícios aquisitivos iniciam sempre no mesmo dia.
    """

    # Essa linha eh necessaria para evitar cascade de CalculoAquisitivoUsofrutoServidorEdital com PeriodoPedidoLicCapacitacao
    PeriodoPedidoLicCapacitacao.objects.filter(pedido__edital=edital, pedido__servidor=servidor).update(aquisitivo_uso_fruto=None)

    CalculoAquisitivoUsofrutoServidorEdital.objects.filter(edital=edital, servidor=servidor).delete()

    if data_inicio_servico_publico:
        # Calcula os primeiros 5 anos
        # ----------------------------
        # Calcula
        inicio_em = data_inicio_servico_publico
        final_em = (inicio_em + relativedelta(years=5)) - relativedelta(days=1)
        # qtd_dias_afast_quinq = relativedelta(days=get_qtd_dias_servidor_afastamento_nao_conta_como_efet_exerc(servidor, inicio_em, final_em)).days
        qtd_dias_afast_quinq = get_qtd_dias_servidor_afastamento_nao_conta_como_efet_exerc(servidor, inicio_em, final_em, calcula_final_real=True)
        final_em_na_pratica = final_em + relativedelta(days=qtd_dias_afast_quinq)

        #
        # Salva
        c_aquisitivo = CalculoAquisitivoUsofrutoServidorEdital()
        c_aquisitivo.servidor = servidor
        c_aquisitivo.edital = edital
        c_aquisitivo.periodo = 1
        c_aquisitivo.inicio_aquisitivo = inicio_em
        c_aquisitivo.final_aquisitivo_teorico = final_em
        c_aquisitivo.qtd_dias_afast_nao_conta_como_efet_exerc = qtd_dias_afast_quinq
        c_aquisitivo.final_aquisitivo_na_patrica = final_em_na_pratica
        c_aquisitivo.save()

        # Calcula os proximos quinquenios (considerando que ja calculou os primeiros 5 anos)
        # ----------------------------
        quinq = 2
        while final_em_na_pratica <= get_datetime_now().date():
            # Forma solicitada pela DIGPE
            inicio_em = final_em_na_pratica + relativedelta(days=1)
            final_em = (inicio_em + relativedelta(years=5)) - relativedelta(days=1)
            # qtd_dias_afast_quinq = relativedelta(days=get_qtd_dias_servidor_afastamento_nao_conta_como_efet_exerc(servidor, inicio_em, final_em)).days
            qtd_dias_afast_quinq = get_qtd_dias_servidor_afastamento_nao_conta_como_efet_exerc(servidor, inicio_em, final_em, calcula_final_real=True)
            final_em_na_pratica = final_em + relativedelta(days=qtd_dias_afast_quinq)

            #
            # Salva
            c_aquisitivo = CalculoAquisitivoUsofrutoServidorEdital()
            c_aquisitivo.servidor = servidor
            c_aquisitivo.edital = edital
            c_aquisitivo.periodo = quinq
            c_aquisitivo.inicio_aquisitivo = inicio_em
            c_aquisitivo.final_aquisitivo_teorico = final_em
            c_aquisitivo.qtd_dias_afast_nao_conta_como_efet_exerc = qtd_dias_afast_quinq
            c_aquisitivo.final_aquisitivo_na_patrica = final_em_na_pratica
            c_aquisitivo.save()

            quinq += 1

        # Quinquenios a cumprir
        # ----------------------------
        # Forma solicitada pela DIGPE
        inicio_em = final_em_na_pratica + relativedelta(days=1)
        final_em = (inicio_em + relativedelta(years=5)) - relativedelta(days=1)
        # qtd_dias_afast_quinq = relativedelta(days=get_qtd_dias_servidor_afastamento_nao_conta_como_efet_exerc(servidor, inicio_em, final_em)).days
        qtd_dias_afast_quinq = get_qtd_dias_servidor_afastamento_nao_conta_como_efet_exerc(servidor, inicio_em, final_em, calcula_final_real=True)
        final_em_na_pratica = final_em + relativedelta(days=qtd_dias_afast_quinq)

        #
        # Salva
        c_aquisitivo = CalculoAquisitivoUsofrutoServidorEdital()
        c_aquisitivo.servidor = servidor
        c_aquisitivo.edital = edital
        c_aquisitivo.periodo = quinq
        c_aquisitivo.inicio_aquisitivo = inicio_em
        c_aquisitivo.final_aquisitivo_teorico = final_em
        c_aquisitivo.qtd_dias_afast_nao_conta_como_efet_exerc = qtd_dias_afast_quinq
        c_aquisitivo.final_aquisitivo_na_patrica = final_em_na_pratica
        c_aquisitivo.save()

    """
    Quinquenios
     - Periodo usofruto
    Periodo aquisitivo e quinquenios

    Periodo aquisito    |     Período de usofruto
    ----------------------------------------------
    Quinquenio 1 (cumprido)       Quinquenio 2
    Quinquenio 2 (cumprido)       Quinquenio 3
    Quinquenio 3 (cumprido)       Quinquenio 4
    Quinquenio 4 (cumprido)       Quinquenio 5 (fim em 30/09/2020)
    Quinquenio 5 (cumprindo)      Quinquenio 6 (inicio em 01/10/2020)
    Quinquenio 6 (a cumprir)           -
    """
    caus = CalculoAquisitivoUsofrutoServidorEdital.objects.filter(edital=edital, servidor=servidor).order_by('periodo')
    if caus:
        qtd_caus = caus.count()
        for cau in caus:
            # Ateh o penultimo cau
            if cau.periodo < qtd_caus:
                proximo_cau = caus[cau.periodo]
                cau.inicio_uso_fruto = proximo_cau.inicio_aquisitivo
                cau.final_uso_fruto = proximo_cau.final_aquisitivo_teorico
                cau.save()
            else:
                break

    """
    Quinquenios
    - Calcula os ativos pela abrangencia do edital
    """
    if caus:
        CalculoAquisitivoUsofrutoServidorEdital.objects.filter(
            servidor=servidor,
            edital=edital,
            inicio_uso_fruto__gte=edital.periodo_abrangencia_inicio,
            final_uso_fruto__lte=edital.periodo_abrangencia_final,
        ).update(ativo_pelo_edital=True)

    """
    Quinquenios
    - Calcula os quinquenios ja gozados em outras epocas
      - aqueles ja cadastrados no SIAPE -- quantidade de dias gozados para cada aquisitivo (distribui para cada aquisitivo)

    Calcula e salva
    Salva todas as licencas capacitacao anteriores
      Qtd de dias dentro de cada periodo aquisitivo
    Conta os dias de lic capacitacao já gozadas
    """

    if caus:
        # SIAPE
        codigos_lc = EditalLicCapacitacao.get_todos_os_codigos_licenca_capacitacao()
        # afastamentos_servidor = ServidorAfastamento.objects.filter(servidor=servidor,
        #                                                           afastamento__codigo=AfastamentoSiape.LICENCA_CAPACITACAO_3_MESES,
        #                                                           cancelado=False).order_by('data_inicio')
        afastamentos_servidor = ServidorAfastamento.objects.filter(servidor=servidor, afastamento__codigo__in=codigos_lc, cancelado=False).order_by(
            'data_inicio'
        )
        CalculoAquisitivoUsofrutoServidorEdital.objects.filter(edital=edital, servidor=servidor).update(qtd_dias_lc_siape=0)
        caus = CalculoAquisitivoUsofrutoServidorEdital.objects.filter(edital=edital, servidor=servidor).order_by('periodo')

        afastamentos_servidor_utilizados = []
        for afast in afastamentos_servidor:
            for cau in caus:
                if cau.final_uso_fruto:
                    # Não existe regra para colocar o excedente de qtd de dias de lic capacitacao para o próx aquisitivo/usofruto
                    # Mantremos este código apenas enquanto não se finaliza o processamento do primeiro edital processado pelo módulo
                    """
                    if afast.data_inicio >= cau.inicio_uso_fruto and afast.data_termino <= cau.final_uso_fruto:
                        # Se o AFASTAMENTO estiver completamente dentro do PERIODO DE USO FRUTO
                        # - Se a licenca ja gozada se inicia e finaliza dentro deste periodo de uso fruto
                        cau.refresh_from_db()
                        cau.qtd_dias_lc_siape += (afast.quantidade_dias_afastamento + 1)

                        cau.save()
                    elif afast.data_inicio >= cau.inicio_uso_fruto and afast.data_inicio <= cau.final_uso_fruto:
                        # Senao conta dias neste periodo de usofruto e o resto na proxima
                        cau.refresh_from_db()
                        cau.qtd_dias_lc_siape += ((cau.final_uso_fruto - afast.data_inicio).days + 1)
                        cau.save()
                        #
                        cau_proximo = CalculoAquisitivoUsofrutoServidorEdital.objects.get(edital=edital,
                                                                                          servidor=servidor,
                                                                                          periodo=cau.periodo + 1)
                        cau_proximo.refresh_from_db()
                        cau_proximo.qtd_dias_lc_siape += ((afast.data_termino - cau_proximo.inicio_uso_fruto).days + 1)
                        cau_proximo.save()
                    """

                    if afast.id not in afastamentos_servidor_utilizados and (
                        afast.data_inicio >= cau.inicio_uso_fruto and afast.data_inicio <= cau.final_uso_fruto
                    ):
                        afastamentos_servidor_utilizados.append(afast.id)
                        cau.qtd_dias_lc_siape += afast.quantidade_dias_afastamento + 1
                        cau.save()

        #
        # SUAP
        CalculoAquisitivoUsofrutoServidorEdital.objects.filter(edital=edital, servidor=servidor).update(qtd_dias_lc_suap=0)
        # afastamentos_servidor_confirmados_suap = PeriodoPedidoLicCapacitacao.get_periodos_de_pedidos_aprovado_em_definitivo_nao_cadastrados_no_siape(
        #    edital, servidor
        # )
        afastamentos_servidor_confirmados_suap = PeriodoPedidoLicCapacitacao.get_periodos_de_pedidos_aprovado_em_definitivo_nao_cadastrados_no_siape(
            None, servidor
        )
        caus = CalculoAquisitivoUsofrutoServidorEdital.objects.filter(edital=edital, servidor=servidor).order_by('periodo')

        afastamentos_servidor_utilizados = []
        for afast in afastamentos_servidor_confirmados_suap:
            for cau in caus:
                if cau.final_uso_fruto:
                    """
                    # 27/02/2021	30/04/2021
                    #
                    # 12/06/2015	12/06/2020
                    # 13/06/2020	13/06/2025
                    # 14/06/2025	14/06/2030
                    """

                    # Não existe regra para colocar o excedente de qtd de dias de lic capacitacao para o próx aquisitivo/usofruto
                    # Mantremos este código apenas enquanto não se finaliza o processamento do primeiro edital processado pelo módulo
                    """
                    # if afast.data_inicio >= cau.inicio_uso_fruto and afast.data_termino <= cau.final_uso_fruto:
                    if afast.data_inicio >= cau.inicio_uso_fruto and afast.data_inicio <= cau.final_uso_fruto:
                        # Se a licenca ja gozada se inicia e finaliza dentro deste periodo de uso fruto
                        # - Se a licenca finaliza ate este periodo de uso fruto
                        cau.qtd_dias_lc_suap += afast.qtd_dias_total
                        cau.save()
                    elif afast.data_inicio >= cau.inicio_uso_fruto and afast.data_inicio <= cau.final_uso_fruto:
                        # Senao conta dias neste periodo de usofruto e o resto na proxima
                        q = (cau.final_uso_fruto - afast.data_inicio).days
                        if q > 0:
                            cau.qtd_dias_lc_suap += (cau.final_uso_fruto - afast.data_inicio).days
                            excedente_para_proximo = afast.get_qtde_dias().days + 1
                            cau.save()
                            cau_proximo = CalculoAquisitivoUsofrutoServidorEdital.objects.get(edital=edital, servidor=servidor, periodo=cau.periodo + 1)
                            cau_proximo.qtd_dias_lc_suap += (afast.data_termino - cau_proximo.inicio_uso_fruto).days + excedente_para_proximo
                            cau_proximo.save()
                    """
                    if afast.id not in afastamentos_servidor_utilizados and (
                        afast.data_inicio >= cau.inicio_uso_fruto and afast.data_inicio <= cau.final_uso_fruto
                    ):
                        if cau.qtd_dias_lc_suap:
                            cau.qtd_dias_lc_suap += afast.qtd_dias_total or 0
                        else:
                            cau.qtd_dias_lc_suap = afast.qtd_dias_total or 0
                        cau.save()

        # Determinando o "periodo aquisitivo" e "Período de usofruto" validos para o edital
        #   Define se ainda aceita pedidos de licenca capacitacao
        CalculoAquisitivoUsofrutoServidorEdital.objects.filter(edital=edital, servidor=servidor).update(ativo_pelo_edital=False)
        caus = CalculoAquisitivoUsofrutoServidorEdital.objects.filter(edital=edital, servidor=servidor).order_by('periodo')
        for cau in caus:
            if cau.final_uso_fruto:
                if (
                    edital.periodo_abrangencia_inicio >= cau.inicio_uso_fruto
                    and edital.periodo_abrangencia_final <= cau.final_uso_fruto
                    or edital.periodo_abrangencia_inicio >= cau.inicio_uso_fruto
                    and edital.periodo_abrangencia_inicio <= cau.final_uso_fruto
                    or edital.periodo_abrangencia_final >= cau.inicio_uso_fruto
                    and edital.periodo_abrangencia_final <= cau.final_uso_fruto
                ):
                    cau.ativo_pelo_edital = True
                    cau.save()

        # Determinando o "periodo aquisitivo" e "Período de usofruto" de cada parcela solicitada
        periodos = PeriodoPedidoLicCapacitacao.objects.filter(pedido__edital=edital, pedido__servidor=servidor).order_by('data_inicio')
        causp = CalculoAquisitivoUsofrutoServidorEdital.objects.filter(edital=edital, servidor=servidor).order_by('periodo')
        for per in periodos:
            for caup in causp:
                if caup.final_uso_fruto:
                    # Se inicia e termina dentro daquele usofruto
                    if (
                        per.data_inicio >= caup.inicio_uso_fruto
                        and per.data_termino <= caup.final_uso_fruto
                        or per.data_inicio >= caup.inicio_uso_fruto
                        and per.data_inicio <= caup.final_uso_fruto
                        or periodos.filter(aquisitivo_uso_fruto__isnull=False).exists()
                        and per.data_termino >= caup.inicio_uso_fruto
                        and per.data_termino <= caup.final_uso_fruto
                    ):
                        per.aquisitivo_uso_fruto = caup
                        per.save()
                        break


def calcular_ch_pedido_capacitacao(pedido):
    """
    # CH da acao do pedido
    # - Art. 26.  O órgão ou a entidade poderá conceder licença para capacitação
    #    somente quando a carga horária total da ação de desenvolvimento ou do
    #    conjunto de ações seja igual ou superior a trinta horas semanais.
    #    (Redação dada pelo Decreto nº 10.506, de 2020)
    # * ITEM 8 da Nota Técnica SEI nº 7737/2020/ME
    # - Levando-se em conta estes três aspectos: i) mês de 30 (trinta) dias, ii)
    #   semana de 7 (sete) dias, e iii) possibilidade de conjugação de ações de
    #   desenvolvimento, entende-se que para fins de cálculo da carga horária
    #   semanal para licença para capacitação, deve-se realizar a seguinte operação:
    # Formula
    # - CH_SEMANAL = (carga_horaria / qtd de dias da licença solicitada) * 7
    # - A CH_SEMANAL vai ser utilizada para validar a regra das 30 horas
    # - A CH_SEMANAL deve ser igual ou superior a trinta horas semanais
    """
    qtd_dias = get_qtd_dias_pedido_capacitacao(pedido)
    if qtd_dias:
        return (pedido.carga_horaria / qtd_dias) * 7
    return 0


def calcular(edital, servidor):
    calcular_periodo_aquisito_usofruto(edital, servidor)


def validar(pedido):
    # TODO criar funcoes para cada regra do checklist

    retorno = []

    """
    REGRA 01
    - Se existe periodo cadastrado
    * Considera apenas os periodos vinculados a ESTE PEDIDO
    --------------------------------------
    """
    m = {}
    m['msg'] = 'O pedido deve ter ao menos uma parcela cadastrada (apenas deste pedido).'
    m['erro'] = False
    periodos = get_todos_periodos_do_pedido(pedido)
    if not periodos:
        m['erro'] = True
    retorno.append(m)

    """
    REGRA 02
    - Garantir ordem das parcelas -- continuidade -- inicio e final
    * Considera todos os periodos que o servidor esta solicitando NESTE EDITAL
    # --------------------------------------
    """
    todos_periodos = get_todos_periodos_dos_pedidos_nao_cancelados_do_edital(pedido.edital, pedido.servidor).order_by('data_inicio')
    qtd_todos_periodos = todos_periodos.count()
    ordem_todos_periodos = 0
    m = {}
    m['msg'] = 'As parcelas (em todos os seus pedidos deste edital) devem iniciar após a parcela anterior.'
    m['erro'] = False
    if todos_periodos:
        while ordem_todos_periodos <= qtd_todos_periodos - 2:
            periodo = todos_periodos[ordem_todos_periodos]
            proximo_periodo = todos_periodos[ordem_todos_periodos + 1]
            if not proximo_periodo.data_inicio > periodo.data_termino:
                m['erro'] = True
                break
            ordem_todos_periodos += 1
    else:
        m['erro'] = True
    retorno.append(m)

    """
    REGRA 03
    - Se o servidor estiver cadastrando o pedido com datas de início e término pretendidas
      fora do período de abrangência do lote de concessões aberto, não permite salvar o
      pedido.
    * Considera apenas os periodos vinculados a ESTE PEDIDO
    --------------------------------------
    """
    m = {}
    m['msg'] = 'A(s) parcela(s) (apenas deste pedido) de licença capacitação deve(m) considerar o período de abrangência do edital.'
    periodos = get_todos_periodos_do_pedido(pedido)
    if periodos:
        inicio = periodos.first().data_inicio
        final = periodos.last().data_termino
        if not inicio >= pedido.edital.periodo_abrangencia_inicio or not final <= pedido.edital.periodo_abrangencia_final:
            m['erro'] = True
        else:
            m['erro'] = False
    else:
        m['erro'] = True
    retorno.append(m)

    """
    REGRA 04
    - Se já foram cadastradas 6 parcelas de licença para capacitação deste servidor,
      correspondentes ao mesmo período aquisitivo, não permite salvar o pedido.
    * Considera todos os periodos que o servidor esta solicitando NESTE EDITAL
    --------------------------------------
    """
    todos_periodos = get_todos_periodos_dos_pedidos_nao_cancelados_do_edital(pedido.edital, pedido.servidor)
    m = {}
    m['msg'] = 'Impossível cadastrar mais de 6 parcelas (em todos os seus pedidos deste edital) vinculados ao mesmo período aquisitivo.'
    if todos_periodos:
        todos_periodos = (
            todos_periodos.values('aquisitivo_uso_fruto')
            .annotate(qtd_periodos=Count('aquisitivo_uso_fruto'))
            .filter(qtd_periodos__gt=6)
            .order_by('data_inicio')
        )
        m['erro'] = False
        if todos_periodos:
            m['erro'] = True
    else:
        m['erro'] = True
    retorno.append(m)

    """
    REGRA 05
    - Se a data de início de licença pretendida não corresponder ao período de usufruto
      do último (válido para este edital) período aquisitivo do servidor,
      não permite salvar o pedido.
        - Se os periodos solicitados correspondem aos aquisitivos validos pra este edital
    * Considera apenas os periodos vinculados a este pedido
    """
    m = {}
    m['msg'] = (
        'Impossível cadastrar uma parcela (apenas deste pedido) que não corresponda a um período aquisitivo/usofruto válido para o servidor neste edital.'
    )
    m['erro'] = False

    periodos_solicitados = get_todos_periodos_do_pedido(pedido)

    if periodos_solicitados:
        # Se cada parcela estah em um periodo ativo
        periodos_aq_us = CalculoAquisitivoUsofrutoServidorEdital.objects.filter(
            edital=pedido.edital, servidor=pedido.servidor, ativo_pelo_edital=True
        )
        if not periodos_aq_us:
            m['erro'] = True

        periodos_solicitados_sem_aquisitivo_usofruto = periodos_solicitados.filter(aquisitivo_uso_fruto__isnull=True)
        if periodos_solicitados_sem_aquisitivo_usofruto:
            m['erro'] = True

        periodos_solicitados_sem_aquisitivo_usofruto_valido = periodos_solicitados.filter(aquisitivo_uso_fruto__ativo_pelo_edital=False)
        if periodos_solicitados_sem_aquisitivo_usofruto_valido:
            m['erro'] = True
    else:
        m['erro'] = True

    retorno.append(m)

    """
    # REGRA 06
    # - Se a quantidade de dias do período de licença que o servidor está cadastrando
    #   for inferior a 15 dias, não permite salvar o pedido.
    #   - Busca se existe alguma parcela com menos de 15 dias
    # * Considera apenas os periodos vinculados a este pedido
    """
    m = {}
    m['msg'] = 'Cada parcela cadastrada deve corresponder a um período maior ou igual a 15 dias (apenas deste pedido). '
    m['erro'] = False
    periodos_solicitados = get_todos_periodos_do_pedido(pedido)
    if periodos_solicitados:
        for ps in periodos_solicitados:
            if ps.qtd_dias_total < 15:
                m['erro'] = True
    else:
        m['erro'] = True
    retorno.append(m)

    """
    # REGRA 07
    # Conforme edital
    #   2.2.1. Quando a licença para capacitação for concedida de forma parcelada,
    #   nos termos do §3° do art. 25 do Decreto n° 9.991, de 2019, deverá ser observado o
    #   interstício mínimo de 60 (sessenta) dias entre quaisquer períodos de gozo de
    #   licença para capacitação.
    # Regra
    #   - Se a data de início da licença que o servidor está cadastrando é menos
    #     de 60 dias após a data de término de outra parcela anterior.
    #     OU se a data de término da licença que o servidor está cadastrando é menor
    #     de 60 dias anterior a data de início de outra parcela posterior,
    #     não permite salvar o pedido
    #     - Considera as parcelas já gozadas
    #     - Se o inicio do primeiro periodo solicitado eh inferior a 60 dias da ultima parcela
    #       ja gozada
    #       OU vinculada a edital anterior a este
    #     - Como fazer
    #       - Pega todas as parcelas de todos os meus pedidos nao cancelados vinculados a
    #         este edital
    #       - Pega a ultima parcela (seja de pedidos/periodos ja aprovados em editais anteriores,
    #         seja ja cadastradas no SIAPE)
    #
    # CONSIDERANDO AS PARCELAS NAO CANCELADAS SOLICITADAS NESTE EDITAL
    # - Sabendo se
    #   - Se a data de término da licença que o servidor está cadastrando é menor
    #     de 60 dias anterior a data de início de outra parcela posterior,
    # * Considera todos os periodos que o servidor esta solicitando neste edital
    """

    todos_periodos = get_todos_periodos_dos_pedidos_nao_cancelados_do_edital(pedido.edital, pedido.servidor).order_by('data_inicio')
    m = {}
    m['msg'] = (
        'A diferença em dias entre uma parcela cadastrada e a parcela posterior '
        '(em todos os seus pedidos deste edital) não pode ser inferior a 60 dias.'
    )
    m['erro'] = False
    if todos_periodos:
        qtd_todos_periodos = todos_periodos.count()
        ordem_todos_periodos = 0
        while ordem_todos_periodos <= qtd_todos_periodos - 2:
            periodo = todos_periodos[ordem_todos_periodos]
            proximo_periodo = todos_periodos[ordem_todos_periodos + 1]
            dias_depois = (proximo_periodo.data_inicio - periodo.data_termino).days
            if dias_depois < 60:
                m['erro'] = True
                break
            ordem_todos_periodos += 1
    else:
        m['erro'] = True
    retorno.append(m)

    """
    # REGRA 08
    # CONSIDERANDO PARCELAS JA APROVADAS (EM CARÁTER DEFINITIVO OU DE FORMA PRELIMINAR) E
    # AS EFETIVADAS NO SIAPE
    # - Sabendo se
    #   - Se a data de início da licença que o servidor está cadastrando é menos de
    #     60 dias após a data de término de outra parcela anterior.
    # * Considera todos os periodos que o servidor esta solicitando neste edital
    # * Compara com todos as licenças capacitação do servidor
    """
    m = {}
    m['msg'] = (
        'A diferença em dias entre o final da última parcela já gozada e o início da '
        'primeira parcela solicitada neste edital (em todos os seus pedidos deste edital) '
        'não pode ser inferior a 60 dias.'
    )
    m['erro'] = False
    periodo_pedido = get_todos_periodos_dos_pedidos_nao_cancelados_do_edital(pedido.edital, pedido.servidor).order_by('data_inicio')
    afastamento = get_servidor_afastamento_todos_siape_suap(pedido.servidor)
    if periodo_pedido:
        if afastamento:
            primeiro_periodo_pedido = periodo_pedido.first()
            ultimo_afastamento = afastamento[-1]
            dias_depois = (primeiro_periodo_pedido.data_inicio - ultimo_afastamento[1]).days
            if dias_depois < 60:
                m['erro'] = True
    else:
        m['erro'] = True
    retorno.append(m)

    """
    REGRA 09
      - Servidor nao possui periodo aquisitivo válido para este edital
    * Considera todos os periodos que o servidor esta solicitando neste edital
    """

    m = {}
    m['msg'] = 'Servidor possui período Aquisitivo e de Usufruto válido para este edital.'
    m['erro'] = False
    periodo_pedido = get_todos_periodos_dos_pedidos_nao_cancelados_do_edital(pedido.edital, pedido.servidor).order_by('data_inicio')
    if periodo_pedido:
        existe_aquisitivo_usofruto_valido_para_edital = periodo_pedido.filter(aquisitivo_uso_fruto__isnull=False).exists()
        m['erro'] = not existe_aquisitivo_usofruto_valido_para_edital
    else:
        m['erro'] = True
    retorno.append(m)

    """
    # REGRA 10
    #   - Se a quantidade de dias de licença para capacitação já concedidas relativas
    #     ao mesmo período aquisitivo do servidor, somadas a parcelas pré-cadastradas,
    #     e somados aos dias do período de licença que o servidor está cadastrando,
    #     for superior a 90 dias, não permite salvar o pedido.
    # Como fazer
    #  - Se a quantidade de dias (de cada periodo + já aprovadas no SUAP + já
    #    cadastradas no SIAPE) considerando o mesmo periodo aquisitivo somar mais de 90
    #    dias nao pode
    #  - Pega todos os periodos do servidor neste edital -- todos eles (os que estao
    #    cadastrados corretamente considerando as regras do checklist) terao um periodo
    #    aquisitivo associado
    #  - Pega esse periodo aquisito e totaliza pra comparar conforme descrição anterior
    # * Considera todos os periodos que o servidor esta solicitando neste edital
    """
    m = {}
    m['msg'] = (
        'Para cada período aquisitivo o servidor só faz jus a 90 dias de licença capacitação (em todos os seus pedidos deste edital). Contabilizando as que estão sendo solicitadas com as já aprovadas.'
    )
    m['erro'] = False
    periodo_pedido = get_todos_periodos_dos_pedidos_nao_cancelados_do_edital(pedido.edital, pedido.servidor).order_by('data_inicio')
    if periodo_pedido:
        for pp in periodo_pedido:
            existe_aquisitivo_usofruto_valido_para_edital = periodo_pedido.filter(aquisitivo_uso_fruto__isnull=False).exists()
            if not existe_aquisitivo_usofruto_valido_para_edital:
                m['erro'] = True
            else:
                try:
                    qtd_dias_total = pp.aquisitivo_uso_fruto.qtd_dias_lc_siape + pp.aquisitivo_uso_fruto.qtd_dias_lc_suap
                except Exception:
                    qtd_dias_total = 90
                if (pp.qtd_dias_total + qtd_dias_total) > 90:
                    m['erro'] = True
                    break
    else:
        m['erro'] = True
    retorno.append(m)

    """
    # REGRA 11
    #   - Se o período compreendido entre a data de início e de término pretendida pelo
    #     servidor extrapolar 2% (parametro do edital) da quantidade de servidores em exercício em algum dia,
    #     não permite salvar o pedido (a verificação é feita para categorias tae e docente
    #     separadamente, e o sistema deverá informar as datas que causam a extrapolação do
    #     limite)
    #     - Utiliza o quadro
    #     - Nao contar com os pedidos que estão sendo submetidos agora
    #     - Conta apenas com os pedidos que ja estão no quadro
    #       - Considera o total (suap+siape)
    # Como fazer
    #  - Pega dos periodos nao cancelados do servidor no pedido
    #  - Verifica se ao adicionar esse servidor em cada dia e somando com os servidores que ja existem no dia extrapola ou nao os 2%
    # - *** Usado apenas na submissao *** Em nada tem haver com o processamento ***
    """

    m = {}
    parametro_percentual_edital_formatado = format_money(pedido.edital.percentual_limite_servidores_em_lic_capacitacao)
    m['msg'] = (
        f'Nenhuma parcela pode extrapolar o limite de {parametro_percentual_edital_formatado}% da quantidade de servidores em exercício em algum dia desse período.'
    )
    m['erro'] = False
    periodo_pedido = get_todos_periodos_dos_pedidos_nao_cancelados_do_edital(pedido.edital, pedido.servidor).order_by('data_inicio')
    limite_qtd_servidores_lic_capacitacao_por_dia_tae = pedido.edital.qtd_limite_taes_em_lic_capacitacao_por_dia
    limite_qtd_servidores_lic_capacitacao_por_dia_docente = pedido.edital.qtd_limite_docentes_em_lic_capacitacao_por_dia
    datas_que_extrapolam = []
    if periodo_pedido:
        for pp in periodo_pedido:
            lcpd = LicCapacitacaoPorDia.objects.filter(data__gte=pp.data_inicio, data__lte=pp.data_termino)
            if pp.pedido.eh_tecnico_administrativo:
                extrapola = lcpd.filter(qtd_taes_geral__gt=limite_qtd_servidores_lic_capacitacao_por_dia_tae).order_by('data')
                if extrapola:
                    datas_que_extrapolam += extrapola.values_list('data', flat=True)
            elif pp.pedido.eh_docente:
                extrapola = lcpd.filter(qtd_docentes_geral__gt=limite_qtd_servidores_lic_capacitacao_por_dia_docente).order_by('data')
                if extrapola:
                    datas_que_extrapolam += extrapola.values_list('data', flat=True)
        if datas_que_extrapolam:
            datas_que_extrapolam_str = []
            for e in datas_que_extrapolam:
                datas_que_extrapolam_str.append(e.strftime('%d/%m/%Y'))
            datas_que_extrapolam = datas_que_extrapolam_str
            m['msg'] += ' As seguintes datas extrapolam o limite: '
            m['msg'] += ', '.join(datas_que_extrapolam)
            m['erro'] = True
    else:
        m['erro'] = True
    retorno.append(m)

    """
    # REGRA 12
    # - Verificar o limite de carga horária para permitir a submissão do
    #   pedido somente quando a carga horária total da ação de desenvolvimento ou do
    #   conjunto de ações seja igual ou superior a trinta horas semanais.
    """

    m = {}
    m['msg'] = 'A carga horária semanal do Curso/Ação vinculado a este pedido deve ser maior ou igual a 30 horas.'
    m['erro'] = False
    if not calcular_ch_pedido_capacitacao(pedido) >= 30:
        m['erro'] = True
    else:
        m['erro'] = False
    retorno.append(m)

    #
    return retorno


def checklist(pedido, calcula_pedido=True):
    # Calcular
    # ---------------
    if calcula_pedido:
        calcular(pedido.edital, pedido.servidor)

    # Valida
    # ---------------
    lista_verificacao = []
    tem_erro = False
    if calcula_pedido:
        lista_verificacao += validar(pedido)
        for lv in lista_verificacao:
            if lv.get('erro'):
                tem_erro = True
                break

    return tem_erro, lista_verificacao
