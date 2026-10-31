from django.db.models import Sum

import comum
from comum.models import Vinculo
from djtools import forms
from djtools.forms.widgets import AutocompleteWidget, BrDataWidget
from financeiro.models import (
    Acao,
    AcaoAno,
    ClassificacaoInstitucional,
    EsferaOrcamentaria,
    Evento,
    FonteRecurso,
    NaturezaDespesa,
    PlanoInterno,
    ProgramaTrabalhoResumido,
    SubElementoNaturezaDespesa,
    UnidadeGestora,
)
from planejamento.models import OrigemRecurso
from rh.models import Setor


class EventoForm(forms.ModelFormPlus):
    class Meta:
        model = Evento
        exclude = ()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.request.user.is_superuser:
            self.fields['codigo'].widget.attrs['readonly'] = True
            self.fields['nome'].widget.attrs['readonly'] = True
            self.fields['descricao'].widget.attrs['readonly'] = True
            self.fields['ativo'].widget.attrs['disabled'] = True
        self.fields['tipo'].required = False


class UnidadeGestoraForm(forms.ModelFormPlus):
    setor = forms.ModelChoiceField(label='Setor Equivalente', queryset=Setor.objects.suap_ativos().filter(codigo=None), widget=forms.Select())

    class Meta:
        model = UnidadeGestora
        exclude = ()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.request.user.is_superuser:
            self.fields['codigo'].widget.attrs['readonly'] = True
            self.fields['nome'] = forms.CharField(label='Função', widget=forms.TextInput(attrs={'readonly': True, 'size': '95'}))
            self.fields['mnemonico'].widget.attrs['readonly'] = True
            self.fields['municipio'] = forms.ModelChoiceField(
                label='Município',
                queryset=comum.models.Municipio.objects.all(),
                widget=AutocompleteWidget(search_fields=comum.models.Municipio.SEARCH_FIELDS, readonly=True),
            )
            self.fields['funcao'] = forms.CharField(label='Função', widget=forms.TextInput(attrs={'readonly': True}))
            self.fields['ativo'].widget.attrs['disabled'] = True
        self.fields['setor'].required = False


class NotaCreditoForm(forms.ModelFormPlus):
    numero = forms.CharField(label='Número da Nota', max_length=12)
    numero_original = forms.CharField(label='Número Original', max_length=12, required=False)
    datahora_emissao = forms.DateTimeFieldPlus(label='Data de Emissão')
    emitente_ug = forms.ModelChoiceField(
        label='UG Emitente', queryset=UnidadeGestora.objects.all(), widget=AutocompleteWidget(search_fields=UnidadeGestora.SEARCH_FIELDS)
    )
    emitente_ci = forms.ModelChoiceField(
        label='Gestão Emitente',
        queryset=ClassificacaoInstitucional.objects.all(),
        widget=AutocompleteWidget(search_fields=ClassificacaoInstitucional.SEARCH_FIELDS),
    )
    favorecido_ug = forms.ModelChoiceField(
        label='UG Favorecida', queryset=UnidadeGestora.objects.all(), widget=AutocompleteWidget(search_fields=UnidadeGestora.SEARCH_FIELDS)
    )
    favorecido_ci = forms.ModelChoiceField(
        label='Gestão Favorecida',
        queryset=ClassificacaoInstitucional.objects.all(),
        widget=AutocompleteWidget(search_fields=ClassificacaoInstitucional.SEARCH_FIELDS),
    )
    tx_cambial = forms.DecimalField(label='Taxa Cambial', required=False)
    sistema_origem = forms.CharField(label='Sistema de Origem', required=False)

    class Meta:
        exclude = ['registro_manual']

    def save(self, commit=True):
        # indica que o registro foi inserido manualmente e não pela importação
        self.instance.registro_manual = True
        return super().save(commit)


