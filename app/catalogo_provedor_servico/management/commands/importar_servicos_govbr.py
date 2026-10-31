from django.conf import settings
from django.core.management.base import BaseCommand

from catalogo_provedor_servico.models import Servico
from comum.models import Configuracao
from djtools.utils import requests

# O parâmetro "codigoUnidade" é o código siorg. No caso do IFRN o código é o 439.
# https://siorg.planejamento.gov.br/siorg-cidadao-webapp/pages/listar_orgaos_estruturas/listar_orgaos_estruturas.jsf
# http://estruturaorganizacional.dados.gov.br/doc/orgao-entidade.xml
# http://estruturaorganizacional.dados.gov.br/doc/unidade-organizacional/439
# https://www.governoeletronico.gov.br/eixos-de-atuacao/governo/novo-siorg/documentos-e-arquivos/SIORG-NovoSiorg-v1.1-WebServices.pdf

# Exemplo de chamada:
# python manage.py importar_servicos_govbr


class Command(BaseCommand):
    def handle(self, *args, **options):
        instituicao_codigo_siorg = Configuracao.get_valor_por_chave('comum', 'instituicao_codigo_siorg')
        url_servicos_gov_br = 'https://servicos.gov.br/api/v1/servicos/orgao'
        url_orgaos_gov_br = 'https://servicos.gov.br/api/v1/orgao'

        if not instituicao_codigo_siorg:
            raise Exception(
                f'O parâmetro "instituicao_codigo_siorg" não foi encontrado. Defina-o em {settings.SITE_URL}/comum/configuracao/comum/ e rode este comando novamente.'
            )

        req = requests.get(
            url=f'{url_orgaos_gov_br}/{instituicao_codigo_siorg}',
            timeout=settings.REQUESTS_TIMEOUT,
            verbosity=True,
            API='ORGAOS_GOVBR',
        )
        if req.ok:
            id_servicos_instituicao = req.json().get('id', None)
            Configuracao.objects.update_or_create(
                app='catalogo_provedor_servico', chave='orgao_id_portal_servicos_govbr', defaults={'valor': id_servicos_instituicao}
            )

        url = f'{url_servicos_gov_br}/{instituicao_codigo_siorg}'
        servicos_portal = requests.get(url, timeout=settings.REQUESTS_TIMEOUT, verbosity=True, API='SERVICOS_GOVBR').json()
        for servico_portal in servicos_portal['resposta']:
            id_servico_portal_govbr = servico_portal['id'].split('/')[-1]
            titulo = servico_portal['nome']
            descricao = servico_portal['descricao']

            servico = Servico.objects.filter(id_servico_portal_govbr=id_servico_portal_govbr)
            if servico.exists():
                try:
                    servico.update(titulo=titulo, descricao=descricao)
                    # servico.update(titulo=titulo, descricao=descricao, icone='fa fa-question-circle')
                    self.stdout.write(f'Serviço "{id_servico_portal_govbr} - {titulo}" atualizado com sucesso.')
                except Exception as e:
                    self.stderr.write(f'Erro ao atualizar o serviço "{id_servico_portal_govbr} - {titulo}": {e}')
            else:
                try:
                    Servico.objects.create(
                        id_servico_portal_govbr=id_servico_portal_govbr,
                        icone='fa fa-question-circle',
                        titulo=titulo,
                        descricao=descricao,
                        ativo=False,
                    )
                    self.stdout.write(f'Serviço "{id_servico_portal_govbr} - {titulo}" inserido com sucesso.')
                except Exception as e:
                    self.stderr.write(f'Erro ao inserir o serviço "{id_servico_portal_govbr} - {titulo}": {e}')
