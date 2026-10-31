"""
Management command: reload_catalogo

Recarrega o catálogo RSC-TAE (Requisito + Nivel + GrupoSaberCompetencia + RolSaberCompetencia)
a partir das fixtures, apagando os registros dependentes antes de recarregar.

Tabelas afetadas (em ordem de deleção):
    AvaliacaoAnexoRSCTae
    RolSaberCompetenciaAnexo
    RolSaberCompetenciaPreenchimento
    RolSaberCompetencia
    GrupoSaberCompetencia
    Requisito (atualizado in-place, não deletado)
    Nivel (atualizado in-place, não deletado — referenciado por ProcessoRSCTae)

Uso:
    python manage.py reload_catalogo                 # pede confirmação interativa
    python manage.py reload_catalogo --force         # sem confirmação
    python manage.py reload_catalogo --dry-run       # apenas mostra o que seria feito
    python manage.py reload_catalogo --skip-requisito  # não recarrega initial_data_requisito
"""

from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import transaction


FIXTURES = [
    'rsc_tae/fixtures/initial_data_requisito.json',
    'rsc_tae/fixtures/initial_data_nivel.json',
    'rsc_tae/fixtures/initial_data_grupo.json',
    'rsc_tae/fixtures/initial_data_saber_competencia.json',
]

DEPENDENT_MODELS = [
    ('rsc_tae', 'AvaliacaoAnexoRSCTae'),
    ('rsc_tae', 'RolSaberCompetenciaAnexo'),
    ('rsc_tae', 'RolSaberCompetenciaPreenchimento'),
    ('rsc_tae', 'RolSaberCompetencia'),
    ('rsc_tae', 'GrupoSaberCompetencia'),
]


class Command(BaseCommand):
    help = 'Recarrega o catálogo RSC-TAE (requisitos, níveis, grupos e itens) a partir das fixtures oficiais.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            help='Executa sem pedir confirmação interativa.',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Apenas exibe o que seria feito, sem alterar o banco.',
        )
        parser.add_argument(
            '--skip-requisito',
            action='store_true',
            help='Não recarrega initial_data_requisito.json (mantém descrições atuais).',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        force = options['force']
        skip_requisito = options['skip_requisito']

        self._print_plan(dry_run, skip_requisito)

        if dry_run:
            self.stdout.write(self.style.WARNING('\n[dry-run] Nenhuma alteração foi realizada.'))
            return

        if not force and not self._confirmar():
            self.stdout.write(self.style.WARNING('Operação cancelada pelo usuário.'))
            return

        with transaction.atomic():
            self._deletar_dependentes()
            self._carregar_fixtures(skip_requisito)

        self.stdout.write(self.style.SUCCESS('\nCatálogo recarregado com sucesso.'))

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _print_plan(self, dry_run, skip_requisito):
        prefix = '[dry-run] ' if dry_run else ''
        self.stdout.write(self.style.MIGRATE_HEADING(f'\n{prefix}Plano de execução — reload_catalogo'))

        self.stdout.write('\n  Passo 1 — Deletar registros dependentes:')
        for app, model_name in DEPENDENT_MODELS:
            count = self._count(app, model_name)
            self.stdout.write(f'    • {model_name}: {count} registro(s)')

        self.stdout.write('\n  Passo 2 — Carregar fixtures:')
        fixtures_a_carregar = FIXTURES if not skip_requisito else FIXTURES[1:]
        for fixture in fixtures_a_carregar:
            self.stdout.write(f'    • {fixture}')
        self.stdout.write('')

    def _confirmar(self):
        self.stdout.write(
            self.style.WARNING(
                'ATENÇÃO: Esta operação apagará permanentemente todos os preenchimentos,\n'
                'anexos e avaliações de itens existentes nos processos.\n'
                'Os processos em si serão mantidos, mas perderão os itens declarados.'
            )
        )
        resposta = input('\nDeseja continuar? [s/N] ').strip().lower()
        return resposta == 's'

    def _count(self, app_label, model_name):
        from django.apps import apps

        try:
            model = apps.get_model(app_label, model_name)
            return model.objects.count()
        except LookupError:
            return 0

    def _deletar_dependentes(self):
        from django.apps import apps

        for app_label, model_name in DEPENDENT_MODELS:
            model = apps.get_model(app_label, model_name)
            count, _ = model.objects.all().delete()
            self.stdout.write(f'  Deletado: {model_name} — {count} registro(s)')

    def _carregar_fixtures(self, skip_requisito):
        fixtures = FIXTURES if not skip_requisito else FIXTURES[1:]
        for fixture in fixtures:
            self.stdout.write(f'  Carregando: {fixture}')
            call_command('loaddata', fixture, verbosity=0)
            self.stdout.write(self.style.SUCCESS(f'    ✓ {fixture}'))
