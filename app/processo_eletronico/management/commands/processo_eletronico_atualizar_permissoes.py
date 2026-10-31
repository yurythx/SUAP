from django.apps import apps
from django.db import transaction

from djtools.management.commands import BaseCommandPlus


class Command(BaseCommandPlus):
    @transaction.atomic()
    def handle(self, *args, **options):
        # Atualiza as permissoes do processo eletronico retirando os servidores excluidos

        Servidor = apps.get_model('rh', 'Servidor')

        CompartilhamentoProcessoEletronicoSetorPessoa = apps.get_model('processo_eletronico', 'CompartilhamentoProcessoEletronicoSetorPessoa')
        CompartilhamentoProcessoEletronicoPoderDeChefe = apps.get_model('processo_eletronico', 'CompartilhamentoProcessoEletronicoPoderDeChefe')

        CompartilhamentoSetorPessoa = apps.get_model('documento_eletronico', 'CompartilhamentoSetorPessoa')

        servidores_excluidos = Servidor.objects.filter(ativo=False).values_list('vinculos', flat=True)

        # exclui permissoes do servidor excluido dos processos eletronicos
        CompartilhamentoProcessoEletronicoSetorPessoa.objects.filter(vinculo_permitido__in=servidores_excluidos).delete()
        CompartilhamentoProcessoEletronicoPoderDeChefe.objects.filter(vinculo_permitido__in=servidores_excluidos).delete()

        # exclui permissoes do servidor excluido dos documentos eletronicos
        vinculos_excluidos = servidores_excluidos.values_list('vinculos', flat=True)
        CompartilhamentoSetorPessoa.objects.filter(vinculo_permitido__in=vinculos_excluidos).delete()
