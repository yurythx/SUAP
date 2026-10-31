"""Testes do multipart montado pelo ``CKANClient``."""

import pytest
from django.core.files.base import ContentFile
from django.db.models.fields.files import FieldFile

from dados_abertos.ckan_client import CKANClient
from dados_abertos.enums import FormatoRecurso
from dados_abertos.models import BaseDados, Organizacao, RecursoDados


@pytest.fixture
def storage_remoto(settings, tmp_path, monkeypatch):
    """Storage de produção (S3/MinIO): ``open`` funciona, ``path`` não existe."""
    settings.MEDIA_ROOT = str(tmp_path)

    def _sem_path(self):
        raise NotImplementedError("This backend doesn't support absolute paths.")

    monkeypatch.setattr(FieldFile, 'path', property(_sem_path))


@pytest.fixture
def envios(monkeypatch):
    """Troca o transporte HTTP e guarda, de cada action, o nome e o conteúdo do upload.

    O conteúdo é lido dentro da chamada, enquanto o cliente mantém o arquivo aberto.
    """
    registrados = []

    def _request(self, action, *, data=None, files=None, method=None):
        for campo, (nome, arquivo) in (files or {}).items():
            registrados.append({'action': action, 'campo': campo, 'nome': nome, 'conteudo': arquivo.read()})
        return {'id': 'x'}

    monkeypatch.setattr(CKANClient, '_request', _request)
    return registrados


def _cliente():
    return CKANClient(base_url='https://ckan.exemplo.br', api_key='chave')


@pytest.mark.django_db
def test_envia_a_imagem_da_organizacao_lida_pelo_storage(storage_remoto, envios):
    """A imagem sobe pelo storage, sem ``path``, com o nome sem o diretório do ``upload_to``."""
    org = Organizacao.objects.create(nome='ifrn', titulo='IFRN')
    org.imagem.save('logo.png', ContentFile(b'png'), save=True)

    _cliente().organization_update({'id': 'org-1'}, imagem=Organizacao.objects.get(pk=org.pk).imagem)

    assert len(envios) == 1
    envio = envios[0]
    assert envio['campo'] == 'image_upload'
    assert '/' not in envio['nome'], envio['nome']
    assert envio['nome'].endswith('.png'), envio['nome']
    assert envio['conteudo'] == b'png'


@pytest.mark.django_db
def test_envia_o_arquivo_do_recurso_lido_pelo_storage(storage_remoto, envios):
    """O arquivo do recurso sobe pelo storage, sem ``path``."""
    base = BaseDados.objects.create(nome='contratos', titulo='Contratos')
    recurso = RecursoDados(dataset=base, nome='Contratos', descricao='Contratos', formato=FormatoRecurso.CSV)
    recurso.arquivo.save('contratos.csv', ContentFile(b'id\n1\n'), save=True)

    _cliente().resource_create({'package_id': 'pkg'}, file_field='upload', arquivo=RecursoDados.objects.get(pk=recurso.pk).arquivo)

    assert [(e['campo'], e['conteudo']) for e in envios] == [('upload', b'id\n1\n')]
