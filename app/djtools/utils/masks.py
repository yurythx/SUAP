import re
from decimal import Decimal, InvalidOperation
from django.conf import settings

# Casas decimais dos valores monetários de almoxarifado/patrimônio (`decimal_places=6`
# nos campos `valor` desses módulos). Usada pelas máscaras e pelo filtro `format_money_almox`.
CASAS_DECIMAIS_ALMOX = 6


def decimal_para_str(value) -> str:
    """
    Converte o valor para string em notação de ponto fixo (sem notação científica).

    ``str(Decimal)`` usa notação científica quando o expoente é positivo ou quando o
    expoente ajustado é menor que -6 — o caso dos valores de almoxarifado/patrimônio,
    em que ``qtd`` (5 casas) multiplicada por ``valor`` (6 casas) gera resultados com 11
    casas decimais, e um total zerado volta do banco como ``Decimal('0E-11')``. As máscaras
    e filtros de dinheiro fatiam a string do valor, então precisam da forma em ponto fixo.

    O zero negativo (``Decimal('-0E-11')``, produzido por multiplicações com fator
    negativo) é normalizado para positivo, para não exibir valores como ``-0,00``.

    Args:
        value: valor a ser convertido.

    Examples:
        decimal_para_str(Decimal('0E-11')) -> '0.00000000000'
        decimal_para_str(Decimal('1E+3')) -> '1000'
        decimal_para_str('1.234,56') -> '1.234,56'

    Returns:
        String do valor em ponto fixo, ou o próprio ``str(value)`` quando não for numérico.
    """
    try:
        valor = Decimal(str(value))
    except InvalidOperation, ValueError:
        return str(value)
    if valor.is_zero():
        valor = abs(valor)
    return format(valor, 'f')


def split_thousands(value, sep='.'):
    """
    Adiciona o **sep** nas centenas do valor passado.

    Args:
        value (string): valor a ser processado.

    Returns:
        String com o valor com separação de centena.

    Note:
        Se for passado um tipo numérico em **value** esse será convertido para string.
    """
    if not isinstance(value, str):
        value = str(value)
    negativo = value.startswith('-')
    if negativo:
        value = value[1:]
    if len(value) <= 3:
        if negativo:
            return '-' + value
        else:
            return value
    if negativo:
        return '-' + split_thousands(value[:-3], sep) + sep + value[-3:]
    else:
        return split_thousands(value[:-3], sep) + sep + value[-3:]


def mask_numbers(value, encode=None):
    """
    Obtem os números contidos no valor passado.

    Args:
        value (string): string a ser processada;
        encode (string): codificação da string passada.

    Example:
        '012abc345def' -> '012345'

    Returns:
        String com os números contidos em **value**.
    """
    if encode:
        value = value.encode(encode)

    return re.sub(r'\D', '', str(value))


def mask_placa(value):
    """
    Obtem o valor passado com a mascara para placa de automóvel.

    Args:
        value (string): string a ser mascarado;

    Example:
        'AAA1111' -> 'AAA-1111'

    Returns:
        String com mascara para placa de automóvel.
    """
    value = str(value)
    return value[:3] + '-' + value[3:]


def mask_number(value):
    if value is None:
        return None
    value = str(value)
    if '.' in value:
        a, b = value.split('.')
        a, b = int(a), int(b)
        if b:
            return f'{a},{b}'
        else:
            return a
    else:
        return value


def mask_money(value):
    """
    Obtem o valor no formato de dinheiro.

    Args:
        value (str): Valor a ser convertido.

    Examples:
        mask_money(1) -> '1,00'
        mask_money(1000) -> '1.000,00'
        mask_money(1000.99) -> '1.000,99'

    Returns:
        String com o valor com masca.
    """
    value = decimal_para_str(value)
    if '.' in value:
        reais, centavos = value.split('.')
        if len(centavos) > 2:
            centavos = centavos[0:2]
    else:
        reais = value
        centavos = '00'
    reais = split_thousands(reais)
    return reais + ',' + centavos


