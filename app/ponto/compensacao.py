import datetime
from collections import OrderedDict
from collections.abc import Callable
from copy import deepcopy
from enum import Enum
from typing import Any

from dateutil.relativedelta import relativedelta
from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.db.models import Model, QuerySet

from comum.models import Configuracao, User
from djtools.db.models import Q
from djtools.utils import datas_entre, formata_segundos
from ponto.enums import TipoLiberacao
from ponto.models import (
    AbonoChefia,
    Afastamento,
    DebitoExterno,
    DebitoExternoCadastro,
    Frequencia,
    HorarioCompensacao,
    RecessoOpcaoEscolhida,
    SaldoExterno,
)
from rh.models import Servidor, ServidorFuncaoHistorico
from rh.utils import periodos_estah_no_pgd1_pgd2


def filter_relatorio_de_ponto(servidor, data_inicial, data_final):
    #
    # relatorio_de_ponto['dias'] ---> [
    #   {'dia': ? (date), 'carga_horaria_do_dia': ? (int q indica horas), ... },
    #   {'dia': ? (date), 'carga_horaria_do_dia': ? (int q indica horas), ... },
    #   {'dia': ? (date), 'carga_horaria_do_dia': ? (int q indica horas), ... },
    #   ...
    # ]

    return Frequencia.relatorio_ponto_pessoa(
        servidor.get_vinculo(),
        data_ini=data_inicial,
        data_fim=data_final,
        sabado=False,
        domingo=False,
        show_grafico=False,
        so_inconsistentes=False,
        trata_compensacoes=False,
        trata_inconsistencias=False,
        calcular_se_estah_no_pgd=False,  # este cálculo será feito/chamado neste módulo em "SituacaoDia.is_dia_em_pgd"
    )


def filter_compensacoes_informadas(servidor, data_inicial, data_final):
    # Informes de compensação do servidor
    """
    Modelo:
        ponto.HorarioCompensacao

    Relacionamentos:
        funcionario ----> rh.Servidor
        chefe ----> rh.Servidor
        saldo_externo_compensacao ----> ponto.SaldoExterno
        abono_na_data_compensacao ----> ponto.AbonoChefia
        abono_na_data_aplicacao ----> ponto.AbonoChefia
    """

    return (
        HorarioCompensacao.objects.select_related('funcionario', 'saldo_externo_compensacao')
        .defer(
            'chefe',
            'abono_na_data_compensacao',
            'abono_na_data_aplicacao',
        )
        .filter(
            Q(
                funcionario=servidor,
                situacao=HorarioCompensacao.SITUACAO_VALIDO,
            )
            & Q(
                # por data do saldo
                Q(data_compensacao__gte=data_inicial, data_compensacao__lte=data_final)
                # por data do débito
                | Q(data_aplicacao__gte=data_inicial, data_aplicacao__lte=data_final)
            )
        )
        .distinct()
    )


def filter_acompanhamentos(servidor, data_inicial, data_final):
    # Compensações específicas do servidor
    """
    Modelo:
        ponto.RecessoOpcaoEscolhida

    Relacionamentos:
        funcionario ----> rh.Servidor
        recesso_opcao ----> ponto.RecessoOpcao ----> ponto.RecessoPeriodoCompensacao, ponto.RecessoDia, ponto.RecessoPeriodo
        validador ----> rh.Servidor
        responsavel_ultima_pos_edicao ----> rh.Servidor
        dias_escolhidos ----> ponto.RecessoDiaEscolhido ----> ponto.RecessoDia
        periodos_escolhidos ----> ponto.RecessoPeriodoEscolhido ----> ponto.RecessoPeriodo
    """

    return (
        RecessoOpcaoEscolhida.objects.select_related(
            'funcionario',
        )
        .prefetch_related('recesso_opcao__periodos_de_compensacao', 'recesso_opcao__dias_do_recesso', 'dias_escolhidos', 'periodos_escolhidos')
        .defer('validador', 'responsavel_ultima_pos_edicao')
        .filter(
            Q(
                # compensações autorizadas autorizadas do servidor informado
                funcionario=servidor,
                validacao=RecessoOpcaoEscolhida.VALIDACAO_AUTORIZADO,
            )
            & Q(
                # períodos de compensação dentro do período informado
                Q(
                    recesso_opcao__periodos_de_compensacao__data_inicial__gte=data_inicial,
                    recesso_opcao__periodos_de_compensacao__data_inicial__lte=data_final,
                )
                | Q(
                    recesso_opcao__periodos_de_compensacao__data_final__gte=data_inicial,
                    recesso_opcao__periodos_de_compensacao__data_final__lte=data_final,
                )
                | Q(
                    recesso_opcao__periodos_de_compensacao__data_inicial__lt=data_inicial,
                    recesso_opcao__periodos_de_compensacao__data_final__gt=data_final,
                )
                # dias escolhidos dentro do período informado
                | Q(dias_escolhidos__dia__data__gte=data_inicial, dias_escolhidos__dia__data__lte=data_final)
                # períodos escolhidos dentro do período informado
                | Q(periodos_escolhidos__periodo__data_inicio__gte=data_inicial, periodos_escolhidos__periodo__data_inicio__lte=data_final)
                | Q(periodos_escolhidos__periodo__data_fim__gte=data_inicial, periodos_escolhidos__periodo__data_fim__lte=data_final)
                | Q(periodos_escolhidos__periodo__data_inicio__lt=data_inicial, periodos_escolhidos__periodo__data_fim__gt=data_final)
            )
        )
        .distinct()
    )


def filter_debitos_externos(servidor, data_inicial, data_final) -> QuerySet[DebitoExterno]:
    # Débitos externos do servidor
    """
    Modelo:
        ponto.DebitoExterno

    Relacionamentos:
        cadastro ----> ponto.DebitoExternoCadastro ----> rh.Servidor, contrib.ContentType
    """

    return (
        DebitoExterno.objects.select_related('cadastro', 'cadastro__servidor', 'cadastro__origem_type')
        .defer('cadastro__servidor_cadastro', 'cadastro__validador', 'cadastro__validador_observacoes')
        .filter(
            cadastro__servidor=servidor,
            cadastro__situacao=DebitoExternoCadastro.SITUACAO_VALIDADO,
            data_debito__gte=data_inicial,
            data_debito__lte=data_final,
        )
    )


def filter_saldos_externos(servidor, data_inicial, data_final) -> QuerySet[SaldoExterno]:
    # Saldos externos do servidor
    """
    Modelo:
        ponto.SaldoExterno

    Relacionamentos:
        servidor ----> rh.Servidor
        servidor_cadastro ----> rh.Servidor
        validador ----> rh.Servidor
    """

    return (
        SaldoExterno.objects.select_related('servidor', 'origem_type')
        .defer('servidor_cadastro', 'validador', 'validador_observacoes')
        .filter(
            Q(servidor=servidor, situacao=SaldoExterno.SITUACAO_VALIDADO)
            & Q(
                Q(data_inicio__gte=data_inicial, data_inicio__lte=data_final)
                | Q(data_fim__gte=data_inicial, data_fim__lte=data_final)
                | Q(data_inicio__lt=data_inicial, data_fim__gt=data_final)
            )
        )
    )


def filter_historico_funcao(servidor, data_inicial, data_final) -> QuerySet[ServidorFuncaoHistorico]:
    return servidor.historico_funcao(data_inicial, data_final)


def filter_afastamentos_parciais(servidor, data_inicial, data_final) -> QuerySet[Afastamento]:
    return Afastamento.buscar_afastamentos_parciais(servidor.get_vinculo(), data_inicial, data_final)


def get_datas_entre(data_inicial, data_final):
    return datas_entre(data_inicial, data_final)


def get_periodos_de_dias_a_atualizar(dias_agendados, dias_atualizados):
    """Retorna 2 períodos que efetivamente precisam ser atualizados.
    A união dos dias agendados com os dias atualizados DEVE formar um
    período total sem "espaços vazios".

    atualizados             |--------------------------------------------|

    agendados 1         |xxx-------|
    agendados 2         |xxx----------------------------------------------xxxxxxxxx|
    agendados 3                 |-------------------|
    agendados 4                              |----------------------------xxxxx|
    agendados 5    |xxxx|vvv
    agendados 6                                                           vvvv|xxxx|

    xxxx = agendados pendentes de atualização
    vvvv = espaço vazio que precisa ser atualizado também
    """
    dias_intersecao = list(set(dias_agendados) & set(dias_atualizados))

    periodo_1 = []
    periodo_2 = []

    if dias_intersecao:
        dias_agendados_pendentes = list(set(dias_agendados or []) - set(dias_intersecao))
        if dias_agendados_pendentes:
            if min(dias_agendados_pendentes) < min(dias_atualizados):
                periodo_1 = [min(dias_agendados_pendentes), min(dias_atualizados) - datetime.timedelta(1)]
            if max(dias_agendados_pendentes) > max(dias_atualizados):
                periodo_2 = [max(dias_atualizados) + datetime.timedelta(1), max(dias_agendados_pendentes)]
    else:
        if dias_agendados and not dias_atualizados:
            periodo_1 = [min(dias_agendados), max(dias_agendados)]
        if dias_agendados and dias_atualizados:
            if max(dias_agendados) < min(dias_atualizados):
                periodo_1 = [min(dias_agendados), min(dias_atualizados) - datetime.timedelta(1)]
            if min(dias_agendados) > max(dias_atualizados):
                periodo_2 = [max(dias_atualizados) + datetime.timedelta(1), max(dias_agendados)]

    dias_agendados = dias_agendados or []
    dias_atualizados = dias_atualizados or []

    return [periodo_1, periodo_2]


def formatar_segundos(segundos=0, add_sufixos_h_min_seg=False, omite_se_zero=False):
    if add_sufixos_h_min_seg:
        return str(formata_segundos(segundos, '{h}h ', '{m}min ', '{s}seg', omite_se_zero))
    return str(formata_segundos(segundos, '{h:02.0f}:', '{m:02.0f}:', '{s:02.0f}', omite_se_zero))


def get_periodos(dias, formatar=False):
    dias = sorted(dias)
    periodos = []
    dia_inicial = None
    dia_anterior = None
    for dia in dias:
        if dia_inicial is None:
            dia_inicial = dia
        if dia_anterior:
            if dia - datetime.timedelta(1) != dia_anterior:
                periodos.append([dia_inicial, dia_anterior])
                dia_inicial = dia
        dia_anterior = dia
    if dia_inicial and dia_anterior:
        periodos.append([dia_inicial, dia_anterior])

    if formatar:
        periodos_formatado = []
        for periodo in periodos:
            if periodo[0] == periodo[1]:
                periodos_formatado.append(str(periodo[0].strftime('%d/%m/%Y')))
            else:
                periodos_formatado.append('{} a {}'.format(periodo[0].strftime('%d/%m/%Y'), periodo[1].strftime('%d/%m/%Y')))
        return ', '.join(periodos_formatado)
    return periodos


