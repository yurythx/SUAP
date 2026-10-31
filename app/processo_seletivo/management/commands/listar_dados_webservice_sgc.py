import datetime
import json
from xml.dom import minidom

from django.conf import settings

from djtools.management.commands import BaseCommandPlus
from djtools.utils import requests
from processo_seletivo.models import WebService
from rh.models import UnidadeOrganizacional


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        # Filtro
        filtro_webservice_id = 2
        filtro_ano = 2016

        title = 'Editais - Análise de Dados do SGC'
        self.stdout.write('\n')
        self.stdout.write('-' * len(title))
        self.stdout.write(title)
        self.stdout.write(f'Webservice: {filtro_webservice_id}')
        self.stdout.write(f'Ano: {filtro_ano}')
        self.stdout.write('-' * len(title))
        self.stdout.write('Início do processamento: {}'.format(datetime.datetime.now().strftime('%d/%m/%Y - %H:%M:%S')))
        self.stdout.write('\n')

        qs_ws = WebService.objects.filter(id=filtro_webservice_id)
        for ws in qs_ws:
            self.stdout.write(f'Carregando editais do webserives {ws} .')

            xml = None
            try:
                self.stdout.write('\n')
                self.stdout.write(f'Tentando consumir o webservice "{ws.url_editais}"')
                xml = requests.get(ws.url_editais, timeout=settings.REQUESTS_TIMEOUT).text
                self.stdout.write('Webservice carregado com sucesso.')
            except Exception as e:
                self.stderr.write(f'Erro ao consumir o webservices. Detalhes: {e}')
                return

            qtd_vagas_total = 0
            qtd_inscricoes_total = 0
            qtd_inscricoes_confirmadas_total = 0

            doc = minidom.parseString(xml)

            self.stdout.write('-' * 200)
            self.stdout.write('Edital;Código;Ano;Semestre;Sisu;Remanescentes;Vagas;Inscrições;Inscrições Deferidas')
            for edital_xml in doc.getElementsByTagName('edital'):
                ano = int(edital_xml.getElementsByTagName('ano')[0].firstChild.nodeValue)
                if ano == filtro_ano:
                    codigo = edital_xml.getElementsByTagName('codigo')[0].firstChild.nodeValue
                    semestre = edital_xml.getElementsByTagName('semestre')[0].firstChild.nodeValue
                    remanescentes = edital_xml.getElementsByTagName('remanescentes')[0].firstChild.nodeValue == 'Sim'

                    sisu = edital_xml.getElementsByTagName('sisu')[0].firstChild.nodeValue == 'Sim'
                    qtd_vagas = int(edital_xml.getElementsByTagName('qtd_vagas')[0].firstChild.nodeValue or 0)
                    qtd_inscricoes = int(edital_xml.getElementsByTagName('qtd_inscricoes')[0].firstChild.nodeValue or 0)
                    qtd_inscricoes_confirmadas = int(edital_xml.getElementsByTagName('qtd_inscricoes_confirmadas')[0].firstChild.nodeValue or 0)

                    detalhamento_por_campus = edital_xml.getElementsByTagName('detalhamento_por_campus')[0].firstChild.nodeValue

                    if edital_xml.getElementsByTagName('descricao')[0].firstChild:
                        descricao = '{} de {}/{}'.format(edital_xml.getElementsByTagName('descricao')[0].firstChild.nodeValue, ano, semestre)
                    else:
                        descricao = f'Edital {codigo} de {ano}/{semestre}'

                    qtd_vagas_total += int(qtd_vagas)
                    qtd_inscricoes_total += int(qtd_inscricoes)
                    qtd_inscricoes_confirmadas_total += int(qtd_inscricoes_confirmadas)

                    self.stdout.write(
                        f'{descricao};{codigo};{ano};{semestre};{sisu};{remanescentes};{qtd_vagas};{qtd_inscricoes};{qtd_inscricoes_confirmadas}'
                    )
                    editais_sgc_dict_list = json.loads(detalhamento_por_campus)
                    for edital in editais_sgc_dict_list:
                        campus = UnidadeOrganizacional.objects.suap().get(pk=edital['suap_unidade_organizacional_id'])
                        self.stdout.write(
                            '   Campus SGC: {}  /  Campus SUAP: {}  /  Vagas: {}  /  Inscricões: {}  /  Inscrições Confirmadas: {}'.format(
                                edital['campus'], campus, edital['qtd_vagas'], edital['qtd_inscricoes'], edital['qtd_inscricoes_confirmadas']
                            )
                        )

            self.stdout.write('-' * 200)
            self.stdout.write(
                f'Total de Inscritos Deferidos(I);{qtd_inscricoes_confirmadas_total};Total de Vagas(VO);{qtd_vagas_total};Índice;{float(qtd_inscricoes_confirmadas_total) / qtd_vagas_total:.4f}'
            )
            self.stdout.write(
                f'Total de Inscritos;{qtd_inscricoes_total};Total de Vagas;{qtd_vagas_total};Índice;{float(qtd_inscricoes_total) / qtd_vagas_total:.4f}'
            )

        self.stdout.write('\n')
        self.stdout.write('Processamento concluído com sucesso')
        self.stdout.write('Fim do processamento: {}'.format(datetime.datetime.now().strftime('%d/%m/%Y - %H:%M:%S')))
