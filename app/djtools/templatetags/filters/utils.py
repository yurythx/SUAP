import base64
import math
import os
import re
from datetime import date, datetime, timedelta
from decimal import Decimal

from dateutil.relativedelta import relativedelta
from django import template
from django.apps import apps
from django.conf import settings
from django.db.models import QuerySet
from django.template.defaultfilters import pluralize
from django.utils.html import escape, format_html
from django.utils.safestring import SafeText, mark_safe
from django.utils.translation import gettext_lazy as _

from comum.utils import tl
from djtools.choices import campos
from djtools.utils import anonimizar_cpf as anonimizador_cpf
from djtools.utils import (
    CASAS_DECIMAIS_ALMOX,
    anonymize,
    data_extenso,
    dinheiro_extenso,
    formata_segundos,
    getattrr,
    int_to_roman,
    mask_money,
    mask_nota,
    mask_numbers,
    normalizar_nome_proprio,
    split_thousands,
    decimal_para_str,
    to_ascii,
)

register = template.Library()


@register.filter(name='length')
def length(value):
    """
    Filtro que retorna o tamanho do conjunto passado.

    Args:
        value (): elemento a ser contado.

    Returns:
        Int com o tamanho de **value**.

    Note:
        O value pode ser um list, um dict ou um Queryset.
    """
    if issubclass(type(value), QuerySet):
        return value.count()
    try:
        return len(value)
    except ValueError, TypeError:
        return 0


@register.filter
def getval(form, key):
    """
    Obtem o valor para uma chave em um dicionário.

    Args:
        form (dict): dicionário;
        key (string): chave de pesquisa do elemento.

    Returns:
         Valor contido em **key** no dicionário passado.
    """
    return form[key]


@register.filter
def getval_label(form, key):
    """
    Obtem o **label** de um field em um formuário.

    Args:
        form (Forms): formulário;
        key (string): nome do campo.

    Returns:
         String com o **label** do campo.
    """
    return form[key].label


@register.filter
def set_periodo_letivo_referencia(obj, periodo_letivo):
    """
    Atribui o **periodo_letivo** para o **obj**.

    Args:
        obj (Model): objeto de modelo;
        periodo_letivo (): período letivo.

    Returns:
        String vazia.
    """
    if periodo_letivo and int(periodo_letivo):
        obj.periodo_letivo_referencia = periodo_letivo
    return ''


@register.filter
def set_ano_letivo_referencia(obj, ano_letivo):
    """
    Atribui o **ano_letivo** para o **obj**.

    Args:
        obj (Model): objeto de modelo;
        periodo_letivo (): ano letivo.

    Returns:
        String vazia.
    """
    if ano_letivo:
        obj.ano_letivo_referencia = ano_letivo
    return ''


@register.filter
def validjs_symbol(str):
    """
    Retira caracteres que são problemáricos no javascript.

    Args:
        str (string): texto a ser processado.

    Returns:
        String com **str** sem caracters.
    """
    return str.replace('-', '')


@register.filter
def seconds_to_timedelta(seconds):
    """
    Converte segundos para um **timedelta**.

    Args:
        seconds: quantidade de segundos.

    Returns:
        Timedelta.
    """
    return timedelta(seconds=seconds)


@register.filter
def hours_to_timedelta(hours):
    """
    Converte horas para um **timedelta**.

    Args:
        hours: quantidade de horas.

    Returns:
        Timedelta.
    """
    return timedelta(hours=hours or 0)


@register.filter
def seconds_to_hours(seconds):
    """
    Converte segundos para **horas**.

    Args:
        seconds: quantidade de segundos.

    Returns:
        Hours.
    """
    return (seconds or 0) / 3600


@register.filter
def format_timedelta(delta):
    """
    Formata um **timedelta**.

    Args:
        delta: delta a ser formatada.

    Returns:
        String formatada.

    Notes:
        Filtro utilizado em **format_**.
    """
    if delta.days < -3650:
        delta = timedelta(days=-3650)
    return timesince(datetime(1980, 1, 1), datetime(1980, 1, 1) + delta)


@register.filter(is_safe=True)
def format_bool(value, html=True):
    """
    Formata um **bool**.

    Args:
        value (bool): boolean a formatar;
        html (bool): indica se o formato de saída deve ser **HTML**.

    Returns:
        String contendo 'Sim' ou 'Não' de acordo com o bool.

    Notes:
        Filtro utilizado em **format_**.
    """
    if html:
        css_class = 'success' if value else 'error'
        texto = 'Sim' if value else 'Não'
        return format_html('<span class="status status-{}">{}</span>', css_class, texto)
    return value and 'Sim' or 'Não'


@register.filter(is_safe=True)
def format_datetime(value):
    """
    Formata um **datetime**.

    Args:
        value: datetime a ser formatada.

    Returns:
        String formatada.

    Notes:
        Filtro utilizado em **format_**.
    """
    try:
        if hasattr(value, 'time'):
            return value.strftime('%d/%m/%Y %H:%M:%S')
        else:
            return value.strftime('%d/%m/%Y')
    except ValueError:
        return value
    except Exception:
        return '-'


@register.filter(is_safe=True)
def format_data_extenso(value):
    """
    Formata um **datetime**.

    Args:
        value: datetime a ser formatada.

    Returns:
        String data por extenso.
    """
    if value is None:
        return '-'
    return data_extenso(value)


@register.filter(is_safe=True)
def format_integer(value):
    return format_money(value).replace(',00', '')


@register.filter(is_safe=True)
def format_money(value):
    """
    Formata um **money**.

    Args:
        value: valor a ser formatada.

    Examples:
        format_money(1) -> '1,00'
        format_money(1000) -> '1.000,00'
        format_money(1000.99) -> '1.000,99'

    Returns:
        String formatada.

    Notes:
        Filtro utilizado em **format_**.
    """
    if value not in [None, '']:
        if value == Decimal(0):
            return '0,00'
        value = decimal_para_str(value)
        if '.' in value:
            reais, centavos = value.split('.')
            if len(centavos) > 2:
                centavos = centavos[0:2]
        else:
            reais = value
            centavos = '00'
        reais = split_thousands(reais)
        return str(reais + ',' + centavos)
    return '-'


