"""Testes do cadastro de recurso com a opção de gerar o espelho em CSV."""

import json

import pytest
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile

from dados_abertos.enums import FormatoRecurso
from dados_abertos.forms import RecursoDadosForm
from dados_abertos.models import BaseDados, RecursoDados

REGISTROS = json.dumps([{'numero': '2026/001', 'objeto': 'Manutenção'}]).encode()


@pytest.fixture
def media_temporaria(settings, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path)
    return tmp_path


@pytest.fixture
def base(db, media_temporaria):
    return BaseDados.objects.create(nome='contratos', titulo='Contratos')


def _dados(base, formato=FormatoRecurso.JSON, gerar=True):
    return {'dataset': base.pk, 'nome': 'Contratos', 'descricao': '', 'formato': formato, 'url': '', 'mimetype': '', 'gerar_csv': gerar}


def test_marcar_a_opcao_cria_o_gemeo_em_csv(base):
    """O checkbox do formulário é o que dispara o espelho."""
    arquivos = {'arquivo': SimpleUploadedFile('contratos.json', REGISTROS, content_type='application/json')}
    formulario = RecursoDadosForm(data=_dados(base), files=arquivos)

    assert formulario.is_valid(), formulario.errors
    recurso = formulario.save()

    espelho = recurso.derivados.first()
    assert espelho is not None
    assert espelho.formato == FormatoRecurso.CSV
    assert espelho.nome == 'Contratos (CSV)'


def test_espelho_so_faz_sentido_em_json(base):
    """Pedir espelho CSV de um recurso que já é CSV é erro de preenchimento, não no-op silencioso."""
    arquivos = {'arquivo': SimpleUploadedFile('contratos.csv', b'numero\n1\n', content_type='text/csv')}
    formulario = RecursoDadosForm(data=_dados(base, formato=FormatoRecurso.CSV), files=arquivos)

    assert not formulario.is_valid()
    assert 'gerar_csv' in formulario.errors


def test_o_proprio_espelho_nao_oferece_a_opcao(base):
    """Espelho não gera espelho: no formulário dele o campo vem inerte."""
    origem = RecursoDados.objects.create(
        dataset=base, nome='Contratos', formato=FormatoRecurso.JSON, arquivo=ContentFile(REGISTROS, name='contratos.json')
    )
    espelho = RecursoDados.objects.create(
        dataset=base, nome='Contratos (CSV)', formato=FormatoRecurso.CSV, derivado_de=origem, arquivo=ContentFile(b'numero\n1\n', name='c.csv')
    )

    assert RecursoDadosForm(instance=espelho).fields['gerar_csv'].disabled


def test_a_tela_de_cadastro_abre_com_a_opcao(admin_client, base):
    """Guarda do fieldset: citar um campo que o formulário não tem quebra a página do admin."""
    resposta = admin_client.get('/admin/dados_abertos/recursodados/add/')

    assert resposta.status_code == 200
    assert 'gerar_csv' in resposta.content.decode()
