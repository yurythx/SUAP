import io
import operator
from collections.abc import Sequence
from functools import partial, reduce, update_wrapper

from django import forms
from django.conf import settings
from django.contrib import admin, messages

#
from django.contrib.admin import helpers
from django.contrib.admin.checks import InlineModelAdminChecks
from django.contrib.admin.decorators import display
from django.contrib.admin.options import IncorrectLookupParameters, InlineModelAdmin, csrf_protect_m, flatten_fieldsets
from django.contrib.admin.templatetags.admin_urls import add_preserved_filters
from django.contrib.admin.utils import lookup_spawns_duplicates, unquote
from django.contrib.admin.views.main import ERROR_FLAG

#
from django.core.exceptions import FieldDoesNotExist, PermissionDenied, SuspiciousOperation
from django.core.management import call_command
from django.db import models, transaction
from django.db.models.fields.related import ManyToManyField
from django.forms import ALL_FIELDS
from django.forms.formsets import all_valid
from django.forms.models import BaseModelFormSet, modelform_defines_fields, modelformset_factory
from django.http import Http404, HttpRequest, HttpResponse, HttpResponseRedirect
from django.template.response import TemplateResponse
from django.urls import URLPattern, path, reverse
from django.utils.encoding import force_str
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.utils.translation import gettext as _
from reversion_compare.admin import CompareVersionAdmin
from sentry_sdk import capture_exception

import djtools.contrib.auth.helpers
from djtools import tasks, utils
from djtools.contrib.admin.helpers import ConfirmacaoExclusaoForm
from djtools.contrib.admin.views import ChangeListPlus
from djtools.contrib.auth.helpers import get_change_permission_for_model, get_view_permission_for_model
from djtools.db.models import ManyToManyFieldPlus
from djtools.db.models.helpers import get_search_field
from djtools.forms import ModelFormPlus, NonrelatedInlineFormSet, nonrelated_inlineformset_factory
from djtools.forms.fields import DateFieldPlus, DateTimeFieldPlus, TimeFieldPlus
from djtools.forms.widgets import RegionalDateTimeWidget, RegionalDateWidget, RegionalTimeWidget
from djtools.lps import MetaModelAdminPlus
from djtools.templatetags.tags import edit_object_icon, view_object_icon
from djtools.utils import eval_attr, httprr, is_ajax, normalizar_termos_busca

FORMFIELD_OVERRIDES = {
    models.DateTimeField: {'form_class': DateTimeFieldPlus, 'widget': RegionalDateTimeWidget},
    models.DateField: {'form_class': DateFieldPlus, 'widget': RegionalDateWidget},
    models.TimeField: {'form_class': TimeFieldPlus, 'widget': RegionalTimeWidget},
}


AVISO_FILTRO_INVALIDO = 'Você escolheu algum filtro inválido, por favor tente novamente nas opções disponíveis.'


def _so_flag_de_erro(request: HttpRequest) -> bool:
    """A URL só tem ``?e=1``: o Django já redirecionou para cá, então a listagem falha sem nenhum filtro do usuário."""
    return set(request.GET) == {ERROR_FLAG}


class TabularInlinePlus(admin.TabularInline):
    formfield_overrides = FORMFIELD_OVERRIDES

    def get_formset(self, request, obj=None, **kwargs):
        """
        Torna o ``request`` disponível no ``form``.
        """
        FormSetClass = super().get_formset(request, obj, **kwargs)
        FormSetClass.form.request = request  # type: ignore[assignment]
        return FormSetClass


class StackedInlinePlus(admin.StackedInline):
    formfield_overrides = FORMFIELD_OVERRIDES

    @property
    def media(self):
        return forms.Media(css={}, js=[])

    def get_formset(self, request, obj=None, **kwargs):
        """
        Torna o ``request`` disponível no ``form``.
        """
        FormSetClass = super().get_formset(request, obj, **kwargs)
        FormSetClass.form.request = request  # type: ignore[assignment]
        return FormSetClass