@register.filter(is_safe=True)
def format_money_almox(value):
    """
    Formata um **money** de almoxarifado/patrimônio preservando a precisão extra.

    Ao contrário de **format_money**, que trunca em 2 casas decimais, mantém as casas
    decimais adicionais usadas nos valores unitários de almoxarifado e patrimônio,
    descartando apenas os zeros à direita e garantindo o mínimo de 2 casas. Valores com
    mais de ``CASAS_DECIMAIS_ALMOX`` casas — típicos de totais (``qtd`` com 5 casas
    multiplicada por ``valor`` com 6 casas) — são truncados, sem arredondamento,
    como em **format_money**.

    Args:
        value: valor a ser formatado.

    Examples:
        format_money_almox(1) -> '1,00'
        format_money_almox(Decimal('1000.50000')) -> '1.000,50'
        format_money_almox(Decimal('1.123456')) -> '1,123456'
        format_money_almox(Decimal('900.98446775458')) -> '900,984467'

    Returns:
        String formatada.

    Notes:
        Uso restrito aos módulos **almoxarifado** e **patrimonio**; os demais módulos
        devem continuar usando **format_money**.
    """
    if value in (None, ''):
        return '-'
    if value == Decimal(0):
        return '0,00'
    value = decimal_para_str(value)
    if '.' in value:
        reais, centavos = value.split('.')
        centavos = centavos[:CASAS_DECIMAIS_ALMOX].rstrip('0').ljust(2, '0')
    else:
        reais = value
        centavos = '00'
    return f'{split_thousands(reais)},{centavos}'


@register.filter(name='format_quantity', is_safe=True)
def format_quantity(value):
    """
    Formata uma **quantidade** no padrão brasileiro, sem casas decimais desnecessárias.

    Examples:
        format_quantity(Decimal('5.00000')) -> '5'
        format_quantity(Decimal('1.50000')) -> '1,5'
        format_quantity(Decimal('1.12345')) -> '1,12345'
        format_quantity(3) -> '3'
    """
    if value in (None, ''):
        return '-'
    value_str = decimal_para_str(value)
    if '.' in value_str:
        inteiro, decimal = value_str.split('.')
        decimal = decimal.rstrip('0')
    else:
        inteiro = value_str
        decimal = ''
    inteiro = split_thousands(inteiro)
    return f'{inteiro},{decimal}' if decimal else inteiro


@register.filter(is_safe=True)
def format_money_with_sign(value):
    """
    Formata um **money**.

    Args:
        value: valor a ser formatada.

    Returns:
        String formatada.

    Notes:
        Filtro utilizado em **format_**.
    """
    if value not in [None, '']:
        return f'R$ {format_money(value)}'
    return '-'


@register.filter(name='format_iterable')
def format_iterable(value, middle_separator=', ', final_separator=None):
    """
    Formata um iterável.

    Args:
        value: valor a ser formatada;
        middle_separator (string): separador de itens;
        final_separator (string): separador para o último item.

    Examples:
        format_iterable([1]) -> '1'
        format_iterable([1, 2]) -> '1 e 2'
        format_iterable([1, 2, 3]) -> '1, 2 e 3'

    Returns:
        String formatada.

    Notes:
        Filtro utilizado em **format_**.
    """
    if not final_separator:
        final_separator = _('and')
    values = []
    for i in value:
        if isinstance(i, bytes):
            values.append(i.decode())
        else:
            values.append(str(format_(i)))
    if len(value) == 0:
        return '-'
    if len(value) == 1:
        return values[0]
    else:
        return f'{middle_separator.join(values[:-1])} {final_separator} {values[-1]}'


@register.filter(name='format_daterange')
def format_daterange(value1, value2):
    """
    Formata um intervalo de datas.

    Args:
        value1 (datetime): data inicial do intervalo;
        value2 (datetime): data final do intervalo;

    Returns:
        String formatada.

    Notes:
        Filtro utilizado em **format_**.
    """
    return f'{format_datetime(value1)} a {format_datetime(value2)}'


@register.filter
def format_user(obj, nome=None, photo=False):
    """
    Formata um objeto **usuario**.

    Args:
        obj (User|Vinculo|Servidor|PrestadorServico|Aluno): objeto *usuario*;
        nome (string): nome do usuário.

    Returns:
        String formatada.

    Notes:
        Filtro utilizado em **format_**.
    """
    # obj: id da pessoa física
    User = apps.get_model('comum', 'User')
    Vinculo = apps.get_model('comum', 'Vinculo')
    PrestadorServico = apps.get_model('comum', 'PrestadorServico')
    Servidor = apps.get_model('rh', 'Servidor')

    list_vinculos = [Servidor, PrestadorServico, Vinculo]
    if 'edu' in settings.INSTALLED_APPS:
        Aluno = apps.get_model('edu', 'Aluno')
        list_vinculos.append(Aluno)

    user = None
    nome = ''
    if isinstance(obj, str):
        profile_id = obj
    else:
        if isinstance(obj, User):
            user = obj
        elif type(obj) in list_vinculos:
            user = obj.get_user()
        if user:
            profile_id = user.uuid
            if hasattr(user, 'get_profile') and user.get_profile():
                nome = user.get_profile().nome_social or user.get_profile().nome_usual or user.get_profile().nome
            else:
                return user.get_full_name()
        else:
            if hasattr(obj, 'username'):
                profile_id = hasattr(obj, 'uuid') and obj.uuid or obj.pessoa_fisica.uuid
                nome = obj.username
            elif getattr(obj, 'eh_pessoaexterna', False):
                return mark_safe(f"""
                    <a href="{obj.relacionamento.get_absolute_url()}">{normalizar_nome_proprio(obj.pessoa.nome)} - Pessoa Externa</a>
                """)
            else:
                return mark_safe(f"""
                    <a href="{obj.get_absolute_url()}">{normalizar_nome_proprio(obj.pessoa_fisica.nome)}</a>
                """)

    absolute_url = '#'
    nome = nome or '-'
    if user:
        absolute_url = user.get_relacionamento() and user.get_relacionamento().get_absolute_url()
    if photo and user:
        v = user.get_vinculo()
        foto_url = v.get_foto_75x100_url() if v else '/static/comum/img/default.jpg'
        return mark_safe(
            f"""<a href="{absolute_url}" class="person smallest popup-user-trigger" data-user-id="{profile_id}">
                    <div class="photo-circle smallest">
                        <img src="{foto_url}" alt="Foto de {normalizar_nome_proprio(nome)}">
                    </div>
                    {normalizar_nome_proprio(nome)}
                </a>"""
        )
    else:
        return mark_safe(
            f"""<div class="popup-user">
                    <a href="{absolute_url}" class="popup-user-trigger" data-user-id="{profile_id}">{normalizar_nome_proprio(nome)}</a>
                </div>"""
        )


