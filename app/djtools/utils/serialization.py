import base64
import datetime
import json
import pickle
import zlib
from decimal import Decimal
from importlib import import_module

from cryptography.fernet import Fernet
from django.apps import apps
from django.conf import settings
from django.contrib.admin import ModelAdmin
from django.contrib.auth.models import AnonymousUser
from django.core import signing
from django.core.signing import Signer
from django.db.models import Model, QuerySet
from django.db.models.query import FlatValuesListIterable
from django.http import HttpRequest, QueryDict
from django.utils.safestring import mark_safe

from djtools.middleware.threadlocals import context


def timeless_dump_qs(query):
    """
    Cria um dump de um queryset na base 64 e realiza sua assinatura.

    Args:
        query (Queryset): queryset a ser processado.

    Returns:
        String codificada na base64 do queryset.
    """
    serialized_str = base64.b64encode(zlib.compress(pickle.dumps(query))).decode()
    signer = Signer()
    signed_data = signer.sign(serialized_str)
    payload = {'data': signed_data}
    return mark_safe(json.dumps(payload))


def timeless_load_qs_query(query):
    """
    Com base em uma string base64 é gerado um queryset.

    Args:
        query (string): string códificada por **timeless_dump_qs**.

    Returns:
        Queryset contido na string códificada.
    """
    payload = json.loads(query)
    signer = Signer()
    signed_data = payload['data']
    data = signer.unsign(signed_data)
    return pickle.loads(zlib.decompress(base64.b64decode(data)))


def encrypt(obj):
    """
    Criptografa um objeto serializável.

    Args:
        obj (dict, list, str, int, boolean, None): object.

    Returns:
        Um string serializada do objeto (str).
    """
    key = base64.b64encode(settings.SECRET_KEY[:32].encode())
    f = Fernet(key)
    text = json.dumps(obj)
    return f.encrypt(text.encode()).decode()


def decrypt(text):
    """
    Descriptografa um texto e transforma em um objeto.

    Args:
        text (str): object.

    Returns:
        O objeto (dict, list, str, int, boolean, None).
    """
    key = base64.b64encode(settings.SECRET_KEY[:32].encode())
    f = Fernet(key)
    serialized_obj = f.decrypt(text.encode()).decode()
    return json.loads(serialized_obj)


def dumps_queryset(queryset):
    """
    Gera um dump assinado que um queryset.

    Args:
        queryset (Queryset): queryset a ser gerado o dump.

    Returns:
        O dump do queryset.
    """
    serialized_str = base64.b64encode(zlib.compress(pickle.dumps(queryset.query))).decode()
    payload = {'model_label': queryset.model._meta.label, 'query': serialized_str}
    signed_data = signing.dumps(payload)
    return signed_data


def dumps_model(o):
    """
    Gera um dump assinado de um modelo.

    Args:
        o (Model): objeto de modelo a ser gerado o dump.

    Returns:
        O dump do modelo.
    """
    payload = {'label': o._meta.label, 'pk': o.pk}
    signed_data = signing.dumps(payload)
    return signed_data


def loads_queryset(data):
    """
    Obetem um queryset apartir de um dump assinado.

    Args:
        data (butes): dump do queryset.

    Returns:
        Queryset contido no dump.
    """
    payload = signing.loads(data)
    model = apps.get_model(payload['model_label'])
    query = pickle.loads(zlib.decompress(base64.b64decode(payload['query'].encode())))
    queryset = model.objects.none()
    queryset.query = query
    return queryset


def loads_model(data):
    """
    Obetem um model apartir de um dump assinado.

    Args:
        data (butes): dump do model.

    Raises:
        Exception caso ocorra erros ao realzizar o *load* de *data*.

    Returns:
        Model contido no dump.
    """
    try:
        payload = signing.loads(data)
        model = apps.get_model(payload['label'])
        return model.objects.filter(pk=payload['pk']).first()
    except Exception as e:
        raise Exception('pk:{}. label:{}. Erro:{}.'.format(payload['pk'], payload['label'], e))


def dump_datetime(data):
    """
    Transforma o datetime ou date em isoformat.

    Args:
        data (Datetime ou Date): objeto a ser convertido em isoformat.

    Returns:
        O datetime ou date em isoformat.
    """
    return data.isoformat()


