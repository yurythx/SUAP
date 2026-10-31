import csv
import json
import mimetypes
import os
import re
import tempfile
import urllib.parse
from collections.abc import Mapping
from functools import WRAPPER_ASSIGNMENTS, wraps

from django.conf import settings
from django.core.serializers.json import DjangoJSONEncoder
from django.forms.forms import BaseForm
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import render as django_render
from django.template import Context, Template, TemplateDoesNotExist
from django.template.base import render_value_in_context
from django.template.loader import get_template, select_template
from django.utils.safestring import SafeString, mark_safe

from djtools.middleware import threadlocals as tl
from djtools.storages.utils import download_temporary_content

from .breadcrumbs import breadcrumbs_add, breadcrumbs_previous_url
from .django import get_app_name
from .email import send_mail
from .http import is_ajax
from .strings import human_str, to_ascii


def solicitar_autenticacao_2fa(request: HttpRequest, next_url: str) -> HttpResponse | None:
    """Encaminha o usuário à verificação do segundo fator por e-mail, quando ainda não a fez.

    Args:
        request: Requisição HTTP em curso.
        next_url: URL de destino após a verificação, **sem codificar** (ex.:
            ``request.get_full_path()``). A codificação é feita aqui, para que os ``&`` da
            query de origem não virem parâmetros da própria tela de verificação.

    Returns:
        O redirecionamento para a verificação (ou para a página anterior, com mensagem de
        erro), ou ``None`` quando a sessão já passou pelo segundo fator.
    """
    if request.session.get('2fa'):
        return None

    if not request.user.is_authenticated:
        return httprr('..', 'Por favor efetue o login novamente.')

    # 2FA usa SÓ o e-mail pessoal — nunca o institucional (mesma senha do SUAP).
    if not request.user.get_vinculo().email_pessoal:
        if request.user.get_vinculo().eh_aluno():
            return httprr(
                '..',
                'Esta funcionalidade requer o envio de um código de autenticação para o seu e-mail pessoal, porém, você não possui este e-maill cadastrado. Entre em contato com a secretaria acadêmica ou coordenação de curso para cadastro do seu email.',
                'error',
            )
        return httprr(
            '..',
            'Esta funcionalidade requer o envio de um código de autenticação para o seu e-mail secundário, porém, você não possui este e-mail cadastrado. Entre em contato com o setor de Gestão de Pessoas da sua unidade para cadastro do seu email.',
            'error',
        )

    from djtools.models import TwoFactorAuthenticationCode

    obj = TwoFactorAuthenticationCode.objects.create()
    if not settings.DEBUG:
        send_mail(
            '[SUAP] Código de Autenticação',
            f'<h1>Código de Autenticação</h1><dl><dt>Código:</dt><dd>{obj.code}</dd></dl><div class="clear"></div><p>Você não deve compartilhar este código com terceiros.</p>',
            settings.DEFAULT_FROM_EMAIL,
            [request.user.get_vinculo().email_pessoal],
        )

    parametros = {'next': next_url}
    if '_popup' in request.GET:
        parametros['_popup'] = '1'
    return HttpResponseRedirect(f'/djtools/two_factor_authentication/?{urllib.parse.urlencode(parametros)}')


def httprr(url, message='', tag='success', anchor='', get_params='', close_popup=False, close_popup_and_force_reload=False):
    """
    Shortcut para o **HttpResponseRedirect** que possibilita a passagem de uma mensagem.

    Args:
        url (string): string com a url a redirecionar;
        message (string): string contendo a mensagem a ser passada;
        tag (string): tag utilizada para caracterizar a mensagem, por exemplo: success, warning
        anchor (string): ancora a ser direcionado a página;
        get_params (string): contem pares chave=valor, por exemplo: 'p1=v1&p2=v2';
        close_popup (bool): instrui fechar imediatamente janela de popup se esse for o caso;
        close_popup_and_force_reload (bool): força o recarregamento da página após fechar o popup

    Returns:
        Objeto HttpResponseRedirect, ou HttpResponse quando for para fechar janelas popups.
    """

    def set_message():
        if message:
            from django.contrib import messages

            if tag == 'success':
                messages.success(request, message)
            elif tag == 'warning':
                messages.warning(request, message)
            else:
                messages.error(request, message, extra_tags='error')

    request = tl.get_request()

    tab = 'tab' in request.GET and request.GET['tab'] and '?tab={}'.format(request.GET['tab']) or ''

    if get_params:
        get_params = f'{tab}{get_params}'
        if get_params[0] != '?':
            get_params = '?{}'.format(get_params.replace('?', ''))

    param_popup_in_request = '_popup' in request.GET

    if close_popup and param_popup_in_request:
        if '_popup_close_noreload' in request.GET and not close_popup_and_force_reload:
            return HttpResponse(f'<script>parent.close_fancybox_noreload("{message}", "{tag}");</script>')
        else:
            # reload por padrão
            set_message()
            return HttpResponse('<script>parent.close_fancybox();</script>')

    if url == '..' and (tag == 'success' or tag == 'warning' or tag == 'error') and param_popup_in_request:
        if '_popup_close_noreload' in request.GET and not close_popup_and_force_reload:
            return HttpResponse(f'<script>parent.close_fancybox_noreload("{message}", "{tag}");</script>')
        else:
            # reload por padrão
            set_message()
            return HttpResponse('<script>parent.close_fancybox();</script>')

    set_message()

    if param_popup_in_request and '_popup=1' not in url:
        # mantém a response no popup
        if '?' in url:
            url = f'{url}&_popup=1'
        else:
            url = f'{url}?_popup=1'

    if url == '.':
        url = f'{request.path}{get_params}'
    elif url == '..':
        url = breadcrumbs_previous_url(request)

    url = anchor and f'{url}#{anchor}' or url

    return HttpResponseRedirect(url)


