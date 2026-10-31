from acervo_academico import tasks
from acervo_academico.models import RotinaImportacao
from djtools import forms
from rh.models import UnidadeOrganizacional


class RotinaImportacaoForm(forms.ModelFormPlus):
    class Meta:
        model = RotinaImportacao
        fields = ('url_diretorio_raiz',)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields[
            'url_diretorio_raiz'
        ].help_text = 'Informe o link completo do diretório raiz no Sharepoint (acesse o diretório raiz pelo navegador e copie a URL).'

    def clean_url_diretorio_raiz(self):
        RotinaImportacao(url_diretorio_raiz=self.cleaned_data['url_diretorio_raiz']).decodificar_url_raiz()


class ProcessarRotinaForm(forms.FormPlus):
    campi = forms.ModelMultipleChoiceField(
        label='Campi',
        queryset=UnidadeOrganizacional.objects.suap().campi(),
        required=True,
        widget=forms.CheckboxSelectMultiplePlus(),
        help_text='Escolha os campi que serão processados nesta execução.',
    )
    reprocessar_bem_sucedidos = forms.BooleanField(label='Reprocessar execuções bem sucedidas', required=False)

    def __init__(self, rotina: RotinaImportacao, ids_campi: list | None = None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.rotina = rotina

        qs_initial_campi = UnidadeOrganizacional.objects.suap().campi()
        if ids_campi:
            qs_initial_campi = qs_initial_campi.filter(pk__in=ids_campi)

        self.fields['campi'].initial = list(qs_initial_campi.values_list('pk', flat=True))

    def processar(self):
        qs_campi = self.cleaned_data['campi']
        reprocessar_bem_sucedidos = self.cleaned_data['reprocessar_bem_sucedidos']
        return tasks.processar_rotina_de_importacao(self.rotina, qs_campi, reprocessar_bem_sucedidos)
