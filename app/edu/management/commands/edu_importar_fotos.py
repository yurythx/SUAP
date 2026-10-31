from djtools.management.commands import BaseCommandPlus


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        from edu.q_academico_fotos import DAO

        dao = DAO()
        print(dao.atualizar_fotos(verbose=1))
