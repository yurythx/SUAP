from argparse import ArgumentParser

from django.core.management.base import BaseCommand
from django.db.models import QuerySet

from eventos.models import Evento


class Command(BaseCommand):
    help = 'Lista eventos com as configurações mínimas para submissão de trabalhos, começando pelos mais recentes.'

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument(
            '--com-avaliacoes-pendentes',
            action='store_true',
            help='Exibe somente eventos que possuem pelo menos uma avaliação vinculada e ainda sem nota.',
        )

    def handle(self, *args: object, **options: object) -> None:
        eventos = self._obter_eventos(bool(options['com_avaliacoes_pendentes']))
        encontrou_evento = False

        for evento in eventos.iterator():
            if not evento.atingiu_configuracoes_minimas_para_submissao_trabalhos():
                continue

            encontrou_evento = True
            self.stdout.write(self.style.SUCCESS(f'Evento encontrado: ID={evento.id} | {evento.nome}'))
            if not self._deseja_continuar():
                return

        if not encontrou_evento:
            self.stdout.write(self.style.WARNING('Nenhum evento correspondente foi encontrado.'))
        else:
            self.stdout.write('Não há outros eventos correspondentes.')

    def _obter_eventos(self, somente_com_avaliacoes_pendentes: bool) -> QuerySet[Evento]:
        eventos = Evento.objects.order_by('-id')
        if somente_com_avaliacoes_pendentes:
            eventos = eventos.filter(
                modalidade__submissao__versoes__pareceres__isnull=False,
                modalidade__submissao__versoes__pareceres__nota__isnull=True,
            ).distinct()
        return eventos

    def _deseja_continuar(self) -> bool:
        resposta = input('Continuar buscando outro? [s/N]: ').strip().lower()
        return resposta in ('s', 'sim')
