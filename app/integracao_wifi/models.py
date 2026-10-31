from django.conf import settings
from django.core.exceptions import ValidationError
from requests import ConnectionError

from comum.models import Configuracao
from djtools.db import models
from djtools.utils import requests


class AutorizacaoDispositivo(models.ModelPlus):
    vinculo_solicitante = models.ForeignKeyPlus('comum.Vinculo', verbose_name='Solicitante')
    localizacao_dispositivo = models.ForeignKeyPlus('comum.Sala', verbose_name='Localização do Dispositivo', blank=True, null=True)
    nome_dispositivo = models.CharFieldPlus(verbose_name='Nome do Dispositivo')
    endereco_mac_dispositivo = models.CharFieldPlus(
        verbose_name='Endereço MAC do Dispositivo', max_length=12, help_text='O Endereço MAC deve ser informado no formato "0010FA6E384A".'
    )
    data_hora_solicitacao = models.DateTimeFieldPlus(auto_now_add=True, verbose_name='Data e Hora da Solicitação')
    data_validade_autorizacao = models.DateFieldPlus(verbose_name='Data de Validade da Autorização')
    expirada = models.BooleanField(default=False, verbose_name='Expirada')
    excluida = models.BooleanField(default=False, verbose_name='Cancelada')

    class Meta:
        verbose_name = 'Autorização de Dispositivo IoT'
        verbose_name_plural = 'Autorizações de Dispositivo IoT'
        permissions = (
            ('pode_escolher_prazo_extendido_iot', 'Pode escolher prazo extendido e quantidade dispositivos ilimitado'),
            ('eh_administrador_iot', 'É administrador dos dispositivos IOT'),
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._endereco_mac_dispositivo = self.endereco_mac_dispositivo

    def delete(self, *args, **kwargs):
        self.desautorizar_dispositivo()
        return super().delete(*args, **kwargs)

    def save(self, *args, **kwargs):
        try:
            # Tratando o formato inserido no formulário para o exigido pelo Radius
            self.endereco_mac_dispositivo = self.endereco_mac_dispositivo.lower().replace('-', '')
            self.endereco_mac_dispositivo = self.endereco_mac_dispositivo.replace(':', '').replace('.', '')

            if not self.pk:
                # Realizando a Autorização do dispositivo na API do Radius
                self.autorizar_dispositivo()
            else:
                if self._endereco_mac_dispositivo != self.endereco_mac_dispositivo:
                    if self.desautorizar_dispositivo():
                        # Realizando a Autorização do dispositivo na API do Radius
                        self.autorizar_dispositivo()
        except ConnectionError:
            raise ValidationError('Não foi possível conectar-se com a API do Radius.')

        return super().save(*args, **kwargs)

    def renovar_autorizacao(self, data_validade):
        self.autorizar_dispositivo()
        self.expirada = False
        self.data_validade_autorizacao = data_validade
        self.save()

    def revogar_autorizacao(self):
        self.desautorizar_dispositivo()
        self.expirada = True
        self.save()

    def cancelar_autorizacao(self):
        self.revogar_autorizacao()
        self.excluida = True
        self.save()

    def autorizar_dispositivo(self):
        url = Configuracao.get_valor_por_chave('integracao_wifi', 'url_api_wifrn_iot')
        data = {'username': self.endereco_mac_dispositivo, 'attribute': 'Cleartext-Password', 'op': ':=', 'value': self.endereco_mac_dispositivo}
        retorno = requests.post(f'{url}/autorizar_dispositivo/', data=data, timeout=settings.REQUESTS_TIMEOUT)
        return retorno.status_code == 201

    def desautorizar_dispositivo(self):
        url = Configuracao.get_valor_por_chave('integracao_wifi', 'url_api_wifrn_iot')
        retorno = requests.delete(f'{url}/desautorizar_dispositivo/{self.endereco_mac_dispositivo}/', timeout=settings.REQUESTS_TIMEOUT)
        return retorno.status_code == 204


class TokenWifi(models.ModelPlus):
    cadastrado_por = models.CurrentUserField(verbose_name='Cadastrado Por', related_name='tokenwifiresponsavel_set')
    usuario_solicitante = models.ForeignKeyPlus('comum.User', verbose_name='Solicitante', null=True)
    data_solicitacao = models.DateFieldPlus(verbose_name='Data da Solicitação')
    validade = models.IntegerField(verbose_name='Validade em Dias')

    identificacao = models.CharFieldPlus(verbose_name='Identificação')
    chave = models.CharFieldPlus(verbose_name='Valor')

    class Meta:
        verbose_name = 'Token Wifi'
        verbose_name_plural = 'Tokens Wifi'

    def save(self, *args, **kwargs):
        if not self.chave:
            from integracao_wifi.utils import get_chave_wifi

            self.chave = get_chave_wifi(self.identificacao)
        super().save(*args, **kwargs)
