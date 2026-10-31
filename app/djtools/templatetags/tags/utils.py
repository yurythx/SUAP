import datetime
import re
import urllib.parse
from xml.dom.minidom import Element, parseString

import django
from django import forms, template
from django.apps import apps
from django.conf import settings
from django.contrib.admin.templatetags.admin_list import date_hierarchy as admin_date_hierarchy
from django.contrib.admin.templatetags.admin_list import pagination
from django.contrib.admin.views.main import PAGE_VAR, SEARCH_VAR
from django.contrib.auth.context_processors import PermWrapper
from django.contrib.contenttypes.models import ContentType
from django.core.cache import cache
from django.template import Library, Node, NodeList, Template, VariableDoesNotExist
from django.template.base import FilterExpression, TemplateSyntaxError
from django.template.context import Context
from django.template.defaultfilters import linebreaksbr, safe
from django.templatetags.static import StaticNode
from django.utils.html import format_html
from django.utils.safestring import SafeData, mark_safe
from django.utils.timesince import timesince
from django_tables2.templatetags.django_tables2 import RenderTableNode

from comum.models import Configuracao, Log
from comum.utils import get_logo_instituicao_fundo_transparente_url, get_logo_instituicao_url, tl
from djtools import HELP_XML_CONTENTS
from djtools.contrib.admin.helpers import get_admin_object_url, get_admin_view_object_url, get_djtools_delete_object_url
from djtools.contrib.auth.helpers import (
    get_change_permission_for_model,
    get_view_permission_for_model,
    has_change_permission,
    has_delete_permission,
    has_view_permission,
)
from djtools.forms.utils import render_form as render_form_util
from djtools.templatetags.filters import sanitize
from djtools.utils import get_ldap_conf, render_to_string

register = Library()


class HelpTextNode(Node):
    """Classe **Node** para processamento da **tag** help."""

    def render(self, context):
        """
        Método responsável por renderizar a tag.

        Args:
            context (dict): contexto passado para o template.

        Returns:
             String contendo os dados renderizados.
        """
        request = context['request']
        if not hasattr(request, 'help_key'):
            return ''
        app, view = request.help_key.split('.')
        if (
            request.help_key in HELP_XML_CONTENTS
            or request.META.get('PATH_INFO', '').startswith('/admin/')
            and (view.startswith(('change_', 'add_')))
        ):
            return mark_safe(
                f'<li><a href="/djtools/help_view/{app}/{view}/" class="btn default popup" data-reload-on-close="false"><span class="fas fa-question-circle" aria-hidden="true"></span> Ajuda</a></li>'
            )
        else:
            return ''


@register.tag
def help_button(parser, token):
    """Adiciona o botão para acesso a ajuda."""

    return HelpTextNode()


def show_view_model_icon(request, model):
    """
    Indica se o usuário tem permissão de visualização de dados.

    Args:
        request (HttpRequest): objeto request;
        model (Model): objeto de modelo.

    Returns:
         Bool se o usuário tiver persmissão de visualização de dados.
    """
    return hasattr(model, 'get_absolute_url') and request.user and request.user.has_perm(get_view_permission_for_model(model))


def show_edit_model_icon(request, model):
    """
    Indica se o usuário tem permissão de edição de dados.

    Args:
        request (HttpRequest): objeto request;
        model (Model): objeto de modelo.

    Returns:
         Bool se o usuário tiver persmissão de edição de dados.
    """
    if not request.user:
        return False

    edit_perm_codename = f'{model._meta.app_label}.change_{model.__name__.lower()}'

    def has_change_permission(model, perm):
        for p in model._meta.permissions:
            if p[0] == perm:
                return True

    # Model has no `edit` permission
    if not has_change_permission(model, edit_perm_codename.split('.')[1]):
        return request.user.has_perm(get_change_permission_for_model(model))

    # Model has `edit` permission
    return request.user.has_perm(edit_perm_codename)


