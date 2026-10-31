import sys

import tqdm
from django.core.management import BaseCommand

from catalogo_provedor_servico.models import Servico, Solicitacao
from catalogo_provedor_servico.providers.base import Etapa


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument('servico', action='store', help='Id do serviço junto ao GOV.BR.', type=int)

    def handle(self, *args, **options):
        servico = Servico.objects.filter(id_servico_portal_govbr=options['servico'])

        if not servico.exists():
            self.stdout.write(self.style.ERROR('Deve-se indicar um serviço existente.'))
            sys.exit(1)

        servico = servico.first()

        self.stdout.write(self.style.SUCCESS('Solicitações com status definifivo serão ignorados no processamento.'))

        for solicitacao in tqdm.tqdm(Solicitacao.objects.filter(servico=servico)):
            solicitacao.extra_dados = ''
            for solicitacao_etapa in solicitacao.solicitacaoetapa_set.all():
                etapa = Etapa.load_from_json(solicitacao_etapa.get_dados_as_json())
                # atualiza_extra_campo(
                #     servico=servico,
                #     solicitacao=solicitacao,
                #     etapa=etapa,
                #     salvar=False
                # )
                solicitacao.atualizar_extra_campo(etapa=etapa)
            Solicitacao.objects.filter(pk=solicitacao.pk).update(extra_dados=solicitacao.extra_dados)
