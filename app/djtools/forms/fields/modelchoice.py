from itertools import chain

from django import forms
from django.forms.models import ModelChoiceField, ModelMultipleChoiceField
from django.template import Context, Template
from django.utils.choices import normalize_choices
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _

from djtools.forms.utils.foreign_key import ModelChoiceIteratorPlus
from djtools.forms.widgets import (
    AutocompleteWidget,
    ChainedSelectWidget,
    CheckboxSelectMultiplePlus,
    SelectMultiplePopup,
    SelectPopup,
)


class ModelChoiceFieldPlus(ModelChoiceField):
    widget = AutocompleteWidget  # Certifique-se de que AutocompleteWidget esteja importado/definido

    def __init__(self, queryset, extra_choices=None, *args, **kwargs):
        self.extra_choices = extra_choices or []
        # # Garante que 'to_field_name' esteja definido (mesmo que seja None)
        self.to_field_name = kwargs.get('to_field_name')
        kwargs.setdefault('to_field_name', kwargs.get('to_field_name'))
        super().__init__(queryset, *args, **kwargs)

    def _get_choices(self):
        # Usa chain para concatenar as extra_choices com as escolhas do queryset de forma lazy.
        if self.extra_choices:
            return chain(self.extra_choices, super()._get_choices())
        return super()._get_choices()

    choices = property(_get_choices, ModelChoiceField.choices.fset)

    def to_python(self, value):
        if self.valid_extra_choices_value(value):
            return value
        return super().to_python(value)

    def valid_extra_choices_value(self, value):
        return any(str(extra_choice[0]) == str(value) for extra_choice in self.extra_choices)


class MultipleModelChoiceField(forms.ModelMultipleChoiceField):
    widget = CheckboxSelectMultiplePlus

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.help_text = ''


class MultipleModelChoiceFieldPlus(forms.ModelMultipleChoiceField):
    def __init__(self, *args, **kwargs):
        # Retira o texto `msg` do `help_text`, já que não faz sentido e confunde o usuário, pois o
        # widget é autocomplete e não precisa segurar as teclas control ou command.
        if 'help_text' in kwargs:
            msg = str(_('Hold down "Control", or "Command" on a Mac, to select more than one.'))
            kwargs['help_text'] = str(kwargs['help_text']).replace(msg, '')
        if 'widget' not in kwargs:
            kwargs['widget'] = AutocompleteWidget(multiple=True)
        super().__init__(*args, **kwargs)

    def clean(self, value):
        # verificando se algum objeto escolhido não consta mais nas opções válidas (queryset)
        pks = [pk for pk in value if pk] if value else []
        try:
            for pk in self.queryset.filter(pk__in=pks).values_list('pk', flat=True) if pks else []:
                pks.remove(str(pk)) if str(pk) in pks else None
        except ValueError:
            raise forms.ValidationError('Escolha(s) inválida(s), escolha outros valores e tente novamente.')
        if pks:  # alguma pk não consta no queryset relacionado ao campo e, portanto, é inválida
            raise forms.ValidationError(
                'Escolha(s) inválida(s): {}'.format(', '.join(str(o) for o in self.queryset.model.objects.filter(pk__in=pks)))
            )
        return super().clean(value)


class ModelChoiceFieldPlus2(forms.ModelChoiceField):
    """
    Uma versão do forms.ModelChoiceField com 2 novas funcionalidades:

    1) Definição do label_template, que é útil quando se quer mostrar algo diferente
       do tradicional ``unicode``.
       USO: campo = ModelChoiceFieldPlus2(queryset=User.objects.all(), label_template='{{obj.first_name}}')
    2) Definição do group_by, que é útil para montar optgroups baseado num atributo
       dos objetos do queryset
    """

    def __init__(
        self,
        queryset,
        *args,
        empty_label='---------',
        required=True,
        widget=None,
        label=None,
        initial=None,
        help_text=None,
        to_field_name=None,
        **kwargs,
    ):
        self.label_template = kwargs.pop('label_template', None)
        self.group_by = kwargs.pop('group_by', None)
        super().__init__(
            queryset,
            *args,
            empty_label=empty_label,
            required=required,
            widget=widget,
            label=label,
            initial=initial,
            help_text=help_text,
            to_field_name=to_field_name,
            **kwargs,
        )

    def _get_choices(self):
        if self.group_by:
            return ModelChoiceIteratorPlus(self)
        else:
            return super()._get_choices()

    def _set_choices(self, value):
        self._choices = self.widget.choices = normalize_choices(value)

    choices = property(_get_choices, _set_choices)

    def label_from_instance(self, obj):
        if not self.label_template:
            return super().label_from_instance(obj)
        t = Template(self.label_template)
        return mark_safe(t.render(Context({'obj': obj})))


