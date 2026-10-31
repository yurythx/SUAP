import datetime
import os

import pandas as pd
from django.apps import apps
from django.contrib.contenttypes.models import ContentType
from django.core.management import call_command
from django.db import connection, transaction
from django.db.models import Count
from tqdm import tqdm

from comum.management.commands.terminal_utils import Terminal
from djtools.management.commands import BaseCommandPlus

Pessoa = apps.get_model('rh', 'Pessoa')
PessoaExterna = apps.get_model('rh', 'PessoaExterna')
Vinculo = apps.get_model('comum', 'Vinculo')
ProcessoIntressado = apps.get_model('processo_eletronico.ProcessoInteressado')
ProcessoAcompanhante = apps.get_model('processo_eletronico.ProcessoAcompanhante')
ComentarioProcesso = apps.get_model('processo_eletronico.ComentarioProcesso')
RequerimentoDigitalizadoCompartilhamento = apps.get_model('processo_eletronico.RequerimentoDigitalizadoCompartilhamento')
Tramite = apps.get_model('processo_eletronico.Tramite')
TramiteDistribuicao = apps.get_model('processo_eletronico.TramiteDistribuicao')
SolicitacaoCiencia = apps.get_model('processo_eletronico.SolicitacaoCiencia')
SolicitacaoJuntada = apps.get_model('processo_eletronico.SolicitacaoJuntada')
SolicitacaoJuntadaDocumento = apps.get_model('processo_eletronico.SolicitacaoJuntadaDocumento')
CompartilhamentoProcessoEletronicoSetorPessoa = apps.get_model('processo_eletronico.CompartilhamentoProcessoEletronicoSetorPessoa')
CompartilhamentoProcessoEletronicoPoderDeChefe = apps.get_model('processo_eletronico.CompartilhamentoProcessoEletronicoPoderDeChefe')
CompartilhamentoProcessoEletronicoLog = apps.get_model('processo_eletronico.CompartilhamentoProcessoEletronicoPoderDeChefe')
SolicitacaoDespacho = apps.get_model('processo_eletronico.SolicitacaoDespacho')
SolicitacaoAssinaturaComAnexacaoProcesso = apps.get_model('processo_eletronico.SolicitacaoAssinaturaComAnexacaoProcesso')
tipo_relacionamento_pe = ContentType.objects.get_for_model(PessoaExterna)


WORK_DIR_BEFORE = '/tmp/processo_eletronico_before'
WORK_DIR_AFTER = '/tmp/processo_eletronico_after'


def migrar_fk_processo(vinculo_pe, vinculo_id):
    ProcessoIntressado.objects.filter(vinculo_id=vinculo_pe).update(vinculo_id=vinculo_id, skip_history=True)
    ProcessoAcompanhante.objects.filter(vinculo_id=vinculo_pe).update(vinculo_id=vinculo_id, skip_history=True)
    ProcessoAcompanhante.objects.filter(vinculo_id=vinculo_pe).update(vinculo_id=vinculo_id, skip_history=True)
    ComentarioProcesso.objects.filter(vinculo_id=vinculo_pe).update(vinculo=vinculo_id, skip_history=True)


def migrar_fk_requerimento_digitalizado_compartilhamento(vinculo_pe, vinculo_id):
    RequerimentoDigitalizadoCompartilhamento.objects.filter(vinculo_id=vinculo_pe).update(vinculo_id=vinculo_id, skip_history=True)


def migrar_fk_tramite(vinculo_pe, vinculo_id):
    Tramite.objects.filter(recebido_por_id=vinculo_pe).update(recebido_por_id=vinculo_id, skip_history=True)
    Tramite.objects.filter(remetente_vinculo_id=vinculo_pe).update(remetente_vinculo_id=vinculo_id, skip_history=True)
    Tramite.objects.filter(destinatario_vinculo_id=vinculo_pe).update(destinatario_vinculo_id=vinculo_id, skip_history=True)
    Tramite.objects.filter(atribuido_para_id=vinculo_pe).update(atribuido_para_id=vinculo_id, skip_history=True)
    Tramite.objects.filter(atribuido_por_id=vinculo_pe).update(atribuido_por_id=vinculo_id, skip_history=True)


def migrar_fk_tramite_distribuicao(vinculo_pe, vinculo_id):
    TramiteDistribuicao.objects.filter(distribuir_para_id=vinculo_pe).update(distribuir_para_id=vinculo_id, skip_history=True)


def migrar_fk_solicitacoes_ciencia(vinculo_pe, vinculo_id):
    SolicitacaoCiencia.objects.filter(solicitado_id=vinculo_pe).update(solicitado_id=vinculo_id, skip_history=True)
    SolicitacaoCiencia.objects.filter(cancelada_por_id=vinculo_pe).update(cancelada_por_id=vinculo_id, skip_history=True)


