"""
Comando que extrai os curriculos lattes
"""

from django.core.cache import cache

from clipping import rss
from djtools.management.commands import BaseCommandPlus


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        verbosity = options.get('verbosity', 3)
        count = rss.importar_tudo(verbosity)
        cache.delete('_cache_quadro_clipping')
        if verbosity:
            print(f'{count} importadas')