@register.filter
def format_user_with_photo(obj):
    return format_user(obj, nome=None, photo=True)


@register.filter
def format_image(value):
    return mark_safe(f'<div class="photo-circle"><img src={value}/></div>')


@register.filter
def index(indexable, i):
    return indexable[int(i)]


@register.filter
def classname(obj):
    return obj.__class__._meta.verbose_name


def _get_perfil(obj: object) -> object | None:
    """Pessoa concreta (física ou jurídica) que ``obj`` representa, ou ``None`` se ``obj`` não for pessoa nem vínculo."""
    Pessoa = apps.get_model('rh', 'Pessoa')
    PessoaFisica = apps.get_model('rh', 'PessoaFisica')
    PessoaJuridica = apps.get_model('rh', 'PessoaJuridica')
    Vinculo = apps.get_model('comum', 'Vinculo')

    # Antes do ramo de Pessoa, do qual são subclasses: nelas o descritor reverso ``pessoafisica``/``pessoajuridica``
    # iria ao banco só para devolver a mesma linha (#17700).
    if isinstance(obj, PessoaFisica | PessoaJuridica):
        return obj
    if isinstance(obj, Pessoa):
        if hasattr(obj, 'pessoafisica'):
            return obj.pessoafisica
        if hasattr(obj, 'pessoa_fisica'):
            return obj.pessoa_fisica
        if hasattr(obj, 'pessoajuridica'):
            return obj.pessoajuridica
        return None
    if isinstance(obj, Vinculo):
        return obj.pessoa
    return None


@register.filter
def format_profile(obj: object, nome: str | None = None) -> str:
    """
    Formata um objeto **Profile**.

    Args:
        obj (Profile): objeto *Profile*;
        nome (string): nome do usuário.

    Returns:
        String formatada.

    Notes:
        Filtro utilizado em **format_**.
    """
    # obj: id da pessoa física
    PessoaJuridica = apps.get_model('rh', 'PessoaJuridica')

    profile = None
    if isinstance(obj, str):
        profile_id = obj
    else:
        profile = _get_perfil(obj)
        if profile:
            if hasattr(profile, 'pessoa'):
                profile_id = profile.pessoa.uuid
            else:
                profile_id = profile.uuid
            nome = profile.nome_usual or profile.nome
            if isinstance(profile, PessoaJuridica):
                nome = str(profile)
        else:
            profile_id = obj.uuid
            nome = obj.username
    #
    user = tl.get_user()
    if user and user.is_anonymous:
        return normalizar_nome_proprio(nome)
    nome = nome or '-'
    return mark_safe(
        f"""<div class="popup-profile">
                <a href="#" class="popup-profile-trigger" data-profile-id="{profile_id}">{normalizar_nome_proprio(nome)}</a>
            </div>"""
    )


@register.filter(is_safe=True)
def format_phone(value):
    """
    Formata uma string no formato de telefone.

    Args:
        value (string): número a ser formatado.

    Returns:
        String formatada.

    Notes:
        Filtro utilizado em **format_**.
    """
    try:
        non_decimal = re.compile(r'[^\d.]+')
        numero = non_decimal.sub('', value)
        if len(numero) == 11:
            return f'({numero[0:2]}) {numero[2:7]}-{numero[7:11]}'
        elif len(numero) == 10:
            return f'({numero[0:2]}) {numero[2:6]}-{numero[6:10]}'
        else:
            return value
    except ValueError:
        return value


@register.filter(is_safe=True)
def format_permission(value):
    """
    Formata/Traduz um valor para uma string de permission.

    Args:
        value (string): string da permission.

    Returns:
        String formatada.

    Notes:
        Filtro utilizado em **format_**.
    """
    if 'Can add' in value:
        return 'Pode adicionar{}'.format(value.split('Can add')[1])
    elif 'Can change' in value:
        return 'Pode gerenciar{}'.format(value.split('Can change')[1])
    elif 'Can delete' in value:
        return 'Pode remover{}'.format(value.split('Can delete')[1])
    elif 'Can view' in value:
        return 'Pode visualizar{}'.format(value.split('Can view')[1])
    return value


@register.filter(name='nbsp')
def nbsp(value):
    """
    Substitui espaços em branco, em um string, pelo código **HTML**.

    Args:
        value (string): texto a processar.

    Returns:
        String com os espaços em branco substituídos por *&nbsp;*.
    """
    return mark_safe(str(value or '').replace(' ', '&nbsp&nbsp&nbsp&nbsp'))