def migrar_fk_solicitacoes_juntada(vinculo_pe, vinculo_id):
    SolicitacaoJuntada.objects.filter(solicitado_id=vinculo_pe).update(solicitado_id=vinculo_id, skip_history=True)
    SolicitacaoJuntada.objects.filter(cancelada_por_id=vinculo_pe).update(cancelada_por_id=vinculo_id, skip_history=True)
    SolicitacaoJuntadaDocumento.objects.filter(avaliado_por_id=vinculo_pe).update(avaliado_por_id=vinculo_id, skip_history=True)


def migrar_fk_solicitacoes_despacho(vinculo_pe, vinculo_id):
    SolicitacaoDespacho.objects.filter(remetente_vinculo_id=vinculo_pe).update(remetente_vinculo_id=vinculo_id, skip_history=True)
    SolicitacaoDespacho.objects.filter(solicitado_id=vinculo_pe).update(solicitado_id=vinculo_id, skip_history=True)
    SolicitacaoDespacho.objects.filter(destinatario_vinculo_tramite_id=vinculo_pe).update(
        destinatario_vinculo_tramite_id=vinculo_id, skip_history=True
    )


def migrar_compartilhamentos(vinculo_pe, vinculo_id):
    CompartilhamentoProcessoEletronicoSetorPessoa.objects.filter(vinculo_permitido_id=vinculo_pe).update(
        vinculo_permitido_id=vinculo_id, skip_history=True
    )
    CompartilhamentoProcessoEletronicoPoderDeChefe.objects.filter(vinculo_permitido_id=vinculo_pe).update(
        vinculo_permitido_id=vinculo_id, skip_history=True
    )
    CompartilhamentoProcessoEletronicoLog.objects.filter(vinculo_permitido_id=vinculo_pe).update(vinculo_permitido_id=vinculo_id, skip_history=True)


def migrar_pessoas_distribuir(vinculo_pe, vinculo_id):
    SolicitacaoAssinaturaComAnexacaoProcesso.objects.filter(vinculo_para_distribuir_id=vinculo_pe).update(
        vinculo_para_distribuir_id=vinculo_id, skip_history=True
    )


def fixit(pessoa_id):
    vinculo = Vinculo.objects.exclude(tipo_relacionamento=tipo_relacionamento_pe).get(pessoa_id=pessoa_id)
    vinculo_pe = Vinculo.objects.get(pessoa_id=pessoa_id, tipo_relacionamento=tipo_relacionamento_pe)
    migrar_fk_processo(vinculo_pe.id, vinculo.id)
    migrar_fk_processo(vinculo_pe.id, vinculo.id)
    migrar_fk_requerimento_digitalizado_compartilhamento(vinculo_pe.id, vinculo.id)
    migrar_fk_tramite(vinculo_pe.id, vinculo.id)
    migrar_fk_tramite_distribuicao(vinculo_pe.id, vinculo.id)
    migrar_fk_solicitacoes_ciencia(vinculo_pe.id, vinculo.id)
    migrar_fk_solicitacoes_despacho(vinculo_pe.id, vinculo.id)
    migrar_fk_solicitacoes_juntada(vinculo_pe.id, vinculo.id)
    migrar_compartilhamentos(vinculo_pe.id, vinculo.id)
    migrar_pessoas_distribuir(vinculo_pe.id, vinculo.id)


def dump_processo_eletronico(directory):
    call_command('processo_eletronico_dump_vinculo', executar_command_via_migration=True, directory=directory)


def check_dumps():
    file1_data = pd.read_csv(f'{WORK_DIR_BEFORE}/processo_eletronico_vinculo_md5sum.csv')
    file2_data = pd.read_csv(f'{WORK_DIR_AFTER}/processo_eletronico_vinculo_md5sum.csv')
    for row1, row2 in zip(file1_data, file2_data, strict=False):
        if row1 != row2:
            print('Checkagem falhou..... Rollback........')
            raise Exception('Sanity checking failed...........')
    print('Checagem de migracao dos vínculos de Pessoa Externa para outro vinculo executada com sucesso.')


class Command(Terminal, BaseCommandPlus):
    def __init__(self):
        Terminal.__init__(self)
        self.data = []
        self.cursor = connection.cursor()
        caminho_arquivo_corrente_sem_extensao = os.path.splitext(__file__)[0]
        self.log_file = f'{caminho_arquivo_corrente_sem_extensao}.log'

    @transaction.atomic()
    def doit(self, pessoas_qs):
        dump_processo_eletronico(WORK_DIR_BEFORE)
        list(tqdm(map(fixit, pessoas_qs), total=len(pessoas_qs), desc='Processing'))
        dump_processo_eletronico(WORK_DIR_AFTER)
        check_dumps()

    def handle(self, *args, **options):
        start_time = datetime.datetime.now()
        qs = Pessoa.objects.annotate(vinculo_count=Count('vinculo')).filter(vinculo_count=2)
        pessoas_qs = qs.filter(vinculo__tipo_relacionamento=tipo_relacionamento_pe).values_list('id', flat=True)
        self.doit(pessoas_qs)
        #
        print(f'Total Duration: {datetime.datetime.now() - start_time}')
