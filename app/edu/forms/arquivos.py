from django.conf import settings

from djtools import forms
from djtools.forms.widgets import (
    AutocompleteWidget,
)
from edu.models import (
    AlunoArquivo,
    TipoAlunoArquivo,
)
from rh.models import ArquivoUnico


class UploadAlunoArquivoUnicoForm(forms.ModelFormPlus):
    conteudo = forms.FileFieldPlus(
        required=True,
        label='Arquivo',
        filetypes=['pdf', 'jpg', 'png'],
        max_file_size=5 * settings.BYTES_SIZE_1MB,
    )
    tipo = forms.ModelChoiceFieldPlus(
        TipoAlunoArquivo.objects.filter(ativo=True).exclude(nome='Outro'),
        required=True,
        label='Tipo',
        widget=AutocompleteWidget(search_fields=TipoAlunoArquivo.SEARCH_FIELDS),
    )

    class Meta:
        model = ArquivoUnico
        fields = ('conteudo',)

    def save(self, *args, **kwargs):
        kwargs.update(commit=False)
        return super().save(*args, **kwargs)


class EditarAlunoArquivoForm(forms.FormPlus):
    tipo = forms.ModelChoiceFieldPlus(queryset=TipoAlunoArquivo.objects.filter(ativo=True), label='Tipo')

    def __init__(self, *args, **kwargs):
        self.instance = kwargs.pop('instance', None)
        super().__init__(*args, **kwargs)
        if self.instance:
            self.fields['tipo'].initial = self.instance.tipo


class AvaliarArquivoUnicoForm(forms.ModelFormPlus):
    validado = forms.ChoiceField(
        label='Validado',
        choices=[[True, 'Sim'], [False, 'Não']],
        initial=True,
        widget=forms.RadioSelect(),
        help_text='Esta escolha não poderá ser desfeita após salvar a avaliação.',
    )

    class Meta:
        model = AlunoArquivo
        fields = 'validado', 'observacao', 'prazo_validade'

    def clean_prazo_validade(self):
        prazo_validade = self.cleaned_data.get('prazo_validade')
        if prazo_validade > 100:
            raise forms.ValidationError('Validade máxima aceita é de 100 anos.')
        return prazo_validade

    def save(self, *args, **kwargs):
        kwargs.update(commit=False)
        return super().save(*args, **kwargs)


class RenovarValidadeArquivoUnicoForm(forms.ModelFormPlus):
    class Meta:
        model = AlunoArquivo
        fields = ('prazo_validade',)

    def processar(self, user):
        self.instance.renovar(user)