@register.filter(name='remove_nbsp')
def remove_nbsp(value):
    """
    Remove espaços em branco ocultos no html.

    Args:
        value (string): texto a processar.

    Returns:
        String com os espaços html em branco oculto removidos.
    """
    value = str(value or '')
    regex = '<span(.*?)>&nbsp;</span>'
    result = re.search(regex, value)
    if result:
        for span in result.groups():
            value = value.replace(f'<span{span}>&nbsp;</span>', '')
    return mark_safe(value)


@register.filter(name='format', is_safe=True)
def format_(value, html=True):
    """
    Formata o valor passado, deixando em um formato amigável.

    Args:
        value: valor a ser formatado;
        html (bool): indica se a saída deve ser **HTML**.

    Returns:
        String com o valor passado formatado.
    """
    if value in (None, ''):
        return '-'
    elif isinstance(value, bytes):
        return value.decode()
    elif isinstance(value, bool):
        return format_bool(value, html)
    elif isinstance(value, timedelta):
        return format_timedelta(value)
    elif value.__class__.__name__ == 'Decimal' or isinstance(value, float):
        return format_money(value)
    elif hasattr(value, 'strftime'):
        return format_datetime(value)
    elif hasattr(value, '_meta') and value._meta.model_name in ('vinculo', 'user', 'servidor', 'prestadorservico', 'aluno'):
        if html:
            return format_user(value)
        else:
            return str(value)
    elif hasattr(value, '_meta') and value._meta.model_name in ('pessoa', 'pessoafisica', 'funcionario', 'pessoajuridica'):
        if html:
            return format_profile(value)
        else:
            return str(value)
    elif isinstance(value, str):
        return value
    elif hasattr(value, '__iter__'):
        return format_iterable(value)
    elif hasattr(value, 'all'):
        return format_iterable(value.all())
    else:
        return value


@register.filter(name='format_time', is_safe=True)
def format_time(value):
    """
    Formata um datetime no formato hh:mm:ss.

    Args:
        value (datetime): objeto datetime a ser formatado.

    Returns:
        String com o valor passado formatado.
    """
    return str(formata_segundos(value, '{h:02.0f}:', '{m:02.0f}:', '{s:02.0f}'))


@register.filter(name='format_time2', is_safe=True)
def format_time2(value):
    """
    Formata um decimal no formato 1,5h (01:30:00) em formato hh:mm:ss

    Args:
        value (datetime): objeto datetime a ser formatado.

    Returns:
        String com o valor passado formatado.
    """
    segundos = value * 3600
    return str(formata_segundos(segundos, '{h:02.0f}:', '{m:02.0f}:', '{s:02.0f}'))


@register.filter(name='format_hours', is_safe=True)
def format_hours(value, default='0h'):
    """
    Formata um decimal no formato 99h. Casas decimais somente com 0 serão suprimidas.

    Args:
        value (decimal): objeto decimal a ser formatado.

    Returns:
        String com o valor passado formatado com "h" no final.
    """
    if value:
        hour, minute = f'{value:.2f}'.split('.')
        hour, minute = int(hour), int(minute)
        if not minute:
            return f'{hour}h'
        return f'{hour}h {int(minute * 60 / 100)}m'
    return default


@register.filter(name='format_time_hms', is_safe=True)
def format_time_hms(value):
    """
    Formata um datetime no formato hh:mm:ss.

    Args:
        value (datetime): objeto datetime a ser formatado.

    Returns:
        String com o valor passado formatado.
    """
    return str(formata_segundos(value, '{h}h ', '{m}min ', '{s}seg '))


@register.filter
def sum_values_by_key(list_of_dicts, key):
    """
    Realiza o somatório de em uma chave de dicionário em uma lista de dicionários.

    Args:
        list_of_dicts (list): lista contendo os dicionários;
        key (string): chave a ser somada.

    Returns:
         Soma do valor solicitado.
    """
    if hasattr(list_of_dicts, 'values'):
        list_of_dicts = list(list_of_dicts.values())
    return sum(d.get(key, 0) for d in list_of_dicts)


@register.filter
def sum_all_dict_values(dictionary):
    """
    Soma todos os valores de um dicionário ou de um dicionário de dicionários.

    Args:
        dictionary: dicionário ou dicionário de dicionários.

    Returns:
        Soma de todos os valores.
    """
    sum_ = 0
    if isinstance(dictionary, dict):
        for v in list(dictionary.values()):
            if isinstance(v, dict):
                sum_ += sum_all_dict_values(v)
            else:
                try:
                    sum_ += Decimal(str(v))
                except Exception:
                    sum_ += 0
    return sum_


@register.filter
def percentage(quantity, total):
    """
    Calcula o valor percentual entre a quantidade passada e o total.

    Args:
        quantity (): quantidade a calcular;
        total (): total dos itens.

    Returns:
        Float com o valor percentual entre **quantity** e **total**.
    """
    try:
        return float(quantity) / total * 100
    except Exception:
        return 0


@register.filter
def count_entries_in_dictlist(dictlist, args):
    """
    Calcula o número de itens em uma lista de dicionários. Os items a pesquisar são passados no formato 'chave;valor'.

    Args:
        dictlist (list): lista de dicionários;
        args (string): string contendo o par chave;valor.

    Returns:
        Int com o número de repetições encontradas.
    """
    sum = 0
    arg_list = [arg.strip() for arg in args.split(';')]
    key = arg_list[0]
    value = arg_list[1]

    if isinstance(dictlist, list):
        for dictionary in dictlist:
            for k, v in list(dictionary.items()):
                if k == key and v == value:
                    sum += 1
    return sum


@register.filter
def indice(value, arg):
    """
    Obtem o elemento **arg** da lista/dicionário **value**.

    Args:
        value (list|dict): lista ou dicionário;
        arg (int|string): item a ser retornado.

    Returns
        Elemento da lista|dicionário.
    """
    return value[arg]


