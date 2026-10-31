"""
Comando que verifica notas de requisições de movimentação de crédito e estorno
"""

from datetime import datetime, timedelta

from django.db import transaction
from django.utils import timezone

from djtools.management.commands import BaseCommandPlus
from plan_estrategico.models import MovimentacaoCredito, MovimentacaoCreditoHistorico, MovimentacaoCreditoUnidade, NotaCredito, NotaDotacao
from tesouro_gerencial.models import EventoNotaDotacao, NotaCredito as NotaCreditoTesouro
from tesouro_gerencial.models import NotaCreditoItem, NotaDotacaoItem
from tesouro_gerencial.models import NotaDotacao as NotaDotacaoTesouro


class Command(BaseCommandPlus):
    def verificar_requisicao(self, movimentacao):
        plano_interno = movimentacao.plano_interno.plano_interno
        ptres = movimentacao.plano_interno.plano_interno.ptres
        gnd = movimentacao.plano_interno.plano_interno.gnd.codigo
        nc_movimentacao = NotaCredito.objects.filter(movimentacao=movimentacao)
        nd_movimentacao = NotaDotacao.objects.filter(movimentacao=movimentacao)
        for nc in nc_movimentacao:
            if not nc.valor and NotaCreditoTesouro.objects.filter(numero=nc.numero).exists():
                ncs_tesouro = NotaCreditoTesouro.objects.filter(numero=nc.numero)
                for nc_tesouro in ncs_tesouro:
                    ncs_item = NotaCreditoItem.objects.filter(
                        nota_credito=nc_tesouro, plano_interno__codigo=plano_interno.codigo, ptres__codigo=ptres.codigo, grupo_despesa_original=gnd
                    )
                    if ncs_item:
                        nc.conferencia_pi_ptres_gnd = True
                        nc.valor = 0
                        for nc_item in ncs_item:
                            nc.valor += abs(nc_item.valor)
                    else:
                        nc.conferencia_pi_ptres_gnd = False
                        movimentacao.status = MovimentacaoCredito.STATUS_INCONSISTENTE
                        movimentacao.save()
                        MovimentacaoCreditoHistorico.objects.create(
                            movimentacao=movimentacao,
                            status=MovimentacaoCredito.STATUS_INCONSISTENTE,
                            alterado_em=datetime.now(),
                        )
                nc.save()
        for nd in nd_movimentacao:
            if not nd.valor and NotaDotacaoTesouro.objects.filter(numero=nd.numero).exists():
                nds_tesouro = NotaDotacaoTesouro.objects.filter(numero=nd.numero, ptres__codigo=ptres.codigo, grupo_despesa_original=gnd)
                for nd_tesouro in nds_tesouro:
                    filters = {
                        'nota_dotacao': nd_tesouro,
                        'plano_interno__codigo': plano_interno.codigo,
                        'detalhamento': 'Acréscimo',
                        'evento__codigo__in': EventoNotaDotacao.ACRESCIMO,
                        'responsavel_ug__codigo': nd.unidade_atendida.setor_equivalente.uo.codigo_ugr,
                    }

                    nds_item = NotaDotacaoItem.objects.filter(**filters)

                    if nds_item:
                        nd.conferencia_pi_ptres_gnd = True
                        nd.valor = 0
                        for nd_item in nds_item:
                            nd.valor += abs(nd_item.valor)
                    else:
                        nd.conferencia_pi_ptres_gnd = False
                        movimentacao.status = MovimentacaoCredito.STATUS_INCONSISTENTE
                        movimentacao.save()
                        MovimentacaoCreditoHistorico.objects.create(
                            movimentacao=movimentacao,
                            status=MovimentacaoCredito.STATUS_INCONSISTENTE,
                            alterado_em=datetime.now(),
                        )

                nd.save()
        if (
            NotaCredito.objects.filter(movimentacao=movimentacao, conferencia_pi_ptres_gnd=False).exists()
            or NotaDotacao.objects.filter(movimentacao=movimentacao, conferencia_pi_ptres_gnd=False).exists()
        ):
            movimentacao.status = MovimentacaoCredito.STATUS_INCONSISTENTE
            movimentacao.save()
            MovimentacaoCreditoHistorico.objects.create(
                movimentacao=movimentacao,
                status=MovimentacaoCredito.STATUS_INCONSISTENTE,
                alterado_em=datetime.now(),
            )

    def conferencia_siafi_requisicao(self, movimentacao):
        plano_interno = movimentacao.plano_interno.plano_interno
        ptres = movimentacao.plano_interno.plano_interno.ptres
        gnd = movimentacao.plano_interno.plano_interno.gnd.codigo
        nc_movimentacao = NotaCredito.objects.filter(movimentacao=movimentacao)
        nd_movimentacao = NotaDotacao.objects.filter(movimentacao=movimentacao)
        if (
            not NotaCredito.objects.filter(movimentacao=movimentacao, valor__isnull=True).exists()
            and not NotaDotacao.objects.filter(movimentacao=movimentacao, valor__isnull=True).exists()
        ):
            mov_unidades = MovimentacaoCreditoUnidade.objects.filter(movimentacao=movimentacao)
            for unid in mov_unidades:
                for nc in nc_movimentacao:
                    ncs_item = NotaCreditoItem.objects.filter(
                        nota_credito__numero=nc.numero,
                        plano_interno__codigo=plano_interno.codigo,
                        ptres__codigo=ptres.codigo,
                        grupo_despesa_original=gnd,
                        responsavel_ug__codigo=unid.unidade.setor_equivalente.uo.codigo_ugr,
                    )
                    if ncs_item:
                        unid.valor_nc_conferido = 0
                        for nc_item in ncs_item:
                            unid.valor_nc_conferido += abs(nc_item.valor)
                        unid.save()
                for nd in nd_movimentacao:
                    nds_item = NotaDotacaoItem.objects.filter(
                        nota_dotacao__numero=nd.numero,
                        plano_interno__codigo=plano_interno.codigo,
                        nota_dotacao__ptres__codigo=ptres.codigo,
                        nota_dotacao__grupo_despesa_original=gnd,
                        responsavel_ug__codigo=unid.unidade.setor_equivalente.uo.codigo_ugr,
                        detalhamento='Acréscimo',
                        evento__codigo__in=EventoNotaDotacao.ACRESCIMO,
                    )
                    if nds_item:
                        unid.valor_nd_conferido = 0
                        for nd_item in nds_item:
                            unid.valor_nd_conferido += abs(nd_item.valor)
                        unid.save()

                total_notas = (unid.valor_nc_conferido or 0) + (unid.valor_nd_conferido or 0)

                if unid.valor == total_notas:
                    unid.conferencia_unidade_siafi = True
                else:
                    unid.conferencia_unidade_siafi = False
                unid.save()

            total = movimentacao.total_notas_credito() + movimentacao.total_notas_dotacao()
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
            status=MovimentacaoCredito.STATUS_AGUARDANDO_VALIDACAO_SISTEMA,
            tipo_requisicao__in=[MovimentacaoCredito.TIPO_MOVIMENTACAO_CREDITO, MovimentacaoCredito.TIPO_ESTORNO_CREDITO],
        )
        for movimentacao in movimentacoes:
            self.verificar_requisicao(movimentacao)
            self.conferencia_siafi_requisicao(movimentacao)
            self.verificar_prazo(movimentacao)
        if verbosity:
            self.stdout.write('\nVerificação das notas das movimentações de crédito e estorno.\n')
