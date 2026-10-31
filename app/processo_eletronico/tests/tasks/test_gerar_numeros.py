"""O comando mantém os totais sem consultas proporcionais ao número de processos."""

from datetime import datetime, timedelta
from io import StringIO

import pytest
from django.core.management import call_command
from django.db import connection
from django.db.models import Avg, F
from django.test.utils import CaptureQueriesContext

from documento_eletronico.models import DocumentoDigitalizado, DocumentoTexto
from documento_eletronico.status import DocumentoStatus
from processo_eletronico.models import (
    NumerosProcessoEletronicoGeral,
    NumerosProcessoEletronicoPorSetor,
    NumerosProcessoEletronicoPorTipo,
    NumerosProcessoEletronicoTempoPorTipo,
    Processo,
    Tramite,
)
from processo_eletronico.status import ProcessoStatus
from processo_eletronico.tests.factories import ProcessoFactory, TipoProcessoFactory, TramiteFactory
from rh.models import Setor
from rh.tests.factories import ServidorFactory, SetorFactory

pytestmark = pytest.mark.django_db
COMANDO = 'processo_eletronico_gerar_numeros'


def test_comando_preserva_totais_e_medias_ao_reprocessar(sync_permissions: None, setor_com_siorg: Setor) -> None:
    usuario = ServidorFactory(setor=setor_com_siorg).get_user()
    destino = SetorFactory()
    vazio = SetorFactory()
    tipo = TipoProcessoFactory()
    tipo_vazio = TipoProcessoFactory()
    processos = ProcessoFactory.create_batch(3, setor_criacao=setor_com_siorg, usuario_gerador=usuario, tipo_processo=tipo)
    processo = processos[0]
    processo.interessados.add(usuario.get_vinculo())
    TramiteFactory.create_batch(2, processo=processo, remetente_setor=setor_com_siorg, destinatario_setor=destino)
    TramiteFactory(processo=processo, remetente_setor=destino, destinatario_setor=setor_com_siorg)
    inicio = datetime(2026, 1, 1)
    for indice, processo in enumerate(processos):
        Processo.objects.filter(pk=processo.pk).update(
            status=ProcessoStatus.STATUS_FINALIZADO,
            data_hora_criacao=inicio,
            data_finalizacao=inicio + timedelta(days=indice + 1, hours=12) if indice < 2 else None,
        )
    saida = StringIO()
    call_command(COMANDO, stdout=saida)
    assert 'Tempo médio por UO e tipo:' in saida.getvalue()
    call_command(COMANDO, verbosity=0)

    origem = NumerosProcessoEletronicoPorSetor.objects.get(setor=setor_com_siorg)
    assert origem.criou == Processo.objects.filter(setor_criacao=setor_com_siorg).count()
    assert origem.tramitou == Tramite.objects.filter(destinatario_setor=setor_com_siorg).values('processo').distinct().count()
    recebido = NumerosProcessoEletronicoPorSetor.objects.get(setor=destino)
    assert recebido.tramitou == Tramite.objects.filter(destinatario_setor=destino).values('processo').distinct().count()
    assert NumerosProcessoEletronicoPorSetor.objects.get(setor=vazio).criou == 0
    assert NumerosProcessoEletronicoPorTipo.objects.get(tipo=tipo).qtd == Processo.objects.filter(tipo_processo=tipo).count()
    assert NumerosProcessoEletronicoPorTipo.objects.get(tipo=tipo_vazio).qtd == 0
    geral = NumerosProcessoEletronicoGeral.objects.get()
    assert Processo.objects.filter(status=ProcessoStatus.STATUS_FINALIZADO).count() == geral.STATUS_FINALIZADO
    assert geral.qtd_processos == Processo.objects.count()
    assert geral.qtd_documentos_texto == DocumentoTexto.objects.exclude(status=DocumentoStatus.STATUS_CANCELADO).count()
    assert geral.qtd_documentos_digitalizado == DocumentoDigitalizado.objects.count()
    media = NumerosProcessoEletronicoTempoPorTipo.objects.get(uo_origem_interessado=setor_com_siorg.uo, tipo=tipo)
    finalizados = Processo.objects.filter(setor_criacao__uo=setor_com_siorg.uo, tipo_processo=tipo, status=ProcessoStatus.STATUS_FINALIZADO)
    assert media.qtd == finalizados.count()
    assert media.tempo_medio == finalizados.aggregate(tempo=Avg(F('data_finalizacao') - F('data_hora_criacao')))['tempo'].days
    sem_processos = NumerosProcessoEletronicoTempoPorTipo.objects.get(uo_origem_interessado=setor_com_siorg.uo, tipo=tipo_vazio)
    assert sem_processos.qtd == 0
    assert sem_processos.tempo_medio is None


def test_consultas_nao_crescem_com_a_quantidade_de_processos(sync_permissions: None, setor_com_siorg: Setor) -> None:
    usuario = ServidorFactory(setor=setor_com_siorg).get_user()
    tipo = TipoProcessoFactory()
    ProcessoFactory(setor_criacao=setor_com_siorg, usuario_gerador=usuario, tipo_processo=tipo)
    call_command(COMANDO, verbosity=0)
    with CaptureQueriesContext(connection) as poucas:
        call_command(COMANDO, verbosity=0)
    ProcessoFactory.create_batch(30, setor_criacao=setor_com_siorg, usuario_gerador=usuario, tipo_processo=tipo)
    with CaptureQueriesContext(connection) as muitas:
        call_command(COMANDO, verbosity=0)
    assert len(muitas) == len(poucas)
    assert NumerosProcessoEletronicoPorTipo.objects.get(tipo=tipo).qtd == Processo.objects.filter(tipo_processo=tipo).count()