@register.filter(name='getattr')
def getattr_(obj, args):
    """
    Tenta obter um atributo de um objeto.

    Args:
        obj (object): objeto base para obter o atributo;
        args (string): nome do atributo.

    Example:
        {% if block|getattr:"editable,True" %}

    Returns:
        Atributo solicitado.

    Try to get an attribute from an object.
    """
    splitargs = args.split(',')
    try:
        (attribute, default) = splitargs
    except ValueError:
        (attribute, default) = args, ''

    try:
        return obj.__getitem__(attribute)
    except Exception:
        pass

    try:
        attr = obj.__getattribute__(attribute)
    except AttributeError:
        attr = obj.__dict__.get(attribute, default) if hasattr(obj, '__dict__') else default
    except Exception:
        attr = default

    if callable(attr):
        return attr.__call__()
    else:
        return attr


@register.filter(name='ldap_attr')
def ldap_attr(obj):
    if isinstance(obj, list):
        if len(obj) == 1:
            val = obj[0]
            if val:
                return mark_safe(val)
            else:
                return mark_safe('-')
        else:
            out = ['<ol>']
            for i in obj:
                out.append(f'<li>{i}</li>')
            out.append('</ol>')
            return mark_safe(''.join(out))
    else:
        if obj:
            return mark_safe(obj)
        else:
            return mark_safe('-')


@register.filter(name='getkey')
def getkey(value, arg):
    """
    Obtem o valor de uma chave em um dicionário.

    Args:
        value (dict): dicionário;
        arg (string): chave de pesquisa

    Returns:
        O elemento do dicionário.

    Note:
        O valor padão para chaves não existentes é a string vazia.
    """
    return value.get(arg, '')


@register.filter(name='app_verbosename')
def app_verbosename(value):
    """
    Obtem o nome de uma aplicação.

    Args:
        value (string): nome da aplicação.

    Returns:
        String contendo o nome da aplicação.

    Note:
        O nome é o **verbose_name** da contido em app.py.
    """
    return apps.get_app_config(value).verbose_name or ''


@register.filter(name='method')
def method(obj, method):
    """
    Obtem um método de um objeto.

    Args:
        obj (object): objeto base para obtenção do método;
        method (string): nome do método.

    Returns:
        Método solicitado.
    """
    return obj.__getattribute__(method)


@register.filter(name='call')
def call(obj, args):
    """
    Invoca um método de um objeto.

    Args:
        obj (object): objeto base para invocação do método;
        args (string): nome do método.

    Returns:
        Resultado do método invocado.
    """
    if isinstance(args, str) and ',' in args:
        return obj.__call__(*args.split(','))
    return obj.__call__(args)


@register.filter(name='param')
def param(obj, arg):
    """
    Adiciona parâmetros na chamada de um método. Uso combinado com a função execute.

    Args:
        obj: objeto base para invocação do método.
        arg: parâmetro a ser adicionado à lista.

    Retorna:
        list: Uma lista contendo o `obj` original como primeiro item e demais parâmetros adicionados na lista

    Exemplo:
        {{my_object|method:"my_method"|param:1|param:True|param:request.user|execute}}
    """
    if not isinstance(obj, list):
        obj = [obj]
    obj.append(arg)
    return obj


@register.filter(name='execute')
def execute(args):
    """
    Chama um objeto executável com os argumentos fornecidos.

    O primeiro elemento na lista `args` é considerado o objeto executável (callable).
    Os elementos restantes são passados como argumentos para o objeto.

    Args:
        args (list): Uma lista onde o primeiro elemento é o objeto executável,
        e os elementos restantes são os argumentos a serem passados.

    Retorna:
        O resultado da chamada do objeto executável com os argumentos fornecidos.

    Exemplo:
         {{my_object|method:"my_method"|param:1|param:True|param:request.user|execute}}
    """
    obj = args[0]
    arg = args[1:]
    return obj.__call__(*arg)


@register.filter(is_safe=True)
def in_group(user, group, ignore_groups_if_superuser=True):
    """
    Verifica se o usuário está no grupo(s) passado(s).

    Args:
        user (User): usuário;
        group (string or list): string com o nome do grupo, ou, grupos;
        ignore_groups_if_superuser (bool): indica se é para ignorar os grupos do usuário logado se ele for **superuser**.

    Examples:
        Usage::
            {% if user|in_group:"GroupX" %}
            or
            {% if user|in_group:"GroupX,A group with white-spaces" %}

    Raises:
        TypeError se o grupo não for uma string ou um iterável.

    Returns:
        True se o usuário estiver no(s) grupo(s) passado(s).

    Notes:
        Para passar mais de um grupo, deve-se separar por virgula.
    """
    return user.is_authenticated and user.has_group_cached(group, ignore_groups_if_superuser=ignore_groups_if_superuser)


@register.filter
def calc_colspan(max_pairs, pairs):
    """
    Calcula o colspan para um conjunto de pares.

    Args:
        max_pairs ():
        pairs ():

    Returns:
        Inteiro com o cálculo do colspan.
    """
    return 2 * (int(max_pairs) - int(pairs)) + 1


@register.filter
def text_small(value):
    """
    Adiciona a tag **small** a um texto.

    Args:
        value (string): texto a ser colocado na **tag small**.

    Returns:
        String contendo o texto passado em uma **tag small**.
    """
    if value:
        return mark_safe(f'<small>{value}</small>')
    else:
        return ''


@register.filter
def status(value, extra_class=''):
    """
    Imprime a **tag span** correspondete ao status de acordo com valor passado.

    Args:
        value: valor a ser analisado;
        extra_class (string): classe **css** extra.

    Returns:
        String contendo **tag span** para o status.
    """
    if value == '-':
        return '-'
    if value:
        if value is True:
            return mark_safe(f'<span class="status status-success {extra_class}">Sim</span>')
        css = to_ascii(str(value).lower().replace(' ', '-'))
        return mark_safe(f'<span class="status status-{css} {extra_class}">{value}</span>')
    else:
        if value is False:
            return mark_safe(f'<span class="status status-error {extra_class}">Não</span>')
        return ''


