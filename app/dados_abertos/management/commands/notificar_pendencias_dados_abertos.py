"""Notifica cada papel das pendências de dados abertos sob sua responsabilidade.

Agendado no Celery Beat por ``dados_abertos/beat.py`` com cadência **própria** — semanal, enquanto
a coleta (``atualizar_bases_dados_abertos``) roda diária. Separar os dois relógios evita repetir a
mesma cobrança todo dia e deixa a frequência ajustável no admin, sem deploy e sem o módulo precisar
guardar estado de "última notificação enviada".

Uso::

    python manage.py notificar_pendencias_dados_abertos
    python manage.py notificar_pendencias_dados_abertos --dry-run
"""

from django.core.management.base import BaseCommand

from dados_abertos.services.notificacao_service import notificar


class Command(BaseCommand):
    help = 'Envia a cada responsável o resumo das pendências de dados abertos que lhe cabem.'

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Apenas registra no log o que seria enviado, sem notificar ninguém.',
        )

    def handle(self, *args, **options) -> None:
        resumo = notificar(dry_run=options['dry_run'])
        prefixo = '[simulação] ' if options['dry_run'] else ''
        self.stdout.write(
            self.style.SUCCESS(f'{prefixo}Pessoais: {resumo.pessoais} | Coletivas: {resumo.coletivas} | Sem vínculo: {resumo.sem_vinculo}')
        )
