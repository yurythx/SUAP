import logging
import re

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.template.loader import render_to_string
from django.utils import timezone

logger = logging.getLogger(__name__)


def _nome_arquivo(pda, versao_str):
    """Monta o nome-base do arquivo: pda_<vigencia>_<versao>."""
    vigencia = f'{pda.vigencia_inicio.year}_{pda.vigencia_fim.year}'
    versao_safe = versao_str.replace('.', '_')
    return f'pda_{vigencia}_{versao_safe}'


def _storage_path(nome_base, extensao):
    return f'pda/{nome_base}.{extensao}'


def _build_context(pda, versao_str):
    """Monta o contexto para renderização do template."""
    capa = pda.capa.first()
    topicos = pda.topicos.order_by('ordem', 'id')

    # Pré-formata o conteúdo de cada tópico
    topicos_formatados = []
    for t in topicos:
        t.conteudo_formatado = t.get_conteudo_formatado()
        topicos_formatados.append(t)

    capa_url = capa.imagem.url if capa and capa.imagem else None

    return {
        'pda': pda,
        'capa': capa,
        'capa_url': capa_url,
        'topicos': topicos_formatados,
        'versao': versao_str,
        'data_geracao': timezone.now(),
    }


def _storage_save(path, content):
    """Salva conteúdo no storage configurado, substituindo arquivo existente."""
    if default_storage.exists(path):
        default_storage.delete(path)
    default_storage.save(path, ContentFile(content))


def gerar_documento_pda(pda, versao_str):
    from weasyprint import HTML

    """
    Gera os arquivos HTML e PDF do PDA via default_storage e retorna
    os caminhos relativos usados no storage.
    """
    context = _build_context(pda, versao_str)
    nome_base = _nome_arquivo(pda, versao_str)

    html_path = _storage_path(nome_base, 'html')
    pdf_path = _storage_path(nome_base, 'pdf')

    # Salva HTML (sem página de capa e sem sumário)
    context['is_pdf'] = False
    html_string = render_to_string('dadosabertos/pda_documento_completo.html', context)
    _storage_save(html_path, html_string.encode('utf-8'))

    # Gera PDF (com sumário, sem imagem de capa) via weasyprint
    context['is_pdf'] = True
    context['capa'] = None
    pdf_html_string = render_to_string('dadosabertos/pda_documento_completo.html', context)
    weasy_doc = HTML(
        string=pdf_html_string,
        base_url=settings.SITE_URL,
    )
    pdf_bytes = weasy_doc.write_pdf()
    _storage_save(pdf_path, pdf_bytes)

    logger.info('Documento PDA gerado: %s (.html e .pdf)', nome_base)

    return html_path, pdf_path


# ── Helpers de leitura/resolução de arquivos ────────────────────────────────


def url_arquivo(pda, versao_str, extensao):
    """Retorna a URL de media do arquivo gerado para uma versão_str, ou None."""
    nome_base = _nome_arquivo(pda, versao_str)
    caminho = _storage_path(nome_base, extensao)
    if default_storage.exists(caminho):
        return default_storage.url(caminho)
    return None


def ler_documento_html(pda, versao_str):
    """Lê o HTML gerado do storage e retorna (style, body_html) ou (None, None)."""
    nome_base = _nome_arquivo(pda, versao_str)
    caminho = _storage_path(nome_base, 'html')
    if not default_storage.exists(caminho):
        return None, None

    with default_storage.open(caminho) as f:
        html = f.read().decode('utf-8')

    styles = re.findall(r'<style[^>]*>(.*?)</style>', html, re.DOTALL | re.IGNORECASE)
    style = '\n'.join(styles) if styles else ''

    body_match = re.search(r'<body[^>]*>(.*?)</body>', html, re.DOTALL | re.IGNORECASE)
    body = body_match.group(1) if body_match else ''

    return style, body


def versoes_com_arquivos(pda):
    """
    Retorna lista de dicts com cada VersaoPDA e as URLs dos arquivos gerados.

    Cada VersaoPDA(X.Y.Z) gera o arquivo nomeado com a versão seguinte na
    sequência (pós-incremento). O último registro corresponde a pda.versao_atual.
    """
    versoes = list(pda.versoes.order_by('major', 'minor', 'patch'))
    resultado = []
    for i, v in enumerate(versoes):
        versao_arquivo = versoes[i + 1].numero_formatado if i + 1 < len(versoes) else pda.versao_atual
        resultado.append(
            {
                'versao': v,
                'versao_arquivo': versao_arquivo,
                'documento_url': url_arquivo(pda, versao_arquivo, 'html'),
                'pdf_url': url_arquivo(pda, versao_arquivo, 'pdf'),
            }
        )
    resultado.reverse()
    return resultado


def find_pda_by_versao_arquivo(versao_str):
    """
    Dado um versao_str (ex: '1.1.7'), percorre todos os PDAs e retorna
    o primeiro (pda, versao_obj) cujo arquivo corresponde a esse string.
    Retorna (None, None) se não encontrado.
    """
    from dados_abertos.models import PlanoDadosAbertos

    for pda in PlanoDadosAbertos.objects.order_by('-vigencia_inicio', '-id'):
        versoes = list(pda.versoes.order_by('major', 'minor', 'patch'))
        for i, v in enumerate(versoes):
            arquivo = versoes[i + 1].numero_formatado if i + 1 < len(versoes) else pda.versao_atual
            if arquivo == versao_str:
                return pda, v
    return None, None
