"""Testes da sincronização de organizações com o CKAN."""

import os

import pytest
from django.core.files.base import ContentFile
from django.db.models.fields.files import FieldFile

from dados_abertos.models import Organizacao
from dados_abertos.services.ckan_service import sync_organization_with_ckan

# Cabeçalho de um PNG de 1x1 — basta ser reconhecível como imagem pelo ImageField.
PNG_MINIMO = (
    b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89'
    b'\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82'
)


class ClienteCKANFake:
    """Cliente CKAN em memória, registrando as chamadas feitas pelo serviço."""

    def __init__(self, resultado: dict | None = None):
        self.resultado = {'id': 'org-1'} if resultado is None else resultado
        self.criacoes: list[dict] = []
        self.atualizacoes: list[dict] = []

    def organization_create(self, data, *, imagem=None):
        self.criacoes.append({'data': data, 'imagem': imagem})
        return self.resultado

    def organization_update(self, data, *, imagem=None):
        self.atualizacoes.append({'data': data, 'imagem': imagem})
        return self.resultado


@pytest.fixture
def media_temporaria(settings, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path)
    return tmp_path


def _storage_sem_caminho_local(monkeypatch):
    """Simula o storage de produção (S3/MinIO), que não implementa ``path``.

    ``Storage.path`` é opcional por design: só faz sentido em sistema de arquivos. O
    backend remoto herda a implementação base, que levanta ``NotImplementedError``.
    ``open``/``exists`` continuam funcionando, e é por eles que o arquivo tem de ser lido.
    """

    def _sem_path(self):
        raise NotImplementedError("This backend doesn't support absolute paths.")

    monkeypatch.setattr(FieldFile, 'path', property(_sem_path))


def _instalar_cliente(monkeypatch, cliente):
    monkeypatch.setattr('dados_abertos.services.ckan_service.CKANClient', lambda **kwargs: cliente)


def _criar_organizacao(**campos):
    return Organizacao.objects.create(nome='ifrn', titulo='IFRN', **campos)


def _anexar_imagem(org):
    org.imagem.save('logo.png', ContentFile(PNG_MINIMO), save=True)
    return org


def _sincronizar(org):
    return sync_organization_with_ckan(Organizacao.objects.filter(pk=org.pk), 'https://ckan.exemplo.br', 'chave')


def _resultado_com_imagem(nome_remoto='2026-08-26-125357.123456logo.png'):
    """Resposta do CKAN após um upload aceito.

    O CKAN devolve em ``image_url`` apenas o **nome do arquivo**; a URL navegável
    vem em ``image_display_url``.
    """
    return {
        'id': 'org-1',
        'image_url': nome_remoto,
        'image_display_url': f'https://ckan.exemplo.br/uploads/group/{nome_remoto}',
    }


@pytest.mark.django_db
def test_envia_a_imagem_local_como_upload(media_temporaria, monkeypatch):
    """Organização com imagem local sobe o arquivo, em vez de mandar image_url."""
    cliente = ClienteCKANFake(resultado=_resultado_com_imagem())
    _instalar_cliente(monkeypatch, cliente)

    org = _anexar_imagem(_criar_organizacao(id_remoto='org-1'))

    assert _sincronizar(org) == (1, 0, [])
    assert len(cliente.atualizacoes) == 1
    # O storage do SUAP acrescenta um hash ao nome, então basta reconhecer o arquivo.
    nome = cliente.atualizacoes[0]['imagem'].name
    assert nome.endswith('.png'), nome
    assert 'logo' in nome, nome
    assert 'image_url' not in cliente.atualizacoes[0]['data'], 'com upload, image_url não deve ser enviado'


@pytest.mark.django_db
def test_usa_a_url_da_imagem_quando_nao_ha_arquivo_local(media_temporaria, monkeypatch):
    """Sem arquivo local, a URL informada é enviada como image_url."""
    cliente = ClienteCKANFake()
    _instalar_cliente(monkeypatch, cliente)

    org = _criar_organizacao(id_remoto='org-1', url_imagem='https://exemplo.br/logo.png')

    assert _sincronizar(org) == (1, 0, [])
    assert cliente.atualizacoes[0]['imagem'] is None
    assert cliente.atualizacoes[0]['data']['image_url'] == 'https://exemplo.br/logo.png'


