import datetime

import pytest

from demandas.models import Atualizacao


@pytest.fixture
def atualizacao(servidor_a):
    atualizacao = Atualizacao.objects.create(
        data=datetime.date.today(),
        descricao='Atualização de Teste',
        tipo=Atualizacao.FUNCIONALIDADE,
    )
    atualizacao.responsaveis.add(servidor_a.get_user())
    return atualizacao


class TestTI:
    def test_atualizacoes(self, api_client, atualizacao):
        results = api_client.get('/api/ti/atualizacoes-suap/').json()['results']
        assert len(results) == 1
        assert results[0]['descricao'] == 'Atualização de Teste'
