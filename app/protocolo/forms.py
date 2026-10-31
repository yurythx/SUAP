from datetime import datetime

from comum.models import Vinculo
from comum.utils import get_setor
from djtools import forms
from djtools.forms import ReCaptchaField
from djtools.forms.fields import BrCpfCnpjField
from djtools.forms.widgets import AutocompleteWidget, BRCpfCnpjWidget
from protocolo.models import Processo, Tramite
from rh.models import Setor


class ConfiguracaoForm(forms.FormPlus):
    tempo_tramite_mesmo_campus = forms.IntegerField(label='Tempo de trâmite no mesmo campus', help_text='Tempo em horas', required=False)
    tempo_tramite_diferentes_campi = forms.IntegerField(label='Tempo de trâmite entre diferentes campi', help_text='Tempo em horas', required=False)
    tempo_analise = forms.IntegerField(label='Tempo de análise', help_text='Tempo em horas', required=False)
    url_consulta_publica = forms.URLField(label='URL para consulta pública', help_text='URL', required=False)
    setores_sei = forms.CharField(
        label='Setores SEI',
        help_text='JSON contendo o mapeamento dos setores do SEI com o SUAP para fins de importação de processos. Execute o comando "python manage.py importar_sei" para que esse campo nessa inicializado.',
        widget=forms.Textarea(),
        required=False,
    )
    habilitar_importacao_sei = forms.BooleanField(
        label='Habilitar a importação do SEI?',
        help_text='Habilita a importação do SEI através do comando "python manage.py importar_sei" pelo sync_suap.',
        required=False,
    )
    sei_endereco_banco = forms.CharField(label='SEI - Endereço da base de dados', required=False)
    sei_usuario_banco = forms.CharField(label='SEI - Nome do usuário na base de dados', required=False)
    sei_senha_banco = forms.CharField(label='SEI - Senha da base de dados', required=False)
    sei_nome_banco = forms.CharField(label='SEI - Nome da base de dados', required=False)
    habilitar_cadastro_manual = forms.BooleanField(label='Habilitar cadastro manual de processos físicos?', required=False)


class ProcessoFormCadastrarComTramite(forms.ModelFormPlus):
    tipo_encaminhamento_primeira_tramitacao = forms.ChoiceField(
        required=False,
        label='Primeiro Trâmite',
        choices=[('nenhum', 'Nenhum'), ('interno', 'Órgão Interno (setor)'), ('externo', 'Órgão Externo')],
        initial='interno',
    )

    class Meta:
        model = Processo
        fields = (
            'interessado_nome',
            'interessado_documento',
            'interessado_pf',
            'interessado_email',
            'interessado_telefone',
            'numero_documento',
            'assunto',
            'tipo',
            'palavras_chave',
        )


class TramiteFormReceber(forms.ModelFormPlus):
    SUBMIT_LABEL = 'Receber'
    EXTRA_BUTTONS = [
        {'value': 'Receber e Encaminhar', 'name': 'receber_e_encaminhar'},
        {'value': 'Receber e Finalizar', 'name': 'receber_e_finalizar'},
    ]

    class Meta:
        model = Tramite
        fields = ['observacao_recebimento']

    def save(self):
        tramite = self.instance
        tramite.data_recebimento = datetime.today()
        tramite.vinculo_recebimento = self.request.user.get_vinculo()
        tramite.observacao_recebimento = self.cleaned_data['observacao_recebimento']
        tramite.save()


class TramiteFormEncaminhar(forms.ModelFormPlus):
    processo = forms.ModelChoiceField(
        label='Processo', queryset=Processo.objects, widget=AutocompleteWidget(search_fields=Processo.SEARCH_FIELDS, readonly=True), required=True
    )
    orgao_interno_recebimento = forms.ModelChoiceField(
        label='Setor de Destino', queryset=Setor.objects, required=False, widget=AutocompleteWidget(search_fields=Setor.SEARCH_FIELDS)
    )

    class Meta:
        model = Tramite
        fields = ['processo', 'observacao_encaminhamento', 'orgao_interno_recebimento']

    class Media:
        js = ('/static/protocolo/js/TramiteFormEncaminhar.js',)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.processo = self.instance.processo
        self.fields['orgao_interno_recebimento'].queryset = Setor.objects.suap_ativos().all()
        # self.fields['orgao_interno_recebimento_arvore'].queryset = Setor.objects.suap_ativos().all()
        self.fields['processo'].initial = self.processo

    def save(self):
        tramite = self.instance
        # Dados de quem está fazendo o encaminhamento.
        tramite.vinculo_encaminhamento = self.request.user.get_vinculo()
        tramite.data_encaminhamento = datetime.now()
        tramite.observacao_encaminhamento = self.cleaned_data['observacao_encaminhamento']
        tramite.save()

    def clean(self):
        if 'orgao_interno_recebimento' in self.cleaned_data:
            setor_indicado = self.cleaned_data.get('orgao_interno_recebimento')
            if not setor_indicado:
                self._errors['orgao_interno_recebimento'] = forms.ValidationError(['É obrigatório informar um setor de destino para o processo.'])
            elif setor_indicado in Setor.get_setores_vazios():
                self._errors['orgao_interno_recebimento'] = forms.ValidationError(
                    [f'O setor {setor_indicado} não tem ninguém cadastrado para receber o processo.']
                )


