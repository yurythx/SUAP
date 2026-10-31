"""Atualiza as bases de dados abertos cuja periodicidade venceu.

Agendado no Celery Beat por ``dados_abertos/beat.py`` (diário), que guarda a saída de cada
execução no admin de agendamentos. Rodar à mão é seguro: a rotina é idempotente — base sem
novidade só tem o relógio confirmado, e nada é publicado sem liberação do LAI.

Uso::

    python manage.py atualizar_bases_dados_abertos
    python manage.py atualizar_bases_dados_abertos --simular
"""

from django.core.management.base import BaseCommand

from dados_abertos.services.atualizacao_service import bases_vencidas, executar


class Command(BaseCommand):
    help = 'Re-coleta e republica no CKAN as bases de dados abertos cuja frequência de atualização venceu.'

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            '--simular',
            action='store_true',
            help='Apenas lista as bases vencidas, sem coletar nem publicar.',
        )

    def handle(self, *args, **options) -> None:
        if options['simular']:
            vencidas = bases_vencidas()
            for base in vencidas:
                self.stdout.write(f'  {base.nome} — {base.titulo}')
            self.stdout.write(self.style.SUCCESS(f'{len(vencidas)} base(s) vencida(s).'))
            return

        resumo = executar()
        self.stdout.write(self.style.SUCCESS(f'Verificadas: {resumo.verificadas} | Publicadas: {resumo.publicadas} | Pendentes: {resumo.pendentes}'))
