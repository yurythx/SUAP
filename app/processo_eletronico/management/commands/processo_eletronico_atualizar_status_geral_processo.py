import datetime

import tqdm
from django.apps import apps
from django.db import transaction
from django.db.models import Q

from djtools.management.commands import BaseCommandPlus
from processo_eletronico.status import ProcessoStatus


class Command(BaseCommandPlus):
    @transaction.atomic()
    def handle(self, *args, **options):
        verbosity = options.get('verbosity', 3)
        ini = datetime.datetime.now()
        sucesso = True

        if verbosity:
            title = 'Processo Eletronico - Command que atualiza o status do processo e suas solicitacoes'
            print()
            print('- ' * len(title))
            print(title)
            print('- ' * len(title))

        Processo = apps.get_model('processo_eletronico', 'Processo')
        LogCommandProcessoEletronico = apps.get_model('processo_eletronico', 'LogCommandProcessoEletronico')

        processos = Processo.objects.filter(
            Q(status=ProcessoStatus.STATUS_ATIVO)
            | Q(status=ProcessoStatus.STATUS_REABERTO)
            | Q(status=ProcessoStatus.STATUS_AGUARDANDO_CIENCIA)
            | Q(status=ProcessoStatus.STATUS_AGUARDANDO_JUNTADA)
            | Q(status=ProcessoStatus.STATUS_EM_HOMOLOGACAO)
        ).order_by('id')

        qtd = processos.count()
        print(f'Foram encontrados {qtd} processos que podem vir a ter o status atualizado.')

        lista_log = []
        lista_log_erro = []
        lista_log.append(f'Serão verificados {qtd} processos')

        if processos.exists():
            if verbosity:
                print('Iniciando a atualizacao dos status ...')
                processos = tqdm.tqdm(processos)
            for processo in processos:
                try:
                    processo_novo = Processo.atualizar_status_processo(processo)
                    if processo_novo.status != processo.status:
                        lista_log.append(
                            f'Processo {processo.id} - {processo} passou de {processo.get_status_display()} para {processo_novo.get_status_display()}'
                        )
                except Exception as e:
                    sucesso = False
                    lista_log_erro.append(f'Processo {processo.id} - {processo} com status {processo.get_status_display()}. Erro: {e}')

        fim = datetime.datetime.now()
        lista_log.append(f'Início: {ini} Final: {fim}')
        if len(lista_log) == 2:
            lista_log.append('Nenhum processo teve seu status alterado')
        log = LogCommandProcessoEletronico()
        log.sucesso = sucesso
        log.comando = 'processo_eletronico_atualizar_status_geral_processo'
        log.dt_ini_execucao = ini
        log.dt_fim_execucao = fim
        log.log = '\n'.join(lista_log) if lista_log else None
        log.log_erro = '\n'.join(lista_log_erro) if lista_log_erro else None
        log.save()

        if verbosity:
            print()
            print(f'Fim do processamento {log.dt_fim_execucao}')