class ModelAdminPlus(admin.ModelAdmin, metaclass=MetaModelAdminPlus):
    """
    O ModelAdminPlus foi criado para dar mais funcionalidades ao ModelAdmin.

    Atributos:
    ==========
    - list_display_icons = False
        O link para edição de cada objeto fica sendo um ícone (ao invés de ser o primeiro atributo do list_display)
    - show_count_on_tabs = False
        Mostra a quantidade de registros para cada aba, é obrigatório passa os parâmetro *args e **kwargs tanto no
        método queryset quanto nos métodos das tabs para passar a variável "skip_tab".

    Métodos:
    ========

    get_action_bar(self, request)
    -----------------------------

    get_tabs(self, request)
    -----------------------
    Deve retornar uma lista de strings. Cada string deve corresponder ao nome de um método do ModelAdmin.
    Se get_tabs retornar ``['foo']`` o método ``foo(self, request)`` deve ser implementado.

    export_to_csv(self, request, queryset)
    --------------------------------------
    Deve retornar uma lista de listas. Esse resultado será retornado como um CsvResponse.

    get_action_bar_view(self, request, obj)
    ----------------------------------
    Retorna uma lista de itens a serem exibidor na view do objeto
    """

    # Atributos modificados de ``admin.ModelAdmin``
    queryset_list_template = None
    change_list_template = 'djtools/templates/adminutils/change_list.html'
    change_form_template = 'djtools/templates/adminutils/change_form.html'
    formfield_overrides = FORMFIELD_OVERRIDES

    # Atributos exclusivos do ``ModelAdminPlus``
    content_main_admin_template = 'djtools/templates/adminutils/content_main_admin.html'
    list_display_icons = False
    show_count_on_tabs = False
    show_tab_any_data = True
    export_to_xls = False
    list_xls_display = None
    preserve_filters = True
    # utilizado para filtros em cascata para o campo autocomplete
    list_filter_autocomplete_form_filters = None
    # utilizado para indicar quais filtros permitem multiplas escolhas
    list_filter_multiple_choices = ()
    # Configuração que faz o admin ignorar termos com menos de 3 caracteres
    avoid_short_search = True
    # Limita a quantidade de termos no campo search
    max_terms_search = 10
    # Esconde um determinado filter
    hidden_filters = []
    no_filters = False
    # Habilita/Desabilita o carregamento do changelist com ajax
    filters_ajax = True
    label_input_search_fields = 'Texto:'
    # Mensagem personalizada exibida quando o queryset resultar vazio (opcional)
    empty_queryset_message = None

    add_form = None
    action_form = helpers.ActionForm
    change_form = None
    add_fieldsets = None

    def get_actions(self, request):
        actions = super().get_actions(request)
        try:
            del actions['delete_selected']
        except KeyError:
            pass
        return actions

    def get_model_perms(self, request):
        super_check = request.path.startswith('/admin/') and request.path.count('/') in (2, 3)
        return (
            super().get_model_perms(request)
            if super_check
            else {
                'add': False,
                'change': False,
                'delete': False,
                'view': False,
            }
        )

    @property
    def media(self):
        return forms.Media(css={}, js=[])

    def get_tab_corrente(self):
        return self.request.GET.get('tab', None)

    def show_list_display_icons(self, obj):
        out = []
        icons_html = []

        # Tentando verificar a aba atual que está sendo utilizada no admin. Se existir, tentamos verificar se para a tab
        # corrente foi especificado algum parâmetro para a url que será chamada em cada registro listado no grid.
        current_tab = self.get_tab_corrente()
        view_object_url_complement = None
        if current_tab:
            if hasattr(self, current_tab) and hasattr(getattr(self, current_tab), 'view_object_url_params'):
                view_object_url_complement = getattr(self, current_tab).view_object_url_params

        admin_can_view = self.has_view_permission(self.request, obj)
        admin_can_change = self.has_change_permission(self.request, obj)

        if admin_can_view or admin_can_change:
            if admin_can_view:
                icons_html.append(view_object_icon(obj, view_object_url_complement, True))
            if admin_can_change:
                icons_html.append(edit_object_icon(obj, True))

        for icon_html in icons_html:
            if icon_html:
                out.append(icon_html)

        return mark_safe(''.join(out))

    show_list_display_icons.short_description = '#'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.search_fields and get_search_field(self.model):
            self.search_fields = (get_search_field(self.model).name,)

    def url_wrap(self, view):
        def wrapper(*args, **kwargs):
            return self.admin_site.admin_view(view)(*args, **kwargs)

        #
        return update_wrapper(wrapper, view)

    def get_changelist(self, request, **kwargs):
        """
        Torna o ``request`` disponível em métodos invocados no changelist admin e utiliza
        a classe ``ChangeListPlus``.
        """
        self.request = request
        return ChangeListPlus

    def get_list_display(self, request):
        """
        Adiciona o método ``show_list_display_icons`` no ``list_display`` se for
        o caso.
        """
        list_display = tuple(self.list_display[:])
        if self.list_display_icons:
            if (
                self.has_view_permission(request)
                or self.has_change_permission(request)
                or request.user.has_perm(get_view_permission_for_model(self.model))
                or request.user.has_perm(get_change_permission_for_model(self.model))
            ):
                list_display = ('show_list_display_icons', *list_display)
            else:
                self.list_display_links = None

        return list_display

    def get_list_display_links(self, request: HttpRequest, list_display: Sequence[str]) -> Sequence[str] | None:
        """
        Sem ``list_display_links`` declarado, o Django envolve a 1ª coluna num ``<a>`` para o change view. Quando a 1ª
        coluna é a dos ícones (que já são links), isso gera ``<a>`` aninhado: o navegador o parte num link vazio,
        que entra na ordem de tabulação sem nome acessível. Os ícones já levam ao visualizar/editar.
        """
        if not self.list_display_links and list_display and list_display[0] == 'show_list_display_icons':
            return None
        return super().get_list_display_links(request, list_display)

    def get_list_filter(self, request):
        """
        Retira do ``self.list_filter`` os itens presentes no ``self.list_filter_autocomplete``.
        """
        return self.list_filter

    def get_tabs(self, request):
        return []

    def get_view_inlines(self, request):
        return []

    def get_queryset(self, request, manager=None, *args, **kwargs):
        queryset = manager or super().get_queryset(request)
        if self.return_empty_queryset(request):
            return queryset.none()
        return queryset

    def get_current_queryset(self, request, *args, **kwargs):
        """
        Retorna o queryset exibido atualmente no changelist e é utilizado na
        ação ``export_to_csv``.
        """
        cl = super().get_changelist_instance(request)
        return cl.get_queryset(request)

    def get_changelist_instance(self, request):
        try:
            cl = super().get_changelist_instance(request)
        except IncorrectLookupParameters as erro:
            # O Django engole a exceção e responde "Database error"; só com o ``e`` na URL é bug de verdade (não filtro do usuário): vai ao Sentry.
            if _so_flag_de_erro(request):
                capture_exception(erro)
            raise
        cl.show_filter_required_message = self.return_empty_queryset(request)
        cl.empty_queryset_message = self.empty_queryset_message
        return cl

    def return_empty_queryset(self, request):
        requires_filter = self.model._meta.model_name in settings.ADMIN_FILTER_REQUIRED_MODELS
        if requires_filter:
            return not request.GET
        return False

    def get_search_results(self, request, queryset, search_term):
        """
        Returns a tuple containing a queryset to implement the search,
        and a boolean indicating if the results may contain duplicates.
        """

        # Apply keyword searches.
        def construct_search(field_name):
            if field_name.startswith('^'):
                return f'{field_name[1:]}__istartswith'
            elif field_name.startswith('='):
                return f'{field_name[1:]}__iexact'
            elif field_name.startswith('@'):
                return f'{field_name[1:]}__search'
            else:
                return f'{field_name}__icontains'

        use_distinct = False
        termos_busca, _termos_retirados = normalizar_termos_busca(search_term, self.avoid_short_search)
        search_terms = termos_busca.split()
        if search_terms:
            if self.max_terms_search and len(search_terms) > self.max_terms_search:
                search_terms = search_terms[0 : self.max_terms_search]
            search_fields = self.get_search_fields(request)
            if search_fields and search_term:
                orm_lookups = [construct_search(str(search_field)) for search_field in search_fields]
                for bit in search_terms:
                    or_queries = [models.Q(**{orm_lookup: bit}) for orm_lookup in orm_lookups]
                    queryset = queryset.filter(reduce(operator.or_, or_queries))
                if not use_distinct:
                    for search_spec in orm_lookups:
                        if lookup_spawns_duplicates(self.opts, search_spec):
                            use_distinct = True
                            break

        return queryset, use_distinct

    def has_view_permission(self, request, obj=None):
        return djtools.contrib.auth.helpers.has_view_permission(model=self.model, user=request.user)

    def has_change_permission(self, request, obj=None):
        if obj and hasattr(obj, 'can_change'):
            if not obj.can_change(request.user):
                return False
        perm = djtools.contrib.auth.helpers.has_change_permission(model=self.model, user=request.user)
        if not perm and obj is None:
            perm = self.has_view_permission(request, obj)
        return perm

    def has_delete_permission(self, request, obj=None):
        return djtools.contrib.auth.helpers.has_delete_permission(model=self.model, obj=obj, user=request.user)

    def get_action_bar(self, request: HttpRequest, remove_add_button: bool = False) -> list[dict]:
        items = []

        # Botão para adicionar
        if self.has_add_permission(request) and not remove_add_button:
            items.append({'url': 'add/', 'label': f'Adicionar {self.model._meta.verbose_name}', 'css_class': 'success'})

        # Botão para exportar para CSV
        if hasattr(self, 'export_to_csv'):
            items.append({'url': self._url_exportacao(request, 'export_to_csv'), 'label': 'Exportar para CSV'})

        if self.get_export_to_xls():
            items.append({'url': self._url_exportacao(request, 'export_to_xls'), 'label': 'Exportar para XLS'})

        # Botão para exportar para fixture
        if self.pode_exportar_fixture(request):
            items.append({'url': self._url_exportacao(request, 'export_to_fixture'), 'label': 'Exportar para Fixture'})

        return items

    @staticmethod
    def _url_exportacao(request: HttpRequest, parametro: str) -> str:
        """URL da listagem atual, com os filtros, acrescida de ``<parametro>=1``."""
        url = request.get_full_path()
        if '?' not in url:
            url = url + '?'
        if not url.endswith('?'):
            url = url + '&'
        return f'{url}{parametro}=1'

    def get_export_to_xls(self):
        return self.export_to_xls

    def pode_exportar_fixture(self, request: HttpRequest) -> bool:
        """O ``dumpdata`` exporta a tabela inteira, ignorando ``get_queryset`` e permissões: só superusuário, e só onde o admin declara."""
        # O stub do django tipa request.user como AbstractBaseUser | AnonymousUser; os dois concretos têm is_superuser.
        return request.user.is_superuser and hasattr(self, 'export_to_fixture')  # pyright: ignore[reportAttributeAccessIssue]

    @staticmethod
    def _pagina_database_error(request: HttpRequest, retorno: HttpResponse) -> HttpResponse:
        """Página "Database error" do Django (lookup inválido com ``?e=1`` já na URL), que vem como ``SimpleTemplateResponse``
        sem context processors e quebrava o ``base.html`` do SUAP sem ``theme`` (#17816).

        Com outros parâmetros na URL o culpado é o filtro: ``'.'`` volta à listagem sem parâmetros. Só com o ``e`` redirecionar entraria
        em loop (a listagem sem filtro falha de novo e o Django devolve ``?e=1``), então renderiza a página de erro, agora com request."""
        if not _so_flag_de_erro(request):
            return httprr('.', AVISO_FILTRO_INVALIDO, 'error')
        return TemplateResponse(request, retorno.template_name, retorno.context_data, status=retorno.status_code)  # pyright: ignore[reportAttributeAccessIssue]

    def _todos_filtros_ocultos(self) -> bool:
        try:
            return bool(
                self.list_filter
                and self.hidden_filters
                and len(self.list_filter) == len(self.hidden_filters)
                and self.list_filter[0] == self.hidden_filters[0]
            )
        except Exception:
            return False

    @csrf_protect_m
    def changelist_view(self, request: HttpRequest, extra_context: dict | None = None):
        self.request = request
        self.no_filters = self._todos_filtros_ocultos()

        # Help
        request.help_key = f'{self.model._meta.app_label}.change_{self.model.__name__.lower()}'

        # Chama a função de exportar para CSV
        if 'export_to_csv' in request.GET:
            request.GET._mutable = True
            del request.GET['export_to_csv']
            queryset = self.get_current_queryset(request)
            return tasks.admin_export('csv', queryset, request, self)
        # XLS
        if self.get_export_to_xls() and 'export_to_xls' in request.GET:
            request.GET._mutable = True
            del request.GET['export_to_xls']
            queryset = self.get_current_queryset(request)
            return tasks.admin_export('xls', queryset, request, self)
        # Fixture
        if 'export_to_fixture' in request.GET:
            request.GET._mutable = True
            del request.GET['export_to_fixture']
            # Sem permissão, o parâmetro é descartado e segue a listagem normal.
            if self.pode_exportar_fixture(request):
                param = f'{self.model._meta.app_label}.{self.model.__name__.lower()}'
                with io.StringIO() as out:
                    call_command('dumpdata', param, stdout=out)
                    response = HttpResponse(out.getvalue().encode(), content_type='application/json')
                    response['Content-Disposition'] = f'attachment; filename={param}.json'
                    return response

        more_context = {
            'object_tools_items': self.get_action_bar(request),
            'title': self.model._meta.verbose_name_plural,
            'disable_general_tabs': True,
        }
        more_context.update(extra_context or {})
        utils.breadcrumbs_add(request, more_context)
        try:
            retorno = super().changelist_view(request, more_context)
        except SuspiciousOperation:
            return httprr('.', AVISO_FILTRO_INVALIDO, 'error')
        if getattr(retorno, 'template_name', None) == 'admin/invalid_setup.html':
            return self._pagina_database_error(request, retorno)
        if is_ajax(request) and hasattr(retorno, 'context_data'):
            return utils.render(self.content_main_admin_template, retorno.context_data)
        return retorno

    def get_fieldsets(self, request, obj=None):
        if not obj and self.add_fieldsets:
            return self.add_fieldsets
        return super().get_fieldsets(request, obj)

    def get_form(self, request, obj=None, **kwargs):
        """
        Torna o ``request`` disponível no ``FormClass``.
        """
        defaults = {}

        if obj is None and self.add_form:
            defaults['form'] = self.add_form

        if obj and self.change_form:
            defaults['form'] = self.change_form

        defaults.update(kwargs)

        FormClass = super().get_form(request, obj, **defaults)

        FormClass.request = request
        return FormClass

    def render_change_form(self, request, context, **kwargs):
        form = context['adminform'].form
        for k in form.fields:
            if hasattr(form.fields[k], 'reload'):
                form.fields[k].reload()
        return super().render_change_form(request, context, **kwargs)

    @csrf_protect_m
    @transaction.atomic
    def add_view(self, request, form_url='', extra_context=None):
        request.help_key = f'{self.model._meta.app_label}.add_{self.model.__name__.lower()}'
        more_context = {'title': f'Adicionar {self.model._meta.verbose_name}'}
        more_context.update(extra_context or {})
        utils.breadcrumbs_add(request, more_context)
        return super().add_view(request, form_url, more_context)

    @csrf_protect_m
    @transaction.atomic
    def change_view(self, request, object_id, form_url='', extra_context=None):
        obj = self.get_object(request, unquote(object_id))
        if obj is None:
            return self._get_obj_does_not_exist_redirect(request, self.model._meta, object_id)

        if not self.has_change_permission(request, obj):
            raise PermissionDenied

        readonly = False
        if extra_context:
            readonly = extra_context.get('readonly', False)
        request.help_key = f'{self.model._meta.app_label}.add_{self.model.__name__.lower()}'
        if not readonly:
            more_context = {'title': f'Editar {obj!s}'}
        else:
            more_context = {'title': f'Visualizar {obj!s}'}
        utils.breadcrumbs_add(request, more_context)
        more_context.update(extra_context or {})
        return super().change_view(request, object_id, form_url, more_context)

    @csrf_protect_m
    @transaction.atomic
    def delete_view(self, request, object_id, extra_context=None):
        form = ConfirmacaoExclusaoForm(request.POST or None, request=request)
        form.fields['senha'].reload()
        extra_context = {'title': f'Remover {self.model._meta.verbose_name}', 'form': form}
        utils.breadcrumbs_add(request, extra_context)
        if request.POST:
            if not form.is_valid():
                return httprr('.', 'Erro ao confirmar identidade.', 'error')
        return super().delete_view(request, object_id, extra_context)

    def response_delete(self, request, obj_display, obj_id):
        """
        Determine the HttpResponse for the delete_view stage.
        """
        opts = self.model._meta
        msg = f'{opts.verbose_name} "{obj_display}": excluído com sucesso.'

        self.message_user(
            request,
            msg,
            messages.SUCCESS,
        )

        if self.has_change_permission(request, None):
            post_url = reverse(
                f'admin:{opts.app_label}_{opts.model_name}_changelist',
                current_app=self.admin_site.name,
            )
            preserved_filters = self.get_preserved_filters(request)
            post_url = add_preserved_filters({'preserved_filters': preserved_filters, 'opts': opts}, post_url)
        else:
            post_url = reverse('admin:index', current_app=self.admin_site.name)
        return HttpResponseRedirect(post_url)

    def response_change(self, request, obj):
        if '_continue' in request.POST or '_addanother' in request.POST:
            return super().response_change(request, obj)
        elif 'fancybox' in request.GET or '_popup' in request.POST:
            self.message_user(
                request,
                'Atualização realizada com sucesso.',
                messages.SUCCESS,
            )
            return HttpResponse('<script>parent.close_fancybox();</script>')
        else:
            self.message_user(
                request,
                'Atualização realizada com sucesso.',
                messages.SUCCESS,
            )
            if hasattr(obj, 'get_absolute_url'):
                url = obj.get_absolute_url()
            elif self.has_change_permission(request, None):
                opts = self.model._meta
                url = reverse(
                    f'admin:{opts.app_label}_{opts.model_name}_changelist',
                    current_app=self.admin_site.name,
                )
            else:
                url = utils.breadcrumbs_previous_url(request=request)
            return HttpResponseRedirect(url)

    def response_add(self, request, obj, post_url_continue=None):
        msg = 'Cadastro realizado com sucesso.'
        if hasattr(obj, 'get_absolute_url'):
            url = obj.get_absolute_url()
        elif self.has_change_permission(request, None):
            opts = self.model._meta
            url = reverse(
                f'admin:{opts.app_label}_{opts.model_name}_changelist',
                current_app=self.admin_site.name,
            )
        else:
            url = utils.breadcrumbs_previous_url(request=request)
        if '_continue' in request.POST or '_addanother' in request.POST:
            return super().response_add(request, obj)
        elif 'fancybox' in request.GET or '_popup' in request.POST:
            self.message_user(
                request,
                msg,
                messages.SUCCESS,
            )
            return HttpResponse('<script>parent.close_fancybox();</script>')
        else:
            self.message_user(
                request,
                msg,
                messages.SUCCESS,
            )
            return HttpResponseRedirect(url)

    def get_urls(self) -> list[URLPattern]:
        new_urls = [path('<str:obj_pk>/view/', self.admin_site.admin_view(self.render_view_object))]

        return new_urls + super().get_urls()

    def get_view_obj_items(self, obj, safe=None):
        is_safe = safe

        def _get_fieldsets(self):
            if self.fieldsets:
                return self.fieldsets
            else:
                fields = [f.name for f in obj.__class__._meta.fields if f.name != 'id']
                return (('', {'fields': (fields,)}),)

        fieldsets = _get_fieldsets(self)
        max_fields_by_row = 1
        for _fieldset_name, fieldset_dict in fieldsets:
            for item in fieldset_dict['fields']:
                if isinstance(item, str):
                    continue
                if len(item) > max_fields_by_row:
                    max_fields_by_row = len(item)

        items = []
        for fieldset_name, fieldset_dict in fieldsets:
            item_dict = {'fieldset': fieldset_name, 'rows': []}
            for fieldset_fields_item in fieldset_dict['fields']:
                if isinstance(fieldset_fields_item, str):
                    fieldset_fields_item = [fieldset_fields_item]
                fields = []
                for field_name in fieldset_fields_item:
                    last_field_in_row = field_name == fieldset_fields_item[-1]  # type: ignore[index]
                    if last_field_in_row:
                        colspan = (max_fields_by_row - len(fieldset_fields_item)) * 2 + 1
                    else:
                        colspan = 1
                    try:
                        model_field = self.model._meta.get_field(field_name)
                        if hasattr(obj, f'get_{field_name}_display'):
                            valor = getattr(obj, f'get_{field_name}_display')
                        elif type(model_field) in [ManyToManyField, ManyToManyFieldPlus]:
                            valor = getattr(obj, field_name).all()
                            is_safe = True
                        elif getattr(model_field, 'name', '') in ['senha', 'password']:
                            valor = '****'
                            is_safe = False
                        else:
                            valor = getattr(obj, field_name)
                            is_safe = False

                        field_dict = {'label': model_field.verbose_name, 'value': valor, 'colspan': colspan, 'is_safe': is_safe}
                        fields.append(field_dict)
                    except Exception:
                        pass
                item_dict['rows'].append(fields)
            items.append(item_dict)
        return items

    def get_action_bar_view(self, request, obj):
        return []

    def _get_first_object(self, request, obj_pk):
        try:
            obj_pk = int(obj_pk)
        except TypeError, ValueError:
            return None
        return self.get_queryset(request).filter(pk=obj_pk).first()

    def render_view_object(self, request, obj_pk):
        safe = hasattr(self, 'safe_view') and self.safe_view or False
        obj = self._get_first_object(request, obj_pk)
        if not obj:
            raise Http404
        if not self.has_view_permission(request, obj):
            raise PermissionDenied

        title = str(obj)
        obj_items = self.get_view_obj_items(obj, safe)
        object_tools_items = self.get_action_bar_view(request, obj)

        inlines = {}
        for func_name in self.get_view_inlines(request):
            func = getattr(self, func_name)
            columns = getattr(func, 'columns', ['__str__'])
            inline_items = []
            items_safe = []
            objects = func(obj)
            if not objects:
                continue
            for model_obj in objects:
                model_cls = model_obj.__class__
                values = []
                for col in columns:
                    values.append(eval_attr(model_obj, col))
                inline_items.append(values)

            columns_verbose_names = []
            for col in columns:
                if col == '__str__':
                    verbose_name = model_cls._meta.verbose_name
                else:
                    verbose_name = model_cls._meta.get_field(col).verbose_name
                columns_verbose_names.append(verbose_name)

            inlines[getattr(func, 'short_description', func_name)] = {
                'columns': columns_verbose_names,
                'items': inline_items,
                'items_safe': items_safe,
            }

        return utils.render('djtools/templates/adminutils/render_view_object.html', locals())

    def get_all_tabs(self, request):
        tabs = self.get_tabs(request)

        if self.show_tab_any_data and 'tab_any_data' not in tabs:
            tabs = ['tab_any_data', *tabs]

        return tabs

    def tab_any_data(self, request, queryset):
        return queryset

    tab_any_data.short_description = 'Todos'

    def get_object(self, request, object_id, from_field=None):
        # No SUAP só é utilizado id inteiro
        try:
            int(object_id)
        except Exception:
            return None
        return super().get_object(request, object_id, from_field)

    def history_view(self, request, object_id, extra_context=None):
        if not extra_context:
            extra_context = {}
        extra_context['is_popup'] = request.GET.get('_popup')
        return super().history_view(request, object_id, extra_context=extra_context)

    @display(description=mark_safe('<input type="checkbox" id="action-toggle">'))
    def action_checkbox(self, obj):
        if self.has_action_permission(self.request, obj):
            return super().action_checkbox(obj)
        return ''

    def has_action_permission(self, request, obj=None):
        return True


