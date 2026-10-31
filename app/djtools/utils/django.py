from urllib.parse import urlparse

from django.apps import apps
from django.urls import resolve


def get_view_name_from_url(url):
    """
    Retorna o namespace de uma view a partir de uma URL

    Args:
         url (string): URL completa do suap, exemplo: https://suap.ifrn.edu.br/admin/erros/erro/add/

    Returns:
        String se o módulo existir e a URL for bem formada, senão retorna None.
    """
    try:
        path = urlparse(url).path
        if path.startswith('/admin'):
            splitted_path = path.split('/')
            url_name = resolve(path).url_name or splitted_path[3]
            return f'{splitted_path[1]}.{splitted_path[2]}.{url_name}'
        else:
            view_func = resolve(path)[0]
            return view_func.__module__ + '.' + view_func.__name__
    except Exception:
        return None


def get_module_from_url(url):
    """
    Retorna o nome completo de um módulo a partir de uma URL

    Args:
         url (string): URL completa do suap, exemplo: https://suap.ifrn.edu.br/admin/erros/erro/add/

    Returns:
        String se o módulo existir e a URL for bem formada, senão retorna None.
    """

    try:
        path = urlparse(url).path
        resolve(path)
        path = path.split('/')
        if len(path) < 3:
            return 'djtools'
        modulo = path[1] != 'admin' and path[1] or path[2]
        apps.get_app_config(modulo)
        return modulo
    except Exception:
        return None


def get_model_object_field_and_values(model_object, use_verbose_name_as_key=True):
    """
    Retorna um dicionário com o nome do campo e seu valor.
    Obs: Valor pode ser um atributo básico (Ex: str, int, float ...) ou pode ser um objeto
    do domínio do SUAP (Ex: PessoaFisica, UnidadeOrganizacional...).

    Args:
        model_object: instância de um Model.
        use_verbose_name_as_key: se True, a chave do dicionário será o verbose_name, caso exista, caso contrário. ou se False, será o nome do campo.
    Returns:
        dict() contendo o nome do campo e o seu valor.

    Ex:
        from djtools.utils import get_model_object_field_and_values
        from rh.models import Servidor

        servidor = Servidor.objects.get(matricula='2107029')
        fields_and_values = get_model_object_field_and_values(servidor)
        print(fields_and_values)

        Console:
        {'id': 2107029, 'Nome': 'Misael Barreto de Queiroz', 'Nome Usual': 'Misael Queiroz',
        'Nome Social': '', 'Nome de Regitro': 'Misael Barreto de Queiroz',
        'E-mail': 'misael.queiroz@ifrn.edu.br', ...}
    """
    fields = list(type(model_object)._meta.fields)
    result = {}
    for field in fields:
        if use_verbose_name_as_key:
            key = field.verbose_name or field.name
        else:
            key = field.name
        result[key] = getattr(model_object, field.name)
    return result


def compare_model_objects(model_object_old, model_object_new, use_verbose_name_as_key=True, atts_to_ignore=None):
    """
    Retorna um dicionário contendo a diferença entre duas instâncias do objeto de um modelo.

    Args:
        model_object_old: instância antiga de um modelo.
        model_object_new: instância nova de um modelo.
        atts_to_ignore: atributos que não devem ser comparados.
    Returns:
        dict() contendo os atributos divegentes e uma descrição contendo o valor anterior e o atual.
    Raises:
        Exception: caso os objetos a serem comparados sejam de domínios distintos.


    Ex:
        from djtools.utils import get_model_object_field_and_values
        from rh.models import Servidor
        import json

        servidor_old = Servidor.objects.get(matricula='2107029')
        servidor_new = Servidor.objects.get(matricula='2107029')
        servidor_new.matricula = '2107029222'
        servidor_new.data_cadastro_siape = datetime.date.today()

        diff = compare_model_objects(servidor_old, servidor_new)
        print(diff)
        print(json.dumps(diff, indent=4))

        Console:
            {'Matrícula': 'Alterado de 2107029 para 2107029222.', 'Data de Cadastro no SIAPE': 'Alterado de 07/04/2014 para 19/09/2022.'}

            {
                "Matrícula": "Alterado de 2107029 para 2107029222.",
                "Data de Cadastro no SIAPE": "Alterado de 07/04/2014 para 19/09/2022."
            }

    """
    from django.db.models.fields.files import FieldFile

    from djtools.templatetags.filters import format_
    # Obs: Fiz esse import interno porque ao tentar fazer lá em cima ocorreu o erro abaixo:
    #   File "suap/djtools/pdf.py", line 21, in <module>
    #     from djtools.utils import human_str
    # ImportError: cannot import name 'human_str'

    # Tentei realizar o import "silecioso", mas também deu o mesmo problema.
    # from django.utils.module_loading import import_string
    # FieldFile = import_string('django.db.models.fields.files.FieldFile')
    # format_ = import_string('djtools.templatetags.filters.format_')
    if atts_to_ignore is None:
        atts_to_ignore = []

    def internal_format(value):
        if isinstance(value, FieldFile):
            value = value.url
        return str(format_(value, html=False))

    if type(model_object_old) is not type(model_object_new):
        raise Exception('Os objetos em questão pertencem a modelos distintos.')

    atts_old = get_model_object_field_and_values(model_object_old, use_verbose_name_as_key)
    atts_new = get_model_object_field_and_values(model_object_new, use_verbose_name_as_key)

    result = {}
    # Varrendo todos os atributos do objeto antigo...
    for k, v in atts_old.items():
        if k not in atts_to_ignore:
            # Caso o atributo exista no objeto antigo e não exista no novo,
            # ele será adicionado no dicionário.
            if k not in atts_new:
                result[k] = f'Atributo removido! Último valor: {internal_format(v)}'
            # Caso contrário, é sinal que o atributo exite em ambos os objetos,
            # daí caso o valor esteja diferente, o atributo do objeto novo será
            # adicionado ao dicionário.
            else:
                att_new_value = atts_new.get(k, None)
                if att_new_value and att_new_value != v:
                    result[k] = f'Alterado de {internal_format(v)} para {internal_format(att_new_value)}.'

    # Caso o atributo exista no objeto novo e não exista no antigo,
    # ele será adicionado no dicionário.
    for k, v in atts_new.items():
        if k not in atts_to_ignore:
            if k not in atts_old:
                result[k] = f'Atributo criado! Valor: {internal_format(v)}'

    return result


def get_qualified_model_name(model):
    """
    Obtem uma string qualificada do nome do Modelo
    Args:
        mnodel (Model): modelo.

    Returns:
        String no formato 'app_label.Modelo'
    """
    return f'{model._meta.app_label}.{model._meta.model_name}'


def get_app_name(function):
    """
    Obtem a aplicação de uma função.

    Args:
        function (Function): função.

    Returns:
         String com o nome da aplicação que contem a função.
    """
    function_path = function.__module__.split('.')
    if (
        'lps' in function_path or len(function_path) == 2 or len(function_path) == 3 and 'views' in function_path
    ):  # the function was defined in the lps module
        return function_path[0]
    return function_path[1]
