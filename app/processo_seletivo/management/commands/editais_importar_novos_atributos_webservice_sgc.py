import datetime
import json
from xml.dom import minidom

from django.conf import settings

from djtools.management.commands import BaseCommandPlus
from djtools.utils import requests
from processo_seletivo.models import Edital, WebService


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        title = 'Editais - Importação de Novos Atributos Vindos Do SGC'
        self.stdout.write('\n')
        self.stdout.write('- ' * len(title))
        self.stdout.write(title)
        self.stdout.write('- ' * len(title))
        self.stdout.write('Início do processamento: {}'.format(datetime.datetime.now().strftime('%d/%m/%Y - %H:%M:%S')))
        self.stdout.write('\n')

        qs_ws = WebService.objects.filter(id=2)
        for ws in qs_ws:
            self.stdout.write(f'Carregando editais do webserives {ws} .')
            self.stdout.write('Obs: Apenas os editais já cadastrados no banco de dados do SUAP terão os dados básicos atualizados.')

            xml = None
            try:
                self.stdout.write('\n')
                self.stdout.write(f'Tentando consumir o webservice "{ws.url_editais}"')
                xml = requests.get(ws.url_editais, timeout=settings.REQUESTS_TIMEOUT).text
                self.stdout.write('Webservice carregado com sucesso.')
            except Exception as e:
                self.stderr.write(f'Erro ao consumir o webservices. Detalhes: {e}')
                return

            doc = minidom.parseString(xml)
            for edital_xml in doc.getElementsByTagName('edital'):
                codigo = edital_xml.getElementsByTagName('codigo')[0].firstChild.nodeValue
                ano = edital_xml.getElementsByTagName('ano')[0].firstChild.nodeValue
                semestre = edital_xml.getElementsByTagName('semestre')[0].firstChild.nodeValue
                remanescentes = edital_xml.getElementsByTagName('remanescentes')[0].firstChild.nodeValue == 'Sim'

                sisu = edital_xml.getElementsByTagName('sisu')[0].firstChild.nodeValue == 'Sim'
                qtd_vagas = edital_xml.getElementsByTagName('qtd_vagas')[0].firstChild.nodeValue
                qtd_inscricoes = edital_xml.getElementsByTagName('qtd_inscricoes')[0].firstChild.nodeValue
                qtd_inscricoes_confirmadas = edital_xml.getElementsByTagName('qtd_inscricoes_confirmadas')[0].firstChild.nodeValue
                detalhamento_por_campus = edital_xml.getElementsByTagName('detalhamento_por_campus')[0].firstChild.nodeValue

                if edital_xml.getElementsByTagName('descricao')[0].firstChild:
                    descricao = '{} de {}/{}'.format(edital_xml.getElementsByTagName('descricao')[0].firstChild.nodeValue, ano, semestre)
                else:
                    descricao = f'Edital {codigo} de {ano}/{semestre}'

                self.stdout.write('\n')
                self.stdout.write(f'{descricao} - Código {codigo} - Ano {ano} - Semestre: {semestre} - Sisu: {sisu}')
                try:
                    edital = Edital.objects.get(codigo=codigo, webservice=ws)
                except Edital.DoesNotExist:
                    edital = None

                if edital:
                    # edital.codigo = edital_selecionado_webservice.codigo
                    # edital.descricao = edital_selecionado_webservice.descricao
                    # edital.ano = edital_selecionado_webservice.ano
                    # edital.semestre = edital_selecionado_webservice.semestre

                    edital.sisu = sisu
                    edital.qtd_vagas = qtd_vagas
                    edital.qtd_inscricoes = qtd_inscricoes
                    edital.qtd_inscricoes_confirmadas = qtd_inscricoes_confirmadas
                    edital.detalhamento_por_campus = detalhamento_por_campus

                    edital.remanescentes = remanescentes
                    # edital.webservice = edital_selecionado_webservice.webservice

                    edital.save()

                    editais_sgc_dict_list = json.loads(edital.detalhamento_por_campus)
                    for edital in editais_sgc_dict_list:
                        self.stdout.write(
                            'Campus SGC: {}  /  Suap_Uo_Id: {}  /  Vagas: {}  /  Inscricões: {}  /  Inscrições Confirmadas: {}'.format(
                                edital['campus'],
                                edital['suap_unidade_organizacional_id'],
                                edital['qtd_vagas'],
                                edital['qtd_inscricoes'],
                                edital['qtd_inscricoes_confirmadas'],
                            )
                        )

                    self.stdout.write('Edital cadastrado no SUAP. Dados atualizados com sucesso.')
                else:
                    self.stdout.write('Edital não cadastrado no SUAP.')

        self.stdout.write('\n')
        self.stdout.write('Processamento concluído com sucesso')
        self.stdout.write('Fim do processamento: {}'.format(datetime.datetime.now().strftime('%d/%m/%Y - %H:%M:%S')))
