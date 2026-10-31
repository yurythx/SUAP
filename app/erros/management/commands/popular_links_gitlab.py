"""
Atualiza a situação das issues no gitlab e sentry e os erros do suap.
"""

import tqdm

from comum.utils import ferramentas_configuradas
from djtools.management.commands import BaseCommandPlus
from erros.models import Erro
from erros.utils import popular_links_gitlab


class Command(BaseCommandPlus):
    def add_arguments(self, parser):
        parser.add_argument('pks', nargs='*', type=int)

    def handle(self, *args, **options):
        verbosity = options.get('verbosity', 3)
        pks = options.get('pks')
        conf = ferramentas_configuradas()
        if not conf:
            self.stderr.write('Sentry ou Gitlab não configurados em /comum/configuracao')
            return

        qs = Erro.objects.exclude(situacao__in=Erro.SITUACOES_FINAIS)
        if pks:
            qs = qs.filter(pk__in=pks)
        if verbosity:
            qs = tqdm.tqdm(qs)

        for erro in qs:
            popular_links_gitlab(erro, conf)
