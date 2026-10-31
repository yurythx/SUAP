"""Testes da sincronização de recursos com o CKAN."""

import datetime

import pytest
from django.core.files.base import ContentFile
from django.db.models.fields.files import FieldFile
from django.utils import timezone

from dados_abertos.ckan_client import CKANError
from dados_abertos.enums import FormatoRecurso
from dados_abertos.models import BaseDados, RecursoDados
from dados_abertos.services.ckan_service import sync_resource_with_ckan


class ClienteCKANFake:
    """Cliente CKAN em memória, registrando as chamadas feitas pelo serviço."""

    def __init__(self, remoto: dict | None = None, recursos_do_dataset: list | None = None):
        self.remoto = remoto
        self.recursos_do_dataset = recursos_do_dataset or []
        self.atualizacoes: list[dict] = []
        self.criacoes: list[dict] = []

    def resource_show(self, resource_id):
        if self.remoto is None:
            raise CKANError('404 Not found')
        return self.remoto

    def package_resources(self, dataset_key):
        return self.recursos_do_dataset

    def resource_update(self, payload, *, file_field=None, arquivo=None):
        self.atualizacoes.append({'payload': payload, 'file_field': file_field, 'arquivo': arquivo})
        return {'id': payload.get('id')}

    def resource_create(self, payload, *, file_field=None, arquivo=None):
        self.criacoes.append({'payload': payload, 'file_field': file_field, 'arquivo': arquivo})
        return {'id': 'res-novo'}


@pytest.fixture
def media_temporaria(settings, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path)
    return tmp_path


@pytest.fixture
def base(db):
    return BaseDados.objects.create(nome='contratos', titulo='Contratos', id_remoto='pkg-1')


def _storage_sem_caminho_local(monkeypatch):
    """Simula o storage de produção (S3/MinIO), que não implementa ``path``."""

    def _sem_path(self):
        raise NotImplementedError("This backend doesn't support absolute paths.")

    monkeypatch.setattr(FieldFile, 'path', property(_sem_path))


def _instalar_cliente(monkeypatch, cliente):
    monkeypatch.setattr('dados_abertos.services.ckan_service.CKANClient', lambda **kwargs: cliente)


def _criar_recurso_upload(base, conteudo=b'id,valor\n1,10\n', **campos):
    recurso = RecursoDados(dataset=base, nome='Contratos 2026', descricao='Contratos vigentes', formato=FormatoRecurso.CSV, **campos)
    recurso.arquivo.save('contratos.csv', ContentFile(conteudo), save=False)
    recurso.save()
    return recurso


def _marcar_sincronizado(recurso, *, ha_dias=0):
    """Define ``sincronizado_em`` sem tocar em ``data_atualizacao`` (que é ``auto_now``)."""
    RecursoDados.objects.filter(pk=recurso.pk).update(sincronizado_em=timezone.now() - datetime.timedelta(days=ha_dias))
    return RecursoDados.objects.get(pk=recurso.pk)


def _remoto_equivalente(recurso: RecursoDados) -> dict:
    """Espelho remoto com os mesmos metadados do recurso local (ou seja: sem diffs)."""
    return {
        'id': recurso.id_remoto,
        'name': recurso.nome,
        'description': recurso.descricao,
        'format': recurso.formato,
        'url_type': 'upload',
    }


def _sincronizar(recurso):
    return sync_resource_with_ckan(RecursoDados.objects.filter(pk=recurso.pk), 'https://ckan.exemplo.br', 'chave')


@pytest.mark.django_db
def test_cria_recurso_de_link_sem_enviar_arquivo(base, media_temporaria, monkeypatch):
    """Recurso só com URL e ainda inexistente no CKAN é criado como link, sem upload."""
    cliente = ClienteCKANFake(remoto=None)
    _instalar_cliente(monkeypatch, cliente)
    monkeypatch.setattr('dados_abertos.models.recurso_dados.RecursoDados._download_and_attach_file_from_url', lambda self: None)

    recurso = RecursoDados.objects.create(dataset=base, nome='Contratos 2026', formato=FormatoRecurso.CSV, url='https://exemplo.br/contratos.csv')

    assert _sincronizar(recurso) == (1, 0)
    assert len(cliente.criacoes) == 1
    assert cliente.criacoes[0]['file_field'] is None
    assert cliente.criacoes[0]['payload']['url'] == 'https://exemplo.br/contratos.csv'


