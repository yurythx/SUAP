import base64
import re
import string
import unicodedata
import urllib.parse
from collections import OrderedDict
from datetime import timedelta
from decimal import Decimal
from unicodedata import normalize

from bs4 import BeautifulSoup, BeautifulStoneSoup
from django.utils.html import escape, linebreaks
from django.utils.safestring import mark_safe


EMAIL_CONTA_INSTITUCIONAL_RE = re.compile(r'^[a-z0-9]+(?:\.[a-z0-9]+)*@[a-z0-9]+(?:[.-][a-z0-9]+)*$')


def eh_nome_completo(nome):
    """
    Verifica se a string passada pode ser um nome completo.

    Args:
        nome (string): string com o nome a ser testado.

    Returns:
        True se o nome pode ser completo.
    """
    return len(nome.strip().split(' ')) > 1 and not any(i.isdigit() for i in nome)


def normalizar_nome_proprio(nome):
    """
    Normaliza o nome próprio dado, aplicando a capitalização correta de acordo com as regras e
    exceções definidas no código.

    Args:
        nome (string): string contendo o nome a ser normalizado.

    Returns:
        String com o nome normalizado.
    :return:
    """
    ponto = r'\.'
    ponto_espaco = '. '
    espaco = ' '
    regex_multiplos_espacos = r'\s+'
    regex_numero_romano = r'^M{0,4}(CM|CD|D?C{0,3})(XC|XL|L?X{0,3})(IX|IV|V?I{0,3})$'

    # colocando espaço após nomes abreviados
    nome = re.sub(ponto, ponto_espaco, nome or '')
    # retirando espaços múltiplos
    nome = re.sub(regex_multiplos_espacos, espaco, nome)
    nome = nome.title()  # alterando os nomes para CamelCase
    partes_nome = nome.split(espaco)  # separando as palavras numa lista
    excecoes = [
        'de',
        'di',
        'do',
        'da',
        'dos',
        'das',
        'dello',
        'della',
        'dalla',
        'dal',
        'del',
        'e',
        'em',
        'na',
        'no',
        'nas',
        'nos',
        'van',
        'von',
        'y',
        'a',
    ]

    resultado = []

    for palavra in partes_nome:
        if palavra.lower() in excecoes:
            resultado.append(palavra.lower())
        elif re.match(regex_numero_romano, palavra.upper()):
            resultado.append(palavra.upper())
        else:
            resultado.append(palavra)

    nome = espaco.join(resultado)
    return nome


def montar_timeline_horizontal(
    queryset, data_inicio_referencia, data_fim_referencia, qs_data_inicio, qs_data_fim, descricao_celula, title='Timeline'
):
    """
    Cria o código **HTML** para uma timeline horizontal.

    Args:
        queryset (Queryset): queryset com resultado para gerar a timeline;
        data_inicio_referencia (datetime): data inicial de referência;
        data_fim_referencia (datetime): data final de referência;
        qs_data_inicio (string): nome do atributo da data inicial para comparação;
        qs_data_fim (string): nome do atributo da data final para comparação;
        descricao_celula (string): nome do atributo que representa o objeto.
        title (string): texto com o título da timeline.

    Returns:
        String contendo o código da timeline.
    """
    if not queryset:
        return ''
    html = f"""
        <div class="table-responsive">
        <table class="timeline-horizontal">
            <thead>
            <tr>
                <th>{title}</th>
        """
    tamanho_qs = Decimal((data_fim_referencia - data_inicio_referencia + timedelta(1)).days)
    queryset = queryset.order_by(qs_data_inicio)
    celulas = OrderedDict()
    for idx, objeto in enumerate(queryset):
        if celulas.get(objeto.__getattribute__(descricao_celula)):
            celulas.get(objeto.__getattribute__(descricao_celula)).append(idx)
        else:
            celulas[objeto.__getattribute__(descricao_celula)] = [idx]

        data_inicio = objeto.__getattribute__(qs_data_inicio)
        data_fim = objeto.__getattribute__(qs_data_fim)
        if not data_fim or data_fim > data_fim_referencia:
            data_fim = data_fim_referencia

        if data_inicio < data_inicio_referencia:
            data_inicio = data_inicio_referencia

        width = Decimal((data_fim - data_inicio + timedelta(1)).days) * Decimal(90) / tamanho_qs
        html += f"""
            <th style="width:{width}%">
                <span class="marker">{data_inicio.day}/{data_inicio.month} {data_inicio.year}</span>
        """
        if idx + 1 == len(queryset):
            html += f"""
                <span class="marker final">{data_fim.day}/{data_fim.month} {data_fim.year}</span>
            """

        html += '</th>'

    html += """
        </tr>
    </thead>
    <tbody>
    """
    for chave, colunas in list(celulas.items()):
        html += f"""
            <tr>
                <td>{chave}</td>"""
        for index in range(queryset.count()):
            if index in colunas:
                html += f'<td class="default" title="{chave}"></td>'
            else:
                html += '<td></td>'
        html += '</tr>'
    html += '</tbody></table></div>'
    return html


