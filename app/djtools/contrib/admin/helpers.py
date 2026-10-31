from __future__ import annotations

from collections.abc import Iterator
from typing import TYPE_CHECKING

from django.apps import apps
from django.contrib import admin
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from djtools import forms

if TYPE_CHECKING:
    from django.contrib.admin.filters import _ListFilterChoices
    from django.contrib.admin.views.main import ChangeList
    from django.db.models import QuerySet
    from django.http import HttpRequest

    class _EscolhaDeSetor(_ListFilterChoices, total=False):
        campus: str


ACTION_CHECKBOX_NAME = '_selected_action'


class ActionForm(forms.Form):
    action = forms.ChoiceField(label=_('Action:'), required=False)
    select_across = forms.BooleanField(
        label='',
        required=False,
        initial=0,
        widget=forms.HiddenInput({'class': 'select-across'}),
    )

    def clean_action(self):
        action = self.data['action']
        if not action:
            raise ValidationError('Por favor escolha alguma ação.')
        return self.data['action']


class ConfirmacaoExclusaoForm(forms.FormPlus):
    senha = forms.PasswordField()


def get_admin_model_url(model, sufix=None):
    """
    Obtem a **URL** de acesso a um admin baseando-se no modelo passado.

    Args:
        model (Model): modelo base bara gerar a **URL**;
        sufix (bool): indica se deve-se colocar '/' ao final da **URL**.

    Returns:
        String com a **URL** de acesso ao admin do modelo.
    """
    assert sufix in [None, 'add']
    base_url = '/admin/%(app)s/%(model)s/'
    if sufix:
        base_url += sufix + '/'
    params = {'app': model._meta.app_label, 'model': model._meta.model_name}
    return base_url % params


def get_admin_object_url(obj):
    """
    Obtem a **URL** de acesso edição do objeto pelo admin.

    Args:
        obj (Model): objeto base para edição.

    Returns:
        A **URL** para edição do objeto no admin.
    """
    base_url = get_admin_model_url(obj.__class__)
    return base_url + str(obj.pk) + '/change/'


def get_admin_view_object_url(obj):
    """
    Obtem a **URL** de acesso visualização do objeto pelo admin.

    Args:
        obj (Model): objeto base para visualização.

    Returns:
        A **URL** para visualização do objeto no admin.
    """
    model = obj.__class__

    base_url = f'/admin/{model._meta.app_label}/{model._meta.model_name}/{obj.pk!s}/view/'

    return base_url


def get_djtools_delete_object_url(obj):
    """
    Obtem a **URL** de exclusão do objeto pelo *DJTools*.

    Args:
        obj (Model): objeto base para exclusão.

    Returns:
        A **URL** para exclusão do objeto pelo *DJTools*.
    """
    model_cls = obj.__class__
    return f'/djtools/delete_object/{model_cls._meta.app_label}/{model_cls._meta.model_name}/{obj.pk}/'


class SetorPorCampusFilter(admin.SimpleListFilter):
    """Filtro de setor que depende do filtro de campus ``parametro_campus`` (ver ``get_uo_setor_listfilter``).

    Lista os setores de todos os campi, cada um com o id do seu campus; ``admin/filter_setor_por_campus.html`` mostra só os do
    campus escolhido. O recorte é feito no navegador, e não aqui: ao trocar ou limpar o campus, a lista de
    setores acompanha na hora, sem esperar um novo "Filtrar" (#16372).
    """

    template = 'admin/filter_setor_por_campus.html'
    parametro_campus: str
    setores: QuerySet

    @property
    def is_setor_inativo_exibido(self) -> bool:
        return apps.get_model('comum', 'Configuracao').get_valor_por_chave('processo_eletronico', 'exibir_setor_inativo_no_filtro')

    def lookups(self, request: HttpRequest, model_admin: admin.ModelAdmin) -> list[tuple[str, str]]:
        setores = self.setores.all() if self.is_setor_inativo_exibido else self.setores.filter(excluido=False)
        self.campus_por_setor: dict[str, str] = {}
        opcoes = []
        for pk, sigla, uo_id in setores.values_list('id', 'sigla', 'uo_id'):
            self.campus_por_setor[str(pk)] = str(uo_id or '')
            opcoes.append((str(pk), sigla))
        return opcoes

    def choices(self, changelist: ChangeList) -> Iterator[_ListFilterChoices]:
        """As opções do Django, cada setor com o id do seu campus (``campus``), lido pelo template."""
        escolhas = super().choices(changelist)
        yield next(escolhas)  # "Todos"
        for (pk, _sigla), escolha in zip(self.lookup_choices, escolhas, strict=True):
            escolha_de_setor: _EscolhaDeSetor = {**escolha, 'campus': self.campus_por_setor[pk]}
            yield escolha_de_setor

    def queryset(self, request: HttpRequest, queryset: QuerySet) -> QuerySet:
        """Filtra pelo setor escolhido; setor inexistente ou fora do campus escolhido é descartado."""
        if self.value():
            try:
                setor = self.setores.filter(pk=self.value())
                if request.GET.get(self.parametro_campus):
                    setor = setor.filter(uo__pk=request.GET.get(self.parametro_campus))
            except Exception:
                setor = self.setores.none()
            if setor.exists():
                return queryset.filter(**{f'{self.parameter_name}__id__exact': self.value()})
            self.used_parameters.pop(str(self.parameter_name))
        return queryset


def get_uo_setor_listfilter(parametro_setor='setor', title_setor='setor', title_uo='campus', setor_suap=True):
    """
    Obtem filtros, para admin, de setor e unidade organizacional com base no setor passado.

    Args:
        parametro_setor (int): id do setor base para criação dos filtros;
        title_setor (string): título para o filtro de setor;
        title_uo (string): título para o filtro de unidade organizacional;
        setor_suap (bool): indica se é para utilizar a árvore de setores do SUAP.

    Returns:
        Tupla contendo as classes para filtro de setor e unidade organizacional.s
    """
    UnidadeOrganizacional = apps.get_model('rh', 'UnidadeOrganizacional')
    Setor = apps.get_model('rh', 'Setor')
    parametro_uo = f'{parametro_setor!s}uo'

    qs_filter_uo = f'{parametro_setor!s}__uo__id__exact'

    queryset_manager_setor = Setor.objects.suap()
    if not setor_suap:
        queryset_manager_setor = Setor.objects.siape()

    queryset_manager_uo = UnidadeOrganizacional.objects.suap()
    if not setor_suap:
        queryset_manager_uo = UnidadeOrganizacional.objects.siape()

    class SetorFilter(SetorPorCampusFilter):
        title = str(title_setor.capitalize())
        parameter_name = str(parametro_setor)
        parametro_campus = parametro_uo
        setores = queryset_manager_setor

    class UoFilter(admin.SimpleListFilter):
        title = str(title_uo.capitalize())
        parameter_name = str(parametro_uo)

        def lookups(self, request, model_admin):
            return queryset_manager_uo.all().values_list('id', 'sigla')

        def queryset(self, request, queryset):
            if self.value():
                try:
                    uo = queryset_manager_uo.filter(pk=request.GET.get(parametro_uo))
                except Exception:
                    uo = queryset_manager_uo.none()
                if uo.exists():
                    return queryset.filter(**{qs_filter_uo: self.value()})
                else:
                    self.used_parameters.pop(self.parameter_name)
            return queryset

    return (UoFilter, SetorFilter)