@pytest.mark.django_db
def test_cria_recurso_de_upload_enviando_o_arquivo(base, media_temporaria, monkeypatch):
    """Recurso com arquivo local e ainda inexistente no CKAN é criado com upload multipart.

    Roda sob o storage de produção (S3/MinIO), que não implementa ``path``: ler o arquivo
    por ``FieldFile.path`` faria o upload funcionar só em desenvolvimento.
    """
    cliente = ClienteCKANFake(remoto=None)
    _instalar_cliente(monkeypatch, cliente)

    recurso = _criar_recurso_upload(base)
    _storage_sem_caminho_local(monkeypatch)

    assert _sincronizar(recurso) == (1, 0)
    assert len(cliente.criacoes) == 1
    assert cliente.criacoes[0]['file_field'] == 'upload'
    assert cliente.criacoes[0]['arquivo'].read() == b'id,valor\n1,10\n'
    assert RecursoDados.objects.get(pk=recurso.pk).id_remoto == 'res-novo'


@pytest.mark.django_db
def test_envia_no_patch_somente_o_metadado_alterado(base, media_temporaria, monkeypatch):
    """O patch carrega apenas o campo divergente — e o arquivo sobe junto.

    O reenvio do arquivo em qualquer divergência é o comportamento herdado: ``data_atualizacao`` é
    ``auto_now`` sobre a linha inteira, então não há como distinguir "trocou o arquivo" de "editou a
    descrição" sem um marcador próprio do arquivo.
    """
    recurso = _criar_recurso_upload(base, id_remoto='res-1')
    remoto = _remoto_equivalente(recurso)
    remoto['description'] = 'Descrição antiga'
    cliente = ClienteCKANFake(remoto=remoto)
    _instalar_cliente(monkeypatch, cliente)

    assert _sincronizar(recurso) == (1, 0)
    assert len(cliente.atualizacoes) == 1
    payload = cliente.atualizacoes[0]['payload']
    assert payload['description'] == 'Contratos vigentes'
    assert set(payload) == {'id', 'description'}, 'o patch não deve carregar campos inalterados'
    assert cliente.atualizacoes[0]['file_field'] == 'upload'


@pytest.mark.django_db
def test_nao_chama_o_ckan_quando_nada_mudou(base, media_temporaria, monkeypatch):
    """Recurso idêntico ao remoto e já sincronizado não gera chamada de atualização."""
    recurso = _criar_recurso_upload(base, id_remoto='res-1')
    recurso = _marcar_sincronizado(recurso)
    cliente = ClienteCKANFake(remoto=_remoto_equivalente(recurso))
    _instalar_cliente(monkeypatch, cliente)

    assert _sincronizar(recurso) == (1, 0)
    assert cliente.atualizacoes == []


@pytest.mark.django_db
def test_force_file_reenvia_mesmo_sem_nada_ter_mudado(base, media_temporaria, monkeypatch):
    """``force_file`` é a saída para quando o arquivo sumiu do CKAN sem o SUAP saber.

    O ``resource_show`` continua respondendo (o metadado remoto sobrevive), os metadados batem e
    o recurso local não mudou — pela regra normal não há o que sincronizar. Só o reenvio forçado
    repõe o conteúdo.
    """
    recurso = _criar_recurso_upload(base, id_remoto='res-1')
    recurso = _marcar_sincronizado(recurso)
    cliente = ClienteCKANFake(remoto=_remoto_equivalente(recurso))
    _instalar_cliente(monkeypatch, cliente)

    assert _sincronizar(recurso) == (1, 0), 'sem force_file o serviço deveria considerar tudo em dia'
    assert cliente.atualizacoes == [], 'pré-condição do teste quebrada: houve envio sem force_file'

    resultado = sync_resource_with_ckan(RecursoDados.objects.filter(pk=recurso.pk), 'https://ckan.exemplo.br', 'chave', force_file=True)

    assert resultado == (1, 0)
    assert cliente.atualizacoes, 'force_file não reenviou o arquivo'
    assert cliente.atualizacoes[0]['file_field'] == 'upload'


@pytest.mark.django_db
def test_reenvia_o_arquivo_quando_so_o_conteudo_muda(base, media_temporaria, monkeypatch):
    """Substituir apenas o arquivo, sem alterar metadados, deve reenviar o conteúdo ao CKAN.

    O recurso é marcado como sincronizado **depois** de criado, para que a única alteração
    posterior seja a troca do arquivo — sem isso o teste passaria mesmo sem a troca, e não provaria
    que ela é o gatilho do reenvio.
    """
    recurso = _criar_recurso_upload(base, id_remoto='res-1')
    recurso = _marcar_sincronizado(recurso)
    cliente = ClienteCKANFake(remoto=_remoto_equivalente(recurso))
    _instalar_cliente(monkeypatch, cliente)

    recurso.arquivo.save('contratos.csv', ContentFile(b'id,valor\n1,99\n'), save=True)

    assert _sincronizar(recurso) == (1, 0)
    assert cliente.atualizacoes, 'nenhuma atualização enviada ao CKAN'
    assert cliente.atualizacoes[0]['file_field'] == 'upload'
