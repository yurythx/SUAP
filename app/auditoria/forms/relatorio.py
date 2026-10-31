from comum.models import Ano, Vinculo
from djtools import forms
from djtools.forms.widgets import AutocompleteWidget
from djtools.utils import get_datetime_now
from documento_eletronico.models import TipoDocumento
from rh.models import Setor

from ..modelos import get_tipo_relatorio_auditoria
from ..models import NucleoAuditoria, Relatorio, RelatorioDocumento, Acao
from ..papeis import get_auditores_ativos
from .documento import DocumentoDigitalizadoForm


class RelatorioAddForm(forms.ModelFormPlus):
    ano_paint = forms.ModelChoiceFieldPlus(label='Ano/PAINT', queryset=Ano.objects.ultimos())
    acao = forms.ModelChoiceFieldPlus(label='Ação de Auditoria', queryset=Acao.objects.none(), required=True)
    nucleo = forms.ModelChoiceFieldPlus(label='Núcleo de Auditoria', queryset=NucleoAuditoria.objects.none(), required=True)
    equipe = forms.MultipleModelChoiceFieldPlus(
        queryset=Vinculo.objects,
        widget=AutocompleteWidget(
            search_fields=Vinculo.SEARCH_FIELDS,
            multiple=True,
            form_filters=[
                ('nucleo', 'nucleoauditoria__in'),
            ],
        ),
        label='Equipe Responsável',
    )
    data_inicio = forms.DateFieldPlus(label='Data Inicial', required=True)
    data_fim = forms.DateFieldPlus(label='Data Final', required=True)
    unidades_auditadas = forms.MultipleModelChoiceFieldPlus(
        label='Unidades Auditadas', queryset=Setor.objects, required=True, widget=AutocompleteWidget(search_fields=Setor.SEARCH_FIELDS, multiple=True)
    )
    fieldsets = (
        (
            'Dados gerais',
            {
                'fields': (
                    ('numero', 'ano'),
                    ('acao', 'ano_paint'),
                )
            },
        ),
        ('Periódo de abrangência', {'fields': (('data_inicio', 'data_fim'),)}),
        (
            'Responsáveis',
            {
                'fields': (
                    'nucleo',
                    'equipe',
                )
            },
        ),
        ('Unidades auditadas', {'fields': ('unidades_auditadas',)}),
    )

    class Meta:
        model = Relatorio
        fields = ['numero', 'ano', 'ano_paint', 'acao', 'nucleo', 'equipe', 'unidades_auditadas', 'data_inicio', 'data_fim']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Equipe de Trabalho
        self.fields['equipe'].queryset = get_auditores_ativos()
        self.fields['nucleo'].queryset = NucleoAuditoria.objects.ativos()
        self.fields['ano'].queryset = Ano.objects.ultimos()
        self.fields['acao'].queryset = Acao.objects.ativas()

    def clean_data_inicio(self):
        data_inicio = self.cleaned_data.get('data_inicio', None)
        if not data_inicio:
            raise forms.ValidationError('Este campo é obrigatório.')
        if data_inicio > get_datetime_now().date():
            raise forms.ValidationError('Data de início não pode ser posterior a hoje')
        return data_inicio

    def clean_data_fim(self):
        data_fim = self.cleaned_data.get('data_fim', None)
        if not data_fim:
            raise forms.ValidationError('Este campo é obrigatório.')
        return data_fim

    def clean(self):
        cleaned_data = super().clean()
        data_inicio = cleaned_data.get('data_inicio', None)
        data_fim = cleaned_data.get('data_fim', None)
        if (data_inicio and data_fim) and (data_inicio > data_fim):
            self.add_error('data_inicio', 'A data de início não pode ser posterior a data de finalização do relatório')
        #
        return cleaned_data


class RelatorioDigitalizadoForm(DocumentoDigitalizadoForm):
    identificador_numero = forms.IntegerField(required=True)
    identificador_ano = forms.IntegerField(required=True)

    tipo = forms.ModelChoiceFieldPlus(TipoDocumento.objects.none(), label='Tipo do  Documento')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        tipo_relatorio = get_tipo_relatorio_auditoria()
        self.fields['tipo'].queryset = TipoDocumento.objects.filter(id=tipo_relatorio.id)
        self.fields['tipo'].initial = tipo_relatorio.id
        self.fields['tipo'].widget.attrs['readonly'] = True
        # O upload serah feito sempre para o setor do usuário
        self.fields['dono_documento'].initial = self.request.user.get_vinculo().id
        self.fields['dono_documento'].queryset = get_auditores_ativos()


class RelatorioDigitalizadoEditForm(DocumentoDigitalizadoForm):
    identificador_numero = forms.IntegerField(required=True)
    identificador_ano = forms.IntegerField(required=True)
    fieldsets = (
        (
            'Dados do Documento',
            {'fields': ('tipo_conferencia', 'tipo', 'assunto', ('setor_dono', 'dono_documento'))},
        ),
        (
            'Dados Adicionais',
            {'fields': (('identificador_numero', 'identificador_ano'), 'identificador_setor_sigla', 'identificador_tipo_documento_sigla')},
        ),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['dono_documento'].queryset = Vinculo.objects.filter(id=self.instance.dono_documento.id)
        self.fields['dono_documento'].widget.attrs['readonly'] = True
        #
        self.fields['setor_dono'].queryset = Setor.objects.suap_ativos().filter(id=self.instance.setor_dono.id)
        self.fields['setor_dono'].widget.attrs['readonly'] = True
        del self.fields['arquivo']


class RemoverDocumentoRelatorioForm(forms.ModelFormPlus):
    justificativa_remocao = forms.CharField(label='Justificativa', widget=forms.Textarea, required=True)

    class Meta:
        model = RelatorioDocumento
        fields = ['justificativa_remocao']

    def save(self, commit=True):
        instance: RelatorioDocumento = super().save(commit=False)
        instance.remover_documento(self.request.user)
        return super().save(commit)


class RelatorioRainFilterForm(forms.FormPlus):
    METHOD = 'GET'
    ano = forms.ModelChoiceField(queryset=Ano.objects.none(), required=False, label='Ano')
    acao = forms.ModelChoiceField(queryset=Acao.objects.none(), required=False, label='Ação')
    fieldsets = (('Filtros Gerais', {'fields': (('ano', 'acao'),)}),)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        anos_relatorios = Relatorio.objects.values_list('ano', flat=True)
        acoes = Relatorio.objects.values_list('acao__id', flat=True)
        self.fields['ano'].queryset = Ano.objects.filter(id__in=anos_relatorios)
        self.fields['acao'].queryset = Acao.objects.filter(id__in=acoes)

    def filter_queryset(self, queryset):
        """
        Aplica os filtros ao queryset de Relatorio
        """
        if self.is_valid():
            ano = self.cleaned_data.get('ano')
            acao = self.cleaned_data.get('acao')
            if ano:
                queryset = queryset.filter(ano=ano)
            if acao:
                queryset = queryset.filter(nome_acao__icontains=acao)
        return queryset