def get_template_path(function):
    """
    Obtem o template, a renderizar, com base em uma função.

    Args
        function (Function): função.

    Returns:
        String com o template a ser renderizado.
    """
    app_name = get_app_name(function)
    if app_name == settings.PROJECT_NAME:
        return f'templates/{function.__name__}.html'
    return f'{app_name}/templates/{function.__name__}.html'


def render(template_name, ctx=None, request=None, template=None):
    """
    Especialização para o shortcut "*render*" que introduz informação do RequestContext no contexto.

    Args:
        template_name (string): string com o nome do template a renderizar;
        ctx (dict): dicionário contendo o contexto passado ao template;
        request (HttpRequest): objeto request.

    Returns:
        HttpResponse com template renderizado.
    """
    DEFAULT_TEMPLATE = 'djtools/templates/default.html'
    if not request or not hasattr(request, 'user'):
        request = tl.get_request()

    ctx = ctx or {}

    # Adiciona os media dos forms nesta variável do contexto para colocar as medias deles no html HEAD
    forms_media = ''
    for value in list(ctx.values()):
        if isinstance(value, BaseForm):
            media = str(value.media)
            if media not in forms_media:
                forms_media += media

    ctx['forms_media'] = forms_media

    # Breadcrumbs
    if request and (not is_ajax(request) and 'two_factor_authentication' not in request.path):
        breadcrumbs_add(request, ctx)

    try:
        if isinstance(template_name, list | tuple):
            select_template(template_name)
        else:
            get_template(template_name)
    except TemplateDoesNotExist as error:
        if template is not None:
            raise error
        return django_render(request, DEFAULT_TEMPLATE, ctx)

    return django_render(request, template_name, ctx)


def rtr(template=None, two_factor_authentication=False):
    """
    Decorator que adiciona renderização a uma função/view.

    Args:
        template (string): nome do template para renderizar.

    Returns:
        Função decorada.

    Note:
        Caso não seja passado o nome de um template, o template será calculado com base em *get_template_path*
    """

    def receive_function(function):
        @wraps(function, assigned=WRAPPER_ASSIGNMENTS)  # type: ignore[assignment]
        def receive_function_args(request, *args, **kwargs):
            if two_factor_authentication:
                response = solicitar_autenticacao_2fa(request, request.get_full_path())
                if response:
                    return response
            f_return = function(request, *args, **kwargs)
            if isinstance(f_return, HttpResponse):
                return f_return
            app_name = get_app_name(function)
            if isinstance(request, HttpRequest):
                request.help_key = f'{app_name}.{function.__name__}'
            template_list = [template or get_template_path(function)]
            if settings.LPS:
                if template:
                    template_name_lps = '{}/lps/{}/templates/{}'.format(app_name, settings.LPS, template.split('/')[-1])
                else:
                    template_name_lps = f'{app_name}/lps/{settings.LPS}/templates/{function.__name__}.html'
                template_list.insert(0, template_name_lps)
            return render(template_list, f_return, request, template)

        return receive_function_args

    return receive_function


def render_from_string(message, dictionary):
    template = Template(message)
    context = Context(dictionary)
    return template.render(context)


# `{{ nome }}` ou `{{ 123 }}` numa mesma linha, como o lexer do Django.
MARCADOR_RE = re.compile(r'\{\{[^\S\n]*([a-zA-Z]\w*|\d+)[^\S\n]*\}\}')