class NotaCreditoItemForm(forms.ModelFormPlus):
    evento = forms.ModelChoiceField(label='Evento', queryset=Evento.objects.all(), widget=AutocompleteWidget(search_fields=Evento.SEARCH_FIELDS))
    esfera = forms.ModelChoiceField(queryset=EsferaOrcamentaria.objects.all())
    ptres = forms.ModelChoiceField(queryset=ProgramaTrabalhoResumido.objects.all().order_by('codigo'))
    fonte_recurso_original = forms.CharField(label='Fonte de Recurso Completa', max_length=10)
    natureza_despesa = forms.ModelChoiceField(
        label='Natureza de Despesa', queryset=NaturezaDespesa.objects.all(), widget=AutocompleteWidget(search_fields=NaturezaDespesa.SEARCH_FIELDS)
    )
    subitem = forms.CharField(required=False)
    ugr = forms.ModelChoiceField(
        queryset=UnidadeGestora.objects.all(), widget=AutocompleteWidget(search_fields=UnidadeGestora.SEARCH_FIELDS), required=False
    )
    plano_interno = forms.ModelChoiceField(queryset=PlanoInterno.objects.all().order_by('codigo'), required=False)
    valor = forms.DecimalFieldPlus(label='Valor')

    fields = ('evento', 'esfera', 'ptres', 'fonte_recurso_original', 'natureza_despesa', 'subitem', 'ugr', 'valor')

    class Meta:
        exclude = ['fonte_recurso']

    def clean(self):
        if self.cleaned_data['fonte_recurso_original']:
            if len(self.cleaned_data['fonte_recurso_original']) != 10:
                raise forms.ValidationError('A fonte de recurso deve conter 10 dígitos.')
            try:
                self.instance.fonte_recurso = FonteRecurso.objects.get(codigo=self.cleaned_data['fonte_recurso_original'][1:4])
            except Exception:
                raise forms.ValidationError('Fonte de recurso desconhecida.')
        return self.cleaned_data


class NotaCreditoConsultaForm(forms.FormPlus):
    numero = forms.CharField(label='Número da Nota', required=False)
    data_inicial = forms.DateFieldPlus(label='Período de Emissão', help_text='Data de início', required=False)
    data_final = forms.DateFieldPlus(help_text='Data final', widget=BrDataWidget(show_label=False), required=False)
    natureza_desp = forms.ModelChoiceField(
        label='Natureza de Despesa',
        required=False,
        queryset=NaturezaDespesa.objects.all(),
        widget=AutocompleteWidget(search_fields=NaturezaDespesa.SEARCH_FIELDS),
    )
    emitente = forms.ModelChoiceField(
        label='Emitente', required=False, queryset=UnidadeGestora.objects.all(), widget=AutocompleteWidget(search_fields=UnidadeGestora.SEARCH_FIELDS)
    )
    favorecido = forms.ModelChoiceField(
        label='Favorecido',
        required=False,
        queryset=UnidadeGestora.objects.all(),
        widget=AutocompleteWidget(search_fields=UnidadeGestora.SEARCH_FIELDS),
    )

    fieldsets = [(None, {'fields': ('numero', 'natureza_desp', 'emitente', 'favorecido', ('data_inicial', 'data_final'))})]

    def clean(self):
        if (
            self.cleaned_data['numero'] == ''
            and self.cleaned_data['emitente'] is None
            and self.cleaned_data['favorecido'] is None
            and self.cleaned_data['data_inicial'] is None
            and self.cleaned_data['data_final'] is None
            and self.cleaned_data['natureza_desp'] is None
        ):
            raise forms.ValidationError('Preencha algum dos campos para a realização da consulta.')

        if self.cleaned_data['data_inicial'] is not None and self.cleaned_data['data_final'] is None:
            raise forms.ValidationError('Forneça a data final do período de emissão.')

        if self.cleaned_data['data_final'] < self.cleaned_data['data_inicial']:
            raise forms.ValidationError('A data limite deve ser posterior a data inicial.')

        return self.cleaned_data


class NotaDotacaoConsultaForm(forms.FormPlus):
    numero = forms.CharField(label='Número da Nota', required=False)
    data_inicial = forms.DateFieldPlus(label='Período de Emissão', help_text='Data de início', required=False)
    data_final = forms.DateFieldPlus(help_text='Data final', widget=BrDataWidget(show_label=False), required=False)
    natureza_desp = forms.ModelChoiceField(
        label='Natureza de Despesa',
        required=False,
        queryset=NaturezaDespesa.objects.all(),
        widget=AutocompleteWidget(search_fields=NaturezaDespesa.SEARCH_FIELDS),
    )
    emitente = forms.ModelChoiceField(
        label='Emitente', required=False, queryset=UnidadeGestora.objects.all(), widget=AutocompleteWidget(search_fields=UnidadeGestora.SEARCH_FIELDS)
    )

    fieldsets = [(None, {'fields': ('numero', 'natureza_desp', 'emitente', ('data_inicial', 'data_final'))})]

    def clean(self):
        if (
            self.cleaned_data['numero'] == ''
            and self.cleaned_data['emitente'] is None
            and self.cleaned_data['data_inicial'] is None
            and self.cleaned_data['data_final'] is None
            and self.cleaned_data['natureza_desp'] is None
        ):
            raise forms.ValidationError('Preencha algum dos campos para a realização da consulta.')

        if self.cleaned_data['data_inicial'] is not None and self.cleaned_data['data_final'] is None:
            raise forms.ValidationError('Forneça a data final do período de emissão.')

        if self.cleaned_data['data_final'] < self.cleaned_data['data_inicial']:
            raise forms.ValidationError('A data limite deve ser posterior a data inicial.')

        return self.cleaned_data


