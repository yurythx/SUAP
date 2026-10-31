import django_filters
import django_tables2 as tables
from crispy_forms.helper import FormHelper

from documento_eletronico.models import Documento

from .models import Processo


class DocumentoTable(tables.Table):
    numero = tables.TemplateColumn(
        '<a href="/processo_eletronico/processo/{{table.processo}}/adicionar/{{record.pk}}">{{record}}</a>', orderable=False
    )

    def __init__(self, *args, **kwargs):
        self.processo = kwargs.pop('processo_pk', None)
        super().__init__(*args, **kwargs)

    class Meta:
        model = Documento
        fields = ('numero', 'assunto', 'tipo', 'nivel_acesso')
        empty_text = 'A busca não encontrou nenhum resultado'


class ProcessoTable(tables.Table):
    numero_protocolo = tables.TemplateColumn(
        '<a href="/processo_eletronico/processo/{{table.processo}}/apensar_processo/{{record.pk}}">{{record}}</a>', orderable=False
    )

    def __init__(self, *args, **kwargs):
        self.processo = kwargs.pop('processo_pk', None)
        super().__init__(*args, **kwargs)

    class Meta:
        model = Processo
        fields = ('numero_protocolo', 'nivel_acesso')
        empty_text = 'A busca não encontrou nenhum resultado'


class ProcessoFilter(django_filters.FilterSet):
    class Meta:
        model = Processo
        fields = ('numero_protocolo',)


class ProcessoFilterFormHelper(FormHelper):
    class Meta:
        model = Documento
        form_tag = False
        fields = ('numero_protocolo', 'tipo_processo', 'nivel_acesso')
