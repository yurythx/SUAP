"""
Comando para preencher os responsáveis pela anuência da chefia
"""

import datetime

import tqdm

from djtools.management.commands import BaseCommandPlus
from projetos.models import Participacao, Projeto


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        for projeto in tqdm.tqdm(Projeto.objects.filter(edital__inicio_inscricoes__year=2022)):
            p = Participacao.objects.get(projeto=projeto, responsavel=True)
            if p.exige_anuencia() and not p.responsavel_anuencia:
                servidor = p.vinculo_pessoa.relacionamento
                chefes = servidor.chefes_na_data(datetime.datetime.now().date())
                if chefes:
                    p.responsavel_anuencia = chefes[0].servidor
                    p.save()
