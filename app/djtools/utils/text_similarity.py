"""
Utilitários para análise de similaridade e comparação de textos.

Este módulo fornece funções para:
- Cálculo de similaridade entre strings
- Normalização de textos para comparação
- Geração de diff visual com HTML formatado

Pode ser usado por qualquer módulo do sistema que precise comparar textos.
"""

import logging
import unicodedata
from difflib import SequenceMatcher

from django.utils.html import escape
from django.utils.safestring import mark_safe

logger = logging.getLogger(__name__)


# =============================================================================
# CONSTANTES
# =============================================================================

# Threshold padrão para considerar linhas similares (99% = quase idênticas)
THRESHOLD_SIMILARIDADE_LINHA = 0.99

# Diferença máxima de tamanho entre linhas para serem consideradas similares (5%)
MAX_DIFF_TAMANHO_LINHA = 0.05

# Configuração padrão do TF-IDF
TFIDF_MAX_FEATURES = 1000
TFIDF_MIN_DF = 1


# =============================================================================
# FUNÇÕES DE CÁLCULO DE SIMILARIDADE
# =============================================================================


def calcular_similaridade_strings(string1, string2, case_sensitive=False):
    """
    Calcula a similaridade entre duas strings usando SequenceMatcher.

    Args:
        string1 (str): Primeira string
        string2 (str): Segunda string
        case_sensitive (bool): Se False, ignora diferenças de maiúsculas/minúsculas

    Returns:
        float: Valor entre 0.0 e 1.0 indicando similaridade (1.0 = idênticas)

    Examples:
        >>> calcular_similaridade_strings('Python', 'python')
        1.0
        >>> calcular_similaridade_strings('Python', 'python', case_sensitive=True)
        0.0
    """
    if not string1 or not string2:
        return 0.0

    texto1 = string1 if case_sensitive else string1.lower()
    texto2 = string2 if case_sensitive else string2.lower()

    return SequenceMatcher(None, texto1, texto2).ratio()


def calcular_similaridade_textos(texto1, texto2, metodo='tfidf'):
    """Calcula a similaridade entre dois textos usando o método especificado.

    Args:
        texto1: primeiro texto para comparação.
        texto2: segundo texto para comparação.
        metodo: método de comparação — ``'tfidf'`` (TF-IDF + cosine similarity,
            mais preciso para textos longos) ou ``'sequencematcher'``
            (SequenceMatcher, mais rápido para textos curtos).

    Returns:
        float: valor entre ``0.0`` e ``1.0`` indicando a similaridade.

    Raises:
        ValueError: se ``metodo`` não for ``'tfidf'`` nem ``'sequencematcher'``.
    """
    if not texto1 or not texto2:
        return 0.0

    if metodo == 'sequencematcher':
        return SequenceMatcher(None, texto1, texto2).ratio()

    if metodo == 'tfidf':
        try:
            from sklearn.feature_extraction.text import TfidfVectorizer
            from sklearn.metrics.pairwise import cosine_similarity

            vectorizer = TfidfVectorizer(
                max_features=TFIDF_MAX_FEATURES,
                stop_words=None,
                min_df=TFIDF_MIN_DF,
            )

            tfidf_matrix = vectorizer.fit_transform([texto1, texto2])
            similaridade = cosine_similarity(tfidf_matrix[0:1], tfidf_matrix[1:2])[0][0]

            return float(similaridade)
        except Exception as e:
            logger.warning(f'Erro ao calcular similaridade com TF-IDF: {e!s}. Usando fallback.')
            return SequenceMatcher(None, texto1, texto2).ratio()

    raise ValueError(f"Método '{metodo}' inválido. Use 'tfidf' ou 'sequencematcher'")


# =============================================================================
# FUNÇÕES DE NORMALIZAÇÃO DE TEXTO
# =============================================================================


