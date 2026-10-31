"""Testa a troca de situação da Tarefa por uma tela de confirmação dedicada, no mesmo
padrão de "Alterar situação" de uma Demanda (``demandas/views.py:827``)."""

from __future__ import annotations

import pytest
from django.urls import reverse

from gerenciador_projetos.enums import SituacaoTarefa
from gerenciador_projetos.models import Projeto, Tarefa
from rh.models import UnidadeOrganizacional


class TestAlterarSituacaoTarefa:
    def _tarefa(self) -> Tarefa:
        uo, _ = UnidadeOrganizacional.objects.get_or_create(setor=self.setor, defaults={'nome': 'Teste', 'sigla': 'TEST'})
        projeto = Projeto.objects.create(titulo='Projeto', descricao='desc', uo=uo, criado_por=self.user_admin)
        projeto.gerentes.add(self.user_admin)
        return Tarefa.objects.create(titulo='Tarefa', projeto=projeto, criado_por=self.user_admin, situacao=SituacaoTarefa.ABERTA)

    def test_modal_exibe_contexto_da_alteracao(self, client) -> None:
        tarefa = self._tarefa()
        client.force_login(self.user_admin)

        response = client.get(reverse('alterar_situacao_tarefa', args=[tarefa.pk, SituacaoTarefa.EM_ANDAMENTO]))

        assert response.status_code == 200
        conteudo = response.content.decode()
        assert 'Confirme a alteração de situação da tarefa abaixo.' in conteudo
        assert '<dt>Tarefa</dt>' in conteudo
        assert 'Tarefa' in conteudo
        assert '<dt>Situação atual</dt>' in conteudo
        assert 'Aberta' in conteudo
        assert '<dt>Nova situação</dt>' in conteudo
        assert 'Em andamento' in conteudo
        assert 'value="Alterar para Em andamento"' in conteudo
        assert 'class="btn"' in conteudo

    def test_altera_situacao(self, client):
        tarefa = self._tarefa()
        client.force_login(self.user_admin)

        # 'csrfmiddlewaretoken' só está aqui para o corpo do POST não ficar vazio: a view usa o idioma
        # `request.POST or None` (padrão do módulo), que trata um QueryDict vazio como GET (form não
        # vinculado). Um POST real de navegador nunca manda corpo vazio (o token CSRF sempre viaja como
        # campo); o test client não injeta esse token por padrão, daí o substituto explícito.
        response = client.post(
            reverse('alterar_situacao_tarefa', args=[tarefa.pk, SituacaoTarefa.EM_ANDAMENTO]),
            {'csrfmiddlewaretoken': 'x'},
            follow=True,
        )

        assert response.status_code == 200
        tarefa.refresh_from_db()
        assert tarefa.situacao == SituacaoTarefa.EM_ANDAMENTO

    def test_fecha_popup_apos_alterar_situacao(self, client) -> None:
        tarefa = self._tarefa()
        client.force_login(self.user_admin)

        response = client.post(
            f'{reverse("alterar_situacao_tarefa", args=[tarefa.pk, SituacaoTarefa.EM_ANDAMENTO])}?_popup=1',
            {'csrfmiddlewaretoken': 'x'},
        )

        assert response.status_code == 200
        assert response.content == b'<script>parent.close_fancybox();</script>'
        tarefa.refresh_from_db()
        assert tarefa.situacao == SituacaoTarefa.EM_ANDAMENTO

    def test_altera_situacao_gera_exatamente_um_historico(self, client):
        """A troca de situação não pode duplicar a entrada de histórico: `Tarefa.save()`
        já registra automaticamente o diff via `has_changed`/`diff_verbose` — o form desta
        tela não deve criar outra manualmente."""
        tarefa = self._tarefa()
        qtd_historico_antes = tarefa.get_historicoevolucao().count()
        client.force_login(self.user_admin)

        client.post(
            reverse('alterar_situacao_tarefa', args=[tarefa.pk, SituacaoTarefa.EM_ANDAMENTO]),
            {'csrfmiddlewaretoken': 'x'},
            follow=True,
        )

        assert tarefa.get_historicoevolucao().count() == qtd_historico_antes + 1

    def test_altera_situacao_para_concluida_gera_exatamente_um_historico(self, client):
        tarefa = self._tarefa()
        qtd_historico_antes = tarefa.get_historicoevolucao().count()
        client.force_login(self.user_admin)

        client.post(
            reverse('alterar_situacao_tarefa', args=[tarefa.pk, SituacaoTarefa.CONCLUIDA]),
            {'csrfmiddlewaretoken': 'x'},
            follow=True,
        )

        tarefa.refresh_from_db()
        assert tarefa.situacao == SituacaoTarefa.CONCLUIDA
        assert tarefa.get_historicoevolucao().count() == qtd_historico_antes + 1

    def test_bloqueado_para_tarefa_concluida(self, client):
        tarefa = self._tarefa()
        tarefa.situacao = SituacaoTarefa.CONCLUIDA
        tarefa.data_conclusao = tarefa.aberto_em.date()
        tarefa.save()
        client.force_login(self.user_admin)

        response = client.post(reverse('alterar_situacao_tarefa', args=[tarefa.pk, SituacaoTarefa.EM_ANDAMENTO]), follow=True)

        mensagens = [str(m) for m in response.context['messages']]
        assert any('não é possível' in m.lower() for m in mensagens)
