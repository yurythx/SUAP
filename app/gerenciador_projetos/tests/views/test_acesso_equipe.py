"""Ações que alteram tarefa ou projeto exigem ser da equipe do projeto, e não só a permissão do grupo.

A permissão de modelo (`change_tarefa`, `change_historicoevolucao`, `change_projeto`) vem dos grupos
*Gerente de Projeto* e *Membro de Projeto*: quem é gerente de um projeto qualquer tem. Cada teste
coloca esse usuário diante de um projeto privado do qual ele não participa, chama a URL
diretamente e confere no banco que nada foi gravado.
"""

from __future__ import annotations

from datetime import date

import pytest
from django.contrib.auth.models import Group
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.urls import reverse

from comum.models import User
from gerenciador_projetos.enums import SituacaoTarefa, TipoRecorrencia
from gerenciador_projetos.models import HistoricoEvolucao, Lista, ListaProjeto, ListaTarefa, Projeto, RecorrenciaTarefa, Tarefa
from gerenciador_projetos.tests.factories import ProjetoFactory, TarefaFactory
from rh.tests.factories import ServidorFactory


def _servidor(*grupos: str) -> User:
    usuario = ServidorFactory().get_user()
    for nome in grupos:
        usuario.groups.add(Group.objects.get(name=nome))
    return usuario


@pytest.fixture
def cenario():
    """Projeto privado da vítima + intruso logado (gerente de outro projeto)."""
    dono = _servidor('Gerente de Projeto')
    vitima = ProjetoFactory(criado_por=dono, titulo='Projeto privado com dados sensíveis')
    vitima.gerentes.add(dono)
    tarefa = TarefaFactory(projeto=vitima, criado_por=dono, titulo='Senha do servidor X')

    intruso = _servidor('Gerente de Projeto', 'Membro de Projeto')
    proprio = ProjetoFactory(criado_por=intruso)
    proprio.gerentes.add(intruso)

    assert not vitima.pode_ver_projeto(intruso), 'premissa: o intruso não deveria ver o projeto vítima'
    cliente = Client()
    cliente.force_login(intruso)
    return {'cliente': cliente, 'intruso': intruso, 'dono': dono, 'projeto': vitima, 'tarefa': tarefa}


def _vulneravel(acao: str, url: str, efeito: str) -> str:
    return f'{acao} sem ser da equipe — {url} — {efeito}'


