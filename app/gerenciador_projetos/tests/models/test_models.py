"""Testa a property que identifica se a data estimada de conclusão da Tarefa já
foi ultrapassada."""

from __future__ import annotations

import datetime
from unittest.mock import patch

import pytest
from django.conf import settings

from gerenciador_projetos.enums import SituacaoTarefa
from gerenciador_projetos.models import HistoricoEvolucao, Projeto, Tarefa
from rh.models import UnidadeOrganizacional
from rh.tests.factories import ServidorFactory


class TestDataEstimadaUltrapassada:
    def _tarefa(self, **kwargs) -> Tarefa:
        uo, _ = UnidadeOrganizacional.objects.get_or_create(setor=self.setor, defaults={'nome': 'Teste', 'sigla': 'TEST'})
        projeto = Projeto.objects.create(titulo='Projeto', descricao='desc', uo=uo, criado_por=self.user_admin)
        return Tarefa.objects.create(titulo='Tarefa', projeto=projeto, criado_por=self.user_admin, **kwargs)

    def test_ultrapassada_quando_data_passou_e_nao_concluida(self):
        ontem = datetime.date.today() - datetime.timedelta(days=1)
        tarefa = self._tarefa(data_conclusao_estimada=ontem)
        assert tarefa.data_estimada_ultrapassada is True

    def test_nao_ultrapassada_quando_data_no_futuro(self):
        amanha = datetime.date.today() + datetime.timedelta(days=1)
        tarefa = self._tarefa(data_conclusao_estimada=amanha)
        assert tarefa.data_estimada_ultrapassada is False

    def test_nao_ultrapassada_quando_tarefa_ja_concluida(self):
        ontem = datetime.date.today() - datetime.timedelta(days=1)
        tarefa = self._tarefa(data_conclusao_estimada=ontem, data_conclusao=datetime.date.today())
        assert tarefa.data_estimada_ultrapassada is False


class TestNotificacaoMudancaSituacaoTarefa:
    def _tarefa(self) -> Tarefa:
        uo, _ = UnidadeOrganizacional.objects.get_or_create(setor=self.setor, defaults={'nome': 'Teste', 'sigla': 'TEST'})
        projeto = Projeto.objects.create(titulo='Projeto', descricao='desc', uo=uo, criado_por=self.user_admin)
        tarefa = Tarefa.objects.create(titulo='Tarefa', projeto=projeto, criado_por=self.user_admin)
        tarefa.atribuido_a.add(self.user_admin)
        return tarefa

    def test_notifica_outros_atribuidos_com_url_absoluta(self, mailoutbox) -> None:
        tarefa = self._tarefa()
        servidor_destinatario = ServidorFactory(setor=self.setor)
        destinatario = servidor_destinatario.get_user()
        vinculo_destinatario = servidor_destinatario.get_vinculo()
        vinculo_destinatario.email_pessoal = f'{servidor_destinatario.matricula}@mail.gov'
        vinculo_destinatario.save(update_fields=['email_pessoal'])
        tarefa.atribuido_a.add(destinatario)
        qtd_emails_antes = len(mailoutbox)

        tarefa.situacao = SituacaoTarefa.EM_ANDAMENTO
        with patch('gerenciador_projetos.models.tl.get_user', return_value=self.user_admin):
            tarefa.save()

        assert len(mailoutbox) == qtd_emails_antes + 1
        assert 'Situação de tarefa alterada' in mailoutbox[-1].subject
        corpo = mailoutbox[-1].body
        assert f'{settings.SITE_URL}{tarefa.get_absolute_url()}' in corpo
        assert '<div class="dados-gerais">' in corpo
        assert '<dt>Tarefa:</dt><dd>Tarefa</dd>' in corpo
        assert '<dt>Situação:</dt><dd>Em andamento</dd>' in corpo

    def test_nao_notifica_quando_situacao_nao_muda(self, mailoutbox):
        tarefa = self._tarefa()
        tarefa.titulo = 'Outro título'
        qtd_emails_antes = len(mailoutbox)

        tarefa.save()

        assert len(mailoutbox) == qtd_emails_antes


