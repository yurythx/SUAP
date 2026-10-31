import json

import tqdm
from django.core.management.base import BaseCommand

from catalogo_provedor_servico.models import Solicitacao, SolicitacaoEtapa


class Command(BaseCommand):
    def handle(self, *args, **options):
        etapas = SolicitacaoEtapa.objects.exclude(solicitacao__status__in=Solicitacao.STATUS_DEFINITIVOS)

        print('Migrando os atributos govbr_user_info  para balcaodigital_user_info...')
        for solicitacao_etapa in tqdm.tqdm(etapas):
            campos = solicitacao_etapa.get_dados_as_json()
            for i, field in enumerate(campos['formulario']):
                if 'govbr_user_info' in field:
                    novo_valor_govbr_attr = field['govbr_user_info']
                    if novo_valor_govbr_attr:
                        novo_valor_govbr_attr = 'GOVBR_{}'.format(field['govbr_user_info'])
                    campos['formulario'][i]['balcaodigital_user_info'] = novo_valor_govbr_attr
                    field.pop('govbr_user_info', None)
            solicitacao_etapa.dados = json.dumps(campos)
            solicitacao_etapa.save()
        print('FIM')
