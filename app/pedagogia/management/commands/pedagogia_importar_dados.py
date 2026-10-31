from django.core.management.base import BaseCommand

from pedagogia.q_academico import DAO


class Command(BaseCommand):
    def handle(self, *args, **options):
        dao = DAO()
        dao.importar_matrizes()
