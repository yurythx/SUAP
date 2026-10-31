from django.apps import apps
from django.db import transaction
from django.db.models import F, Max, Q

from djtools.management.commands import BaseCommandPlus


class Command(BaseCommandPlus):
    def print_title(self, title):
        self.stdout.write('')
        self.stdout.write('=' * len(title))
        self.stdout.write(title)
        self.stdout.write('=' * len(title))

    @transaction.atomic()
    def handle(self, *args, **options):
        title = 'Processo Eletrônico - Command que corrige os trâmites "descasados"'
        self.stdout.write('')
        self.stdout.write('- ' * len(title))
        self.stdout.write(title)
        self.stdout.write('- ' * len(title))

        self.stdout.write(
            'Cenário exemplo: Alguns processos não estavam podendo ser recebidos. Ao tentar recebê-los estava ocorrendo\n'
            'o erro "turned more than one Tramite -- it returned 2".  No caso identificamos que o problema é porque\n'
            'alguns processos estão com mais de um trâmite "em aberto". Possivelmente isso ocorreu na época em que\n'
            'havia um bug que permitia a remoção do último trâmite de um processo mas o mesmo não ocorria com os \n'
            'processos apensados.'
        )

        self.stdout.write('')
        self.stdout.write(
            'O objetivo deste command é identificar esses trâmites "descasados" e removê-los. Aproveitamos a ocorrência\n'
            'para verificar também se todos os processos estão com a referência correta no atributo "último trâmite".'
        )

        self.stdout.write('')
        executar_command = options.get('executar_command') or input('Deseja continuar? (S/n)').strip().upper() == 'S'
        if not executar_command:
            self.stdout.write('')
            self.stdout.write('Processamento abortado.')
            return

        Processo = apps.get_model('processo_eletronico', 'Processo')
        Tramite = apps.get_model('processo_eletronico', 'Tramite')

        self.print_title('Verificando se todos os processos estão com o último trâmite correto...')
        processos_com_ultimo_tramite_errado = Processo.objects.annotate(max_ultimo_tramite_id=Max('tramites__id')).filter(
            ~Q(max_ultimo_tramite_id=F('ultimo_tramite__id'))
        )
        if processos_com_ultimo_tramite_errado:
            self.stdout.write(f'Existem {processos_com_ultimo_tramite_errado.count()} processos com o último trâmite errado.')
            self.stdout.write('Iniciando a correção...')
            for p in processos_com_ultimo_tramite_errado:
                self.stdout.write('')
                self.stdout.write(f'<<< Processo {p} (id: {p.id}) >>> ')
                self.stdout.write(f' - Corrigindo o último trâmite de id #{p.ultimo_tramite.id} para id #{p.max_ultimo_tramite_id}')
                p.ultimo_tramite = Tramite.objects.get(pk=p.max_ultimo_tramite_id)
                p.save()
            self.stdout.write('')
            self.stdout.write('Correção finalizada com sucesso.')
        else:
            self.stdout.write('Todos os processos estão com o último trâmite correto. Nenhum ajuste é necessário.')

        self.print_title('Verificando se há trâmites descasados...')
        # Procurando todos os trâmites em aberto anteriores ao último trâmite do processo.
        tramites_descasados = Tramite.objects.filter(data_hora_recebimento__isnull=True, id__lt=F('processo__ultimo_tramite__id')).order_by(
            'processo__id'
        )
        if tramites_descasados:
            self.stdout.write(f'Existem {tramites_descasados.count()} trâmites descasados.')
            self.stdout.write('Iniciando a correção...')
            for t in tramites_descasados:
                if t.processo.apensamentoprocesso_set.exists():
                    processo_tem_registro_apensamento = 'Sim'
                else:
                    processo_tem_registro_apensamento = 'Não'

                self.stdout.write('')
                self.stdout.write(f'<<< Processo {t.processo} (id: {t.processo.id}, tem/teve apensamentos: {processo_tem_registro_apensamento}) >>>')
                self.stdout.write(f'Trâmite descasado: #{t.id}')
                self.stdout.write(' - Data Hora Encaminhamento: {}'.format(t.data_hora_encaminhamento.strftime('%d/%m/%Y %H:%M:%S')))
                self.stdout.write(' - Remetente:')
                self.stdout.write(f'    - Setor: {t.remetente_setor}')
                self.stdout.write(f'    - Pessoa: {t.remetente_vinculo}')
                self.stdout.write('    - Despacho: {}'.format(t.despacho_corpo or ''))
                self.stdout.write(' - Destinatário:')
                self.stdout.write('     - Setor: {}'.format(t.destinatario_setor or ''))
                self.stdout.write('     - Pessoa: {}'.format(t.destinatario_vinculo.pessoa if t.destinatario_vinculo else ''))
                t.delete()

            self.stdout.write('')
            self.stdout.write('Todos os trâmites descasados foram removidos com sucesso.')
        else:
            self.stdout.write('Não há trâmites descasados. Nenhum ajuste é necessário.')

        self.stdout.write('')
        self.stdout.write('FIM')