@register.filter
def normalizar(nome):
    """
    Normaliza um nome.

    Args:
        nome (string): nome a ser normalizado.

    Returns:
         String com o nome normalizado.

    Note:
        O nome passado sai no formato: Fulade de Tal.
    """
    return normalizar_nome_proprio(str(nome))


@register.filter(name='getattrr')
def getattr_anonymize(obj, args, request=None, justification='html'):
    """
    Obtém um atributo de um objeto.

    Args:
        obj (object): objeto base;
        args (string): nome do atributo.
        request (HttpRequest): objeto HttpRequest
        justification (str|None): html -> exibe a justificativa em html, txt -> exibe a justificativa em texto, None -> não exibe a justificativa
    Returns:
        Atributo solicitado ou string vazia.
    """

    html = justification == 'html'
    if hasattr(obj, 'Anonymize'):
        if not request:
            request = tl.get_request()
        current, changed, obs = anonymize(obj, args, request, html)
        if changed:
            if justification and not html:
                current = str(current) + ' - ' + str(obs)
            return current
    return getattrr(obj, args)


@register.filter
def subtract(arg1, arg2):
    """
    Realiza a subtração entre dois valores.

    Args:
        arg1: minuendo;
        arg2: subtraendo.

    Returns:
        Valor obtido pela subtração: arg1 - arg2
    """
    if isinstance(arg1, datetime | date):
        # subtrair arg2 (um inteiro) dia(s) de arg1 (uma data) # no template: {{ data|subtract:1 }}
        return arg1 - timedelta(arg2)
    return arg1 - arg2


@register.filter(name='times')
def times(number):
    """
    Gera uma lista com um **range** de **number**.

    Args:
        number (int): valor a gerar o **range**.

    Returns:
         Lista contendo o **range** de **number**.
    """
    return list(range(number))


@register.filter
def timesince(data, now=None):
    """
    Gera uma string com expressando o número de anos, meses e dias de uma determinanda data, ou período.

    Args:
        data (date|datetime): data inicial para comparação;
        now (date|datetime): data final para comparação.

    Returns:
         String contendo a expressão da quantidade de anos, meses e dias.

    Notes:
        * Se as datas passadas forem do tipo **datetime** será acescentado as horas, minutos e segundos a strig;
        * Se o argumento now não for passado, será considerada a data atual.
    """
    if not data:
        return ''

    is_datetime = isinstance(data, datetime) and ((now and isinstance(now, datetime)) or not now)

    def append_result(result, str_to_append):
        if result:
            result += ', '
        result += str_to_append
        return result

    if not isinstance(data, datetime):
        data = datetime(data.year, data.month, data.day)

    if now and not isinstance(now, datetime):
        now = datetime(now.year, now.month, now.day)

    if not now:
        now = datetime.now()

    if not is_datetime:
        data = data.date()
        now = now.date()

    delta = relativedelta(now, data)
    result = ''

    if delta.years:
        result = append_result(result, f'{delta.years} ano{pluralize(delta.years, "s")}')

    if delta.months:
        result = append_result(result, f'{delta.months} m{pluralize(delta.months, "ês,eses")}')

    if delta.days:
        result = append_result(result, f'{delta.days} dia{pluralize(delta.days, "s")}')

    if is_datetime:
        if delta.hours:
            result = append_result(result, f'{delta.hours} hora{pluralize(delta.hours, "s")}')

        if delta.minutes:
            result = append_result(result, f'{delta.minutes} minuto{pluralize(delta.minutes, "s")}')

        if delta.seconds and result == '':
            result = append_result(result, f'{delta.seconds} segundo{pluralize(delta.seconds, "s")}')

    return result


@register.filter
def filename(value):
    """
    Obtem o nome do arquivo em disco para um **field** do tipo **File**.

    Args:
        value (FileField): campo do tipo arquivo.

    Returns:
        String com o nome do arquivo em disco.

    Notes:
        Caso não seja encontrado arquivos, será retornada a string "Arquivo não encontrado".
    """
    import os

    try:
        return os.path.basename(value.file.name)
    except Exception:
        return 'Arquivo não encontrado'


@register.filter
def arvore_setor(setor, lista=None):
    """
    Gera a árvore de setores com base em um setor.

    Args:
        setor (Setor): setor base para montagem da árvore;
        l (list):

    Returns:
        String com estrutura, em **HTML**, da árvore de setores.
    """
    if lista is None:
        lista = []
    areas_vinculacao = []
    for area_vinculacao in setor.areas_vinculacao.all():
        areas_vinculacao.append(f'<div class="tree-tag">{area_vinculacao.descricao}</div>')
    destaque = areas_vinculacao and 'negrito' or 'disabled'
    areas_vinculacao = areas_vinculacao and ''.join(areas_vinculacao) or ''
    lista.append(f'<li><span class="{destaque}">{setor}</span> {areas_vinculacao}')
    if setor.setor_set.exists():
        lista.append('<ul>')
        for subsetor in setor.setor_set.all():
            arvore_setor(subsetor, lista)
        lista.append('</ul>')
    lista.append('</li>')
    return mark_safe(''.join(lista))


@register.filter
def verbose(instance, arg):
    """
    Obtem o **verbose_name** de um field com base em uma instãncia.

    Args:
        instance (Model): instância base para obter o **field**;
        arg (string): nome do **field**.

    Returns:
        String com o **verbose_name**
    """
    return instance._meta.get_field(arg).verbose_name


@register.filter
def order(queryset, request):
    """
    Ordena um queryset com base no atributo **order** contido em GET.

    Args:
        queryset (Queryset): queryset a ser ordenado;
        request (HttpRequest): objeto request.

    Returns:
        QuerySet ordenada.
    """
    if request.GET.get('order'):
        args = [x.strip() for x in request.GET['order'].split(',')]
        return queryset.order_by(*args)
    return queryset


