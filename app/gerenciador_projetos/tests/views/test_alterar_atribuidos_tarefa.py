"""Testa a tela dedicada de adicionar/remover atribuídos de uma Tarefa, no mesmo
padrão de "Alterar Analistas" de uma Demanda (`demandas/views.py:231`,
`demandas/forms.py:341`)."""

from __future__ import annotations

import pytest
from django.conf import settings
from django.test import Client
from django.urls import reverse

from comum.models import User
from gerenciador_projetos.enums import SituacaoTarefa
from gerenciador_projetos.models import Projeto, Tarefa
from rh.models import UnidadeOrganizacional
from rh.tests.factories import ServidorFactory


class TestAlterarAtribuidosTarefa:
    def _tarefa(self) -> Tarefa:
        uo, _ = UnidadeOrganizacional.objects.get_or_create(setor=self.setor, defaults={'nome': 'Teste', 'sigla': 'TEST'})
        projeto = Projeto.objects.create(titulo='Projeto', descricao='desc', uo=uo, criado_por=self.user_admin)
        projeto.gerentes.add(self.user_admin)
        projeto.membros.add(self.user_admin)
        return Tarefa.objects.create(titulo='Tarefa', projeto=projeto, criado_por=self.user_admin)

    def test_adiciona_e_remove_atribuido(self, client):
        tarefa = self._tarefa()
        client.force_login(self.user_admin)

        response = client.post(reverse('alterar_atribuidos_tarefa', args=[tarefa.pk]), {'atribuido_a': [self.user_admin.pk]}, follow=True)

        assert response.status_code == 200
        tarefa.refresh_from_db()
        assert list(tarefa.atribuido_a.all()) == [self.user_admin]

        # 'csrfmiddlewaretoken' aqui só serve para o corpo do POST não ficar vazio: a view usa o idioma
        # `request.POST or None` (padrão do módulo — ver forms.py), que trata um QueryDict vazio como se
        # fosse GET (form não vinculado). Num POST real de navegador isso nunca acontece porque o token CSRF
        # sempre viaja como campo do form; o test client, que não injeta esse token por padrão, precisa de
        # um substituto para simular o mesmo POST "não-vazio, mas sem nenhum atribuído marcado".
        response = client.post(reverse('alterar_atribuidos_tarefa', args=[tarefa.pk]), {'csrfmiddlewaretoken': 'x'}, follow=True)
        tarefa.refresh_from_db()
        assert list(tarefa.atribuido_a.all()) == []

    def test_nao_notifica_usuario_que_se_atribuiu(self, client, mailoutbox):
        tarefa = self._tarefa()
        client.force_login(self.user_admin)
        quantidade_anterior = len(mailoutbox)

        client.post(reverse('alterar_atribuidos_tarefa', args=[tarefa.pk]), {'atribuido_a': [self.user_admin.pk]})

        assert len(mailoutbox) == quantidade_anterior

    def test_registra_historico_ao_adicionar_atribuido(self, client) -> None:
        tarefa = self._tarefa()
        client.force_login(self.user_admin)

        client.post(reverse('alterar_atribuidos_tarefa', args=[tarefa.pk]), {'atribuido_a': [self.user_admin.pk]})

        historico = tarefa.get_historicoevolucao().first()
        assert historico is not None
        assert 'Atribuições alteradas por' in historico.comentario
        assert 'Atribuídos adicionados:' in historico.comentario
        assert str(self.user_admin) in historico.comentario

    def test_registra_historico_ao_remover_atribuido(self, client) -> None:
        tarefa = self._tarefa()
        tarefa.atribuido_a.add(self.user_admin)
        client.force_login(self.user_admin)

        client.post(reverse('alterar_atribuidos_tarefa', args=[tarefa.pk]), {'csrfmiddlewaretoken': 'x'})

        historico = tarefa.get_historicoevolucao().first()
        assert historico is not None
        assert 'Atribuições alteradas por' in historico.comentario
        assert 'Atribuídos removidos:' in historico.comentario
        assert str(self.user_admin) in historico.comentario

    def test_registra_um_historico_quando_autor_da_atribuicao_muda(self, client: Client) -> None:
        tarefa = self._tarefa()
        tarefa.atribuido_por = User.objects.create_user(username='atribuidor_anterior')
        tarefa.save()
        quantidade_anterior = tarefa.get_historicoevolucao().count()
        client.force_login(self.user_admin)

        client.post(reverse('alterar_atribuidos_tarefa', args=[tarefa.pk]), {'atribuido_a': [self.user_admin.pk]})

        assert tarefa.get_historicoevolucao().count() == quantidade_anterior + 1

    def test_fecha_popup_apos_salvar_atribuicoes(self, client) -> None:
        tarefa = self._tarefa()
        client.force_login(self.user_admin)

        response = client.post(f'{reverse("alterar_atribuidos_tarefa", args=[tarefa.pk])}?_popup=1', {'atribuido_a': [self.user_admin.pk]})

        assert response.status_code == 200
        assert response.content == b'<script>parent.close_fancybox();</script>'
        tarefa.refresh_from_db()
        assert list(tarefa.atribuido_a.all()) == [self.user_admin]

    def test_email_de_notificacao_inclui_quem_atribuiu(self, client, mailoutbox):
        # `atribuido_por` precisa estar salvo na Tarefa ANTES do `.set(users)` disparar o signal
        # `m2m_changed`, que monta o e-mail de forma síncrona (ver `atualizar_atribuicoes` em
        # `gerenciador_projetos/models.py` e o signal em `gerenciador_projetos/signals.py`).
        tarefa = self._tarefa()
        servidor_destinatario = ServidorFactory(setor=self.setor)
        destinatario = servidor_destinatario.get_user()
        vinculo_destinatario = servidor_destinatario.get_vinculo()
        vinculo_destinatario.email_pessoal = f'{servidor_destinatario.matricula}@mail.gov'
        vinculo_destinatario.save(update_fields=['email_pessoal'])
        tarefa.projeto.membros.add(destinatario)
        mailoutbox.clear()
        client.force_login(self.user_admin)

        client.post(reverse('alterar_atribuidos_tarefa', args=[tarefa.pk]), {'atribuido_a': [destinatario.pk]})

        assert len(mailoutbox) >= 1
        corpo = mailoutbox[-1].body
        assert 'Atribuído por' in corpo
        assert str(self.user_admin) in corpo
        assert f'{settings.SITE_URL.rstrip("/")}{tarefa.get_absolute_url()}' in corpo
        assert '<div class="dados-gerais">' in corpo
        assert '<dt>Tarefa:</dt><dd>Tarefa</dd>' in corpo

    def test_bloqueia_alteracao_de_tarefa_cancelada(self, client):
        tarefa = self._tarefa()
        tarefa.situacao = SituacaoTarefa.CANCELADA
        tarefa.save()
        assert tarefa.data_conclusao is None
        client.force_login(self.user_admin)

        response = client.post(reverse('alterar_atribuidos_tarefa', args=[tarefa.pk]), {'atribuido_a': [self.user_admin.pk]}, follow=True)

        assert response.status_code == 200
        tarefa.refresh_from_db()
        assert list(tarefa.atribuido_a.all()) == []