class CompareVersionAdminPlus(CompareVersionAdmin):
    def compare(self, obj, version1, version2):
        diff, has_unfollowed_fields = super().compare(obj, version1, version2)
        if hasattr(self, 'list_display_compare'):
            displayed_diff = []
            for diff_field in diff:
                if diff_field['field'].name in self.list_display_compare:
                    displayed_diff.append(diff_field)

            diff = displayed_diff
        return diff, has_unfollowed_fields


class ReadOnlyAdmin(ModelAdminPlus):
    """ """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.user_readonly_inlines = {}

    def get_readonly_fields(self, request, obj=None):
        if self.user_is_readonly(request):
            return list(self.readonly_fields) + [field.name for field in obj._meta.fields]
        return super(ModelAdminPlus, self).get_readonly_fields(request, obj)

    def has_add_permission(self, request, obj=None):
        if not self.user_is_readonly(request):
            return super().has_add_permission(request)
        return False

    def has_delete_permission(self, request, obj=None):
        if not self.user_is_readonly(request):
            return super().has_delete_permission(request)
        return False

    def get_actions(self, request):
        actions = super().get_actions(request)
        if self.user_is_readonly(request):
            if 'delete_selected' in actions:
                del actions['delete_selected']
        return actions

    def change_view(self, request, object_id, extra_context=None):
        extra_context = extra_context or {}
        if not request.user.is_superuser and self.user_is_readonly(request):
            request.readonly = True
            extra_context.update(
                {
                    # set a context var telling our customized template to suppress the Save button group
                    'readonly': True
                }
            )
        try:
            return super().change_view(request, object_id, extra_context=extra_context)
        except PermissionDenied:
            pass
        #
        if request.method == 'POST':
            raise PermissionDenied
        #
        return super().change_view(request, object_id, extra_context=extra_context)

    def view_object_icon(self, obj):
        """
        Templatetag para incluir ícone de visualização do obj, já testando se o usuário
        autenticado tem permissões para isso.
        """
        from djtools.contrib.admin.helpers import get_admin_object_url

        return format_html(
            '<a class="icon icon-view" href="{}" title="{}"><span class="visually-hidden">Visualizar</span></a>',
            get_admin_object_url(obj),
            f'Ver {obj!s}',
        )

    def show_list_display_icons(self, obj):
        if self.user_is_readonly(self.request):
            return self.view_object_icon(obj)
        else:
            return super().show_list_display_icons(obj)

    show_list_display_icons.allow_tags = True
    show_list_display_icons.short_description = '#'

    def user_is_readonly(self, request):
        groups = [x.name for x in request.user.groups.all()]
        return 'readonly' in groups


