"""Testes do ``RecursoDados`` — obtenção do arquivo a partir da URL."""

import pytest

from dados_abertos.enums import FormatoRecurso
from dados_abertos.models import BaseDados, RecursoDados


class RespostaFake:
    """Resposta HTTP mínima no formato que ``_download_and_attach_file_from_url`` consome."""

    def __init__(self, conteudo: bytes, content_type: str = 'application/json'):
        self.content = conteudo
        self.headers = {'Content-Type': content_type}

    def raise_for_status(self):
        return None


@pytest.fixture
def base_dados(db):
    return BaseDados.objects.create(nome='contratos', titulo='Contratos')


@pytest.fixture
def media_temporaria(settings, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path)
    return tmp_path


@pytest.mark.django_db
def test_rebaixa_o_arquivo_quando_a_url_muda(base_dados, media_temporaria, monkeypatch):
    """Trocar a URL do recurso deve substituir o arquivo pelo conteúdo do novo endereço."""
    respostas = {
        'https://exemplo.br/v1.json': b'{"versao": 1}',
        'https://exemplo.br/v2.json': b'{"versao": 2}',
    }
    monkeypatch.setattr(
        'dados_abertos.models.recurso_dados.requests.get',
        lambda url, **kwargs: RespostaFake(respostas[url]),
    )

    recurso = RecursoDados.objects.create(
        dataset=base_dados,
        nome='Contratos',
        formato=FormatoRecurso.JSON,
        url='https://exemplo.br/v1.json',
    )
    assert recurso.arquivo.read() == b'{"versao": 1}'

    recurso.url = 'https://exemplo.br/v2.json'
    recurso.save()

    recurso.arquivo.open('rb')
    try:
        assert recurso.arquivo.read() == b'{"versao": 2}'
    finally:
        recurso.arquivo.close()


@pytest.mark.django_db
def test_nao_rebaixa_o_arquivo_quando_a_url_nao_muda(base_dados, media_temporaria, monkeypatch):
    """Salvar sem mexer na URL preserva o arquivo — inclusive um enviado manualmente."""
    downloads = []

    def get_fake(url, **kwargs):
        downloads.append(url)
        return RespostaFake(b'{"versao": 1}')

    monkeypatch.setattr('dados_abertos.models.recurso_dados.requests.get', get_fake)

    recurso = RecursoDados.objects.create(
        dataset=base_dados,
        nome='Contratos',
        formato=FormatoRecurso.JSON,
        url='https://exemplo.br/v1.json',
    )
    assert downloads == ['https://exemplo.br/v1.json']

    recurso.descricao = 'Descrição revisada'
    recurso.save()

    assert downloads == ['https://exemplo.br/v1.json']