def substituir_marcadores(texto: str, valores: Mapping[str, object]) -> SafeString:
    """Substitui os marcadores `{{ nome }}` de um texto editado pelo usuário pelos `valores`.

    Ao contrário de `render_from_string`, não executa tags (`{% include %}`, `{% load %}`...): o texto do usuário não pode
    ser renderizado como template (#17926). Cada valor sai como o Django o renderizaria (localizado e escapado, salvo
    SafeString); marcador desconhecido vira ''. Tags, comentários e marcadores malformados ficam como texto.
    """
    contexto = Context()

    def substituir(match: re.Match) -> str:
        nome = match.group(1)
        valor = int(nome) if nome.isdigit() else valores.get(nome, '')
        return render_value_in_context(valor, contexto)

    return mark_safe(MARCADOR_RE.sub(substituir, texto))


def render_html_file(html, dicionario, request, task):
    dicionario['menu_as_html'] = request.session.get('menu_as_html', '')
    dicionario['debug'] = settings.DEBUG
    tmp = tempfile.NamedTemporaryFile(suffix='.html', mode='w+b', delete=False)
    tmp.write(render(html, dicionario, request=request).content)
    tmp.close()
    return task.finalize('Relatório gerado com sucesso.', '..', file_path=tmp.name)


class XmlResponse(HttpResponse):
    def __init__(self, data):
        HttpResponse.__init__(self, content=data, content_type='application/xhtml+xml')


class JsonResponse(HttpResponse):
    """
    Classe derivada do **HttpResponse** que retorna um conteúdo do tipo '*application/json*'.
    """

    def __init__(self, data, status=200, cls=DjangoJSONEncoder):
        """
        Construtor da classe.

        Args:
            data (dict|list): dados do conteúdo.
        """
        self.status_code = status
        content = json.dumps(data, cls=cls)
        HttpResponse.__init__(self, content=content, content_type='application/json')

    @staticmethod
    def invalid(message, field_name=None, field_index=None):
        """
        Método estático para conteúdo invalido.

        Args:
            message (string): mensagem a ser passada;
            field_name (string): nome do campo;
            field_index (): .

        Note:
            O argumento message deve ser Unicode, caso não seja, será convertida.
        """
        if not isinstance(message, str):
            message = message.decode('utf-8')
        return JsonResponse(
            {'valid': False, 'field_name': field_name, 'field_in_list': field_index is not None, 'field_index': field_index, 'message': message}
        )

    @staticmethod
    def valid(args=None, message=None):
        """
        Método estático para conteúdo válido.

        Args:
            args (): ;
            message (string): mensagem a ser passada.
        """
        data = {'valid': True}
        if args:
            for key in args:
                data[key] = args[key]
        if message:
            data['message'] = message
        return JsonResponse(data)


class PDFResponse(HttpResponse):
    """
    Classe derivada do **HttpResponse** que retorna um conteúdo do tipo '*application/pdf*'.
    """

    def __init__(self, data, nome='relatorio.pdf', anexo=False):
        """
        Construtor da classe.

        Args:
            data (byte): conteúdo a ser processado;
            nome (string): nome do arquivo;
            anexo (bool): indica que o conteúdo deve ser anexado.
        """
        HttpResponse.__init__(self, content=data, content_type='application/pdf')
        if anexo:
            self['Content-Disposition'] = f'attachment; filename={nome}'
        else:
            self['Content-Disposition'] = f'inline; filename={nome}'


def render_to_string(template_name, context=None, request=None, using=None):
    """
    Load a template and render it with a context. Return a string.

    template_name may be a string or a list of strings.
    """
    # verificando se existe lps
    lps_context = context.pop('lps_context', None)
    if settings.LPS and lps_context and 'nome_modulo' in lps_context:
        try:
            # verificando o template path para recuperar o nome do arquivo
            t_split = template_name.split('/')
            if t_split and isinstance(t_split, list) and t_split[-1] != '':
                template_file = t_split[-1]
            else:
                raise TemplateDoesNotExist('O template não pode ser encontrado.')

            # montando a url do template lps
            app_name = lps_context.get('nome_modulo')
            template_name_lps = f'{app_name}/lps/{settings.LPS}/templates/{template_file}'

            # se existir diretório extra dentro do diretorio de template
            if 'extra_dir' in lps_context:
                # montando a url do template lps
                extra_dirs = lps_context.get('extra_dir')
                template_name_lps = f'{app_name}/lps/{settings.LPS}/templates/{extra_dirs}/{template_file}'

            # verificando se o template existe, provocando o TemplateDoesNotExist caso o template não exista
            get_template(template_name_lps)
            # se o template existir, setamos o template_name para o novo endereço
            template_name = template_name_lps
        except TemplateDoesNotExist:
            # caso dê erro no get_template, não é necessário intervenção alguma
            pass

    if isinstance(template_name, list | tuple):
        template = select_template(template_name, using=using)
    else:
        template = get_template(template_name, using=using)
    return template.render(context, request)