def view_object_icon(obj, url_complement=None, has_perm=False):
    """
    Apresenta o icon de visualização de dados.

    Args:
        obj (Model): objeto de modelo;
        url_complement (string): complemento para a url.

    Returns:
        String com o código para apresentação do icon.
    """
    ret_url = ''
    if has_perm or has_view_permission(obj.__class__):
        if hasattr(obj, 'get_absolute_url') and obj.get_absolute_url():
            href = urllib.parse.urljoin(obj.get_absolute_url(), url_complement)
        else:
            href = get_admin_view_object_url(obj)
        ret_url = format_html(
            '<a class="icon icon-view" href="{}" title="{}"><span class="visually-hidden">Visualizar</span></a>', href, f'Ver {obj!s}'
        )
    return ret_url


register.simple_tag(view_object_icon)


def edit_object_icon(obj, has_perm=False):
    """
    Apresenta o icon de edição de dados.

    Args:
        obj (Model): objeto de modelo;
        url_complement (string): complemento para a url.

    Returns:
        String com o código para apresentação do icon.
    """
    if has_perm or has_change_permission(obj.__class__):
        return mark_safe(icon('edit', url=get_admin_object_url(obj), title=f'Editar {obj!s}'))
    return ''


register.simple_tag(edit_object_icon)


def delete_object_icon(obj):
    """
    Apresenta o icon de exclusão de dados.

    Args:
        obj (Model): objeto de modelo;
        url_complement (string): complemento para a url.

    Returns:
        String com o código para apresentação do icon.
    """
    if not has_delete_permission(obj=obj):
        return ''
    return mark_safe(icon('delete', url=get_djtools_delete_object_url(obj), title=f'Remover {obj!s}'))


register.simple_tag(delete_object_icon)


def dt_search_form(cl):
    return {'cl': cl, 'show_result_count': cl.result_count != cl.full_result_count, 'search_var': SEARCH_VAR}


dt_search_form = register.inclusion_tag('djtools/templates/adminutils/search_form.html')(dt_search_form)


def dt_pagination(cl):
    return pagination(cl)


dt_pagination = register.inclusion_tag('djtools/templates/adminutils/pagination.html')(dt_pagination)


def dt_date_hierarchy(cl):
    context = admin_date_hierarchy(cl)
    if context and context.get('choices'):
        context['choices'] = list(reversed(context['choices']))
    return context


dt_date_hierarchy = register.inclusion_tag('djtools/templates/adminutils/date_hierarchy.html')(dt_date_hierarchy)


def dt_paginator_number(cl, i):
    try:
        i = int(i)
    except Exception:
        return mark_safe('<li>...</li>')

    if i == cl.page_num:
        return mark_safe(f'<li class="active disabled"><a>{i}</a></li> ')
    else:
        url = cl.get_query_string({PAGE_VAR: i})
        classe = i == cl.paginator.num_pages - 1 and ' class="end"' or ''
        return mark_safe(f'<li><a href="{url}"{classe}>{i}</a></li> ')


dt_paginator_number = register.simple_tag(dt_paginator_number)


################################################################################
# {% render_form %}


class RenderFormNode(Node):
    """Classe **Node** para processamento da **tag** render_form."""

    def __init__(self, form_name, render_full=True, submit_button=True):
        """
        Construtor da classe.

        Args:
            form_name (string): nome do formulário;
            render_full (bool): indica se é uma renderização completa;
            submit_button (bool): indica se é para apresentar o botão de submissão de dados.
        """
        self.form_name = form_name
        self.render_full = render_full
        self.submit_button = submit_button

    def render(self, context):
        """
        Método responsável por renderizar a tag.

        Args:
            context (dict): contexto passado para o template.

        Returns:
             String contendo os dados renderizados.
        """
        if context.get(self.form_name):
            form = context[self.form_name]
        else:
            # Se for um formset passa aqui com "."
            form = getattr(context[self.form_name.split('.')[0]], self.form_name.split('.')[1])
        if not hasattr(form, 'SUBMIT_LABEL'):
            if isinstance(form, forms.ModelForm):
                form.SUBMIT_LABEL = 'Salvar'
            else:
                form.SUBMIT_LABEL = ''
        if hasattr(form, 'SUBMIT_BUTTON'):
            self.submit_button = form.SUBMIT_BUTTON
        if not hasattr(form, 'rendered'):
            form.rendered = render_form_util(form)
        form.ID = form.__class__.__name__.lower().replace('form', '_form')
        return render_to_string(
            template_name='djtools/templates/form.html',
            context={'form': form, 'render_full': self.render_full, 'submit_button': self.submit_button},
            request=context['request'],
        )