class TestAcessoEquipe:
    def test_registrar_evolucao(self, cenario):
        tarefa = cenario['tarefa']
        url = reverse('gerenciar_historicoevolucao', args=[tarefa.pk])

        cenario['cliente'].post(url, {'comentario': 'alterado por intruso', 'percentual_executado': 50})

        gravou = HistoricoEvolucao.objects.filter(tarefa=tarefa, comentario='alterado por intruso').exists()
        assert not gravou, _vulneravel('registrar evolução', url, 'evolução e percentual gravados na tarefa alheia')

    def test_comentario_rapido(self, cenario):
        tarefa = cenario['tarefa']
        url = reverse('adicionar_comentario_rapido_tarefa', args=[tarefa.pk])

        cenario['cliente'].post(url, {'comentario': 'comentário de intruso'})

        gravou = HistoricoEvolucao.objects.filter(tarefa=tarefa, comentario='comentário de intruso').exists()
        assert not gravou, _vulneravel('comentar', url, 'comentário gravado na tarefa alheia')

    def test_adicionar_anexo(self, cenario):
        tarefa = cenario['tarefa']
        url = reverse('adicionar_anexo', args=[tarefa.pk])
        pdf = SimpleUploadedFile('intruso.pdf', b'%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n', content_type='application/pdf')

        cenario['cliente'].post(url, {'comentario': 'anexo de intruso', 'anexo': pdf})

        gravou = HistoricoEvolucao.objects.filter(tarefa=tarefa, comentario='anexo de intruso').exists()
        assert not gravou, _vulneravel('anexar arquivo', url, 'arquivo anexado na tarefa alheia')

    def test_recorrencia(self, cenario):
        tarefa = cenario['tarefa']
        url = reverse('recorrencia_tarefa', args=[tarefa.pk])

        cenario['cliente'].post(url, {'tipo_recorrencia': TipoRecorrencia.MENSALMENTE, 'dia_do_mes': 1})

        assert not RecorrenciaTarefa.objects.filter(tarefa=tarefa).exists(), _vulneravel('criar recorrência', url, 'tarefa alheia passa a se repetir')

    def test_remover_recorrencia(self, cenario):
        recorrencia = RecorrenciaTarefa.objects.create(tarefa=cenario['tarefa'], tipo_recorrencia=TipoRecorrencia.SEMANALMENTE, dia_da_semana=1)
        url = reverse('remover_recorrencia_tarefa', args=[recorrencia.pk])

        cenario['cliente'].post(url)

        assert RecorrenciaTarefa.objects.filter(pk=recorrencia.pk).exists(), _vulneravel(
            'remover recorrência', url, 'recorrência da tarefa alheia apagada'
        )

    def test_reabrir_tarefa(self, cenario):
        tarefa = cenario['tarefa']
        Tarefa.objects.filter(pk=tarefa.pk).update(situacao=SituacaoTarefa.CONCLUIDA, percentual_executado=100, data_conclusao=date.today())
        url = reverse('reabrir_tarefa', args=[tarefa.pk])

        cenario['cliente'].post(url)

        tarefa.refresh_from_db()
        assert tarefa.situacao == SituacaoTarefa.CONCLUIDA, _vulneravel('reabrir tarefa ', url, 'tarefa alheia concluída foi reaberta')

    def test_mudar_lista(self, cenario):
        tarefa, projeto = cenario['tarefa'], cenario['projeto']
        lista = Lista.objects.create(nome='Fazendo', criada_por=cenario['dono'])
        ListaProjeto.objects.create(lista=lista, projeto=projeto, posicao=1)
        url = reverse('mudarlista', args=[tarefa.pk, lista.pk, 2])

        cenario['cliente'].post(url)

        moveu = ListaTarefa.objects.filter(tarefa=tarefa, registrado_por=cenario['intruso']).exists()
        assert not moveu, _vulneravel('mover tarefa de lista', url, 'tarefa alheia mudou de coluna no quadro')

    def test_atribuir_a_mim(self, cenario):
        tarefa = cenario['tarefa']
        url = reverse('atribuir_a_mim', args=[tarefa.pk])

        cenario['cliente'].post(url)

        assert not tarefa.atribuido_a.filter(pk=cenario['intruso'].pk).exists(), _vulneravel(
            'atribuir a mim ', url, 'intruso vira responsável pela tarefa alheia (e recebe as notificações dela)'
        )

    def test_clonar_tarefa(self, cenario):
        tarefa = cenario['tarefa']
        url = reverse('clonar_tarefa', args=[tarefa.pk])
        antes = Tarefa.objects.filter(projeto=cenario['projeto']).count()

        cenario['cliente'].post(url)

        assert Tarefa.objects.filter(projeto=cenario['projeto']).count() == antes, _vulneravel(
            'clonar tarefa ', url, 'cópia criada dentro do projeto alheio'
        )

    def test_clonar_projeto(self, cenario):
        projeto = cenario['projeto']
        url = reverse('clonar_projeto', args=[projeto.pk])

        cenario['cliente'].post(url)

        copia = Projeto.objects.filter(gerentes=cenario['intruso'], titulo=f'Cópia de {projeto.titulo}').first()
        detalhe = ''
        if copia:
            tarefas = list(Tarefa.objects.filter(projeto=copia).values_list('titulo', flat=True))
            detalhe = f'; o intruso vira gerente da cópia e lê as tarefas: {tarefas}'
        assert copia is None, _vulneravel('clonar projeto ', url, 'projeto privado inteiro copiado para o intruso' + detalhe)

    def test_posicao_da_lista(self, cenario):
        projeto = cenario['projeto']
        a = ListaProjeto.objects.create(lista=Lista.objects.create(nome='A'), projeto=projeto, posicao=1)
        b = ListaProjeto.objects.create(lista=Lista.objects.create(nome='B'), projeto=projeto, posicao=2)
        url = reverse('atualizar_posicao_lista_projeto', args=[b.pk])

        cenario['cliente'].post(url, {'posicao': 1})

        a.refresh_from_db()
        b.refresh_from_db()
        assert (a.posicao, b.posicao) == (1, 2), _vulneravel('reordenar listas do projeto', url, 'colunas do quadro alheio reordenadas')

    def test_editar_tarefa_alheia_pela_url_do_proprio_projeto(self, cenario):
        """A permissão é conferida no projeto da URL; a tarefa precisa ser desse projeto."""
        tarefa = cenario['tarefa']
        proprio = Projeto.objects.get(gerentes=cenario['intruso'])
        url = reverse('alterar_tarefa', args=[proprio.pk, tarefa.pk])

        formulario = cenario['cliente'].get(url)
        cenario['cliente'].post(url, {'titulo': 'renomeada por intruso', 'descricao': 'x', 'prioridade': 2})

        tarefa.refresh_from_db()
        assert formulario.status_code == 404, _vulneravel('abrir edição de tarefa alheia', url, 'formulário mostra a tarefa do projeto privado')
        assert tarefa.titulo == 'Senha do servidor X', _vulneravel('editar tarefa alheia', url, 'título da tarefa alheia alterado')

    def test_controle_alterar_situacao(self, cenario):
        """Controle: ação que já verificava a equipe antes desta correção (o cenário é justo)."""
        tarefa = cenario['tarefa']
        url = reverse('alterar_situacao_tarefa', args=[tarefa.pk, SituacaoTarefa.EM_ANDAMENTO])

        cenario['cliente'].post(url)

        tarefa.refresh_from_db()
        assert tarefa.situacao == SituacaoTarefa.ABERTA, 'o controle deveria estar protegido'