class Contexto:
    """
    Representa a situação do ponto de um servidor em um período
    """

    def __init__(
        self,
        servidor,
        periodo_data_inicial,
        periodo_data_final,
        relatorio_de_ponto=None,  # ATT: se informado, o período do contexto deve ser o mesmo período do relatório de ponto
        considera_valor_debito_se_dia_futuro=False,
    ):
        self.servidor = servidor
        assert self.servidor is not None

        assert periodo_data_inicial is not None
        assert periodo_data_final is not None

        # tabela contendo os dias relacionados e suas respectivas situações (instâncias de SituacaoDia)
        self.situacao = OrderedDict()  # {date: SituacaoDia, date: SituacaoDia, date: SituacaoDia, ...}

        # se adianta visando menos consultas simples (de uma data) no futuro
        # engloba desde o dia 01 do mês anterior até o último dia do mês posterior ao período informado
        periodo_data_inicial_um_mes_antes = periodo_data_inicial - relativedelta(months=1)
        periodo_data_final_dois_meses_depois = periodo_data_final + relativedelta(months=2)

        periodo_data_inicial_plus = datetime.date(year=periodo_data_inicial_um_mes_antes.year, month=periodo_data_inicial_um_mes_antes.month, day=1)

        periodo_data_final_plus = datetime.date(
            year=periodo_data_final_dois_meses_depois.year, month=periodo_data_final_dois_meses_depois.month, day=1
        ) - datetime.timedelta(1)  # subtrai um dia para ter o último dia do mês posterior

        ###
        # sobre considerar valores de débitos em dias futuros
        self.considera_valor_debito_se_dia_futuro = considera_valor_debito_se_dia_futuro

        # dados "anexos" ao contexto (são os dados necessários para fazer TODOS os cálculos)
        # após instanciação, esses dados são atualizados conforme os dias vão sendo adicionados

        #########
        if relatorio_de_ponto:
            if 'dias' in relatorio_de_ponto:
                self.relatorio_de_ponto = {'dias': deepcopy(relatorio_de_ponto['dias'])}
                # ATT: considera que o período informado do contexto é o mesmo período do relatório de ponto informado
                self.relatorio_de_ponto_dias_atualizados = get_datas_entre(periodo_data_inicial, periodo_data_final)
                self.relatorio_de_ponto_dias_agendados_para_atualizacao = []
                self.relatorio_de_ponto_periodos_consultados = [
                    self.periodos_consultados_get_periodo_str(periodo_data_inicial, periodo_data_final)
                ]  # ['periodo', 'periodo', 'periodo', ...]
            else:
                self.relatorio_de_ponto = {}
                self.relatorio_de_ponto_dias_atualizados = []
                self.relatorio_de_ponto_dias_agendados_para_atualizacao = get_datas_entre(periodo_data_inicial_plus, periodo_data_final_plus)
                self.relatorio_de_ponto_periodos_consultados = []  # ['periodo', 'periodo', 'periodo', ...]
        else:
            self.relatorio_de_ponto = {}
            self.relatorio_de_ponto_dias_atualizados = []
            self.relatorio_de_ponto_dias_agendados_para_atualizacao = get_datas_entre(periodo_data_inicial_plus, periodo_data_final_plus)
            self.relatorio_de_ponto_periodos_consultados = []  # ['periodo', 'periodo', 'periodo', ...]

        #########
        self.compensacoes_informadas = (
            HorarioCompensacao.objects.none()
        )  # filter_compensacoes_informadas(servidor, periodo_data_inicial_plus, periodo_data_final_plus)
        self.compensacoes_informadas_dias_atualizados = []  # get_datas_entre(periodo_data_inicial_plus, periodo_data_final_plus)
        self.compensacoes_informadas_dias_agendados_para_atualizacao = get_datas_entre(periodo_data_inicial_plus, periodo_data_final_plus)  # []
        self.compensacoes_informadas_periodos_consultados = {}  # {'periodo': [compensacao, compensacao, compensacao, ...]}

        #########
        self.acompanhamentos_envolvidos = (
            RecessoOpcaoEscolhida.objects.none()
        )  # filter_acompanhamentos(servidor, periodo_data_inicial_plus, periodo_data_final_plus)
        self.acompanhamentos_envolvidos_dias_atualizados = []  # get_datas_entre(periodo_data_inicial_plus, periodo_data_final_plus)
        self.acompanhamentos_envolvidos_dias_agendados_para_atualizacao = get_datas_entre(periodo_data_inicial_plus, periodo_data_final_plus)  # []
        self.acompanhamentos_envolvidos_periodos_consultados = {}  # {'periodo': [acompanhamento, acompanhamento, acompanhamento, ...]}
        self.acompanhamentos_envolvidos_periodos_de_compensacao_consultados = {}  # {recesso_opcao.id: [periodo_compensacao, periodo_compensacao, periodo_compensacao, ...]}
        self.acompanhamentos_envolvidos_dias_escolhidos_consultados = {}  # {recesso_opcao_escolhida.id: [dia_escolhido, dia_escolhido, dia_escolhido, ...]}
        self.acompanhamentos_envolvidos_periodos_escolhidos_consultados = {}  # {recesso_opcao_escolhida.id: [periodo_escolhido, periodo_escolhido, periodo_escolhido, ...]}
        self.acompanhamentos_envolvidos_dias_efetivos_a_compensar = {}  # {id_acompanhamento: dias_efetivos}

        #########
        self.debitos_externos_envolvidos = (
            DebitoExterno.objects.none()
        )  # filter_debitos_externos(servidor, periodo_data_inicial_plus, periodo_data_final_plus)
        self.debitos_externos_envolvidos_dias_atualizados = []  # get_datas_entre(periodo_data_inicial_plus, periodo_data_final_plus)
        self.debitos_externos_envolvidos_dias_agendados_para_atualizacao = get_datas_entre(periodo_data_inicial_plus, periodo_data_final_plus)  # []
        self.debitos_externos_envolvidos_periodos_consultados = {}  # {'periodo': [debitoexterno, debitoexterno, debitoexterno, ...]}

        #########
        self.saldos_externos_envolvidos = (
            SaldoExterno.objects.none()
        )  # filter_saldos_externos(servidor, periodo_data_inicial_plus, periodo_data_final_plus)
        self.saldos_externos_envolvidos_dias_atualizados = []  # get_datas_entre(periodo_data_inicial_plus, periodo_data_final_plus)
        self.saldos_externos_envolvidos_dias_agendados_para_atualizacao = get_datas_entre(periodo_data_inicial_plus, periodo_data_final_plus)  # []
        self.saldos_externos_envolvidos_periodos_consultados = {}  # {'periodo': [saldoexterno, saldoexterno, saldoexterno, ...]}

        #########
        self.historico_funcao = (
            ServidorFuncaoHistorico.objects.none()
        )  # self.servidor.historico_funcao(periodo_data_final_plus, periodo_data_final_plus)
        self.historico_funcao_dias_atualizados = []  # get_datas_entre(periodo_data_inicial_plus, periodo_data_final_plus)
        self.historico_funcao_dias_agendados_para_atualizacao = get_datas_entre(periodo_data_inicial_plus, periodo_data_final_plus)  # []
        self.historico_funcao_periodos_consultados = {}  # {'periodo': [servidorfuncaoHistorico, servidorfuncaoHistorico, servidorfuncaoHistorico, ...]}

        #########
        self.afastamentos_parciais = (
            Afastamento.objects.none()
        )  # Afastamento.buscar_afastamentos_parciais(self.servidor, periodo_data_final_plus, periodo_data_final_plus)
        self.afastamentos_parciais_dias_atualizados = []  # get_datas_entre(periodo_data_inicial_plus, periodo_data_final_plus)
        self.afastamentos_parciais_dias_agendados_para_atualizacao = get_datas_entre(periodo_data_inicial_plus, periodo_data_final_plus)  # []
        self.afastamentos_parciais_periodos_consultados = {}  # {'periodo': [afastamento, afastamento, afastamento, ...]}

        #########
        self.periodos_em_pgd = periodos_estah_no_pgd1_pgd2(
            self.servidor
        )  # [[data_i, data_f], [data_i, data_f], [data_i, data_f], [data_i, data_f], ...]

        # adiciona os dias no contexto atual
        for dia in get_datas_entre(periodo_data_inicial_plus, periodo_data_final_plus):
            self.add_dia(dia)

        # guarda o período INICIALMENTE informado (escopo dos totais e outras informações)
        self.periodo_inicial = [periodo_data_inicial, periodo_data_final]

        # ponto docente ativado?
        self.ponto_docente_ativado = (
            'pit_rit' in settings.INSTALLED_APPS and Configuracao.get_valor_por_chave('pit_rit', 'ponto_docente_ativado') == 'True'
        )

        # datas início e fim de exercício na instituição
        self.data_inicio_exercicio_na_instituicao = self.servidor.data_inicio_exercicio_na_instituicao
        self.data_fim_servico_na_instituicao = self.servidor.data_fim_servico_na_instituicao

        # datas início e fim para fins de compensação
        self.data_inicio_a_cobrar_compensacao = self.data_inicio_exercicio_na_instituicao  # padrão
        self.data_fim_a_cobrar_compensacao = self.data_fim_servico_na_instituicao

        # chamado 75933: cobrar compensação a partir da data em que havia cadastro em algum setor
        # procura a data mais antiga em que o servidor estava cadastrado em um setor (data inicial no primeiro setor)
        # código baseado em "ponto.views.frequencia_funcionario_get_contexto_relatorio_ponto_pessoa"
        # no contexto desse método de referência, essa informação é calculada conforme variável
        # "dias_em_que_estava_no_campus"
        dias_iniciais_em_setores = []
        for setor in self.servidor.historico_setor_suap(self.data_inicio_exercicio_na_instituicao, None):
            dias_iniciais_em_setores.append(setor.data_inicio_no_setor)
        if dias_iniciais_em_setores:
            self.data_inicio_a_cobrar_compensacao = min(dias_iniciais_em_setores)

        # confirmando os dados "anexos"
        # manter essas chamadas no final do __init__
        self.update_relatorio_de_ponto()
        self.update_compensacoes_informadas()
        self.update_acompanhamentos_envolvidos()
        self.update_debitos_externos_envolvidos()
        self.update_saldos_externos_envolvidos()
        self.update_historico_funcao()
        self.update_afastamentos_parciais()

    # -------------------------------------------------------------------------------------------------------

    def update_relatorio_de_ponto(self):
        for periodo in get_periodos_de_dias_a_atualizar(
            self.relatorio_de_ponto_dias_agendados_para_atualizacao, self.relatorio_de_ponto_dias_atualizados
        ):
            if periodo and periodo[0] and periodo[1]:
                dias_agendados_para_atualizacao_final = get_datas_entre(periodo[0], periodo[1])
                if dias_agendados_para_atualizacao_final:
                    data_inicio = min(set(dias_agendados_para_atualizacao_final))
                    data_fim = max(set(dias_agendados_para_atualizacao_final))

                    relatorio_ponto_atualizacao = filter_relatorio_de_ponto(self.servidor, data_inicio, data_fim)

                    if self.relatorio_de_ponto:
                        self.relatorio_de_ponto['dias'] += relatorio_ponto_atualizacao['dias']
                    else:
                        self.relatorio_de_ponto = relatorio_ponto_atualizacao

                    self.relatorio_de_ponto_dias_atualizados += dias_agendados_para_atualizacao_final
                    self.relatorio_de_ponto_periodos_consultados.append(self.periodos_consultados_get_periodo_str(data_inicio, data_fim))

        self.relatorio_de_ponto_dias_agendados_para_atualizacao = []

    def update_compensacoes_informadas(self):
        for periodo in get_periodos_de_dias_a_atualizar(
            self.compensacoes_informadas_dias_agendados_para_atualizacao, self.compensacoes_informadas_dias_atualizados
        ):
            if periodo and periodo[0] and periodo[1]:
                dias_agendados_para_atualizacao_final = get_datas_entre(periodo[0], periodo[1])

                if dias_agendados_para_atualizacao_final:
                    data_inicio = min(set(dias_agendados_para_atualizacao_final))
                    data_fim = max(set(dias_agendados_para_atualizacao_final))

                    nova_consulta = filter_compensacoes_informadas(self.servidor, data_inicio, data_fim)

                    self.compensacoes_informadas = self.compensacoes_informadas | nova_consulta
                    self.compensacoes_informadas_dias_atualizados += dias_agendados_para_atualizacao_final
                    self.compensacoes_informadas_periodos_consultados[self.periodos_consultados_get_periodo_str(data_inicio, data_fim)] = (
                        nova_consulta
                    )

        self.compensacoes_informadas_dias_agendados_para_atualizacao = []

    def update_acompanhamentos_envolvidos(self):
        for periodo in get_periodos_de_dias_a_atualizar(
            self.acompanhamentos_envolvidos_dias_agendados_para_atualizacao, self.acompanhamentos_envolvidos_dias_atualizados
        ):
            if periodo and periodo[0] and periodo[1]:
                dias_agendados_para_atualizacao_final = get_datas_entre(periodo[0], periodo[1])

                if dias_agendados_para_atualizacao_final:
                    data_inicio = min(set(dias_agendados_para_atualizacao_final))
                    data_fim = max(set(dias_agendados_para_atualizacao_final))

                    nova_consulta = filter_acompanhamentos(self.servidor, data_inicio, data_fim)

                    self.acompanhamentos_envolvidos = self.acompanhamentos_envolvidos | nova_consulta
                    self.acompanhamentos_envolvidos_dias_atualizados += dias_agendados_para_atualizacao_final
                    self.acompanhamentos_envolvidos_periodos_consultados[self.periodos_consultados_get_periodo_str(data_inicio, data_fim)] = (
                        nova_consulta
                    )

                    for acompanhamento in nova_consulta:
                        if acompanhamento.id not in self.acompanhamentos_envolvidos_dias_efetivos_a_compensar:
                            self.acompanhamentos_envolvidos_dias_efetivos_a_compensar[acompanhamento.id] = acompanhamento.dias_efetivos_a_compensar(
                                contexto_compensacao=self
                            )

        self.acompanhamentos_envolvidos_dias_agendados_para_atualizacao = []

    def update_debitos_externos_envolvidos(self):
        for periodo in get_periodos_de_dias_a_atualizar(
            self.debitos_externos_envolvidos_dias_agendados_para_atualizacao, self.debitos_externos_envolvidos_dias_atualizados
        ):
            if periodo and periodo[0] and periodo[1]:
                dias_agendados_para_atualizacao_final = get_datas_entre(periodo[0], periodo[1])

                if dias_agendados_para_atualizacao_final:
                    data_inicio = min(set(dias_agendados_para_atualizacao_final))
                    data_fim = max(set(dias_agendados_para_atualizacao_final))

                    nova_consulta = filter_debitos_externos(self.servidor, data_inicio, data_fim)

                    self.debitos_externos_envolvidos = self.debitos_externos_envolvidos | nova_consulta
                    self.debitos_externos_envolvidos_dias_atualizados += dias_agendados_para_atualizacao_final
                    self.debitos_externos_envolvidos_periodos_consultados[self.periodos_consultados_get_periodo_str(data_inicio, data_fim)] = (
                        nova_consulta
                    )

        self.debitos_externos_envolvidos_dias_agendados_para_atualizacao = []

    def update_saldos_externos_envolvidos(self):
        for periodo in get_periodos_de_dias_a_atualizar(
            self.saldos_externos_envolvidos_dias_agendados_para_atualizacao, self.saldos_externos_envolvidos_dias_atualizados
        ):
            if periodo and periodo[0] and periodo[1]:
                dias_agendados_para_atualizacao_final = get_datas_entre(periodo[0], periodo[1])

                if dias_agendados_para_atualizacao_final:
                    data_inicio = min(set(dias_agendados_para_atualizacao_final))
                    data_fim = max(set(dias_agendados_para_atualizacao_final))

                    nova_consulta = filter_saldos_externos(self.servidor, data_inicio, data_fim)

                    self.saldos_externos_envolvidos = self.saldos_externos_envolvidos | nova_consulta
                    self.saldos_externos_envolvidos_dias_atualizados += dias_agendados_para_atualizacao_final
                    self.saldos_externos_envolvidos_periodos_consultados[self.periodos_consultados_get_periodo_str(data_inicio, data_fim)] = (
                        nova_consulta
                    )

        self.saldos_externos_envolvidos_dias_agendados_para_atualizacao = []

    def update_historico_funcao(self):
        for periodo in get_periodos_de_dias_a_atualizar(
            self.historico_funcao_dias_agendados_para_atualizacao, self.historico_funcao_dias_atualizados
        ):
            if periodo and periodo[0] and periodo[1]:
                dias_agendados_para_atualizacao_final = get_datas_entre(periodo[0], periodo[1])

                if dias_agendados_para_atualizacao_final:
                    data_inicio = min(set(dias_agendados_para_atualizacao_final))
                    data_fim = max(set(dias_agendados_para_atualizacao_final))

                    nova_consulta = filter_historico_funcao(self.servidor, data_inicio, data_fim)

                    self.historico_funcao = self.historico_funcao | nova_consulta
                    self.historico_funcao_dias_atualizados += dias_agendados_para_atualizacao_final
                    self.historico_funcao_periodos_consultados[self.periodos_consultados_get_periodo_str(data_inicio, data_fim)] = nova_consulta

        self.historico_funcao_dias_agendados_para_atualizacao = []

    def update_afastamentos_parciais(self):
        for periodo in get_periodos_de_dias_a_atualizar(
            self.afastamentos_parciais_dias_agendados_para_atualizacao, self.afastamentos_parciais_dias_atualizados
        ):
            if periodo and periodo[0] and periodo[1]:
                dias_agendados_para_atualizacao_final = get_datas_entre(periodo[0], periodo[1])

                if dias_agendados_para_atualizacao_final:
                    data_inicio = min(set(dias_agendados_para_atualizacao_final))
                    data_fim = max(set(dias_agendados_para_atualizacao_final))

                    nova_consulta = filter_afastamentos_parciais(self.servidor, data_inicio, data_fim)

                    self.afastamentos_parciais = self.afastamentos_parciais | nova_consulta
                    self.afastamentos_parciais_dias_atualizados += dias_agendados_para_atualizacao_final
                    self.afastamentos_parciais_periodos_consultados[self.periodos_consultados_get_periodo_str(data_inicio, data_fim)] = nova_consulta

        self.afastamentos_parciais_dias_agendados_para_atualizacao = []

    # -------------------------------------------------------------------------------------------------------
    def relatorio_de_ponto_get_dia(self, dia: datetime.date) -> {}:
        def get_dia(dia: datetime.date) -> {}:
            relatorio_ponto_do_dia = {}
            for ponto_do_dia in self.relatorio_de_ponto['dias']:
                if ponto_do_dia['dia'] == dia:
                    relatorio_ponto_do_dia = ponto_do_dia
                    break
            return relatorio_ponto_do_dia

        result = get_dia(dia)

        if not result:
            # tenta mais uma vez após atualizar os dados de origem
            quinze_dias = datetime.timedelta(15)
            self.relatorio_de_ponto_dias_agendados_para_atualizacao = get_datas_entre(dia - quinze_dias, dia + quinze_dias)
            self.update_relatorio_de_ponto()
            result = get_dia(dia)

        return result

    def periodos_consultados_get_periodo_str(self, data_inicio: datetime.date, data_fim: datetime.date) -> str:
        # "dd/mm/yyyy-dd/mm/yyyy"
        return f'{data_inicio.strftime("%d/%m/%Y")}-{data_fim.strftime("%d/%m/%Y")}'

    def periodos_consultados_get_periodo(self, periodo_str: str) -> tuple[datetime.date, datetime.date]:
        # periodo_str: "dd/mm/yyyy-dd/mm/yyyy"
        data_inicio_str, data_fim_str = periodo_str.split('-')
        return [datetime.datetime.strptime(data_inicio_str, '%d/%m/%Y').date(), datetime.datetime.strptime(data_fim_str, '%d/%m/%Y').date()]

    def periodos_consultados_dia_in_periodo(self, periodo_str: str, dia: datetime.date) -> bool:
        data_inicio, data_fim = self.periodos_consultados_get_periodo(periodo_str)
        return data_inicio <= dia and dia <= data_fim

    def compensacoes_informadas_get_dia(self, dia: datetime.date) -> list[HorarioCompensacao]:
        def get_dia(dia: datetime.date) -> list[HorarioCompensacao]:
            for periodo_str, compensacoes in self.compensacoes_informadas_periodos_consultados.items():
                if self.periodos_consultados_dia_in_periodo(periodo_str, dia):
                    return [compensacao for compensacao in compensacoes if compensacao.data_compensacao == dia or compensacao.data_aplicacao == dia]
            return []

        result = get_dia(dia)

        if not result:
            # tenta mais uma vez após atualizar os dados de origem
            quinze_dias = datetime.timedelta(15)
            self.compensacoes_informadas_dias_agendados_para_atualizacao = get_datas_entre(dia - quinze_dias, dia + quinze_dias)
            self.update_compensacoes_informadas()
            result = get_dia(dia)

        return result

    def acompanhamentos_envolvidos_get_dia(self, dia: datetime.date, dia_como_saldo=True, dia_como_debito=True) -> list[RecessoOpcaoEscolhida]:
        def get_periodos_de_compensacao(recesso_opcao):
            # resolvendo o many-to-many "periodos_de_compensacao" uma única vez por opção de compensação
            if recesso_opcao.id not in self.acompanhamentos_envolvidos_periodos_de_compensacao_consultados:
                self.acompanhamentos_envolvidos_periodos_de_compensacao_consultados[recesso_opcao.id] = list(
                    recesso_opcao.periodos_de_compensacao.all()
                )
            return self.acompanhamentos_envolvidos_periodos_de_compensacao_consultados[recesso_opcao.id]

        def get_dias_escolhidos(recesso_opcao_escolhida):
            # resolvendo o many-to-many "dias_escolhidos" uma única vez por opção de compensação escolhida
            if recesso_opcao_escolhida.id not in self.acompanhamentos_envolvidos_dias_escolhidos_consultados:
                self.acompanhamentos_envolvidos_dias_escolhidos_consultados[recesso_opcao_escolhida.id] = list(
                    recesso_opcao_escolhida.dias_escolhidos.all().select_related('dia')
                )
            return self.acompanhamentos_envolvidos_dias_escolhidos_consultados[recesso_opcao_escolhida.id]

        def get_periodos_escolhidos(recesso_opcao_escolhida):
            # resolvendo o many-to-many "periodos_escolhidos" uma única vez por opção de compensação escolhida
            if recesso_opcao_escolhida.id not in self.acompanhamentos_envolvidos_periodos_escolhidos_consultados:
                self.acompanhamentos_envolvidos_periodos_escolhidos_consultados[recesso_opcao_escolhida.id] = list(
                    recesso_opcao_escolhida.periodos_escolhidos.all().select_related('periodo')
                )
            return self.acompanhamentos_envolvidos_periodos_escolhidos_consultados[recesso_opcao_escolhida.id]

        def get_dia(dia: datetime.date, dia_como_saldo=True, dia_como_debito=True) -> list[RecessoOpcaoEscolhida]:
            for periodo_str, acompanhamentos in self.acompanhamentos_envolvidos_periodos_consultados.items():
                if self.periodos_consultados_dia_in_periodo(periodo_str, dia):
                    acompanhamentos_result = []

                    for acompanhamento in acompanhamentos:
                        acompanhamento_result_add = False

                        if dia_como_saldo:
                            # o dia está no período de compensação da opção?
                            for periodo_compensacao in get_periodos_de_compensacao(acompanhamento.recesso_opcao):
                                if periodo_compensacao.data_inicial <= dia and dia <= periodo_compensacao.data_final:
                                    acompanhamentos_result.append(acompanhamento)
                                    acompanhamento_result_add = True
                                    break

                        if not acompanhamento_result_add:
                            if dia_como_debito:
                                # o dia está nos dias escolhidos pelo servidor?
                                for dia_escolhido in get_dias_escolhidos(acompanhamento):
                                    if dia_escolhido.dia.data == dia:
                                        acompanhamentos_result.append(acompanhamento)
                                        acompanhamento_result_add = True
                                        break

                        if not acompanhamento_result_add:
                            if dia_como_debito:
                                # o dia está nos dias escolhidos contidos nos períodos escolhidos pelo servidor?
                                # a escolha de um período pode abranger o período como todo ou um ou mais dias
                                # dentro do período (Demanda 2210)
                                for periodo_escolhido in get_periodos_escolhidos(acompanhamento):
                                    if dia in periodo_escolhido.get_dias_escolhidos():
                                        acompanhamentos_result.append(acompanhamento)
                                        break

                    return acompanhamentos_result

            return []

        result = get_dia(dia, dia_como_saldo, dia_como_debito)

        if not result:
            # tenta mais uma vez após atualizar os dados de origem
            quinze_dias = datetime.timedelta(15)
            self.acompanhamentos_envolvidos_dias_agendados_para_atualizacao = get_datas_entre(dia - quinze_dias, dia + quinze_dias)
            self.update_acompanhamentos_envolvidos()
            result = get_dia(dia, dia_como_saldo, dia_como_debito)

        return result

    def debitos_externos_envolvidos_get_dia(self, dia: datetime.date, origem_debito_externo: Model = None) -> list[DebitoExterno]:
        debito_externo_cadastro_origem_type = None
        if origem_debito_externo:
            debito_externo_cadastro_origem_type = ContentType.objects.get_for_model(origem_debito_externo)

        def get_dia(dia: datetime.date, origem_debito_externo: Model = None, debito_externo_cadastro_origem_type=None) -> list[DebitoExterno]:
            for periodo_str, debitos_externos in self.debitos_externos_envolvidos_periodos_consultados.items():
                if self.periodos_consultados_dia_in_periodo(periodo_str, dia):
                    debitos_externos_result = []
                    for debito_externo in debitos_externos:
                        if debito_externo.data_debito == dia:
                            if origem_debito_externo:
                                if (
                                    debito_externo.cadastro.origem_type == debito_externo_cadastro_origem_type
                                    and debito_externo.cadastro.origem_id == origem_debito_externo.id
                                ):
                                    debitos_externos_result.append(debito_externo)
                            else:
                                debitos_externos_result.append(debito_externo)
                    return debitos_externos_result
            return []

        result = get_dia(dia, origem_debito_externo, debito_externo_cadastro_origem_type)

        if not result:
            # tenta mais uma vez após atualizar os dados de origem
            quinze_dias = datetime.timedelta(15)
            self.debitos_externos_envolvidos_dias_agendados_para_atualizacao = get_datas_entre(dia - quinze_dias, dia + quinze_dias)
            self.update_debitos_externos_envolvidos()
            result = get_dia(dia, origem_debito_externo, debito_externo_cadastro_origem_type)

        return result

    def saldos_externos_envolvidos_get_dia(self, dia: datetime.date) -> list[SaldoExterno]:
        def get_dia(dia: datetime.date) -> list[SaldoExterno]:
            for periodo_str, saldos_externos in self.saldos_externos_envolvidos_periodos_consultados.items():
                if self.periodos_consultados_dia_in_periodo(periodo_str, dia):
                    saldos_externos_result = []
                    for saldo_externo in saldos_externos:
                        # o saldo externo pode ser utilizado pelo dia?
                        # if saldo_externo.data_inicio <= dia and dia <= saldo_externo.data_fim:
                        if saldo_externo.pode_ser_utilizado_neste_debito(dia):
                            saldos_externos_result.append(saldo_externo)
                    return saldos_externos_result
            return []

        result = get_dia(dia)

        if not result:
            # tenta mais uma vez após atualizar os dados de origem
            quinze_dias = datetime.timedelta(15)
            self.saldos_externos_envolvidos_dias_agendados_para_atualizacao = get_datas_entre(dia - quinze_dias, dia + quinze_dias)
            self.update_saldos_externos_envolvidos()
            result = get_dia(dia)

        return result

    def historico_funcao_get_dia(self, dia: datetime.date) -> list[ServidorFuncaoHistorico]:
        def get_dia(dia: datetime.date) -> list[ServidorFuncaoHistorico]:
            for periodo_str, historico_funcoes in self.historico_funcao_periodos_consultados.items():
                if self.periodos_consultados_dia_in_periodo(periodo_str, dia):
                    historico_funcoes_result = []
                    for historico_funcao in historico_funcoes:
                        if historico_funcao.data_inicio_funcao <= dia and (
                            (historico_funcao.data_fim_funcao and dia <= historico_funcao.data_fim_funcao) or not historico_funcao.data_fim_funcao
                        ):
                            historico_funcoes_result.append(historico_funcao)
                    return historico_funcoes_result
            return []

        result = get_dia(dia)

        if not result:
            # tenta mais uma vez após atualizar os dados de origem
            quinze_dias = datetime.timedelta(15)
            self.historico_funcao_dias_agendados_para_atualizacao = get_datas_entre(dia - quinze_dias, dia + quinze_dias)
            self.update_historico_funcao()
            result = get_dia(dia)

        return result

    def afastamentos_parciais_get_dia(self, dia: datetime.date) -> list[Afastamento]:
        def get_dia(dia: datetime.date) -> list[Afastamento]:
            for periodo_str, afastamentos in self.afastamentos_parciais_periodos_consultados.items():
                if self.periodos_consultados_dia_in_periodo(periodo_str, dia):
                    afastamentos_result = []
                    for afastamento in afastamentos:
                        if afastamento.data_ini <= dia and dia <= afastamento.data_fim:
                            afastamentos_result.append(afastamento)
                    return afastamentos_result
            return []

        result = get_dia(dia)

        if not result:
            # tenta mais uma vez após atualizar os dados de origem
            quinze_dias = datetime.timedelta(15)
            self.afastamentos_parciais_dias_agendados_para_atualizacao = get_datas_entre(dia - quinze_dias, dia + quinze_dias)
            self.update_afastamentos_parciais()
            result = get_dia(dia)

        return result

    # -------------------------------------------------------------------------------------------------------

    def dia_estah_em_pgd(self, dia: datetime.date) -> bool:
        for periodo in self.periodos_em_pgd:
            data_inicio, data_fim = periodo
            if data_inicio <= dia and dia <= data_fim:
                return True
        return False

    # -------------------------------------------------------------------------------------------------------

    @property
    def dias(self):
        """todos os dias dentro do período informado"""
        dias = datas_entre(self.periodo_inicial[0], self.periodo_inicial[1])
        return self._get_dias(dias)

    @property
    def dias_saldos(self):
        """todos os saldos dentro do período informado"""
        dias = datas_entre(self.periodo_inicial[0], self.periodo_inicial[1])
        return self._get_dias(dias, 'is_saldo')

    @property
    def dias_debitos(self):
        """todos os débitos dentro do período informado"""
        dias = datas_entre(self.periodo_inicial[0], self.periodo_inicial[1])
        return self._get_dias(dias, 'is_debito')

    @property
    def todos_dias_debitos(self):
        """todos os débitos envolvidos"""
        dias = self._get_dias_debitos_efetivos()
        return self._get_dias(dias, 'is_debito')

    @property
    def dias_debitos_especificos(self):
        """todos os débitos específicos dentro do período informado"""
        dias = datas_entre(self.periodo_inicial[0], self.periodo_inicial[1])
        return self._get_dias(dias, 'is_debito_especifico')

    @property
    def todos_dias_debitos_especificos(self):
        """todos os débitos específicos envolvidos"""
        dias = self._get_dias_debitos_efetivos()
        return self._get_dias(dias, 'is_debito_especifico')

    @property
    def dias_debitos_pendentes(self):
        """todos os débitos pendentes dentro do período informado"""
        dias = datas_entre(self.periodo_inicial[0], self.periodo_inicial[1])
        return self._get_dias(dias, 'is_debito_pendente')

    @property
    def todos_dias_debitos_pendentes(self):
        """todos os débitos pendentes envolvidos"""
        dias = self._get_dias_debitos_efetivos()
        return self._get_dias(dias, 'is_debito_pendente')

    # -------------------------------------------------------------------------------------------------------

    def __str__(self):
        contexto = ''
        for dia in list(self.situacao.keys()):
            contexto += '{}\n'.format(dia.strftime('%d/%m/%Y'))
        return contexto

    def add_dia(self, dia, situacao_dia=None):
        # dia = datetime.date
        if not situacao_dia:
            if dia in self.situacao:
                situacao_dia = self.situacao[dia]
            else:
                situacao_dia = SituacaoDia(servidor=self.servidor, dia=dia, contexto=self)
        self.situacao[dia] = situacao_dia

        # apenas agenda o dia para atualização (caso necessário) dos dados "anexos" ao contexto
        self.relatorio_de_ponto_dias_agendados_para_atualizacao.append(dia)
        self.compensacoes_informadas_dias_agendados_para_atualizacao.append(dia)
        self.acompanhamentos_envolvidos_dias_agendados_para_atualizacao.append(dia)
        self.debitos_externos_envolvidos_dias_agendados_para_atualizacao.append(dia)
        self.saldos_externos_envolvidos_dias_agendados_para_atualizacao.append(dia)
        self.historico_funcao_dias_agendados_para_atualizacao.append(dia)
        self.afastamentos_parciais_dias_agendados_para_atualizacao.append(dia)

        return self.get_dia(dia)

    def add_periodo(self, data_inicial, data_final):
        for dia in get_datas_entre(data_inicial, data_final):
            self.add_dia(dia)

    def add_dias(self, dias):
        for dia in dias:
            self.add_dia(dia)

    def get_dia(self, dia, add_se_nao_existir=False):
        # dia = datetime.date
        if dia in self.situacao:
            return self.situacao[dia]  # instância de SituacaoDia
        elif add_se_nao_existir:
            return self.add_dia(dia)
        return None

    @property
    def get_periodo(self):
        return self.periodo_inicial

    @property
    def get_todo_periodo_envolvido(self):
        """
        baseado nos dias dos debitos efetivos
        """
        debito_data_minima = None
        debito_data_maxima = None

        dias_debitos_efetivos = self._get_dias_debitos_efetivos()
        if dias_debitos_efetivos:
            debito_data_minima = min(dias_debitos_efetivos)
            debito_data_maxima = max(dias_debitos_efetivos)

        return [debito_data_minima, debito_data_maxima]

    @property
    def get_relatorio_de_ponto(self):
        return self.relatorio_de_ponto

    @property
    def get_compensacoes_informadas(self):
        return self.compensacoes_informadas

    @property
    def get_acompanhamentos_envolvidos(self):
        return self.acompanhamentos_envolvidos

    @property
    def get_frequencias_as_queryset(self):
        frequencias = Frequencia.objects.none()
        if self.relatorio_de_ponto and 'dias' in self.relatorio_de_ponto:
            for dia_ponto in self.relatorio_de_ponto['dias']:
                frequencias = frequencias | Frequencia.objects.filter(id__in=[frequencia.id for frequencia in dia_ponto['horarios']])
        return frequencias

    # -------------------------------------------------------------------------------------------------------

    @property
    def total_carga_horaria_qtd(self):
        """dentro do período informado"""
        return self._total_qtd(self.periodo_inicial[0], self.periodo_inicial[1], 'carga_horaria_qtd')

    @property
    def total_carga_horaria_trabalhada_qtd(self):
        """dentro do período informado"""
        return self._total_qtd(self.periodo_inicial[0], self.periodo_inicial[1], 'carga_horaria_trabalhada_final_qtd')

    @property
    def total_debito_qtd_considerado(self):
        """dentro do período informado"""
        return self._total_qtd(self.periodo_inicial[0], self.periodo_inicial[1], 'debito_qtd_considerado')

    @property
    def total_debito_qtd_desconsiderado(self):
        """dentro do período informado"""
        return self._total_qtd(self.periodo_inicial[0], self.periodo_inicial[1], 'debito_qtd_desconsiderado')

    @property
    def total_debito_qtd_reposto(self):
        """dentro do período informado"""
        return self._total_qtd(self.periodo_inicial[0], self.periodo_inicial[1], 'debito_qtd_reposto')

    @property
    def total_debito_qtd_restante(self):
        """dentro do período informado"""
        return self._total_qtd(self.periodo_inicial[0], self.periodo_inicial[1], 'debito_qtd_restante')

    @property
    def total_saldo_qtd_considerado(self):
        """dentro do período informado"""
        return self._total_qtd(self.periodo_inicial[0], self.periodo_inicial[1], 'saldo_qtd_considerado')

    @property
    def total_saldo_qtd_desconsiderado(self):
        """dentro do período informado"""
        return self._total_qtd(self.periodo_inicial[0], self.periodo_inicial[1], 'saldo_qtd_desconsiderado')

    @property
    def total_saldo_qtd_utilizado(self):
        """dentro do período informado"""
        return self._total_qtd(self.periodo_inicial[0], self.periodo_inicial[1], 'saldo_qtd_utilizado')

    @property
    def total_saldo_qtd_restante(self):
        """dentro do período informado"""
        return self._total_qtd(self.periodo_inicial[0], self.periodo_inicial[1], 'saldo_qtd_restante')

    # -------------------------------------------------------------------------------------------------------

    @property
    def mensagens_debito_desconsiderado(self):
        """dentro do período informado"""
        return self._get_log(self.periodo_inicial[0], self.periodo_inicial[1], SituacaoDia.LOG_OPERACAO_DEBITO_DESCONSIDERADO)

    @property
    def mensagens_saldo_desconsiderado(self):
        """dentro do período informado"""
        return self._get_log(self.periodo_inicial[0], self.periodo_inicial[1], SituacaoDia.LOG_OPERACAO_SALDO_DESCONSIDERADO)

    @property
    def dias_debito_desconsiderado(self):
        """dentro do período informado"""
        return self._get_dias_com_log(self.periodo_inicial[0], self.periodo_inicial[1], SituacaoDia.LOG_OPERACAO_DEBITO_DESCONSIDERADO)

    @property
    def dias_saldo_desconsiderado(self):
        """dentro do período informado"""
        return self._get_dias_com_log(self.periodo_inicial[0], self.periodo_inicial[1], SituacaoDia.LOG_OPERACAO_SALDO_DESCONSIDERADO)

    # -------------------------------------------------------------------------------------------------------
    def get_totais(
        self,
        before_process_dia: Callable[[SituacaoDia], bool] | None = None,
        complete_process_dia: Callable[[SituacaoDia], None] | None = None,
    ) -> ContextoTotais:
        return ContextoTotais(contexto=self, before_process_dia=before_process_dia, complete_process_dia=complete_process_dia)

    # -------------------------------------------------------------------------------------------------------

    def _get_dias_debitos_efetivos(self):
        """
        são todos os débitos do período informado + os débitos cobertos por cada um dos saldos do período informado
        """
        dias_debitos_efetivos = list(self.dias_debitos.keys())

        if self.dias_saldos:
            for saldo_situacao in list(self.dias_saldos.values()):
                for dia_possivel_debito in saldo_situacao.saldo_dias_dos_debitos:
                    if self.get_dia(dia_possivel_debito, add_se_nao_existir=True).is_debito:
                        dias_debitos_efetivos.append(dia_possivel_debito)

        return set(dias_debitos_efetivos)

    def _get_dias(self, dias, property_condicao=None):
        dias_situacao: OrderedDict[datetime.date, SituacaoDia] = OrderedDict()  # {dia: SituacaoDia, ...}
        for dia in dias:
            if property_condicao:
                if getattr(self.get_dia(dia, add_se_nao_existir=True), property_condicao):
                    dias_situacao[dia] = self.get_dia(dia)
            else:
                dias_situacao[dia] = self.get_dia(dia)
        return dias_situacao

    def _total_qtd(self, data_inicial, data_final, attr):
        total = 0
        for dia in datas_entre(data_inicial, data_final):
            total += getattr(self.get_dia(dia, add_se_nao_existir=True), attr)
        return total

    def _get_log(self, data_inicial, data_final, operacao):
        mensagens = []
        for dia in datas_entre(data_inicial, data_final):
            log = self.get_dia(dia).get_log(operacao)
            if log:
                mensagens.append('<strong>{}</strong>: {} '.format(dia.strftime('%d/%m/%Y'), log))
        return mensagens

    def _get_dias_com_log(self, data_inicial, data_final, operacao):
        dias = []
        for dia in datas_entre(data_inicial, data_final):
            log = self.get_dia(dia).get_log(operacao)
            if log:
                dias.append(dia)
        return dias


