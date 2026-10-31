"""Tarefa travada é somente leitura: Concluída, Cancelada, Suspensa ou de projeto Concluído/Cancelado.

Continuam valendo ver, observar, clonar e excluir; a encerrada (Concluída/Cancelada) pode ser
reaberta e a Suspensa pode mudar de situação para ser retomada. Em projeto encerrado, nada muda.
"""

from __future__ import annotations

from datetime import date

import pytest
from django.contrib.auth.models import Group
from django.test import Client
from django.urls import reverse

from gerenciador_projetos.enums import SituacaoProjeto, SituacaoTarefa, TipoRecorrencia
from gerenciador_projetos.models import HistoricoEvolucao, Lista, ListaProjeto, ListaTarefa, RecorrenciaTarefa, Tarefa
from gerenciador_projetos.tests.factories import ProjetoFactory, TarefaFactory
from rh.tests.factories import ServidorFactory

TRAVADAS = {
    'concluida': {'situacao': SituacaoTarefa.CONCLUIDA, 'data_conclusao': date(2026, 1, 10), 'percentual_executado': 100},
    'cancelada': {'situacao': SituacaoTarefa.CANCELADA},
    'suspensa': {'situacao': SituacaoTarefa.SUSPENSA},
    'projeto_encerrado': {'situacao': SituacaoTarefa.EM_ANDAMENTO},
}


@pytest.fixture
def equipe():
    gerente = ServidorFactory().get_user()
    for grupo in ('Gerente de Projeto', 'Membro de Projeto'):
        gerente.groups.add(Group.objects.get(name=grupo))
    projeto = ProjetoFactory(criado_por=gerente)
    projeto.gerentes.add(gerente)
    cliente = Client()
    cliente.force_login(gerente)
    return {'cliente': cliente, 'gerente': gerente, 'projeto': projeto}


def _tarefa(equipe, estado: str) -> Tarefa:
    tarefa = TarefaFactory(projeto=equipe['projeto'], criado_por=equipe['gerente'])
    Tarefa.objects.filter(pk=tarefa.pk).update(**TRAVADAS[estado])
    if estado == 'projeto_encerrado':
        type(equipe['projeto']).objects.filter(pk=equipe['projeto'].pk).update(situacao=SituacaoProjeto.CONCLUIDO)
    tarefa.refresh_from_db()
    return tarefa