class NonrelatedInlineModelAdminChecks(InlineModelAdminChecks):
    """
    Check used by the admin system to determine whether or not an inline model
    has a relationship to the parent object.
    In this case we always want this check to pass.
    """

    def _check_exclude_of_parent_model(self, obj, parent_model):
        return []

    def _check_relation(self, obj, parent_model):
        return []


class NonrelatedStackedInline(admin.StackedInline):
    """
    Stacked inline base class for models not explicitly related to the inline
    model.
    """

    checks_class = NonrelatedInlineModelAdminChecks
    formset = NonrelatedInlineFormSet

    def get_form_queryset(self, obj):
        raise NotImplementedError

    def save_new_instance(self, parent, instance):
        raise NotImplementedError

    def save_formset(self, request, form, formset, change):
        instances = formset.save(commit=False)
        for instance in instances:
            self.update_instance(formset.instance, instance)
            instance.save()
        formset.save_m2m()

    def get_formset(self, request, obj=None, **kwargs):
        if 'fields' in kwargs:
            fields = kwargs.pop('fields')
        else:
            fields = flatten_fieldsets(self.get_fieldsets(request, obj))

        exclude = [*(self.exclude or []), *self.get_readonly_fields(request, obj)]
        if self.exclude is None and hasattr(self.form, '_meta') and self.form._meta.exclude:  # type: ignore[assignment]
            exclude.extend(self.form._meta.exclude)  # type: ignore[union-attr]
        exclude = exclude or None

        can_delete = self.can_delete and self.has_delete_permission(request, obj)

        queryset = self.model.objects.none()
        if obj:
            queryset = self.get_form_queryset(obj)

        defaults = {
            'form': self.form,
            'formfield_callback': partial(self.formfield_for_dbfield, request=request),
            'formset': self.formset,
            'extra': self.get_extra(request, obj),
            'can_delete': can_delete,
            'can_order': False,
            'fields': fields,
            'min_num': self.get_min_num(request, obj),
            'max_num': self.get_max_num(request, obj),
            'exclude': exclude,
            'queryset': queryset,
            **kwargs,
        }

        if defaults['fields'] is None and not modelform_defines_fields(defaults['form']):
            defaults['fields'] = ALL_FIELDS

        return nonrelated_inlineformset_factory(self.model, save_new_instance=self.save_new_instance, **defaults)


