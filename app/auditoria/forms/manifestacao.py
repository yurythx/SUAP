from django.db import transaction

from tinymce.widgets import TinyMCE
from djtools import forms
from rh.models import Setor

from ..models import Manifestacao, ManifestacaoDocumento, Monitoramento, ProrrogacaoPrazo, TipoManifestacao


class MonitoramentoManifestacaoForm(forms.ModelFormPlus):
    texto = forms.CharField(
        widget=TinyMCE(attrs={'class': 'tinymce', 'style': 'width: 100%;  min-height: 600px;'}), label='Manifestação do auditado', required=True
    )
    # prazo = forms.DateFieldPlus(label='Prazo', required=False)

    class Meta:
        model = Manifestacao
        fields = ['tipo', 'texto']

    def __init__(self, *args, **kwargs):
        self.monitoramento: Monitoramento = kwargs.pop('monitoramento', None)
        super().__init__(*args, **kwargs)
        current_choices = self.fields['tipo'].choices
        self.fields['tipo'].choices = [
            choice
            for choice in current_choices
            if choice[0] not in [TipoManifestacao.SOLICITACAO_PRORROGACAO, TipoManifestacao.AUSENCIA_MANIFESTACAO]
        ]

    def save(self, commit=True):
        instance: Manifestacao = super().save(commit=False)
        instance.monitoramento = self.monitoramento
        instance.solicitacao_providencia = self.monitoramento.ultima_solicitacao
        return super().save(commit)


class SolicitarProrrogacaoManifestacaoForm(forms.ModelFormPlus):
    prazo_atual = forms.DateFieldPlus(label='Prazo atual')
    prazo_solicitado = forms.DateFieldPlus(label='Prazo solicitado', required=True)
    tipo = forms.ChoiceField(label='Tipo de manifestação', required=True)
    texto = forms.CharField(
        widget=TinyMCE(attrs={'class': 'tinymce', 'style': 'width: 100%;  min-height: 600px;'}), label='Justificativa', required=True
    )

    fieldsets = (
        (
            'Dados gerais',
            {
                'fields': (
                    'tipo',
                    'texto',
                )
            },
        ),
        ('Cronograma', {'fields': (('prazo_atual', 'prazo_solicitado'),)}),
    )

    class Meta:
        model = Manifestacao
        fields = ['texto', 'tipo']

    def __init__(self, *args, **kwargs):
        self.monitoramento: Monitoramento = kwargs.pop('monitoramento', None)
        super().__init__(*args, **kwargs)
        # Configura 'tipo' para ser apenas 'Solicitação de Prorrogação' e esconde o campo
        self.initial['tipo'] = TipoManifestacao.SOLICITACAO_PRORROGACAO
        self.initial['prazo_atual'] = self.monitoramento.ultima_solicitacao.prazo_atual
        #
        self.fields['tipo'].choices = [
            (TipoManifestacao.SOLICITACAO_PRORROGACAO, TipoManifestacao.get_label(TipoManifestacao.SOLICITACAO_PRORROGACAO))
        ]
        self.fields['prazo_atual'].widget.attrs['readonly'] = True
        if self.instance.pk:
            self.fields['prazo_solicitado'].initial = ProrrogacaoPrazo.objects.get(manifestacao=self.instance).prazo_solicitado

    def clean(self):
        cleaned_data = super().clean()
        prazo_atual = cleaned_data.get('prazo_atual')
        prazo_solicitado = cleaned_data.get('prazo_solicitado')
        if not prazo_atual:
            self.add_error('prazo_atual', 'O prazo atual não pode ser nulo')
        if not prazo_solicitado:
            self.add_error('prazo_solicitado', 'O prazo solicitado não pode ser nulo')
        if prazo_atual and prazo_solicitado and prazo_atual >= prazo_solicitado:
            self.add_error('prazo_solicitado', 'O prazo solicitado não pode ser menor que o prazo atual')

    @transaction.atomic()
    def save(self, commit=True):
        instance: Manifestacao = super().save(commit=False)
        instance.monitoramento = self.monitoramento
        instance.solicitacao_providencia = self.monitoramento.ultima_solicitacao
        prazo = self.cleaned_data['prazo_solicitado']
        if commit:
            instance = super().save(commit)
            ProrrogacaoPrazo.objects.update_or_create(manifestacao=instance, defaults={'prazo_solicitado': prazo})
        return instance


def ManifestacaoFormFactory(request, manifestacao: Manifestacao):
    if manifestacao.prorrogacao_prazo:
        return SolicitarProrrogacaoManifestacaoForm(
            request.POST or None, request=request, monitoramento=manifestacao.monitoramento, instance=manifestacao
        )
    return MonitoramentoManifestacaoForm(request.POST or None, request=request, monitoramento=manifestacao.monitoramento, instance=manifestacao)


class RemoverDocumentoManifestacaoForm(forms.ModelFormPlus):
    justificativa_remocao = forms.CharField(label='Justificativa', widget=forms.Textarea, required=True)

    class Meta:
        model = ManifestacaoDocumento
        fields = ['justificativa_remocao']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def save(self, commit=True):
        instance: ManifestacaoDocumento = super().save(commit=False)
        instance.remover_documento(self.request.user)
        return super().save(commit)


class ReclassificarManifestacaoForm(forms.ModelFormPlus):
    manifestacao = forms.ModelChoiceField(queryset=Manifestacao.objects.none(), label='Manifestação')
    unidade = forms.ModelChoiceField(Setor.objects, label='Unidade')

    fieldsets = (('Dados gerais', {'fields': ('manifestacao', 'unidade')}), ('Tipo', {'fields': ('tipo',)}))

    class Meta:
        model = Manifestacao
        fields = ('tipo',)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        #
        self.fields['manifestacao'].initial = self.instance.id
        self.fields['manifestacao'].queryset = Manifestacao.objects.filter(id=self.instance.id)
        self.fields['manifestacao'].widget.attrs['readonly'] = True
        self.fields['unidade'].initial = self.instance.unidade.id
        self.fields['unidade'].queryset = Setor.objects.suap_ativos().filter(id=self.instance.unidade.id)
        self.fields['unidade'].widget.attrs['readonly'] = True
        current_choices = self.fields['tipo'].choices
        self.fields['tipo'].choices = [choice for choice in current_choices if choice[0] != TipoManifestacao.SOLICITACAO_PRORROGACAO]