def tooltip_text(text, description):
    """
    Cria um **span** para ser utilizado como tooltip.

    Args:
        text (string): texto apresentado ao cliente;
        description (string): texto apresentado ao passar o mouse no texto.

    Returns:
        String contendo o código do **span**
    """
    return f'<span class="hint" aria-label="{description}">{text}</span>'


def human_str(val, encoding='utf-8', blank=''):
    """
    Retorna uma representação humana para o objeto.

    Args:
        val (object): objeto a ser analisado;
        encoding (string): codificação do texto de saída;
        blank (string): valor padrão caso val não exista;

    Examples:

        human_basestring(True) -> 'Sim'
        human_basestring(False) -> 'Não'
        human_basestring(User.objects.get(id=1)) -> 'admin'
        human_basestring(None) -> ''
        human_basestring(None, blank=u'-') -> '-'
        human_basestring(u'Teste') -> 'Teste'
        human_basestring('Teste') -> 'Teste'

    Returns:
        String contendo a representação humana do objeto.
    """
    if val is None:
        val = blank
    elif not isinstance(val, str):  # Não é uma string
        if isinstance(val, bool):
            val = val and 'Sim' or 'Não'
        elif hasattr(val, 'strftime'):
            if hasattr(val, 'time'):
                try:
                    val = val.strftime('%d/%m/%Y %H:%M:%S')
                except Exception:
                    val = str(val)
            else:
                try:
                    val = val.strftime('%d/%m/%Y')
                except Exception:
                    val = str(val)
        else:
            val = str(val)
    return val  # .encode(encoding, 'replace')


def force_utf8_string(value):
    """
    Sanitiza uma string substituindo sequências UTF-8 inválidas por um
    caractere de substituição. Retorna uma coerção para string se não for string.
    """
    if isinstance(value, str):
        return value.encode('utf-8', 'replace').decode('utf-8')
    return str(value)


def replace_ignore_case_accent(text: str, search: str, replace: str) -> str:
    # Normalize the text to remove accents
    def normalize(text: str) -> str:
        return ''.join(c for c in unicodedata.normalize('NFD', text) if unicodedata.category(c) != 'Mn')

    # Function to create a case-insensitive regex pattern
    escaped_search = re.escape(normalize(search))
    pattern = re.compile(escaped_search, re.IGNORECASE)

    # Function to replace while keeping original text structure intact
    def replacement(match):
        return replace

    # Find matches while preserving original structure
    result = []
    last_pos = 0

    # Normalize text for comparison but retain original characters
    normalized_text = normalize(text)

    for match in pattern.finditer(normalized_text):
        start, end = match.span()
        # Append text before the match and the replacement term
        result.append(text[last_pos:start])  # Text before the match
        result.append(replacement(match))  # Replacement text
        last_pos = end

    # Append any remaining text
    result.append(text[last_pos:])
    return ''.join(result)