class ReverseInlineFormSet(BaseModelFormSet):
    """
    A formset with either a single object or a single empty
    form. Since the formset is used to render a required OneToOne
    relation, the forms must not be empty.
    """

    parent_fk_name = ''

    def __init__(self, data=None, files=None, instance=None, prefix=None, queryset=None, save_as_new=False):
        object = getattr(instance, self.parent_fk_name, None)
        #
        if object:
            qs = self.model.objects.filter(pk=object.pk)
        else:
            qs = self.model.objects.none()
            self.extra = 1
        #
        super().__init__(data, files, prefix=prefix, queryset=qs)
        for form in self.forms:
            form.empty_permitted = False


def _get_parent_fk_field(obj, formset):
    return next((f for f in obj._meta.fields if f.name == formset.parent_fk_name), None)


def _remove_blank_reverse_inlines(obj, formset_inline_tuples):
    """
    Hacky implementation, but for some reasons blank inlines are being treated
    as invalid. So, let's remove them from validation, since we know that they are
    actually valid.
    """

    def to_filter(formset):
        if not isinstance(formset, ReverseInlineFormSet):
            return True
        field = _get_parent_fk_field(obj, formset)
        return not (field.blank and not formset.has_changed())

    return list(filter(lambda t: to_filter(t[0]), formset_inline_tuples))


