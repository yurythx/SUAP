import datetime

import tqdm

from comum.models import PrestadorServico, Vinculo
from djtools.management.commands import BaseCommandPlus


class Command(BaseCommandPlus):
    help = 'Atualiza o setor do prestador de serviço ou torna usuário externo se ele tem ocupacao ativa ou não'

    def handle(self, *args, **options):
        verbosity = options.get('verbosity', 3)
        qs = PrestadorServico.objects.filter(ocupacaoprestador__data_fim__gte=datetime.datetime.today()).distinct()
        if verbosity:
            qs = tqdm.tqdm(qs)
        prestadores_ativos = 0
        for prestador in qs:
            prestadores_ativos += 1
            prestador.save()
        prestadores_inativos = (
            PrestadorServico.objects.exclude(ocupacaoprestador__data_fim__gte=datetime.datetime.today())
            .filter(usuario_externo=False)
            .update(usuario_externo=True)
        )
        prestadores_setor_invalidos = (
            PrestadorServico.objects.exclude(ocupacaoprestador__data_fim__gte=datetime.datetime.today()).exclude(setor=None).update(setor=None)
        )
        Vinculo.objects.filter(
            id_relacionamento__in=PrestadorServico.objects.filter(setor__isnull=True), tipo_relacionamento__model='prestadorservico'
        ).update(setor=None)
        self.stdout.write(f'{prestadores_ativos} prestadores com ocupação foram atualizados.')
        self.stdout.write(f'{prestadores_inativos} prestadores sem ocupação ativa foram transformados em usuários externos.')
        self.stdout.write(f'{prestadores_setor_invalidos} prestadores sem ocupação ativa tiveram seus setores removidos.')
