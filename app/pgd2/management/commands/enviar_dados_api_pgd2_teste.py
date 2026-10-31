import logging

from djtools.management.commands import BaseCommandPlus

logger = logging.getLogger(__name__)


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        from pgd2.api_pgd2_v2 import get_api_pgd2_v2

        api_pgd = get_api_pgd2_v2()
        if not api_pgd:
            logger.warning('API PGD2 não está ativa. Encerrando.')
            return
        api_pgd.resetar_envio_dados_exceto_log()
        api_pgd.enviar_dados_api(self_command=self)