@register.tag
def render_form(parser, token):
    """
    Renderiza o form considerando seu atributo fieldsets.

    Args:
        parser ():
        token ():

    Examples:

        {% render_form form render_full=True  submit_label=True %}

    Returns:
        String contendo o código do **form**.

    Notes:
        * O ``render_full`` por padrão é True e define que o formulário será renderizado totalmente, com mensagens de
          validação e a própria tag form. Caso seja False, será renderizado apenas o form, como o form.as_table.

        * O ``submit_label`` por padrão é True e define que o formulário será renderizado com um botão de submissão
          padrão
    """
    contents_splited = token.split_contents()
    if len(contents_splited) == 2:
        _tag_name, form_name = contents_splited
        render_full = True
        submit_button = True
    elif len(contents_splited) == 3:
        _tag_name, form_name, render_full = contents_splited
        render_full = not ('0' in render_full or 'False' in render_full)
        submit_button = True
    elif len(contents_splited) == 4:
        _tag_name, form_name, render_full, submit_button = contents_splited
        render_full = not ('0' in render_full or 'False' in render_full)
        submit_button = not ('0' in submit_button or 'False' in submit_button)
    #
    return RenderFormNode(form_name, render_full, submit_button)


################################################################################
# {% box %}


class RenderBox(Node):
    """Classe **Node** para processamento da **tag** box."""

    def __init__(self, nodelist: NodeList, args: dict[str, FilterExpression]) -> None:
        self.nodelist = nodelist
        self.args = args

    def resolve(self, key: str, context: Context) -> str:
        """
        Resolve o argumento ``key`` da tag.

        Só um literal escrito no template (``{% box 'Log' badge="{{ rotina.logs.count }}" %}``) é renderizado como
        template. O valor de uma variável ou filtro pode vir de dado do usuário: compilá-lo como template executaria
        ``{{ }}``/``{% %}`` no servidor com o contexto inteiro, então ele é devolvido como texto e o autoescape do
        ``box.html`` se aplica.
        """
        expr = self.args.get(key)
        if expr is None:
            return ''
        try:
            valor = expr.resolve(context)
        except VariableDoesNotExist:
            return ''
        if valor is None:
            return ''
        if not expr.is_var and not expr.filters:
            return Template(valor).render(Context(context))
        return valor if isinstance(valor, SafeData) else str(valor)

    def render(self, context: Context) -> str:
        return render_to_string(
            'djtools/templates/box.html',
            {
                'title': self.resolve('title', context),
                'class': self.resolve('class', context),
                'boxid': self.resolve('boxid', context),
                'badge': self.resolve('badge', context),
                'extra': self.resolve('extra', context),
                'content': self.nodelist.render(context),
            },
        )


@register.tag(name='box')
def do_box(parser, token):
    bits = token.split_contents()
    # retirando o nome da tag
    bits.pop(0)
    args = {}

    # O primeiro argumento é sempre o title (obrigatório)
    if not bits:
        raise template.TemplateSyntaxError("A tag 'box' requer ao menos um argumento (title).")
    args['title'] = parser.compile_filter(bits.pop(0))

    # Os próximos argumentos podem ser posicionais (class, boxid, badge) ou nomeados
    param_names = ['class', 'boxid', 'badge', 'extra']
    for i, bit in enumerate(bits):
        if '=' in bit:
            key, val = bit.split('=', 1)
            args[key] = parser.compile_filter(val)
        else:
            # Se for posicional, atribui na ordem class, boxid, badge
            if i < len(param_names):
                args[param_names[i]] = parser.compile_filter(bit)
            else:
                raise template.TemplateSyntaxError(f"Argumento posicional inesperado: '{bit}'")

    nodelist = parser.parse(('endbox',))
    parser.delete_first_token()
    return RenderBox(nodelist, args)


@register.simple_tag
def media_filter_box():
    """
    Renderiza os arquivo de **CSS** e **JS**.

    Returns:
         String contendo a **tag link** e **script** para apresentar boxes.
    """
    return mark_safe(
        '<link type="text/css" rel="stylesheet" href="/static/djtools/filter_box/css/filter_box.css" />'
        '<script src="/static/djtools/filter_box/js/filter_box.js"></script>'
    )


