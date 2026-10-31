from django.core.management import CommandError

from djtools.management.commands import BaseCommandPlus


class Command(BaseCommandPlus):
    """
    Comando desativado: reprocessava passaportes vacinais COVID pendentes chamando
    saude.management.commands.importar_dados_rnmaisvacina. Removido do agendamento do beat
    (saude/beat.py e edu/beat.py); substituído pelo serviço saude.services.importacao_rnvacina.
    """

    def handle(self, *args, **options):
        raise CommandError('Comando desativado. A importação de vacinas do RN+Vacina agora é feita via saude.services.importacao_rnvacina.')
