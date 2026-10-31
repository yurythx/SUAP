import datetime

from django.apps import apps
from django.db import transaction

from djtools.management.commands import BaseCommandPlus
from processo_eletronico.status import ProcessoStatus, SolicitacaoJuntadaDocumentoStatus, SolicitacaoJuntadaStatus


class Command(BaseCommandPlus):
    @transaction.atomic()
    def handle(self, *args, **options):
        title = 'Processo Eletronico - Command que corrige o status do processo para permitir a analise de documentos \njuntados.'
        print()
        print('- ' * len(title))
        print(title)
        print('- ' * len(title))

        print()
        print(
            'O objetivo deste command eh alterar o status do processo para "Em validacao de juntada de documentos" para '
            'todos aqueles processos que estao com juntada "Concluida pelo usuario", com documentos "Pendentes" de '
            'avaliacao e com o status do processo "Em tramite", destravando assim o processo e permitindo que os documentos '
            'juntados possam ser avaliados.\n'
        )

        executar_command_via_migration = options.get('executar_command_via_migration')

        if executar_command_via_migration:
            executar_pra_valer = True
        else:
            user_input = input('Informe o que deseja fazer? (SIMULAR/EXECUTAR/ABORTAR) ').strip().upper()

            executar_simulacao = user_input == 'SIMULAR'
            executar_pra_valer = user_input == 'EXECUTAR'
            if not executar_simulacao and not executar_pra_valer:
                print()
                print('Processamento abortado.')
                return

        print()
        print('Inicio do processamento: {}'.format(datetime.datetime.now().strftime('%d/%m/%Y - %H:%M:%S')))
        print()

        Processo = apps.get_model('processo_eletronico', 'Processo')

        processos = Processo.objects.filter(
            status=ProcessoStatus.STATUS_ATIVO,
            tramites__solicitacaojuntada__status=SolicitacaoJuntadaStatus.STATUS_CONCLUIDO,
            tramites__solicitacaojuntada__solicitacaojuntadadocumento__status=SolicitacaoJuntadaDocumentoStatus.STATUS_ESPERANDO,
        ).distinct()

        print(f'Foram encontrados {processos.count()} processos que estao "travados" e que precisam ter o status corrigido.')
        if processos.exists():
            print('Iniciando a correcao...')
            for processo in processos:
                print(f' - Processo {processo} (id: {processo.id}, setor atual: {processo.setor_atual})')

            if executar_pra_valer:
                # O update esta sendo executado "via banco" para evitar o erro "AttributeError: Direct status modification
                # is not allowed", uma vez que esse atributo "status" eh controlado via mehtodos "transitions".
                processos.update(status=ProcessoStatus.STATUS_EM_HOMOLOGACAO)

            print()

        print('Processamento concluido com sucesso.')

        if not executar_pra_valer:
            print(
                'OBS: Este processamento foi apenas uma SIMULACAO. Nada foi gravado no banco de dados. Para executar '
                'algo em definitivo, realize novamente o processamento e escolha a opcao "EXECUTAR".'
            )

        print()
        print('Fim do processamento: {}'.format(datetime.datetime.now().strftime('%d/%m/%Y - %H:%M:%S')))