def normalizar_texto_para_comparacao(texto):
    """
    Normaliza texto para comparação, removendo diferenças triviais de formatação.

    Operações realizadas:
    - Normalização Unicode NFC (composição canônica)
    - Unificação de quebras de linha (\\r\\n → \\n)
    - Conversão de espaços especiais para espaço normal
    - Remoção de zero-width characters

    Args:
        texto (str): Texto a ser normalizado

    Returns:
        str: Texto normalizado

    Examples:
        >>> normalizar_texto_para_comparacao('texto\\r\\ncom\\xa0espacos')
        'texto\\ncom espacos'
    """
    if not texto:
        return ''

    # Normalização Unicode para forma canônica composta
    texto = unicodedata.normalize('NFC', texto)

    # Unifica quebras de linha
    texto = texto.replace('\r\n', '\n').replace('\r', '\n')

    # Substitui espaços especiais por espaço normal
    # Nota: \xa0 e \u00a0 são a mesma coisa (non-breaking space)
    espacos_especiais = {
        '\xa0': ' ',  # Non-breaking space
        '\u2009': ' ',  # Thin space
        '\u200b': '',  # Zero-width space
        '\u200c': '',  # Zero-width non-joiner
        '\u200d': '',  # Zero-width joiner
        '\ufeff': '',  # Zero-width no-break space
    }

    for especial, normal in espacos_especiais.items():
        texto = texto.replace(especial, normal)

    return texto


def linhas_sao_similares(linha1, linha2, threshold=THRESHOLD_SIMILARIDADE_LINHA):
    """
    Verifica se duas linhas são praticamente idênticas após normalização.

    Usa threshold alto (padrão 99%) para garantir que apenas diferenças
    triviais de formatação sejam ignoradas.

    Args:
        linha1 (str): Primeira linha
        linha2 (str): Segunda linha
        threshold (float): Limite de similaridade (0.0 a 1.0)

    Returns:
        bool: True se as linhas são praticamente idênticas

    Examples:
        >>> linhas_sao_similares('Python  3.11', 'Python 3.11')
        True
        >>> linhas_sao_similares('Python 3.11', 'Python 3.12')
        False
    """
    # Normaliza ambas as linhas
    norm1 = normalizar_texto_para_comparacao(linha1)
    norm2 = normalizar_texto_para_comparacao(linha2)

    # Se ficarem idênticas após normalização, são iguais
    if norm1 == norm2:
        return True

    # Se uma das duas está vazia, não são similares
    if not norm1 or not norm2:
        return False

    # Verifica diferença de tamanho (evita falsos positivos)
    len_diff = abs(len(norm1) - len(norm2))
    len_max = max(len(norm1), len(norm2))
    if len_max > 0 and len_diff > len_max * MAX_DIFF_TAMANHO_LINHA:
        return False

    # Calcula similaridade
    similaridade = SequenceMatcher(None, norm1, norm2).ratio()

    return similaridade >= threshold


# =============================================================================
# FUNÇÕES DE GERAÇÃO DE DIFF VISUAL
# =============================================================================


def _formatar_palavra_html(palavra, tipo_mudanca):
    """
    Formata uma palavra com estilo HTML baseado no tipo de mudança.

    Args:
        palavra (str): Palavra a ser formatada
        tipo_mudanca (str): Tipo de mudança ('delete', 'insert', 'replace')

    Returns:
        str: HTML formatado com strong tag e estilos inline
    """
    estilos = {
        'delete': 'background-color: #f8d7da !important; color: #721c24 !important;',
        'insert': 'background-color: #d4edda !important; color: #155724 !important;',
        'replace': 'background-color: #fff3cd !important; color: #856404 !important;',
    }

    estilo_base = 'padding: 2px 4px !important; border-radius: 3px !important; font-weight: bold !important;'
    estilo_completo = f'{estilos.get(tipo_mudanca, "")} {estilo_base}'

    return f'<strong style="{estilo_completo}">{escape(palavra)}</strong>'