class ContextoTotais:
    contexto: Contexto
    before_process_dia: Callable[[SituacaoDia], bool]
    complete_process_dia: Callable[[SituacaoDia], None]

    total_exigido_previo: int  # jornada de trabalho descontada de férias, afastamentos, liberações parciais, etc.
    total_exigido_final: int  # total prévio descontado os abonos da chefia imediata

    total_trabalhado: int  # ponto batido válido

    total_situacao_inicial_debito: int
    total_situacao_inicial_saldo: int

    total_considerado_debito: int
    total_debito_externo: int
    total_desconsiderado_debito: int
    mensagens_debito_desconsiderado: list[str]
    dias_debito_desconsiderado: list[datetime.date]
    total_reposto_debito: int
    total_restante_debito: int

    total_considerado_saldo: int  # inclui os saldos externos ENVOLVIDOS
    total_desconsiderado_saldo: int
    mensagens_saldo_desconsiderado: list[str]
    dias_saldo_desconsiderado: list[datetime.date]
    total_utilizado_saldo: int  # inclui os saldos externos UTILIZADOS
    total_utilizado_saldo_externo: int  # apenas os saldos externos UTILIZADOS
    total_restante_saldo_externo: int  # apenas os saldos externos ENVOLVIDOS
    total_restante_saldo: int  # inclui os saldos externos ENVOLVIDOS

    saldos_externos_envolvidos: QuerySet[SaldoExterno]
    saldos_externos_utilizados: QuerySet[SaldoExterno]

    def __init__(
        self,
        contexto: Contexto,
        before_process_dia: Callable[[SituacaoDia], bool] | None = None,
        complete_process_dia: Callable[[SituacaoDia], None] | None = None,
    ):
        self.contexto = contexto
        self.before_process_dia = before_process_dia
        self.complete_process_dia = complete_process_dia

        assert isinstance(self.contexto, Contexto)

        self.total_exigido_previo = 0
        self.total_exigido_final = 0

        self.total_trabalhado = 0

        self.total_situacao_inicial_debito = 0
        self.total_situacao_inicial_saldo = 0

        self.total_considerado_debito = 0
        self.total_debito_externo = 0
        self.total_desconsiderado_debito = 0
        self.mensagens_debito_desconsiderado = []
        self.dias_debito_desconsiderado = []
        self.total_reposto_debito = 0
        self.total_restante_debito = 0

        self.total_considerado_saldo = 0
        self.total_desconsiderado_saldo = 0
        self.mensagens_saldo_desconsiderado = []
        self.dias_saldo_desconsiderado = []
        self.total_utilizado_saldo = 0
        self.total_utilizado_saldo_externo = 0
        self.total_restante_saldo_externo = 0
        self.total_restante_saldo = 0

        self.saldos_externos_envolvidos = SaldoExterno.objects.none()
        self.saldos_externos_utilizados = SaldoExterno.objects.none()

        self._calc()

    def _calc(self):
        saldos_externos_envolvidos_ids: list[int] = []
        saldos_externos_utilizados_ids: list[int] = []

        for dia in list(self.contexto.dias.values()):
            if self.before_process_dia:
                if not self.before_process_dia(dia):
                    continue

            self.total_exigido_previo += dia.carga_horaria_qtd
            self.total_exigido_final += dia.carga_horaria_final_qtd
            self.total_trabalhado += dia.carga_horaria_trabalhada_final_qtd

            self.total_situacao_inicial_debito += dia.debito_qtd_inicial
            self.total_situacao_inicial_saldo += dia.saldo_qtd_inicial

            self.total_considerado_debito += dia.debito_qtd_considerado
            self.total_debito_externo += dia.debito_externo_qtd
            self.total_desconsiderado_debito += dia.debito_qtd_desconsiderado

            log_debito_desconsiderado = dia.get_log(dia.LOG_OPERACAO_DEBITO_DESCONSIDERADO)
            if log_debito_desconsiderado:
                self.mensagens_debito_desconsiderado.append(f'{dia.dia.strftime("%d/%m/%Y")}: {log_debito_desconsiderado}')
                self.dias_debito_desconsiderado.append(dia.dia)

            self.total_reposto_debito += dia.debito_qtd_reposto
            self.total_restante_debito += dia.debito_qtd_restante

            self.total_considerado_saldo += dia.saldo_qtd_considerado
            self.total_desconsiderado_saldo += dia.saldo_qtd_desconsiderado

            log_saldo_desconsiderado = dia.get_log(dia.LOG_OPERACAO_SALDO_DESCONSIDERADO)
            if log_saldo_desconsiderado:
                self.mensagens_saldo_desconsiderado.append(f'{dia.dia.strftime("%d/%m/%Y")}: {log_saldo_desconsiderado}')
                self.dias_saldo_desconsiderado.append(dia.dia)

            saldo_qtd_utilizado_do_dia = dia.saldo_qtd_utilizado
            saldos_externos_qtd_utilizado_no_dia = dia.saldos_externos_qtd_utilizado_no_dia
            self.total_utilizado_saldo += saldo_qtd_utilizado_do_dia + saldos_externos_qtd_utilizado_no_dia
            self.total_utilizado_saldo_externo += saldos_externos_qtd_utilizado_no_dia
            self.total_restante_saldo += dia.saldo_qtd_restante

            saldos_externos_envolvidos_ids += [saldo_externo.id for saldo_externo in dia.saldos_externos_que_cobrem_o_dia]

            saldos_externos_utilizados_ids += [saldo_externo.id for saldo_externo in dia.saldos_externos_utilizados_no_dia]

            if self.complete_process_dia:
                self.complete_process_dia(dia)

        self.saldos_externos_envolvidos = SaldoExterno.objects.filter(id__in=list(set(saldos_externos_envolvidos_ids)))
        self.saldos_externos_utilizados = SaldoExterno.objects.filter(id__in=list(set(saldos_externos_utilizados_ids)))

        for saldo_externo in self.saldos_externos_envolvidos:
            valor_saldo_externo = saldo_externo.valor_saldo
            valor_saldo_externo_restante = saldo_externo.valor_saldo_restante

            self.total_considerado_saldo += valor_saldo_externo
            self.total_restante_saldo_externo += valor_saldo_externo_restante
            self.total_restante_saldo += valor_saldo_externo_restante

    def as_dict(self):
        result = self.__dict__.copy()

        for key in ['before_process_dia', 'complete_process_dia']:
            if key in result:
                del result[key]

        return result