class HttpResponseConflict(HttpResponse):
    status_code = 409


def CsvResponse(rows, name='report', attachment=True, encoding='utf-8', value_for_none='-', processo=None, delimiter=','):
    """
    Classe derivada do **HttpResponse** que retorna um conteúdo no formato CSV.

    Args:
        rows (list of list): Dados a serem processados;
        name (string): Nome do arquivo a ser enviado ao browser;
        attachment (bool): Indica se o conteúdo será atachado a resposta;
        encoding (string): Especifica a codificação do conteúdo;
        value_for_none (string): Valor padrão utilizado quando estiver tratando None;
        processo (object): Objeto de processamento em segundo plano;
        delimiter (string): Delimitador de campo no conteúdo gerado;

    Raises:
        ValueError: Caso o paramentro '*rows*' não sera uma lista de listas.

    Returns:
        Resposta contendo o conteúdo processado ou arquivo anexado.
    """
    if not isinstance(rows, list) or (len(rows) and not isinstance(rows[0], list)):
        raise ValueError('``rows`` must be a list of lists')
    if processo:
        response = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.csv')
    else:
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="{name}.csv"'
    writer = csv.writer(response, delimiter=delimiter, quotechar='"', quoting=csv.QUOTE_MINIMAL)
    for row in rows:
        row = [human_str(i, encoding=encoding, blank=value_for_none) for i in row]
        writer.writerow(row)

    if processo:
        response.close()
        processo.finalize('Arquivo gerado com sucesso.', '..', file_path=response.name)
    else:
        return response


def XlsResponse(
    rows, name='report', attachment=True, encoding='utf-8', value_for_none='-', convert_to_ascii=False, processo=None, iterate_processo=True
):
    """
    Retorna uma resposta no formato *xlsx*. Todos os valores valores serão convertidos com '*human_str*'.

    Args:
        rows: linhas do dado a ser processado;
        name (string): Nome do arquivo a ser anexado;
        attachment (bool): Indica se o conteúdo deverá ser um anexado;
        encoding (string): Codificação do conteúdo a ser retornado;
        value_for_none (string): Valor a ser utilizado quando estiver escrevendo um None;
        convert_to_ascii (bool): Indica se deve-se converter para o padrão **ASCII**;
        processo: Objeto que realiza o processamento em segundo plano;

    Raises:
        ValueError: caso '**rows**' não seja nem uma lista de listas e nem um dicionário de lista de listas

    Returns:
        Resposta contendo o conteúdo processado ou arquivo anexado.
    """
    import pandas as pd

    rows_as_list_of_lists = isinstance(rows, list) and len(rows) and isinstance(rows[0], list)

    rows_as_dict_of_list_of_lists = (
        isinstance(rows, dict)
        and len(rows)
        and isinstance(next(iter(rows.values())), list)
        and len(next(iter(rows.values())))
        and isinstance(next(iter(rows.values()))[0], list)
    )

    if not rows_as_list_of_lists and not rows_as_dict_of_list_of_lists:
        raise ValueError('``rows`` must be a "list of lists" or a "dict of list of lists"')

    # Dicionário que servirá de base para a montagem da planilha.
    dict_to_mount_excel = {}
    if rows_as_list_of_lists:
        dict_to_mount_excel['Planilha1'] = rows
    else:
        dict_to_mount_excel = rows

    if processo:
        tmp_dir = settings.TEMP_DIR
        if not os.path.exists(tmp_dir):
            os.mkdir(tmp_dir)
        response = tempfile.NamedTemporaryFile(mode='w+b', dir=tmp_dir, delete=False, suffix='.xlsx')
    else:
        response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        response['Content-Disposition'] = f'attachment; filename={name}.xlsx'

    def truncar_com_aviso(texto, qtd_caracteres=32765, aviso='[cortado]...'):
        if isinstance(texto, str) and len(texto) > qtd_caracteres:
            return texto[: qtd_caracteres - len(aviso)] + aviso
        return texto

    with pd.ExcelWriter(response) as writer:
        # Cada item do dicionário preencherá uma guia do arquivo excel.
        for sheet_name, sheet_rows in list(dict_to_mount_excel.items()):
            # Adicionando os dados da guia corrente. `sheet_rows` é uma matriz, ou seja, uma
            # lista de listas, logo `row_data` é uma lista.
            processed_rows = []
            for row_data in processo and iterate_processo and processo.iterate(sheet_rows) or sheet_rows:
                if convert_to_ascii:
                    row_data = [to_ascii(val) for val in row_data]

                # Aplicando o método `human_str` para cada item da lista.
                # Ex: ['2107029', 'Misael Barreto', '01054377430']
                row_data = [human_str(i, encoding=encoding, blank=value_for_none) for i in row_data]

                # Aplicando o método `truncar_com_aviso` para cada item da lista.
                row_data = [truncar_com_aviso(i) for i in row_data]
                processed_rows.append(row_data)

                if processo and iterate_processo and hasattr(processo, 'next'):
                    next(processo)

            df = pd.DataFrame(processed_rows)
            df.to_excel(writer, sheet_name=sheet_name, index=False, header=False)

    if processo:
        response.close()
        processo.finalize('Arquivo gerado com sucesso.', '..', file_path=response.name)
    else:
        return response