def load_datetime(data):
    """
    Args:
        data (str): datetime ou date em isoformat.
    Raises:
        Exception caso ocorra erros ao realizar o *load* da *data*
    Returns:
        instância de datetime.
    """
    return datetime.datetime.fromisoformat(data)


def get_serializable_meta(meta):
    cleaned_meta = {}
    included_keys = ['REMOTE_ADDR', 'QUERY_STRING', 'REQUEST_METHOD', 'CONTENT_TYPE', 'CONTENT_LENGTH', 'PATH_INFO']
    for key, value in meta.items():
        if key in included_keys or key.startswith(('HTTP_', 'REQUEST_')):
            try:
                json.dumps(value)
                cleaned_meta[key] = value
            except Exception:
                pass
    return cleaned_meta


def dump_request(request):
    """
    Args:
        request (HttpRequest): django http request.
    Raises:
        Exception caso ocorra erros ao realizar o *dump* do *request*
    Returns:
        O request em string
    """
    meta_str = get_serializable_meta(request.META)

    get_list = {key: request.GET.getlist(key) for key in request.GET if len(request.GET.getlist(key)) > 1}
    get_str = request.GET
    post_list = {key: request.POST.getlist(key) for key in request.POST if len(request.POST.getlist(key)) > 1}
    post_str = request.POST
    session_key = hasattr(request, 'session') and request.session.session_key or ''
    return signing.dumps(
        {
            'meta': meta_str,
            'get': get_str,
            'get_list': get_list,
            'post': post_str,
            'post_list': post_list,
            'user_id': request.user.id,
            'session_key': session_key,
            'method': request.method,
            'path': request.path,
        }
    )


def load_request(data):
    from comum.models import User

    """
    Args:
        data (str): serialized HttpResquest.
    Raises:
        Exception caso ocorra erros ao realizar o *load* da *data*
    Returns:
        instância de HttpRequest.
    """
    request = HttpRequest()
    request_data = signing.loads(data)
    request.META = request_data['meta']
    get_query_dict = QueryDict(mutable=True)
    for key, values in request_data['get_list'].items():
        for value in values:
            get_query_dict.appendlist(key, value)
    get_query_dict.update(request_data['get'])
    request.GET = get_query_dict
    post_query_dict = QueryDict(mutable=True)
    for key, values in request_data['post_list'].items():
        for value in values:
            post_query_dict.appendlist(key, value)
    post_query_dict.update(request_data['post'])
    request.POST = post_query_dict
    request.path = request_data['path']
    if request_data.get('user_id'):
        request.user = User.objects.get(pk=request_data['user_id'])
    else:
        request.user = AnonymousUser()
    request.method = request_data['method']
    session_key = request_data['session_key']
    if session_key:
        session = import_module(settings.SESSION_ENGINE).SessionStore(session_key=session_key)
    else:
        session = {}

    request.session = session
    context.user = getattr(request, 'user', None)
    context.request = request
    return request


def dump_bytes(o):
    """
    Args:
        o (bytes): string binária.
    Raises:
        Exception caso ocorra erros ao realizar o *dump* do *binario*
    Returns:
        string serializada
    """
    return base64.b64encode(o).decode()


def load_bytes(o):
    """
    Args:
        o (str): serialized binary string.
    Raises:
        Exception caso ocorra erros ao realizar o *load* da *string*
    Returns:
        string binária
    """
    return base64.b64decode(o)


def dump_admin(o):
    """
    Args:
        o (ModelAdmin): django ModelAdmin.
    Raises:
        Exception caso ocorra erros ao realizar o *dump* do *ModelAdmin*
    Returns:
        O ModelAdmin em string
    """
    request = getattr(o, 'request', '')
    return signing.dumps(
        {
            'qualified_name': str(o),
            'model': o.model._meta.label,
            'request': request and dump_request(request),
        }
    )