class TestAcoesExigemPost:
    """Alterar dados por GET deixa um link externo agir em nome de quem está logado (CSRF)."""

    @pytest.fixture
    def gerente(self):
        dono = _servidor('Gerente de Projeto', 'Membro de Projeto')
        projeto = ProjetoFactory(criado_por=dono)
        projeto.gerentes.add(dono)
        tarefa = TarefaFactory(projeto=projeto, criado_por=dono)
        cliente = Client()
        cliente.force_login(dono)
        return {'cliente': cliente, 'dono': dono, 'projeto': projeto, 'tarefa': tarefa}

    def test_get_nao_altera_nada(self, gerente):
        cliente, projeto, tarefa = gerente['cliente'], gerente['projeto'], gerente['tarefa']
        Tarefa.objects.filter(pk=tarefa.pk).update(situacao=SituacaoTarefa.CONCLUIDA, percentual_executado=100, data_conclusao=date.today())
        lista = Lista.objects.create(nome='Fazendo')
        ListaProjeto.objects.create(lista=lista, projeto=projeto, posicao=1)
        tarefas_antes, projetos_antes = Tarefa.objects.count(), Projeto.objects.count()

        cliente.get(reverse('reabrir_tarefa', args=[tarefa.pk]))
        cliente.get(reverse('clonar_tarefa', args=[tarefa.pk]))
        cliente.get(reverse('clonar_projeto', args=[projeto.pk]))
        cliente.get(reverse('atribuir_a_mim', args=[tarefa.pk]))
        cliente.get(reverse('mudarlista', args=[tarefa.pk, lista.pk, 2]))
        cliente.get(reverse('excluir_tarefa', args=[tarefa.pk]))

        assert Tarefa.objects.filter(pk=tarefa.pk).exists(), 'GET excluiu a tarefa'
        tarefa.refresh_from_db()
        assert tarefa.situacao == SituacaoTarefa.CONCLUIDA
        assert (Tarefa.objects.count(), Projeto.objects.count()) == (tarefas_antes, projetos_antes)
        assert not tarefa.atribuido_a.exists()
        assert not ListaTarefa.objects.filter(tarefa=tarefa).exists()

    def test_equipe_continua_fazendo_por_post(self, gerente):
        cliente, projeto, tarefa = gerente['cliente'], gerente['projeto'], gerente['tarefa']
        lista = Lista.objects.create(nome='Fazendo')
        ListaProjeto.objects.create(lista=lista, projeto=projeto, posicao=1)

        cliente.post(reverse('atribuir_a_mim', args=[tarefa.pk]))
        cliente.post(reverse('mudarlista', args=[tarefa.pk, lista.pk, 2]))
        cliente.post(reverse('clonar_projeto', args=[projeto.pk]))

        assert tarefa.atribuido_a.filter(pk=gerente['dono'].pk).exists()
        assert ListaTarefa.objects.filter(tarefa=tarefa, lista=lista).exists()
        assert Projeto.objects.filter(titulo=f'Cópia de {projeto.titulo}', gerentes=gerente['dono']).exists()

    def test_mudarlista_recusa_lista_de_outro_projeto(self, gerente):
        cliente, tarefa = gerente['cliente'], gerente['tarefa']
        alheia = Lista.objects.create(nome='Lista de outro projeto')
        ListaProjeto.objects.create(lista=alheia, projeto=ProjetoFactory(criado_por=gerente['dono']), posicao=1)

        cliente.post(reverse('mudarlista', args=[tarefa.pk, alheia.pk, 2]))

        assert not ListaTarefa.objects.filter(tarefa=tarefa).exists()

    def test_excluir_exige_post(self, gerente):
        tarefa = gerente['tarefa']

        gerente['cliente'].post(reverse('excluir_tarefa', args=[tarefa.pk]))

        assert not Tarefa.objects.filter(pk=tarefa.pk).exists()

    def test_nao_ha_edicao_de_campo_arbitrario(self, gerente):
        """A antiga rota `editar_tarefa` gravava qualquer campo do POST (até `projeto_id`), sem CSRF."""
        tarefa = gerente['tarefa']
        outro = ProjetoFactory(criado_por=gerente['dono'])

        gerente['cliente'].post(f'/gerenciador_projetos/tarefa/{tarefa.pk}/editar_tarefa/', {'field': 'projeto_id', 'value': outro.pk})

        tarefa.refresh_from_db()
        assert tarefa.projeto_id == gerente['projeto'].pk

    def test_post_sem_token_csrf_e_recusado(self, gerente):
        """Sem `@csrf_exempt`: uma página externa não cria tarefa nem muda campus em nome de quem está logado."""
        projeto, tarefa = gerente['projeto'], gerente['tarefa']
        cliente = Client(enforce_csrf_checks=True)
        cliente.force_login(gerente['dono'])
        antes = Tarefa.objects.filter(projeto=projeto).count()

        api = cliente.post(reverse('adicionar_tarefa_api', args=[projeto.pk]), {'titulo': 'via página externa'})
        campus = cliente.post(reverse('atribuir_tarefa_a_campus', args=[tarefa.pk]), {})
        exclusao = cliente.post(reverse('excluir_tarefa', args=[tarefa.pk]))

        assert (api.status_code, campus.status_code, exclusao.status_code) == (403, 403, 403)
        assert Tarefa.objects.filter(projeto=projeto).count() == antes
