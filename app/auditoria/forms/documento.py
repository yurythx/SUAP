from django.conf import settings
from django.forms import ValidationError

from auditoria.papeis import get_auditores_ativos
from comum.models import Configuracao, Vinculo
from comum.utils import get_setor
from djtools import forms
from djtools.forms.widgets import AutocompleteWidget
from djtools.utils import full_check_file, get_datetime_now
from documento_eletronico.models import DocumentoDigitalizado, TipoDocumento
from rh.models import Setor


class DocumentoDigitalizadoForm(forms.ModelFormPlus):
    identificador_numero = forms.IntegerFieldPlus(label='Identificador/Número')
    identificador_ano = forms.IntegerFieldPlus(label='Ano')
    tipo = forms.ModelPopupChoiceField(TipoDocumento.objects, label='Tipo', required=True)
    setor_dono = forms.ModelChoiceFieldPlus2(Setor.objects.suap_ativos().none(), label='Setor Dono', widget=AutocompleteWidget(readonly='readonly'))
    dono_documento = forms.ModelChoiceFieldPlus(
        Vinculo.objects.none(),
        label='Responsável pelo Documento',
        required=True,
        help_text='Deve ser informada um auditor.',
        widget=AutocompleteWidget(search_fields=Vinculo.SEARCH_FIELDS),
    )
    fieldsets = (
        (
            'Dados do Documento',
            {'fields': ('arquivo', 'tipo_conferencia', 'tipo', 'assunto', ('setor_dono', 'dono_documento'))},
        ),
        (
            'Dados Adicionais',
            {'fields': (('identificador_numero', 'identificador_ano'), 'identificador_setor_sigla', 'identificador_tipo_documento_sigla')},
        ),
    )

    class Meta:
        model = DocumentoDigitalizado
        fields = (
            'identificador_tipo_documento_sigla',
            'identificador_numero',
            'identificador_ano',
            'identificador_setor_sigla',
            'assunto',
            'arquivo',
            'tipo',
            'setor_dono',
            'dono_documento',
            'tipo_conferencia',
        )

    def __init__(self, *args, **kwargs):
        self.request = kwargs.get('request')
        user = self.request.user
        super().__init__(*args, **kwargs)
        self.max_file_upload_size = settings.PROCESSO_ELETRONICO_DOCUMENTO_EXTERNO_MAX_UPLOAD_SIZE
        self.tamanho_maximo_upload_personalizado = Configuracao.get_valor_por_chave(
            app='processo_eletronico', chave='tamanho_maximo_upload_personalizado'
        )
        #
        setor_user = get_setor(user)
        qs_setores = Setor.objects.suap_ativos().filter(pk=setor_user.id)
        self.fields['setor_dono'].queryset = qs_setores
        self.fields['setor_dono'].initial = setor_user.id
        self.fields['setor_dono'].widget.attrs['readonly'] = True

        self.fields['dono_documento'].initial = user.get_vinculo()
        self.fields['dono_documento'].queryset = get_auditores_ativos()

    def clean_arquivo(self):
        content = self.cleaned_data.get('arquivo', None)
        full_check_file(content)
        return content

    def save(self, commit=True):
        try:
            self.instance.setor_dono = self.cleaned_data['setor_dono']
            self.instance.data_ultima_modificacao = get_datetime_now()
            self.instance.usuario_ultima_modificacao = self.request.user
            documento = super().save(False)
            if documento.id:
                documento.data_alteracao = get_datetime_now()
                documento.usuario_alteracao = self.request.user
            else:
                documento.usuario_criacao = self.request.user
            #
            return super().save(commit=commit)
        except Exception as e:
            raise ValidationError(f'{e}')


class ManifestacaoDocumentoDigitalizadoForm(DocumentoDigitalizadoForm):
    dono_documento = forms.ModelChoiceFieldPlus(
        Vinculo.objects.none(),
        label='Responsável pelo Documento',
        required=True,
        widget=AutocompleteWidget(search_fields=Vinculo.SEARCH_FIELDS),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['dono_documento'].queryset = Vinculo.objects.servidores()
