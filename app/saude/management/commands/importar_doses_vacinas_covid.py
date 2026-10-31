import json

import tqdm

from comum.models import Vinculo
from djtools.management.commands import BaseCommandPlus
from saude.models import CartaoVacinal, Prontuario, Vacina


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        with open('saude/fixtures/cartaovacinal.json') as data_file:
            data = json.load(data_file)
            vacina_covid = Vacina.objects.get(eh_covid=True)
            for v in tqdm.tqdm(data):
                vinculo = Vinculo.objects.get(id=v['fields']['vinculo'])
                prontuario = Prontuario.get_prontuario(vinculo)
                CartaoVacinal.objects.get_or_create(
                    prontuario=prontuario,
                    data_prevista=v['fields']['data_prevista'],
                    vacina=vacina_covid,
                    numero_dose=v['fields']['numero_dose'],
                    obs='Importado do RN+Vacina',
                    data_vacinacao=v['fields']['data_vacinacao'],
                )
