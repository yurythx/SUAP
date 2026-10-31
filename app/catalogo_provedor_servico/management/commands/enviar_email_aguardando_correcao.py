import tqdm
from django.conf import settings
from sentry_sdk import capture_exception

from catalogo_provedor_servico.models import Solicitacao
from catalogo_provedor_servico.utils import Notificar
from djtools.management.commands import BaseCommandPlus


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        verbosity = int(options['verbosity']) > 1

        solitacoes_aguardando_correcao = Solicitacao.objects.filter(status=Solicitacao.STATUS_AGUARDANDO_CORRECAO_DE_DADOS)
        for solicitacao in tqdm.tqdm(solitacoes_aguardando_correcao):
            try:
                service_provider = solicitacao.servico.get_service_provider()
                dados_email = service_provider.get_dados_email(solicitacao=solicitacao)
                if service_provider.get_avaliacao_disponibilidade(solicitacao.cpf, verbosity).is_ok:
                    Notificar.solicitacao_correcao_de_dados(solicitacao, dados_email)
            except Exception as e:
                if settings.DEBUG:
                    raise e
                capture_exception(e)
