from django.core.management import CommandError

from djtools.management.commands import BaseCommandPlus


class Command(BaseCommandPlus):
    """
    Comando desativado: fazia a importação em lote de doses vacinais via saude.management.
    commands.importar_dados_rnmaisvacina (específico de COVID-19). Substituído pelo serviço
    saude.services.importacao_rnvacina, disparado sob demanda por paciente (aba do prontuário
    ou autoatendimento). Não há limite de frequência: repetir a importação é seguro, pois
    doses/reforços já existentes não são duplicados (consolidação por dose/reforço).
    """

    def handle(self, *args, **options):
        raise CommandError('Comando desativado. A importação de vacinas do RN+Vacina agora é feita via saude.services.importacao_rnvacina.')