class SituacaoDiasDados:
    """
    Concentra resultados de consultas ao banco (e outras informações) que serão
    utilizados por cada objeto 'SituacaoDia' relacionado ao contexto.
    """

    contexto: Contexto

    compensacoes_informadas_data_inicio: datetime.date
    compensacoes_informadas_data_fim: datetime.date
    compensacoes_especificas_data_inicio: datetime.date
    compensacoes_especificas_data_fim: datetime.date

    def __init__(self, contexto):
        self.contexto = contexto


class SituacaoDiaOrigemDebito(Enum):
    APENAS_FREQUENCIAS = 1
    APENAS_DEBITOS_EXTERNOS = 2
    QUALQUER = 3


class SituacaoDia:
    """
    Representa a situação do ponto de um dia específico
    """

    LOG_OPERACAO_DEBITO_DESCONSIDERADO = 'debito_desconsiderado'
    LOG_OPERACAO_SALDO_DESCONSIDERADO = 'saldo_desconsiderado'

    def __init__(self, servidor, dia, contexto=None, considera_valor_debito_se_dia_futuro=False):
        self.servidor = servidor
        self.dia = dia  # datetime.date

        assert self.servidor is not None
        assert self.dia is not None

        # uma instância de Contexto (representa o período analisado e origem dos dados)
        self._contexto = contexto

        ###
        # origem dos valores dos débitos

        # informa o "caminho" dos valores do débito
        self._origem_debito = SituacaoDiaOrigemDebito.QUALQUER

        # restringe os débitos externos a uma origem que é uma instância de um Model (ver attrs ponto.models.DebitoExternoCadastro.origem_?)
        self._origem_debito_externo = None  # por padrão, considera todos os débitos externos associados ao dia em análise

        ###
        self._considera_valor_debito_se_dia_futuro = (
            contexto.considera_valor_debito_se_dia_futuro if contexto else considera_valor_debito_se_dia_futuro
        )

        self._reset_attrs()

    def _reset_attrs(self):
        self.logs = {}  # {'operação': ['msg1', 'msg2', ...]}

        # inicializa os atributos que serão calculados nas suas respectivas propriedades

        self._relatorio_ponto_do_dia = None  # {'dia': dia, ... } --> uma linha do relatório de ponto
        self._compensacoes_informadas_para_o_dia = None  # [compensação, compensação, compensação]
        self._acompanhamentos_envolvidos_contendo_o_dia = None
        self._acompanhamentos_envolvidos_contendo_o_dia_como_debito = None
        self._acompanhamentos_envolvidos_contendo_o_dia_como_saldo = None
        self._abonos_do_dia = None
        self._liberacao_tipo_parcial_do_dia = None
        self._liberacao_tipo_evento_do_dia = None
        self._debitos_externos_do_dia = None
        self._saldos_externos_que_cobrem_o_dia = None
        self._saldos_externos_utilizados_no_dia = None
        self._is_dia_em_pgd = None

        # qtd = TODAS AS QUANTIDADES DE CH são em segundos

        self._carga_horaria_inicial_qtd = None
        self._carga_horaria_qtd = None
        self._carga_horaria_trabalhada_bruta_qtd = None

        self._distribuicao_possivel_calculada = None

        self._debito_eh_especifico = None
        self._debito_qtd_inicial = None
        self._debito_via_frequencias_reposicao_qtds = None
        self._debito_via_frequencias_bloqueado_qtd = None
        self._debito_qtd_desconsiderado = None
        self._debito_externo_qtd = None
        self._debito_qtd_considerado = None
        self._debito_dias_dos_saldos = None
        self._debito_qtd_reposto = None
        self._debito_qtd_percentual_reposicao = None
        self._debito_qtd_restante = None
        self._debito_reposicao_distribuicao = None

        self._saldo_qtd_inicial = None
        self._saldo_qtd_maxima_permitida = None
        self._saldo_permitida_utilizacao = None
        self._saldo_qtd_desconsiderado = None
        self._saldo_qtd_considerado = None
        self._saldo_dias_dos_debitos = None
        self._saldo_qtd_utilizado = None
        self._saldo_qtd_percentual_utilizacao = None
        self._saldo_qtd_restante = None
        self._saldo_utilizacao_distribuicao = None
        self._saldos_externos_qtd_utilizado_no_dia = None

    @property
    def contexto(self):
        if self._contexto is None:
            self._contexto = Contexto(self.servidor, self.dia, self.dia)
            # adiciona o dia (e sua situação) atual ao contexto
            self._contexto.add_dia(dia=self.dia, situacao_dia=self)
        return self._contexto

    def _add_log(self, operacao, mensagem):
        if operacao not in self.logs:
            self.logs[operacao] = []
        self.logs[operacao].append(mensagem)

    @property
    def hoje(self):
        return datetime.date.today()

    def get_log(self, operacao):
        log = ''
        if operacao in self.logs:
            log = '. '.join(self.logs[operacao])
        if log:
            log += '. '
        return log

    @property
    def get_log_ch_desconsiderada(self):
        return ''.join([self.get_log(self.LOG_OPERACAO_DEBITO_DESCONSIDERADO), self.get_log(self.LOG_OPERACAO_SALDO_DESCONSIDERADO)])

    # -------------------------------------------------------------------------------------------------------

    @property
    def origem_debito(self) -> SituacaoDiaOrigemDebito:
        return self._origem_debito

    @property
    def origem_debito_externo(self) -> Model:
        return self._origem_debito_externo

    @property
    def origem_debito_qualquer(self) -> bool:
        return self.origem_debito == SituacaoDiaOrigemDebito.QUALQUER

    @property
    def origem_debito_apenas_via_frequencias(self) -> bool:
        return self.origem_debito == SituacaoDiaOrigemDebito.APENAS_FREQUENCIAS

    @property
    def origem_debito_apenas_via_debitos_externos(self) -> bool:
        return self.origem_debito == SituacaoDiaOrigemDebito.APENAS_DEBITOS_EXTERNOS

    def set_origem_debito(self, origem_debito: SituacaoDiaOrigemDebito, origem_debito_externo: Model = None):
        self._origem_debito = origem_debito
        self._origem_debito_externo = origem_debito_externo
        self._reset_attrs()

    # -------------------------------------------------------------------------------------------------------

    @property
    def relatorio_ponto_do_dia(self):
        """
        relatorio_ponto_do_dia = {'dia': ? (date), 'carga_horaria_do_dia': ? (int q indica horas), ... }
        """
        if self._relatorio_ponto_do_dia is None:
            if self.origem_debito_apenas_via_debitos_externos:
                self._relatorio_ponto_do_dia = {}
            else:
                self._relatorio_ponto_do_dia = self.contexto.relatorio_de_ponto_get_dia(self.dia)
        return self._relatorio_ponto_do_dia

    @property
    def ha_frequencia_no_dia(self):
        ponto_do_dia = self.relatorio_ponto_do_dia
        return ponto_do_dia and ponto_do_dia['duracao_segundos'] > 0

    @property
    def compensacao_info_do_dia(self) -> CompensacaoInfoDia:
        # retorna informações sobre compensação do dia
        return CompensacaoInfoDia(self)

    @property
    def relatorio_ponto_do_dia_with_compensacao_info_do_dia(self) -> dict:
        # retorna o próprio relatório do dia, atualizado
        # com informações sobre compensação do dia para fins de relatório de frequências
        if self.relatorio_ponto_do_dia:
            frequencia_do_dia = self.relatorio_ponto_do_dia

            compensacao_info = self.compensacao_info_do_dia

            frequencia_do_dia.update({'compensacao': compensacao_info.as_dict()})

            return {'funcionario': self.contexto.servidor, 'dias': [frequencia_do_dia]}
        return {}

    # -----------------------------------------------------
    @property
    def compensacoes_informadas_para_o_dia(self) -> list[HorarioCompensacao]:
        if self._compensacoes_informadas_para_o_dia is None:
            self._compensacoes_informadas_para_o_dia = self.contexto.compensacoes_informadas_get_dia(self.dia)
        return self._compensacoes_informadas_para_o_dia

    @property
    def acompanhamentos_envolvidos_contendo_o_dia(self) -> list[RecessoOpcaoEscolhida]:
        if self._acompanhamentos_envolvidos_contendo_o_dia is None:
            self._acompanhamentos_envolvidos_contendo_o_dia = self.contexto.acompanhamentos_envolvidos_get_dia(self.dia)
        return self._acompanhamentos_envolvidos_contendo_o_dia

    @property
    def acompanhamentos_envolvidos_contendo_o_dia_como_debito(self) -> list[RecessoOpcaoEscolhida]:
        if self._acompanhamentos_envolvidos_contendo_o_dia_como_debito is None:
            acompanhamentos_envolvidos_contendo_o_dia_como_debito = self.contexto.acompanhamentos_envolvidos_get_dia(self.dia, dia_como_saldo=False)

            # chamado 63394: É possível que um servidor venha trabalhar normalmente mesmo em um dia que ele
            # mesmo escolheu para débito. Nesse caso, o dia passa a ser normal (podendo gerar saldo ou débito)
            acompanhamentos_envolvidos_contendo_o_dia_como_debito_final = []
            for acompanhamento in acompanhamentos_envolvidos_contendo_o_dia_como_debito:
                # se a opção de compensação permite que o público alvo escolha livremente os dias
                # e o dia em questão tem frequências, então esse dia deixa de ser um débito com um acompanhamento
                # específico
                if acompanhamento.recesso_opcao.is_permite_escolha_pelos_servidores:
                    if not self.ha_frequencia_no_dia:
                        acompanhamentos_envolvidos_contendo_o_dia_como_debito_final.append(acompanhamento)
                else:
                    acompanhamentos_envolvidos_contendo_o_dia_como_debito_final.append(acompanhamento)

            self._acompanhamentos_envolvidos_contendo_o_dia_como_debito = acompanhamentos_envolvidos_contendo_o_dia_como_debito_final

        return self._acompanhamentos_envolvidos_contendo_o_dia_como_debito

    @property
    def acompanhamentos_envolvidos_contendo_o_dia_como_saldo(self) -> list[RecessoOpcaoEscolhida]:
        if self._acompanhamentos_envolvidos_contendo_o_dia_como_saldo is None:
            self._acompanhamentos_envolvidos_contendo_o_dia_como_saldo = self.contexto.acompanhamentos_envolvidos_get_dia(
                self.dia, dia_como_debito=False
            )
        return self._acompanhamentos_envolvidos_contendo_o_dia_como_saldo

    @property
    def debitos_externos_do_dia(self) -> list[DebitoExterno]:
        if self._debitos_externos_do_dia is None:
            if self.origem_debito_apenas_via_frequencias:
                self._debitos_externos_do_dia = []
            else:
                self._debitos_externos_do_dia = self.contexto.debitos_externos_envolvidos_get_dia(self.dia, self.origem_debito_externo)
        return self._debitos_externos_do_dia

    @property
    def has_debitos_externos(self) -> bool:
        return any(self.debitos_externos_do_dia)

    @property
    def saldos_externos_que_cobrem_o_dia(self) -> list[SaldoExterno]:
        if self._saldos_externos_que_cobrem_o_dia is None:
            self._saldos_externos_que_cobrem_o_dia = self.contexto.saldos_externos_envolvidos_get_dia(self.dia)
        return self._saldos_externos_que_cobrem_o_dia

    @property
    def has_saldos_externos_que_cobrem_o_dia(self) -> bool:
        return any(self.saldos_externos_que_cobrem_o_dia)

    @property
    def saldos_externos_utilizados_no_dia(self) -> list[SaldoExterno]:
        """saldos externos utilizados NO dia (repondo o dia em questão)"""
        if self._saldos_externos_utilizados_no_dia is None:
            saldos_externos_utilizados_no_dia = []

            for compensacao in self.compensacoes_informadas_para_o_dia:
                if compensacao.data_aplicacao == self.dia and compensacao.saldo_externo_compensacao:
                    # informe de compensação que utilizou um saldo externo
                    if compensacao.saldo_externo_compensacao not in saldos_externos_utilizados_no_dia:
                        saldos_externos_utilizados_no_dia.append(compensacao.saldo_externo_compensacao)

            self._saldos_externos_utilizados_no_dia = saldos_externos_utilizados_no_dia

        return self._saldos_externos_utilizados_no_dia

    @property
    def has_saldos_externos_utilizados_no_dia(self) -> bool:
        return any(self.saldos_externos_utilizados_no_dia)

    @property
    def saldos_externos_qtd_utilizado_no_dia(self) -> int:
        if self._saldos_externos_qtd_utilizado_no_dia is None:
            saldos_externos_utilizados = self.saldos_externos_utilizados_no_dia

            self._saldos_externos_qtd_utilizado_no_dia = 0

            for compensacao in self.compensacoes_informadas_para_o_dia:
                if compensacao.data_aplicacao == self.dia and compensacao.saldo_externo_compensacao in saldos_externos_utilizados:
                    # informe de compensação que utilizou um saldo externo para repor o dia em questão
                    self._saldos_externos_qtd_utilizado_no_dia += Frequencia.time_para_segundos(compensacao.ch_compensada)

            if self._saldos_externos_qtd_utilizado_no_dia is None:
                self._saldos_externos_qtd_utilizado_no_dia = 0

        return self._saldos_externos_qtd_utilizado_no_dia

    # -----------------------------------------------------

    def get_funcoes_no_dia(self, liberado_frequencia: bool = False) -> list[ServidorFuncaoHistorico]:
        funcoes_no_dia = []
        for funcao in self.contexto.historico_funcao_get_dia(self.dia):
            if liberado_frequencia:
                funcao_add = funcao.eh_liberado_frequencia
                if funcao_add:
                    funcoes_no_dia.append(funcao)
            else:
                funcoes_no_dia.append(funcao)
        return funcoes_no_dia

    def get_funcoes_liberadas_do_ponto_no_dia(self) -> list[ServidorFuncaoHistorico]:
        return self.get_funcoes_no_dia(liberado_frequencia=True)

    @property
    def has_funcao_no_dia(self) -> bool:
        return any(self.get_funcoes_no_dia())

    @property
    def has_funcao_liberada_do_ponto_no_dia(self) -> bool:
        return any(self.get_funcoes_liberadas_do_ponto_no_dia())

    # -------------------------------------------------------------------------------------------------------
    @property
    def carga_horaria_maxima_permitida_para_o_dia(self):
        # 10 horas
        ch_qtd_maxima_diaria = 10 * 60 * 60  # em segundos

        # trata liberação parcial (pode ser que a máxima exigida seja menor que as 10h)
        liberacao_parcial = self.liberacao_tipo_parcial_do_dia
        if liberacao_parcial:
            ch_qtd_maxima_diaria = liberacao_parcial.ch_maxima_exigida * 60 * 60  # em segundos

        return ch_qtd_maxima_diaria

    @property
    def abonos_do_dia(self) -> list[AbonoChefia]:
        if self._abonos_do_dia is None:
            ponto_do_dia = self.relatorio_ponto_do_dia
            if 'abonos_chefia' in ponto_do_dia:
                self._abonos_do_dia = ponto_do_dia['abonos_chefia']
            self._abonos_do_dia = self._abonos_do_dia or []
        return self._abonos_do_dia

    @property
    def liberacao_tipo_parcial_do_dia(self):
        if self._liberacao_tipo_parcial_do_dia is None:
            ponto_do_dia = self.relatorio_ponto_do_dia
            if ponto_do_dia:
                for liberacao in ponto_do_dia.get('liberacoes', []):
                    if liberacao.tipo == TipoLiberacao.get_numero(TipoLiberacao.LIBERACAO_PARCIAL):
                        self._liberacao_tipo_parcial_do_dia = liberacao
        return self._liberacao_tipo_parcial_do_dia

    @property
    def liberacao_tipo_evento_do_dia(self):
        if self._liberacao_tipo_evento_do_dia is None:
            ponto_do_dia = self.relatorio_ponto_do_dia
            if ponto_do_dia:
                for liberacao in ponto_do_dia.get('liberacoes', []):
                    if liberacao.tipo == TipoLiberacao.get_numero(TipoLiberacao.EVENTO):
                        self._liberacao_tipo_evento_do_dia = liberacao
        return self._liberacao_tipo_evento_do_dia

    @property
    def carga_horaria_inicial_qtd(self):
        """Retorna a carga horária inicial exigida para o dia em segundos.

        Returns:
            int: carga horária inicial em segundos, ou ``0`` para dias
                sem carga horária exigida.
        """
        if self._carga_horaria_inicial_qtd is None:
            # {'dia': ? (date), 'carga_horaria_do_dia': ? (int q indica horas), ... }
            ponto_do_dia = self.relatorio_ponto_do_dia

            if self.is_dia_que_pode_haver_debito:
                if 'carga_horaria_do_dia' in ponto_do_dia:
                    self._carga_horaria_inicial_qtd = ponto_do_dia['carga_horaria_do_dia'] * 60 * 60  # em segundos

                if self.is_sabado or self.is_domingo:
                    self._carga_horaria_inicial_qtd = 0  # nada é exigido

            if self._carga_horaria_inicial_qtd is None:
                self._carga_horaria_inicial_qtd = 0
        return self._carga_horaria_inicial_qtd

    @property
    def carga_horaria_qtd(self):
        """ch exigida PRÉVIA para o dia"""
        if self._carga_horaria_qtd is None:
            self._carga_horaria_qtd = self.carga_horaria_inicial_qtd

            # trata a liberação parcial, que pode reduzir a jornada de trabalho
            # até esse ponto
            liberacao_parcial = self.liberacao_tipo_parcial_do_dia
            if liberacao_parcial:
                ch_maxima_exigida_pela_instituicao = liberacao_parcial.ch_maxima_exigida * 60 * 60  # segundos
                if self._carga_horaria_qtd > ch_maxima_exigida_pela_instituicao:
                    self._carga_horaria_qtd = ch_maxima_exigida_pela_instituicao

            if self._carga_horaria_qtd is None:
                self._carga_horaria_qtd = 0
        return self._carga_horaria_qtd

    @property
    def carga_horaria_final_qtd(self):
        """ch exigida FINAL para o dia"""
        carga_horaria_final = self.carga_horaria_qtd

        # trata os abonos
        nao_precisa_repor = self.debito_via_frequencias_reposicao_qtds[1]
        nao_pode_repor = self.debito_via_frequencias_bloqueado_qtd
        carga_horaria_final -= nao_precisa_repor + nao_pode_repor

        return carga_horaria_final

    @property
    def carga_horaria_trabalhada_bruta_qtd(self):
        """carga horária trabalhada BRUTA no dia"""

        if self._carga_horaria_trabalhada_bruta_qtd is None:
            ponto_do_dia = self.relatorio_ponto_do_dia

            if 'duracao_segundos_bruto' in ponto_do_dia:
                self._carga_horaria_trabalhada_bruta_qtd = ponto_do_dia['duracao_segundos_bruto']

            if self._carga_horaria_trabalhada_bruta_qtd is None:
                self._carga_horaria_trabalhada_bruta_qtd = 0

        return self._carga_horaria_trabalhada_bruta_qtd

    @property
    def carga_horaria_trabalhada_final_qtd(self):
        """carga horária trabalhada FINAL no dia"""

        carga_horaria_trabalhada_final = self.carga_horaria_trabalhada_bruta_qtd

        # máximo 10 horas por dia
        ch_qtd_maxima_diaria = 10 * 60 * 60  # em segundos
        if carga_horaria_trabalhada_final > ch_qtd_maxima_diaria:
            carga_horaria_trabalhada_final = ch_qtd_maxima_diaria

        # desconta os abonos de chefia com carga horária descontada informada
        for abono_do_dia in self.abonos_do_dia:
            if abono_do_dia.ch_descontada:
                carga_horaria_trabalhada_final -= abono_do_dia.ch_descontada

        if carga_horaria_trabalhada_final <= 0:
            carga_horaria_trabalhada_final = 0

        return carga_horaria_trabalhada_final

    @property
    def is_sabado_ou_domingo(self):
        return self.is_sabado or self.is_domingo

    @property
    def is_sabado(self):
        return self.dia.weekday() == 5

    @property
    def is_domingo(self):
        return self.dia.weekday() == 6

    @property
    def is_dia_possivel(self):
        escopo_data_minima = self.contexto.data_inicio_a_cobrar_compensacao
        escopo_data_maxima = self.contexto.data_fim_a_cobrar_compensacao or self.dia
        return escopo_data_minima and escopo_data_minima <= self.dia <= escopo_data_maxima

    @property
    def is_dia_util(self):
        """é um dia útil para o servidor?
        com informações extras

        :return [True/False, ['infor extra', 'infor extra', 'infor extra', ...]]
        """
        if not self.is_dia_possivel:
            return False, []

        informacoes_extras = []
        ponto_do_dia = self.relatorio_ponto_do_dia or {}

        # condição 1 (não pode ser sáb ou dom)
        condicao_1 = not self.is_sabado_ou_domingo
        if not condicao_1:
            if self.is_sabado:
                informacoes_extras.append('Sábado')
            elif self.is_domingo:
                informacoes_extras.append('Domingo')

        # condição 2 (não pode haver qualquer afastamento, liberação, viagens ou férias)
        afastamentos = [ponto_do_dia.get('afastamentos_siape'), ponto_do_dia.get('afastamentos_rh')]

        liberacoes = [ponto_do_dia.get('liberacoes')]

        viagens_ferias = [ponto_do_dia.get('viagens_scdp'), ponto_do_dia.get('ferias')]

        # ocorrencias = [[obj, obj, obj], [obj, obj, obj], [obj, obj, str, str]]
        ocorrencias = afastamentos + liberacoes + viagens_ferias

        condicao_2 = not any(ocorrencias)
        if not condicao_2:
            for tipo_ocorrencias in ocorrencias:
                if tipo_ocorrencias:
                    if isinstance(tipo_ocorrencias, str):
                        try:
                            informacoes_extras.append(tipo_ocorrencias)
                        except Exception:
                            pass
                    else:
                        for ocorrencia in tipo_ocorrencias:
                            try:
                                informacoes_extras.append(str(ocorrencia))
                            except Exception:
                                pass

        # dia útil ?
        is_dia_util = condicao_1 and condicao_2

        # ordem de precedência
        # viagens_ferias > afastamentos > liberações

        if not is_dia_util:
            if not any(viagens_ferias):
                # trata exceções em afastamento/liberações que ainda podem tornar o dia como útil
                if any(afastamentos):
                    # trata afastamento parcial
                    afastamentos_parciais = self.contexto.afastamentos_parciais_get_dia(self.dia)

                    for afastamento in afastamentos:
                        if afastamento in afastamentos_parciais:
                            ch_do_dia = ponto_do_dia['carga_horaria_do_dia'] * 60 * 60
                            if ch_do_dia > 0:
                                # o dia é útil conforme contexto:
                                #   - não há férias ou viagens
                                #   - há afastamento parcial
                                #   - CH do dia é maior que zero (CH que deve ser cumprida!!!)
                                is_dia_util = True
                                break
                elif any(liberacoes):
                    # trata liberacao parcial
                    if self.liberacao_tipo_parcial_do_dia:
                        # o dia é útil conforme contexto:
                        #   - não há férias ou viagens
                        #   - não há afastamentos
                        #   - há liberação parcial
                        #   - CH que deve ser cumprida até o limite definido no cadastro da liberação parcial
                        is_dia_util = True

        return is_dia_util, informacoes_extras

    @property
    def is_dia_que_pode_haver_debito(self):
        """considera a situação inicial antes de qualquer fonte de débito (via frequência, via débitos externos)"""

        if not self.is_dia_possivel:
            return False

        # o dia é útil para o servidor e não tem função liberada de bater ponto
        condicao_1 = self.is_dia_util[0] and not self.has_funcao_liberada_do_ponto_no_dia

        if not self.servidor.eh_docente:
            return condicao_1
        else:
            ###
            # trata servidor docente
            # o ponto docente está ativado
            # o docente não tem função liberada de bater o ponto no dia
            # o dia não é um débito de um acompanhamento específico
            # então, o cálculo de débitos está fora do escopo deste módulo
            condicao_2 = self.contexto.ponto_docente_ativado and not self.has_funcao_liberada_do_ponto_no_dia and not self.is_debito_especifico

            if condicao_2:
                return False
            ###

            return condicao_1

    @property
    def is_dia_que_pode_haver_saldo(self):
        """Verifica se o dia pode gerar saldo positivo de horas.

        Returns:
            bool: ``True`` se o dia pode gerar saldo, ``False`` caso
                contrário.
        """
        if not self.is_dia_possivel:
            return False

        # regra geral
        condicao_1 = any([self.is_sabado_ou_domingo, self.is_dia_que_pode_haver_debito])

        # trata o tipo de liberação EVENTO
        # o dia em questão possui uma liberação e isso, por padrão, impossibilita a geração de saldo,
        # exceto se a liberação é do tipo EVENTO
        condicao_2 = self.liberacao_tipo_evento_do_dia is not None

        # trata servidor docente
        # o ponto docente está ativado
        # o docente não tem função liberada de bater o ponto no dia
        # então, o cálculo de saldos está fora do escopo deste módulo
        condicao_3 = all([self.servidor.eh_docente, self.contexto.ponto_docente_ativado, not self.has_funcao_liberada_do_ponto_no_dia])

        pode_gerar_saldo = any([condicao_1, condicao_2, condicao_3])

        return pode_gerar_saldo

    def get_reposicao_distribuicao_for_display(self, distribuicao_full: list[tuple[datetime.date, int, list[HorarioCompensacao]]]):
        # omite períodos longos a partir de 20 dias sem nenhuma informação sobre compensações,
        # mas coloca uma informação que o período está vazio
        # também coloca a posição ordinal do dia na sequência

        distribuicao_for_display = OrderedDict()

        periodo_vazio_seq = 0
        periodo_vazio_processando = False
        periodo_vazio_data_inicio: datetime.date = None
        periodo_vazio_data_fim: datetime.date = None
        periodo_vazio_dias: OrderedDict[datetime.date, int] = OrderedDict()  # dia: ordem

        dia_ordem = 0
        dia_ordem_maxima = len(distribuicao_full)

        for dia, ch_compensacao, compensacoes in distribuicao_full:
            dia_ordem += 1

            if dia_ordem == 1:
                # exibe o primeiro dia
                distribuicao_for_display[dia] = [f'{dia_ordem}º) {dia.strftime("%d/%m/%Y")}', ch_compensacao, compensacoes]
                continue
            elif dia_ordem == dia_ordem_maxima:
                # prorroga a exibição do último dia
                continue

            if ch_compensacao:
                if periodo_vazio_processando:
                    if len(periodo_vazio_dias) >= 20:
                        periodo_vazio_display = f'{periodo_vazio_data_inicio.strftime("%d/%m/%Y")} a '
                        periodo_vazio_display += f'{periodo_vazio_data_fim.strftime("%d/%m/%Y")} '
                        periodo_vazio_display += f'(nesse período há {len(periodo_vazio_dias)} dias sem informações a exibir)'
                        distribuicao_for_display[f'empty_{periodo_vazio_seq}'][0] = periodo_vazio_display
                    else:
                        del distribuicao_for_display[f'empty_{periodo_vazio_seq}']

                        for dia_, dia_ordem_ in periodo_vazio_dias.items():
                            distribuicao_for_display[dia_] = [f'{dia_ordem_}º) {dia_.strftime("%d/%m/%Y")}', 0, []]

                    periodo_vazio_processando = False
                    periodo_vazio_data_inicio = None
                    periodo_vazio_data_fim = None
                    periodo_vazio_dias = OrderedDict()

                distribuicao_for_display[dia] = [f'{dia_ordem}º) {dia.strftime("%d/%m/%Y")}', ch_compensacao, compensacoes]
            else:
                if not periodo_vazio_processando:
                    periodo_vazio_seq += 1
                    periodo_vazio_processando = True
                    periodo_vazio_data_inicio = dia
                    distribuicao_for_display[f'empty_{periodo_vazio_seq}'] = ['?', 0, []]
                periodo_vazio_data_fim = dia
                periodo_vazio_dias[dia] = dia_ordem

        if periodo_vazio_processando:
            if len(periodo_vazio_dias) >= 20:
                periodo_vazio_display = f'{periodo_vazio_data_inicio.strftime("%d/%m/%Y")} a '
                periodo_vazio_display += f'{periodo_vazio_data_fim.strftime("%d/%m/%Y")} '
                periodo_vazio_display += f'(nesse período há {len(periodo_vazio_dias)} dias sem informações a exibir)'
                distribuicao_for_display[f'empty_{periodo_vazio_seq}'][0] = periodo_vazio_display
            else:
                del distribuicao_for_display[f'empty_{periodo_vazio_seq}']

                for dia_, dia_ordem_ in periodo_vazio_dias.items():
                    distribuicao_for_display[dia_] = [f'{dia_ordem_}º) {dia_.strftime("%d/%m/%Y")}', 0, []]

        # exibe o último dia
        if dia_ordem_maxima:
            ultimo_dia = distribuicao_full[dia_ordem_maxima - 1]
            distribuicao_for_display[dia] = [f'{dia_ordem_maxima}º) {ultimo_dia[0].strftime("%d/%m/%Y")}', ultimo_dia[1], ultimo_dia[2]]

        return list(distribuicao_for_display.values())

    @property
    def is_dia_em_pgd(self):
        if self._is_dia_em_pgd is None:
            self._is_dia_em_pgd = self.contexto.dia_estah_em_pgd(self.dia)
        return self._is_dia_em_pgd

    # -------------------------------------------------------------------------------------------------------
    @property
    def considera_valor_debito_se_dia_futuro(self):
        return self._considera_valor_debito_se_dia_futuro

    def set_considera_valor_debito_se_dia_futuro(self, considera: bool):
        self._considera_valor_debito_se_dia_futuro = considera
        self._reset_attrs()

    @property
    def is_debito_inicialmente(self):
        if not self.considera_valor_debito_se_dia_futuro:
            # o futuro, para fins de débito, é de hoje em diante
            # se o dia está no futuro e não é um débito específico,
            # então não há, ainda, o que se falar em débito para o dia
            if self.dia >= self.hoje and not self.is_debito_especifico:
                return False
        return self.is_dia_que_pode_haver_debito and (
            self.carga_horaria_trabalhada_final_qtd - self.carga_horaria_qtd < 0
        )  # trabalhou menos que a exigida?

    @property
    def is_debito_especifico(self):
        """é um débito específico em acompanhamento?"""
        if self._debito_eh_especifico is None:
            self._debito_eh_especifico = any(self.acompanhamentos_envolvidos_contendo_o_dia_como_debito)

            if self._debito_eh_especifico is None:
                self._debito_eh_especifico = False
        return self._debito_eh_especifico

    @property
    def debito_qtd_inicial(self):
        """origem da informação: frequências (ponto batido)"""
        if self._debito_qtd_inicial is None:
            if self.is_debito_inicialmente:
                self._debito_qtd_inicial = (self.carga_horaria_trabalhada_final_qtd - self.carga_horaria_qtd) * -1

            if self._debito_qtd_inicial is None:
                self._debito_qtd_inicial = 0
        return self._debito_qtd_inicial

    @property
    def debito_via_frequencias_reposicao_qtds(self) -> tuple[int, int]:  # return (qtd precisa repor, qtd não precisa repor)
        """abonos da chefia: quanto precisa repor? quanto não precisa repor?

        ATT: nesse caso, abonos parciais sobrepõem a ação de abonos não parciais
            Ex de um dia com N abonos de chefia:
                abono parcial de 2h = AbonoChefia.ABONADO_COM_COMPENSACAO
                    repor = 2h
                    não repor = 0h
                abono parcial de 2h = AbonoChefia.ABONADO
                    repor = 0h
                    não repor = 2h
                abono não parcial   = AbonoChefia.ABONADO_COM_COMPENSACAO
                    repor = TUDO
                    não repor = 0h
                abono não parcial   = AbonoChefia.ABONADO
                    repor = 0h
                    não repor = TUDO
                abono não parcial   = AbonoChefia.TRABALHO_REMOTO (não aplicável para abonos parciais)
                    repor = 0h
                    não repor = TUDO

                afinal, repor 2h, repor 0h ou repor TUDO ???
                    R: conforme a prioridade dada aos abonos parciais, então será
                    repor 2h devido ao abono parcial de 2h = AbonoChefia.ABONADO_COM_COMPENSACAO.

        precisa repor:
            acao_abono = AbonoChefia.ABONADO_COM_COMPENSACAO
            repor = totalmente
                no caso de abono não parcial
            repor = parcialmente
                conforme cada abono parcial

        não precisa repor:
            acao_abono = AbonoChefia.ABONADO
                msg de log única
                    se houver abono não parcial
                msg de log por ch solicitada
                    conforme cada abono parcial
            acao_abono = AbonoChefia.TRABALHO_REMOTO
                msg de log única
                    no caso de abono não parcial
            repor = 0
        """
        if self._debito_via_frequencias_reposicao_qtds is None:
            abonos_do_dia = self.abonos_do_dia

            tem_abono_com_compensacao_parcial = False
            tem_abono_sem_compensacao_parcial = False
            tem_abono_sem_compensacao_total = False
            tem_abono_trabalho_remoto = False

            ab_parcial_precisa_repor_qtd = 0  # em segundos
            ab_total_precisa_repor_qtd = 0  # em segundos
            ab_parcial_nao_precisa_repor_qtd = 0  # em segundos
            ab_total_nao_precisa_repor_qtd = 0  # em segundos

            for abono_do_dia in abonos_do_dia:
                # precisa repor?
                if abono_do_dia.acao_abono == AbonoChefia.ABONADO_COM_COMPENSACAO:
                    if abono_do_dia.eh_abono_parcial:
                        # conforme o que foi solicitado no abono parcial
                        ab_parcial_precisa_repor_qtd += abono_do_dia.solicitacao_abono_parcial.ch_solicitada
                        tem_abono_com_compensacao_parcial = True
                    else:
                        ab_total_precisa_repor_qtd = self.debito_qtd_inicial  # "TUDO"
                # não precisa repor?
                else:
                    if abono_do_dia.acao_abono == AbonoChefia.ABONADO:
                        if abono_do_dia.eh_abono_parcial:
                            # conforme o que foi solicitado no abono parcial
                            ab_parcial_nao_precisa_repor_qtd += abono_do_dia.solicitacao_abono_parcial.ch_solicitada
                            tem_abono_sem_compensacao_parcial = True
                            self._add_log(
                                self.LOG_OPERACAO_DEBITO_DESCONSIDERADO,
                                f'{abono_do_dia.solicitacao_abono_parcial.ch_solicitada_display}: Abonado Sem Compensação pela Chefia Imediata',
                            )
                        else:
                            ab_total_nao_precisa_repor_qtd = self.debito_qtd_inicial  # "TUDO"
                            tem_abono_sem_compensacao_total = True
                    elif abono_do_dia.acao_abono == AbonoChefia.TRABALHO_REMOTO:
                        ab_total_nao_precisa_repor_qtd = self.debito_qtd_inicial  # "TUDO"
                        tem_abono_trabalho_remoto = True

            # Prioridade do valor: abono parcial.
            precisa_repor_qtd = ab_parcial_precisa_repor_qtd or ab_total_precisa_repor_qtd
            nao_precisa_repor_qtd = ab_parcial_nao_precisa_repor_qtd or ab_total_nao_precisa_repor_qtd

            # Limite dos valores.
            precisa_repor_qtd = min(
                [
                    precisa_repor_qtd,  # Pode haver vários abonos que ultrapassem o valor do débito.
                    self.debito_qtd_inicial,
                ]
            )
            nao_precisa_repor_qtd = min(
                [
                    nao_precisa_repor_qtd,  # Pode haver vários abonos que ultrapassem o valor do débito.
                    self.debito_qtd_inicial,
                ]
            )

            # Débito não coberto por abonos parciais.
            precisa_repor_qtd += self.debito_qtd_inicial - (precisa_repor_qtd + nao_precisa_repor_qtd)

            self._debito_via_frequencias_reposicao_qtds = (precisa_repor_qtd, nao_precisa_repor_qtd)

            if tem_abono_sem_compensacao_total:
                if tem_abono_sem_compensacao_parcial:
                    self._add_log(
                        self.LOG_OPERACAO_DEBITO_DESCONSIDERADO,
                        'Abonado Sem Compensação pela Chefia Imediata. Porém foi tornado sem efeito para fins de débito devido aos abonos parciais',
                    )
                else:
                    self._add_log(self.LOG_OPERACAO_DEBITO_DESCONSIDERADO, 'Abonado Sem Compensação pela Chefia Imediata')

            if tem_abono_trabalho_remoto:
                if tem_abono_com_compensacao_parcial or tem_abono_sem_compensacao_parcial:
                    self._add_log(
                        self.LOG_OPERACAO_DEBITO_DESCONSIDERADO,
                        'Trabalho remoto validado pela Chefia Imediata. Porém foi tornado sem efeito para fins de débito devido aos abonos parciais',
                    )
                else:
                    self._add_log(self.LOG_OPERACAO_DEBITO_DESCONSIDERADO, 'Trabalho remoto validado pela Chefia Imediata')

            if self._debito_via_frequencias_reposicao_qtds is None:
                self._debito_via_frequencias_reposicao_qtds = (self.debito_qtd_inicial, 0)  # "TUDO" e zero

        return self._debito_via_frequencias_reposicao_qtds

    @property
    def debito_via_frequencias_bloqueado_qtd(self):
        """
        abonos da chefia: quanto não pode repor?

        ATT: nesse caso, abonos parciais sobrepõem a ação de abonos não parciais
            Ex de um dia com N abonos de chefia:
                abono parcial de 2h = AbonoChefia.ABONADO_COM_COMPENSACAO
                    bloqueado = 0h
                abono parcial de 2h = AbonoChefia.ABONADO
                    bloqueado = 0h
                abono parcial de 2h = AbonoChefia.NAO_ABONADO
                    bloqueado = 2h
                abono não parcial   = AbonoChefia.ABONADO_COM_COMPENSACAO
                    bloqueado = 0h
                abono não parcial   = AbonoChefia.ABONADO
                    bloqueado = 0h
                abono não parcial   = AbonoChefia.NAO_ABONADO
                    bloqueado = TUDO

                afinal, bloqueado 0h, bloqueado 2h ou bloqueado TUDO ???
                    R: conforme a prioridade dada aos abonos parciais, então será
                    bloqueado 2h devido ao abono parcial de 2h = AbonoChefia.NAO_ABONADO.

        não pode repor:
            AbonoChefia.NAO_ABONADO
        """
        if self._debito_via_frequencias_bloqueado_qtd is None:
            abonos_do_dia = self.abonos_do_dia

            tem_abono_nao_abonado_parcial = False
            tem_abono_nao_abonado_total = False

            ab_parcial_nao_pode_repor_qtd = 0  # em segundos
            ab_total_nao_pode_repor_qtd = 0  # em segundos

            for abono_do_dia in abonos_do_dia:
                # não pode repor?
                if abono_do_dia.acao_abono == AbonoChefia.NAO_ABONADO:
                    if abono_do_dia.eh_abono_parcial:
                        ab_parcial_nao_pode_repor_qtd += (
                            abono_do_dia.solicitacao_abono_parcial.ch_solicitada
                        )  # conforme o que foi solicitado no abono parcial
                        tem_abono_nao_abonado_parcial = True
                        self._add_log(
                            self.LOG_OPERACAO_DEBITO_DESCONSIDERADO,
                            f'{abono_do_dia.solicitacao_abono_parcial.ch_solicitada_display}: Não Abonado pela Chefia Imediata',
                        )
                    else:
                        ab_total_nao_pode_repor_qtd = self.debito_qtd_inicial  # "TUDO"
                        tem_abono_nao_abonado_total = True

            # Prioridade do valor: abono parcial.
            nao_pode_repor_qtd = ab_parcial_nao_pode_repor_qtd or ab_total_nao_pode_repor_qtd

            # Limite dos valores.
            nao_pode_repor_qtd = min(
                [
                    nao_pode_repor_qtd,  # Pode haver vários abonos que ultrapassem o valor do débito.
                    self.debito_qtd_inicial,
                ]
            )

            self._debito_via_frequencias_bloqueado_qtd = nao_pode_repor_qtd

            if tem_abono_nao_abonado_total:
                if tem_abono_nao_abonado_parcial:
                    self._add_log(
                        self.LOG_OPERACAO_DEBITO_DESCONSIDERADO,
                        'Não Abonado pela Chefia Imediata. Porém foi tornado sem efeito para fins de débito devido aos abonos parciais',
                    )
                else:
                    self._add_log(self.LOG_OPERACAO_DEBITO_DESCONSIDERADO, 'Não Abonado pela Chefia Imediata')

            if self._debito_via_frequencias_bloqueado_qtd is None:
                self._debito_via_frequencias_bloqueado_qtd = 0

        return self._debito_via_frequencias_bloqueado_qtd

    @property
    def debito_qtd_desconsiderado(self):
        """com os motivos"""
        if self._debito_qtd_desconsiderado is None:
            if self.debito_qtd_inicial:
                self._debito_qtd_desconsiderado = 0

                self._debito_qtd_desconsiderado += self.debito_via_frequencias_reposicao_qtds[1]
                self._debito_qtd_desconsiderado += self.debito_via_frequencias_bloqueado_qtd

                # trata liberação parcial
                liberacao_parcial = self.liberacao_tipo_parcial_do_dia
                if liberacao_parcial:
                    ch_maxima_exigida_pela_instituicao = liberacao_parcial.ch_maxima_exigida * 60 * 60  # em segundos
                    ch_exigida_inicial_servidor = self.carga_horaria_inicial_qtd
                    ch_trabalhada_servidor = self.carga_horaria_trabalhada_final_qtd

                    if ch_trabalhada_servidor:
                        if ch_trabalhada_servidor < ch_exigida_inicial_servidor:
                            if ch_trabalhada_servidor >= ch_maxima_exigida_pela_instituicao:
                                self._debito_qtd_desconsiderado = self.debito_qtd_inicial  # TOTALMENTE desconsiderado
                                self._add_log(
                                    self.LOG_OPERACAO_DEBITO_DESCONSIDERADO,
                                    'Não precisará pagar o débito pois a carga horária trabalhada é maior '
                                    'que a carga horária máxima exigida pela instituição devido à liberação '
                                    'parcial ocorrida no dia em questão',
                                )

            if self._debito_qtd_desconsiderado is None:
                self._debito_qtd_desconsiderado = 0
        return self._debito_qtd_desconsiderado

    @property
    def debito_externo_qtd(self):
        if self._debito_externo_qtd is None:
            self._debito_externo_qtd = 0
            if self.has_debitos_externos:
                for debito_externo in self.debitos_externos_do_dia:
                    self._debito_externo_qtd += debito_externo.valor_debito
        return self._debito_externo_qtd

    @property
    def debito_qtd_considerado(self):
        if self._debito_qtd_considerado is None:
            if self.debito_qtd_inicial:
                self._debito_qtd_considerado = self.debito_qtd_inicial - self.debito_qtd_desconsiderado

            if self._debito_qtd_considerado is None:
                self._debito_qtd_considerado = self.debito_qtd_inicial

            self._debito_qtd_considerado += self.debito_externo_qtd

        return self._debito_qtd_considerado

    @property
    def debito_via_frequencias_qtd_considerado(self):
        return self.debito_qtd_considerado - self.debito_externo_qtd

    @property
    def is_debito(self):
        return self.debito_qtd_considerado > 0

    @property
    def debito_dias_dos_saldos(self):
        """apenas possível abrangência dos saldos"""
        if self._debito_dias_dos_saldos is None:
            self._debito_dias_dos_saldos = []

            # regra: mês seguinte
            dia_inicial_saldo = self.dia + datetime.timedelta(1)
            dia_final_saldo = datetime.date(
                (self.dia + relativedelta(months=2)).year, (self.dia + relativedelta(months=2)).month, 1
            ) - datetime.timedelta(1)
            self._debito_dias_dos_saldos += get_datas_entre(dia_inicial_saldo, dia_final_saldo)

            # regra: compensações específicas
            for acompanhamento in self.acompanhamentos_envolvidos_contendo_o_dia_como_debito:
                for periodo_compensacao in self.contexto.acompanhamentos_envolvidos_periodos_de_compensacao_consultados.get(
                    acompanhamento.recesso_opcao.id, []
                ):
                    self._debito_dias_dos_saldos += get_datas_entre(periodo_compensacao.data_inicial, periodo_compensacao.data_final)

            self._debito_dias_dos_saldos = sorted(set(self._debito_dias_dos_saldos))

            if self._debito_dias_dos_saldos is None:
                self._debito_dias_dos_saldos = []

        return self._debito_dias_dos_saldos

    @property
    def debito_qtd_reposto(self):
        """débito com reposição informada"""
        if self._debito_qtd_reposto is None:
            if self.debito_qtd_considerado:
                self._debito_qtd_reposto = 0

                for compensacao in self.compensacoes_informadas_para_o_dia:
                    if compensacao.data_aplicacao == self.dia:
                        self._debito_qtd_reposto += Frequencia.time_para_segundos(compensacao.ch_compensada)

            if self._debito_qtd_reposto is None:
                self._debito_qtd_reposto = 0
        return self._debito_qtd_reposto

    @property
    def debito_qtd_percentual_reposicao(self):
        """percentual de reposição do débito"""
        if self._debito_qtd_percentual_reposicao is None:
            self._debito_qtd_percentual_reposicao = 0
            if self.debito_qtd_considerado:
                self._debito_qtd_percentual_reposicao = int(self.debito_qtd_reposto * 100 / self.debito_qtd_considerado)
                if self._debito_qtd_percentual_reposicao > 100:  # possível situação de duplicidade de compensações
                    self._debito_qtd_percentual_reposicao = 100
        return self._debito_qtd_percentual_reposicao

    @property
    def debito_qtd_restante(self):
        """o que resta de débito"""
        if self._debito_qtd_restante is None:
            if self.debito_qtd_considerado:
                self._debito_qtd_restante = self.debito_qtd_considerado - self.debito_qtd_reposto
            else:
                self._debito_qtd_restante = 0

            if self._debito_qtd_restante is None:
                self._debito_qtd_restante = 0

            if self._debito_qtd_restante < 0:  # possível situação de duplicidade de compensações
                self._debito_qtd_restante = 0
        return self._debito_qtd_restante

    @property
    def debito_reposicao_distribuicao(self):
        if self._debito_reposicao_distribuicao is None:
            debito_distribuicoes = OrderedDict()

            for dia_saldo in self.debito_dias_dos_saldos:
                # informações:
                #   data do saldo
                #   ch compensada
                #   compensações que geraram a ch compensada

                debito_distribuicao = [dia_saldo, 0, []]

                for compensacao in self.compensacoes_informadas_para_o_dia:
                    if compensacao.data_compensacao == dia_saldo:
                        debito_distribuicao[1] += Frequencia.time_para_segundos(compensacao.ch_compensada)
                        debito_distribuicao[2].append(compensacao)

                debito_distribuicoes[dia_saldo] = (debito_distribuicao[0], debito_distribuicao[1], debito_distribuicao[2])

            self._debito_reposicao_distribuicao = list(debito_distribuicoes.values())
        return self._debito_reposicao_distribuicao

    @property
    def debito_reposicao_distribuicao_for_display(self):
        return self.get_reposicao_distribuicao_for_display(self.debito_reposicao_distribuicao)

    @property
    def is_debito_pendente(self):
        return self.debito_qtd_restante > 0

    # -------------------------------------------------------------------------------------------------------

    @property
    def is_saldo_inicialmente(self):
        """é um possível saldo ?"""
        if self.dia >= self.hoje:
            return False  # o dia está no futuro
        return self.is_dia_que_pode_haver_saldo and (
            self.carga_horaria_trabalhada_final_qtd - self.carga_horaria_qtd > 0
        )  # trabalhou mais que a exigida?

    @property
    def saldo_qtd_inicial(self):
        if self._saldo_qtd_inicial is None:
            if self.is_saldo_inicialmente:
                self._saldo_qtd_inicial = self.carga_horaria_trabalhada_final_qtd - self.carga_horaria_qtd

            if self._saldo_qtd_inicial is None:
                self._saldo_qtd_inicial = 0
        return self._saldo_qtd_inicial

    @property
    def saldo_qtd_maxima_permitida(self):
        if self._saldo_qtd_maxima_permitida is None:
            # qtd máxima diária - CH do dia
            self._saldo_qtd_maxima_permitida = self.carga_horaria_maxima_permitida_para_o_dia - self.carga_horaria_qtd

            if self._saldo_qtd_maxima_permitida <= 0:
                # isso ocorrerá em algum momento ???
                # sim. no caso de liberação parcial do dia.
                # nessa caso, é possível que não haja margem para
                # geração de saldo (ex: minha carga horária é 8h mas a instituição exigiu apenas 6h)
                self._saldo_qtd_maxima_permitida = 0
        return self._saldo_qtd_maxima_permitida

    @property
    def saldo_permitida_utilizacao(self):
        """pode utilizar?"""
        if self._saldo_permitida_utilizacao is None:
            if self.saldo_qtd_inicial:
                abonos_do_dia = self.abonos_do_dia

                abono_negativo_1 = False
                abono_negativo_2 = False
                abono_negativo_3 = False
                abono_negativo_4 = False

                for abono_do_dia in abonos_do_dia:
                    abono_negativo_1 = abono_negativo_1 or abono_do_dia.acao_abono == AbonoChefia.HORA_EXTRA_NAO_JUSTIFICADA
                    abono_negativo_2 = abono_negativo_2 or abono_do_dia.acao_abono == AbonoChefia.HORA_EXTRA_JUSTIFICADA
                    abono_negativo_3 = abono_negativo_3 or abono_do_dia.acao_abono == AbonoChefia.TRABALHO_FDS_NAO_PERMITIDO
                    abono_negativo_4 = abono_negativo_4 or abono_do_dia.acao_abono == AbonoChefia.TRABALHO_FDS_PERMITIDO_COMO_HORA_EXTRA

                saldo_is_desconsiderado_via_abono = abonos_do_dia and (abono_negativo_1 or abono_negativo_2 or abono_negativo_3 or abono_negativo_4)

                estah_em_pgd_no_dia = self.is_dia_em_pgd

                self._saldo_permitida_utilizacao = not estah_em_pgd_no_dia and (
                    not abonos_do_dia or (abonos_do_dia and not saldo_is_desconsiderado_via_abono)
                )

                if not self._saldo_permitida_utilizacao:
                    if abono_negativo_1:
                        self._add_log(self.LOG_OPERACAO_SALDO_DESCONSIDERADO, 'Hora Extra Não Justificada')

                    if abono_negativo_2:
                        self._add_log(self.LOG_OPERACAO_SALDO_DESCONSIDERADO, 'Hora Extra Justificada')

                    if abono_negativo_3:
                        self._add_log(self.LOG_OPERACAO_SALDO_DESCONSIDERADO, 'Trabalho no Fim de Semana Não Justificado')

                    if abono_negativo_4:
                        self._add_log(self.LOG_OPERACAO_SALDO_DESCONSIDERADO, 'Trabalho no Fim de Semana como Hora Extra')

                    if estah_em_pgd_no_dia:
                        self._add_log(self.LOG_OPERACAO_SALDO_DESCONSIDERADO, 'Saldo Gerado no Período de PGD')

            if self._saldo_permitida_utilizacao is None:
                self._saldo_permitida_utilizacao = False

        return self._saldo_permitida_utilizacao

    @property
    def saldo_qtd_desconsiderado(self):
        """com os motivos"""
        if self._saldo_qtd_desconsiderado is None:
            if self.saldo_qtd_inicial:
                self._saldo_qtd_desconsiderado = 0

                if not self.saldo_permitida_utilizacao:
                    self._saldo_qtd_desconsiderado = self.saldo_qtd_inicial  # TOTALMENTE desconsiderado

                # trata o saldo máximo permitido
                elif self.saldo_qtd_inicial > self.saldo_qtd_maxima_permitida:
                    # desconsidera o excedente
                    self._saldo_qtd_desconsiderado = self.saldo_qtd_inicial - self.saldo_qtd_maxima_permitida

                    if self.saldo_qtd_maxima_permitida > 0:
                        self._add_log(
                            self.LOG_OPERACAO_SALDO_DESCONSIDERADO,
                            f'{formatar_segundos(self._saldo_qtd_desconsiderado, True, True)} foram desconsiderados como saldo pois o limite de '
                            f'carga horária máxima diária de {formatar_segundos(self.carga_horaria_maxima_permitida_para_o_dia, True, True)} foi ultrapassado',
                        )
                    else:
                        # desconsidera tudo que foi gerado
                        self._add_log(
                            self.LOG_OPERACAO_SALDO_DESCONSIDERADO,
                            f'{formatar_segundos(self._saldo_qtd_desconsiderado, True, True)} foram desconsiderados como saldo pois no dia em questão '
                            'não há possibilidade de geração de saldo',
                        )

            if self._saldo_qtd_desconsiderado is None:
                self._saldo_qtd_desconsiderado = 0
        return self._saldo_qtd_desconsiderado

    @property
    def saldo_qtd_considerado(self):
        if self._saldo_qtd_considerado is None:
            if self.saldo_qtd_inicial:
                self._saldo_qtd_considerado = self.saldo_qtd_inicial - self.saldo_qtd_desconsiderado
            if self._saldo_qtd_considerado is None:
                self._saldo_qtd_considerado = self.saldo_qtd_inicial
        return self._saldo_qtd_considerado

    @property
    def is_saldo(self):
        return self.saldo_qtd_considerado > 0

    @property
    def saldo_dias_dos_debitos(self):
        """apenas possível abrangência dos débitos"""
        if self._saldo_dias_dos_debitos is None:
            self._saldo_dias_dos_debitos = []

            # regra: mês seguinte (anterior nesse caso)
            dia_inicial_debito = datetime.date((self.dia - relativedelta(months=1)).year, (self.dia - relativedelta(months=1)).month, 1)
            dia_final_debito = self.dia - datetime.timedelta(1)

            self._saldo_dias_dos_debitos += get_datas_entre(dia_inicial_debito, dia_final_debito)

            # regra: débitos em acompanhamento
            for acompanhamento in self.acompanhamentos_envolvidos_contendo_o_dia_como_saldo:
                if acompanhamento.id in self.contexto.acompanhamentos_envolvidos_dias_efetivos_a_compensar:
                    self._saldo_dias_dos_debitos += self.contexto.acompanhamentos_envolvidos_dias_efetivos_a_compensar[acompanhamento.id]
                else:
                    self._saldo_dias_dos_debitos += acompanhamento.dias_efetivos_a_compensar(contexto_compensacao=self.contexto)

            self._saldo_dias_dos_debitos = sorted(set(self._saldo_dias_dos_debitos))

            if self._saldo_dias_dos_debitos is None:
                self._saldo_dias_dos_debitos = []

        return self._saldo_dias_dos_debitos

    @property
    def saldo_qtd_utilizado(self):
        """saldo utilizado DO dia em reposições"""
        if self._saldo_qtd_utilizado is None:
            if self.saldo_qtd_considerado:
                self._saldo_qtd_utilizado = 0

                for compensacao in self.compensacoes_informadas_para_o_dia:
                    if compensacao.data_compensacao == self.dia:
                        self._saldo_qtd_utilizado += Frequencia.time_para_segundos(compensacao.ch_compensada)

            if self._saldo_qtd_utilizado is None:
                self._saldo_qtd_utilizado = 0
        return self._saldo_qtd_utilizado

    @property
    def saldo_qtd_percentual_utilizacao(self):
        """percentual de utilização do saldo"""
        if self._saldo_qtd_percentual_utilizacao is None:
            self._saldo_qtd_percentual_utilizacao = 0
            if self.saldo_qtd_considerado:
                self._saldo_qtd_percentual_utilizacao = int(self.saldo_qtd_utilizado * 100 / self.saldo_qtd_considerado)
                if self._saldo_qtd_percentual_utilizacao > 100:  # possível situação de duplicidade de compensações
                    self._saldo_qtd_percentual_utilizacao = 100
        return self._saldo_qtd_percentual_utilizacao

    @property
    def saldo_qtd_restante(self):
        """o que resta de saldo"""
        if self._saldo_qtd_restante is None:
            if self.saldo_qtd_considerado:
                self._saldo_qtd_restante = self.saldo_qtd_considerado - self.saldo_qtd_utilizado
            else:
                self._saldo_qtd_restante = 0

            if self._saldo_qtd_restante < 0:  # possível situação de duplicidade de compensações
                self._saldo_qtd_restante = 0
        return self._saldo_qtd_restante

    @property
    def saldo_utilizacao_distribuicao(self):
        if self._saldo_utilizacao_distribuicao is None:
            saldo_distribuicoes = OrderedDict()

            for dia_debito in self.saldo_dias_dos_debitos:
                # informações:
                #   data do débito
                #   ch utilizada
                #   compensações que geraram a ch utilizada,

                saldo_distribuicao = [dia_debito, 0, []]

                for compensacao in self.compensacoes_informadas_para_o_dia:
                    if compensacao.data_aplicacao == dia_debito:
                        saldo_distribuicao[1] += Frequencia.time_para_segundos(compensacao.ch_compensada)
                        saldo_distribuicao[2].append(compensacao)

                saldo_distribuicoes[dia_debito] = (saldo_distribuicao[0], saldo_distribuicao[1], saldo_distribuicao[2])

            self._saldo_utilizacao_distribuicao = list(saldo_distribuicoes.values())
        return self._saldo_utilizacao_distribuicao

    @property
    def saldo_utilizacao_distribuicao_for_display(self):
        return self.get_reposicao_distribuicao_for_display(self.saldo_utilizacao_distribuicao)

    # -------------------------------------------------------------------------------------------------------


