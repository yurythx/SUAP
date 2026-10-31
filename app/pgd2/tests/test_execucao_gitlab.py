import datetime
from decimal import Decimal

import pytest
from django.core.exceptions import PermissionDenied
from django.db import IntegrityError

from demandas.models import AnalistaDesenvolvedor
from pgd2 import services
from pgd2.models import PlanoIndividualTrabalho, RelatorioIndividualTrabalho

pytestmark = pytest.mark.django_db(databases='__all__')


class TestRitProvenienciaGitLab:
    def test_cria_rit_com_proveniencia_gitlab(self, cadeia_rit_pgd2) -> None:
        rit = RelatorioIndividualTrabalho.objects.create(
            entrega_pit=cadeia_rit_pgd2.entrega_pit,
            titulo='Corrige bug no histórico',
            descricao='Ajuste descrito na issue #7.',
            tempo_executado=Decimal('3'),
            data_inicio=datetime.date.today(),
            data_fim=datetime.date.today(),
            gitlab_project_id=42,
            gitlab_mr_iid=7,
        )
        assert rit.gitlab_project_id == 42
        assert rit.gitlab_mr_iid == 7

    def test_unique_parcial_projeto_mr(self, cadeia_rit_pgd2) -> None:
        kwargs = {
            'entrega_pit': cadeia_rit_pgd2.entrega_pit,
            'descricao': 'd',
            'tempo_executado': Decimal('1'),
            'gitlab_project_id': 42,
            'gitlab_mr_iid': 7,
        }
        RelatorioIndividualTrabalho.objects.create(titulo='a', **kwargs)
        with pytest.raises(IntegrityError):
            RelatorioIndividualTrabalho.objects.create(titulo='b', **kwargs)

    def test_rits_manuais_sem_gitlab_nao_colidem(self, cadeia_rit_pgd2) -> None:
        RelatorioIndividualTrabalho.objects.create(entrega_pit=cadeia_rit_pgd2.entrega_pit, titulo='m1', descricao='d', tempo_executado=Decimal('1'))
        RelatorioIndividualTrabalho.objects.create(entrega_pit=cadeia_rit_pgd2.entrega_pit, titulo='m2', descricao='d', tempo_executado=Decimal('1'))
        assert RelatorioIndividualTrabalho.objects.filter(gitlab_mr_iid__isnull=True).count() == 2


class TestResolverServidor:
    def test_resolve_servidor_por_username_gitlab(self, cadeia_rit_pgd2) -> None:
        user = cadeia_rit_pgd2.servidor.get_user()
        AnalistaDesenvolvedor.objects.create(usuario=user, username_gitlab='dev.fulano', ativo=True)
        servidor = services.resolver_servidor_por_gitlab_username('dev.fulano')
        assert servidor == cadeia_rit_pgd2.servidor

    def test_username_inexistente_levanta_valueerror(self, db) -> None:
        with pytest.raises(ValueError):
            services.resolver_servidor_por_gitlab_username('nao.existe')


class TestEntregasDisponiveis:
    def test_lista_entregas_quando_gate_permite(self, cadeia_rit_pgd2, monkeypatch) -> None:
        monkeypatch.setattr(PlanoIndividualTrabalho, 'pode_cadastrar_entrega_rit', lambda self, *a, **k: True)
        entregas = services.get_entregas_disponiveis_para_servidor(cadeia_rit_pgd2.servidor)
        assert cadeia_rit_pgd2.entrega_pit in entregas

    def test_nao_lista_quando_gate_nega(self, cadeia_rit_pgd2, monkeypatch) -> None:
        monkeypatch.setattr(PlanoIndividualTrabalho, 'pode_cadastrar_entrega_rit', lambda self, *a, **k: False)
        entregas = services.get_entregas_disponiveis_para_servidor(cadeia_rit_pgd2.servidor)
        assert entregas == []


class TestLancarRitViaGitlab:
    def _dados(self, **over):
        dados = {
            'titulo': 'Execução do MR !7',
            'descricao': 'Trabalho entregue.',
            'tempo_executado': Decimal('4'),
            'perc_executada_em_teletrabalho': Decimal('50'),
            'data_inicio': datetime.date.today(),
            'data_fim': datetime.date.today(),
            'quantidade_progresso': Decimal('100'),
        }
        dados.update(over)
        return dados

    def test_cria_rit_mapeando_campos(self, cadeia_rit_pgd2, monkeypatch) -> None:
        monkeypatch.setattr(PlanoIndividualTrabalho, 'pode_cadastrar_entrega_rit', lambda self, *a, **k: True)
        monkeypatch.setattr(PlanoIndividualTrabalho, 'calcular_pit', lambda self: None)

        rit = services.lancar_rit_via_gitlab(cadeia_rit_pgd2.entrega_pit, self._dados(), gitlab_project_id=42, gitlab_mr_iid=7)

        assert isinstance(rit, RelatorioIndividualTrabalho)
        assert rit.titulo == 'Execução do MR !7'
        assert rit.tempo_executado == Decimal('4')
        # tempo_executada_em_teletrabalho = 50% de 4 = 2
        assert rit.tempo_executada_em_teletrabalho == Decimal('2')
        assert rit.gitlab_project_id == 42
        assert rit.gitlab_mr_iid == 7

    def test_idempotente_atualiza_mesmo_rit(self, cadeia_rit_pgd2, monkeypatch) -> None:
        monkeypatch.setattr(PlanoIndividualTrabalho, 'pode_cadastrar_entrega_rit', lambda self, *a, **k: True)
        monkeypatch.setattr(PlanoIndividualTrabalho, 'calcular_pit', lambda self: None)

        rit1 = services.lancar_rit_via_gitlab(cadeia_rit_pgd2.entrega_pit, self._dados(), gitlab_project_id=42, gitlab_mr_iid=7)
        rit2 = services.lancar_rit_via_gitlab(
            cadeia_rit_pgd2.entrega_pit, self._dados(tempo_executado=Decimal('6')), gitlab_project_id=42, gitlab_mr_iid=7
        )

        assert rit1.id == rit2.id
        assert rit2.tempo_executado == Decimal('6')
        assert RelatorioIndividualTrabalho.objects.filter(gitlab_project_id=42, gitlab_mr_iid=7).count() == 1

    def test_permissao_negada_levanta_permissiondenied(self, cadeia_rit_pgd2, monkeypatch) -> None:
        monkeypatch.setattr(PlanoIndividualTrabalho, 'pode_cadastrar_entrega_rit', lambda self, *a, **k: False)
        with pytest.raises(PermissionDenied):
            services.lancar_rit_via_gitlab(cadeia_rit_pgd2.entrega_pit, self._dados(), gitlab_project_id=42, gitlab_mr_iid=7)

    def test_gate_real_nega_quando_mes_ja_enviado(self, cadeia_rit_pgd2) -> None:
        cadeia_rit_pgd2.pit.situacao_rit = PlanoIndividualTrabalho.AGUARDANDO_PARECER_RIT
        cadeia_rit_pgd2.pit.save()
        with pytest.raises(PermissionDenied):
            services.lancar_rit_via_gitlab(cadeia_rit_pgd2.entrega_pit, self._dados(), gitlab_project_id=42, gitlab_mr_iid=7)