@register.tag(name='filter_box')
def do_filter_box(parser, token):
    """
    Renderiza a **tag** box para filtros com o conteúdo passado.

    Args:
        parser ():
        token ():

    Returns:
        String contendo o código **HTML** do box.
    """
    nodelist = parser.parse(('endfilter_box',))
    contents_splited = token.split_contents()
    if len(contents_splited) == 1:
        expansible = False
        expanded = True
    elif len(contents_splited) == 2:
        _tag_name, expanded = contents_splited
        expansible = True
        expanded = expanded not in ('0', 'False')
    parser.delete_first_token()
    return RenderFilterBox(nodelist, expansible, expanded)


class RenderFilterBox(Node):
    """Classe **Node** para processamento da **tag** render_form."""

    def __init__(self, nodelist, expansible=False, expanded=True):
        """
        Construtor da classe.

        Args:
            nodelist (list): lista dos nós que compõe seu body;
            expansible (bool): indica se o box será expansível;
            expanded (bool): indica se o box deve ser extendido.
        """
        self.nodelist = nodelist
        self.expansible = expansible
        self.expanded = expanded

    def render(self, context):
        """
        Método responsável por renderizar a tag.

        Args:
            context (dict): contexto passado para o template.

        Returns:
             String contendo os dados renderizados.
        """
        content = re.sub(r'[\t\n\r]', '', self.nodelist.render(context))
        data = []
        pairs = 0

        try:
            root_node = parseString(content).documentElement
            if root_node.nodeName == 'table':
                for row_tag in root_node.childNodes:
                    if row_tag.nodeType == Element.ELEMENT_NODE and row_tag.nodeName == 'tr':
                        row = []

                        item_tags = []
                        for child in row_tag.childNodes:
                            if child.nodeType == Element.ELEMENT_NODE and child.nodeName == 'td':
                                item_tags.append(child)

                        n_elem = len(item_tags)
                        for i in range(0, n_elem, 2):
                            # é preciso testar para evitar extrair conteúdo de tags <td> sem conteúdo
                            if item_tags[i].firstChild:
                                if item_tags[i].firstChild.nodeType == Element.TEXT_NODE:
                                    key = item_tags[i].firstChild.toxml() + ':'
                                else:
                                    key = item_tags[i].firstChild.toxml()
                            else:
                                # é repassado string vazia quando a tag <td> não possui conteúdo
                                key = ''

                            # verifica se existe algum par chave/valor em que foi repassado apenas a chave e neste case
                            # repassa a string '!@#' que é tratada pelo template para que não seja apresentado nenhum default
                            if (n_elem % 2) != 0 and i == n_elem - 1:
                                value = '!@#'
                            elif item_tags[i + 1].firstChild:
                                value = item_tags[i + 1].firstChild.toxml()
                            else:
                                value = ''

                            # o None é substituído por que em alguns casos o termo é enviado pelo template que chamou o templatetag
                            row.append([key.replace('None', ''), value.replace('None', '')])

                        data.append(row)

                for row in data:
                    if len(row) > pairs:
                        pairs = len(row)

                return render_to_string(
                    'djtools/templates/render_filter_box.html',
                    {'data': data, 'expansible': self.expansible, 'expanded': self.expanded, 'max_pairs': pairs},
                )

        except Exception:
            raise


@register.simple_tag
def debug_info():
    user = tl.get_user()
    bd = settings.DATABASES['default']
    info = f'Django <strong>{django.get_version()}</strong>'
    if 'localhost' in settings.SITE_URL or (user and user.is_superuser):
        info = f'{info} | Project path: <strong>{settings.BASE_DIR}</strong> | Database: <strong>{bd["NAME"]} {bd["USER"]}@{bd["HOST"]}:{bd["PORT"]} | Date Time: {datetime.datetime.now().isoformat()}</strong>'
    return mark_safe(info)


