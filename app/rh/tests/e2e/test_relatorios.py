"""Relatórios, cadastros de consulta e permissões RH: detecta erro de renderização e exposição indevida.

Smoke usa a sessão real do navegador; status HTTP e texto distintivo provam resposta positiva.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date

import pytest
from playwright.sync_api import Page

from djtools.e2e_ui import Tela

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

RELATORIOS = [
    ('/rh/', 'Indicadores'),
    ('/rh/servidores_sem_setor_suap/', 'Servidores sem Setor SUAP'),
    ('/rh/servidores_sem_cargo/', 'Servidores sem Cargo'),
    ('/rh/tela_recursos_humanos/', 'Sexo'),
    ('/rh/tela_servidores_com_funcao/', 'Lista de Servidores com Função'),
    ('/rh/servidor/buscar/', 'Buscar servidores'),
    ('/rh/servidores_capacitacao_setor/', 'Dados dos Servidores para concessão de capacitação Strictu Sensu'),
    ('/rh/aniversariantes/', 'Aniversariantes do Mês'),
    ('/rh/enderecos/', 'Relação de Endereços'),
    ('/rh/enderecos_fora_do_estado/', 'Servidores com endereço fora do'),
    ('/rh/quadro_referencia/', 'Quadro de referência'),
    ('/rh/afastamentos_servidores/', 'Afastamentos dos Servidores'),
    ('/rh/relatorio_afastamentos_saude/', 'Relatório de afastamentos por motivo de saúde'),
    ('/rh/setor_jornada_historico_pendencias/', 'Setores com pendências em Histórico de Jornadas de Trabalho'),
    ('/rh/viagens_consolidadas/', 'Relatório de Viagens Consolidadas'),
    ('/rh/viagens_consolidadas_detalhamento/{ano}/0/todos/', 'Detalhamento do Relatório de Viagens Consolidadas'),
    ('/rh/disciplina_ingresso_docentes/', 'Docentes por Disciplina de Ingresso'),
    ('/rh/organograma/', 'Organograma'),
    ('/rh/servidores_por_area/', 'Servidores por Área'),
    ('/rh/importar_servidor/', 'Importar/Atualizar dados do servidor'),
]


@pytest.mark.parametrize(('url', 'texto'), RELATORIOS)
def test_relatorios_rh(logado_rh: Callable[[str], Page], url: str, texto: str) -> None:
    tela = Tela(logado_rh('sistemico'))
    resposta = tela.buscar(url.format(ano=date.today().year))
    assert resposta.status == 200, f'{url}: HTTP {resposta.status}: {resposta.text()[:1000]}'
    assert texto in resposta.text(), f'{url}: conteúdo de relatório ausente'


@pytest.mark.parametrize(
    ('papel', 'url', 'status'),
    [
        ('servidor', '/rh/', 403),
        ('servidor', '/rh/servidor/buscar/', 403),
        ('servidor', '/rh/importacao_siape/', 403),
        ('servidor', '/rh/organograma/', 200),
        ('campus', '/rh/servidor/buscar/', 200),
        ('campus', '/rh/importacao_siape/', 403),
        ('campus', '/rh/', 403),
        ('auditor', '/rh/servidor/buscar/', 200),
        ('auditor', '/rh/importacao_siape/', 403),
        ('sistemico', '/rh/importacao_siape/', 200),
        ('saude', '/rh/servidor/buscar/', 403),
        ('saude', '/admin/rh/acaosaude/', 200),
    ],
)
def test_permissoes_por_papel(logado_rh: Callable[[str], Page], papel: str, url: str, status: int) -> None:
    tela = Tela(logado_rh(papel))
    assert tela.buscar(url).status == status


def test_enderecos_fora_do_estado(logado_rh: Callable[[str], Page]) -> None:
    tela = Tela(logado_rh('sistemico'))
    from comum.models import Configuracao
    from comum.tests.factories import MunicipioFactory, PessoaEnderecoFactory
    from rh.tests.factories import ServidorFactory
    from uuid import uuid4

    Configuracao.objects.update_or_create(app='comum', chave='instituicao_estado', defaults={'valor': 'RN'})
    tag = uuid4().hex[:10]
    fora = ServidorFactory(matricula=str(int(uuid4().hex[:8], 16)), pessoa_fisica__nome='Fora RN ' + tag)
    dentro = ServidorFactory(matricula=str(int(uuid4().hex[:8], 16)), pessoa_fisica__nome='Dentro RN ' + tag)
    inativo = ServidorFactory(matricula=str(int(uuid4().hex[:8], 16)), pessoa_fisica__nome='Inativo PB ' + tag, ativo=False)
    municipio = MunicipioFactory(uf='PB')
    PessoaEnderecoFactory(pessoa=fora.pessoa_fisica, municipio=municipio)
    PessoaEnderecoFactory(pessoa=dentro.pessoa_fisica, municipio=MunicipioFactory(uf='RN'))
    PessoaEnderecoFactory(pessoa=inativo.pessoa_fisica, municipio=municipio)
    resposta = tela.buscar('/rh/enderecos_fora_do_estado/')
    assert resposta.status == 200
    html = resposta.text()
    assert fora.nome in html
    assert municipio.nome in html
    assert dentro.nome not in html
    assert inativo.nome not in html
