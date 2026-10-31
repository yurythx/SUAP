from __future__ import annotations

import logging
import os
import tempfile
from typing import TYPE_CHECKING

import requests
from django.conf import settings
from django.contrib.staticfiles import finders
from django.http import HttpRequest

from djtools.assincrono import task
from djtools.models import Task
from djtools.utils import convert_pdf_to_pdfa

if TYPE_CHECKING:
    from documento_eletronico.models import DocumentoTexto

logger = logging.getLogger(__name__)

MENSAGEM_CONVERSOR_PDFA_INDISPONIVEL = 'Serviço de conversão para PDF/A indisponível no momento. Tente novamente mais tarde.'

MENSAGEM_GERADOR_PDF_INDISPONIVEL = 'Serviço de geração de PDF indisponível no momento. Tente novamente mais tarde.'


@task('Imprimir Documento em formato PDF')
def imprimir_pdf(
    request: HttpRequest,
    documento: DocumentoTexto,
    consulta_publica_hash: str | None,
    leitura_para_barramento: bool,
    eh_consulta_publica: bool,
    orientacao: str,
    task: Task | None = None,
) -> object:
    if task is None:
        raise RuntimeError('A tarefa de impressão não foi inicializada.')
    task.start_progress(100)
    try:
        pdf = documento.get_pdf(
            orientacao=orientacao,
            user=request.user,
            consulta_publica_hash=consulta_publica_hash,
            leitura_para_barramento=leitura_para_barramento,
            eh_consulta_publica=eh_consulta_publica,
        )
    except requests.exceptions.RequestException as e:
        # Mesma razão do conversor PDF/A em ``imprimir_pdfa``: infra fora do ar, sem nova tentativa.
        logger.warning('Gerador de PDF indisponível ao imprimir o documento %s: %r', documento.pk, e)
        return task.finalize(MENSAGEM_GERADOR_PDF_INDISPONIVEL, '..', error=True)
    tmp = tempfile.NamedTemporaryFile(suffix='.pdf', mode='w+b', delete=False)
    tmp.write(pdf)
    tmp.close()
    task.update_progress(100)
    return task.finalize('Documento impresso com sucesso.', '..', file_path=tmp.name)


@task('Imprimir Documento em formato PDFA')
def imprimir_pdfa(
    request: HttpRequest,
    documento: DocumentoTexto,
    consulta_publica_hash: str | None,
    leitura_para_barramento: bool,
    eh_consulta_publica: bool,
    orientacao: str,
    task: Task | None = None,
) -> object:
    if task is None:
        raise RuntimeError('A tarefa de impressão não foi inicializada.')
    task.start_progress(100)
    try:
        pdf = documento.get_pdf(
            orientacao=orientacao,
            user=request.user,
            consulta_publica_hash=consulta_publica_hash,
            leitura_para_barramento=leitura_para_barramento,
            eh_consulta_publica=eh_consulta_publica,
        )
    except requests.exceptions.RequestException as e:
        logger.warning('Gerador de PDF indisponível ao imprimir o documento %s: %r', documento.pk, e)
        return task.finalize(MENSAGEM_GERADOR_PDF_INDISPONIVEL, '..', error=True)
    task.update_progress(50)
    tmp = tempfile.NamedTemporaryFile(suffix='.pdf', mode='w+b', delete=False)
    tmp.write(pdf)
    tmp.close()
    try:
        converted = convert_pdf_to_pdfa(tmp.name, version=1)
    except requests.exceptions.RequestException as e:
        # Lentidão/queda/erro HTTP (Timeout, ConnectionError, HTTPError) do serviço externo é infra: avisa o usuário e registra warning, que o Sentry guarda só como breadcrumb.
        # Sem nova tentativa de propósito: cada uma prenderia o worker por mais REQUESTS_TIMEOUT (60 s) e o urllib3 já repete a conexão.
        logger.warning('Conversor de PDF/A indisponível ao imprimir o documento %s: %r', documento.pk, e)
        return task.finalize(MENSAGEM_CONVERSOR_PDFA_INDISPONIVEL, '..', error=True)
    finally:
        os.unlink(tmp.name)
    task.update_progress(100)
    return task.finalize('Documento impresso com sucesso.', '..', file_path=converted)


@task('Imprimir versão de Documento em formato PDF')
def imprimir_versao_pdf(request: HttpRequest, conteudo_html: str, orientacao: str, task: Task | None = None) -> object:
    # Import tardio: o weasyprint depende de bibliotecas de sistema (glib/pango) que não
    # estão presentes em todos os ambientes. Importar no topo quebraria a carga do app.
    from weasyprint import CSS, HTML

    if task is None:
        raise RuntimeError('A tarefa de impressão não foi inicializada.')
    task.start_progress(100)
    caminhos_css = (
        finders.find('ckeditor/ckeditor/contents.css'),
        finders.find('documento_eletronico/css/documento.css'),
        finders.find('djtools/css/pdf_assinaturas.css'),
    )
    folhas_estilo = [CSS(filename=caminho) for caminho in caminhos_css if caminho]
    folhas_estilo.append(CSS(string=f'@page {{ size: A4 {orientacao}; }}'))
    html = f'<html lang="pt-br"><body class="document-content">{conteudo_html}</body></html>'
    pdf = HTML(string=html, base_url=settings.SITE_URL).write_pdf(stylesheets=folhas_estilo)
    arquivo = tempfile.NamedTemporaryFile(suffix='.pdf', mode='w+b', delete=False)
    arquivo.write(pdf)
    arquivo.close()
    task.update_progress(100)
    return task.finalize('Documento impresso com sucesso.', '..', file_path=arquivo.name)