def reverse_inlineformset_factory(model, parent_fk_name, form=ModelFormPlus, fields=None, exclude=None, formfield_callback=lambda f: f.formfield()):
    if fields is None and exclude is None:
        related_fields = [
            f for f in model._meta.get_fields() if (f.one_to_many or f.one_to_one or f.many_to_many) and f.auto_created and not f.concrete
        ]
        fields = [f.name for f in model._meta.get_fields() if f not in related_fields]  # ignoring reverse relations
    #
    kwargs = {
        'form': form,
        'formfield_callback': formfield_callback,
        'formset': ReverseInlineFormSet,
        'extra': 0,
        'can_delete': True,
        'can_order': False,
        'fields': fields,
        'exclude': exclude,
        'max_num': 1,
    }
    FormSet = modelformset_factory(model, **kwargs)
    FormSet.parent_fk_name = parent_fk_name
    return FormSet


class ReverseInlineModelAdmin(InlineModelAdmin):
    """
    Use the name and the help_text of the owning models field to
    render the verbose_name and verbose_name_plural texts.
    """

    def __init__(self, parent_model, parent_fk_name, model, admin_site, inline_type):
        self.template = f'admin/edit_inline/{inline_type}.html'
        self.parent_fk_name = parent_fk_name
        self.model = model
        field_descriptor = getattr(parent_model, self.parent_fk_name)
        field = field_descriptor.field
        #
        self.verbose_name_plural = field.verbose_name.title()
        self.verbose_name = field.help_text
        if not self.verbose_name:
            self.verbose_name = self.verbose_name_plural
        #
        super().__init__(parent_model, admin_site)

    def get_formset(self, request, obj=None, **kwargs):
        if 'fields' in kwargs:
            fields = kwargs.pop('fields')
        elif self.get_fieldsets(request, obj):
            fields = flatten_fieldsets(self.get_fieldsets(request, obj))
        else:
            fields = None

        # want to combine exclude arguments - can't do that if they're None
        # also, exclude starts as a tuple - need to make it a list
        non_editable_fields = [f for f in self.model._meta.fields if not f.editable]
        exclude = list(kwargs.get('exclude', []))
        exclude.extend(self.get_readonly_fields(request, obj))
        exclude_2 = self.exclude or []
        exclude.extend(list(exclude_2))
        exclude.extend(non_editable_fields)
        # but need exclude to be None if result is an empty list
        exclude = exclude or None

        defaults = {
            'form': self.form,
            'fields': fields,
            'exclude': exclude,
            'formfield_callback': partial(self.formfield_for_dbfield, request=request),
        }
        kwargs.update(defaults)
        return reverse_inlineformset_factory(self.model, self.parent_fk_name, **kwargs)