class CompensacaoInfoDia:
    is_debito: bool
    ch_paga_percentual: float
    ch_restante_a_pagar: str
    ch_restante_a_pagar_is_maior_que_zero: bool
    ch_restante_a_pagar_is_menor_que_15min: bool
    is_saldo: bool
    ch_utilizada_percentual: float
    ch_restante_a_utilizar: int
    acompanhamentos_compensacoes_especificas: QuerySet[RecessoOpcaoEscolhida]
    all_info_dia: SituacaoDia

    def __init__(self, situacao_dia: SituacaoDia) -> None:
        self.is_debito = situacao_dia.is_debito
        self.ch_paga_percentual = situacao_dia.debito_qtd_percentual_reposicao
        self.ch_restante_a_pagar = formatar_segundos(situacao_dia.debito_qtd_restante)
        self.ch_restante_a_pagar_is_maior_que_zero = situacao_dia.debito_qtd_restante > 0
        self.ch_restante_a_pagar_is_menor_que_15min = situacao_dia.debito_qtd_restante < 900
        self.is_saldo = situacao_dia.is_saldo
        self.ch_utilizada_percentual = situacao_dia.saldo_qtd_percentual_utilizacao
        self.ch_restante_a_utilizar = situacao_dia.saldo_qtd_restante
        self.acompanhamentos_compensacoes_especificas = situacao_dia.acompanhamentos_envolvidos_contendo_o_dia_como_debito
        self.all_info_dia = situacao_dia

    def as_dict(self):
        return self.__dict__


