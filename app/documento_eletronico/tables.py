import django_filters
import django_tables2 as tables
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Field, Layout
from django import forms

from .models import Documento


class DocumentoTable(tables.Table):
    class Meta:
        model = Documento
        fields = ('identificador', 'tipo_documento', 'nivel_acesso')
        empty_text = 'A busca não encontrou nenhum resultado'
        attrs = {'class': 'paleblue'}


class DocumentoFilter(django_filters.FilterSet):
    class Meta:
        model = Documento
        fields = ('identificador', 'tipo', 'nivel_acesso', 'setor_dono__uo', 'setor_dono')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        CHOICES_FOR_FILTER = [('', '---------')]
        CHOICES_FOR_FILTER.extend(list(Documento.NIVEL_ACESSO_CHOICES))
        self.filters['nivel_acesso'].extra.update({'choices': CHOICES_FOR_FILTER})


class DocumentoFilterFormHelper(forms.ModelForm):
    class Meta:
        model = Documento
        fields = ['identificador', 'tipo', 'nivel_acesso', 'setor_dono']

    def __init__(self, *args, **kwargs):
        self.helper = FormHelper()
        self.helper.form_method = 'get'
        self.helper.form_action = 'submit_filter'
        self.helper.form_id = 'id-DocumentoFilterFormHelper'
        self.helper.form_class = 'form-horizontal'
        self.helper.label_class = 'col-sm-2'
        self.helper.field_class = 'col-sm-4'
        self.helper.error_text_inline = False
        self.helper.form_tag = False
        self.helper.layout = Layout(Field('identificador'), Field('tipo'), Field('nivel_acesso'), Field('setor_dono'))
        super().__init__(*args, **kwargs)