def mask_money_almox(value, casas_decimais=CASAS_DECIMAIS_ALMOX):
    """
    Obtém o valor no formato de dinheiro do almoxarifado/patrimônio, com casas decimais extras.

    Diferente de **mask_money**, que trunca em 2 casas, mantém exatamente ``casas_decimais``
    casas — formato esperado pela máscara javascript ``mask_money_almox``, que preenche o campo
    da direita para a esquerda.

    Args:
        value: Valor a ser convertido.
        casas_decimais (int): Quantidade de casas decimais a manter.

    Examples:
        mask_money_almox(1) -> '1,000000'
        mask_money_almox(Decimal('1000.5')) -> '1.000,500000'
        mask_money_almox(Decimal('1.1234567')) -> '1,123456'

    Returns:
        String com o valor com máscara.
    """
    value = decimal_para_str(value)
    if '.' in value:
        reais, centavos = value.split('.')
    else:
        reais, centavos = value, ''
    centavos = centavos[:casas_decimais].ljust(casas_decimais, '0')
    return f'{split_thousands(reais)},{centavos}'


def mask_nota(value):
    """
    Obtem a nota no formato decimal (configuração no settings).

    Args:
        value (int): Valor a ser convertido.

    Returns:
        String com o valor com máscara.
    """
    if settings.NOTA_DECIMAL:
        try:
            value = int(value)
        except Exception:
            return ''
        if settings.NOTA_DECIMAL and settings.CASA_DECIMAL == 1:
            tokens = str(value / 10).split('.')
            if len(tokens) == 1:
                value = f'{tokens[0]},0'
            else:
                value = f'{tokens[0]},{tokens[1][0:1]}'
        elif settings.NOTA_DECIMAL and settings.CASA_DECIMAL == 2:
            tokens = str(value / 100).split('.')
            if len(tokens) == 1:
                value = f'{tokens[0]},00'
            else:
                value = '{},{}'.format(tokens[0], tokens[1].ljust(2, '0')[0:2])
    return value


def mask_ch_componente(value):
    """
    Converte a CH salva como inteiro para o formato decimal caso configuração "COMPONENTE_CH_DECIMAL" esteja habilitada no settings.
    Senão retorna o valor original.

    Args:
        value (int): Valor a ser convertido.

    """
    if value is None:
        return None

    if settings.COMPONENTE_CH_DECIMAL:
        value = int(value)
        return Decimal(value / 100).quantize(Decimal('0.00'))

    return value


def mask_cpf(value, clean=True):
    """
    Obtem o valor passado com a mascara para CPF.

    Args:
        value (strig): valor a ser mascarado;
        clean (bool): indica se é necessário limpar o **value**.

    Examples:
        '00000000000' -> '000.000.000-00'

    Returns:
        String com mascara para CPF.
    """
    if clean:
        value = mask_numbers(value)
    if not len(value):
        return ''
    return value[:3] + '.' + value[3:6] + '.' + value[6:9] + '-' + value[9:11]


def mask_processo_eletronico(value, clean=True):
    """
    Obtem o valor passado com a mascara para Processo Eletronico.

    Args:
        value (strig): valor a ser mascarado;
        clean (bool): indica se é necessário limpar o **value**.

    Examples:
        '00000000000000000' -> '00000.000000.0000-00'

    Returns:
        String com mascara para Processo Eletronico.
    """
    if clean:
        value = mask_numbers(value)
    if not len(value):
        return ''
    return value[:5] + '.' + value[5:11] + settings.NUM_PROCESSO_DIVISOR_SUFIXO + value[11:15] + '-' + value[15:17]