@pytest.mark.django_db
def test_guarda_a_url_navegavel_apos_o_upload(media_temporaria, monkeypatch):
    """Após o upload, url_imagem recebe a URL de exibição — não o nome do arquivo.

    ``url_imagem`` é um ``URLField``; gravar ali o ``image_url`` cru (que o CKAN
    devolve como nome de arquivo) envenena a próxima sincronização, que passaria a
    mandar esse nome como se fosse uma URL.
    """
    cliente = ClienteCKANFake(resultado=_resultado_com_imagem())
    _instalar_cliente(monkeypatch, cliente)

    org = _anexar_imagem(_criar_organizacao(id_remoto='org-1'))

    assert _sincronizar(org) == (1, 0, [])
    assert Organizacao.objects.get(pk=org.pk).url_imagem == 'https://ckan.exemplo.br/uploads/group/2026-08-26-125357.123456logo.png'


@pytest.mark.django_db
def test_envia_a_imagem_com_storage_que_nao_expoe_caminho_local(media_temporaria, monkeypatch):
    """Em produção a mídia mora no S3/MinIO, e a sincronização precisa funcionar lá.

    Ler o arquivo por ``FieldFile.path`` amarra a sincronização ao storage de sistema de
    arquivos: no backend remoto o ``path`` levanta ``NotImplementedError`` e nenhuma
    organização com imagem anexada consegue ser sincronizada. O arquivo tem de ser lido
    pelo storage, que é o mesmo nos dois ambientes.
    """
    cliente = ClienteCKANFake(resultado=_resultado_com_imagem())
    _instalar_cliente(monkeypatch, cliente)

    org = _anexar_imagem(_criar_organizacao(id_remoto='org-1'))
    _storage_sem_caminho_local(monkeypatch)

    assert _sincronizar(org) == (1, 0, [])
    assert cliente.atualizacoes[0]['imagem'].read() == PNG_MINIMO


@pytest.mark.django_db
def test_relata_erro_quando_o_ckan_ignora_a_imagem_enviada(media_temporaria, monkeypatch):
    """Upload aceito mas descartado pelo CKAN não pode ser reportado como sucesso.

    É o sintoma que motivou estes testes: o ``organization_patch`` responde 200, a
    organização é atualizada em todos os outros campos e a imagem simplesmente não
    aparece — sem nenhum aviso ao usuário.
    """
    cliente = ClienteCKANFake(resultado={'id': 'org-1', 'image_url': '', 'image_display_url': ''})
    _instalar_cliente(monkeypatch, cliente)

    org = _anexar_imagem(_criar_organizacao(id_remoto='org-1'))

    sucessos, erros, mensagens = _sincronizar(org)

    assert (sucessos, erros) == (0, 1)
    assert any('imagem' in m.lower() for m in mensagens), mensagens


@pytest.mark.django_db
def test_preserva_o_id_remoto_quando_so_a_imagem_falha(media_temporaria, monkeypatch):
    """Falha de imagem não pode descartar o que o CKAN já confirmou.

    Numa primeira sincronização o ``organization_create`` cria a organização lá e
    devolve o ``id``. Se a cobrança da imagem interrompesse a gravação, o
    ``id_remoto`` se perderia e a sincronização seguinte tentaria criar a mesma
    organização de novo — colidindo com o nome já existente no CKAN.
    """
    cliente = ClienteCKANFake(resultado={'id': 'org-1', 'image_url': '', 'image_display_url': ''})
    _instalar_cliente(monkeypatch, cliente)

    org = _anexar_imagem(_criar_organizacao())

    sucessos, erros, _mensagens = _sincronizar(org)

    assert (sucessos, erros) == (0, 1)
    assert len(cliente.criacoes) == 1
    gravada = Organizacao.objects.get(pk=org.pk)
    assert gravada.id_remoto == 'org-1', 'o id devolvido pelo CKAN precisa sobreviver ao erro de imagem'
    assert gravada.sincronizado_em is None, 'sincronização com imagem faltando não pode ser carimbada como concluída'


