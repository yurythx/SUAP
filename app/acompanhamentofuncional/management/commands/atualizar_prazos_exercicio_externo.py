from django.apps import apps

from acompanhamentofuncional.models import ServidorCessao
from djtools.management.commands import BaseCommandPlus

Log = apps.get_model('comum', 'log')


class Command(BaseCommandPlus):
    help = 'Atualizar prazos dos processos de exercício externo'

    def handle(self, *args, **options):
        ServidorCessao.atualiza_prazos()
