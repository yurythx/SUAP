import base64
import functools
import logging
from datetime import timedelta
from difflib import SequenceMatcher
from functools import WRAPPER_ASSIGNMENTS, wraps
from random import choice, randint

from django.conf import settings
from sentry_sdk import capture_exception

from .test import running_tests

logger = logging.getLogger('djtools.utils.python')


def similaridade(a, b):
    """
    Verifica se duas sequências são similares.

    Args:
        a (iterable): sequência comparável.
        b (iterable): sequência comparável.

    Returns:
        Float, entre 0 e 1, que demonstra o grau de similaridade entre as duas sequências.
    """
    return SequenceMatcher(None, a, b).ratio()


def djtools_max(*args):
    """
    Especialização da função built-in que retorna o maior valor de uma lista. Essa implementação ignora valores None.

    Args:
        args: sequência de valores a analisar.

    Returns:
        Maior valor contido na sequência.
    """
    return max(i for i in list(args) if i is not None)


def djtools_min(*args):
    """
    Especialização da função built-in que retorna o menor valor de uma lista. Essa implementação ignora valores None.

    Args:
        args: sequência de valores a analisar.

    Returns:
        Menor valor contido na sequência.
    """
    return min(i for i in list(args) if i is not None)


def silenciar(silenciar_debug=False, return_on_error=None):
    """
    Decorator que captura excessões podendo lançá-las ou não.

    Args:
        silenciar_debug (bool): indica se é para ser silenciada ou não a função;
        return_on_error (): retorno padrão para funções silenciadas.

    Returns:
        Função decorada.
    """

    def receive_function(func):
        @wraps(func, assigned=WRAPPER_ASSIGNMENTS)  # type: ignore[assignment]
        def wrapper(*args, **kwargs):
            if not silenciar_debug and (settings.DEBUG or running_tests()):
                return func(*args, **kwargs)
            try:
                return func(*args, **kwargs)
            except Exception as e:
                capture_exception(e)
                return return_on_error

        return wrapper

    return receive_function


def print_(*msgs):
    logger.info(' '.join([str(msg) for msg in msgs]))


def getattr_coalesce(obj: object, attribute: str, default: object = None):
    for attr in attribute.split('.'):
        obj = getattr(obj, attr, None)
        if not obj:
            break
    return obj if obj is not None else default


def getattrr(obj, args):
    """
    Obtém um atributo de um objeto.

    Args:
        obj (object): objeto base;
        args (string): nome do atributo.
    Returns:
        Atributo solicitado ou string vazia.
    """
    try:
        return getattr_rec(obj, args.split('.'))
    except AttributeError:
        return '-'
    except Exception:
        return '-'


def getattr_rec(obj, args):
    """
    Obtem um atributo de um objeto.

    Args:
        obj (object): objeto base;
        args (list): nome do atributo.

    Returns:
        Atributo solicitado ou string vazia.
    """
    if obj is None:
        return '-'
    if callable(obj):
        obj = obj()
    if len(args) > 1:
        attr = args.pop(0)
        return getattr_rec(getattrr(obj, attr), args)
    else:
        retorno = getattr(obj, args[0])
        if hasattr(retorno, 'all'):
            return ', '.join([str(x) for x in retorno.all()])
        if callable(retorno):
            retorno = retorno()
        return retorno


def random_with_N_digits(n):
    range_start = 10 ** (n - 1)
    range_end = (10**n) - 1
    return randint(range_start, range_end)


def eval_attr(obj, attr):
    """
    Obtem o valor a partir de uma string contendo atrobutos e subatributos.

    Example:
        eval_attr(<Person Túlio>, 'city.country.name') --> 'Brazil'

    Args:
        obj: objeto base para iniciar a busca;
        attr (string): string contendo os atributos na naveação.

    Returns:
        Valor de **attr** com **obj** como base.
    """
    path = attr.split('.')
    current_val = obj
    for node in path:
        if hasattr(current_val, 'get_' + node + '_display'):
            current_val = getattr(current_val, 'get_' + node + '_display')
        elif hasattr(current_val, node):
            current_val = getattr(current_val, node)
        else:
            ''
        if callable(current_val):
            current_val = current_val.__call__()
    return current_val


def randomic(size=10, allowed_chars='abcdefghjkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789'):
    """
    Obtem um string randomica.

    Args:
        size (int): tamanho da string a gerar;
        allowed_chars (string): todos os caracteres que podem ser utilizados.

    Returns:
        String randomica com tamanho solicitado.
    Returns a randomic string.
    """
    return ''.join([choice(allowed_chars) for i in range(size)])


