import json

import tqdm
from django.core.management import BaseCommand

from catalogo_provedor_servico.models import Solicitacao, SolicitacaoEtapa


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument('servico', action='store', help='Id do servico no GovBR', type=int)
        parser.add_argument('form_num', action='store', help='Número do formulário', type=int)
        parser.add_argument('mudancas', action='store', help='Mudanças a serem realizadas', type=str)

    def handle(self, *args, **options):
        servico = options['servico']
        form_num = options['form_num']
        mudanca = json.loads(options['mudancas'])
        solicitacoes = Solicitacao.objects.filter(servico__id_servico_portal_govbr=servico).exclude(status__in=Solicitacao.STATUS_DEFINITIVOS)
        for etapa in tqdm.tqdm(SolicitacaoEtapa.objects.filter(solicitacao__in=solicitacoes, numero_etapa=form_num)):
            formulario = []
            dados = etapa.get_dados_as_json()
            for field in dados['formulario']:
                if field['name'] == mudanca['field']:
                    for att, value in mudanca['changes']:
                        field[att] = value
                formulario.append(field)
            dados['formulario'] = formulario
            etapa.dados = json.dumps(dados)
            etapa.save()