class FormSubElementoNaturezaDespesa(forms.ModelFormPlus):
    class Meta:
        model = SubElementoNaturezaDespesa
        exclude = ['codigo']

    natureza_despesa = forms.ModelChoiceField(
        queryset=NaturezaDespesa.objects.all(), widget=AutocompleteWidget(search_fields=NaturezaDespesa.SEARCH_FIELDS), required=False
    )


class AcaoFiltroForm(forms.FormPlus):
    acao_orcamento = None

    def __init__(self, *args, **kwargs):
        if 'id_acao' in kwargs:
            id_acao = kwargs.pop('id_acao')

            # verifica se foi repassado algum valor que deve ser exibido como propriedade empty_label
            if 'empty_label' in kwargs:
                empty_label = kwargs.pop('empty_label')
            else:
                empty_label = '---------'

            super().__init__(*args, **kwargs)

            self.fields['acao_orcamento'] = forms.ModelChoiceFieldPlus2(
                label='Ação do Orçamento',
                queryset=Acao.objects.all(),
                widget=forms.Select(attrs={'onchange': 'submeter_form(this)'}),
                empty_label=empty_label,
            )

            # verifica se existe acao para o id informado
            if id_acao:
                acao = Acao.objects.get(id=id_acao)
                self.fields['acao_orcamento'].initial = acao.id


class AcaoAnoForm(forms.ModelFormPlus):
    class Meta:
        model = AcaoAno
        exclude = ()

    def clean_valor_capital(self):
        if self.instance.pk:
            total_origemrecurso = next(iter(OrigemRecurso.objects.filter(acao_ano=self.instance.pk).aggregate(Sum('valor_capital')).values())) or 0
            if total_origemrecurso > self.cleaned_data['valor_capital']:
                raise forms.ValidationError('Este valor é inferior ao planejado nas Origens de Recursos')
        return self.cleaned_data['valor_capital']

    def clean_valor_custeio(self):
        if self.instance.pk:
            total_origemrecurso = next(iter(OrigemRecurso.objects.filter(acao_ano=self.instance.pk).aggregate(Sum('valor_custeio')).values())) or 0
            if total_origemrecurso > self.cleaned_data['valor_custeio']:
                raise forms.ValidationError('Este valor é inferior ao planejado nas Origens de Recursos')
        return self.cleaned_data['valor_custeio']


class NotaEmpenhoForm(forms.ModelFormPlus):
    numero = forms.CharField(label='Número da Nota', max_length=12)
    data_emissao = forms.DateFieldPlus(label='Data de Emissão')
    data_transacao = forms.DateTimeFieldPlus(label='Data da Transação')
    emitente_ug = forms.ModelChoiceField(
        label='UG Emitente', queryset=UnidadeGestora.objects.all(), widget=AutocompleteWidget(search_fields=UnidadeGestora.SEARCH_FIELDS)
    )
    vinculo_operador = forms.ModelChoiceField(
        label='Operador', widget=AutocompleteWidget(search_fields=Vinculo.SEARCH_FIELDS), queryset=Vinculo.objects.all()
    )
    ug_operador = forms.ModelChoiceField(
        label='UG Operador', queryset=UnidadeGestora.objects.all(), widget=AutocompleteWidget(search_fields=UnidadeGestora.SEARCH_FIELDS)
    )
    valor = forms.DecimalFieldPlus()

    class Meta:
        fields = [
            'numero',
            'data_emissao',
            'data_transacao',
            'emitente_ug',
            'evento',
            'natureza_despesa',
            'valor',
            'vinculo_operador',
            'ug_operador',
            'ptres',
        ]

    # indica que o registro foi inserido manualmente e não pela importação
    def save(self, commit=True):
        self.instance.registro_manual = True
        return super().save(commit)


class NotaEmpenhoItemForm(forms.ModelFormPlus):
    subitem = forms.ModelChoiceField(label='Subitem', queryset=SubElementoNaturezaDespesa.objects.all().order_by('codigo'))
    data_transacao = forms.DateTimeFieldPlus(label='Data de Emissão')
    valor_total = forms.DecimalFieldPlus()
    valor_unitario = forms.DecimalFieldPlus()

    class Meta:
        fields = ['numero', 'subitem', 'data_transacao', 'quantidade', 'valor_total', 'valor_unitario']


class NotaEmpenhoListaItemForm(forms.ModelFormPlus):
    class Meta:
        exclude = ['nota_empenho']