def load_admin(o):
    """
    Obtem um ModelAdmin a partir de um dump assinado.

    Args:
        o (ModelAdmin): dump do model.

    Raises:
        Exception caso ocorra erros ao realizar o *load* de *ModelAdmin*.

    Returns:
        ModelAdmin contido no dump.
    """
    from django.contrib import admin

    def get_admin(qualified_name):
        module_name = f'{qualified_name.split(".")[0]}.admin'
        class_name = qualified_name.split('.')[1]
        module = import_module(module_name)
        return getattr(module, class_name)

    payload = signing.loads(o)
    try:
        request = payload['request']
        model = apps.get_model(payload['model'])
        Admin = get_admin(payload['qualified_name'])
        obj = Admin(model, admin.site)
        obj.request = request and load_request(request)
        return obj
    except Exception as e:
        raise Exception('pk:{}. label:{}. Erro:{}.'.format(payload['model'], payload['qualified_name'], e))


def dump_function(o):
    """
    Args:
        o (function): python function.
    Raises:
        Exception caso ocorra erros ao realizar o *dump* do *function*
    Returns:
        O function em string
    """
    return f'{o.__module__}/{o.__name__}'


def load_function(o):
    """
    Obtem um function a partir de um dump

    Args:
        o (str): dump do function

    Raises:
        Exception caso ocorra erros ao realizar o *load* de *function*.

    Returns:
        function contido no dump.
    """
    module, function = o.split('/')
    mod = import_module(module)
    return getattr(mod, function)


def serialize(o):
    """
    Serializa um elemento, queryset ou model.

    Args:
        o (object): objetos a serem serializados.

    Returns:
        (str): O dump de **o**.
    """
    return json.dumps(o, cls=SuapEncoder)


class SuapEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, QuerySet):
            if o._iterable_class == FlatValuesListIterable:
                return list(o)
            else:
                return {'QuerySet': dumps_queryset(o)}
        elif isinstance(o, Model):
            return {'Model': dumps_model(o)}
        elif isinstance(o, datetime.datetime):
            return {'Datetime': dump_datetime(o)}
        elif isinstance(o, datetime.date):
            return {'Date': dump_datetime(o)}
        elif isinstance(o, HttpRequest):
            return {'HttpRequest': dump_request(o)}
        elif isinstance(o, Decimal):
            return {'Decimal': str(o)}
        elif isinstance(o, bytes):
            return {'Bytes': dump_bytes(o)}
        elif isinstance(o, AnonymousUser):
            return {'AnonymousUser': None}
        elif isinstance(o, ModelAdmin):
            return {'ModelAdmin': dump_admin(o)}
        elif callable(o):
            return {'Function': dump_function(o)}
        # Let the base class default method raise the TypeError
        return json.JSONEncoder.default(self, o)


def deserialize(o):
    """
    Desserializar um dump.

    Args:
        o (str): dump a ser desseralizado.

    Returns:
         Objetos contidos no dump.
    """
    return json.loads(o, cls=SuapDecoder)


class SuapDecoder(json.JSONDecoder):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, object_hook=self.object_hook, **kwargs)
        self.scan_once = json.scanner.py_make_scanner(self)

    def object_hook(self, o):
        if isinstance(o, dict):
            for key, value in o.items():
                if key == 'QuerySet':
                    return loads_queryset(value)
                elif key == 'Model':
                    return loads_model(value)
                elif key == 'Datetime':
                    return load_datetime(value)
                elif key == 'Date':
                    return load_datetime(value).date()
                elif key == 'HttpRequest':
                    return load_request(value)
                elif key == 'Decimal':
                    return Decimal(value)
                elif key == 'Bytes':
                    return load_bytes(value)
                elif key == 'AnonymousUser':
                    return AnonymousUser()
                elif key == 'ModelAdmin':
                    return load_admin(value)
                elif key == 'Function':
                    return load_function(value)
        return o


def pickle_dumps(o):
    """
    Serializa um objeto usando pickle e comprime o resultado.
    Args:
        o (object): objeto a ser serializado.
    Returns:
        (str): O dump de **o**.
    """
    return base64.b64encode(zlib.compress(pickle.dumps(o))).decode()


def pickle_loads(o):
    """
    Desserializa um objeto usando pickle e descomprime o resultado.
    Args:
        o (str): dump a ser desseralizado.
    Returns:
         Objetos contidos no dump.
    """
    return pickle.loads(zlib.decompress(base64.b64decode(o.encode())))
