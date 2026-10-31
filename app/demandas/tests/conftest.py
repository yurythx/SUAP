from unittest import mock

import pytest

from comum.tests.factories import UserFactory
from demandas.models import Demanda
from demandas.tests.factories import DemandaFactory


@pytest.fixture(autouse=True)
def sem_efeitos_externos():
    """Isola os fluxos dos colaboradores externos/ruidosos de alterar_situacao.

    São dependências reais externas — e-mail e API do GitLab — não regras do
    fluxo. Mocká-las mantém os testes rápidos e determinísticos sem alterar a
    transição de estado em si.
    """
    with (
        # Patch no módulo que usa os nomes: `demandas.models` só os reexporta.
        mock.patch('demandas.models.demanda.Notificar'),
        mock.patch('demandas.models.demanda.adicionar_comentario'),
        mock.patch.object(Demanda, 'gerenciar_issues_gitlab'),
        mock.patch.object(Demanda, 'criar_mergerequest_gitlab'),
        # geração de changelog na conclusão depende da configuração da área; é tangencial à transição de estado.
        mock.patch.object(Demanda, 'gerar_atualizacao_demanda'),
    ):
        yield


# --- Fixtures de fluxo -------------------------------------------------------


@pytest.fixture
def usuario(db):
    return UserFactory()


@pytest.fixture
def demanda(db):
    """Demanda recém-aberta (nasce em ESTADO_ABERTO / 'Solicitada')."""
    return DemandaFactory(titulo='Melhorar o relatório X')