@pytest.mark.django_db
def test_relata_erro_quando_o_arquivo_da_imagem_sumiu_do_storage(media_temporaria, monkeypatch):
    """Registro aponta para um arquivo que não existe mais — o erro precisa dizer isso.

    Sem conferir o arquivo no storage, quem falha é o ``open()`` lá dentro do cliente, e o
    erro cru não menciona imagem alguma.
    """
    cliente = ClienteCKANFake()
    _instalar_cliente(monkeypatch, cliente)

    org = _anexar_imagem(_criar_organizacao(id_remoto='org-1'))
    os.remove(org.imagem.path)

    sucessos, erros, mensagens = _sincronizar(org)

    assert (sucessos, erros) == (0, 1)
    assert any('imagem' in m.lower() for m in mensagens), mensagens
    assert cliente.atualizacoes == []


@pytest.mark.django_db
def test_nao_reenvia_como_url_um_url_imagem_que_nao_e_url(media_temporaria, monkeypatch):
    """Organização com ``url_imagem`` envenenado não propaga o valor ao CKAN.

    Antes da correção, um upload bem-sucedido gravava em ``url_imagem`` o nome do
    arquivo devolvido pelo CKAN. Os registros que passaram por aquele código carregam
    esse lixo, e reenviá-lo como ``image_url`` só espalharia o estrago.
    """
    cliente = ClienteCKANFake()
    _instalar_cliente(monkeypatch, cliente)

    org = _criar_organizacao(id_remoto='org-1', url_imagem='2026-08-26-125357.123456logo.png')

    assert _sincronizar(org) == (1, 0, [])
    assert cliente.atualizacoes[0]['data']['image_url'] is None


@pytest.mark.django_db
def test_cria_a_organizacao_enviando_a_imagem(media_temporaria, monkeypatch):
    """Caminho feliz da primeira sincronização: cria no CKAN já com a imagem.

    Os demais testes de sucesso partem de ``id_remoto`` preenchido, ou seja, do
    ``organization_patch``. O cenário que motivou a correção também passa pelo
    ``organization_create``, e sem este teste o caminho de criação só era exercitado
    pela variante de erro.
    """
    cliente = ClienteCKANFake(resultado=_resultado_com_imagem())
    _instalar_cliente(monkeypatch, cliente)

    org = _anexar_imagem(_criar_organizacao())

    assert _sincronizar(org) == (1, 0, [])
    assert len(cliente.criacoes) == 1
    assert cliente.criacoes[0]['imagem'].name.endswith('.png')

    gravada = Organizacao.objects.get(pk=org.pk)
    assert gravada.id_remoto == 'org-1'
    assert gravada.url_imagem == 'https://ckan.exemplo.br/uploads/group/2026-08-26-125357.123456logo.png'
    assert gravada.sincronizado_em is not None


@pytest.mark.django_db
def test_aceita_o_upload_quando_o_ckan_devolve_so_o_nome_do_arquivo(media_temporaria, monkeypatch):
    """Imagem registrada é imagem registrada, mesmo sem ``image_display_url`` na resposta.

    O ``group_dictize`` do CKAN 2.11.5 sempre deriva ``image_display_url`` de
    ``image_url``, mas amarrar a detecção a esse campo tornaria a checagem refém de um
    detalhe de serialização. Os dois vazios significam uma coisa só: nada registrado.
    Como o nome do arquivo não é uma URL, ele não pode ir para o ``url_imagem``.
    """
    cliente = ClienteCKANFake(resultado={'id': 'org-1', 'image_url': '2026-08-26-125357.123456logo.png'})
    _instalar_cliente(monkeypatch, cliente)

    org = _anexar_imagem(_criar_organizacao(id_remoto='org-1'))

    assert _sincronizar(org) == (1, 0, [])
    gravada = Organizacao.objects.get(pk=org.pk)
    assert gravada.url_imagem == '', 'nome de arquivo não é URL e não pode ser gravado no URLField'
    assert gravada.sincronizado_em is not None
