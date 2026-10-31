import json
import logging
from datetime import datetime

from django.conf import settings
from sentry_sdk import capture_exception

from catalogo_provedor_servico.models import RegistroNotificacaoGovBR, TemplateNotificaGovBR
from comum.models import APIExterna, Configuracao
from comum.services import APIExternaService
from djtools.utils import requests, send_mail

logger = logging.getLogger(__name__)


# (conexão, leitura) em segundos. A notificação é disparada dentro da requisição do atendente
# (executar/avaliar solicitação) e a falha já fica registrada para o reenvio do
# enviar_notificacoes_notifica_govbr: esperar o REQUESTS_TIMEOUT (60s) por chamada, com o
# Notifica lento, derrubava o worker antes de a resposta sair (#17521).
TIMEOUT_NOTIFICA_GOVBR = (5, 15)


class ApiNotificaGovBRService(APIExternaService):
    def __init__(self):
        super().__init__(APIExterna.NOTIFICA_GOVBR)

    def get_timeout(self) -> tuple[int, int]:
        return TIMEOUT_NOTIFICA_GOVBR

    def _execute_api_call(self, method, url_path, verbosity=False, **kwargs):
        """
        Método auxiliar para executar chamadas à API e padronizar o tratamento de resposta e exceções.
        Retorna (True, json_response) em caso de sucesso ou (False, error_dict) em caso de falha.
        """
        try:
            req_http = method(
                f'{self.api_externa.url_base}{url_path}',
                headers=self.get_headers(verbosity=verbosity),
                timeout=self.get_timeout(),
                verbosity=verbosity,
                API=self.api_externa.nome,
                **kwargs,
            )
            if req_http.ok:
                return True, req_http.json()
            else:
                return False, {'status': 'error', 'detail': req_http.text}
        except Exception as e:
            capture_exception(e)
            if verbosity:
                logger.info(f'API NOTIFICA_GOVBR Call Exception: {method.__name__.upper()} {self.api_externa.url_base}{url_path} - Exception: {e}')
            return False, {'status': 'error', 'detail': str(e)}

    def send_cpf_notification(self, cpf: str, id_template: str, parametrosTemplate: dict):
        """
        Envia notificação pela plataforma notifica
        O canal de notificação (APP do GovBR, SMS ou E-mail) é definido no cadastro dos templates em https://notifica.serpro.gov.br/
        """
        cpf_limpo = cpf.replace('.', '').replace('-', '')

        data = {
            'cpf': (None, cpf_limpo),
            'codigoTemplate': (None, id_template),
            'parametrosTemplate': (None, json.dumps(parametrosTemplate or {})),
        }

        return self._execute_api_call(requests.post, '/mensagens', files=data)

    def get_status_notification(self, codigoMensagem: str):
        """
        Obtem o status de uma  notificação pela plataforma notifica
        Exemplo de resposta:
        {
        "status": "SUCESSO",
        "dataEnvio": "2022-02-17T17:35:34.722156",
        "descricaoFalha": "CPF_DISPOSITIVO_NAO_VINCULADO"
        }
        """
        return self._execute_api_call(requests.get, f'/mensagens/{codigoMensagem}')

    def estah_acessivel(self, verbosity=False):
        """
        Verifica se a plataforma notifica está acessível
        """
        self.get_token()
        sucesso, _ = self.get_status_service(verbosity)
        return sucesso

    def get_status_service(self, verbosity=False):
        """
        Obtem o status do serviço da plataforma notifica
        Exemplo de resposta:
        {
          "versao": "v1.0.0"
        }
        """
        return self._execute_api_call(requests.get, '/status', verbosity=verbosity)

    def notificar_cidadao_via_notifica_govbr(
        self,
        solicitacao,
        mensagem_email=None,
        mensagem_sms=None,
        mensagem_app_govbr=None,
        assunto=None,
        dados_email=None,
        registro_notificacao=None,
        tipo_notificacao=None,
        variaveis=None,
    ):
        """
        Função utilizada para notificar cidadães através da Plataforma Notifica Gov.BR
        :param solicitacao: Solicitação que pertente a um cidadão com CPF (somente números) que será notificado
        :param mensagem_email: Se esse parametro for preenchido será enviado e-mail (cadastro Login único) para o cidadão
        :param mensagem_sms: Se esse parametro for preenchido será enviado sms (cadastro Login único) para o cidadão
        :param mensagem_govbr: Se é parametro for preenchido o cidadão será notificado no app Gov.BR
        :return:
        """
        cpf = solicitacao.cpf.replace('.', '').replace('-', '')
        email = ''
        if dados_email:
            for dado in dados_email:
                if dado['name'] == 'email' or dado['name'] == 'email_pessoal':
                    email = dado['value']
                    break
        else:
            if solicitacao.extra_dados:
                dados_email = json.loads(solicitacao.extra_dados)
                for chave, valor in dados_email.items():
                    if 'email' in chave or 'email_pessoal' in chave:
                        email = valor
                        break
        if not assunto:
            assunto = f'{Configuracao.get_valor_por_chave("comum", "instituicao")} - Notificação'
        api_externa = APIExterna.NOTIFICA_GOVBR
        if api_externa.ativo:
            data_envio = None
            api_service = api_externa.get_service()

            if mensagem_email:
                if email:
                    try:
                        send_mail(assunto=assunto, mensagem=mensagem_email, de=settings.DEFAULT_FROM_EMAIL, para=[email])
                        response_email = {'email': email, 'cpf': cpf, 'assunto': assunto, 'mensagem': mensagem_email}
                        email_enviado = True
                        data_envio = datetime.now()
                    except Exception as e:
                        email_enviado = False
                        response_email = {
                            'email': 'Erro ao tentar enviar email: {email}',
                            'cpf': cpf,
                            'assunto': assunto,
                            'mensagem': mensagem_email,
                            'exception': str(e),
                        }
                    RegistroNotificacaoGovBR.objects.create(
                        response_content=response_email,
                        solicitacao=solicitacao,
                        tipo=RegistroNotificacaoGovBR.EMAIL_SUAP,
                        data_envio=data_envio,
                        enviada=email_enviado,
                    )

            if api_service:
                if mensagem_sms:
                    try:
                        sms_enviado = False
                        id_template = (
                            TemplateNotificaGovBR.objects.filter(tipo_notificacao=tipo_notificacao, canal_notificacao=TemplateNotificaGovBR.SMS)
                            .first()
                            .id_template
                        )
                        sucesso, response_sms = api_service.send_cpf_notification(cpf=cpf, id_template=id_template, parametrosTemplate=variaveis)
                        if sucesso:
                            sms_enviado = True
                            data_envio = datetime.now()
                    except Exception as e:
                        response_sms = {'mensagem': f'Erro ao enviar mensagem {mensagem_sms}.', 'cpf': cpf, 'exception': str(e)}
                        sms_enviado = False

                    if registro_notificacao:
                        registro_notificacao.enviada = sms_enviado
                        registro_notificacao.data_envio = data_envio if sms_enviado else None
                        registro_notificacao.save()
                    else:
                        RegistroNotificacaoGovBR.objects.create(
                            mensagem=mensagem_sms,
                            response_content=response_sms,
                            solicitacao=solicitacao,
                            tipo=RegistroNotificacaoGovBR.SMS,
                            data_envio=data_envio,
                            enviada=sms_enviado,
                        )

                if mensagem_app_govbr:
                    try:
                        app_enviado = False
                        id_template = (
                            TemplateNotificaGovBR.objects.filter(tipo_notificacao=tipo_notificacao, canal_notificacao=TemplateNotificaGovBR.APP_GOVBR)
                            .first()
                            .id_template
                        )
                        sucesso, response_app_govbr = api_service.send_cpf_notification(
                            cpf=cpf, id_template=id_template, parametrosTemplate=variaveis
                        )
                        if sucesso:
                            app_enviado = True
                            data_envio = datetime.now()
                    except Exception as e:
                        response_app_govbr = {'mensagem': f'Erro ao enviar mensagem {mensagem_app_govbr}.', 'cpf': cpf, 'exception': str(e)}
                        app_enviado = False

                    if registro_notificacao:
                        registro_notificacao.enviada = app_enviado
                        registro_notificacao.data_envio = data_envio if app_enviado else None
                        registro_notificacao.save()
                    else:
                        RegistroNotificacaoGovBR.objects.create(
                            mensagem=mensagem_app_govbr,
                            response_content=response_app_govbr,
                            solicitacao=solicitacao,
                            tipo=RegistroNotificacaoGovBR.APP,
                            data_envio=data_envio,
                            enviada=app_enviado,
                        )
        else:
            if mensagem_email:
                if email:
                    try:
                        send_mail(assunto=assunto, mensagem=mensagem_email, de=settings.DEFAULT_FROM_EMAIL, para=[email])
                        response_email = {'email': email, 'cpf': cpf, 'assunto': assunto, 'mensagem': mensagem_email}
                        email_enviado = True
                        data_envio = datetime.now()
                    except Exception as e:
                        email_enviado = False
                        response_email = {
                            'email': 'Erro ao tentar enviar email: {email}',
                            'cpf': cpf,
                            'assunto': assunto,
                            'mensagem': mensagem_email,
                            'exception': str(e),
                        }
                    RegistroNotificacaoGovBR.objects.create(
                        response_content=response_email,
                        solicitacao=solicitacao,
                        tipo=RegistroNotificacaoGovBR.EMAIL_SUAP,
                        data_envio=data_envio,
                        enviada=email_enviado,
                    )