def to_ascii(txt):
    """
    Converte texto passado para o padrão ASCII.

    Args:
        txt (string): texto a ser convertido.

    Return:
        String codificado no padrão ASCII.
    """
    if not isinstance(txt, str):
        txt = str(txt)
    return normalize('NFKD', txt).encode('ASCII', 'ignore').decode('utf-8')


def normalizar_token_email_conta(token: str) -> str:
    return re.sub(r'[^a-z0-9]', '', to_ascii(token).lower())


def validar_email_conta_institucional(email: str) -> bool:
    if not email:
        return True
    return bool(EMAIL_CONTA_INSTITUCIONAL_RE.match(email.strip().lower()))


def break_lines_safe(txt):
    """
    Só quebra linhas, mas mantém o texto seguro
    """
    return mark_safe(linebreaks(escape(txt)))


def normalizar_termos_busca(busca, avoid_short_search=True):
    preposicoes = ('da', 'de', 'di', 'do', 'du', 'das', 'dos', 'e')
    nova_palavra = []
    retiradas = []
    for token in busca.split():
        if not avoid_short_search or (token.lower() not in preposicoes and len(token) > 2):
            nova_palavra.append(token.strip(string.punctuation))
        else:
            retiradas.append(f'"{token}"')
    return ' '.join(nova_palavra), ', '.join(retiradas)


def convert_bytes_to_strb64(bytes):
    # bytes > encode to bytes b64 > decode to string b64
    bytes_b64 = base64.b64encode(bytes)
    str_b64 = bytes_b64.decode('utf-8')
    return str_b64


def convert_strb64_to_bytes(strb64):
    # string b64 > encode to bytes b64 > decode to bytes
    bytes_b64 = strb64.encode('utf-8')
    bytes = base64.b64decode(bytes_b64)
    return bytes


def retira_acentos(s):
    return ''.join(c for c in unicodedata.normalize('NFD', s) if unicodedata.category(c) != 'Mn')


def retira_caracteres_ocultos(texto):
    texto = unicodedata.normalize('NFKD', texto)
    return ''.join(c for c in texto if unicodedata.category(c)[0] != 'C')


def HTMLEntitiesToUnicode(text):
    """Converter entidades HTML em unicode. Ex.: &amp; para &. &lt; para <."""
    text = str(BeautifulStoneSoup(text, convertEntities=BeautifulStoneSoup.ALL_ENTITIES))
    return text


def HMTLParaStringUnicode(text):
    """Converter string com tags HTML e entidades HTML em string unicode limpa."""
    tag_re = re.compile(r'(<!--.*?-->|<[^>]*>)')
    texto_unicode_com_tags = HTMLEntitiesToUnicode(text)
    # Remove well-formed tags, fixing mistakes by legitimate users
    no_tags = tag_re.sub('', texto_unicode_com_tags)
    # Clean up anything else by escaping
    ready_for_web = urllib.parse.parse_qs(no_tags)
    return ready_for_web


def remover_tags_html(texto_html):
    # Verifica se o texto não está vazio
    if not texto_html or not isinstance(texto_html, str):
        # Cria um objeto BeautifulSoup com o texto HTML
        soup = BeautifulSoup(texto_html, 'html.parser')
        # Extrai o texto do objeto BeautifulSoup
        texto_sem_tags = soup.get_text(separator=' ')
        return texto_sem_tags
    else:
        return str(texto_html)


def retirar_preposicoes_nome(nome):
    preposicoes = ('da', 'de', 'di', 'do', 'du', 'das', 'dos', 'e')
    nova_palavra = []
    for token in nome.split():
        if token.lower() not in preposicoes:
            nova_palavra.append(token)
    return ' '.join(nova_palavra)


def gera_nomes(nome, separador=' '):
    tokens = to_ascii(retirar_preposicoes_nome(nome).upper()).split()
    nomes = []
    for t1 in tokens:
        for t2 in tokens:
            if t1 != t2:
                nome = f'{t1}{separador}{t2}'
                nomes.append(nome)
    return nomes


def insert_space(string, index):
    if len(string) <= index:
        return string
    return string[:index] + ' ' + string[index:]
