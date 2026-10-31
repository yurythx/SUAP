import json

import tqdm
from django.core.management.base import BaseCommand

from catalogo_provedor_servico.models import Solicitacao, SolicitacaoEtapa


class Command(BaseCommand):
    def handle(self, *args, **options):
        etapas = SolicitacaoEtapa.objects.exclude(solicitacao__status__in=Solicitacao.STATUS_DEFINITIVOS)

        print('Migrando os choices_function e autocomplete_id para choices_resource_id...')
        for solicitacao_etapa in tqdm.tqdm(etapas):
            campos = solicitacao_etapa.get_dados_as_json()
            for i, field in enumerate(campos['formulario']):
                if 'choices_function' in field:
                    function = field['choices_function']
                    campos['formulario'][i]['choices_resource_id'] = function
            solicitacao_etapa.dados = json.dumps(campos)
            solicitacao_etapa.save()
        print('FIM')