@register.filter()
def value(obj, campo):
    """
    Obtem o valor de um campo em um dicionário.

    Args:
        obj (dict): objeto, dict, para obter o valor;
        campo (string): nome do campo.

    Returns:
        O valor de **campo** em **obj**.
    """
    return obj.get(campo)


@register.filter()
def alias(campo):
    """
    Obtem o **alias** na lista **djtools.choices.campos**.

    Args:
        campo (string): nome do campo.

    Returns:
         String contendo o **alias**.
    """
    for filtro in campos:
        if filtro['campo'] == campo:
            return filtro['alias']
    return campo


@register.filter()
def get_value_dict(dicionario: dict, chave: str):
    """
    Obtem o valor de um item de dicionário.

    Args:
        dicionario (dict): dicionário base de pesquisa;
        chave (string): chave a ser procurada.

    Returns:
         Valor contido no dicionário no índice chave.
    """
    return dicionario.get(chave, '')


@register.filter()
def get_value_list(lista: list, indice: int):
    """
    Obtem o valor de um item de lista.

    Args:
        dicionario (list): lista base de pesquisa;
        indice (int): indice a ser procurado.

    Returns:
        Valor contido na lista no indice correspondente.
    """
    return lista[indice] if indice < len(lista) else ''


@register.filter()
def mascara_dinheiro(valor):
    """
    Coloca a mascará de dinheiro em um valor.

    Args:
        valor (): valor a ser mascarado.

    Returns:
        String com o valor na mascara de dinheiro.
    """
    return mask_money(valor or 0.0)


@register.filter
def mostrar_virgula(value):
    """
    Substitui ponto por virgula.

    Args:
        value (string): texto a ser processado.

    Returns:
         String com o valor passado substituido ponto por vírgula.
    """
    return value.replace('.', ',')


@register.filter()
def latest(obj, campo):
    """
    Obtem o último item do **queryset**.

    Args:
        obj (Queryset): objeto queryset;
        campo (string): nome do campo.

    Returns
        Último elemento do queryset.
    """
    try:
        return obj.latest(campo)
    except Exception:
        return None


@register.filter()
def mask_number(valor):
    """
    Coloca a mascará de dinheiro em um valor.

    Args:
        valor (): valor a ser mascarado.

    Returns:
        String com o valor na mascara de dinheiro.
    """
    return mask_numbers(valor)


@register.filter()
def mask_roman(valor):
    """
    Exibe um número inteiro em número romano.

    Args:
        valor (): número inteiro.

    Returns:
       número romano.
    """
    return int_to_roman(valor)


@register.filter()
def anonimizar_cpf(cpf):
    """
    Anonimiza CPF.

    Args:
        valor (): valor a ser anonimizado.

    Returns:
        String com o valor anonimizado.
    """
    return anonimizador_cpf(cpf)


@register.filter()
def hora_relogio(hora_aula):
    return math.ceil(Decimal(hora_aula) * Decimal(3) / 4)


@register.filter
def cpf_sem_caracteres(value):
    """
    Obtem o CPF sem mascara.

    Args:
        value (string): string contendo o CPF.

    Returns:
         CPF sem mascara.
    """
    if value is None:
        return ''
    return value.replace('.', '').replace('-', '')


@register.filter
def ordenar_faixas_classificacao(faixas_classificacao):
    if faixas_classificacao.exists():
        lista = []
        d = {}
        for faixa_classificacao in faixas_classificacao:
            d[faixa_classificacao.oferta_vaga.lista.descricao] = faixa_classificacao
        if faixa_classificacao.oferta_vaga.edital.configuracao_migracao_vagas:
            nomes = faixa_classificacao.oferta_vaga.edital.configuracao_migracao_vagas.get_nomes_listas_ordenadas_por_restricao()
            for nome in nomes:
                if nome in d:
                    lista.append(d.pop(nome))
            lista.extend(list(d.values()))
            return lista
    return faixas_classificacao


@register.filter
def push_item(lst, item):
    """
    Adiciona um item a uma lista.

    Args:
        l (list): lista;
        item: valor a ser adicionado.

    Returns:
        String vazia.
    """
    lst.append(item)
    return ''


@register.filter(name='range')
def _range(_min, args=None):
    """
    Obtem um **range**.

    Args:
        _min (int): valor mínimo do range;
        args: valor máximo e passo.

    Returns:
        Lista contendo os elementos de um range.
    """
    _max, _step = None, None
    if args:
        if not isinstance(args, int):
            _max, _step = list(map(int, args.split(',')))
        else:
            _max = args
    args = [_f for _f in (_min, _max, _step) if _f]
    return list(range(*args))


@register.filter(is_safe=True)
def getobjectfieldbyid(value, args):
    """
    Obtem um objeto com base no nome completo da classe.

    Args:
        value (int): id do objeto;
        args (string): nome completo da classe.

    Returns:
        Objeto com base na classe e valor passado.

    Notes:
        O nome completo é no formato aplicação.modelo.campo.
    """
    from django.apps import apps

    app, model, field = args.split(',')
    model = apps.get_model(app, model)
    return model.objects.get(id=value).__getattribute__(field)


@register.filter
def collapse_if_true(value):
    """
    Obterm a classe (CSS) para colapsar.

    Args:
        value (): valor a ser considerado.

    Returns:
         String 'collapsed'se algum valor em **value** for passado.
    """
    return 'collapsed' if bool(value) else ''


@register.filter
def getextfrompath(path):
    """
    Obtem a extensão de um arquivo.

    Args:
        path (string): string contendo o **path** completo do arquivo.

    Returns:
        String contendo a extensão do arquivo.
    """
    return os.path.splitext(path)[1]


@register.filter
def getfilenamefrompath(path):
    return os.path.split(path)[1]


