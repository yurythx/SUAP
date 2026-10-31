"""
Comando que verifica notas de requisições de ajuste interno
"""

from datetime import datetime, timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models.aggregates import Sum
from django.utils import timezone

from djtools.management.commands import BaseCommandPlus
from plan_estrategico.models import MovimentacaoCredito, MovimentacaoCreditoHistorico, MovimentacaoCreditoUnidade, NotaDotacao
from tesouro_gerencial.models import EventoNotaDotacao, NotaDotacao as NotaDotacaoTesouro
from tesouro_gerencial.models import NotaDotacaoItem


class Command(BaseCommandPlus):
    def verificar_requisicao(self, movimentacao):
        plano_interno_concedente = movimentacao.plano_interno.plano_interno
        plano_interno_recebedor = movimentacao.plano_interno_recebedor.plano_interno
        ptres_concedente = movimentacao.plano_interno.plano_interno.ptres
        ptres_recebedor = movimentacao.plano_interno_recebedor.plano_interno.ptres
        gnd_concedente = movimentacao.plano_interno.plano_interno.gnd.codigo
        gnd_recebedor = movimentacao.plano_interno_recebedor.plano_interno.gnd.codigo
        nd_movimentacao = NotaDotacao.objects.filter(movimentacao=movimentacao)

        for nd in nd_movimentacao:
            if not nd.valor and NotaDotacaoTesouro.objects.filter(numero=nd.numero).exists():
                nds_tesouro = NotaDotacaoTesouro.objects.filter(
                    numero=nd.numero, ptres__codigo=ptres_concedente.codigo, grupo_despesa_original=gnd_concedente
                )
                nds_tesouro_recebedor = NotaDotacaoTesouro.objects.filter(
                    numero=nd.numero, ptres__codigo=ptres_recebedor.codigo, grupo_despesa_original=gnd_recebedor
                )
                total_nds = 0
                total_nds_recebedor = 0
                if nds_tesouro:
                    nds_item = NotaDotacaoItem.objects.filter(
                        nota_dotacao=nds_tesouro[0],
                        plano_interno__codigo=plano_interno_concedente.codigo,
                        detalhamento='Redução',
                        evento__codigo__in=EventoNotaDotacao.REDUCAO,
                        responsavel_ug__codigo=nd.unidade_atendida.setor_equivalente.uo.codigo_ugr,
                    )
                    total_nds = nds_item.aggregate(total=Sum('valor'))
                if nds_tesouro_recebedor:
                    nds_item_recebedor = NotaDotacaoItem.objects.filter(
                        nota_dotacao=nds_tesouro_recebedor[0],
                        plano_interno__codigo=plano_interno_recebedor.codigo,
                        detalhamento='Acréscimo',
                        evento__codigo__in=EventoNotaDotacao.ACRESCIMO,
                        responsavel_ug__codigo=nd.unidade_atendida.setor_equivalente.uo.codigo_ugr,
                    )

                    total_nds_recebedor = nds_item_recebedor.aggregate(total=Sum('valor')).get('total')
                if (nds_tesouro and nds_tesouro_recebedor) and total_nds.get('total') == total_nds_recebedor:
                    nd.conferencia_pi_ptres_gnd = True
                    nd.valor = Decimal(total_nds_recebedor)
                else:
                    nd.conferencia_pi_ptres_gnd = False
                nd.save()
        if NotaDotacao.objects.filter(movimentacao=movimentacao, conferencia_pi_ptres_gnd=False).exists():
            movimentacao.status = MovimentacaoCredito.STATUS_INCONSISTENTE
            movimentacao.save()
            MovimentacaoCreditoHistorico.objects.create(
                movimentacao=movimentacao,
                status=MovimentacaoCredito.STATUS_INCONSISTENTE,
                alterado_em=datetime.now(),
            )

    def conferencia_siafi_requisicao(self, movimentacao):
        plano_interno_concedente = movimentacao.plano_interno.plano_interno
        plano_interno_recebedor = movimentacao.plano_interno_recebedor.plano_interno
        ptres_concedente = movimentacao.plano_interno.plano_interno.ptres
        ptres_recebedor = movimentacao.plano_interno_recebedor.plano_interno.ptres
        gnd_concedente = movimentacao.plano_interno.plano_interno.gnd.codigo
        gnd_recebedor = movimentacao.plano_interno_recebedor.plano_interno.gnd.codigo
        nd_movimentacao = NotaDotacao.objects.filter(movimentacao=movimentacao)
        if not NotaDotacao.objects.filter(movimentacao=movimentacao, valor__isnull=True).exists():
            mov_unidades = MovimentacaoCreditoUnidade.objects.filter(movimentacao=movimentacao)
            for unid in mov_unidades:
                for nd in nd_movimentacao:
                    nds_item_concedente = NotaDotacaoItem.objects.filter(
                        nota_dotacao__numero=nd.numero,
                        plano_interno__codigo=plano_interno_concedente.codigo,
                        nota_dotacao__ptres__codigo=ptres_concedente.codigo,
                        nota_dotacao__grupo_despesa_original=gnd_concedente,
                        detalhamento='Redução',
                        evento__codigo__in=EventoNotaDotacao.REDUCAO,
                        responsavel_ug__codigo=nd.unidade_atendida.setor_equivalente.uo.codigo_ugr,
                    )
                    total_nds_concedente = nds_item_concedente.aggregate(total=Sum('valor')).get('total')
                    nds_item_recebedor = NotaDotacaoItem.objects.filter(
                        nota_dotacao__numero=nd.numero,
                        plano_interno__codigo=plano_interno_recebedor.codigo,
                        nota_dotacao__ptres__codigo=ptres_recebedor.codigo,
                        nota_dotacao__grupo_despesa_original=gnd_recebedor,
                        detalhamento='Acréscimo',
                        evento__codigo__in=EventoNotaDotacao.ACRESCIMO,
                        responsavel_ug__codigo=nd.unidade_atendida.setor_equivalente.uo.codigo_ugr,
                    )
                    total_nds_recebedor = nds_item_recebedor.aggregate(total=Sum('valor')).get('total')
                    unid.valor_nd_conferido = 0
                    if (nds_item_concedente and nds_item_recebedor) and total_nds_concedente == total_nds_recebedor:
                        unid.valor_nd_conferido = Decimal(total_nds_recebedor)
                        unid.save()

                total_notas = unid.valor_nd_conferido

                if unid.valor == total_notas:
                    unid.conferencia_unidade_siafi = True
                else:
                    unid.conferencia_unidade_siafi = False
                unid.save()

            total = movimentacao.total_notas_dotacao()
            if total == movimentacao.get_total_unidades():
                movimentacao.conferencia_requisicao_siafi = True
            else:
                movimentacao.conferencia_requisicao_siafi = False
            movimentacao.save()

            if (movimentacao.conferencia_requisicao_siafi is False) or MovimentacaoCreditoUnidade.objects.filter(
                conferencia_unidade_siafi=False, movimentacao=movimentacao
            ).exists():
                movimentacao.status = MovimentacaoCredito.STATUS_INCONSISTENTE
                movimentacao.save()
                MovimentacaoCreditoHistorico.objects.create(
                    movimentacao=movimentacao,
                    status=MovimentacaoCredito.STATUS_INCONSISTENTE,
                    alterado_em=datetime.now(),
                )
            if (movimentacao.conferencia_requisicao_siafi is True) and not MovimentacaoCreditoUnidade.objects.filter(
                conferencia_unidade_siafi=False, movimentacao=movimentacao
            ).exists():
                movimentacao.status = MovimentacaoCredito.STATUS_CONCLUIDA
                movimentacao.save()
                MovimentacaoCreditoHistorico.objects.create(
                    movimentacao=movimentacao,
                    status=MovimentacaoCredito.STATUS_CONCLUIDA,
                    alterado_em=datetime.now(),
                )

    def verificar_prazo(self, movimentacao):
        if movimentacao.status == MovimentacaoCredito.STATUS_AGUARDANDO_VALIDACAO_SISTEMA:
            ultima_data_historico = MovimentacaoCreditoHistorico.objects.filter(movimentacao=movimentacao).order_by('-id')[0].alterado_em
            diferenca_tempo = timezone.now() - ultima_data_historico
            if diferenca_tempo > timedelta(days=5):
                movimentacao.status = MovimentacaoCredito.STATUS_INCONSISTENTE
                MovimentacaoCreditoHistorico.objects.create(
                    movimentacao=movimentacao,
                    status=MovimentacaoCredito.STATUS_INCONSISTENTE,
                    alterado_em=datetime.now(),
                )
                movimentacao.save()

    @transaction.atomic
    def handle(self, *args, **options):
        verbosity = options.get('verbosity', 3)
        movimentacoes = MovimentacaoCredito.objects.filter(
            status=MovimentacaoCredito.STATUS_AGUARDANDO_VALIDACAO_SISTEMA, tipo_requisicao__in=[MovimentacaoCredito.TIPO_AJUSTE_INTERNO]
        )
        for movimentacao in movimentacoes:
            self.verificar_requisicao(movimentacao)
            self.conferencia_siafi_requisicao(movimentacao)
            self.verificar_prazo(movimentacao)
        if verbosity:
            self.stdout.write('\nVerificação das notas das movimentações de ajuste interno.\n')
