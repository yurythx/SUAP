# -------------------------------------
# Sincronizar Permissões comissão
# -------------------------------------

from djtools.management.commands import BaseCommandPlus


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        from pgd2.models import ComissaoPGD

        ComissaoPGD.sincronizar_permissoes_comissao()
