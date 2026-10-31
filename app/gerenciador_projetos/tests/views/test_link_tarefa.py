"""Testa adicionar, editar e remover Links de uma Tarefa, incluindo o envio direto
pelo formulário de Registro de evolução."""

from __future__ import annotations

import pytest
from django.contrib.auth.models import Permission
from django.test import Client
from django.urls import reverse

from comum.models import User
from gerenciador_projetos.enums import SituacaoTarefa
from gerenciador_projetos.models import LinkTarefa, Projeto, Tarefa
from rh.models import UnidadeOrganizacional
from rh.tests.factories import ServidorFactory


class TestLinkTarefa:
    def _tarefa(self, atribuir: bool = True) -> Tarefa:
        uo, _ = UnidadeOrganizacional.objects.get_or_create(setor=self.setor, defaults={'nome': 'Teste', 'sigla': 'TEST'})
        projeto = Projeto.objects.create(titulo='Projeto', descricao='desc', uo=uo, criado_por=self.user_admin)
        projeto.gerentes.add(self.user_admin)
        projeto.membros.add(self.user_admin)
        tarefa = Tarefa.objects.create(titulo='Tarefa', projeto=projeto, criado_por=self.user_admin)
        if atribuir:
            tarefa.atribuido_a.add(self.user_admin)
        return tarefa

    def _gerente_sem_permissao_de_link(self, tarefa: Tarefa) -> User:
        gerente = self.user_admin
        gerente.is_superuser = False
        gerente.groups.clear()
        gerente.user_permissions.clear()
        gerente.user_permissions.add(Permission.objects.get(content_type__app_label='gerenciador_projetos', codename='change_tarefa'))
        gerente.save()
        if hasattr(gerente, '_perm_cache'):
            del gerente._perm_cache
        tarefa.projeto.gerentes.add(gerente)
        return gerente

    def test_adiciona_link(self, client):
        tarefa = self._tarefa()
        client.force_login(self.user_admin)

        response = client.post(
            reverse('adicionar_link_tarefa', args=[tarefa.pk]),
            {'titulo': 'Documentação', 'url': 'https://exemplo.gov.br/doc'},
            follow=True,
        )

        assert response.status_code == 200
        assert LinkTarefa.objects.filter(tarefa=tarefa, titulo='Documentação').exists()

    def test_notifica_novo_link_sem_notificar_autor(self, client, mailoutbox):
        tarefa = self._tarefa()
        servidor_destinatario = ServidorFactory(setor=self.setor)
        destinatario = servidor_destinatario.get_user()
        vinculo_destinatario = servidor_destinatario.get_vinculo()
        vinculo_destinatario.email_pessoal = f'{servidor_destinatario.matricula}@mail.gov'
        vinculo_destinatario.save(update_fields=['email_pessoal'])
        tarefa.atribuido_a.add(destinatario)
        quantidade_anterior = len(mailoutbox)
        client.force_login(self.user_admin)

        client.post(
            reverse('adicionar_link_tarefa', args=[tarefa.pk]),
            {'titulo': 'Documentação', 'url': 'https://exemplo.gov.br/doc'},
        )

        assert len(mailoutbox) == quantidade_anterior + 1
        assert f'{servidor_destinatario.matricula}@mail.gov' in mailoutbox[-1].to
        assert f'{self.admin.get_vinculo().email_pessoal}' not in mailoutbox[-1].to
        assert 'novo link' in mailoutbox[-1].subject.lower()

    def test_gerente_com_permissao_de_tarefa_pode_adicionar_link(self, client) -> None:
        tarefa = self._tarefa()
        gerente = self._gerente_sem_permissao_de_link(tarefa)
        client.force_login(gerente)

        response = client.post(
            reverse('adicionar_link_tarefa', args=[tarefa.pk]),
            {'titulo': 'Documentação', 'url': 'https://exemplo.gov.br/doc'},
            follow=True,
        )

        assert response.status_code == 200
        assert LinkTarefa.objects.filter(tarefa=tarefa, titulo='Documentação', criado_por=gerente).exists()

    def test_fecha_popup_apos_salvar_link(self, client) -> None:
        tarefa = self._tarefa()
        client.force_login(self.user_admin)

        response = client.post(
            f'{reverse("adicionar_link_tarefa", args=[tarefa.pk])}?_popup=1',
            {'titulo': 'Documentação', 'url': 'https://exemplo.gov.br/doc'},
        )

        assert response.status_code == 200
        assert response.content == b'<script>parent.close_fancybox();</script>'
        assert LinkTarefa.objects.filter(tarefa=tarefa, titulo='Documentação').exists()

    @pytest.mark.parametrize('situacao', [SituacaoTarefa.CONCLUIDA, SituacaoTarefa.CANCELADA])
    def test_nao_exibe_acoes_de_link_quando_tarefa_bloqueada(self, client, situacao) -> None:
        tarefa = self._tarefa()
        link = LinkTarefa.objects.create(tarefa=tarefa, titulo='Doc', url='https://exemplo.gov.br', criado_por=self.user_admin)
        tarefa.situacao = situacao
        tarefa.save()
        client.force_login(self.user_admin)

        response = client.get(f'{reverse("tarefa", args=[tarefa.pk])}?tab=links')

        assert response.status_code == 200
        conteudo = response.content.decode()
        assert reverse('adicionar_link_tarefa', args=[tarefa.pk]) not in conteudo
        assert reverse('editar_link_tarefa', args=[tarefa.pk, link.pk]) not in conteudo
        assert reverse('excluir_link_tarefa', args=[link.pk]) not in conteudo

    def test_gerente_pode_remover_link_de_outro_usuario(self, client):
        tarefa = self._tarefa()
        link = LinkTarefa.objects.create(tarefa=tarefa, titulo='Doc', url='https://exemplo.gov.br', criado_por=self.user_admin)
        client.force_login(self.user_admin)

        response = client.post(reverse('excluir_link_tarefa', args=[link.pk]), follow=True)

        assert response.status_code == 200
        assert not LinkTarefa.objects.filter(pk=link.pk).exists()

    def test_get_nao_remove_link(self, client: Client) -> None:
        tarefa = self._tarefa()
        link = LinkTarefa.objects.create(tarefa=tarefa, titulo='Doc', url='https://exemplo.gov.br', criado_por=self.user_admin)
        client.force_login(self.user_admin)

        response = client.get(reverse('excluir_link_tarefa', args=[link.pk]))

        assert response.status_code == 405
        assert LinkTarefa.objects.filter(pk=link.pk).exists()

    def test_tela_remove_link_por_formulario_post(self, client: Client) -> None:
        tarefa = self._tarefa()
        link = LinkTarefa.objects.create(tarefa=tarefa, titulo='Doc', url='https://exemplo.gov.br', criado_por=self.user_admin)
        client.force_login(self.user_admin)

        response = client.get(f'{reverse("tarefa", args=[tarefa.pk])}?tab=links')

        conteudo = response.content.decode()
        assert f'action="{reverse("excluir_link_tarefa", args=[link.pk])}"' in conteudo
        assert '<form method="post"' in conteudo
        assert 'name="csrfmiddlewaretoken"' in conteudo

    def test_recusa_remocao_sem_token_csrf(self) -> None:
        tarefa = self._tarefa()
        link = LinkTarefa.objects.create(tarefa=tarefa, titulo='Doc', url='https://exemplo.gov.br', criado_por=self.user_admin)
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user_admin)

        response = client.post(reverse('excluir_link_tarefa', args=[link.pk]))

        assert response.status_code == 403
        assert LinkTarefa.objects.filter(pk=link.pk).exists()

    def test_bloqueia_adicionar_link_em_tarefa_concluida(self, client):
        tarefa = self._tarefa()
        tarefa.situacao = SituacaoTarefa.CONCLUIDA
        tarefa.save()
        client.force_login(self.user_admin)

        response = client.post(
            reverse('adicionar_link_tarefa', args=[tarefa.pk]),
            {'titulo': 'Documentação', 'url': 'https://exemplo.gov.br/doc'},
            follow=True,
        )

        mensagens = [str(m) for m in response.context['messages']]
        assert any('não é possível' in m.lower() for m in mensagens)
        assert not LinkTarefa.objects.filter(tarefa=tarefa, titulo='Documentação').exists()

    def test_bloqueia_excluir_link_de_tarefa_cancelada(self, client):
        tarefa = self._tarefa()
        link = LinkTarefa.objects.create(tarefa=tarefa, titulo='Doc', url='https://exemplo.gov.br', criado_por=self.user_admin)
        tarefa.situacao = SituacaoTarefa.CANCELADA
        tarefa.save()
        client.force_login(self.user_admin)

        response = client.post(reverse('excluir_link_tarefa', args=[link.pk]), follow=True)

        mensagens = [str(m) for m in response.context['messages']]
        assert any('não é possível' in m.lower() for m in mensagens)
        assert LinkTarefa.objects.filter(pk=link.pk).exists()

    def test_link_pode_ser_enviado_pelo_registro_de_evolucao(self, client):
        tarefa = self._tarefa()
        client.force_login(self.user_admin)

        client.post(
            reverse('gerenciar_historicoevolucao', args=[tarefa.pk]),
            {'comentario': 'Segue o link', 'link_titulo': 'Planilha', 'link_url': 'https://exemplo.gov.br/planilha'},
        )

        assert LinkTarefa.objects.filter(tarefa=tarefa, titulo='Planilha', url='https://exemplo.gov.br/planilha').exists()