def icon(type, url, title='', extra_class='', confirm=''):
    if title == '':
        if type == 'view':
            title = 'Visualizar'
        elif type == 'edit':
            title = 'Editar'
        else:
            title = 'Remover'
    font = f'icon icon-{type}' if type in ['view', 'edit', 'delete'] else f'icon fas fa-{type}'
    return render_to_string('djtools/templates/icon.html', {'font': font, 'url': url, 'title': title, 'extra_class': extra_class, 'confirm': confirm})


class RenderIcon(Node):
    def __init__(self, type, url, title, extra_class, show_title):
        self.type = (type or '')[1:-1]
        self.url = (url or '')[1:-1]
        if title == '':
            current_type = type[1:-1]
            if current_type == 'view':
                self.title = 'Visualizar'
            elif current_type == 'edit':
                self.title = 'Editar'
            else:
                self.title = 'Remover'
        else:
            self.title = (title or '')[1:-1]
        self.extra_class = (extra_class or '')[1:-1]
        self.show_title = (show_title or '')[1:-1]

    def render(self, context):
        font = f'icon icon-{self.type}' if self.type in ['view', 'edit', 'delete'] else f'icon fas fa-{self.type}'
        return render_to_string(
            'djtools/templates/icon.html',
            {
                'font': Template(font).render(Context(context)),
                'url': Template(self.url).render(Context(context)) or '#',
                'extra_class': Template(self.extra_class).render(Context(context)),
                'title': Template(self.title).render(Context(context)),
                'show_title': Template(self.show_title).render(Context(context)),
            },
        )


@register.tag(name='icon')
def icon_tag(parser, token):
    contents_splited = token.split_contents()
    max_tamanho_lista = 6
    tamanho_lista = len(contents_splited)
    if 2 > tamanho_lista > max_tamanho_lista:
        raise Exception('A templatetag icon deve conter apenas o título.')

    contents_splited = contents_splited + [''] * (max_tamanho_lista - tamanho_lista)
    _tag_name, type, url, title, extra_class, show_title = contents_splited
    return RenderIcon(type, url, title, extra_class, show_title)


@register.tag(name='render_table')
def render_table(parser, token):
    bits = token.split_contents()
    try:
        _tag, table = bits.pop(0), parser.compile_filter(bits.pop(0))
    except ValueError:
        raise TemplateSyntaxError(f"'{bits[0]}' must be given a table or queryset.")

    template = parser.compile_filter(bits.pop(0)) if bits else parser.compile_filter('"table_plus.html"')
    return RenderTableNode(table, template)


@register.simple_tag(name='verbose_field_name')
def get_verbose_field_name(obj, field_name):
    """Returns verbose_name for a field."""

    field = obj._meta.get_field(field_name)
    return get_verbose_name(field)


@register.simple_tag(name='verbose_field_name_by_class')
def get_verbose_field_name_by_class(class_, field_name):
    """
    Renderiza o **verbose_name** de um campo de formulário.

    Args:
        class_ (string) nome da classe que contem o campo;
        field_name (string): nome do campo.

    Returns:
        String contendo o **verbose_name**.
    """

    """
    Returns verbose_name for a field.
    """
    class_module, class_name = class_.split('.')
    module = __import__(class_module)
    class_ = getattr(module.models, class_name)
    field = class_._meta.get_field(field_name)
    return get_verbose_name(field)


def get_verbose_name(field):
    """
    Renderiza o **verbose_name** de um campo de formulário.

    Args:
        field (Field): campo a obter o **verbose_name**.

    Returns:
        String contendo o **verbose_name**.
    """
    verbose_name = field._verbose_name
    # if is not defined "title" the field name
    if not verbose_name:
        verbose_name = field.verbose_name.title()

    return verbose_name