def gerar_diff_inline(texto1, texto2):
    """
    Gera diff inline (palavra por palavra) com destaque HTML.

    Args:
        texto1 (str): Primeiro texto (original)
        texto2 (str): Segundo texto (modificado)

    Returns:
        tuple: (html_texto1, html_texto2) com marcações de diferenças

    Examples:
        >>> html1, html2 = gerar_diff_inline('Python 2', 'Python 3')
        >>> '<strong' in html1
        True
    """
    # Normaliza para comparação
    norm1 = normalizar_texto_para_comparacao(texto1)
    norm2 = normalizar_texto_para_comparacao(texto2)

    # Se são idênticos após normalização, retorna sem destaque
    if norm1 == norm2:
        return escape(texto1), escape(texto2)

    # Divide em palavras para comparação granular
    palavras1 = texto1.split()
    palavras2 = texto2.split()

    # Detecta diferenças palavra por palavra
    matcher = SequenceMatcher(None, palavras1, palavras2)
    opcodes = matcher.get_opcodes()

    html1 = []
    html2 = []

    for tag, i1, i2, j1, j2 in opcodes:
        if tag == 'equal':
            # Palavras iguais
            html1.extend(escape(p) for p in palavras1[i1:i2])
            html2.extend(escape(p) for p in palavras2[j1:j2])

        elif tag == 'delete':
            # Palavras removidas (só no texto1)
            html1.extend(_formatar_palavra_html(p, 'delete') for p in palavras1[i1:i2])

        elif tag == 'insert':
            # Palavras adicionadas (só no texto2)
            html2.extend(_formatar_palavra_html(p, 'insert') for p in palavras2[j1:j2])

        elif tag == 'replace':
            # Palavras modificadas
            html1.extend(_formatar_palavra_html(p, 'replace') for p in palavras1[i1:i2])
            html2.extend(_formatar_palavra_html(p, 'replace') for p in palavras2[j1:j2])

    # Junta as palavras com espaços
    resultado1 = ' '.join(html1) if html1 else '&nbsp;'
    resultado2 = ' '.join(html2) if html2 else '&nbsp;'

    return mark_safe(resultado1), mark_safe(resultado2)


def _formatar_linha_diff_html(linha, tipo_linha, prefixo=''):
    """
    Formata uma linha de diff com classes CSS apropriadas.

    Args:
        linha (str): Conteúdo da linha
        tipo_linha (str): Tipo ('equal', 'delete', 'insert', 'replace')
        prefixo (str): Prefixo opcional (ex: '- ' ou '+ ')

    Returns:
        str: HTML formatado
    """
    conteudo = f'{prefixo}{escape(linha)}' if prefixo else escape(linha)
    return f'<div class="diff-line diff-{tipo_linha}">{conteudo}</div>'


def gerar_diff_lado_a_lado(texto1, texto2):
    """
    Gera diff lado a lado de dois textos com HTML formatado.

    Características:
    - Normaliza textos antes da comparação
    - Compara linhas com threshold de similaridade
    - Destaca apenas diferenças reais de conteúdo
    - Retorna HTML com classes CSS para estilização

    Classes CSS geradas:
    - .diff-line: Linha do diff
    - .diff-equal: Linha igual
    - .diff-delete: Linha removida (prefixo '- ')
    - .diff-insert: Linha adicionada (prefixo '+ ')
    - .diff-replace: Linha modificada (com destaque palavra por palavra)

    Args:
        texto1 (str): Primeiro texto (original)
        texto2 (str): Segundo texto (modificado)

    Returns:
        dict: {'original': html_texto1, 'duplicata': html_texto2}
    """
    # Normaliza os textos completos primeiro
    texto1_normalizado = normalizar_texto_para_comparacao(texto1)
    texto2_normalizado = normalizar_texto_para_comparacao(texto2)

    # Separa em linhas (mantendo originais para exibição)
    linhas1_original = texto1.splitlines()
    linhas2_original = texto2.splitlines()
    linhas1_norm = texto1_normalizado.splitlines()
    linhas2_norm = texto2_normalizado.splitlines()

    # Detecta diferenças entre linhas normalizadas
    differ = SequenceMatcher(None, linhas1_norm, linhas2_norm)
    opcodes = differ.get_opcodes()

    html_original = []
    html_duplicata = []

    for tag, i1, i2, j1, j2 in opcodes:
        if tag == 'equal':
            # Linhas iguais
            for idx in range(i1, i2):
                linha = linhas1_original[idx] if idx < len(linhas1_original) else ''
                html_original.append(_formatar_linha_diff_html(linha, 'equal'))
            for idx in range(j1, j2):
                linha = linhas2_original[idx] if idx < len(linhas2_original) else ''
                html_duplicata.append(_formatar_linha_diff_html(linha, 'equal'))

        elif tag == 'delete':
            # Linhas removidas (só no original)
            for idx in range(i1, i2):
                linha = linhas1_original[idx] if idx < len(linhas1_original) else ''
                html_original.append(_formatar_linha_diff_html(linha, 'delete', '- '))

        elif tag == 'insert':
            # Linhas adicionadas (só na duplicata)
            for idx in range(j1, j2):
                linha = linhas2_original[idx] if idx < len(linhas2_original) else ''
                html_duplicata.append(_formatar_linha_diff_html(linha, 'insert', '+ '))

        elif tag == 'replace':
            # Linhas modificadas - verifica se são realmente diferentes
            linhas_orig = [linhas1_original[idx] if idx < len(linhas1_original) else '' for idx in range(i1, i2)]
            linhas_dup = [linhas2_original[idx] if idx < len(linhas2_original) else '' for idx in range(j1, j2)]

            _processar_linhas_replace(linhas_orig, linhas_dup, html_original, html_duplicata)

    # Equaliza tamanho para alinhamento visual
    _equalizar_html_diff(html_original, html_duplicata)

    return {'original': mark_safe(''.join(html_original)), 'duplicata': mark_safe(''.join(html_duplicata))}