def anonimizar_cpf(value):
    """
    Anonimiza o CPF passado ocultando os 3 primeiros e os 2 ultimos digitos.

    Args:
        value (strig): valor a ser anonimizado;

    Examples:
        '00000000000' -> '***.000.000-**'

    Returns:
        CPF Anonimizado.
    """
    value = mask_numbers(value)
    if not len(value):
        return ''
    return '***' + '.' + value[3:6] + '.' + value[6:9] + '-' + '**'


def anonimizar_matricula(value):
    """
    Anonimiza a matrícula passada ocultando os 4 últimos digitos.

    Args:
        value (strig): valor a ser anonimizado;

    Examples:
        '0000000' -> '000****'

    Returns:
        Matrícula Anonimizada.
    """
    value = mask_numbers(value)
    if not len(value):
        return ''
    return value[0:3] + '****'


# documento_identificador sintético da pessoa física sem documento (ver rh/deduplicacao/documentos.py): <prefixo><id>[-<documento>]
PREFIXOS_SINTETICOS = ('SEMDOC-', 'SEMPAIS-', 'CONFLITO-', 'INVALIDO-')


def anonimizar_documento(documento: str | None) -> str:
    """O ``documento_identificador`` da pessoa física para exibição: CPF como ``***.358.734-**``, passaporte só com o fim
    (``ARG-****3456``).

    No sintético, prefixo e id ficam (não identificam a pessoa) e o documento guardado nele é anonimizado.
    """
    if not documento:
        return ''
    if documento.startswith(PREFIXOS_SINTETICOS):
        prefixo, pf_id, *guardado = documento.split('-', 2)
        return '-'.join([prefixo, pf_id, *(anonimizar_documento(valor) for valor in guardado)])
    if len(mask_numbers(documento)) == 11 and not re.search('[A-Za-z]', documento):
        return anonimizar_cpf(documento)
    iso, hifen, numero = documento.rpartition('-')
    visiveis = min(4, len(numero) // 2)
    return f'{iso}{hifen}{"*" * (len(numero) - visiveis)}{numero[len(numero) - visiveis :]}'


def mask_cnpj(value):
    """
    Obtem o valor passado com a mascara para CNPJ.

    Args:
        value (strig): valor a ser mascarado.

    Examples:
        'XXXXXXXXXXXXXX' -> 'XX.XXX.XXX/XXXX-XX'

    Returns:
        String com mascara para CNPJ.
    """
    value = mask_numbers(value)
    return value[:2] + '.' + value[2:5] + '.' + value[5:8] + '/' + value[8:12] + '-' + value[12:14]


def mask_cep(value):
    """
    Obtem o valor passado com a mascara para CEP.

    Args:
        value (strig): valor a ser mascarado.

    Examples:
        '99999999' -> '99999-999'

    Returns:
        String com mascara para CEP.
    """
    value = mask_numbers(value)
    return value[:5] + '-' + value[5:]


def format_telefone(ddd, numero):
    """
    Retorna o número de telefone formatado como (XX) XXXX-XXXX.
    O traço ficará sempre antes dos 4 últimos.
    Espaços existentes antes ou depois do ddd ou numero são removidos.

    Args:
        ddd (string): código de discagem a distância;
        numero (string): número do telefone.

    Examples:
        >>> format_telefone('84', '12345678')
        '(84) 1234-5678'
        >>> format_telefone('48', '1234567')
        '(48) 123-4567'
        >>> format_telefone('', '12345678')
        '(XX) 1234-5678'
        >>> format_telefone(' 84 ', '12345678')
        '(84) 1234-5678'
        >>> format_telefone(' 84 ', '  12345678 ')
        '(84) 1234-5678'

    Returns:
        String com o telefone mascarado.
    """
    ddd = ddd.strip()
    if not ddd:
        ddd = 'XX'
    else:
        ddd = ddd[-2:]

    numero = numero.strip()
    return f'({ddd}) {numero[: len(numero) - 4]}-{numero[len(numero) - 4 :]}'
