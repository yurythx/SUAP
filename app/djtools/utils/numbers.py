from decimal import Decimal

from .masks import mask_nota


def str_money_to_decimal(value):
    """
    Convert uma string em um valor decimal.

    Args:
        value (string): string contendo o valor a ser convertido.

    Example:
        '1.010,10' -> Decimal('1010.00')

    Returns:
        Decimal da string passada.
    """
    value_float = float(value.replace('.', '').replace(',', '.').replace(' ', ''))
    return Decimal(str(value_float))


def int_to_roman(value):
    """
    Converte um número inteiro para algarísmo romano.

    Args:
        value (int): valor a ser convertido.

    Raises:
        ValueError se não for possível converter para inteiro o valor passado;
        TypeError se o valor passado não for um *int*;
        ValueError se o valor estiver fora da faixa [0, 4000].

    Returns:
        String com o valor em algarísmo romano.
    """
    try:
        value = int(value)
    except Exception:
        raise ValueError(f'Expected integer, got {type(value)}')
    if not isinstance(value, int):
        raise TypeError(f'Expected integer, got {type(value)}')
    if not 0 < value < 4000:
        raise ValueError('Argument must be between 1 and 3999')
    ints = (1000, 900, 500, 400, 100, 90, 50, 40, 10, 9, 5, 4, 1)
    nums = ('M', 'CM', 'D', 'CD', 'C', 'XC', 'L', 'XL', 'X', 'IX', 'V', 'IV', 'I')
    result = []
    for i in range(len(ints)):
        count = int(value / ints[i])
        result.append(nums[i] * count)
        value -= ints[i] * count
    return ''.join(result)


def roman_to_int(input_value):
    """
    Converte um valor em algorísmo romano em inteiro.

    Args:
        input_value (string): algorísmo romano a ser convertido.

    Raises:
        TypeError se o **input_value** não for uma string;
        ValueError se não for possível a conversão.

    Returns:
        Int do algorísmo romano passado.
    """

    if not isinstance(input_value, str):
        raise TypeError(f'expected string, got {type(input_value)}')
    input_value = input_value.upper()
    nums = {'M': 1000, 'D': 500, 'C': 100, 'L': 50, 'X': 10, 'V': 5, 'I': 1}
    sum_value = 0
    for i in range(len(input_value)):
        try:
            value = nums[input_value[i]]
            # If the next place holds a larger number, this value is negative
            if i + 1 < len(input_value) and nums[input_value[i + 1]] > value:
                sum_value -= value
            else:
                sum_value += value
        except KeyError:
            raise ValueError(f'input is not a valid Roman numeral: {input_value}')
    # easiest test for validity...
    if int_to_roman(sum_value) == input_value:
        return sum_value
    else:
        raise ValueError(f'input is not a valid Roman numeral: {input_value}')


def nota_to_float(value):
    value = mask_nota(value)
    if value == '':
        return float(0)
    if isinstance(value, int):
        return float(value)
    if isinstance(value, str):
        return float(value.replace(',', '.'))
    return value


def text_to_int(text):
    """
    Retorna um inteiro, convertendo caracteres em seus respectivos valores inteiros.
    Ex: 123 -> 123; A232 -> 65505150
    """
    if text is None:
        return None
    else:
        text = str(text)
        if text.isdigit():
            return int(text)
        else:
            return int(''.join([str(ord(c)) for c in text]))