@register.simple_tag
def ldap_actions(obj):
    """Retorna ações relativas ao ldap_backend para o `obj`."""
    ldap_conf = get_ldap_conf()
    if not ldap_conf or not ldap_conf.has_connectivity() or not ldap_conf.has_write_permission():
        return ''
    user = tl.get_user()
    perms = PermWrapper(user)
    if not perms['ldap_backend']:
        return ''

    template_str = """
    <li class="has-child">
        <a class="btn" href="#"><span class="fas fa-square" aria-hidden="true"></span> {{ ldap_conf.get_solucao_display }}</a>
        <ul>
            {% if perms.ldap_backend.view_ldap_user and obj_tem_usuario_ldap %}
                <li><a href="/ldap_backend/show_object/{{ obj.username}}/">Ver usuário</a></li>
            {% endif %}
            {% if perms.ldap_backend.sync_ldap_user %}
                <li>
                    <a href="/ldap_backend/sync_user/{{ obj.username}}/">
                        {{ texto_sync }} usuário
                    </a>
                </li>
            {% endif %}
        </ul>
    </li>"""
    obj_tem_usuario_ldap = obj.get_vinculo().get_usuario_ldap(attrs=['dn'])
    texto_sync = obj_tem_usuario_ldap and 'Sincronizar' or 'Criar'
    return Template(template_str).render(Context(locals()))


@register.simple_tag
def icone(obj: str, extra_class: str = '') -> SafeData:  # Font Awesome (Solid)
    """
    Renderiza o icom com base na fonte Awesome (Solid).

    Args:
        obj (str): ícone a ser apresentado.
        extra_class (str): classes CSS adicionais para o ícone.

    Returns:
        String contendo a tag do icon.
    """
    classes = f'icone fas fa-{obj}'
    if extra_class:
        classes += f' {extra_class}'
    return format_html('<span class="{}" aria-hidden="true"></span>', classes)


@register.simple_tag
def progressbar(percent):
    try:
        if isinstance(percent, str) and '/' in percent:
            numerator, denominator = map(float, percent.split('/'))
            percent_value = (numerator / denominator) * 100 if denominator != 0 else 0
            display_text = percent
        else:
            percent_value = float(percent)
            display_text = f'{percent_value:.0f}%'
    except ValueError, ZeroDivisionError:
        percent_value = 0
        display_text = '0%'

    percent_display = round(percent_value, 2)

    return mark_safe(
        f'<div class="progressbar-container">'
        f'<progress value="{percent_display}" max="100" data-progress="p{percent_display}%"></progress>'
        f'<span>{display_text}</span>'
        f'</div>'
    )


