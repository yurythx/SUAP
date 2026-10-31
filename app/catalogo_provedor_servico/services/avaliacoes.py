import logging
from datetime import datetime

from django.conf import settings

from catalogo_provedor_servico.models import RegistroAvaliacaoGovBR
from comum.models import APIExterna, Configuracao
from comum.services import APIExternaService
from djtools.utils import requests

logger = logging.getLogger(__name__)


class ApiAvaliacaoGovBRService(APIExternaService):
    def __init__(self):
        super().__init__(APIExterna.AVALIACAO_GOVBR)

    def get_orgao_id(self):
        return int(Configuracao.get_valor_por_chave('catalogo_provedor_servico', 'orgao_id_portal_servicos_govbr') or 0)

    def estah_acessivel(self, verbosity=False):
        """
        Verifica se a plataforma de avaliações está acessível
        """
        payload = {
            'paginaAtual': '0',
        }
        url = self.api_externa.url_base + 'porServico'
        # url = 'https://h-avaliacao-govbrapi.np.estaleiro.serpro.gov.br/api/avaliacao/porServico'
        r = requests.get(
            url,
            headers=self.get_headers(verbosity=verbosity),
            params=payload,
            timeout=self.get_timeout(),
            verbosity=verbosity,
            API=self.api_externa.nome,
        )
        return r.ok and 'retorno' in r.text

    def obter_link_formulario_avaliacao(self, solicitacao):
        payload = {
            'cpfCidadao': solicitacao.cpf.replace('.', '').replace('-', ''),
            'etapa': solicitacao.status,
            'orgao': str(self.get_orgao_id()),
            'protocolo': str(solicitacao.id),
            'servico': solicitacao.servico.id,
        }
        registro_avaliacao, _registro_criado = RegistroAvaliacaoGovBR.objects.update_or_create(solicitacao=solicitacao)
        try:
            url = self.api_externa.url_base + 'formulario'

            req = requests.post(
                url,
                headers=self.get_headers(),
                json=payload,
                timeout=self.get_timeout(),
            )
            if req.ok:
                resposta = {'status_code': req.status_code, 'url': req.json()['location']}
                if registro_avaliacao:
                    registro_avaliacao.url_avaliacao = resposta['url']
                    registro_avaliacao.data_cadastro_link_formulario = datetime.now()
                    registro_avaliacao.save()
                return resposta
            else:
                status = None
                if 'status' in req.text:
                    status = req.json()['status']
                resposta = {'status_code': req.status_code, 'response': req.text, 'status': status}
                return resposta
        except Exception as e:
            if settings.DEBUG:
                raise e

    def atualizar_registro_avaliacao(self, registro_acompanhamento, verbosity=False):
        cpf = registro_acompanhamento.payload['cpfCidadao']
        registro_acompanhamento.payload['cpfCidadao'] = cpf.replace('.', '').replace('-', '')
        try:
            req = requests.get(
                url=self.api_externa.url_base,
                params=registro_acompanhamento.payload,
                headers=self.get_headers(),
                timeout=self.get_timeout(),
            )
            if req.ok and 'avaliacao' in req.json():
                registro_avaliacao, _created = RegistroAvaliacaoGovBR.objects.get_or_create(solicitacao=registro_acompanhamento.solicitacao)
                registro_avaliacao.resposta_avaliacao = req.text
                registro_avaliacao.data_cadastro_avaliacao = datetime.now()
                registro_avaliacao.avaliado = True
                registro_avaliacao.save()
                registro_acompanhamento.avaliado = True
                registro_acompanhamento.save()
                if verbosity:
                    logger.info(f'Avaliação registrada para solicitação {registro_acompanhamento.solicitacao.id}')
            else:
                registro_acompanhamento.tentativas_envio += 1
                registro_acompanhamento.save()
                if verbosity:
                    logger.info(f'Nenhum registro de avaliação para solicitação {registro_acompanhamento.solicitacao.id}')
        except Exception as e:
            if settings.DEBUG:
                raise e