ext = [
    {
        1: 'um',
        2: 'dois',
        3: 'três',
        4: 'quatro',
        5: 'cinco',
        6: 'seis',
        7: 'sete',
        8: 'oito',
        9: 'nove',
        10: 'dez',
        11: 'onze',
        12: 'doze',
        13: 'treze',
        14: 'quatorze',
        15: 'quinze',
        16: 'dezesseis',
        17: 'dezessete',
        18: 'dezoito',
        19: 'dezenove',
    },
    {2: 'vinte', 3: 'trinta', 4: 'quarenta', 5: 'cinquenta', 6: 'sessenta', 7: 'setenta', 8: 'oitenta', 9: 'noventa'},
    {
        1: 'cento',
        2: 'duzentos',
        3: 'trezentos',
        4: 'quatrocentos',
        5: 'quinhentos',
        6: 'seiscentos',
        7: 'setecentos',
        8: 'oitocentos',
        9: 'novecentos',
    },
]
und = ['', ' mil', (' milhão', ' milhões'), (' bilhão', ' bilhões'), (' trilhão', ' trilhões')]


def cent(s, grand):
    s = '0' * (3 - len(s)) + s
    if s == '000':
        return ''
    if s == '100':
        return 'cem'
    ret = ''
    dez = s[1] + s[2]
    if s[0] != '0':
        ret += ext[2][int(s[0])]
        if dez != '00':
            ret += ' e '
        else:
            return ret + (isinstance(und[grand], tuple) and (int(s) > 1 and und[grand][1] or und[grand][0]) or und[grand])
    if int(dez) < 20:
        ret += ext[0][int(dez)]
    else:
        if s[1] != '0':
            ret += ext[1][int(s[1])]
            if s[2] != '0':
                ret += ' e ' + ext[0][int(s[2])]

    return ret + (isinstance(und[grand], tuple) and (int(s) > 1 and und[grand][1] or und[grand][0]) or und[grand])


def dinheiro_extenso(reais, centavos):
    ret = []
    grand = 0
    if int(centavos) == 0:
        ret.append('zero centavos')
    elif int(centavos) == 1:
        ret.append('um centavo')
    else:
        ret.append(cent(centavos, 0) + ' centavos')
    if int(reais) == 0:
        ret.append('zero reais')
        ret.reverse()
        return ' e '.join([r for r in ret if r])
    elif int(reais) == 1:
        ret.append('um real')
        ret.reverse()
        return ' e '.join([r for r in ret if r])
    while reais:
        s = reais[-3:]
        reais = reais[:-3]
        if grand == 0:
            ret.append(cent(s, grand) + ' reais')
        else:
            ret.append(cent(s, grand))
        grand += 1
    ret.reverse()
    return ' e '.join([r for r in ret if r])


def somar_qtd(lista_de_listas, indice):
    """Soma índice numa lista de listas"""
    soma = Decimal('0.0')
    for item in lista_de_listas:
        value = item[indice]
        if value is not None:
            if isinstance(value, str):
                soma += str_money_to_decimal(value)
            elif isinstance(value, float | int):
                soma += Decimal(str(value))
            elif isinstance(value, Decimal):
                soma += value
    return soma.__int__()


def somar_indice(lista_de_listas, indice):
    """Soma índice numa lista de listas"""
    soma = Decimal('0.0')
    for item in lista_de_listas:
        value = item[indice]
        if value is not None:
            if isinstance(value, str):
                soma += str_money_to_decimal(value)
            elif isinstance(value, float | int):
                soma += Decimal(str(value))
            elif isinstance(value, Decimal):
                soma += value
    return soma