class ReverseModelAdminPlus(ModelAdminPlus):
    """
    Patched ModelAdmin class. The add_view method is overridden to
    allow the reverse inline formsets to be saved before the parent
    model.
    """

    def __init__(self, model, admin_site):
        #
        super().__init__(model, admin_site)
        self.exclude = list(self.exclude or [])
        inline_instances = []
        for field_name in self.inline_reverse:
            #
            kwargs = {}
            admin_class = None
            #
            if isinstance(field_name, tuple):
                kwargs = field_name[1]
                field_name = field_name[0]
            elif isinstance(field_name, dict):
                kwargs = field_name.get('kwargs', kwargs)
                admin_class = field_name.get('admin_class', admin_class)
                field_name = field_name['field_name']
            #
            field = model._meta.get_field(field_name)
            if isinstance(field, models.OneToOneField | models.ForeignKey):
                if admin_class:
                    admin_class_to_use = type(
                        str(f'DynamicReverseInlineModelAdmin_{admin_class.__name__}'),
                        (admin_class, ReverseInlineModelAdmin),
                        {},
                    )
                else:
                    admin_class_to_use = ReverseInlineModelAdmin
                #
                name = field.name
                parent = field.remote_field.model
                inline = admin_class_to_use(model, name, parent, admin_site, self.inline_type)
                if kwargs:
                    inline.__dict__.update(kwargs)
                inline_instances.append(inline)
                self.exclude.append(name)
        # These are the inline reverse instances for ReverseModelAdmin
        self.tmp_inline_instances = inline_instances

    def get_inline_instances(self, request, obj=None):
        own = list(
            filter(
                lambda inline: (
                    inline.has_view_or_change_permission(request, obj)
                    or inline.has_add_permission(request, obj)
                    or inline.has_delete_permission(request, obj)
                ),
                self.tmp_inline_instances,
            )
        )
        return own + super().get_inline_instances(request, obj)

    def change_view(self, request, object_id, form_url='', extra_context=None):
        return self._changeform_view(request, object_id, form_url, extra_context)

    def add_view(self, request, form_url='', extra_context=None):
        return self._changeform_view(request, None, form_url, extra_context)

    def _save_object(self, request, new_object, form, formsets, add):
        self.save_model(request, new_object, form, change=not add)
        self.save_related(request, form, formsets, change=not add)
        form.save_m2m()
        change_message = self.construct_change_message(request, form, formsets, add)
        if add:
            self.log_addition(request, new_object, change_message)
        else:
            self.log_change(request, new_object, change_message)

    def _changeform_view(self, request, object_id, form_url, extra_context):
        add = object_id is None
        #
        model = self.model
        opts = model._meta
        #
        if add:
            if not self.has_add_permission(request):
                raise PermissionDenied
            obj = None

        else:
            obj = self.get_object(request, unquote(object_id))

            if request.method == 'POST':
                if not self.has_change_permission(request, obj):
                    raise PermissionDenied
            else:
                if not self.has_view_or_change_permission(request, obj):
                    raise PermissionDenied

            if obj is None:
                return self._get_obj_does_not_exist_redirect(request, opts, object_id)

        formsets = []
        model_form = self.get_form(request, obj=obj, change=not add)
        if request.method == 'POST':
            form = model_form(request.POST, request.FILES, instance=obj)
            form_validated = form.is_valid()
            #
            if form_validated:
                new_object = self.save_form(request, form, change=not add)
            else:
                new_object = form.instance
            formsets, _inline_instances = self._create_formsets(request, new_object, change=not add)
            formset_inline_tuples = zip(formsets, self.get_inline_instances(request), strict=False)
            formset_inline_tuples = _remove_blank_reverse_inlines(new_object, formset_inline_tuples)
            formsets = [t[0] for t in formset_inline_tuples]
            #
            if form_validated and not formsets:
                self._save_object(request, new_object, form, formsets, add)
                return self.response_add(request, new_object)
            elif form_validated and all_valid(formsets):
                # Here is the modified code.
                for formset, inline in formset_inline_tuples:
                    if not isinstance(inline, ReverseInlineModelAdmin):
                        continue
                    # The idea or this piece is coming from:
                    #  https://stackoverflow.com/questions/50910152/inline-formset-returns-empty-list-on-save.
                    # Without this, formset.save() was returning None for forms that
                    # haven't been modified
                    forms = list(formset)
                    if not forms:
                        continue
                    obj = forms[0].save()
                    setattr(new_object, inline.parent_fk_name, obj)
                #
                self._save_object(request, new_object, form, formsets, add)
                for formset in formsets:
                    self.save_formset(request, form, formset, change=not add)

                # self.log_addition(request, new_object)
                return self.response_add(request, new_object)
        else:
            # Prepare the dict of initial data from the request.
            # We have to special-case M2Ms as a list of comma-separated PKs.
            initial = dict(request.GET.items())
            for k, v in initial.items():
                try:
                    f = opts.get_field(k)
                except FieldDoesNotExist:
                    continue
                if isinstance(f, models.ManyToManyField):
                    initial[k] = v.split(',')
            if add:
                form = model_form(initial=initial)
                prefixes = {}
                for FormSet, _inline in self.get_formsets_with_inlines(request):
                    prefix = FormSet.get_default_prefix()
                    prefixes[prefix] = prefixes.get(prefix, 0) + 1

                    if prefixes[prefix] != 1:
                        prefix = f'{prefix}-{prefixes[prefix]}'
                    #
                    formset = FormSet(instance=self.model(), prefix=prefix)
                    formsets.append(formset)
            else:
                form = model_form(instance=obj)
                formsets, _inline_instances = self._create_formsets(request, obj, change=True)

        if not add and not self.has_change_permission(request, obj):
            readonly_fields = flatten_fieldsets(self.get_fieldsets(request, obj))
        else:
            readonly_fields = self.get_readonly_fields(request, obj)

        adminForm = helpers.AdminForm(
            form, list(self.get_fieldsets(request)), self.prepopulated_fields, readonly_fields=readonly_fields, model_admin=self
        )
        media = self.media + adminForm.media
        inline_admin_formsets = self.get_inline_formsets(request, formsets, self.get_inline_instances(request), obj)

        for inline_formset in inline_admin_formsets:
            media = media + inline_formset.media

        # Inherit the default context from admin_site
        context = self.admin_site.each_context(request)
        reverse_admin_context = {
            'title': _(('Change %s', 'Add %s')[add]) % force_str(opts.verbose_name),
            'adminform': adminForm,
            'is_popup': False,
            'object_id': object_id,
            'original': obj,
            'media': mark_safe(media),
            'inline_admin_formsets': inline_admin_formsets,
            'errors': helpers.AdminErrorList(form, formsets),
            'app_label': opts.app_label,
        }
        context.update(reverse_admin_context)
        context.update(extra_context or {})
        return self.render_change_form(request, context, form_url=form_url, add=add, change=not add, obj=obj)