@register.simple_tag(takes_context=True)
def comentarios(context, obj, msg=None, pode_comentar=None):
    """
    Renderiza os elementos para tratamento de comentários para um objeto de modelo.

    Args:
        obj (Model): objeto base para os comentários;
        msg (string): mensagem.
        pode_comentar: boolean resultante de uma cálculo personalizado
            indicando permissão ou não para adicionar comentários.

    Returns:
        String contendo conteúdo para tratamento das mensagens.
    """

    Comentario = apps.get_model('comum', 'Comentario')
    aplicacao = obj._meta.app_label
    modelo = obj._meta.model_name

    def montar_arvore(content_type, raiz, primeiro=False):
        out = []
        if primeiro:
            out.append('<ul class="lista-comentarios">')
        else:
            if raiz:
                out.append('<ul>')

        for item in raiz:
            profile = item.cadastrado_por.get_profile()
            is_owner = context['user'] == item.cadastrado_por
            owner_class = 'is_owner' if is_owner else ''

            out.append(f"""<li class="comment-item {owner_class}">
                <div class="photo-circle sm">
                    <img title="{profile.nome_usual}" src="{item.cadastrado_por.get_vinculo().get_foto_75x100_url()}">
                </div>
                <div class="comentario">""")

            texto = linebreaksbr(sanitize(item.texto), False)
            if item.desconsiderado:
                out.append(f'<p><s title="Comentário desconsiderado pelo autor">{texto}</s></p>')
            else:
                out.append(f'<p>{texto}</p>')

            out.append(f"""<div class="d-flex align-items-end justify-content-between">
                <p class="obs mb-0" title="Em {item.cadastrado_em.strftime('%d/%m/%Y')}"><strong>{profile.nome_usual}</strong> há {timesince(item.cadastrado_em)} ({item.cadastrado_em.strftime('%d/%m/%Y %H:%M')})</p>
                <ul class="action-bar">""")

            if not item.desconsiderado and context['user'] == item.cadastrado_por:
                out.append(
                    f'<li><a href="/comum/comentario/desconsiderar/{item.id}/" class="btn warning confirm" title="Desconsiderar Comentário"><span class="fas fa-strikethrough" aria-hidden="true"></span><span class="visually-hidden">Desconsiderar Comentário</span></a></li>'
                )

            if pode_comentar is None:
                if hasattr(obj, 'pode_comentar'):
                    if obj.pode_comentar():
                        out.append(f'<a href="/comum/comentario/add/{aplicacao}/{modelo}/{obj.pk}/{item.id}/" class="btn popup">Responder</a>')
                else:
                    out.append(f'<a href="/comum/comentario/add/{aplicacao}/{modelo}/{obj.pk}/{item.id}/" class="btn popup">Responder</a>')

            elif pode_comentar:
                out.append(f'<li><a href="/comum/comentario/add/{aplicacao}/{modelo}/{obj.pk}/{item.id}/" class="btn popup">Responder</a></li>')

            out.append('</ul></div></div>')
            out.append(
                montar_arvore(
                    content_type,
                    Comentario.objects.filter(content_type=content_type, object_id=obj.pk, resposta__id=item.id).order_by('-cadastrado_em'),
                )
            )
            out.append('</li>')
        if raiz:
            out.append('</ul>')
        return '\n'.join(out)

    content_type = ContentType.objects.get(app_label=obj._meta.app_label, model=obj._meta.model_name)
    out = []

    if pode_comentar is None:
        if hasattr(obj, 'pode_comentar'):
            if obj.pode_comentar():
                out.append('<ul class="action-bar">')
                out.append(
                    f'<li><a href="/comum/comentario/add/{aplicacao}/{modelo}/{obj.pk}/" class="btn success popup"><span class="fas fa-plus" aria-hidden="true"></span> Adicionar Comentário</a></li>'
                )
                out.append('</ul>')

        else:
            out.append('<ul class="action-bar">')
            out.append(
                f'<li><a href="/comum/comentario/add/{aplicacao}/{modelo}/{obj.pk}/" class="btn success popup"><span class="fas fa-plus" aria-hidden="true"></span> Adicionar Comentário</a></li>'
            )
            out.append('</ul>')

    elif pode_comentar:
        out.append('<ul class="action-bar">')
        out.append(
            f'<li><a href="/comum/comentario/add/{aplicacao}/{modelo}/{obj.pk}/" class="btn success popup"><span class="fas fa-plus" aria-hidden="true"></span> Adicionar Comentário</a></li>'
        )
        out.append('</ul>')

    raiz = Comentario.objects.filter(content_type=content_type, object_id=obj.pk, resposta=None).order_by('-cadastrado_em')
    if raiz.exists():
        out.append(montar_arvore(content_type, raiz, True))
    else:
        if msg:
            out.append(f'<p class="alert alert-warning">{msg}</p>')
        else:
            out.append('<p class="alert alert-warning">Nenhum comentário até o momento.</p>')
    return safe('\n'.join(out))


@register.simple_tag(takes_context=True)
def index_paginacao(context):
    start_index = context['page_obj'].start_index()
    counter = context['forloop']['counter']
    if counter == 1:
        return start_index
    else:
        return (start_index + counter) - 1


@register.simple_tag
def total_coluna_moeda(tabela_id, indice):
    """
    Retorna uma função javascript que calcula o total da coluna passada como parâmetro.

    Args:
        tabela_id (string): id da tabela;
        indice (string):

    Returns:
        String contendo o código da função JS.

    Notes:
        https://pt.stackoverflow.com/questions/188190/formatar-moeda-com-separador-de-milhar
    """
    template_str = f"""
        <script>
            resultado = 0;
            columns = $("#{tabela_id} tbody tr td:nth-child({indice})");
            columns.each(function (index, value){{
                resultado += parseFloat(this.innerText.replace('R$ ', '').replace('.', '').replace(',', '.')) || 0;
            }});
            resultado_formatado = resultado.toFixed(2).split('.');
            resultado_formatado[0] = "R$ " + resultado_formatado[0].split(/(?=(?:...)*$)/).join('.');
            resultado_formatado = resultado_formatado.join(',');
            document.write(resultado_formatado);
        </script>
        """
    return Template(template_str).render(Context(locals()))