class ChainedModelChoiceField(forms.ModelChoiceField):
    """
    Uma versão do forms.ModelChoiceField que trabalha de forma aninhada, onde ele é preenchido de acordo com uma escolha de outro "select".
    Keyword arguments:
       *obj_label:             Uma string com o label que deve ser colocado no option do select
        empty_label            Uma string a ser apresentada quando não tiver dados
        url:                   Uma string com a url de pesquisa. Ela deve retornar um Json e recebe os seguintes parametros: `request.POST` expected args: 'chained_attr', 'id', 'obj_label'
        qs_filter:             Uma query no formato string
                                 Exemplo: aluno__caracterizacao__isnull=False
        qs_filter_params_map   Um dict com parâmetros para o qs_fitler
                                 Exemplo: qs_filter='avaliadores_de_agendamentos=current_user'
                                          qs_filter_params_map    = {'current_user': tl.get_user().id},
      * form_filters           Uma lista de lista que tem 'Uma string com o nome do campo relacionado' e 'Uma string representado com o valor que deve colocar no filter'

    * parametros obrigatórios

    Exemplo:
        estado = forms.ModelChoiceField(Estado.object.all(), label=u'Estado')
        cidade = forms.ChainedModelChoiceFieldPlus(Cidade.objects.all(),
                                              label                = u'Cidade',
                                              empty_label          = u'Selecione o Estado',
                                              obj_label            = 'nome',
                                              form_filters         = [('estado', 'estado_id')]
                                              qs_filter            = 'estado__pais=pais'
                                              qs_filter_params_map = {'pais':1})
    """

    widget = ChainedSelectWidget

    def __init__(
        self,
        queryset,
        *args,
        empty_label='---------',
        required=True,
        widget=None,
        label=None,
        initial=None,
        help_text=None,
        to_field_name=None,
        **kwargs,
    ):
        try:
            obj_label = kwargs.pop('obj_label')
        except KeyError:
            raise KeyError('Parameter obj_label is required.')

        try:
            form_filters = kwargs.pop('form_filters')
        except KeyError:
            raise KeyError('Parameter form_filters is required.')

        qs_filter = kwargs.pop('qs_filter', None)
        qs_filter_params_map = kwargs.pop('qs_filter_params_map', {})
        url = kwargs.pop('url', None)
        if not url:
            class_name = queryset.model.__name__
            class_module = queryset.model._meta.app_label
            url = f'/chained_select/{class_module}/{class_name}/'

        super().__init__(
            queryset,
            *args,
            empty_label=empty_label,
            required=required,
            widget=widget,
            label=label,
            initial=initial,
            help_text=help_text,
            to_field_name=to_field_name,
            **kwargs,
        )

        self.widget.initial = initial
        self.widget.empty_label = empty_label
        self.widget.url = url
        self.widget.form_filters = form_filters
        self.widget.obj_label = obj_label
        self.widget.qs_filter = qs_filter
        self.widget.qs_filter_params_map = qs_filter_params_map
        self.widget.queryset = queryset


class ModelMultiplePopupChoiceField(ModelMultipleChoiceField):
    widget = SelectMultiplePopup

    def __init__(self, queryset, required=True, widget=None, label=None, initial=None, help_text=None, **kwargs):
        form_filters = kwargs.pop('form_filters', None)
        list_template = kwargs.pop('list_template', 'popup_multiple_choices.html')
        super().__init__(queryset, required=required, widget=widget, label=label, initial=initial, help_text=help_text, **kwargs)
        self.help_text = help_text
        self.widget.form_filters = form_filters
        self.widget.list_template = list_template


class ModelPopupChoiceField(ModelChoiceField):
    widget = SelectPopup

    def __init__(self, queryset, *args, empty_label='---------', required=True, widget=None, label=None, initial=None, help_text=None, **kwargs):
        form_filters = kwargs.pop('form_filters', None)
        list_template = kwargs.pop('list_template', 'popup_choices.html')
        super().__init__(
            queryset,
            *args,
            empty_label=empty_label,
            required=required,
            widget=widget,
            label=label,
            initial=initial,
            help_text=help_text,
            **kwargs,
        )
        self.help_text = help_text
        self.widget.form_filters = form_filters
        self.widget.list_template = list_template