class TestReabrirTarefa:
    def _tarefa(self) -> Tarefa:
        uo, _ = UnidadeOrganizacional.objects.get_or_create(setor=self.setor, defaults={'nome': 'Teste', 'sigla': 'TEST'})
        projeto = Projeto.objects.create(titulo='Projeto', descricao='desc', uo=uo, criado_por=self.user_admin)
        return Tarefa.objects.create(titulo='Tarefa', projeto=projeto, criado_por=self.user_admin)

    def test_reabrir_tarefa_concluida_volta_para_aberta(self) -> None:
        tarefa = self._tarefa()
        tarefa.fechar_tarefa()

        tarefa.reabrir(self.user_admin)

        tarefa.refresh_from_db()
        assert tarefa.data_conclusao is None
        assert tarefa.situacao == SituacaoTarefa.ABERTA
        assert tarefa.percentual_executado == 0
        assert tarefa.bloqueada_para_novas_acoes is False


class TestEvolucaoTarefa:
    def _tarefa(self, **kwargs: object) -> Tarefa:
        uo, _ = UnidadeOrganizacional.objects.get_or_create(setor=self.setor, defaults={'nome': 'Teste', 'sigla': 'TEST'})
        projeto = Projeto.objects.create(titulo='Projeto', descricao='desc', uo=uo, criado_por=self.user_admin)
        return Tarefa.objects.create(titulo='Tarefa', projeto=projeto, criado_por=self.user_admin, **kwargs)

    def test_percentual_cem_conclui_tarefa_e_subtarefas(self) -> None:
        tarefa = self._tarefa()
        subtarefa = Tarefa.objects.create(titulo='Subtarefa', projeto=tarefa.projeto, criado_por=self.user_admin, tarefa_pai=tarefa)

        HistoricoEvolucao.objects.create(
            tarefa=tarefa,
            comentario='Execução concluída.',
            percentual_executado=100,
            registrado_por=self.user_admin,
        )

        tarefa.refresh_from_db()
        subtarefa.refresh_from_db()
        assert tarefa.situacao == SituacaoTarefa.CONCLUIDA
        assert tarefa.percentual_executado == 100
        assert tarefa.data_conclusao == datetime.date.today()
        assert subtarefa.situacao == SituacaoTarefa.CONCLUIDA
        assert subtarefa.data_conclusao == datetime.date.today()

    def test_percentual_parcial_coloca_tarefa_em_andamento(self) -> None:
        tarefa = self._tarefa()

        HistoricoEvolucao.objects.create(
            tarefa=tarefa,
            comentario='Execução iniciada.',
            percentual_executado=50,
            registrado_por=self.user_admin,
        )

        tarefa.refresh_from_db()
        assert tarefa.percentual_executado == 50
        assert tarefa.situacao == SituacaoTarefa.EM_ANDAMENTO

    def test_evolucao_preserva_data_de_conclusao_informada(self) -> None:
        tarefa = self._tarefa()
        data_conclusao = datetime.date.today() - datetime.timedelta(days=1)

        HistoricoEvolucao.objects.create(
            tarefa=tarefa,
            comentario='Execução concluída.',
            percentual_executado=100,
            data_conclusao=data_conclusao,
            registrado_por=self.user_admin,
        )

        tarefa.refresh_from_db()
        assert tarefa.situacao == SituacaoTarefa.CONCLUIDA
        assert tarefa.percentual_executado == 100
        assert tarefa.data_conclusao == data_conclusao


class TestNotificacaoAtribuirPara:
    def _tarefa(self) -> Tarefa:
        uo, _ = UnidadeOrganizacional.objects.get_or_create(setor=self.setor, defaults={'nome': 'Teste', 'sigla': 'TEST'})
        projeto = Projeto.objects.create(titulo='Projeto', descricao='desc', uo=uo, criado_por=self.user_admin)
        return Tarefa.objects.create(titulo='Tarefa', projeto=projeto, criado_por=self.user_admin)

    def test_atribuir_para_notifica_uma_unica_vez(self, mailoutbox):
        tarefa = self._tarefa()
        qtd_emails_antes = len(mailoutbox)

        tarefa.atribuir_para(self.user_admin)

        assert len(mailoutbox) == qtd_emails_antes + 1
