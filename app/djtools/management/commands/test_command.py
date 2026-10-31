import time

from djtools.management.commands import BaseCommandPlus


class Command(BaseCommandPlus):
    help = 'Reformatação automática dos códigos do SUAP'

    def add_arguments(self, parser):
        parser.add_argument('apps', nargs='*', type=str)

        parser.add_argument(
            '--all',
            action='store_true',
            help='Realiza uma verificação em todos os arquivos e não somente os alterados em relação a branch master.',
        )
        parser.add_argument(
            '--wait',
            type=int,
            help='Número de segundos para aguardar antes de finalizar o comando.',
        )

    def handle(self, *args, **options):
        wait_seconds = options['wait'] or -1
        if wait_seconds > 0:
            self.stdout.write(self.style.SUCCESS(f'Aguardando {wait_seconds} segundo(s)...'))

            time.sleep(wait_seconds)
        print(f'Foram obtidos os seguintes argumentos: {args} {options}')
