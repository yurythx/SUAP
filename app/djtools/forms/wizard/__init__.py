from copy import deepcopy

from django.forms.fields import BooleanField

from djtools import forms


class FormWizardPlus(forms.FormPlus):
    LAST_SUBMIT_LABEL = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if hasattr(self, 'first_step'):
            self.first_step()
        self.original_fields = self.fields
        for name in self.fields:
            if self.fields[name].initial and isinstance(self.fields[name], BooleanField):
                raise Exception('Boolean fields can not have their initial value defined in FormWizardFlus ')
        for key in self.initial:
            if isinstance(self.fields[key], BooleanField):
                raise Exception('Boolean fields can not have their initial value defined in FormWizardFlus ')
        if not hasattr(self, 'cleaned_data'):
            self.cleaned_data = {}

        self.is_wizard = True
        self.length = len(self.steps)
        self.step = 1

        self.configure_fields(0)

    def get_entered_data(self, field_name, is_list=False):
        if field_name in self.data:
            try:
                if is_list:
                    if self.data[field_name] and self.data[field_name].find(';') == -1:
                        value = self.data.getlist(field_name)
                    else:
                        value = self.data[field_name].split(';') if self.data[field_name] else []
                else:
                    value = self.data[field_name]
                if field_name in self.original_fields:
                    return self.original_fields[field_name].clean(value)
                return value
            except forms.ValidationError:
                pass
        return None

    def extract_field_names(self, fields):
        flatten_fieldset = []
        for field in fields:
            if isinstance(field, tuple):
                flatten_fieldset.extend(field)
            else:
                flatten_fieldset.append(field)
        #
        return flatten_fieldset

    def configure_fields(self, current_step):
        self.configure_submit_label(current_step)
        if current_step == len(self.__class__.steps):
            current_step = len(self.steps) - 1
        self.next_step()
        self.fields = {}
        self.steps = deepcopy(self.__class__.steps)
        for i in range(len(self.steps)):
            if i <= current_step:
                for fieldset in self.steps[i]:
                    field_set = self.extract_field_names(fieldset[1]['fields'])
                    for field_name in field_set:
                        if field_name in self.original_fields:
                            self.fields[field_name] = self.original_fields[field_name]

        self.fieldsets = []
        for i in range(current_step + 1):
            for fieldset in self.steps[i]:
                if i < current_step:
                    fieldset[1]['classes'] = ['hidden']
                self.fieldsets.append(fieldset)

    def is_valid(self):
        if not self.data:
            return False

        step = self.get_step(self.data)

        self.configure_fields(step)
        errors = []
        valid = True
        for i in range(len(self.steps)):
            if i <= step:
                for fieldset in self.steps[i]:
                    for field_name in fieldset[1]['fields']:
                        if field_name in list(self.errors.keys()):
                            errors.append(field_name)
                            valid = False

        if '__all__' in list(self.errors.keys()):
            valid = False

        for key in list(self.errors.keys()):
            if key not in errors and key != '__all__':
                del self.errors[key]

        last_step = False
        if valid:
            last_step = self.get_step(self.cleaned_data) == len(self.__class__.steps) - 1
            self.full_clean()
            self.configure_fields(step + 1)
            self.step += 1

        return valid and last_step

    def next_step(self):
        pass

    def configure_submit_label(self, step):
        if step == len(self.__class__.steps) - 1:
            self.__class__.SUBMIT_LABEL = self.LAST_SUBMIT_LABEL or 'Finalizar'
        else:
            self.__class__.SUBMIT_LABEL = 'Continuar'

    def set_data(self, obj):
        for key in list(self.cleaned_data.keys()):
            if hasattr(obj, key):
                setattr(obj, key, self.cleaned_data[key])

    def get_step(self, source=None):
        if not source:
            source = self.fields
        lista = list(range(len(self.steps)))
        lista.reverse()
        for i in lista:
            for fieldset in self.steps[i]:
                for field_name in fieldset[1]['fields']:
                    if field_name in source:
                        self.step = i + 1
                        return i
        self.step = 1
        return 0
