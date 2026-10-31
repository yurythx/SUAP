from comum.models import Configuracao, User
from djtools import forms
from djtools.forms.widgets import AutocompleteWidget
from processo_eletronico.models import TipoProcesso
from rh.models import Setor

from .models import HipoteseLegalPEN, MapeamentoTiposDocumento, TipoDocumentoPEN


class ConfiguracaoForm(forms.FormPlus):
    setor_recebimento_pen = forms.ModelChoiceFieldPlus(
        Setor.objects,
        label='Sigla do Setor Base para Recebimento de Trâmites Externos',
        required=False,
    )
    urlProducaoWS_pen = forms.CharFieldPlus(
        label='URL de Produção do WS (REST)', help_text='https://homolog.pen.api.trafficmanager.net/interoperabilidade/rest/v2', required=False
    )
    pathCertificadoPublico_pen = forms.CharFieldPlus(
        label='Caminho do Certificado Digital (.pem, .cer)', help_text='/opt/certs/cert.pem', required=False
    )
    pathCertificadoPrivado_pen = forms.CharFieldPlus(label='Caminho do Certificado Digital (privkey.pem, .key)', required=False)
    senhaWS_pen = forms.CharFieldPlus(label='Senha de Produção do WS', required=False)
    maximoTentativasReceb_pen = forms.IntegerFieldPlus(label='Máximo de Tentativas de Recebimento', help_text='3', required=False)
    tamanhoMaximoDocumento_pen = forms.IntegerFieldPlus(label='Tamanho máximo de documento para envio', help_text='Tamanho em MB', required=False)
    tipo_processo_recebimento_pen = forms.ModelChoiceFieldPlus(
        TipoProcesso.objects.all(),
        label='Tipo de Processo para Recebimento de Trâmites Externos',
        help_text='Ex: Demanda Externa: Outros Órgãos Públicos',
        required=False,
    )
    usuario_recebimento_pen = forms.ModelChoiceFieldPlus(
        User.objects.filter(is_active=True),
        widget=AutocompleteWidget(search_fields=User.SEARCH_FIELDS),
        label='Usuário Responsável pelos Processos Recebidos do Barramento',
        help_text='Usuário registrado como responsável pelos processos recebidos automaticamente do barramento (rotina agendada). '
        'Sem ele, os trâmites recebidos ficam pendentes.',
        required=False,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields[
            'setor_recebimento_pen'
        ].help_text = f'Os trâmites enviados para o {Configuracao.get_valor_por_chave("comum", "instituicao_sigla")} que não forem entregues corretamente ao destinatário indicado serão direcionados a este setor.'


class TipoDocumentoPENForm(forms.ModelFormPlus):
    class Meta:
        model = TipoDocumentoPEN
        fields = ('id_tipo_doc_pen', 'nome', 'observacao')


class MapeamentoTiposDocumentoForm(forms.ModelFormPlus):
    tipo_doc_barramento_pen = forms.ModelChoiceFieldPlus(
        queryset=TipoDocumentoPEN.objects, required=True, widget=AutocompleteWidget(), label='Tipo Documento Barramento PEN'
    )

    class Meta:
        model = MapeamentoTiposDocumento
        fields = ('tipo_doc_barramento_pen', 'tipo_doc_suap', 'tipo_para_recebimento_suap')


class HipoteseLegalPadraoPENForm(forms.FormPlus):
    hipotese = forms.ModelChoiceField(
        queryset=HipoteseLegalPEN.objects.exclude(hipotese_padrao=True),
        label='Selecione a Hipótese Padrão',
        required=True,
        widget=AutocompleteWidget(),
    )