class TramiteFormEncaminharExternamente(forms.ModelFormPlus):
    processo = forms.ModelChoiceField(
        label='Processo', queryset=Processo.objects, widget=AutocompleteWidget(search_fields=Processo.SEARCH_FIELDS, readonly=True), required=True
    )

    class Meta:
        model = Tramite
        fields = ['processo', 'observacao_encaminhamento', 'orgao_vinculo_externo_recebimento']

    orgao_vinculo_externo_recebimento = forms.ModelChoiceField(
        label='Órgão externo de destino', queryset=Vinculo.objects.pessoas_juridicas(), widget=AutocompleteWidget(search_fields=Vinculo.SEARCH_FIELDS)
    )

    def save(self):
        tramite = self.instance

        # Dados de quem está fazendo o encaminhamento.
        tramite.vinculo_encaminhamento = self.request.user.get_vinculo()
        tramite.data_encaminhamento = datetime.now()
        tramite.observacao_encaminhamento = self.cleaned_data['observacao_encaminhamento']

        # Setor de destino do encaminhamento.
        tramite.orgao_vinculo_externo_recebimento = self.cleaned_data['orgao_vinculo_externo_recebimento']
        tramite.save()


def TramiteFormEncaminharFactory(tramite, request_method=None, request=None):
    if tramite.tipo_encaminhamento == Tramite.TIPO_ENCAMINHAMENTO_INTERNO:
        return TramiteFormEncaminhar(data=request_method, instance=tramite, request=request)
    elif tramite.tipo_encaminhamento == Tramite.TIPO_ENCAMINHAMENTO_EXTERNO:
        return TramiteFormEncaminharExternamente(data=request_method, instance=tramite, request=request)


class TramiteFormInformarRecebimentoExterno(forms.ModelFormPlus):
    class Meta:
        model = Tramite
        fields = ['vinculo_recebimento', 'data_recebimento', 'observacao_recebimento']

    vinculo_recebimento = forms.ModelChoiceField(
        label='Orgão externo - Pessoa que recebeu o processo',
        queryset=Vinculo.objects.funcionarios(),
        widget=AutocompleteWidget(search_fields=Vinculo.SEARCH_FIELDS),
    )

    data_recebimento = forms.DateFieldPlus(label='Orgão externo - Data recebimento')

    observacao_recebimento = forms.CharField(label='Orgão externo - Despacho', widget=forms.Textarea(), required=False)

    def save(self):
        tramite = self.instance
        # Dados de quem está fazendo o encaminhamento.
        tramite.vinculo_recebimento = self.cleaned_data['vinculo_recebimento']
        tramite.data_recebimento = self.cleaned_data['data_recebimento']
        tramite.observacao_recebimento = self.cleaned_data['observacao_recebimento']
        tramite.save()


class TramiteFormRetornarProcessoParaAmbitoInterno(forms.ModelFormPlus):
    class Meta:
        model = Tramite
        fields = ['orgao_vinculo_externo_encaminhamento', 'vinculo_encaminhamento', 'observacao_encaminhamento', 'observacao_recebimento']

    orgao_vinculo_externo_encaminhamento = forms.ModelChoiceField(
        label='Órgão externo - Origem do encaminhamento',
        queryset=Vinculo.objects.pessoas_juridicas(),
        widget=AutocompleteWidget(search_fields=Vinculo.SEARCH_FIELDS),
    )

    vinculo_encaminhamento = forms.ModelChoiceField(
        label='Órgão externo - Pessoa que enviou o processo',
        queryset=Vinculo.objects.funcionarios(),
        widget=AutocompleteWidget(search_fields=Vinculo.SEARCH_FIELDS),
    )

    observacao_encaminhamento = forms.CharField(label='Orgão externo - Despacho', widget=forms.Textarea(), required=False)
    observacao_recebimento = forms.CharField(label='Despacho de recebimento', widget=forms.Textarea(), required=False)

    def save(self):
        tramite = self.instance

        # Informações capturadas automaticamente.
        tramite.data_recebimento = datetime.today()
        tramite.orgao_interno_recebimento = get_setor()
        tramite.vinculo_recebimento = self.request.user.get_vinculo()

        # Informações explicitamente dadas pelo operador.
        tramite.orgao_vinculo_externo_encaminhamento = self.cleaned_data['orgao_vinculo_externo_encaminhamento']
        tramite.vinculo_encaminhamento = self.cleaned_data['vinculo_encaminhamento']
        tramite.observacao_encaminhamento = self.cleaned_data['observacao_encaminhamento']
        tramite.observacao_recebimento = self.cleaned_data['observacao_recebimento']

        tramite.save()


class ProcessoFormFinalizar(forms.ModelFormPlus):
    class Meta:
        model = Processo
        fields = ['observacao_finalizacao']

    def save(self):
        processo = self.instance
        processo.data_finalizacao = datetime.today()
        processo.vinculo_finalizacao = self.request.user.get_vinculo()
        processo.observacao_finalizacao = self.cleaned_data['observacao_finalizacao']
        processo.status = Processo.STATUS_FINALIZADO
        processo.save()


class ProtocoloForm(forms.FormPlus):
    numero_processo = forms.CharField(
        label='Nº Processo',
        help_text='(Informe o número do processo completo, com ponto e traço)',
        widget=forms.TextInput(attrs={'size': '25'}),
        max_length=25,
        required=True,
    )

    documento = BrCpfCnpjField(label='CPF / CNPJ', widget=BRCpfCnpjWidget, required=True)

    recaptcha = ReCaptchaField(label='')