def respond_as_attachment(file_path, original_filename):
    fp = open(file_path, 'rb')
    response = HttpResponse(fp.read())
    fp.close()
    file_type, encoding = mimetypes.guess_type(original_filename)
    if file_type is None:
        file_type = 'application/octet-stream'
    response['Content-Type'] = file_type
    response['Content-Length'] = str(os.stat(file_path).st_size)
    if encoding is not None:
        response['Content-Encoding'] = encoding
    filename_header = f"filename*=UTF-8''{urllib.parse.quote(original_filename)}"
    response['Content-Disposition'] = 'attachment; ' + filename_header
    return response


def get_tabs(request, template, modulo='comum', dict_context=None):
    #
    # identificando o template
    template_name = f'{modulo}/templates/{template}'
    #
    # atualizando o dicinário do contexto
    context = {
        'lps_context': {'nome_modulo': modulo},  # esteja ativado, o lps será tratado para o módulo
    }
    if dict_context:
        context.update(dict_context)
    #
    # utilizando o render_to_string que dá suporte ao recurso de LPS
    return render_to_string(
        template_name=template_name,
        context=context,
        request=request,
    )


# Mapeia a extensão do arquivo para (content_type, Content-Disposition).
_FILE_RESPONSE_BY_EXTENSION = {
    '.xls': ('application/ms-excel', 'inline; filename=Relatorio.xls'),
    '.xlsx': ('application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', 'inline; filename=Relatorio.xlsx'),
    '.zip': ('application/zip', 'inline; filename=Arquivo.zip'),
    '.pdf': ('application/pdf', 'inline; filename=Documento.pdf'),
    '.csv': ('text/csv', 'inline; filename=Relatorio.csv'),
    '.txt': ('text/txt', 'inline; filename=Relatorio.txt'),
    '.json': ('application/json', 'attachment; filename=Relatorio.json'),
    '.docx': ('application/vnd.openxmlformats-officedocument.wordprocessingml.document', 'inline; filename=Arquivo.docx'),
}
_FILE_RESPONSE_DEFAULT = ('application/octet-stream', 'inline; filename=Arquivo.txt')


def generate_file_response(task):
    """Gera a resposta HTTP de download do arquivo temporário de uma task.

    O ``content_type`` e o ``Content-Disposition`` são definidos pela extensão
    do arquivo (ver :data:`_FILE_RESPONSE_BY_EXTENSION`); extensões não mapeadas
    usam ``application/octet-stream``. Arquivos ``.html`` são servidos como
    resposta padrão (sem ``Content-Disposition``).

    Args:
        task: Objeto com o atributo ``file`` (caminho do arquivo temporário).

    Returns:
        HttpResponse: Resposta com o conteúdo do arquivo; ou um redirect via
        :func:`httprr` quando o arquivo já expirou.
    """
    try:
        content = download_temporary_content(task.file)
    except Exception:
        return httprr('/', 'Arquivo expirado.', 'error')
    if task.file.endswith('.html'):
        return HttpResponse(content)
    _, extension = os.path.splitext(task.file)
    content_type, content_disposition = _FILE_RESPONSE_BY_EXTENSION.get(extension, _FILE_RESPONSE_DEFAULT)
    response = HttpResponse(content, content_type=content_type)
    response['Content-Disposition'] = content_disposition
    return response


class EmptyImageResponse(HttpResponse):
    def __init__(self):
        content = (
            b'GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00'
            b'\xff\xff\xff!\xf9\x04\x01\x00\x00\x00\x00,'
            b'\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02'
            b'D\x01\x00;'
        )
        super().__init__(content, content_type='image/gif')
