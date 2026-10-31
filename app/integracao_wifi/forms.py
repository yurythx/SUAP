import datetime

from tinymce.widgets import TinyMCE

from django.conf import settings
from requests import ConnectionError

from comum.models import Configuracao, User, Vinculo
from djtools import forms
from djtools.forms import AutocompleteWidget
from djtools.utils import requests
from integracao_wifi.models import AutorizacaoDispositivo, TokenWifi


class ConfiguracaoForm(forms.FormPlus):
    url_api_wifrn_iot = forms.URLField(label='URL da API de Autorização dos Dispositivos', help_text='Ex: http://iot.ifrn.edu.br', required=False)
    qtd_maximas_dispositivos_por_usuario = forms.IntegerFieldPlus(label='Quantidade Máxima de Dispositivos por Usuário', required=False)
    qtd_maxima_dias_autorizacao = forms.IntegerFieldPlus(label='Quantidade Máxima de Dias de Autorização dos Dispositivos', required=False)
    qtd_maxima_dias_autorizacao_expandido = forms.IntegerFieldPlus(
        label='Quantidade Máxima de Dias de Autorização dos Dispositivos Expandido', required=False
    )
    texto_politica_utilizacao = forms.CharField(
        label='Política de Utilização da Rede wIFRN-IoT',
        widget=TinyMCE(attrs={'class': 'tinymce', 'style': 'width: 100%;  min-height: 600px;'}),
        required=False,
    )

    solucao_wifi = forms.ChoiceField(label='Solução de WiFi', required=False, initial='ruckus', choices=(('ruckus', 'Ruckus'),))
    url_wifi = forms.URLField(label='URL de acesso ao WiFi', required=False)
    usuario_wifi = forms.CharField(label='Usuário de acesso ao WiFi', required=False)
    senha_wifi = forms.CharField(label='Senha de acesso ao WiFi', required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields[
            'texto_politica_utilizacao'
        ].label = f'Política de Utilização da Rede w{Configuracao.get_valor_por_chave("comum", "instituicao_sigla")}-IoT'
        sigla = Configuracao.get_valor_por_chave('comum', 'instituicao_sigla')
        if sigla:
            self.fields['url_api_wifrn_iot'].help_text = f'Ex: http://iot.{sigla.lower()}.edu.br'


class RenovacaoAutorizacaoDispositivoForm(forms.ModelFormPlus):
    def clean_data_validade_autorizacao(self):
        qtd_maxima_dias_autorizacao = Configuracao.get_valor_por_chave('integracao_wifi', 'qtd_maxima_dias_autorizacao')
        data_validade_autorizacao = self.cleaned_data.get('data_validade_autorizacao')
        if datetime.date.today() > data_validade_autorizacao:
            raise forms.ValidationError('A Data e Hora de Validade da Autorização não pode ser menor que a data de hoje.')

        if (data_validade_autorizacao - datetime.date.today()).days > int(qtd_maxima_dias_autorizacao):
            raise forms.ValidationError(f'A Data e Hora de Validade da Autorização não pode ser maior que {qtd_maxima_dias_autorizacao} dias.')

        return data_validade_autorizacao

    def save(self, *args, **kwargs):
        self.instance.renovar_autorizacao(self.instance.data_validade_autorizacao)
        return super().save(*args, **kwargs)

    class Meta:
        model = AutorizacaoDispositivo
        fields = ('data_validade_autorizacao',)


class AutorizacaoDispositivoForm(forms.ModelFormPlus):
    vinculo_solicitante = forms.ModelChoiceFieldPlus(
        queryset=Vinculo.objects.all(), widget=AutocompleteWidget(search_fields=Vinculo.SEARCH_FIELDS), label='Solicitante'
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Se não pertencer ao grupo Administradores de Dispositivos IoT, o solicitante é o próprio usuário logado
        if not self.request.user.has_perm('integracao_wifi.eh_administrador_iot'):
            self.fields['vinculo_solicitante'].queryset = Vinculo.objects.filter(pk=self.request.user.get_vinculo().pk)

        self.fields['vinculo_solicitante'].initial = self.request.user.get_vinculo().pk

    def clean_data_validade_autorizacao(self):
        vinculo_solicitante = self.cleaned_data.get('vinculo_solicitante')
        qtd_maxima_dias_autorizacao_normal = Configuracao.get_valor_por_chave('integracao_wifi', 'qtd_maxima_dias_autorizacao')
        qtd_maxima_dias_autorizacao_expandido = Configuracao.get_valor_por_chave('integracao_wifi', 'qtd_maxima_dias_autorizacao_expandido')

        data_validade_autorizacao = self.cleaned_data.get('data_validade_autorizacao')

        user_in_grupo_prazo_expandido_iot = vinculo_solicitante.user.has_perm('integracao_wifi.pode_escolher_prazo_extendido_iot')

        if user_in_grupo_prazo_expandido_iot:
            qtd_maxima_dias_autorizacao = int(qtd_maxima_dias_autorizacao_expandido) if qtd_maxima_dias_autorizacao_expandido else 365
        else:
            qtd_maxima_dias_autorizacao = int(qtd_maxima_dias_autorizacao_normal)

        if datetime.date.today() > data_validade_autorizacao:
            raise forms.ValidationError('A Data e Hora de Validade da Autorização não pode ser menor que a data de hoje.')

        if (data_validade_autorizacao - datetime.date.today()).days > int(qtd_maxima_dias_autorizacao):
            raise forms.ValidationError(f'A Data e Hora de Validade da Autorização não pode ser maior que {qtd_maxima_dias_autorizacao} dias.')

        return data_validade_autorizacao

    def clean_endereco_mac_dispositivo(self):
        # Validando no banco de dados do SUAP
        endereco_mac_dispositivo = self.cleaned_data.get('endereco_mac_dispositivo')
        endereco_mac_dispositivo.lower().replace('-', '').replace(':', '').replace('.', '')
        qs = AutorizacaoDispositivo.objects.exclude(pk=self.instance.pk).filter(endereco_mac_dispositivo=endereco_mac_dispositivo, expirada=False)
        if qs.exists():
            raise forms.ValidationError(f'O Endereço MAC informado já foi cadastrado pelo usuário "{qs[0].vinculo_solicitante}".')

        # Validando na API do Radius
        if not self.instance.pk:
            url_api_wifrn_iot = Configuracao.get_valor_por_chave('integracao_wifi', 'url_api_wifrn_iot')
            if not url_api_wifrn_iot:
                raise forms.ValidationError('A URL da API do Radius não foi configurada.')

            try:
                retorno = requests.get(f'{url_api_wifrn_iot}/consultar_dispositivo/{endereco_mac_dispositivo}/', timeout=settings.REQUESTS_TIMEOUT)
                if retorno.status_code == 200:
                    raise forms.ValidationError('O Endereço MAC informado já está autorizado no Radius.')
            except ConnectionError:
                raise forms.ValidationError('Não foi possível conectar-se com a API do Radius.')

        return endereco_mac_dispositivo

    def save(self, *args, **kwargs):
        try:
            url_api_wifrn_iot = Configuracao.get_valor_por_chave('integracao_wifi', 'url_api_wifrn_iot')
            endereco_mac_dispositivo = self.cleaned_data.get('endereco_mac_dispositivo').lower().replace('-', '').replace(':', '').replace('.', '')
            data = {'username': endereco_mac_dispositivo, 'attribute': 'Cleartext-Password', 'op': ':=', 'value': endereco_mac_dispositivo}

            if not self.instance.pk:
                # Realizando a Autorização do dispositivo na API do Radius
                retorno = self.autorizar_dispositivo(url_api_wifrn_iot, data)
                if not retorno:
                    raise Exception('Erro ao tentar autorizar dispositivo.')
            else:
                obj_antigo = AutorizacaoDispositivo.objects.get(pk=self.instance.pk)

                if obj_antigo.endereco_mac_dispositivo != endereco_mac_dispositivo:
                    if self.desautorizar_dispositivo(url_api_wifrn_iot, obj_antigo.endereco_mac_dispositivo):
                        # Realizando a Autorização do dispositivo na API do Radius
                        retorno = self.autorizar_dispositivo(url_api_wifrn_iot, data)
                        if not retorno:
                            raise Exception('Erro ao tentar autorizar dispositivo.')

            return super().save(*args, **kwargs)
        except ConnectionError:
            raise forms.ValidationError('Não foi possível conectar-se com a API do Radius.')
        except Exception:
            raise forms.ValidationError('Erro ao tentar autorizar dispositivo.')

    def autorizar_dispositivo(self, url, data):
        retorno = requests.post(f'{url}/autorizar_dispositivo/', data=data, timeout=settings.REQUESTS_TIMEOUT)
        return retorno.status_code == 201

    def desautorizar_dispositivo(self, url, endereco_mac):
        retorno = requests.delete(f'{url}/desautorizar_dispositivo/{endereco_mac}/', timeout=settings.REQUESTS_TIMEOUT)
        return retorno.status_code == 204

    class Meta:
        model = AutorizacaoDispositivo
        exclude = ('data_hora_solicitacao', 'expirada', 'excluida')


class GerarTokensWifiForm(forms.FormPlus):
    usuario_solicitante = forms.ModelChoiceFieldPlus(User.objects.all(), label='Solicitante')
    data_solicitacao = forms.DateFieldPlus(label='Data da Solicitação')
    validade = forms.IntegerField(label='Validade em Dias')

    identificacao = forms.CharField(
        label='Identificação',
        widget=forms.Textarea(),
        help_text='Informe, em cada linha, o nome ou e-mail das pessoas que receberão o token de acesso.',
    )

    fieldsets = (
        ('Dados da Solicitação', {'fields': ('usuario_solicitante',)}),
        ('Validade', {'fields': (('data_solicitacao', 'validade'),)}),
        ('Chave', {'fields': ('identificacao',)}),
    )

    def clean_validade(self):
        validade = self.cleaned_data['validade']
        if validade < 0:
            raise forms.ValidationError('A validade deve ser maior que zero.')
        if validade > 180:
            raise forms.ValidationError('A validade deve ser menor que 180.')
        return validade

    def processar(self):
        from integracao_wifi.utils import get_chave_wifi

        tokens = []
        for identificacao in self.cleaned_data['identificacao'].split('\n'):
            identificacao = identificacao.strip()
            chave = get_chave_wifi(identificacao)
            tokens.append((identificacao, chave))
            if chave != 'ERRO AO GERAR CHAVE':
                token = TokenWifi()
                token.identificacao = identificacao
                token.usuario_resposavel = self.request.user
                token.usuario_solicitante = self.cleaned_data['usuario_solicitante']
                token.data_solicitacao = self.cleaned_data['data_solicitacao']
                token.validade = self.cleaned_data['validade']
                token.chave = chave
                token.save()
        return tokens
