# ruff: noqa: UP032
"""Formulários de integração abrem sem chamar serviço externo; consultas próprias respeitam vínculo real."""

from __future__ import annotations

from collections.abc import Callable

import pytest
from playwright.sync_api import Page

from djtools.e2e_ui import Tela

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]


@pytest.mark.parametrize(
    ('papel', 'url', 'texto'),
    [
        ('auditor', '/rh/importar_pj/', 'Importador de Pessoa Jurídica'),
        ('almox', '/rh/importar_pessoajuridica/', 'Importar Pessoa Jurídica da base do CNPJ/RFB'),
        ('scdp', '/rh/diarias_passagens/importar_do_arquivo/', 'Importar Arquivo do SCDP'),
        ('avaliacao', '/rh/definir_areas_vinculacao/', 'Definir Áreas dos Setores'),
        ('avaliacao', '/rh/areas_vinculacao_setor/', 'Áreas de Vinculação dos Setores'),
        ('servidor', '/rh/indicadores_publicos/', 'Indicadores'),
    ],
)
def test_formularios_integracao(logado_rh: Callable[[str], Page], papel: str, url: str, texto: str) -> None:
    tela = Tela(logado_rh(papel))
    resposta = tela.buscar(url)
    assert resposta.status == 200, f'{url}: {resposta.text()[:1000]}'
    assert texto in resposta.text()


def test_consultas_proprias(logado_rh: Callable[[str], Page], rh_seed: dict) -> None:
    tela = Tela(logado_rh('servidor'))
    vinculo = rh_seed['servidor'].get_vinculo()
    for url, texto in [
        ('/rh/atualizar_dados_avaliador/', 'Atualizar Dados Pessoais'),
        ('/rh/pessoa_info_complementar/{}/'.format(vinculo.pk), 'Informações Complementares'),
        ('/rh/importar_dados_completares_pessoa/{}/'.format(vinculo.pk), 'Obter Informações Complementares'),
    ]:
        resposta = tela.buscar(url)
        assert resposta.status == 200, resposta.text()[:1000]
        assert texto in resposta.text()


def test_formularios_restritos(logado_rh: Callable[[str], Page], rh_seed: dict) -> None:
    servidor = rh_seed['servidor']
    for papel, url, texto in [
        ('digital', '/rh/editar_informacoes_digitais_fracas/{}/'.format(servidor.pessoa_fisica_id), 'Digitais Fracas'),
        ('sistemico', '/rh/editar_servidor_cargo_emprego_area/{}/'.format(servidor.pk), 'Editar Área do Cargo Emprego'),
    ]:
        resposta = Tela(logado_rh(papel)).buscar(url)
        assert resposta.status == 200, resposta.text()[:1000]
        assert texto in resposta.text()