@pytest.mark.parametrize('estado', TRAVADAS)
class TestTarefaTravada:
    def test_servidor_recusa_alteracoes(self, equipe, estado):
        tarefa = _tarefa(equipe, estado)
        cliente, projeto = equipe['cliente'], equipe['projeto']
        # Primeiro: as mensagens das recusas seguintes ficariam na sessão e apareceriam nesta página.
        progresso = cliente.post(reverse('alterar_progresso_tarefa', args=[tarefa.pk, 50]), follow=True).content.decode()
        motivo = 'o projeto está encerrado' if estado == 'projeto_encerrado' else f'a tarefa está {tarefa.get_situacao_display()}'
        formularios = {
            'nova subtarefa': reverse('adicionar_tarefa', args=[projeto.pk]) + f'?tarefa_pai={tarefa.pk}',
            'editar': reverse('alterar_tarefa', args=[projeto.pk, tarefa.pk]),
            'registrar evolução': reverse('gerenciar_historicoevolucao', args=[tarefa.pk]),
            'anexo': reverse('adicionar_anexo', args=[tarefa.pk]),
            'recorrência': reverse('recorrencia_tarefa', args=[tarefa.pk]),
            'campus': reverse('atribuir_tarefa_a_campus', args=[tarefa.pk]),
        }
        abertos = [nome for nome, url in formularios.items() if cliente.get(url).status_code == 200]

        cliente.post(reverse('adicionar_comentario_rapido_tarefa', args=[tarefa.pk]), {'comentario': 'na travada'})
        cliente.post(reverse('recorrencia_tarefa', args=[tarefa.pk]), {'tipo_recorrencia': TipoRecorrencia.MENSALMENTE, 'dia_do_mes': 1})
        cliente.post(reverse('atribuir_a_mim', args=[tarefa.pk]))

        assert abertos == [], f'{estado}: formulários abertos {abertos}'
        assert motivo in progresso, f'{estado}: a recusa não diz o motivo real'
        assert not HistoricoEvolucao.objects.filter(tarefa=tarefa, comentario='na travada').exists()
        assert not RecorrenciaTarefa.objects.filter(tarefa=tarefa).exists()
        assert not tarefa.atribuido_a.exists()
        tarefa.refresh_from_db()
        assert tarefa.percentual_executado != 50

    def test_tela_nao_oferece_alteracoes(self, equipe, estado):
        tarefa = _tarefa(equipe, estado)
        lista = Lista.objects.create(nome='Coluna')
        ListaProjeto.objects.create(lista=lista, projeto=equipe['projeto'], posicao=1)
        ListaTarefa.objects.create(lista=lista, tarefa=tarefa, posicao=0, registrado_por=equipe['gerente'])
        Tarefa.objects.filter(pk=tarefa.pk).update(lista=lista)
        cliente = equipe['cliente']

        telas = {
            'tarefa': cliente.get(reverse('tarefa', args=[tarefa.pk])).content.decode(),
            'quadro': cliente.get(reverse('dashboard', args=[equipe['projeto'].pk])).content.decode(),
        }
        proibidos = {
            'nova subtarefa': f'tarefa_pai={tarefa.pk}',
            'editar': reverse('alterar_tarefa', args=[equipe['projeto'].pk, tarefa.pk]) + '"',
            'registrar evolução': reverse('gerenciar_historicoevolucao', args=[tarefa.pk]),
            'progresso': f'/tarefa/{tarefa.pk}/alterar_progresso/',
            'recorrência': reverse('recorrencia_tarefa', args=[tarefa.pk]),
            'campus': reverse('atribuir_tarefa_a_campus', args=[tarefa.pk]),
            'atribuir a mim': reverse('atribuir_a_mim', args=[tarefa.pk]),
        }

        oferecidos = [f'{tela}: {nome}' for tela, html in telas.items() for nome, marca in proibidos.items() if marca in html]
        assert oferecidos == []


class TestSaidasDaTrava:
    def test_suspensa_volta_a_andar_pela_situacao(self, equipe):
        tarefa = _tarefa(equipe, 'suspensa')

        # O navegador sempre manda o token; sem corpo, o form do módulo (`request.POST or None`) fica sem dados.
        equipe['cliente'].post(reverse('alterar_situacao_tarefa', args=[tarefa.pk, SituacaoTarefa.EM_ANDAMENTO]), {'csrfmiddlewaretoken': 'x'})

        tarefa.refresh_from_db()
        assert tarefa.situacao == SituacaoTarefa.EM_ANDAMENTO

    def test_cancelada_pode_ser_reaberta(self, equipe):
        tarefa = _tarefa(equipe, 'cancelada')

        equipe['cliente'].post(reverse('reabrir_tarefa', args=[tarefa.pk]))

        tarefa.refresh_from_db()
        assert tarefa.situacao == SituacaoTarefa.ABERTA

    def test_projeto_encerrado_nao_reabre_nem_exclui(self, equipe):
        tarefa = _tarefa(equipe, 'concluida')
        type(equipe['projeto']).objects.filter(pk=equipe['projeto'].pk).update(situacao=SituacaoProjeto.CANCELADO)

        equipe['cliente'].post(reverse('reabrir_tarefa', args=[tarefa.pk]))
        equipe['cliente'].post(reverse('excluir_tarefa', args=[tarefa.pk]))

        tarefa.refresh_from_db()
        assert tarefa.situacao == SituacaoTarefa.CONCLUIDA

    def test_concluida_ainda_pode_ser_excluida(self, equipe):
        tarefa = _tarefa(equipe, 'concluida')

        equipe['cliente'].post(reverse('excluir_tarefa', args=[tarefa.pk]))

        assert not Tarefa.objects.filter(pk=tarefa.pk).exists()