def dict_from_keys_n_values(keys, values):
    """
    Cria um dicionário com base em duas listas.

    Args:
        keys (list): chaves para o dicionário;
        values (list): valores para o dicionário

    Returns:
        Dict baseado nos **keys** e **values**
    """
    assert len(keys) == len(values)
    return dict(zip(keys, values, strict=False))


def group_by(list_of_dicts, group_by_key, sub_group_by_key=None, blank_label=None, as_dict=False):
    if not list_of_dicts:
        return []
    if blank_label is None:
        blank_label = 'Nenhum'
    try:
        list_of_dicts = sorted(list_of_dicts, key=lambda i: str(i[group_by_key]))
    except KeyError:
        pass
    current_group = list_of_dicts[0].get(group_by_key, None) or blank_label
    grouped = [{'group': current_group, 'items': []}]

    for item in list_of_dicts:
        value = item.get(group_by_key, None) or blank_label
        if value != current_group:  # create a new group
            current_group = value
            grouped.append({'group': current_group, 'items': [item]})
        else:  # an existing group
            grouped[-1]['items'].append(item)

    if sub_group_by_key:
        for g in grouped:
            g['subgroups'] = group_by(g['items'], sub_group_by_key)

    if as_dict:
        grouped_as_dict = {}
        for g in grouped:
            subgroups_as_dict = {}
            for s in g['subgroups']:
                subgroups_as_dict[s['group']] = s
            g['subgroups_as_dict'] = subgroups_as_dict
            grouped_as_dict[g['group']] = g
        return grouped_as_dict

    return grouped


def sub_instances(instance):
    """
    Obtem todas as sub instâncias de um objeto de modelo.

    Args:
        instance (Model): instância a processar.

    Returns:
        Lista com as instãncias das sub instâncias.
    """

    def inner(instance, children=None):
        if children is None:
            children = []
        children.append(instance)
        fields = [f for f in instance._meta.get_fields() if (f.one_to_many or f.one_to_one) and f.auto_created]
        for field in fields:
            try:
                if issubclass(field.related_model, instance._meta.model) or issubclass(instance._meta.model, field.related_model):
                    obj = getattr(instance, field.name)
                    if obj not in children:
                        inner(obj, children)
            except Exception:
                pass
        return list(set(children))

    return inner(instance, [])


def b64encode(content):
    """
    Método que converte um conteúdo original para um conteúdo base 64.

    Args:
        content: string ou byte

    Raises:
        Exception caso o **content_64** não seja um string ou bytes.

    Returns:
        String na base b4 caso o parâmetro de entrada seja uma string e byte na base 64 caso o parâmetro de
        entrada seja bytes.
    """
    if isinstance(content, str):
        return base64.b64encode(content.encode()).decode()
    elif isinstance(content, bytes):
        return base64.b64encode(content)
    else:
        raise Exception('O método b64encode só aceita como parâmetro de entrada uma String ou Bytes.')


def b64decode(content_b64):
    """
    Método que converte um conteúdo base 64 para o conteúdo original.

    Args:
        content_b64 (string): string base 64 ou bytes na base 64

    Raises:
        Exception caso o **content_64** não seja um string ou bytes.

    Returns:
        String "original" caso o parâmetro de entrada seja uma string base 64 e byte "original" caso caso o parâmetro
        de entrada seja bytes base 64.
    """
    if isinstance(content_b64, str):
        return base64.b64decode(content_b64.encode()).decode()
    elif isinstance(content_b64, bytes):
        return base64.b64decode(content_b64)
    else:
        raise Exception('O método b64decode só aceita como parâmetro de entrada String ou Bytes.')


def rgetattr(obj, attr, *args):
    """
    Obtem um atributo pertence a um objeto de forma recursiva.

    Args:
        obj (object): objeto base para pesquisa;
        attr (string): atributo a ser pesquisado, formato: atributo.atributo.atributo ...;
        args: (): argumentos extras

    Returns:
        Atributo seguindo a pesquisa por attr em obj.
    """

    def _getattr(obj, attr):
        try:
            return getattr(obj, attr, *args)
        except Exception:
            return None

    return functools.reduce(_getattr, [obj, *attr.split('.')])


