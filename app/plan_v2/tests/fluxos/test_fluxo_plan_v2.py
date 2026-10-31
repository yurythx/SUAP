"""Teste de fluxo do Planejamento Institucional (plan_v2).

O arquivo legado era apenas um esqueleto sem testes de fato. Aqui exercitamos
o ponto de entrada real do módulo: o administrador cadastra um Eixo (a raiz da
estrutura PDI -> Dimensão -> Macroprocesso -> Ação) pelo admin.
"""

import pytest

from comum.pytest_fixtures import assert_no_validation_errors
from plan_v2.models import Eixo


@pytest.mark.django_db(databases='__all__')
class TestFluxoPlanV2:
    def test_administrador_cadastra_eixo(self, administrador):
        resposta = administrador.post('/admin/plan_v2/eixo/add/', {'nome': 'Eixo 1'})

        assert_no_validation_errors(resposta)
        assert Eixo.objects.filter(nome='Eixo 1').exists()
