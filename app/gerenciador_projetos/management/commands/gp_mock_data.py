"""
Comando útil para preparar um ambiente inicial
python manage.py gp_mock_data
"""

import datetime
import random
from datetime import timedelta

import lorem

from comum.models import AreaAtuacao, User
from comum.utils import get_sigla_reitoria
from djtools.management.commands import BaseCommandPlus
from gerenciador_projetos.enums import PrioridadeTarefa
from gerenciador_projetos.models import Lista, Projeto, Tarefa, TipoAtividade
from rh.models import UnidadeOrganizacional


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        gerente = User.objects.get(username='2106812')
        tipo_atividade, _created = TipoAtividade.objects.get_or_create(
            nome='Planejamento'
        )  # Início, Planejamento, Execução, Monitoramento e Controle, Encerramento
        hoje = datetime.date.today()

        membros = User.objects.filter(username__in=('1543163', '2101623', '1979677', '2107029'))

        projeto = Projeto()
        projeto.titulo = lorem.sentence()
        projeto.descricao = lorem.paragraph()
        projeto.uo = UnidadeOrganizacional.objects.suap().get(sigla=get_sigla_reitoria())
        projeto.criado_por = gerente
        projeto.save()

        projeto.interessados = User.objects.filter(username__in=('1577655', '277119'))
        projeto.membros = membros
        projeto.areas = AreaAtuacao.objects.all()
        projeto.gerentes.add(gerente)

        Lista.objects.get_or_create(nome='A FAZER')
        Lista.objects.get_or_create(nome='FAZENDO')
        Lista.objects.get_or_create(nome='FEITO')

        for i in range(1, 21):
            self.stdout.write(f'Criando {i}a tarefa')
            tarefa = Tarefa()
            tarefa.projeto = projeto
            tarefa.titulo = lorem.sentence()
            tarefa.descricao = lorem.paragraph()
            tarefa.tipo_atividade = tipo_atividade
            tarefa.criado_por = gerente
            tarefa.prioridade = random.choice(list(PrioridadeTarefa.choices))[0]
            tarefa.atribuido_a.set([membros[random.randint(0, 3)]])
            tarefa.atribuido_por = membros[random.randint(0, 3)]
            inicio = hoje + timedelta(days=random.randint(0, 10))
            tarefa.data_inicio = inicio
            tarefa.data_conclusao_estimada = inicio + timedelta(days=random.randint(0, 15))
            tarefa.save()
        self.stdout.write('Execução finalizada.')
