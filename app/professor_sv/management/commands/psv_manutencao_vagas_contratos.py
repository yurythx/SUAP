from djtools.management.commands import BaseCommandPlus


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        from professor_sv.models import Vaga, Contrato

        Vaga.atualizar_historico_movimentacao_vagas()
        Contrato.concluir_contratos_expirados()