def debito_pendente(servidor, data_inicial, data_final, data_limite_compensacao=None):
    """retorna o débito restante/pendente em segundos no período informado

    Se for informado uma data limite para compensação, retornará uma lista com:
        - o débito restante/pendente em segundos no período informado
        - o débito restante/pendente em segundos no período informado que pode ser compensado até a data limite
    """
    contexto = Contexto(servidor=servidor, periodo_data_inicial=data_inicial, periodo_data_final=data_final)

    ch_pendente_no_periodo = 0  # em segundos
    ch_pendente_no_periodo_ate_data_limite_compensacao = 0  # em segundos

    for dia_debito_situacao in list(contexto.dias_debitos_pendentes.values()):
        ch_pendente_no_periodo += dia_debito_situacao.debito_qtd_restante

        if data_limite_compensacao:
            pode_quitar_apos_data_limite_compensacao = False
            for dia_saldo in dia_debito_situacao.debito_dias_dos_saldos:
                if dia_saldo > data_limite_compensacao:
                    pode_quitar_apos_data_limite_compensacao = True
                    break
            if not pode_quitar_apos_data_limite_compensacao:
                ch_pendente_no_periodo_ate_data_limite_compensacao += dia_debito_situacao.debito_qtd_restante

    return ch_pendente_no_periodo, ch_pendente_no_periodo_ate_data_limite_compensacao


