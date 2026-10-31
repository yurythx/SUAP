import tqdm
from django.core.management.base import BaseCommand

from catalogo_provedor_servico.models import RegistroAcompanhamentoGovBR
from comum.models import APIExterna

# Exemplo de chamada:
# python manage.py atualizar_avaliacao_govbr


class Command(BaseCommand):
    def handle(self, *args, **options):
        api = APIExterna.AVALIACAO_GOVBR
        if not api.ativo:
            self.stdout.write('API de Avaliação GOV.BR está inativa. Ative-a para atualizar as avaliações.')
            return

        service = api.get_service()
        solicitacoes_pendentes_de_avaliacao = RegistroAcompanhamentoGovBR.objects.filter(
            tipo=RegistroAcompanhamentoGovBR.TIPO_CONCLUSAO, avaliado=False, tentativas_envio__lt=3
        )
        for registro in tqdm.tqdm(solicitacoes_pendentes_de_avaliacao):
            service.atualizar_registro_avaliacao(registro, verbosity=True)
