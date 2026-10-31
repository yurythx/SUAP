import html
import re
from django import template

register = template.Library()


@register.filter(name='quebrar_palavras_grandes')
def quebrar_palavras_grandes(texto, limite=100):
    """
    Adiciona caracteres ZWSP (zero-width space, ou espaço de largura zero) em pontos específicos de palavras grandes
    (maiores que `limite`) para forçar a quebra de linha e evitar que o texto extrapole a área visível.

    Por "palavra", considera-se uma sequência contínua de caracteres alfanuméricos, sem espaços.

    O filtro espera que `texto` seja uma string simples. EVITE aplicá-lo em texto HTML (ou em outro formato estruturado),
    pois isso pode quebrar estruturas importantes, como atributos e seus valores, e produzir anomalias.

    A inserção do caractere ZWSP será prioritariamente realizada após separadores naturais, como símbolos e sinais de pontuação.
    Se não for possível, será inserido após blocos de 10 caracteres.
    """

    def adicionar_zwsp(match):
        """Adiciona caractere ZWSP (zero-width space) ao grupo capturado pela expressão regular."""
        trecho = match.group(1)
        return f'{trecho}\u200b'

    if not isinstance(texto, str):
        texto = str(texto)

    regex_palavra_longa = r'\S{' + str(limite) + ',}'
    # Palavra seguida por símbolos em geral (exclui o ponto para evitar quebra de endereços web).
    regex_separadores_naturais = r'(\w+[^\w\.])'
    # Blocos de 10 caracteres (será usado se a palavra não possuir separadores naturais).
    regex_bloco_10_caracteres = r'(\w{10})'
    for palavra in re.findall(regex_palavra_longa, texto):
        regex_substituicao = regex_separadores_naturais if re.match(regex_separadores_naturais, palavra) else regex_bloco_10_caracteres
        palavra_ajustada = re.sub(regex_substituicao, adicionar_zwsp, palavra)
        texto = texto.replace(palavra, palavra_ajustada)

    return texto


@register.filter(name='normalizar_formatacao')
def normalizar_formatacao(texto):
    """
    Aplica uma série de ajustes a um texto HTML para exibição mais padronizada para uso na geração do PDF
    """
    texto = html.unescape(texto)

    h_tag = r'<h[^>]*>(.*?)</h[^>]*>'

    def substitui_h_tag(match):
        tag_content = match.group(1)
        return f'<strong>{tag_content}</strong>'

    html_substituido = re.sub(h_tag, substitui_h_tag, texto)

    estilos = r'style="[^"]*"'
    texto = re.sub(estilos, '', html_substituido)

    data_font = r'data-font="[^"]*"'
    texto = re.sub(data_font, '', texto)

    paragrafo_vazio = r'</?br>|<p[^>]*>(\s)*</p>'
    texto = re.sub(paragrafo_vazio, '', texto)

    span = r'</?span[^>]*>'
    texto = re.sub(span, '', texto)

    recuos_paragrafo = r'<p>\s+'
    texto = re.sub(recuos_paragrafo, '<p>', texto)

    multiplos_espacos = r'\s+'
    texto = re.sub(multiplos_espacos, ' ', texto)

    caractere_shy = r'\u00AD'
    texto = re.sub(caractere_shy, '', texto)

    texto = quebrar_palavras_grandes(texto)

    return texto
