from django.apps import apps
from django.db import transaction
from tqdm import tqdm

from comum.models import Configuracao, Vinculo
from djtools.management.commands import BaseCommandPlus


class Command(BaseCommandPlus):
    @transaction.atomic
    def handle(self, *args, **options):
        User = apps.get_model('comum', 'User')
        Servidor = apps.get_model('rh', 'Servidor')
        Aluno = apps.get_model('edu', 'Aluno')

        # email_notificacao virou property derivada (institucional do papel, senão email_pessoal):
        # o institucional já é a 1ª escolha da property — não há mais o que zerar/backfillar.
        # Aqui só populamos email_pessoal (quando vazio) com um e-mail NÃO institucional (SIAPE/qacadêmico).

        # Servidores: e-mail SIAPE não-institucional vira email_pessoal (se vazio). User.email = institucional.
        for servidor_id, matricula, email_institucional, email_siape in tqdm(
            Servidor.objects.values_list('id', 'matricula', 'email_institucional', 'email_siape'),
            desc='Atualizando e-mail dos servidores',
        ):
            if email_siape and not Configuracao.eh_email_institucional(email_siape):
                Vinculo.objects.filter(tipo_relacionamento__model='servidor', id_relacionamento=servidor_id, email_pessoal='').update(
                    email_pessoal=email_siape
                )
            # Guarda ao contrário do importador (que ignora vazio): aqui o vazio precisa propagar, pois é
            # assim que um e-mail institucional removido é limpo. O que se barra é o valor de domínio
            # de terceiros (servidor cedido), que sobrescreveria o e-mail de notificação com o do órgão de origem.
            if not email_institucional or Configuracao.email_institucional_permitido(email_institucional):
                User.objects.filter(username=matricula).update(email=email_institucional)

        # Alunos: e-mail do Q-Acadêmico não-institucional vira email_pessoal (se vazio). User.email = acadêmico.
        for aluno_id, matricula, email_academico, email_qacademico in tqdm(
            Aluno.objects.filter(situacao__ativo=True).values_list('id', 'matricula', 'email_academico', 'email_qacademico'),
            desc='Atualizando emails dos alunos',
        ):
            if email_qacademico and not Configuracao.eh_email_institucional(email_qacademico):
                Vinculo.objects.filter(tipo_relacionamento__model='aluno', id_relacionamento=aluno_id, email_pessoal='').update(
                    email_pessoal=email_qacademico
                )
            if email_academico:
                User.objects.filter(username=matricula).update(email=email_academico)