def rhasattr(obj, attr, *args):
    """
    Verifica se um atributo pertence a um objeto de forma recursiva.

    Args:
        obj (object): objeto base para pesquisa;
        attr (string): atributo a ser pesquisado, formato: atributo.atributo.atributo ...;
        args: (): argumentos extras

    Returns:
        True se existir o atributo.
    """

    def _hasattr(obj, attr):
        return hasattr(obj, attr, *args)

    return functools.reduce(_hasattr, [obj, *attr.split('.')])


def diferenca_listas(lista1, lista2):
    return list(set(lista1).difference(set(lista2)))


class Relatorio:
    @staticmethod
    def _soma(*args):
        if not args:
            return 0
        else:
            return sum(args)

    @staticmethod
    def _transposta(ltabela):
        """
        Realiza a transpostar de uma tabela (lista de lista)
        """
        return list(map(list, zip(*ltabela, strict=False)))

    @classmethod
    def get_dados_em_coluna_linha(cls, lista_de_dict, cabecalho, nome_coluna, nome_linha, nome_valor, adiciona_e_totaliza=False):
        """
        Recebe uma lista de dicionário ({'nome_coluna':'', 'nome_linha':'', 'nome_valor':0.0},)
        Converte o dicionário em uma tabela (lista de lista), onde o primeiro item é nome_linha e
        os demais são os valores correspondentes aos itens de lista_cabecalho

        lista_cabecalho é passada por referência, ela é prenchida com os valores de nome_coluna
        presentes no dicionário lista_de_dict
        """
        # Cria uma lista com os estados sem repetição
        for ditem in lista_de_dict:
            try:
                cabecalho.index(ditem[nome_coluna])
            except ValueError:
                cabecalho.append(ditem[nome_coluna])

        # Adiciona o valor para cada nome_coluna e nome_linha
        ltabela_aux = []
        for ditem in lista_de_dict:
            nomeLinha = ditem[nome_linha]
            llinha = cls._find(nomeLinha, ltabela_aux)
            nova_linha = False
            if not llinha:
                # cria uma linha vazia com len(cabecalho)+1 colunas
                llinha = [0.0] * (len(cabecalho) + 1)
                llinha[0] = nomeLinha
                nova_linha = True
            try:
                index = cabecalho.index(ditem[nome_coluna])
                llinha[index + 1] += float(ditem[nome_valor])
            except ValueError:
                pass
            if nova_linha:
                ltabela_aux.append(llinha)

        # adiciona em ltabela somente se existir produção, ou seja,, no mínimo, um item ser diferente de zero.
        ltabela = []
        for litem in ltabela_aux:
            if any(i > 0 for i in litem[1:]):
                ltabela.append(litem)

        if adiciona_e_totaliza:
            Relatorio.adiciona_e_totaliza_coluna(ltabela)
            cabecalho.append('Total')

        return ltabela

    @classmethod
    def _find(cls, item, lista):
        for valor in lista:
            if valor[0] == item:
                return valor
        return None

    @classmethod
    def adiciona_e_totaliza_coluna(cls, ltabela, lfunctabela=None):
        """
        Adiciona uma nova coluna na tabela ltabela
        Parâmetros:
            lfunctabela : uma lista de lista, representa uma tabela com num_colunaslista
            lfunctabela: formato [funcao, 1,2], onde:
                funcao: é um ponteiro para função
                demais itens, refere-se as colunas que serão calculadas com a fórmula funcao
        """
        if not ltabela:
            return

        for linha in ltabela:
            if lfunctabela:
                # Extrai os valores das colunas a serem calculadas
                lcoluna = [linha[col] for col in lfunctabela[1:]]
                # Aplica a função e adiciona o resultado à linha
                linha.append(round(lfunctabela[0](*lcoluna), 2))
            else:
                # Soma os valores das colunas (excluindo a primeira) e adiciona o resultado à linha
                linha.append(round(cls._soma(*linha[1:]), 2))

    @classmethod
    def adiciona_nova_coluna(cls, ltabela, lresultados, dic_values, num_colunas):
        """
        Adiciona ou edita uma coluna na tabela.

        Recebe os seguintes parâmetros:
        ltabela : uma lista de lista, representa uma tabela com num_colunaslista
        lresultados: lista a ser inserida na tabela, cada item de lresultados é uma linha na tabela
        dic_values: dicionário (chave, valor), onde chave representa a coluna (índice da nova coluna a ser inserida na ltabela)
                    e valor representa o valor (índice de lresultados[0] da célula da ltabela.
        num_colunas: é o número de colunas da tabela, istó é, o número de itens da lista.
        """
        if lresultados:
            for item in lresultados:
                llinha = cls._find(item[0], ltabela)
                nova_linha = False
                if not llinha:
                    # cria uma linha vazia com num_colunas
                    llinha = [0.0] * num_colunas
                    llinha[0] = item[0]
                    nova_linha = True
                for k, v in list(dic_values.items()):
                    # linha na tabela já existe, atualiza os valures das colunas
                    llinha[k] = float(item[v])
                if nova_linha:
                    ltabela.append(llinha)

    @classmethod
    def get_linha_total(cls, ltabela, dic_execfunc=None):
        """
        ltabela: (lista de lista)
        Recebe dic_execfunc no formato {1:soma,2:mult, 3:media}, onde a
        chave é o índice de ltabela[linha] e o valor e o ponteiro para função.
        Exemplo:
            lt = [['a',5,10,15], ['b', 2, 4, 6]]
            get_linha_total(lt,{1:media, 2:mult}), retorno = [3.5, 40, 21)
            onde:
                3.5 é a media dos itens da 1ª coluna
                40 é a multicplicação dos itens da 2ª coluna
                21 é o padrão, isto é a soma dos itens para cada coluna restante
        """
        if ltabela:
            ltabela_inversa = cls._transposta(ltabela)
            num_colunas = len(ltabela[0])
            ltotal = [0.0] * num_colunas
            ltotal[0] = 'TOTAL'
            for icol in range(1, len(ltabela_inversa)):
                if dic_execfunc and dic_execfunc.get(icol, None):
                    execfunc = dic_execfunc.get(icol, None)
                    ltotal[icol] = execfunc(*ltabela_inversa[icol])
                else:
                    ltotal[icol] = cls._soma(*ltabela_inversa[icol])
            return ltotal

    @classmethod
    def ordernar(cls, dados, funcao=lambda e: e[0]):
        return sorted(dados, key=funcao)


