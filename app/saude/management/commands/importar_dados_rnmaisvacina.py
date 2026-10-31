"""
Comando desativado: importava os dados de vacinação do usuário diretamente do RN+Vacina, mas só
para a vacina COVID-19. Substituído por saude.services.importacao_rnvacina, que consulta o
RN+Vacina via o cadastro centralizado de APIs externas (comum.models.APIExterna) e trata COVID-19
como qualquer outra vacina do catálogo.
"""

from django.core.management import CommandError

from djtools.management.commands import BaseCommandPlus


class Command(BaseCommandPlus):
    help = 'Comando desativado. Ver saude.services.importacao_rnvacina.'

    def handle(self, *args, **options):
        raise CommandError(
            'Comando desativado. A importação de vacinas do RN+Vacina agora é feita via saude.services.importacao_rnvacina, '
            'que trata COVID-19 como qualquer outra vacina.'
        )
