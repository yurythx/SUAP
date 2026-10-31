""" """

from djtools.management.commands import BaseCommandPlus
from edu.q_academico import DAO


class Command(BaseCommandPlus):
    def add_arguments(self, parser):
        parser.add_argument('args', nargs='*', type=str)

    def handle(self, *args, **options):
        dao = DAO()
        # dao.importar_livros()
        dao.importar_registros_diploma()
