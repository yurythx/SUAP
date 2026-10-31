from arquivo.models import Arquivo, Processo, TipoArquivo
from djtools import forms
from djtools.forms.widgets import AutocompleteWidget
from protocolo.models import Processo as ProcessoProtocolo
from rh.models import Servidor, UnidadeOrganizacional


class IdentificarArquivoForm(forms.ModelFormPlus):
    IDENTIFICACAO_CHOICES_FORMULARIO = [[1, 'Identificar'], [3, 'Rejeitar Imagem']]

    acao = forms.ChoiceField(label='Ação:', choices=IDENTIFICACAO_CHOICES_FORMULARIO, required=True, widget=forms.RadioSelect)
    tipo_arquivo = forms.ModelChoiceField(
        label='Tipo de Arquivo',
        queryset=TipoArquivo.objects.all(),
        widget=AutocompleteWidget(search_fields=TipoArquivo.SEARCH_FIELDS),
        help_text='Você deve buscar e selecionar um Tipo de Arquivo pré-cadastrado',
        required=False,
    )
    justificativa_rejeicao = forms.CharField(
        widget=forms.Textarea,
        label='Justificativa da Rejeição:',
        help_text='Descreva o motivo pelo qual o arquivo está sendo rejeitado',
        required=False,
    )

    class Meta:
        model = Arquivo
        exclude = (
            'validado_em',
            'identificado_em',
            'nome',
            'pasta_arquivo',
            'status',
            'objeto',
            'content_type',
            'object_id',
            'file',
            'id',
            'processo_protocolo',
        )

    class Media:
        js = ('/static/arquivo/js/RejeitarArquivo.js',)

    def clean(self):
        if 'acao' in self.cleaned_data:
            if self.cleaned_data['acao'] == '1' and self.cleaned_data['tipo_arquivo'] is None:
                raise forms.ValidationError('Escolha um tipo de Arquivo')
            if self.cleaned_data['acao'] == '3' and self.cleaned_data['justificativa_rejeicao'] == '':
                raise forms.ValidationError(
                    'Descreva o motivo da rejeição \
                                            do arquivo'
                )
        return self.cleaned_data


class ValidarArquivoForm(forms.ModelFormPlus):
    VALIDACAO_CHOICES_FORMULARIO = [[2, 'Validar Arquivo'], [3, 'Rejeitar Imagem']]
    acao = forms.ChoiceField(label='Ação:', choices=VALIDACAO_CHOICES_FORMULARIO, required=True, widget=forms.RadioSelect)
    tipo_arquivo = forms.ModelChoiceField(
        label='Tipo de Arquivo',
        queryset=TipoArquivo.objects.all(),
        widget=AutocompleteWidget(search_fields=TipoArquivo.SEARCH_FIELDS),
        required=False,
    )
    justificativa_rejeicao = forms.CharField(
        widget=forms.Textarea,
        label='Justificativa Rejeição:',
        help_text='Descreva o porque da \
                                             imagem está sendo rejeitada.',
        required=False,
    )

    class Meta:
        model = Arquivo
        exclude = (
            'validado_em',
            'identificado_em',
            'nome',
            'pasta_arquivo',
            'status',
            'objeto',
            'content_type',
            'object_id',
            'id',
            'file',
            'processo_protocolo',
        )

    class Media:
        js = ('/static/arquivo/js/RejeitarArquivo.js',)


class ProtocolarArquivoForm(forms.ModelFormPlus):
    processo_protocolo = forms.ModelChoiceField(
        label='Protocolo',
        queryset=ProcessoProtocolo.objects,
        widget=AutocompleteWidget(search_fields=ProcessoProtocolo.SEARCH_FIELDS),
        required=False,
    )

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        if user.has_perms(['rh.eh_rh_sistemico', 'rh.eh_rh_campus']):
            self.fields['processo_protocolo'].queryset = ProcessoProtocolo.todos.all()

    class Meta:
        model = Arquivo
        fields = ('processo_protocolo',)


class FilterArquivosPorCampusForm(forms.FormPlus):
    campus = forms.ModelChoiceField(queryset=UnidadeOrganizacional.objects.suap().all(), label='Filtrar por Campus', required=False)


class ArquivoForm(forms.ModelFormPlus):
    class Meta:
        model = Arquivo
        exclude = ()


class ArquivoServidorForm(forms.FormPlus):
    servidor = forms.ModelChoiceField(
        queryset=Servidor.objects.all(), label='Selecione o Servidor', required=True, widget=AutocompleteWidget(search_fields=Servidor.SEARCH_FIELDS)
    )

    def clean_servidor(self):
        servidor = self.cleaned_data['servidor']
        if Servidor.objects.filter(id=servidor.id).exists():
            return servidor
        else:
            raise forms.ValidationError('O servidor não foi localizado.')


class ArquivoUploadForm(forms.FormPlus):
    MEGABYTE = 200
    arquivo = forms.AjaxFileUploadField('/arquivo/arquivos_upload/upload/', 'onCompleteUpload', sizeLimit=1024 * 1024 * MEGABYTE)

    def __init__(self, *args, **kwargs):
        servidor = kwargs.pop('servidor')
        super().__init__(*args, **kwargs)
        self.fields['arquivo'].widget.request = self.request
        self.fields['arquivo'].widget.params['servidor'] = servidor.matricula


class TipoArquivoForm(forms.ModelFormPlus):
    processo = forms.ModelChoiceField(
        queryset=Processo.objects.all(), label='Selecione o Processo', required=True, widget=AutocompleteWidget(search_fields=Processo.SEARCH_FIELDS)
    )

    class Meta:
        model = TipoArquivo
        exclude = ()
