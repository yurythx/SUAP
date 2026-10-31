from django import forms
from django.forms import BaseModelFormSet, SplitDateTimeField, modelformset_factory

from djtools.forms.fields import AutocompleteWidget, DateTimeFieldPlus
from djtools.lps import MetaFormPlus, MetaModelFormPlus


class FormPlus(forms.Form, metaclass=MetaFormPlus):
    """
    Torna o ``request`` disponível no ``FormPlus`` através de ``self.request`` quando passado como parêmetro no inicialização.
    """

    def __init__(self, *args, **kwargs):
        if 'request' in kwargs:
            self.request = kwargs.pop('request')
        super().__init__(*args, **kwargs)

    def clean(self):
        cleaned_data = super().clean()
        if self.errors:
            raise forms.ValidationError('Existem erros no formulário. Verifique os campos destacados.')
        return cleaned_data


class ModelFormPlus(forms.ModelForm, metaclass=MetaModelFormPlus):
    # class ModelFormPlus(forms.ModelForm):
    """
    Torna o ``request`` disponível no ``ModelFormPlus`` através de ``self.request`` quando passado como parêmetro no inicialização.
    """

    def __init__(self, *args, **kwargs):
        if 'request' in kwargs:
            self.request = kwargs.pop('request')
        super().__init__(*args, **kwargs)

    def clean(self):
        cleaned_data = super().clean()
        if self.errors:
            raise forms.ValidationError('Existem erros no formulário. Verifique os campos destacados.')
        return cleaned_data


class DtModelForm(forms.ModelForm):
    """
    ``forms.ModelForm`` com mais poderes

    * Atributo ``required_fields``
    * Atributo ``readonly_fields``
    * Atributo ``hidden_fields_``

    * Definição automática de widgets
       - ModelChoiceField com mais de 50 opções será um AutocompleteWidget
    """

    def _get_widget_for_modelchoicefield(self, fname):
        field = self.fields[fname]
        if isinstance(field, forms.ModelMultipleChoiceField):
            return forms.CheckboxSelectMultiple
        elif isinstance(field, forms.ModelChoiceField):
            if fname in self.declared_fields and self.declared_fields[fname].widget:
                return field.widget
            if isinstance(field, forms.ModelChoiceField):
                if field.queryset.count() <= 50:
                    return field.widget
                return AutocompleteWidget

    def get_field_attrs_for_modelchoicefield(self, fname):
        field = self.fields[fname]
        return {
            'widget': self._get_widget_for_modelchoicefield(fname),
            'required': field.required,
            'queryset': field.queryset,
            'empty_label': field.empty_label,
            'label': field.label,
            'initial': field.initial,
            'help_text': field.help_text,
            'to_field_name': field.to_field_name,
        }

    def get_field_attrs_for_datefield(self, fname):
        field = self.fields[fname]
        return {'required': field.required, 'label': field.label, 'initial': field.initial, 'help_text': field.help_text}

    def __init__(self, *args, **kwargs):
        self.Meta.exclude = ['cadastrado_em', 'cadastrado_por']
        super().__init__(*args, **kwargs)

        self.required_fields = getattr(self, 'required_fields', [])
        self.readonly_fields = getattr(self, 'readonly_fields', [])
        self.hidden_fields_ = getattr(self, 'hidden_fields_', [])
        self.exclude = [f.name for f in self._meta.model._meta.fields if not f.editable]

        for fname, field in list(self.fields.items()):
            if isinstance(field, forms.ModelChoiceField):
                new_f = forms.ModelChoiceField(**self.get_field_attrs_for_modelchoicefield(fname))
                self.fields[fname] = new_f

            if isinstance(field, forms.ModelMultipleChoiceField):
                attrs = self.get_field_attrs_for_modelchoicefield(fname)
                attrs.pop('empty_label')
                attrs.pop('to_field_name')
                new_f = forms.ModelMultipleChoiceField(**attrs)
                self.fields[fname] = new_f

            if isinstance(field, forms.DateTimeField | SplitDateTimeField):
                new_f = DateTimeFieldPlus(**self.get_field_attrs_for_datefield(fname))
                self.fields[fname] = new_f

            if fname in self.required_fields:
                self.fields[fname].required = True

            if fname in self.readonly_fields:
                self.fields[fname].widget.attrs.update({'readonly': 'readonly'})

            if fname in self.hidden_fields_:
                self.fields[fname].widget = forms.HiddenInput()


class NonrelatedInlineFormSet(BaseModelFormSet):
    """
    A basic implementation of an inline formset that doesn't make assumptions
    about any relationship between the form model and its parent instance.
    """

    def __init__(self, instance=None, save_as_new=None, **kwargs):
        self.instance = instance
        super().__init__(**kwargs)
        self.queryset = self.real_queryset

    @classmethod
    def get_default_prefix(cls):
        opts = cls.model._meta
        return opts.app_label + '-' + opts.model_name

    def save_new(self, form, commit=True):
        obj = super().save_new(form, commit=False)
        self.save_new_instance(self.instance, obj)
        if commit:
            obj.save()
        return obj


def nonrelated_inlineformset_factory(model, obj=None, queryset=None, formset=NonrelatedInlineFormSet, save_new_instance=None, **kwargs):
    """
    FormSet factory that sets an explicit queryset on new classes.
    """
    FormSet = modelformset_factory(model, formset=formset, **kwargs)
    FormSet.real_queryset = queryset
    FormSet.save_new_instance = save_new_instance
    return FormSet