def saldo_restante(servidor, data_inicial, data_final):
    """retorna o saldo restante em segundos no período informado"""
    contexto = Contexto(servidor=servidor, periodo_data_inicial=data_inicial, periodo_data_final=data_final)

    ch_restante_no_periodo = 0  # em segundos

    for dia_saldo_situacao in list(contexto.dias_saldos.values()):
        ch_restante_no_periodo += dia_saldo_situacao.saldo_qtd_restante

    return ch_restante_no_periodo


##################################################################################################################

# aliases


class PontoPeriodo(Contexto):
    """Um alias para Contexto"""

    def __init__(self, servidor, periodo_data_inicial, periodo_data_final, relatorio_de_ponto=None):
        super().__init__(servidor, periodo_data_inicial, periodo_data_final, relatorio_de_ponto)


class PontoDia(SituacaoDia):
    """Um alias para SituacaoDia"""

    def __init__(self, servidor, dia, contexto=None):
        super().__init__(servidor, dia, contexto)


##################################################################################################################

# adicionar novas compensação de horários


class PeriodoInfo:
    PERIODO_OBJETIVO_SALDO = 'utilizar_o_saldo_do_periodo'
    PERIODO_OBJETIVO_DEBITO = 'compensar_o_debito_do_periodo'

    user: User
    servidor: Servidor
    periodo_data_inicio: datetime.date
    periodo_data_fim: datetime.date
    periodo_objetivo: str  # ver constantes PERIODO_OBJETIVO_SALDO e PERIODO_OBJETIVO_DEBITO

    compensacao_contexto: Contexto
    saldos_disponiveis: OrderedDict[datetime.date, int]
    debitos_pendentes: OrderedDict[datetime.date, int]
    periodo_envolvido_data_inicio: datetime.date
    periodo_envolvido_data_fim: datetime.date
    compensacoes_especificas: QuerySet[RecessoOpcaoEscolhida]
    datas_debitos_especificos: list[datetime.date]
    saldos_externos_disponiveis: OrderedDict[SaldoExterno, int]
    debitos_externos: QuerySet[DebitoExterno]
    saldo_total_em_segundos: int
    debito_total_em_segundos: int
    frequencias_no_periodo: QuerySet[Frequencia]

    @property
    def periodo_eh_utilizar_o_saldo(self):
        return self.periodo_objetivo == PeriodoInfo.PERIODO_OBJETIVO_SALDO

    @property
    def periodo_eh_compensar_o_debito(self):
        return self.periodo_objetivo == PeriodoInfo.PERIODO_OBJETIVO_DEBITO

    def get_periodo_objetivo_display(self):
        if self.periodo_eh_utilizar_o_saldo:
            return 'Utilizar o saldo do período informado'
        if self.periodo_eh_compensar_o_debito:
            return 'Compensar o débito do período informado'
        return '?'

    @property
    def periodo_envolvido_eh_valido(self) -> bool:
        return bool(self.periodo_envolvido_data_inicio and self.periodo_envolvido_data_fim)

    @property
    def periodo_total(self) -> list[datetime.date]:
        periodo_total_data_inicio = self.periodo_envolvido_data_inicio or self.periodo_data_inicio
        periodo_total_data_fim = self.periodo_envolvido_data_fim or self.periodo_data_fim

        if periodo_total_data_inicio > self.periodo_data_inicio:
            periodo_total_data_inicio = self.periodo_data_inicio

        if periodo_total_data_fim < self.periodo_data_fim:
            periodo_total_data_fim = self.periodo_data_fim

        return [periodo_total_data_inicio, periodo_total_data_fim]

    @property
    def periodo_total_data_inicio(self) -> datetime.date:
        return self.periodo_total[0]

    @property
    def periodo_total_data_fim(self) -> datetime.date:
        return self.periodo_total[1]


def get_periodo_info(
    user: User,
    periodo_data_inicio: datetime.date,
    periodo_data_fim: datetime.date,
    periodo_objetivo: str,  # ver constantes PERIODO_OBJETIVO_SALDO e PERIODO_OBJETIVO_DEBITO
    omite_debitos_de_compensacoes_especificas: bool = False,
    abrange_apenas_debitos_dessas_compensacoes_especificas_ids: list[int] | None = None,
    omite_saldos_externos: bool = False,
    abrange_apenas_saldos_externos: bool = False,
    abrange_apenas_esses_saldos_externos_ids: list[int] | None = None,
) -> PeriodoInfo:
    if abrange_apenas_esses_saldos_externos_ids is None:
        abrange_apenas_esses_saldos_externos_ids = []

    if abrange_apenas_debitos_dessas_compensacoes_especificas_ids is None:
        abrange_apenas_debitos_dessas_compensacoes_especificas_ids = []

    info = PeriodoInfo()

    info.user = user
    info.servidor = user.get_relacionamento()
    info.periodo_data_inicio = periodo_data_inicio
    info.periodo_data_fim = periodo_data_fim
    info.periodo_objetivo = periodo_objetivo

    # instância inicial do Contexto, o qual será "engordado" com mais informações
    # sobre saldos e débitos nas etapas seguintes ... a intenção é ter apenas uma
    # única instância (Contexto) que será compartilhada por todos os dias (SituacaoDia)
    info.compensacao_contexto = Contexto(
        servidor=info.servidor, periodo_data_inicial=info.periodo_data_inicio, periodo_data_final=info.periodo_data_fim
    )

    info.saldos_disponiveis = OrderedDict()
    info.debitos_pendentes = OrderedDict()

    info.periodo_envolvido_data_inicio = None
    info.periodo_envolvido_data_fim = None

    info.compensacoes_especificas = RecessoOpcaoEscolhida.objects.none()
    compensacoes_especificas_ids: list[int] = []
    info.datas_debitos_especificos = []

    info.saldos_externos_disponiveis = OrderedDict()
    saldos_externos = SaldoExterno.objects.none()
    info.debitos_externos = DebitoExterno.objects.none()

    info.saldo_total_em_segundos = 0
    info.debito_total_em_segundos = 0

    info.frequencias_no_periodo = Frequencia.objects.none()

    if info.periodo_objetivo == PeriodoInfo.PERIODO_OBJETIVO_SALDO:
        # dias envolvidos contém todos os dias dos débitos que o período informado de saldos
        # pode abranger
        dias_envolvidos: list[datetime.date] = []

        # saldos
        if not abrange_apenas_saldos_externos or not abrange_apenas_esses_saldos_externos_ids:
            for dia_saldo in get_datas_entre(info.periodo_data_inicio, info.periodo_data_fim):
                dia_situacao = info.compensacao_contexto.get_dia(dia_saldo, add_se_nao_existir=True)
                if dia_situacao.saldo_qtd_restante > 0:
                    info.saldos_disponiveis[dia_saldo] = dia_situacao.saldo_qtd_restante
                dias_envolvidos += dia_situacao.saldo_dias_dos_debitos

        dias_envolvidos = sorted(set(dias_envolvidos))

        # débitos
        for dia_debito in dias_envolvidos:
            dia_situacao = info.compensacao_contexto.get_dia(dia_debito, add_se_nao_existir=True)

            if dia_situacao.is_debito_especifico:
                info.datas_debitos_especificos.append(dia_debito)

            if dia_situacao.debito_qtd_restante > 0:
                compensacoes_especificas_ids += [
                    compensao_especifica.id for compensao_especifica in dia_situacao.acompanhamentos_envolvidos_contendo_o_dia_como_debito
                ]
                if omite_debitos_de_compensacoes_especificas and dia_situacao.is_debito_especifico:
                    continue
                if abrange_apenas_debitos_dessas_compensacoes_especificas_ids:
                    dia_exibir = False
                    for compensao_especifica in dia_situacao.acompanhamentos_envolvidos_contendo_o_dia_como_debito:
                        if compensao_especifica.id in abrange_apenas_debitos_dessas_compensacoes_especificas_ids:
                            dia_exibir = True
                            break
                    if not dia_exibir:
                        continue

                info.debitos_pendentes[dia_debito] = dia_situacao.debito_qtd_restante
                info.debitos_externos = info.debitos_externos | DebitoExterno.objects.filter(
                    id__in=[debito_externo.id for debito_externo in dia_situacao.debitos_externos_do_dia]
                )

        if dias_envolvidos:
            info.periodo_envolvido_data_inicio = min(dias_envolvidos)
            info.periodo_envolvido_data_fim = max(dias_envolvidos)

        # saldos externos candidatos
        if info.periodo_envolvido_eh_valido and not omite_saldos_externos:
            saldos_externos = SaldoExterno.get_saldos_externos_meus_validados(
                eu=info.user,
                utilizacao_data_inicio=info.periodo_envolvido_data_inicio,
                utilizacao_data_fim=info.periodo_envolvido_data_fim,
            )

            if abrange_apenas_esses_saldos_externos_ids:
                saldos_externos = saldos_externos.filter(id__in=abrange_apenas_esses_saldos_externos_ids)

    elif info.periodo_objetivo == PeriodoInfo.PERIODO_OBJETIVO_DEBITO:
        # dias envolvidos contém todos os dias dos saldos que o período informado de débitos
        # pode abranger
        dias_envolvidos: list[datetime.date] = []

        # débitos
        for dia_debito in get_datas_entre(info.periodo_data_inicio, info.periodo_data_fim):
            dia_situacao = info.compensacao_contexto.get_dia(dia_debito, add_se_nao_existir=True)

            if dia_situacao.is_debito_especifico:
                info.datas_debitos_especificos.append(dia_debito)

            if dia_situacao.debito_qtd_restante > 0:
                compensacoes_especificas_ids += [
                    compensao_especifica.id for compensao_especifica in dia_situacao.acompanhamentos_envolvidos_contendo_o_dia_como_debito
                ]
                if omite_debitos_de_compensacoes_especificas and dia_situacao.is_debito_especifico:
                    continue
                if abrange_apenas_debitos_dessas_compensacoes_especificas_ids:
                    dia_exibir = False
                    for compensao_especifica in dia_situacao.acompanhamentos_envolvidos_contendo_o_dia_como_debito:
                        if compensao_especifica.id in abrange_apenas_debitos_dessas_compensacoes_especificas_ids:
                            dia_exibir = True
                            break
                    if not dia_exibir:
                        continue
                info.debitos_pendentes[dia_debito] = dia_situacao.debito_qtd_restante
                info.debitos_externos = info.debitos_externos | DebitoExterno.objects.filter(
                    id__in=[debito_externo.id for debito_externo in dia_situacao.debitos_externos_do_dia]
                )
            dias_envolvidos += dia_situacao.debito_dias_dos_saldos

        dias_envolvidos = sorted(set(dias_envolvidos))

        # saldos
        if not abrange_apenas_saldos_externos or not abrange_apenas_esses_saldos_externos_ids:
            for dia_saldo in dias_envolvidos:
                dia_situacao = info.compensacao_contexto.get_dia(dia_saldo, add_se_nao_existir=True)
                if dia_situacao.saldo_qtd_restante > 0:
                    info.saldos_disponiveis[dia_saldo] = dia_situacao.saldo_qtd_restante

        if dias_envolvidos:
            info.periodo_envolvido_data_inicio = min(dias_envolvidos)
            info.periodo_envolvido_data_fim = max(dias_envolvidos)

        # saldos externos candidatos
        if info.periodo_envolvido_eh_valido and not omite_saldos_externos:
            saldos_externos = SaldoExterno.get_saldos_externos_meus_validados(
                eu=info.user,
                utilizacao_data_inicio=info.periodo_data_inicio,
                utilizacao_data_fim=info.periodo_data_fim,
            )

            if abrange_apenas_esses_saldos_externos_ids:
                saldos_externos = saldos_externos.filter(id__in=abrange_apenas_esses_saldos_externos_ids)

    for saldo_externo in saldos_externos:
        valor_saldo_restante = saldo_externo.valor_saldo_restante  # faz uma cópia para evitar recalcular
        if valor_saldo_restante:
            info.saldos_externos_disponiveis[saldo_externo] = valor_saldo_restante

    info.compensacoes_especificas = RecessoOpcaoEscolhida.objects.filter(id__in=list(set(compensacoes_especificas_ids)))

    # débitos externos (apenas ajuste)
    info.debitos_externos = info.debitos_externos.distinct()

    for _, saldo in list(info.saldos_disponiveis.items()):
        info.saldo_total_em_segundos += saldo

    for saldo in info.saldos_externos_disponiveis.values():
        info.saldo_total_em_segundos += saldo

    for _, debito in list(info.debitos_pendentes.items()):
        info.debito_total_em_segundos += debito

    info.frequencias_no_periodo = info.compensacao_contexto.get_frequencias_as_queryset

    return info