def agrupar_em_pares(lista):
    """
    [0, 1, 2, 3, 4, 5, 6] --> [[0, 1], [2, 3], [4, 5], [6]]
    """
    lista_pares = []
    for index, item in enumerate(lista):
        if index % 2 == 0:
            lista_pares.append([item])
        else:
            lista_pares[-1].append(item)
    return lista_pares


def existe_conflito_entre_intervalos(datas):
    datas = agrupar_em_pares(datas)

    for data in datas:
        dataInicioIntervalo = data[0]
        dataFimIntervalo = data[1]

        for data2 in datas:
            if data != data2:
                dataInicioIntervalo2 = data2[0]
                dataFimIntervalo2 = data2[1]

                if dataInicioIntervalo >= dataInicioIntervalo2 and dataInicioIntervalo <= dataFimIntervalo2:
                    return True

                if dataFimIntervalo >= dataInicioIntervalo2 and dataFimIntervalo <= dataFimIntervalo2:
                    return True
    return False


def ha_choque_de_periodo(lista_periodos, periodo_teste, retornar_periodo_choque=False):
    """
    lista_periodos = ((data1, data2),(data1, data2),...)
    periodo_teste = (data1, data2)

            A---------B
     C-----D     OU    C-----D

     (D < A) OU (C > B) --> O período C---D não conflita.

     retorna True/False + o período de "choque"

    """
    ha_choque = False
    periodo_choque_data_inicio = None
    periodo_choque_data_fim = None
    for d1, d2 in lista_periodos:
        if not (periodo_teste[1] < d1 or periodo_teste[0] > d2):
            ha_choque = True
            periodo_choque_data_inicio = d1
            periodo_choque_data_fim = d2
            break  # sai na primeira ocorrência

    if retornar_periodo_choque:
        return ha_choque, periodo_choque_data_inicio, periodo_choque_data_fim
    else:
        return ha_choque