class dExtenso:
    trioextenso: tuple[tuple[str, ...], ...]
    classextenso: tuple[str, ...]

    def __init__(self):
        self.trioextenso = (
            ('dummy', 'um', 'dois', 'três', 'quatro', 'cinco', 'seis', 'sete', 'oito', 'nove'),
            ('dez', 'onze', 'doze', 'treze', 'quatorze', 'quinze', 'dezesseis', 'dezessete', 'dezoito', 'dezenove'),
            ('dummy', 'dummy', 'vinte', 'trinta', 'quarenta', 'cinquenta', 'sessenta', 'setenta', 'oitenta', 'noventa'),
            ('dummy', 'cento', 'duzentos', 'trezentos', 'quatrocentos', 'quinhentos', 'seiscentos', 'setecentos', 'oitocentos', 'novecentos'),
        )
        self.classextenso = (
            'dummy',
            'mil',
            'milh',
            'bilh',
            'trilh',
            'quatrilh',
            'quintilh',
            'sextilh',
            'septilh',
            'octilh',
            'nonilh',
            'decilh',
            'undecilh',
            'duodecilh',
            'tredecilh',
            'quatordecilh',
            'quindecilh',
            'sexdecilh',
            'setedecilh',
            'octodecilh',
            'novedecilh',
            'vigesilh',
        )

    def escrever_trio_extenso(self, trio):
        """
        Retorna um trio por extenso.

        Entrada: trio na forma de string.

        Retorno: trio em extenso.
        """
        saida = []

        if trio == '100':
            # Erro antigo aqui. Consertado usando "return"
            return 'cem'
        elif trio == '000':
            return 'zero'
        else:
            c, d, u = trio
            c, d, u = int(c), int(d), int(u)

            if c != 0:
                saida.append(self.trioextenso[3][c])
            if d == 1:
                saida.append(self.trioextenso[1][u])
            else:
                if d != 0:
                    saida.append(self.trioextenso[2][d])
                if u != 0:
                    saida.append(self.trioextenso[0][u])
        return ' e '.join(saida)

    def nao_e_ultimo_trio(self, totalTrios, contador):
        """
        Retorna verdadeiro se o trio indicado pelo contador
        não é o último (isso é, não é o mais à direita).

        Entrada: Número total de trios e o contador.

        Retorno: Verdadeiro se o trio NÃO é o último e
        falso caso contrário.
        """
        return contador < (totalTrios - 1)

    def trio_a_esquerda_eq_zero(self, trioLista, contador):
        """
        Retorna verdadeiro se o trio à esquerda do trio
        indicado pelo contador é igual a zero.

        Entrada: Os trios em forma de Lista e o contador.

        Retorno: Verdadeiro se o trio à esquerda do contador
        for zero e falso caso contrário.
        """

        # Contador igual a zero indexa o elemento mais à direita,
        # por isso devemos acrescentar tamanho da lista.
        t = len(trioLista) - 1
        return trioLista[t - contador - 1] == '000'

    def getExtenso(self, num, quebradelinhas=0):
        """
        Algoritmo principal. Recebe um número na forma de
        string e retorna sua escrita em extenso.

        Entrada: Número na forma de string e uma flag que, se
        tiver o valor 0 (zero), o extenso é retornado em uma
        só linha. Um valor 1 (um) faz o extenso ser quebrado
        em várias linhas.

        Retorno: O número de entrada em extenso na forma de
        string.
        """

        # Remove os zeros iniciais e faz padding
        # para números com quantidade de algarismos
        # não múltipla de 3
        num = num.lstrip('0')
        pad = 3 - len(num) % 3
        if pad < 3:
            num = '0' * pad + num

        it = iter(num)
        trioLista = [f'{a}{b}{c}' for a, b, c in zip(it, it, it, strict=False)]

        if len(trioLista) > len(self.classextenso):
            raise IndexError('Número muito grande')

        contador = 0
        saida = ''
        extensofinal = ''

        for trio in reversed(trioLista):
            trioInt = int(trio)

            if trioInt > 0:
                saida = self.escrever_trio_extenso(trio)
                if contador > 0:
                    saida = saida + ' ' + self.classextenso[contador]
                if contador > 1:
                    if trioInt > 1:
                        saida = saida + 'ões'
                    else:
                        saida = saida + 'ão'
                if quebradelinhas == 0:
                    if self.nao_e_ultimo_trio(len(trioLista), contador):
                        if self.trio_a_esquerda_eq_zero(trioLista, contador):
                            saida = ' e ' + saida
                        elif trioInt >= 100:
                            saida = ', ' + saida
                        else:
                            saida = ' e ' + saida
                else:
                    saida = saida + '\n'

                extensofinal = saida + extensofinal
            contador = contador + 1
        return extensofinal.rstrip('\n')
