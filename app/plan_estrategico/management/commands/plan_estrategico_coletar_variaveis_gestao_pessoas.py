"""
Comando que coleta valores atualizados das variaveis de gestão de pessoas.
"""

import datetime
from datetime import date

from django.db import transaction
from django.db.models.aggregates import Sum

from djtools.management.commands import BaseCommandPlus
from plan_estrategico.models import PeriodoPreenchimentoVariavel, VariavelCampus, VariavelTrimestralCampus
from rh.models import Servidor, ServidorAfastamento, UnidadeOrganizacional


class Command(BaseCommandPlus):
    @transaction.atomic
    def handle(self, *args, **options):
        if PeriodoPreenchimentoVariavel.objects.filter(data_inicio__date=datetime.date.today()).exists():
            ano = PeriodoPreenchimentoVariavel.objects.filter(data_inicio__date=datetime.date.today()).first().ano.ano
            hoje = datetime.datetime.now()
            periodo_referencia = date(ano, 1, 1)
            for uo in UnidadeOrganizacional.objects.uo().all():
                variaveis = (
                    'ADP_serv',
                    'ATS_15mais',
                    'ATS_ate15',
                    'ATS_total',
                    'SAP',
                    'SAP_E1',
                    'TAE',
                )
                ATIVO_PERMANENTE = '01'
                CEDIDO = '03'
                COLABORADOR_PCCTAE = '41'
                EXCEDENTE_A_LOTACAO = '11'
                EXERCICIO_PROVISORIO = '19'
                EXERC_DESCENT_CARREI = '18'

                SITUACOES_EM_EXERCICIO = [
                    ATIVO_PERMANENTE,
                    CEDIDO,
                    EXCEDENTE_A_LOTACAO,
                    EXERCICIO_PROVISORIO,
                    EXERC_DESCENT_CARREI,
                    COLABORADOR_PCCTAE,
                ]
                for var in variaveis:
                    total = 0
                    if var == 'SAP' or var == 'SAP_E1':
                        total = Servidor.objects.filter(situacao__codigo__in=SITUACOES_EM_EXERCICIO, setor__uo=uo, ativo=True).count()
                    if var == 'TAE':
                        total = Servidor.objects.filter(
                            situacao__codigo__in=SITUACOES_EM_EXERCICIO, setor__uo=uo, ativo=True, eh_tecnico_administrativo=True
                        ).count()

                    afastamentos_servidor = (
                        ServidorAfastamento.objects.filter(
                            afastamento__codigo__in=['0087', '0084', '0162', '0270'],
                            data_termino__gte=periodo_referencia,
                            data_inicio__lte=hoje,
                            servidor__setor__uo=uo,
                            cancelado=False,
                        )
                        .values('servidor')
                        .annotate(total=Sum('quantidade_dias_afastamento'))
                    )
                    total_15mais = 0
                    total_ate15 = 0
                    for afastamento in afastamentos_servidor:
                        if afastamento['total'] > 15:
                            total_15mais += 1
                        else:
                            total_ate15 += 1
                    if var == 'ATS_ate15':
                        total = total_ate15
                    if var == 'ATS_15mais':
                        total = total_15mais
                    if var == 'ATS_total':
                        total = afastamentos_servidor.count()
                    if var == 'ADP_serv':
                        total = afastamentos_servidor.filter(afastamento__codigo='0087').count()
                    if VariavelCampus.objects.filter(variavel__sigla=var, uo=uo, ano=ano).exists():
                        variavel = VariavelCampus.objects.get(variavel__sigla=var, uo=uo, ano=ano)
                        variavel.valor_real = total
                        variavel.data_atualizacao = datetime.datetime.now()
                        variavel.save()
                        trimestre = PeriodoPreenchimentoVariavel.objects.filter(data_inicio__date=datetime.date.today()).first().trimestre
                        variavel_trimestral = VariavelTrimestralCampus.objects.get_or_create(
                            variavel=variavel, ano=variavel.ano, trimestre=trimestre
                        )[0]
                        variavel_trimestral.valor = variavel.valor_real
                        variavel_trimestral.save()

            print('Váriáveis de Gestão de Pessoas Importadas')
