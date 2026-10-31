import datetime

from django.apps import apps
from django.db import transaction

from djtools.management.commands import BaseCommandPlus
from processo_eletronico.status import ProcessoStatus


class Command(BaseCommandPlus):
    @transaction.atomic()
    def handle(self, *args, **options):
        title = (
            'Processo Eletronico - Command que corrige os ultimos tramites que estao como setor destinatario\n'
            'um setor SIAPE ao inves de um setor SUAP.'
        )
        print()
        print('- ' * len(title))
        print(title)
        print('- ' * len(title))

        print()
        print(
            'O objetivo deste command eh varrer todos os ultimos tramites de processos que estao ativos e que o desti-\n'
            'natario setor do tramite eh um setor SIAPE ao inves de ser um setor SUAP. Isso faz com que o botao de\n'
            '"Receber Processo" fique indisponível. Isso foi possivel porque a tela DeferirDespachoSetorForm\n'
            'usava diretamente o atributo destinatario_setor_tramite do modelo SolicitacaoDespacho, e como o manager\n'
            'default atual de Setor eh "todos", entao eram listados tanto setores SIAPE como SUAP, permitindo o usuario\n'
            'tal alteracao.'
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
        print('Início do processamento: {}'.format(datetime.datetime.now().strftime('%d/%m/%Y - %H:%M:%S')))
        print()

        Tramite = apps.get_model('processo_eletronico', 'Tramite')
        Setor = apps.get_model('rh', 'Setor')

        ultimos_tramites_usando_setor_siap = Tramite.objects.filter(
            processo_ultimo_tramite__isnull=False, processo__status=ProcessoStatus.STATUS_ATIVO, destinatario_setor__codigo__isnull=False
        )

        print(f'Foram encontrados {ultimos_tramites_usando_setor_siap.count()} tramites que precisam ser ajustados...')
        for tramite in ultimos_tramites_usando_setor_siap:
            setor_siap = tramite.destinatario_setor
            # Dicionario contendo a sigla "SIAPE" e a sigla "SUAP" equivalente. Tivemos que fazer esse mapeamento pontual
            # pros setores que as siglas sao diferentes e que apresentaram o problema tratado aqui nesse command.
            setores_siap_com_siglas_diferentes = {'COGPE-AP': 'COGPE/AP', 'DIARENCNAT': 'DIAREN/CNAT', 'DIAES': 'DIAES/CNAT'}

            # Tentando localizar o Setor Suap correspondente...
            setor_suap = Setor.objects.suap_ativos().filter(sigla=setores_siap_com_siglas_diferentes.get(setor_siap.sigla, setor_siap.sigla))

            if setor_suap.exists():
                if setor_suap.count() > 1:
                    raise Exception(f'Existe mais de um setor SUAP para o setor SIAPE {setor_siap} informado!')

                setor_suap = setor_suap.first()
                print()
                print(f'Processo {tramite.processo} - {tramite}')
                print('-' * 80)
                print('Alterado o setor destinatario do setor siape para o setor suap correspondente:')
                print('Data do encaminhamento: {}'.format(tramite.data_hora_encaminhamento.strftime('%d/%m/%Y - %H:%M:%S')))
                print(f'Remetente: {tramite.remetente_vinculo}')
                print(f'Setor SIAP "{setor_siap}" (id: {setor_siap.id}, codigo: {setor_siap.codigo})')
                print(f'Setor SUAP "{setor_suap}" (id: {setor_suap.id}, codigo: {setor_suap.codigo})')

                tramite.destinatario_setor = setor_suap

                if executar_pra_valer:
                    tramite.save()
                print('Tramite ajustado com sucesso.')
            else:
                print(f'Setor SIAP "{setor_siap}" (id: {setor_siap.id}, codigo: {setor_siap.codigo}, Processo: {tramite.processo})')

        print()
        print('Processamento concluído com sucesso.')
        if not executar_pra_valer:
            print(
                'OBS: Este processamento foi apenas uma SIMULACAO. Nada foi gravado no banco de dados. Para executar '
                'algo em definitivo, realize novamente o processamento e escolha a opçao "EXECUTAR".'
            )

        print()
        print('Fim do processamento: {}'.format(datetime.datetime.now().strftime('%d/%m/%Y - %H:%M:%S')))
