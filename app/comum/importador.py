from operator import itemgetter

from django.core.files.storage import default_storage


def formatar_ref(arquivo_ref):
    """
    Faz a conversão de um arquivo de referencia para uma lista de dicionários.
    As chaves do dicionários serão ser:
        - descricao: nome do campo
        - tipo: tipo do campo
        - tamanho: tamanho tal qual está no arquivo de referencia (ex: 0012 ou 12,2)
        - tamanho_int: tamanho realmente ocupado pelo campo (ex: 12,2 => 14)
        - inicio: posicao inicial do campo
        - fim: posicao final do campo
    >>> print 'Não sei pq estes testes não estão sendo executados...'
    >>> conteudo = ['GR-MATRICULA                            N 0012',
                    'IT-NO-SERVIDOR                          A 0060']
    >>> ref = formatar_ref(conteudo)
    >>> matricula = ref[0]
    >>> matricula['descricao']
    'GR-MATRICULA'
    >>> matricula['tipo']
    'N'
    >>> matricula['tamanho']
    '0012'
    >>> matricula['tamanho_int']
    12
    >>> matricula['inicio']
    0
    >>> matricula['fim']
    12 - isso vai falhar qd for executado
    """
    campos = []
    posicao = 1
    for i in arquivo_ref:
        descricao, tipo, tamanho = i.split()
        tamanho_int = sum(int(n) for n in tamanho.split(','))
        inicio = posicao - 1
        fim = inicio + tamanho_int
        campos.append(
            {'descricao': descricao, 'tipo': tipo, 'tamanho': tamanho, 'tamanho_int': tamanho_int, 'inicio': inicio, 'fim': fim}
        )  # i[41:], # tamanho puro ## Pq não somente tamanho?
        posicao = posicao + tamanho_int
    return campos


def get_itens(ref_filename, txt_filename, order_by=None):
    """
    Faz a conversão do arquivo txt para um lista de dicionario
    """
    itens = []
    if default_storage.exists(ref_filename) and default_storage.exists(txt_filename):
        with default_storage.open(ref_filename, 'rb') as arquivo_ref:
            ref_linhas_b = arquivo_ref.readlines()
        ref_linhas = [linha.decode('utf-8') for linha in ref_linhas_b]

        with default_storage.open(txt_filename, 'rb') as arquivo_txt:
            txt_linhas_b = arquivo_txt.readlines()
        txt_linhas = [linha.decode('utf-8') for linha in txt_linhas_b]

        ref = formatar_ref(ref_linhas)

        for linha in txt_linhas:
            item = {}
            linha = linha.strip()
            for campo in ref:
                valor = linha[campo['inicio'] : campo['fim']].strip()
                item[campo['descricao']] = valor
            itens.append(item)

        if order_by:
            itens = sorted(itens, key=itemgetter(order_by))

    return itens
