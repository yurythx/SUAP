from djtools import forms
from djtools.forms.widgets import AutocompleteWidget
from ..models import Acao, TipoServico


class AcaoForm(forms.ModelFormPlus):
    nome = forms.CharField(max_length=255, label='Nome da ação', help_text='Informe o nome da ação de auditoria.', required=True)
    descricao = forms.CharField(
        max_length=500,
        label='Descrição',
        help_text='Informe uma descrição detalhada da ação.',
        required=False,
        widget=forms.Textarea(attrs={'rows': 3, 'placeholder': 'Descrição da ação'}),
    )
    tipo_servico = forms.ModelChoiceField(
        queryset=TipoServico.objects.none(),  # This should be set to the appropriate queryset in the view
        label='Tipo de Serviço',
        help_text='Selecione o tipo de serviço relacionado à ação.',
        required=True,
        widget=AutocompleteWidget(search_fields=TipoServico.SEARCH_FIELDS),
    )
    ativo = forms.BooleanField(initial=True, label='Ativo', help_text='Marque se a ação está ativa.', required=False)

    fieldsets = (
        (
            None,
            {
                'fields': ('nome', 'descricao', 'tipo_servico', 'ativo'),
            },
        ),
    )

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request', None)
        super().__init__(*args, **kwargs)
        self.fields['tipo_servico'].queryset = TipoServico.objects.ativos()

    class Meta:
        model = Acao
        fields = ['nome', 'tipo_servico', 'ativo']

    def save(self, commit=True):
        instance: Acao = super().save(commit=False)
        if commit:
            if not instance.pk:
                # If the instance is new, set created_by and modified_by
                instance.criado_por = self.request.user.vinculo
            instance.alterado_por = self.request.user.vinculo
            return super().save(commit=True)
        return instance
