"""Atualiza os indicadores em lote, sem consultas individuais por processo."""

from time import perf_counter
from typing import Any

from django.db import transaction
from django.db.models import Avg, Count, F

from djtools.management.commands import BaseCommandPlus
from documento_eletronico.models import DocumentoDigitalizado, DocumentoTexto
from documento_eletronico.status import DocumentoStatus
from processo_eletronico.models import (
    NumerosProcessoEletronicoGeral,
    NumerosProcessoEletronicoPorSetor,
    NumerosProcessoEletronicoPorTipo,
    NumerosProcessoEletronicoTempoPorTipo,
    Processo,
    TipoProcesso,
    Tramite,
)
from processo_eletronico.status import ProcessoStatus
from rh.models import Setor, UnidadeOrganizacional


class Command(BaseCommandPlus):
    help = 'Atualiza os números de processos com agregações no banco e gravação em lote.'

    @transaction.atomic()
    def handle(self, *args: Any, **options: Any) -> None:
        etapas = (
            ('Por setor', self.processar_setores),
            ('Por tipo', self.processar_tipos),
            ('Geral', self.processar_geral),
            ('Tempo médio por UO e tipo', self.processar_tempos),
        )
        for nome, processar in etapas:
            inicio = perf_counter()
            processar()
            if options.get('verbosity', 1):
                self.stdout.write(f'{nome}: {perf_counter() - inicio:.2f}s')

    def processar_setores(self) -> None:
        criados = dict(Processo.objects.order_by().values('setor_criacao_id').annotate(total=Count('pk')).values_list('setor_criacao_id', 'total'))
        tramitados = dict(
            Tramite.objects.order_by()
            .values('destinatario_setor_id')
            .annotate(total=Count('processo_id', distinct=True))
            .values_list('destinatario_setor_id', 'total')
        )
        numeros = [
            NumerosProcessoEletronicoPorSetor(setor_id=pk, criou=criados.get(pk, 0), tramitou=tramitados.get(pk, 0))
            for pk in Setor.objects.suap_ativos().values_list('pk', flat=True)
        ]
        NumerosProcessoEletronicoPorSetor.objects.all().delete()
        NumerosProcessoEletronicoPorSetor.objects.bulk_create(numeros, batch_size=1000)

    def processar_tipos(self) -> None:
        quantidades = dict(
            Processo.objects.order_by().values('tipo_processo_id').annotate(total=Count('pk')).values_list('tipo_processo_id', 'total')
        )
        numeros = [
            NumerosProcessoEletronicoPorTipo(tipo_id=pk, qtd=quantidades.get(pk, 0)) for pk in TipoProcesso.objects.values_list('pk', flat=True)
        ]
        NumerosProcessoEletronicoPorTipo.objects.all().delete()
        NumerosProcessoEletronicoPorTipo.objects.bulk_create(numeros, batch_size=1000)

    def processar_geral(self) -> None:
        quantidades = dict(Processo.objects.order_by().values('status').annotate(total=Count('pk')).values_list('status', 'total'))
        campos = (
            'STATUS_ATIVO',
            'STATUS_ARQUIVADO',
            'STATUS_SOBRESTADO',
            'STATUS_FINALIZADO',
            'STATUS_ANEXADO',
            'STATUS_REABERTO',
            'STATUS_AGUARDANDO_CIENCIA',
            'STATUS_AGUARDANDO_JUNTADA',
            'STATUS_EM_HOMOLOGACAO',
        )
        dados = {campo: quantidades.get(getattr(ProcessoStatus, campo), 0) for campo in campos}
        NumerosProcessoEletronicoGeral.objects.all().delete()
        NumerosProcessoEletronicoGeral.objects.create(
            **dados,
            qtd_processos=sum(dados.values()),
            qtd_documentos_texto=DocumentoTexto.objects.exclude(status=DocumentoStatus.STATUS_CANCELADO).count(),
            qtd_documentos_digitalizado=DocumentoDigitalizado.objects.count(),
        )

    def processar_tempos(self) -> None:
        agrupados = (
            Processo.objects.filter(status=ProcessoStatus.STATUS_FINALIZADO)
            .order_by()
            .values('setor_criacao__uo_id', 'tipo_processo_id')
            .annotate(tempo=Avg(F('data_finalizacao') - F('data_hora_criacao')), total=Count('pk'))
        )
        tempos = {
            (linha['setor_criacao__uo_id'], linha['tipo_processo_id']): (linha['tempo'].days if linha['tempo'] else None, linha['total'])
            for linha in agrupados
        }
        tipos = list(TipoProcesso.objects.values_list('pk', flat=True))
        numeros = []
        for uo_id in UnidadeOrganizacional.objects.suap().values_list('pk', flat=True):
            for tipo_id in tipos:
                tempo, quantidade = tempos.get((uo_id, tipo_id), (None, 0))
                numeros.append(
                    NumerosProcessoEletronicoTempoPorTipo(uo_origem_interessado_id=uo_id, tipo_id=tipo_id, tempo_medio=tempo, qtd=quantidade)
                )
        NumerosProcessoEletronicoTempoPorTipo.objects.all().delete()
        NumerosProcessoEletronicoTempoPorTipo.objects.bulk_create(numeros, batch_size=1000)
