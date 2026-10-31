from __future__ import annotations

import datetime
from unittest.mock import MagicMock

import pytest
from django.contrib.admin.sites import AdminSite

from edu.admin.alunos import AlunoAdmin
from edu.models import Aluno


class TestAlunoAdminGetInfoPrincipal:
    @pytest.fixture
    def aluno_admin(self):
        admin_site = AdminSite()
        return AlunoAdmin(Aluno, admin_site)

    @pytest.fixture
    def aluno_mock(self):
        aluno = MagicMock()
        aluno.pessoa_fisica.nome_registro = 'NOME ALUNO SOBRENOME'
        aluno.pessoa_fisica.nome_social = ''
        aluno.pessoa_fisica.cpf = '302.728.490-81'
        aluno.matricula = '20231163000026'
        aluno.curso_campus = 'ENGENHARIA DE PRODUÇÃO'
        aluno.codigo_sistec = 110996661
        aluno.data_inicio_ciclo = datetime.date(2023, 3, 1)
        aluno.data_prevista_termino_ciclo = datetime.date(2027, 12, 31)
        return aluno

    def test_exibe_dados_sistec_quando_tem_permissao_operador_censo(self, aluno_admin, aluno_mock):
        request = MagicMock()
        request.user.has_perm.side_effect = lambda perm: perm == 'comum.is_operador_de_censo'
        request.user.groups.values_list.return_value = []
        aluno_admin.request = request

        html = aluno_admin.get_info_principal(aluno_mock)

        assert '<dt>Dados SISTEC:</dt>' in html
        assert '<dd>110996661 | 01/03/2023 | 31/12/2027</dd>' in html

    def test_nao_exibe_dados_sistec_quando_sem_permissao_operador_censo(self, aluno_admin, aluno_mock):
        request = MagicMock()
        request.user.has_perm.return_value = False
        request.user.groups.values_list.return_value = []
        aluno_admin.request = request

        html = aluno_admin.get_info_principal(aluno_mock)

        assert '<dt>Dados SISTEC:</dt>' not in html
        assert '110996661' not in html

    def test_exibe_tracos_quando_dados_sistec_sao_none(self, aluno_admin, aluno_mock):
        request = MagicMock()
        request.user.has_perm.side_effect = lambda perm: perm == 'comum.is_operador_de_censo'
        request.user.groups.values_list.return_value = []
        aluno_admin.request = request

        aluno_mock.codigo_sistec = None
        aluno_mock.data_inicio_ciclo = None
        aluno_mock.data_prevista_termino_ciclo = None

        html = aluno_admin.get_info_principal(aluno_mock)

        assert '<dt>Dados SISTEC:</dt>' in html
        assert '<dd>- | - | -</dd>' in html