@register.filter
def por_extenso(value):
    """
    Obtem o extenso de um valor.

    Args:
        value (): valor a ser escrito.

    Returns:
         String que expressa **value** por extenso.
    """
    if bool(value):
        reais, centavos = str(value).split('.')
        return f'{dinheiro_extenso(reais, centavos)}'
    else:
        return '-'


@register.filter
def tem_atributo(obj, value):
    """
    Verifica se o atributo indicado em **value** existe em **obj**.

    Args:
        obj (object): objeto base para pesquisa;
        value (string): nome do atributo.

    Returns:
        True se o elemento existir.
    """
    return hasattr(obj, value)


@register.filter
def somar(valor1, valor2):
    """
    Obtem a soma de dois valores.

    Args:
        valor1: primeiro valor;
        valor2: segundo valor.

    Returns:
         A soma dos dois valores.
    """
    return valor1 + valor2


@register.filter
def dividir_inteiro(valor1, valor2):
    """
    Obtem a divisão entre dois valores arredondando para baixo de dois valores.

    Args:
        valor1: primeiro valor;
        valor2: segundo valor.

    Returns:
         A soma dos dois valores.
    """
    try:
        return int(valor1) // int(valor2)
    except ValueError, ZeroDivisionError:
        return None


@register.filter
def count_first_queryset(d):
    """
    Conta os elementos da primeiro queryset do dicionário passado.

    Args:
        d (dict): dicionário.

    Returns:
        Inteiro contendo o número de elementos do primeiro queryset.
    """
    lista = [*d.values()]
    return lista and lista[0].count() or 0


@register.filter
def tratar_parametros_filter(url, parametro):
    """
    Trata a "**query string**" passada tranformando no padrão chave=valor.

    Args:
        url (string): string contendo a **query string**;
        parametro (string): parametro a ser retornado.

    Returns:
        String contendo o parametro solicitado.
    """
    for valor in url.replace('?', '').split('&'):
        parametros = valor.split('=')
        if len(parametros) > 1 and parametro == parametros[0]:
            return f'{parametros[0]}={parametros[1]}'
    return ''


@register.filter
def tratar_list_filter(url, list_filter):
    """
    Trata a "**query string**" passada tranformando no padrão chave=valor.

    Args:
        url (string): string contendo a **query string**;
        list_filter (ListFilter): list filter utilizado.

    Returns:
        String contendo o parametro solicitado.
    """
    for valor in url.replace('?', '').split('&'):
        parametros = valor.split('=')
        if len(parametros) > 1 and parametros[0] in list_filter.expected_parameters():
            return f'{parametros[0]}={parametros[1]}'
    return ''


@register.filter
def retirar_parametro_get(url, parametros):
    """
    Trata a "**query string**" passada retirando as chaves passadas.
    Exemplo:
    def retirar_parametro_get('?setor=1&campus=2&tab=2', 'setor,tab'):
        return '&campus=2'


    Args:
        url (string): string contendo a **query string**;
        parametros (string): parametros separados por ',' a serem retirados.

    Returns:
        String contendo o parametro solicitado.
    """
    retorno = ''
    parametros = parametros.split(',')
    for valor in url.replace('?', '').split('&'):
        if valor:
            url_param = valor.split('=')
            if len(url_param) and url_param[0] not in parametros:
                valor = ''
                if len(url_param) > 1:
                    valor = url_param[1]
                retorno += f'&{url_param[0]}={valor}'
    return retorno


@register.filter()
def base64encode(val):
    return base64.b64encode(val.encode()).decode()


@register.filter()
def base64decode(val):
    return base64.b64decode(val.encode()).decode()


@register.filter
def safe_message(message):
    return message.message if message and isinstance(message.message, SafeText) else escape(message.message)


@register.filter('int')
def integer(a):
    return int(a)


@register.filter
def multiply(a, b=1):
    return a * b


@register.filter
def checkbox_input(obj, checked=False):
    return '<input type="checkbox" value="{}" name="item_{}" id="item_{}" title="{}" {} style="margin-right:10px"/>'.format(
        obj.pk, obj.pk, obj.pk, obj, 'checked' if checked else ''
    )


@register.filter
def radio_input(obj, checked=False):
    return '<input type="radio" value="{}" name="item" id="item_{}" title="{}" {} style="margin-right:10px"/>'.format(
        obj.pk, obj.pk, obj, 'checked' if checked else ''
    )


@register.filter
def input_label(obj):
    return f'<label for="item_{obj.pk}">{obj}</label>'


@register.filter
def formatar_nota(nota):
    if nota is None:
        nota = ''
    else:
        nota = mask_nota(nota)
    return nota


@register.filter
def nota_boletim(obj, etapa):
    alerta = ''
    if not obj.is_nota_visivel(etapa):
        alerta = 'class="hint hint-bottom" aria-label="Nota estará pública após entrega da etapa pelo professor."'
    nota = format_(obj.get_nota_boletim(etapa))
    return mark_safe(f'<span {alerta}>{nota}</span>')


@register.filter
def nota_diario(obj, etapa):
    return obj.get_nota_boletim(etapa, ignora_autopublicacao=True) or ''


@register.filter
def nota_parcial_boletim(obj, etapa):
    alerta = ''
    if not obj.is_nota_visivel(etapa):
        alerta = 'class="hint hint-bottom" aria-label="Nota estará pública após entrega da etapa pelo professor."'
    nota_parcial = format_(obj.get_nota_parcial_boletim(etapa))
    return mark_safe(f'<span {alerta}>{nota_parcial}</span>')


@register.filter
def nota_recuperacao_boletim(obj, etapa):
    alerta = ''
    if not obj.is_nota_visivel(etapa):
        alerta = 'class="hint hint-bottom" aria-label="Nota estará pública após entrega da etapa pelo professor."'
    nota_parcial = format_(obj.get_recuperacao_boletim(etapa))
    return mark_safe(f'<span {alerta}>{nota_parcial}</span>')


@register.filter()
def split(value, delimiter):
    return value.split(delimiter) if value else ''
