"""Docente: abre o processo de RSC, anexa e pontua comprovantes, salva o relatório e exclui o que não enviou.

A tela do processo grava tudo por AJAX (``salvar_processo_rsc``, ``salvar_arquivo_rsc``, os dois uploaders e as
exclusões): o teste dirige os botões da página, que mandam o token e o cabeçalho de AJAX que as views exigem,
e confere no banco o que cada gesto gravou.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from django.conf import settings
from playwright.sync_api import Page, Response, expect

from djtools.e2e_ui import ARQUIVOS, Tela

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

CRIAR = '/rsc/criar_processo_rsc/'
ABRIR = '/rsc/abrir_processo_rsc/{}/'
EXCLUIR = '/rsc/excluir_processo_rsc/{}/'
CLONAR = '/rsc/clonar_processo_rsc/{}/'
SALVAR = '/rsc/salvar_processo_rsc/{}/'
SALVAR_ARQUIVO = '/rsc/salvar_arquivo_rsc/{}/'
UPLOAD = '/rsc/rsc_upload/'
UPLOAD_PRELIMINAR = '/rsc/rsc_upload_documentos_exigidos/'
EXCLUIR_ARQUIVO = '/rsc/excluir_arquivo_pdf/{}/'
EXCLUIR_PRELIMINAR = '/rsc/excluir_arquivo_exigido_pdf/{}/'
PDF = str(Path(settings.BASE_DIR, ARQUIVOS['pdf']))


def test_docente_cria_processo(logado_rsc: Callable[[str], Page], rsc_seed: dict) -> None:
    from rsc.models import ProcessoRSC

    tela = Tela(logado_rsc('docente')).ir(CRIAR)
    antes = set(ProcessoRSC.objects.filter(servidor=rsc_seed['docente']).values_list('pk', flat=True))
    tela.preencher('RSC Pretendida', 'lista', 'RSC-II - docente')
    tela.clicar_botao('Adicionar')
    tela.ver_titulo('RSC-II')
    novo = ProcessoRSC.objects.filter(servidor=rsc_seed['docente']).exclude(pk__in=antes).get()
    assert (novo.tipo_rsc.nome, novo.status) == ('RSC-II', ProcessoRSC.STATUS_AGUARDANDO_ENVIO_CPPD)


def test_docente_anexa_pontua_e_salva(logado_rsc: Callable[[str], Page], rsc_seed: dict, processo_rsc: Callable[..., Any]) -> None:
    from rsc.models import Arquivo, ArquivosExigidos, ProcessoRSC

    processo = processo_rsc(ProcessoRSC.STATUS_AGUARDANDO_ENVIO_CPPD)
    criterio = rsc_seed['criterios']['RSC-II']
    arquivo = processo.arquivo_set.get(criterio=criterio)
    pagina = logado_rsc('docente')
    tela = Tela(pagina).ir(ABRIR.format(processo.pk))
    tela.clicar_aba('RSC-II')
    _abrir_criterio(pagina, criterio.pk)

    with pagina.expect_response(_chamou(UPLOAD)) as upload:
        pagina.locator(f'#criterio_{criterio.pk} input[type=file]').set_input_files(PDF)
    assert upload.value.status == 200
    assert Arquivo.objects.filter(processo=processo, criterio=criterio).count() == 2, 'o upload por critério não gravou o arquivo'

    pagina.locator(f'#qtd_{arquivo.pk}').fill('3')
    with pagina.expect_response(_chamou(SALVAR_ARQUIVO)):
        pagina.locator(f'tr[class~="linha-arquivo-{arquivo.encrypted_pk}"] a', has_text='Salvar').click()
    expect(pagina.locator('#feedback_message')).to_have_text('Arquivo salvo com sucesso.')
    arquivo.refresh_from_db()
    assert (arquivo.qtd_itens, arquivo.nota_pretendida) == (3, 3)

    tela.clicar_aba('Relatório Descritivo')
    pagina.locator('#id_introducao_relatorio_descritivo').fill('Introdução escrita no e2e.')
    with pagina.expect_response(_chamou(SALVAR)) as salvamento:
        pagina.locator('a[onclick^="Processa_Salvamento(\'salvar\'"]').click()
    assert salvamento.value.status == 200
    processo.refresh_from_db()
    assert processo.introducao_relatorio_descritivo == 'Introdução escrita no e2e.'

    exigido = processo.arquivosexigidos_set.get(tipo=ArquivosExigidos.CONCESSAO_ULTIMA_RT)
    tela.clicar_aba('Documentos Preliminares')
    quadro = tela.quadro('Concessão da última RT')
    # A resposta do uploader e o banco, não o realce verde do widget, que no CI chegou a passar dos 15 s.
    with pagina.expect_response(_chamou(UPLOAD_PRELIMINAR)) as upload:
        quadro.loc('//input[@type="file"]').set_input_files(PDF)
    assert upload.value.status == 200
    assert not ArquivosExigidos.objects.filter(pk=exigido.pk).exists(), 'o novo documento preliminar não substituiu o do mesmo tipo'
    assert processo.arquivosexigidos_set.filter(tipo=ArquivosExigidos.CONCESSAO_ULTIMA_RT).count() == 1


def test_docente_exclui_arquivos(logado_rsc: Callable[[str], Page], rsc_seed: dict, processo_rsc: Callable[..., Any]) -> None:
    """A lixeira de cada arquivo chama ``excluir_arquivo_pdf``/``excluir_arquivo_exigido_pdf`` por AJAX, depois de confirmar."""
    from rsc.models import Arquivo, ArquivosExigidos, ProcessoRSC

    processo = processo_rsc(ProcessoRSC.STATUS_AGUARDANDO_ENVIO_CPPD)
    criterio = rsc_seed['criterios']['RSC-II']
    arquivo = processo.arquivo_set.get(criterio=criterio)
    exigido = processo.arquivosexigidos_set.get(tipo=ArquivosExigidos.CONCESSAO_ULTIMA_RT)
    pagina = logado_rsc('docente')
    tela = Tela(pagina).ir(ABRIR.format(processo.pk))
    tela.clicar_aba('RSC-II')
    _abrir_criterio(pagina, criterio.pk)
    with pagina.expect_response(_chamou(EXCLUIR_ARQUIVO)):
        pagina.locator(f'tr[class~="linha-arquivo-{arquivo.encrypted_pk}"] a.icon-delete').click()
    expect(pagina.locator(f'tr[class~="linha-arquivo-{arquivo.encrypted_pk}"]')).to_have_count(0)
    assert not Arquivo.objects.filter(pk=arquivo.pk).exists()

    tela.clicar_aba('Documentos Preliminares')
    with pagina.expect_response(_chamou(EXCLUIR_PRELIMINAR)):
        pagina.locator(f'tr[id="linha-{exigido.encrypted_pk}"] a.icon-delete').click()
    expect(pagina.locator(f'tr[id="linha-{exigido.encrypted_pk}"]')).to_have_count(0)
    assert not ArquivosExigidos.objects.filter(pk=exigido.pk).exists()


def test_docente_clona_e_exclui_processo(logado_rsc: Callable[[str], Page], rsc_seed: dict, processo_rsc: Callable[..., Any]) -> None:
    from rsc.models import ProcessoRSC

    original = processo_rsc(ProcessoRSC.STATUS_REJEITADO)
    tela = Tela(logado_rsc('docente'))
    antes = set(ProcessoRSC.objects.filter(servidor=rsc_seed['docente']).values_list('pk', flat=True))
    tela.ir(CLONAR.format(original.pk))
    tela.sucesso('Processo RSC clonado com sucesso.')
    clone = ProcessoRSC.objects.filter(servidor=rsc_seed['docente']).exclude(pk__in=antes).get()
    assert (clone.clonado, clone.status, clone.arquivo_set.count()) == (True, ProcessoRSC.STATUS_AGUARDANDO_ENVIO_CPPD, 3)

    tela.ir(EXCLUIR.format(clone.pk))
    tela.sucesso('Processo excluído com sucesso.')
    assert not ProcessoRSC.objects.filter(pk=clone.pk).exists()


def _abrir_criterio(pagina: Page, criterio_id: int) -> None:
    """O quadro de cada critério nasce recolhido: o uploader e os campos do arquivo só ficam visíveis aberto."""
    pagina.locator(f'button[data-bs-target="#criterio_{criterio_id}"]').click()
    expect(pagina.locator(f'#criterio_{criterio_id}')).to_be_visible()


def _chamou(rota: str) -> Callable[[Response], bool]:
    """A resposta veio do endpoint ``rota`` (o trecho antes do primeiro parâmetro): o gesto acionou a view esperada."""
    prefixo = rota.partition('{}')[0]
    return lambda resposta: prefixo in resposta.url
