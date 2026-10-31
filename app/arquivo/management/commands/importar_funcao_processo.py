import os

from django.conf import settings
from django.db import transaction

from arquivo.models import Funcao, Processo
from djtools.management.commands import BaseCommandPlus


class Command(BaseCommandPlus):
    @transaction.atomic
    def handle(self, *args, **options):
        self.stdout.write('Importando Função e Processo ...')
        arquivo = os.path.join(settings.BASE_DIR, 'arquivo/static/arquivo/funcoes_processos.txt')
        funcoes_criadas = 0
        processos_criados = 0

        with open(arquivo) as txt_file:
            for linha in txt_file:
                processo_descricao, _, funcao_descricao = linha.partition(':')
                processo_descricao = processo_descricao.strip()
                funcao_descricao = funcao_descricao.strip()
                if not processo_descricao or not funcao_descricao:
                    continue
                funcao, fc = Funcao.objects.get_or_create(descricao=funcao_descricao)
                processo, pc = Processo.objects.get_or_create(descricao=processo_descricao)
                if processo.funcao_id != funcao.pk:
                    processo.funcao = funcao
                    processo.save()
                funcoes_criadas += int(fc)
                processos_criados += int(pc)

        self.stdout.write(f'{funcoes_criadas} Funções criadas. {processos_criados} Processos criados.')
