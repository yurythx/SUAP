import logging

import pytest

from comum.pytest_fixtures import api_auth_mocks, suap_client, sync_permissions


@pytest.fixture(autouse=True)
def auto_db(db, sync_permissions):
    """Banco e grupos para todos os testes do `rh`.

    `sync_permissions` porque o `save` de `Servidor` dispara signals que buscam grupos por
    nome ('Aposentado', 'Servidor'...); sem eles o save estoura `Group.DoesNotExist`. Era
    dependência do antigo `siape_executado`.
    """


@pytest.fixture
def logging_habilitado():
    """O conftest raiz desliga o logging na sessão (`logging.disable(CRITICAL)`); a captura de ocorrências da importação SIAPE precisa dele."""
    anterior = logging.root.manager.disable
    logging.disable(logging.NOTSET)
    yield
    logging.disable(anterior)


@pytest.fixture
def importacao_serial():
    """Motor da importação SIAPE em série: threads não enxergam a transação do teste."""
    from comum.models import Configuracao

    Configuracao.objects.update_or_create(app='rh', chave='importacao_siape_workers', defaults={'valor': '1'})
    Configuracao.clear_cache()
    yield
    Configuracao.clear_cache()


@pytest.fixture
def limpar_importacoes(settings, tmp_path):
    """Mídia das importações SIAPE num diretório temporário, com a semântica de pasta do S3/MinIO.

    Os IDs do banco de teste recomeçam em 1: gravando no `deploy/media` do desenvolvedor, um teste
    que criasse a importação 8 e terminasse apagaria a pasta `importacoes/8` real dele. E em
    produção o storage é o MinIO, onde uma pasta não "existe" (ver `rh.tests.armazenamento_s3`).
    """
    settings.MEDIA_ROOT = str(tmp_path)
    settings.STORAGES = {**settings.STORAGES, 'default': {'BACKEND': 'rh.tests.armazenamento_s3.ArmazenamentoComoS3'}}