class PeriodoProcessamentoInfo:
    periodo: PeriodoInfo
    fields: dict[str, str]
    saldos_utilizacao: OrderedDict[datetime.date, int]
    debitos_saldos_utilizacao: OrderedDict[datetime.date, OrderedDict[datetime.date, int]]
    saldos_externos_utilizacao: OrderedDict[SaldoExterno, int]
    debitos_saldos_externos_utilizacao: OrderedDict[datetime.date, OrderedDict[SaldoExterno, int]]
    saldo_total_distribuido_em_segundos: int
    saldo_total_a_distribuir_em_segundos: int
    debito_total_compensado_em_segundos: int
    debito_total_restante_em_segundos: int

    def salva_compensacoes(self, fields_values: dict[str, str | datetime.date] | None = None) -> list[HorarioCompensacao]:
        if not fields_values:
            fields_values = self.fields

        compensacoes_salvas: list[HorarioCompensacao] = []

        for field_info in CompensacaoHorarioAddFormUtils.get_fields_infos(fields_values.keys(), fields_values):
            field_value = field_info.field_value
            data_debito = field_info.data_debito
            data_saldo = field_info.data_saldo
            saldo_externo_id = field_info.saldo_externo_id

            ch_compensada = field_value

            if ch_compensada:
                obs_na_data_compensacao_info_extra = ''
                obs_na_data_aplicacao_info_extra = ''

                if data_debito in self.periodo.datas_debitos_especificos:
                    compensacoes_especificas = self.periodo.compensacao_contexto.get_dia(
                        data_debito
                    ).acompanhamentos_envolvidos_contendo_o_dia_como_debito

                    for compensacao_especifica in compensacoes_especificas:
                        # as observações terão uma informação extra sobre o recesso que está sendo compensado
                        obs_na_data_compensacao_info_extra += f' ({compensacao_especifica.recesso_opcao})'
                        obs_na_data_aplicacao_info_extra += obs_na_data_compensacao_info_extra

                informe_compensacao = HorarioCompensacao()

                informe_compensacao.funcionario = self.periodo.servidor
                informe_compensacao.data_aplicacao = data_debito
                informe_compensacao.ch_compensada = ch_compensada

                if data_saldo:
                    informe_compensacao.data_compensacao = data_saldo

                if saldo_externo_id:
                    saldo_externo = SaldoExterno.objects.filter(id=saldo_externo_id).first()
                    informe_compensacao.saldo_externo_compensacao = saldo_externo

                obs_na_data_compensacao = f'{informe_compensacao.get_auto_obs_descricao_na_data_compensacao()}{obs_na_data_compensacao_info_extra}.'

                obs_na_data_aplicacao = f'{informe_compensacao.get_auto_obs_descricao_na_data_aplicacao()}{obs_na_data_aplicacao_info_extra}.'

                informe_compensacao.save_observacao_no_ponto(
                    descricao_na_data_compensacao=obs_na_data_compensacao, descricao_na_data_aplicacao=obs_na_data_aplicacao, commit=False
                )

                informe_compensacao.save()

                compensacoes_salvas.append(informe_compensacao)

        return compensacoes_salvas


def get_periodo_processamento_info(
    periodo_info: PeriodoInfo,
    values: dict[str, Any],
) -> PeriodoProcessamentoInfo:
    processamento_info = PeriodoProcessamentoInfo()

    processamento_info.periodo = periodo_info

    processamento_info.fields = {}  # {'fieldname': 'hh:mm:ss'}

    processamento_info.saldos_utilizacao = OrderedDict()
    processamento_info.debitos_saldos_utilizacao = OrderedDict()
    processamento_info.saldos_externos_utilizacao = OrderedDict()
    processamento_info.debitos_saldos_externos_utilizacao = OrderedDict()

    processamento_info.saldo_total_distribuido_em_segundos = 0
    processamento_info.saldo_total_a_distribuir_em_segundos = 0

    processamento_info.debito_total_compensado_em_segundos = 0
    processamento_info.debito_total_restante_em_segundos = 0

    # processa as datas dos débitos, criando os fields ref. aos informes de compensação
    if not values:
        ###########
        # Distribui o saldo e cria os fields automaticamente.
        ###########
        for data_debito in periodo_info.debitos_pendentes:
            debito_na_data = periodo_info.debitos_pendentes.get(data_debito, 0)

            processamento_info.debitos_saldos_utilizacao[data_debito] = OrderedDict()
            processamento_info.debitos_saldos_externos_utilizacao[data_debito] = OrderedDict()

            # aloca saldo suficiente para quitar o débito
            carga_horaria_a_compensar = 0

            # saldos (ponto batido)
            for data_saldo, saldo_restante in list(periodo_info.saldos_disponiveis.items()):
                # o saldo pode ser utilizado pelo débito?
                saldo_pode_ser_utilizado = data_saldo in periodo_info.compensacao_contexto.get_dia(data_debito).debito_dias_dos_saldos

                if saldo_pode_ser_utilizado:
                    if data_saldo not in processamento_info.saldos_utilizacao:
                        processamento_info.saldos_utilizacao[data_saldo] = 0
                    saldo_a_utilizar = saldo_restante - processamento_info.saldos_utilizacao[data_saldo]

                    if saldo_a_utilizar > 0:
                        carga_horaria_a_compensar += saldo_a_utilizar

                        if carga_horaria_a_compensar >= debito_na_data:
                            diferenca = carga_horaria_a_compensar - debito_na_data
                            carga_horaria_a_compensar = debito_na_data  # limita-se ao débito
                            saldo_a_utilizar -= diferenca

                        processamento_info.saldos_utilizacao[data_saldo] += saldo_a_utilizar

                        if data_saldo not in processamento_info.debitos_saldos_utilizacao[data_debito]:
                            processamento_info.debitos_saldos_utilizacao[data_debito][data_saldo] = 0
                        processamento_info.debitos_saldos_utilizacao[data_debito][data_saldo] += saldo_a_utilizar

            # saldos externos
            for saldo_externo, valor_restante in periodo_info.saldos_externos_disponiveis.items():
                if carga_horaria_a_compensar == debito_na_data:
                    break

                # o saldo externo pode ser utilizado pelo débito?
                # saldo_pode_ser_utilizado = saldo_externo.data_inicio <= data_debito <= saldo_externo.data_fim
                saldo_pode_ser_utilizado = saldo_externo.pode_ser_utilizado_neste_debito(data_debito)

                if saldo_pode_ser_utilizado:
                    if saldo_externo not in processamento_info.saldos_externos_utilizacao:
                        processamento_info.saldos_externos_utilizacao[saldo_externo] = 0
                    saldo_a_utilizar = valor_restante - processamento_info.saldos_externos_utilizacao[saldo_externo]

                    if saldo_a_utilizar > 0:
                        carga_horaria_a_compensar += saldo_a_utilizar

                        if carga_horaria_a_compensar >= debito_na_data:
                            diferenca = carga_horaria_a_compensar - debito_na_data
                            carga_horaria_a_compensar = debito_na_data  # limita-se ao débito
                            saldo_a_utilizar -= diferenca

                        processamento_info.saldos_externos_utilizacao[saldo_externo] += saldo_a_utilizar

                        if saldo_externo not in processamento_info.debitos_saldos_externos_utilizacao[data_debito]:
                            processamento_info.debitos_saldos_externos_utilizacao[data_debito][saldo_externo] = 0
                        processamento_info.debitos_saldos_externos_utilizacao[data_debito][saldo_externo] += saldo_a_utilizar

            ####
            # field representa um informe de compensação do débito

            # saldos (ponto batido)
            for data_saldo, saldo in list(processamento_info.debitos_saldos_utilizacao[data_debito].items()):
                field_name = CompensacaoHorarioAddFormUtils.get_field_name(data_debito, data_saldo)
                field_value = '{h}:{m}:{s}'.format(**formata_segundos(saldo))
                processamento_info.fields[field_name] = field_value

            # saldos externos
            for saldo_externo, saldo in list(processamento_info.debitos_saldos_externos_utilizacao[data_debito].items()):
                field_name = CompensacaoHorarioAddFormUtils.get_field_name_saldo_externo(data_debito, saldo_externo)
                field_value = '{h}:{m}:{s}'.format(**formata_segundos(saldo))
                processamento_info.fields[field_name] = field_value
    else:
        ###########
        # Nesse caso, a distribuição do saldo e os fields de compensação
        # estão nos values.
        ###########

        # inicializa os débitos sem distribuir os saldos e sem criar os fields
        for data_debito in periodo_info.debitos_pendentes:
            debito_na_data = periodo_info.debitos_pendentes.get(data_debito, 0)
            if debito_na_data:
                # apenas prepara
                processamento_info.debitos_saldos_utilizacao[data_debito] = OrderedDict()
                processamento_info.debitos_saldos_externos_utilizacao[data_debito] = OrderedDict()

        # distribui os saldos e cria os fields
        for field_info in CompensacaoHorarioAddFormUtils.get_fields_infos(values.keys(), values):
            try:
                field_name = field_info.field_name
                field_value = field_info.field_value
                data_debito = field_info.data_debito
                data_saldo = field_info.data_saldo
                saldo_externo_id = field_info.saldo_externo_id

                saldo_utilizado = Frequencia.time_para_segundos(field_value)

                if data_saldo:
                    if data_saldo not in processamento_info.saldos_utilizacao:
                        processamento_info.saldos_utilizacao[data_saldo] = 0

                    processamento_info.saldos_utilizacao[data_saldo] += saldo_utilizado

                    if data_debito not in processamento_info.debitos_saldos_utilizacao:
                        processamento_info.debitos_saldos_utilizacao[data_debito] = OrderedDict()

                    if data_saldo not in processamento_info.debitos_saldos_utilizacao[data_debito]:
                        processamento_info.debitos_saldos_utilizacao[data_debito][data_saldo] = 0

                    processamento_info.debitos_saldos_utilizacao[data_debito][data_saldo] += saldo_utilizado

                if saldo_externo_id:
                    saldo_externo = SaldoExterno.objects.filter(id=saldo_externo_id).first()

                    if saldo_externo:
                        if saldo_externo not in processamento_info.saldos_externos_utilizacao:
                            processamento_info.saldos_externos_utilizacao[saldo_externo] = 0

                        processamento_info.saldos_externos_utilizacao[saldo_externo] += saldo_utilizado

                        if data_debito not in processamento_info.debitos_saldos_externos_utilizacao:
                            processamento_info.debitos_saldos_externos_utilizacao[data_debito] = OrderedDict()

                        if saldo_externo not in processamento_info.debitos_saldos_externos_utilizacao[data_debito]:
                            processamento_info.debitos_saldos_externos_utilizacao[data_debito][saldo_externo] = 0

                        processamento_info.debitos_saldos_externos_utilizacao[data_debito][saldo_externo] += saldo_utilizado

                processamento_info.fields[field_name] = field_value

            except Exception:
                pass

    for data_saldo, saldo in list(periodo_info.saldos_disponiveis.items()):
        saldo_utilizado = processamento_info.saldos_utilizacao.get(data_saldo, 0)
        saldo_a_utilizar = saldo - saldo_utilizado
        processamento_info.saldo_total_distribuido_em_segundos += saldo_utilizado
        processamento_info.saldo_total_a_distribuir_em_segundos += saldo_a_utilizar

    for saldo_externo, saldo in periodo_info.saldos_externos_disponiveis.items():
        saldo_utilizado = processamento_info.saldos_externos_utilizacao.get(saldo_externo, 0)
        saldo_a_utilizar = saldo - saldo_utilizado
        processamento_info.saldo_total_distribuido_em_segundos += saldo_utilizado
        processamento_info.saldo_total_a_distribuir_em_segundos += saldo_a_utilizar

    for data_debito in list(periodo_info.debitos_pendentes.keys()):
        # saldos utilizados (ponto batido)
        for compensado in list(processamento_info.debitos_saldos_utilizacao.get(data_debito, {}).values()):
            processamento_info.debito_total_compensado_em_segundos += compensado

        # saldos externos utilizados
        for compensado in list(processamento_info.debitos_saldos_externos_utilizacao.get(data_debito, {}).values()):
            processamento_info.debito_total_compensado_em_segundos += compensado

    processamento_info.debito_total_restante_em_segundos = (
        periodo_info.debito_total_em_segundos - processamento_info.debito_total_compensado_em_segundos
    )

    if processamento_info.debito_total_restante_em_segundos < 0:
        processamento_info.debito_total_restante_em_segundos = 0

    return processamento_info


class FieldInfo:
    field_name: str = None
    field_value: datetime.time = None
    data_debito: datetime.date = None
    data_saldo: datetime.date = None
    saldo_externo_id: int = None


class CompensacaoHorarioAddFormUtils:
    # gerenciamento dos fields do formulário

    @staticmethod
    def get_field_name(data_debito: datetime.date, data_saldo: datetime.date):
        return '{}__{}'.format(data_debito.strftime('%Y%m%d'), data_saldo.strftime('%Y%m%d'))

    @staticmethod
    def get_field_name_saldo_externo(data_debito: datetime.date, saldo_externo: SaldoExterno):
        return '{}__saldo_externo__{}'.format(data_debito.strftime('%Y%m%d'), saldo_externo.id)

    @staticmethod
    def get_fields_infos(fields_names: list[str], src_fields_values: dict[str, Any]) -> list[FieldInfo]:
        result: dict[str, FieldInfo] = OrderedDict()

        for field_name in list(fields_names):
            field_info: FieldInfo = FieldInfo()
            field_info.field_name = field_name

            # cada field representam um informe de compensação do débito
            try:
                ####
                # field_name
                # 1) datadebito__datasaldo
                # 2) datadebito__saldo_externo__saldoexternoid

                # ['data_debito', 'data_saldo']
                # ou
                # ['data_debito', 'saldo_externo', 'saldo_externo_id']
                field_name_partes = field_name.split('__')

                data_debito = datetime.datetime.strptime(field_name_partes[0], '%Y%m%d').date()

                data_saldo = None
                saldo_externo_id = None

                if 'saldo_externo' in field_name_partes:
                    saldo_externo_id = field_name_partes[2]
                else:
                    data_saldo = datetime.datetime.strptime(field_name_partes[1], '%Y%m%d').date()

                ####
                # field_value
                # H:M:S
                # máximo de compensação por dia é de 23:59:59 (por óbvio)
                if isinstance(src_fields_values[field_name], str):
                    field_value = datetime.datetime.strptime(src_fields_values[field_name].strip(), '%H:%M:%S').time()
                else:
                    field_value = src_fields_values[field_name]

                field_info.field_value = field_value
                field_info.data_debito = data_debito
                field_info.data_saldo = data_saldo
                field_info.saldo_externo_id = saldo_externo_id

                result[field_name] = field_info
            except Exception:
                pass

        return result.values()