def periodos_sucessivos(periodos):
    """
    periodos = ((date inicial, date final), (date inicial, date final), ... )

    retorna
        FALSE e uma lista de mensagens referentes a:
            - dias conflitantes (sobreposição de períodos)
            - dias descobertos (períodos não sucessivos)
            - períodos com datas inválidas (datas nulas ou data inicial > data final)

        TRUE e sem mensagens.
    """
    lista_mensagens = []

    # dias do periodo completo, considerando todos os periodos
    datas = {}  # datas = {'20141016': 16/10/2014, ...}
    for periodo in periodos:
        # periodo = (data inicial, data final)
        data_inicio = periodo[0]
        data_fim = periodo[1]

        if data_inicio:
            dia_key = data_inicio.strftime('%Y%m%d')
            datas[dia_key] = data_inicio

        if data_fim and (data_fim != data_inicio):
            dia_key = data_fim.strftime('%Y%m%d')
            datas[dia_key] = data_fim

    # menor data e maior data entre os dias do período completo
    menor_data = min(datas.values())
    maior_data = max(datas.values())
    if menor_data and maior_data:
        dias_do_periodo_completo = [menor_data + timedelta(days=dia) for dia in range((maior_data - menor_data).days + 1)]

        dias_do_periodo_completo_ocorrencias = {}
        for dia_do_periodo_completo in dias_do_periodo_completo:
            dia_key = dia_do_periodo_completo.strftime('%Y%m%d')
            if dia_key not in dias_do_periodo_completo_ocorrencias:
                dias_do_periodo_completo_ocorrencias[dia_key] = 0  # inicializa a qtde de ocorrencias da data

        # contabiliza os dias e testa períodos inválidos
        for periodo in periodos:
            # periodo = (data inicial, data final)
            data_inicio = periodo[0]
            data_fim = periodo[1]

            if data_inicio:
                dia_key = data_inicio.strftime('%Y%m%d')
                dias_do_periodo_completo_ocorrencias[dia_key] += 1  # dia coberto

            if data_fim and (data_fim != data_inicio):
                dia_key = data_fim.strftime('%Y%m%d')
                dias_do_periodo_completo_ocorrencias[dia_key] += 1  # dia coberto

            if data_inicio and data_fim:  # período com as 2 datas definidas
                if data_inicio > data_fim:
                    lista_mensagens.append(
                        'O período {} a {} tem data final menor que a data inicial. '.format(
                            data_inicio.strftime('%d/%m/%Y'), data_fim.strftime('%d/%m/%Y')
                        )
                    )
                else:
                    dias_do_periodo = [data_inicio + timedelta(days=dia) for dia in range((data_fim - data_inicio).days + 1)]
                    for dia_do_periodo in dias_do_periodo:
                        # datas limites do período já "testadas" acima
                        if dia_do_periodo != data_inicio and dia_do_periodo != data_fim:
                            dia_key = dia_do_periodo.strftime('%Y%m%d')
                            dias_do_periodo_completo_ocorrencias[dia_key] += 1  # dia coberto
            else:
                if data_inicio:
                    lista_mensagens.append('O período que se inicia em {} não tem data final. '.format(data_inicio.strftime('%d/%m/%Y')))
                else:
                    lista_mensagens.append('Há períodos sem datas definidas. ')

        # dias/períodos descobertos e dias/período conflitantes
        periodo_descoberto_data_inicial = None
        periodo_descoberto_qtd_dias = 0
        periodo_descoberto_data_fim = None
        periodo_conflitante_data_inicial = None
        periodo_conflitante_qtd_dias = 0
        periodo_conflitante_data_fim = None
        for dia_do_periodo_completo in dias_do_periodo_completo:
            dia_key = dia_do_periodo_completo.strftime('%Y%m%d')

            # dias/períodos descobertos
            if dias_do_periodo_completo_ocorrencias[dia_key] == 0:
                if not periodo_descoberto_data_inicial:
                    periodo_descoberto_data_inicial = dia_do_periodo_completo
                    periodo_descoberto_qtd_dias = 0
                    periodo_descoberto_data_fim = None
                else:
                    periodo_descoberto_qtd_dias += 1
                    dentro_do_mesmo_periodo = (dia_do_periodo_completo - periodo_descoberto_data_inicial).days == periodo_descoberto_qtd_dias

                    if dentro_do_mesmo_periodo:
                        periodo_descoberto_data_fim = dia_do_periodo_completo
                    else:
                        if periodo_descoberto_data_fim:
                            lista_mensagens.append(
                                'O período {} a {} está descoberto. '.format(
                                    periodo_descoberto_data_inicial.strftime('%d/%m/%Y'), periodo_descoberto_data_fim.strftime('%d/%m/%Y')
                                )
                            )
                        else:
                            lista_mensagens.append('O dia {} está descoberto. '.format(periodo_descoberto_data_inicial.strftime('%d/%m/%Y')))

                        # inicia novo período
                        periodo_descoberto_data_inicial = dia_do_periodo_completo
                        periodo_descoberto_qtd_dias = 0
                        periodo_descoberto_data_fim = None

            # dias/período conflitantes
            if dias_do_periodo_completo_ocorrencias[dia_key] > 1:
                if not periodo_conflitante_data_inicial:
                    periodo_conflitante_data_inicial = dia_do_periodo_completo
                    periodo_conflitante_qtd_dias = 0
                    periodo_conflitante_data_fim = None
                else:
                    periodo_conflitante_qtd_dias += 1
                    dentro_do_mesmo_periodo = (dia_do_periodo_completo - periodo_conflitante_data_inicial).days == periodo_conflitante_qtd_dias

                    if dentro_do_mesmo_periodo:
                        periodo_conflitante_data_fim = dia_do_periodo_completo
                    else:
                        if periodo_conflitante_data_fim:
                            lista_mensagens.append(
                                'O intervalo de {} a {} está sendo usado em mais de um período. '.format(
                                    periodo_conflitante_data_inicial.strftime('%d/%m/%Y'), periodo_conflitante_data_fim.strftime('%d/%m/%Y')
                                )
                            )
                        else:
                            lista_mensagens.append(
                                'O dia {} está sendo usado em mais de um período. '.format(periodo_conflitante_data_inicial.strftime('%d/%m/%Y'))
                            )

                        # inicia novo período
                        periodo_conflitante_data_inicial = dia_do_periodo_completo
                        periodo_conflitante_qtd_dias = 0
                        periodo_conflitante_data_fim = None

        # é possível que tenha se iniciado a contagem de um período descoberto sem tê-lo concluído
        if periodo_descoberto_data_inicial:
            if periodo_descoberto_data_fim:
                lista_mensagens.append(
                    'O período {} a {} está descoberto. '.format(
                        periodo_descoberto_data_inicial.strftime('%d/%m/%Y'), periodo_descoberto_data_fim.strftime('%d/%m/%Y')
                    )
                )
            else:
                lista_mensagens.append('O dia {} está descoberto. '.format(periodo_descoberto_data_inicial.strftime('%d/%m/%Y')))

        # é possível que tenha se iniciado a contagem de um período conflitante sem tê-lo concluído
        if periodo_conflitante_data_inicial:
            if periodo_conflitante_data_fim:
                lista_mensagens.append(
                    'O intervalo de {} a {} está sendo usado em mais de um período.'.format(
                        periodo_conflitante_data_inicial.strftime('%d/%m/%Y'), periodo_conflitante_data_fim.strftime('%d/%m/%Y')
                    )
                )
            else:
                lista_mensagens.append(
                    'O dia {} está sendo usado em mais de um período. '.format(periodo_conflitante_data_inicial.strftime('%d/%m/%Y'))
                )
    else:
        lista_mensagens.append('Períodos sem datas definidas. ')

    if lista_mensagens:
        return False, lista_mensagens
    else:
        return True, []


