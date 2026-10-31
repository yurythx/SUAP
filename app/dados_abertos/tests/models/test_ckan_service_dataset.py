"""Testes dos metadados DCAT-BR enviados ao CKAN na sincronização do conjunto de dados."""

import datetime

import pytest

from dados_abertos.ckan_client import CKANError
from dados_abertos.enums import CoberturaEspacial, ObservanciaLegal, Periodicidade
from dados_abertos.models import BaseDados
from dados_abertos.services.ckan_service import sync_dataset_with_ckan
from dados_abertos.services.metadados import payload_dataset
from dados_abertos.tests.factories import BaseDadosFactory, LicencaFactory, PDABaseDadosFactory


class ClienteCKANFake:
    """Cliente CKAN em memória, registrando criações e patches de package."""

    def __init__(self, remoto: dict | None = None):
        self.remoto = remoto
        self.criacoes: list[dict] = []
        self.patches: list[dict] = []

    def package_show(self, key):
        if self.remoto is None:
            raise CKANError('404 Not found')
        return self.remoto

    def package_create(self, payload):
        self.criacoes.append(payload)
        return {'id': 'pkg-novo'}

    def package_update(self, payload):
        self.patches.append(payload)
        return payload


def _sincronizar(base, cliente, monkeypatch):
    monkeypatch.setattr('dados_abertos.services.ckan_service.CKANClient', lambda **kwargs: cliente)
    return sync_dataset_with_ckan(BaseDados.objects.filter(pk=base.pk), 'https://ckan.exemplo.br', 'chave')


@pytest.fixture
def base(db):
    base = BaseDadosFactory(
        licenca=LicencaFactory(codigo_ckan='cc-by'),
        autor='Diretoria de Gestão de Atividades Estudantis',
        autor_email='diae@ifrn.edu.br',
        versao='1.0',
        cobertura_espacial=CoberturaEspacial.ESTADUAL,
        valor_cobertura_espacial='RN',
        cobertura_temporal_inicio=datetime.date(2025, 1, 1),
        observancia_legal=ObservanciaLegal.PUBLICO,
        ods=[10, 4],
        extras={'fonte': 'SUAP', 'coberturaEspacial': 'NACIONAL'},
    )
    PDABaseDadosFactory(base_dados=base, frequencia_atualizacao=Periodicidade.ANUAL)
    PDABaseDadosFactory(base_dados=base, frequencia_atualizacao=Periodicidade.MENSAL)
    return base


@pytest.mark.django_db
def test_cria_o_conjunto_com_os_metadados_dcat_br(base, monkeypatch):
    cliente = ClienteCKANFake()

    assert _sincronizar(base, cliente, monkeypatch) == (1, 0)

    [criado] = cliente.criacoes
    assert criado['license_id'] == 'cc-by'
    assert (criado['author'], criado['author_email'], criado['version']) == (
        'Diretoria de Gestão de Atividades Estudantis',
        'diae@ifrn.edu.br',
        '1.0',
    )
    extras = {e['key']: e['value'] for e in criado['extras']}
    assert extras == {
        # Vale a promessa mais curta entre os PDAs da base.
        'periodicidade': 'MENSAL',
        'idioma': 'pt-BR',
        # O campo validado prevalece sobre a chave homônima digitada no JSON livre.
        'coberturaEspacial': 'ESTADUAL',
        'valorCoberturaEspacial': 'RN',
        'coberturaTemporalInicio': '2025-01-01',
        'observanciaLegal': 'PÚBLICO',
        'ods': '4 - Educação de Qualidade; 10 - Redução das Desigualdades',
        'dadosGenero': 'false',
        'dadosRacaEtnia': 'false',
        'fonte': 'SUAP',
    }


@pytest.mark.django_db
def test_atualiza_no_ckan_so_o_metadado_alterado(base, monkeypatch):
    remoto = {**payload_dataset(base), 'id': 'pkg-1', 'state': 'active', 'license_id': 'other-open'}
    cliente = ClienteCKANFake(remoto=remoto)

    _sincronizar(base, cliente, monkeypatch)

    assert cliente.patches == [{'id': 'pkg-1', 'license_id': 'cc-by'}]


@pytest.mark.django_db
def test_metadado_vazio_no_suap_nao_apaga_o_que_esta_no_ckan(monkeypatch):
    # Licença cadastrada antes do código CKAN existir: não pode limpar a licença publicada.
    base = BaseDadosFactory(licenca=LicencaFactory(codigo_ckan=''), versao='')
    remoto = {**payload_dataset(base), 'id': 'pkg-1', 'state': 'active', 'license_id': 'cc-by', 'author': 'DIGAE', 'version': '2.0'}
    cliente = ClienteCKANFake(remoto=remoto)

    _sincronizar(base, cliente, monkeypatch)

    assert cliente.patches == []
