from decimal import Decimal
import datetime
from dateutil.relativedelta import relativedelta
from django.db.models import Sum, Q
from django.db.models.functions import Cast
from django.db import models
from ae.models import RespostaParticipacao, PerguntaParticipacao, OfertaValorBolsa, DemandaAlunoAtendida, OfertaValorRefeicao
from rh.models import UnidadeOrganizacional


def calcula_valor_transporte(lista_de_participacoes, data_inicio, data_termino):
    lista = list(lista_de_participacoes.values('data_inicio', 'data_termino', 'participacaopasseestudantil__valor_concedido'))
    TWOPLACES = Decimal(10) ** -2
    total_gasto = Decimal(0)
    for participacao in lista:
        if participacao['data_termino']:
            fim = min(data_termino, participacao['data_termino'])
        else:
            fim = data_termino
        inicio = max(data_inicio, participacao['data_inicio'])
        calcula_meses = relativedelta(fim, inicio)
        concedido = participacao['participacaopasseestudantil__valor_concedido']
        if calcula_meses.years:
            meses = calcula_meses.years * 12
        else:
            meses = calcula_meses.months
        diferenca_dias = calcula_meses.days
        if concedido:
            if meses and not diferenca_dias:
                valor = (Decimal(meses).quantize(TWOPLACES) * concedido).quantize(TWOPLACES)
            elif not meses and diferenca_dias:
                valor = Decimal((Decimal(diferenca_dias).quantize(TWOPLACES) * concedido) / 30).quantize(TWOPLACES)
            else:
                valor = (Decimal(meses).quantize(TWOPLACES) * concedido).quantize(TWOPLACES) + Decimal(
                    (Decimal(diferenca_dias).quantize(TWOPLACES) * concedido) / 30
                ).quantize(TWOPLACES)
            total_gasto += valor

    return total_gasto


def calcula_valor_refeicao(data_inicio, data_termino):
    total_refeicoes = DemandaAlunoAtendida.objects.filter(
        quantidade__gt=0, demanda__in=[1, 2, 19], data__lte=data_termino, data__gte=data_inicio
    ).values('aluno_id', 'data', 'campus', 'quantidade')
    beneficiados = len(set(total_refeicoes.values_list('aluno_id', flat=True)))
    SEARCH_QUERY_OFERTA = (
        Q(data_inicio__gte=data_inicio, data_termino__lte=data_termino)
        | Q(data_inicio__lte=data_inicio, data_termino__gte=data_termino)
        | Q(data_inicio__lte=data_inicio, data_termino__gte=data_inicio, data_termino__lte=data_termino)
        | Q(data_inicio__gte=data_inicio, data_inicio__lte=data_termino, data_termino__gte=data_termino)
    )
    total_gasto = Decimal(0)
    for campus in UnidadeOrganizacional.objects.filter(id__in=OfertaValorRefeicao.objects.values_list('campus_id', flat=True)).values('id'):
        for oferta in OfertaValorRefeicao.objects.filter(Q(campus_id=campus['id']), SEARCH_QUERY_OFERTA).values(
            'valor', 'data_inicio', 'data_termino'
        ):
            valor_total_refeicoes = total_refeicoes.filter(data__gte=oferta['data_inicio'], data__lte=oferta['data_termino'], campus_id=campus['id'])
            if valor_total_refeicoes:
                total_gasto += Decimal(valor_total_refeicoes.aggregate(total=Sum('quantidade'))['total']) * Decimal(oferta['valor'])
    return total_gasto, beneficiados


def calcula_valor_trabalho(lista_de_participacoes, data_inicio, data_termino):
    lista = list(lista_de_participacoes.values('data_inicio', 'data_termino', 'programa__instituicao'))
    TWOPLACES = Decimal(10) ** -2
    total_gasto = Decimal(0)
    for participacao in lista:
        if participacao['data_termino']:
            fim = min(data_termino, participacao['data_termino'])
        else:
            fim = data_termino
        inicio = max(data_inicio, participacao['data_inicio'])
        calcula_meses = relativedelta(fim, inicio)
        if calcula_meses.years:
            meses = calcula_meses.years * 12
        else:
            meses = calcula_meses.months
        diferenca_dias = calcula_meses.days
        bolsa = OfertaValorBolsa.objects.filter(data_inicio__lte=fim, data_termino__gte=inicio, campus=participacao['programa__instituicao']).first()
        if bolsa:
            concedido = bolsa.valor
            if meses and not diferenca_dias:
                valor = (Decimal(meses).quantize(TWOPLACES) * concedido).quantize(TWOPLACES)
            elif not meses and diferenca_dias:
                valor = Decimal((Decimal(diferenca_dias).quantize(TWOPLACES) * concedido) / 30).quantize(TWOPLACES)
            else:
                valor = (Decimal(meses).quantize(TWOPLACES) * concedido).quantize(TWOPLACES) + Decimal(
                    (Decimal(diferenca_dias).quantize(TWOPLACES) * concedido) / 30
                ).quantize(TWOPLACES)
            total_gasto += valor

    return total_gasto


def calcula_valor_programa_generico(lista_de_participacoes, data_inicio, data_termino):
    lista = list(lista_de_participacoes.values('id', 'data_inicio', 'data_termino'))
    TWOPLACES = Decimal(10) ** -2
    total_gasto = Decimal(0)
    for participacao in lista:
        if participacao['data_termino']:
            fim = participacao['data_termino'] + datetime.timedelta(1) if participacao['data_termino'] < data_termino else data_termino
        else:
            fim = data_termino

        inicio = max(data_inicio, participacao['data_inicio'])
        calcula_meses = relativedelta(fim, inicio)
        concedido = Decimal(
            RespostaParticipacao.objects.filter(
                participacao_id=participacao['id'],
                pergunta__ativo=True,
                pergunta__tipo_resposta=PerguntaParticipacao.NUMERO,
                pergunta__eh_info_financeira=True,
            ).aggregate(total=Sum(Cast('valor_informado', output_field=models.FloatField())))['total']
        )
        if calcula_meses.years:
            meses = calcula_meses.years * 12
        else:
            meses = calcula_meses.months
        diferenca_dias = calcula_meses.days
        if concedido:
            if meses and not diferenca_dias:
                valor = (Decimal(meses).quantize(TWOPLACES) * concedido).quantize(TWOPLACES)
            elif not meses and diferenca_dias:
                valor = Decimal((Decimal(diferenca_dias).quantize(TWOPLACES) * concedido) / 30).quantize(TWOPLACES)
            else:
                valor = (Decimal(meses).quantize(TWOPLACES) * concedido).quantize(TWOPLACES) + Decimal(
                    (Decimal(diferenca_dias).quantize(TWOPLACES) * concedido) / 30
                ).quantize(TWOPLACES)
            total_gasto += valor

    return total_gasto