def get_values_from_choices(choice_keys, choices):
    """
    Retorna o valor amigável de um item, ou vários itens, de um choices
    Obs: Caso você queira apenar o valor amigável de um campo do models seu usa CHOICES, basta fazer "model.get_campo_display()"

    Exemplo:

    NIVEL_ACESSO_SIGILOSO = 1
    NIVEL_ACESSO_RESTRITO = 2
    NIVEL_ACESSO_PUBLICO = 3
    NIVEL_ACESSO_CHOICES = (
        (NIVEL_ACESSO_SIGILOSO, u'Sigiloso'),
        (NIVEL_ACESSO_RESTRITO, u'Restrito'),
        (NIVEL_ACESSO_PUBLICO, u'Público'),
    )
    print get_value_from_choices(NIVEL_ACESSO_SIGILOSO, NIVEL_ACESSO_CHOICES)
    >>> Sigiloso

    print get_value_from_choices([NIVEL_ACESSO_SIGILOSO, NIVEL_ACESSO_RESTRITO], NIVEL_ACESSO_CHOICES)
    >>> [Sigiloso, Restrito]

    :param choice_keys: um chave ou várias chaves do choices
    :param choices: choices que contém as chaves e valores

    :return: uma string caso choice_keys seja apenas uma key ou uma lista de strings caso choice_keys seja uma lista de keys.
    """
    choices_as_dict = dict(choices)

    if type(choice_keys) is list:
        result = []
        for key in choice_keys:
            result.append(choices_as_dict[key])
        return result
    else:
        return choices_as_dict[choice_keys]