@register.simple_tag
def total_coluna_inteiro(tabela_id, indice, linha_inicial=''):
    """
    Retorna uma função javascript que calcula o total da coluna passada como parâmetro.

    Args:
        tabela_id (string): id da tabela;
        indice (string):
        linha_inicial (int): linha inicial para cálculo.

    Returns:
        String contendo o código da função JS.
    """
    if linha_inicial:
        linha_inicial = f':nth-child(n+{linha_inicial})'

    template_str = f"""
        <script>
            resultado = 0;
            columns = $("#{tabela_id} tbody tr{linha_inicial} td:nth-child({indice})");
            columns.each(function (index, value){{
                resultado += parseInt(this.innerText);
            }});
            document.write(resultado);
        </script>
        """
    return Template(template_str).render(Context(locals()))


@register.simple_tag
def total_linha_inteiro(tabela_id, indice):
    """
    Retorna uma função javascript que calcula o total da linha passada como parâmetro.

    Args:
        tabela_id (string): id da tabela;
        indice (string):

    Returns:
        String contendo o código da função JS.
    """
    template_str = f"""
        <script>
            resultado = 0;
            rows = $("#{tabela_id} tbody tr:nth-child({indice}) td").not(".nao-somar");
            rows.each(function (index, value){{
                resultado += parseInt(this.innerText);
            }});
            document.write(resultado);
        </script>
        """
    return Template(template_str).render(Context(locals()))


@register.simple_tag
def get_valor_por_chave(app, valor):
    """
    Obtem o valor para a chave passada.

    Args:
        app (string): nome da aplicação;
        valor (string): chave para pesquisa.

    Returns:
        Valor do item para a chave passada.
    """
    return f'{Configuracao.get_valor_por_chave(app, valor)}'


@register.simple_tag
def get_logo_instituicao():
    """
    Obtem a logo da instituição a partir das configurações do sistema.

    Returns:
        Valor do path para o arquivo de logo.
    """
    return f'{get_logo_instituicao_url()}'


@register.simple_tag
def get_logo_instituicao_fundo_transparente():
    """
    Obtem a logo da instituição com fundo transparente a partir das configurações do sistema.

    Returns:
        Valor do path para o arquivo de logo com fundo transparente.
    """
    return f'{get_logo_instituicao_fundo_transparente_url()}'


@register.simple_tag
def data_ultima_importacao_siape():
    timeout = 86400
    if not cache.get('data_ultima_importacao_siape', local_ttl=60):
        try:
            importacao = Log.objects.filter(app='rh', titulo='Importação de arquivos').order_by('-id').first()
            data = importacao.horario.strftime('%d/%m/%Y') if importacao else None
            cache.set('data_ultima_importacao_siape', data, timeout)
        except Exception:
            cache.set('data_ultima_importacao_siape', '', timeout)
    return cache.get('data_ultima_importacao_siape', local_ttl=60) or '-'


@register.simple_tag
def data_ultima_atualizacao_suap():
    timeout = 86400
    if not cache.get('data_ultima_atualizacao_suap', local_ttl=60):
        try:
            atualizacao = Log.objects.filter(titulo='Atualização do Sistema').order_by('-id').first()
            data = atualizacao.horario.strftime('%d/%m/%Y %H:%M') if atualizacao else None
            cache.set('data_ultima_atualizacao_suap', data, timeout)
        except Exception:
            cache.set('data_ultima_atualizacao_suap', '', timeout)
    return cache.get('data_ultima_atualizacao_suap', local_ttl=60) or '-'


class EscapeScriptNode(Node):
    TAG_NAME = 'escapescript'

    def __init__(self, nodelist):
        super().__init__()
        self.nodelist = nodelist

    def render(self, context):
        out = self.nodelist.render(context)
        escaped_out = out.replace('</script>', '<\\/script>')
        return escaped_out


@register.tag(EscapeScriptNode.TAG_NAME)
def media(parser, token):
    nodelist = parser.parse(('end' + EscapeScriptNode.TAG_NAME,))
    parser.delete_first_token()
    return EscapeScriptNode(nodelist)


class SafeStaticNode(StaticNode):
    def render(self, context):
        url = self.url(context)
        if self.varname is None:
            return url
        context[self.varname] = url
        return ''


@register.tag('safe_static')
def safe_static(parser, token):
    return SafeStaticNode.handle_token(parser, token)
