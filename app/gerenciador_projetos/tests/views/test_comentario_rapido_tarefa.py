"""Testa o formulário rápido de novo comentário exibido acima da listagem de
histórico de uma Tarefa."""

from __future__ import annotations

import pytest
from django.urls import reverse

from gerenciador_projetos.enums import SituacaoTarefa
from gerenciador_projetos.models import HistoricoEvolucao, Projeto, Tarefa
from rh.models import UnidadeOrganizacional
from rh.tests.factories import ServidorFactory


class TestComentarioRapidoTarefa:
    def _tarefa(self) -> Tarefa:
        uo, _ = UnidadeOrganizacional.objects.get_or_create(setor=self.setor, defaults={'nome': 'Teste', 'sigla': 'TEST'})
        projeto = Projeto.objects.create(titulo='Projeto', descricao='desc', uo=uo, criado_por=self.user_admin)
        projeto.gerentes.add(self.user_admin)
        return Tarefa.objects.create(titulo='Tarefa', projeto=projeto, criado_por=self.user_admin)

    def test_adiciona_comentario_rapido(self, client):
        tarefa = self._tarefa()
        client.force_login(self.user_admin)

        response = client.post(reverse('adicionar_comentario_rapido_tarefa', args=[tarefa.pk]), {'comentario': 'Comentário rápido'}, follow=True)

        assert response.status_code == 200
        assert HistoricoEvolucao.objects.filter(tarefa=tarefa, comentario='Comentário rápido', mensagem_automatica=False).exists()

    def test_notifica_novo_comentario_sem_notificar_autor(self, client, mailoutbox):
        tarefa = self._tarefa()
        servidor_destinatario = ServidorFactory(setor=self.setor)
        destinatario = servidor_destinatario.get_user()
        vinculo_destinatario = servidor_destinatario.get_vinculo()
        vinculo_destinatario.email_pessoal = f'{servidor_destinatario.matricula}@mail.gov'
        vinculo_destinatario.save(update_fields=['email_pessoal'])
        tarefa.atribuido_a.add(destinatario)
        quantidade_anterior = len(mailoutbox)
        client.force_login(self.user_admin)

        comentario = 'Comentário para notificar\nSegunda linha do comentário'
        client.post(reverse('adicionar_comentario_rapido_tarefa', args=[tarefa.pk]), {'comentario': comentario})

        assert len(mailoutbox) == quantidade_anterior + 1
        assert f'{servidor_destinatario.matricula}@mail.gov' in mailoutbox[-1].to
        assert f'{self.admin.get_vinculo().email_pessoal}' not in mailoutbox[-1].to
        assert 'novo comentário' in mailoutbox[-1].subject.lower()
        corpo = mailoutbox[-1].body
        nome_autor = self.user_admin.get_profile().nome_usual
        assert (
            f'<dt>Comentário por {nome_autor}:</dt><dd class="featured-info">Comentário para notificar<br>Segunda linha do comentário</dd>' in corpo
        )
        inicio_dados_gerais = corpo.index('<div class="dados-gerais">')
        fim_dados_gerais = corpo.index('</div>', inicio_dados_gerais)
        assert '<dt>Tarefa:</dt><dd>Tarefa</dd>' in corpo[inicio_dados_gerais:fim_dados_gerais]
        assert corpo.index('</div>', inicio_dados_gerais) < corpo.index('<p class="more-info">', inicio_dados_gerais)

    def test_bloqueado_para_tarefa_concluida(self, client):
        tarefa = self._tarefa()
        tarefa.data_conclusao = tarefa.aberto_em.date()
        tarefa.situacao = SituacaoTarefa.CONCLUIDA
        tarefa.save()
        client.force_login(self.user_admin)

        client.post(reverse('adicionar_comentario_rapido_tarefa', args=[tarefa.pk]), {'comentario': 'Não deveria salvar'})

        assert not HistoricoEvolucao.objects.filter(tarefa=tarefa, comentario='Não deveria salvar').exists()

    def test_bloqueado_para_tarefa_cancelada_sem_data_conclusao(self, client):
        """Cobre o caso que distingue `bloqueada_para_novas_acoes` (baseada em `situacao`) de
        `concluida` (baseada em `data_conclusao`): uma tarefa Cancelada sem `data_conclusao`
        preenchida é `concluida == False`, mas ainda assim deve bloquear novas ações."""
        tarefa = self._tarefa()
        tarefa.situacao = SituacaoTarefa.CANCELADA
        tarefa.save()
        client.force_login(self.user_admin)

        client.post(reverse('adicionar_comentario_rapido_tarefa', args=[tarefa.pk]), {'comentario': 'Não deveria salvar'})

        assert not HistoricoEvolucao.objects.filter(tarefa=tarefa, comentario='Não deveria salvar').exists()
