from django.db import transaction
from django.db.models import CharField, F, Value
from django.db.models.functions import Concat

from comum.models import Ano, Vinculo
from djtools import forms
from djtools.forms.widgets import AutocompleteWidget
from rh.models import Setor

from ..models import DescricaoRecomendacao, NucleoAuditoria, Recomendacao, RecomendacaoDocumento, Relatorio
from ..papeis import get_auditores_ativos


class RecomendacaoAddForm(forms.ModelFormPlus):
    nucleo = forms.ModelChoiceFieldPlus(label='Núcleo executor', queryset=NucleoAuditoria.objects.none(), required=True)
    monitor = forms.ModelChoiceFieldPlus(
        queryset=Vinculo.objects.none(),
        widget=AutocompleteWidget(
            search_fields=Vinculo.SEARCH_FIELDS,
            multiple=False,
            form_filters=[
                ('nucleo', 'nucleoauditoria__in'),
            ],
        ),
        label='Monitor',
    )
    revisor = forms.ModelChoiceFieldPlus(label='Revisor', queryset=Vinculo.objects.none(), required=False)
    relatorio = forms.ModelChoiceFieldPlus(
        label='Relatório de Auditoria:',
        queryset=Relatorio.objects.none(),
        widget=AutocompleteWidget(search_fields=['identificador_annotated'], multiple=False),
    )
    unidades = forms.MultipleModelChoiceFieldPlus(
        queryset=Setor.objects,
        widget=AutocompleteWidget(
            search_fields=Setor.SEARCH_FIELDS,
            multiple=True,
            form_filters=[
                ('relatorio', 'auditoria_relatorio_unidades'),
            ],
        ),
        label='Setores monitorados',
    )
    descricao = forms.CharField(label='Descrição', max_length=1000, widget=forms.Textarea, required=True)

    fieldsets = (
        ('Dados gerais', {'fields': ('relatorio', 'descricao')}),
        ('Cronograma', {'fields': ('data_limite',)}),
        ('Auditoria', {'fields': ('nucleo', ('monitor', 'revisor'), 'unidades')}),
    )

    class Meta:
        model = Recomendacao
        fields = ['relatorio', 'monitor', 'revisor', 'unidades', 'data_limite', 'nucleo']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['relatorio'].queryset = Relatorio.objects.annotate(
            identificador_annotated=Concat(
                F('numero'),
                Value('/'),
                F('ano__ano'),
                Value(' - '),
                F('nucleo__nome'),
                output_field=CharField(),  # Explicitly define the output type as CharField
            )
        ).all()
        self.fields['nucleo'].queryset = NucleoAuditoria.objects.ativos()
        self.fields['monitor'].queryset = get_auditores_ativos()
        self.fields['revisor'].queryset = get_auditores_ativos()

    @transaction.atomic()
    def save(self, commit=True):
        instance = super().save(commit)
        if commit:
            descricao = self.cleaned_data.get('descricao')
            DescricaoRecomendacao.objects.create(recomendacao=instance, descricao=descricao)
        return instance


