"""Roteiros executáveis de geração do manual de Contratos."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from datetime import date

import pytest
from playwright.sync_api import Page, expect

from djtools.e2e_ui import Tela
from contratos.models import Contrato
from contratos.tests.doc.conftest import DadosContratos

Capturar = Callable[[Page, str], Path]

pytestmark = [pytest.mark.doc, pytest.mark.e2e]


def test_01_cadastrar_contrato(contratos_doc_seed: DadosContratos, logado: Callable[[str], Page], capturar: Capturar) -> None:
    pagina = logado('159601')
    tela = Tela(pagina)
    tela.ir('/contratos/redirect_contratos/')
    expect(pagina.get_by_role('link', name='Adicionar Contrato', exact=True)).to_be_visible()
    capturar(pagina, 'contratos-listagem')
    tela.clicar_botao('Adicionar Contrato')
    expect(pagina.locator('#contrato_form')).to_be_visible()
    ano = date.today().year
    tela.preencher_formulario(
        [
            ('Número', 'texto', f'90001/{ano}'),
            ('Valor', 'texto', '12.000,00'),
            ('Data de Início', 'data', f'01/01/{ano}'),
            ('Data de Término', 'data', f'31/12/{ano}'),
            ('Objeto de Contrato', 'textarea', 'Manutenção predial de demonstração'),
            ('Processo', 'autocomplete', contratos_doc_seed['processo'].numero_processo),
            ('Campus Gerenciador', 'autocomplete', 'DOCCT'),
            ('Campi Atendidos', 'filteredselectmultiple', 'DOCCT'),
            ('Contratada', 'autocomplete', contratos_doc_seed['contratada'].cnpj),
            ('Quantidade de Parcelas', 'texto', '2'),
            ('Tipo', 'lista', 'Contrato'),
            ('Subtipo', 'lista', 'Serviço de manutenção'),
            ('Continuidade', 'lista', 'Contínuo'),
            ('Natureza', 'lista', 'Despesa'),
            ('Possui dedicação de mão de obra exclusiva?', 'lista', 'Não'),
            ('Tipo de Licitação', 'lista', 'Convite'),
            ('Licitação/Ano/UASG da Licitação', 'texto', f'00001/{ano} (999001)'),
            ('Base Legal', 'lista', 'Base legal de demonstração'),
            ('Arquivo do Contrato', 'arquivo', 'pdf'),
        ]
    )
    capturar(pagina, 'contrato-cadastro')
    tela.clicar_botao('Salvar')
    tela.sucesso('Cadastro realizado com sucesso.')
    contrato = Contrato.objects.get(numero=f'90001/{ano}')
    tela.ir(f'/contratos/contrato/{contrato.pk}/')
    capturar(pagina, 'contrato-detalhamento')


def contrato_documentado() -> Contrato:
    return Contrato.objects.get(numero=f'90001/{date.today().year}')


def test_02_cronograma_e_parcelas(contratos_doc_seed: DadosContratos, logado: Callable[[str], Page], capturar: Capturar) -> None:
    pagina = logado('159601')
    tela = Tela(pagina)
    contrato = contrato_documentado()
    tela.ir(f'/contratos/contrato/{contrato.pk}/')
    tela.clicar_aba('Cronograma')
    tela.clicar_botao('Criar Cronograma')
    popup = tela.popup()
    popup.preencher('Número do Cronograma', 'texto', '1')
    capturar(pagina, 'cronograma-numero')
    popup.clicar_botao('Salvar')
    tela.sucesso('Número de cronograma definido com sucesso. As parcelas necessitam ser geradas.')
    tela.clicar_aba('Cronograma')
    tela.clicar_botao('Gerar Várias Parcelas')
    capturar(pagina, 'cronograma-gerar-parcelas')
    tela.clicar_botao('Gerar Parcelas')
    tela.sucesso('Parcelas geradas com sucesso.')
    tela.clicar_aba('Cronograma')
    expect(pagina.get_by_text('6.000,00', exact=False).first).to_be_visible()
    capturar(pagina, 'cronograma-parcelas')


def test_03_designar_fiscal(contratos_doc_seed: DadosContratos, logado: Callable[[str], Page], capturar: Capturar) -> None:
    pagina = logado('159601')
    tela = Tela(pagina)
    contrato = contrato_documentado()
    tela.ir(f'/contratos/contrato/{contrato.pk}/')
    tela.clicar_aba('Fiscais')
    tela.clicar_botao('Adicionar Fiscal')
    popup = tela.popup()
    ano = date.today().year
    popup.preencher_formulario(
        [
            ('Tipo', 'lista', 'Titular'),
            ('Portaria', 'texto', f'01/{ano}'),
            ('Data da Nomeação', 'data', f'01/01/{ano}'),
            ('Data Final da Vigência', 'data', f'31/12/{ano}'),
            ('Servidor', 'autocomplete', 'Carlos Fiscal'),
            ('Campus', 'autocomplete', 'DOCCT'),
        ]
    )
    capturar(pagina, 'fiscal-cadastro')
    popup.clicar_botao('Salvar')
    tela.sucesso('Fiscal adicionado com sucesso.')
    tela.clicar_aba('Fiscais')
    expect(pagina.get_by_text('Carlos Fiscal', exact=False).first).to_be_visible()
    capturar(pagina, 'fiscais')


def test_04_vincular_empenho(contratos_doc_seed: DadosContratos, logado: Callable[[str], Page], capturar: Capturar) -> None:
    pagina = logado('159601')
    tela = Tela(pagina)
    contrato = contrato_documentado()
    tela.ir(f'/contratos/contrato/{contrato.pk}/')
    tela.clicar_aba('Empenho')
    tela.clicar_botao('Adicionar Empenho')
    popup = tela.popup()
    popup.preencher('Nota de Empenho', 'autocomplete', contratos_doc_seed['empenho'].numero)
    capturar(pagina, 'empenho-cadastro')
    popup.clicar_botao('Salvar')
    tela.sucesso('Empenho adicionado com sucesso.')
    tela.clicar_aba('Empenho')
    expect(pagina.get_by_text(contratos_doc_seed['empenho'].numero, exact=False).first).to_be_visible()
    capturar(pagina, 'empenhos')


def test_05_medir_parcela(contratos_doc_seed: DadosContratos, logado: Callable[[str], Page], capturar: Capturar) -> None:
    pagina = logado('159602')
    tela = Tela(pagina)
    contrato = contrato_documentado()
    tela.ir(f'/contratos/contrato/{contrato.pk}/')
    tela.clicar_aba('Cronograma')
    pagina.get_by_role('link', name='Efetuar Medição', exact=True).first.click()
    popup = tela.popup()
    popup.preencher('Nº do Documento', 'texto', 'NF-90001')
    popup.preencher('Arquivo da Medição', 'arquivo', 'pdf')
    popup.preencher('Processo', 'autocomplete', contratos_doc_seed['processo'].numero_processo)
    popup.preencher('Campus', 'autocomplete', 'DOCCT')
    popup.preencher('Nota de Empenho', 'autocomplete', contratos_doc_seed['empenho'].numero)
    popup.preencher('Valor', 'texto', '6.000,00')
    capturar(pagina, 'medicao-formulario')
    popup.clicar_botao('Salvar')
    tela.sucesso('Medição realizada com sucesso.')
    tela.clicar_aba('Cronograma')
    expect(pagina.get_by_text('NF-90001', exact=False).first).to_be_visible()
    capturar(pagina, 'medicao-registrada')


def test_06_consulta_publica(contratos_doc_seed: DadosContratos, page: Page, capturar: Capturar) -> None:
    tela = Tela(page)
    tela.ir('/contratos/listar_contratos/')
    expect(page.locator('h2').first).to_be_visible()
    capturar(page, 'contratos-publicos')
    contrato = contrato_documentado()
    page.get_by_role('link', name=contrato.numero, exact=True).click()
    expect(page.locator('h2').first).to_contain_text(contrato.numero)
    capturar(page, 'contrato-publico')


@pytest.mark.parametrize(
    ('rota', 'slug'),
    [
        ('indicadores', 'indicadores'),
        ('rol_responsabilidade_fiscais', 'responsabilidades-fiscais'),
        ('visualizar_fiscais', 'consulta-fiscais'),
        ('pendencias', 'notificar-pendencias'),
        ('contratos_a_serem_aditivados', 'relatorio-aditivos'),
        ('contratos_a_serem_licitados', 'relatorio-licitacoes'),
        ('relatorio_consumo_energia', 'relatorio-energia'),
        ('relatorio_terceirizados', 'relatorio-terceirizados'),
        ('relatorio_empenhos', 'relatorio-empenhos'),
        ('relatorio_pendencias', 'relatorio-pendencias'),
        ('situacao_contratos', 'situacao-contratos'),
    ],
)
def test_07_consultas_e_relatorios(
    contratos_doc_seed: DadosContratos, logado: Callable[[str], Page], capturar: Capturar, rota: str, slug: str
) -> None:
    pagina = logado('159601')
    resposta = pagina.goto(f'/contratos/{rota}/')
    assert resposta.status == 200
    expect(pagina.locator('h2').first).to_be_visible()
    _filtrar_relatorio(tela=Tela(pagina), rota=rota)
    expect(pagina.locator('h2').first).to_be_visible()
    capturar(pagina, slug)


def _filtrar_relatorio(tela: Tela, rota: str) -> None:
    if rota == 'visualizar_fiscais':
        tela.preencher('Campus', 'lista', 'DOCCT')
        tela.preencher('Matrícula do Servidor', 'texto', '159602')
        tela.clicar_botao('Buscar')
        expect(tela.pagina.get_by_text('Carlos Fiscal', exact=False).first).to_be_visible()
    elif rota in ('pendencias', 'relatorio_pendencias'):
        tela.preencher('Filtrar por Campus', 'lista', 'DOCCT')
        tela.clicar_botao('Enviar')
    elif rota == 'situacao_contratos':
        ano = date.today().year
        tela.preencher_formulario([('Campus', 'lista', 'DOCCT'), ('Data inicial', 'data', f'01/01/{ano}'), ('Data final', 'data', f'31/12/{ano}')])
        tela.clicar_botao('Enviar')
    elif rota == 'relatorio_consumo_energia':
        tela.preencher('Filtrar por Campus', 'autocomplete', 'DOCCT')
        tela.preencher('Ano', 'lista', str(date.today().year))
        tela.clicar_botao('Enviar')
    elif rota == 'indicadores':
        tela.preencher('Filtrar por Campus', 'lista', 'DOCCT')
        tela.preencher('Filtrar por Ano', 'lista', str(date.today().year))
        tela.clicar_botao('Buscar')
        # Highcharts anima as barras após o DOM ficar pronto: a captura anterior mostrou barras incompletas.
        tela.pagina.wait_for_timeout(1200)
    elif rota == 'relatorio_terceirizados':
        tela.preencher('Filtrar por Campus', 'autocomplete', 'DOCCT')
        tela.clicar_botao('Enviar')


def test_08_exportar_contratos(contratos_doc_seed: DadosContratos, logado: Callable[[str], Page], capturar: Capturar, tmp_path: Path) -> None:
    pagina = logado('159601')
    tela = Tela(pagina)
    tela.ir('/contratos/exportacao/')
    tela.preencher('Tipo do Contrato', 'autocomplete', 'Contrato')
    tela.preencher('Campi', 'filteredselectmultiple', 'DOCCT')
    capturar(pagina, 'exportacao')
    tela.clicar_botao('Enviar')
    expect(pagina.get_by_role('link', name='Continuar', exact=True)).to_be_visible()
    capturar(pagina, 'exportacao-resultado')
    with pagina.expect_download() as transferencia:
        pagina.get_by_role('link', name='Continuar', exact=True).click()
    arquivo = transferencia.value
    assert arquivo.failure() is None
    destino = tmp_path / arquivo.suggested_filename
    arquivo.save_as(destino)
    assert destino.stat().st_size > 0


def test_09_consultar_contrato(contratos_doc_seed: DadosContratos, logado: Callable[[str], Page], capturar: Capturar) -> None:
    pagina = logado('159601')
    tela = Tela(pagina)
    contrato = contrato_documentado()
    tela.ir('/contratos/redirect_contratos/')
    tela.linha(contrato.numero).clicar_icone('exibição')
    expect(pagina.locator('h2').first).to_contain_text(contrato.numero)
    expect(pagina.get_by_text('Manutenção predial de demonstração', exact=True)).to_be_visible()
    capturar(pagina, 'contrato-consulta')
