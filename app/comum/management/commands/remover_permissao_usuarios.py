from django.contrib.auth.models import Group

from djtools.management.commands import BaseCommandPlus
from edu.models import Aluno
from rh.models import Servidor


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        self.remover_chaves_usuario_inativos()
        self.remover_servidores_inativos()

    def remover_chaves_usuario_inativos(self):
        # Remoção de permissão de chaves para servidores removidos/redistribuídos
        servidores = Servidor.objects.filter(situacao__nome_siape='REDISTRIBUIDO', vinculos__chave__isnull=False)
        for servidor in servidores:
            vinculo = servidor.get_vinculo()
            for chave in vinculo.chave_set.all():
                chave.vinculos.remove(vinculo)

        # alunos/bolsistas egressos ou transferidos (sem matrícula ativa)
        alunos = Aluno.objects.filter(situacao__ativo=False, vinculos__chave__isnull=False)
        for aluno in alunos:
            vinculo = aluno.get_vinculo()
            for chave in vinculo.chave_set.all():
                chave.vinculos.remove(vinculo)

    def remover_servidores_inativos(self):
        grupo_avaliador_sala = Group.objects.get(name='Avaliador de Sala')
        servidores_inativos = Servidor.objects.inativos().filter(vinculos__user__groups=grupo_avaliador_sala)
        for servidor in servidores_inativos:
            servidor.get_user().groups.remove(grupo_avaliador_sala)
