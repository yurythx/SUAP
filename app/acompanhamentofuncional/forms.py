import datetime

from django.conf import settings

from acompanhamentofuncional.models import Ato, ServidorCessao, ServidorCessaoFrequencia, TipoAtoConfiguracao
from djtools import forms
from djtools.forms.widgets import AutocompleteWidget
from djtools.storages.utils import generate_filename
from rh.models import Instituicao, Servidor

##############################
# Cessão de Servidores
##############################


class ServidorCessaoForm(forms.ModelFormPlus):
    servidor_cedido = forms.ModelChoiceField(
        queryset=Servidor.objects, widget=AutocompleteWidget(search_fields=Servidor.SEARCH_FIELDS), label='Servidor Cedido'
    )
    instituicao_destino = forms.ModelChoiceField(
        queryset=Instituicao.objects, widget=AutocompleteWidget(search_fields=Instituicao.SEARCH_FIELDS), label='Instituição Destino'
    )

    if 'ponto' in settings.INSTALLED_APPS:
        from ponto.models import TipoAfastamento

        tipo_afastamento = forms.ModelChoiceField(
            queryset=TipoAfastamento.objects,
            widget=AutocompleteWidget(search_fields=TipoAfastamento.SEARCH_FIELDS),
            label='Tipo de Afastamento',
            required=False,
            help_text='Ponto SUAP: Tipo de Afastamento a partir do qual será criado um Afastamento a cada Frequência enviada.',
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        usuario_logado = self.request.user
        if not ServidorCessao.is_servidor_rh_sistemico(usuario_logado) and ServidorCessao.is_servidor_rh_campus(usuario_logado):
            usuario_logado_campus_sigla = usuario_logado.get_relacionamento().setor.uo.sigla
            self.fields['servidor_cedido'].queryset = Servidor.objects.filter(setor__uo__sigla=usuario_logado_campus_sigla)

    class Meta:
        model = ServidorCessao
        exclude = ('status_prazo',)


class ServidorCessaoArquivoFrequenciaForm(forms.ModelFormPlus):
    class Meta:
        model = ServidorCessaoFrequencia
        fields = ('data_inicial', 'data_final', 'arquivo')

    def clean_arquivo(self):
        arquivo = self.cleaned_data['arquivo']
        filename = generate_filename(
            parts=[self.instance.servidor_cessao.id, self.instance.data_envio, datetime.datetime.now()],
            file_obj=arquivo,
        )

        arquivo.name = filename

        return arquivo


##############################


class AtoAdicionarForm(forms.ModelFormPlus):
    class Meta:
        model = Ato
        exclude = ('situacao_envio', 'prazo_envio', 'data_envio', 'motivo_cancelamento')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        user_solicitante_campus_sigla = self.request.user.get_relacionamento().setor.uo.sigla
        self.fields['servidor'].queryset = Servidor.objects.filter(setor__uo__sigla=user_solicitante_campus_sigla)

    def clean(self):
        clean = super().clean()

        tipo_ato = self.cleaned_data.get('tipo')
        if tipo_ato:
            if not TipoAtoConfiguracao.get_ultima_configuracao(tipo_ato):
                self.add_error(
                    'tipo',
                    'O tipo de ato escolhido ainda não tem nenhuma configuração definida. '
                    "Acesse o menu 'Configuração de Tipos de Atos' para criar uma configuração.",
                )

        return clean

    def save(self, commit=True):
        self.instance.situacao_envio = Ato.SITUACAO_ENVIO_PENDENTE
        return super().save(commit)


class AtoEditarForm(forms.ModelFormPlus):
    class Meta:
        model = Ato
        exclude = ('tipo',)

    def clean(self):
        clean = super().clean()

        data_ocorrencia = self.cleaned_data.get('data_ocorrencia')
        situacao_envio = self.cleaned_data.get('situacao_envio')
        data_envio = self.cleaned_data.get('data_envio')
        motivo_cancelamento = self.cleaned_data.get('motivo_cancelamento')

        if situacao_envio != Ato.SITUACAO_ENVIO_ENVIADO and data_envio:
            self.add_error('data_envio', 'A data do envio é necessária apenas na situação de enviado.')

        if situacao_envio == Ato.SITUACAO_ENVIO_ENVIADO and not data_envio:
            self.add_error('data_envio', 'Na situação de enviado, a data do envio é obrigatória.')

        if situacao_envio != Ato.SITUACAO_ENVIO_CANCELADO and motivo_cancelamento:
            self.add_error('motivo_cancelamento', 'O motivo do cancelamento é necessário apenas na situação de cancelado.')

        if situacao_envio == Ato.SITUACAO_ENVIO_CANCELADO and not motivo_cancelamento:
            self.add_error('motivo_cancelamento', 'Na situação de cancelado, o motivo do cancelamento é obrigatório.')

        if situacao_envio == Ato.SITUACAO_ENVIO_ENVIADO and data_envio and data_envio < data_ocorrencia:
            self.add_error('data_envio', 'A data do envio não pode ser inferior à data de ocorrência.')

        return clean
