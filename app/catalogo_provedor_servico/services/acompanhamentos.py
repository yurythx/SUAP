import logging
from datetime import datetime

from catalogo_provedor_servico.models import RegistroAcompanhamentoGovBR
from comum.models import APIExterna, Configuracao
from comum.services import APIExternaService
from djtools.utils import requests

logger = logging.getLogger(__name__)


class ApiAcompanhamentosGovBRService(APIExternaService):
    def __init__(self):
        super().__init__(APIExterna.ACOMPANHAMENTO_GOVBR)

    def get_orgao_id(self):
        return int(Configuracao.get_valor_por_chave('catalogo_provedor_servico', 'orgao_id_portal_servicos_govbr') or 0)

    def estah_acessivel(self, verbosity=False):
        """
        Verifica se a plataforma de acompanhamentos está acessível
        """
        headers = self.get_headers(verbosity=verbosity)
        params = {
            'periodoInicio': headers.get('periodoInicio', ''),
            'periodoFinal': headers.get('periodoFinal', ''),
            'paginaAtual': '0',
            'orgao': self.get_orgao_id(),
        }
        url = self.api_externa.url_base + 'porOrgao'
        # url = 'https://h-acompanhamento-govbrapi.np.estaleiro.serpro.gov.br/api/acompanhamento/porOrgao'
        r = requests.get(
            url,
            headers=headers,
            params=params,
            timeout=self.get_timeout(),
            verbosity=verbosity,
            API=self.api_externa.nome,
        )
        return r.ok and 'retorno' in r.text

    def atualizar_registro(self, tipo, payload, method, url, registro=None, solicitacao=None):
        if registro:
            payload = registro.payload
            solicitacao = registro.solicitacao
        else:
            registro, _registro_criado = RegistroAcompanhamentoGovBR.objects.update_or_create(
                solicitacao=solicitacao,
                tipo=tipo,
                payload=payload,
                status=RegistroAcompanhamentoGovBR.PENDENTE,
            )
        try:
            r = getattr(requests, method)(
                url,
                headers=self.get_headers(),
                json=payload,
                timeout=self.get_timeout(),
            )
            if r.ok:
                registro.status = RegistroAcompanhamentoGovBR.ENVIADO
                registro.status_code = r.status_code
                registro.save()
                return r.json()
            else:
                registro.status = RegistroAcompanhamentoGovBR.ERRO
                registro.tentativas_envio = registro.tentativas_envio + 1
                registro.status_code = r.status_code
                registro.save()
                return r.text
        except Exception:
            registro.status = RegistroAcompanhamentoGovBR.ERRO
            registro.tentativas_envio = registro.tentativas_envio + 1
            registro.save()

    def registrar_acompanhamento_servico(
        self,
        registro=None,
        solicitacao=None,
    ):
        solicitacao = registro.solicitacao if registro else solicitacao
        payload = {
            'cpfCidadao': solicitacao.cpf.replace('.', '').replace('-', ''),  # "08254631654",
            'dataEtapa': datetime.strftime(solicitacao.data_criacao, '%d/%m/%Y'),  # "10/10/2017",
            'dataSituacaoEtapa': datetime.strftime(solicitacao.data_ultima_atualizacao, '%d/%m/%Y'),
            'etapa': solicitacao.status,  # "Em analise",
            'orgao': self.get_orgao_id(),  # "36802",
            'protocolo': solicitacao.id,  # "0001AC.20171212",
            'servico': solicitacao.servico.id,  # "47",
            'situacaoEtapa': solicitacao.status_detalhamento[:30],  # "Alguma descrição da situação."
        }
        self.atualizar_registro(
            tipo=RegistroAcompanhamentoGovBR.TIPO_ACOMPANHAMENTO,
            payload=payload,
            method='post',
            url=self.api_externa.url_base,
            registro=registro,
            solicitacao=solicitacao,
        )

    def registrar_conclusao_servico(
        self,
        registro=None,
        solicitacao=None,
    ):
        solicitacao = registro.solicitacao if registro else solicitacao
        payload = {
            'cpfCidadao': solicitacao.cpf.replace('.', '').replace('-', ''),
            'orgao': self.get_orgao_id(),
            'protocolo': solicitacao.id,
            'servico': solicitacao.servico.id,
            'situacaoServico': 2,  # 1 = Aberto/Reaberto - 2 = Concluído
        }
        self.atualizar_registro(
            tipo=RegistroAcompanhamentoGovBR.TIPO_CONCLUSAO,
            payload=payload,
            method='put',
            url=self.api_externa.url_base + 'situacao',
            registro=registro,
            solicitacao=solicitacao,
        )

    def registrar_reabertura_servico(
        self,
        registro=None,
        solicitacao=None,
    ):
        solicitacao = registro.solicitacao if registro else solicitacao
        payload = {
            'cpfCidadao': solicitacao.cpf.replace('.', '').replace('-', ''),
            'orgao': self.get_orgao_id(),
            'protocolo': solicitacao.id,
            'servico': solicitacao.servico.id,
            'situacaoServico': 1,  # 1 = Aberto/Reaberto - 2 = Concluído
        }
        self.atualizar_registro(
            tipo=RegistroAcompanhamentoGovBR.TIPO_REABERTURA,
            payload=payload,
            method='put',
            url=self.api_externa.url_base + 'situacao',
            registro=registro,
            solicitacao=solicitacao,
        )