def _processar_linhas_replace(linhas_orig, linhas_dup, html_original, html_duplicata):
    """
    Processa linhas modificadas comparando par a par ou tratando como inserção/remoção.

    Args:
        linhas_orig (list): Linhas do texto original
        linhas_dup (list): Linhas do texto duplicata
        html_original (list): Lista HTML do original (será modificada in-place)
        html_duplicata (list): Lista HTML da duplicata (será modificada in-place)
    """
    # Se temos o mesmo número de linhas, compara par a par
    if len(linhas_orig) == len(linhas_dup):
        for linha1, linha2 in zip(linhas_orig, linhas_dup, strict=True):
            if linhas_sao_similares(linha1, linha2):
                # Linhas suficientemente similares - trata como iguais
                html_original.append(_formatar_linha_diff_html(linha1, 'equal'))
                html_duplicata.append(_formatar_linha_diff_html(linha2, 'equal'))
            else:
                # Diferenças reais - faz diff palavra por palavra
                diff_linha1, diff_linha2 = gerar_diff_inline(linha1, linha2)
                html_original.append(f'<div class="diff-line diff-replace">{diff_linha1}</div>')
                html_duplicata.append(f'<div class="diff-line diff-replace">{diff_linha2}</div>')
    else:
        # Número diferente de linhas - emparelha o que for possível
        max_pairs = min(len(linhas_orig), len(linhas_dup))

        for i in range(max_pairs):
            linha1 = linhas_orig[i]
            linha2 = linhas_dup[i]

            if linhas_sao_similares(linha1, linha2):
                html_original.append(_formatar_linha_diff_html(linha1, 'equal'))
                html_duplicata.append(_formatar_linha_diff_html(linha2, 'equal'))
            else:
                diff_linha1, diff_linha2 = gerar_diff_inline(linha1, linha2)
                html_original.append(f'<div class="diff-line diff-replace">{diff_linha1}</div>')
                html_duplicata.append(f'<div class="diff-line diff-replace">{diff_linha2}</div>')

        # Adiciona linhas restantes
        for linha in linhas_orig[max_pairs:]:
            html_original.append(_formatar_linha_diff_html(linha, 'delete', '- '))

        for linha in linhas_dup[max_pairs:]:
            html_duplicata.append(_formatar_linha_diff_html(linha, 'insert', '+ '))


def _equalizar_html_diff(html_original, html_duplicata):
    """
    Equaliza o tamanho de duas listas HTML adicionando linhas vazias.

    Args:
        html_original (list): Lista HTML do original (será modificada in-place)
        html_duplicata (list): Lista HTML da duplicata (será modificada in-place)
    """
    linha_vazia = '<div class="diff-line diff-equal">&nbsp;</div>'

    while len(html_original) < len(html_duplicata):
        html_original.append(linha_vazia)

    while len(html_duplicata) < len(html_original):
        html_duplicata.append(linha_vazia)