class RecomendacaoForm(forms.ModelFormPlus):
    numero = forms.IntegerFieldPlus(label='Número', required=True)
    ano = forms.ModelChoiceField(Ano.objects.none(), label='Ano', required=True)
    nucleo = forms.ModelChoiceFieldPlus(label='Núcleo executor', queryset=NucleoAuditoria.objects.none(), required=True)
    monitor = forms.ModelChoiceFieldPlus(
        queryset=Vinculo.objects.none(),
        widget=AutocompleteWidget(
            search_fields=Vinculo.SEARCH_FIELDS,
            multiple=False,
            form_filters=[
                ('nucleo', 'nucleoauditoria__in'),
            ],
        ),
        label='Monitor',
    )
    revisor = forms.ModelChoiceFieldPlus(label='Revisor', queryset=Vinculo.objects.none(), required=False)
    relatorio = forms.ModelChoiceField(label='Relatório de Auditoria:', queryset=Relatorio.objects)
    unidades = forms.MultipleModelChoiceFieldPlus(
        queryset=Setor.objects,
        widget=AutocompleteWidget(
            search_fields=Setor.SEARCH_FIELDS,
            multiple=True,
            form_filters=[
                ('relatorio', 'auditoria_relatorio_unidades'),
            ],
        ),
        label='Setores monitorados',
    )
    descricao = forms.CharField(label='Descrição', max_length=1000, widget=forms.Textarea, required=True)

    fieldsets = (
        (('Dados gerais', {'fields': (('numero', 'ano'), 'relatorio', 'descricao')})),
        ('Cronograma', {'fields': ('data_limite',)}),
        ('Auditoria', {'fields': ('nucleo', ('monitor', 'revisor'), 'unidades')}),
    )

    class Meta:
        model = Recomendacao
        fields = ['numero', 'ano', 'relatorio', 'monitor', 'revisor', 'unidades', 'data_limite', 'nucleo']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['nucleo'].queryset = NucleoAuditoria.objects.ativos()
        self.fields['monitor'].queryset = get_auditores_ativos()
        self.fields['revisor'].queryset = get_auditores_ativos()
        #
        self.fields['ano'].initial = self.instance.ano
        self.fields['ano'].widget.attrs['readonly'] = True
        self.fields['ano'].queryset = Ano.objects.filter(id=self.instance.ano_id)

        self.fields['numero'].widget.attrs['readonly'] = True
        self.fields['numero'].initial = self.instance.numero

        self.fields['descricao'].initial = self.instance.descricao
        if not self.instance.registrada:
            self.fields['descricao'].widget.attrs['readonly'] = True

    def clean_numero(self):
        return self.instance.numero

    def clean_ano(self):
        return self.instance.ano

    def clean_descricao(self):
        return self.cleaned_data['descricao'] if self.instance.registrada else self.instance.descricao


class CancelarRecomendacaoForm(forms.ModelFormPlus):
    recomendacao = forms.ModelChoiceField(label='Recomendação', queryset=Recomendacao.objects.none())
    justificativa = forms.CharFieldPlus(label='Justificativa', widget=forms.Textarea(), required=True)

    fieldsets = (
        (
            'Dados gerais',
            {
                'fields': (
                    'recomendacao',
                    'justificativa',
                )
            },
        ),
    )

    class Meta:
        model = Recomendacao
        fields = ('justificativa',)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['recomendacao'].queryset = Recomendacao.objects.filter(id=self.instance.id)
        self.fields['recomendacao'].initial = self.instance.id
        self.fields['recomendacao'].widget.attrs['readonly'] = True

    def save(self, commit=True):
        if commit:
            self.instance.cancelar(self.request.user, self.cleaned_data['justificativa'])
        return super().save(commit)


class DescricaoRecomendacaoForm(forms.ModelFormPlus):
    recomendacao = forms.ModelChoiceField(label='Recomendação', queryset=Recomendacao.objects.none())
    descricao = forms.CharFieldPlus(label='Nova Descricação', widget=forms.Textarea(), required=True, max_length=1000)
    justificativa = forms.CharFieldPlus(label='Justificativa', widget=forms.Textarea(), required=True, max_length=500)

    class Meta:
        model = DescricaoRecomendacao
        fields = ('recomendacao', 'descricao', 'justificativa')

    def __init__(self, *args, **kwargs):
        recomendacao_id = kwargs.pop('recomendacao_id')
        super().__init__(*args, **kwargs)
        self.fields['recomendacao'].queryset = Recomendacao.objects.filter(id=recomendacao_id)
        self.fields['recomendacao'].initial = recomendacao_id
        self.fields['recomendacao'].widget.attrs['readonly'] = True


class RemoverDocumentoRecomendacaoForm(forms.ModelFormPlus):
    justificativa_remocao = forms.CharField(label='Justificativa', widget=forms.Textarea, required=True)

    class Meta:
        model = RecomendacaoDocumento
        fields = ['justificativa_remocao']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def save(self, commit=True):
        instance: RecomendacaoDocumento = super().save(commit=False)
        instance.remover_documento(self.request.user)
        return super().save(commit)
