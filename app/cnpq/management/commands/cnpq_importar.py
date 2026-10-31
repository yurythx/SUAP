"""
Comando que extrai os curriculos lattes
"""

import datetime
import io
import os
import os.path
import re
import sys
import tempfile
import time
import zipfile
from urllib.error import URLError

from django.apps import apps
from django.conf import settings
from django.core.mail import mail_admins
from django.core.management import CommandError
from django.db import transaction
from django.utils import termcolors
from sentry_sdk import capture_exception
from suds.client import Client

from cnpq.models import CurriculoVittaeLattes
from cnpq.xml_parsers import CurriculoVittaeLattesParser
from comum.models import Configuracao, Vinculo
from djtools.management.commands import BaseCommandPlus
from djtools.storages import get_temp_storage
from djtools.utils import b64decode
from rh.models import Servidor


class EmptyResponse(Exception):
    pass


class Command(BaseCommandPlus):
    help = 'Executa os testes do SUAP'

    def add_arguments(self, parser):
        parser.add_argument(
            '--file',
            '-f',
            dest='file',
            action='store',
            default=[],
            help='Arquivo zip contendo o currículo lattes em formato xml baixado da plataforma lattes.',
        )

        parser.add_argument('--matricula', '-m', dest='matricula', action='store', default=[], help='Matricula.')

        parser.add_argument('--forcar', action='store_true', dest='forcar', default=False, help='Forçar a importação de todos.')

        parser.add_argument('--alunos', action='store_true', dest='alunos', default=False, help='Importar somente alunos.')

        parser.add_argument('--servidores', action='store_true', dest='servidores', default=False, help='Importar somente servidores.')

        parser.add_argument('--xml', dest='xml', action='store_true', default=False, help='Importa e salva os XML.')

    def handle(self, *args, **options):
        # Baixar o arquivo .zip com o currículo da pessoa que desejar diretamente da plataforma Lattes
        # Testar importação Servidor: ./manage.py cnpq_importar --forcar -m=1488270 -f=3181772060208133.zip
        # Testar importação Aluno:  ./manage.py cnpq_importar --forcar -m=20241996260042 -f=2584348916976776.zip

        queryset_objs = None
        forcar = options.get('forcar', False)
        somente_servidores = options.get('servidores', False)
        somente_alunos = options.get('alunos', False)
        nome_arquivo = options.get('file', '')
        matricula = options.get('matricula')
        origem_chamada = options.get('origem_view')
        xml = options.get('xml')
        verbosity = options.get('verbosity', 3)

        # Verifica se o app "edu" está instalado para habilitar a importação de alunos
        aplicacao_edu_esta_instalada = 'edu' in settings.INSTALLED_APPS
        Aluno, NivelEnsino = None, None
        if aplicacao_edu_esta_instalada:
            Aluno = apps.get_model('edu', 'Aluno')
            NivelEnsino = apps.get_model('edu', 'NivelEnsino')

        if matricula:
            servidor = Servidor.objects.filter(matricula=matricula).first()
            if servidor:
                queryset_objs = Vinculo.objects.filter(id_relacionamento=servidor.id, tipo_relacionamento__model='servidor')
            if not queryset_objs and aplicacao_edu_esta_instalada:
                aluno = Aluno.objects.filter(matricula=matricula).first()
                if aluno:
                    queryset_objs = Vinculo.objects.filter(id_relacionamento=aluno.id, tipo_relacionamento__model='aluno')
        if nome_arquivo:
            if os.path.isfile(nome_arquivo):
                file_name, _file_extension = os.path.splitext(nome_arquivo)
                identificador_cnpq = file_name.split('/')[-1]
                curriculo_str = self.get_arquivo_xml(nome_arquivo, 'curriculo')
                data_atualizacao = None
                curriculo_lattes = CurriculoVittaeLattesParser(curriculo_str, data_atualizacao, identificador_cnpq, forcar)
                if queryset_objs:
                    vinculo = queryset_objs[0]
                    curriculo_lattes.parse(vinculo)
                    if hasattr(vinculo, 'vinculo_curriculo_lattes'):
                        from cnpq.views import atualizar_grupos_pesquisa

                        atualizar_grupos_pesquisa(vinculo.vinculo_curriculo_lattes)
                    self.stdout.write(self.style.SUCCESS(f'Currículo de {queryset_objs[0]} importado com sucesso.'))
                    return
            else:
                raise CommandError(f'Arquivo {nome_arquivo} não encontrado.')

        qs_servidores = Servidor.objects.filter(ativo=True).values_list('id', flat=True)
        if aplicacao_edu_esta_instalada:
            qs_alunos = Aluno.ativos.filter(curso_campus__modalidade__nivel_ensino=NivelEnsino.POS_GRADUACAO).values_list('id', flat=True)
        if somente_servidores:
            queryset_objs = Vinculo.objects.filter(tipo_relacionamento__model='servidor', id_relacionamento__in=qs_servidores)
        elif somente_alunos and aplicacao_edu_esta_instalada:
            queryset_objs = Vinculo.objects.filter(tipo_relacionamento__model='aluno', id_relacionamento__in=qs_alunos)
        elif not queryset_objs and not nome_arquivo:
            queryset_objs = Vinculo.objects.filter(tipo_relacionamento__model='servidor', id_relacionamento__in=qs_servidores, ativo=True)
            if aplicacao_edu_esta_instalada:
                qs_vinculos_alunos = Vinculo.objects.filter(tipo_relacionamento__model='aluno', id_relacionamento__in=qs_alunos, ativo=True)
                queryset_objs = queryset_objs.union(qs_vinculos_alunos)

        total = queryset_objs.count()

        count_extraidos = 0
        count_novos = 0
        count_atualizados = 0
        count_erros = 0
        count = 0
        count1_exceptions = 0
        count2_exceptions = 0
        exceptions = {}
        tmp = tempfile.NamedTemporaryFile(mode='w+b', suffix='.zip')
        zip_file = zipfile.ZipFile(tmp.name, 'w', zipfile.ZIP_DEFLATED)
        for vinculo in queryset_objs:
            time.sleep(1)
            count += 1
            porcentagem = int(float(count) / total * 100)

            if verbosity:
                sys.stdout.write(
                    termcolors.make_style(fg='cyan', opts=('bold',))(
                        '\r[{}] {}% - Extraindo {} de {}'.format('#' * int(porcentagem / 10), porcentagem, count, total)
                    )
                )
                sys.stdout.flush()

            identificador_cnpq = ''

            try:
                identificador_cnpq = self.get_identificador(vinculo.relacionamento.pessoa_fisica.cpf)
            except Exception:
                count_erros += 1
                continue

            if identificador_cnpq is None:
                count_erros += 1
                continue

            novo = False

            data_atualizacao = None

            sid = transaction.savepoint()

            tipo_acao = 0

            try:
                data_atualizacao_str = self.get_data_atualizacao(identificador_cnpq)
                eh_servidor = vinculo.eh_servidor()
                if data_atualizacao_str != 'None':
                    data_atualizacao = datetime.datetime.strptime(data_atualizacao_str, '%d/%m/%Y %H:%M:%S')
                curriculo_str = None
                if hasattr(vinculo, 'vinculo_curriculo_lattes'):
                    if xml:
                        curriculo_str = self.get_curriculo(identificador_cnpq, eh_servidor, xml and zip_file or None)
                    data_ultima_extracao = vinculo.vinculo_curriculo_lattes.data_extracao

                    if not data_ultima_extracao or data_atualizacao >= data_ultima_extracao or forcar:
                        tipo_acao = 1
                else:
                    novo = True
                    tipo_acao = 2

                if tipo_acao == 0:
                    continue

                count_extraidos += 1

                if tipo_acao == 1 and hasattr(vinculo, 'vinculo_curriculo_lattes'):
                    vinculo.vinculo_curriculo_lattes.delete()
                if not curriculo_str:
                    curriculo_str = self.get_curriculo(identificador_cnpq, eh_servidor, xml and zip_file or None)

                curriculo_lattes = CurriculoVittaeLattesParser(curriculo_str, data_atualizacao, identificador_cnpq, forcar)

                executou_parse = curriculo_lattes.parse(vinculo)

                if executou_parse:
                    curriculo_atualizado = CurriculoVittaeLattes.objects.get(vinculo=vinculo)
                    curriculo_atualizado.data_extracao = datetime.datetime.now()
                    curriculo_atualizado.save()
                    from cnpq.views import atualizar_grupos_pesquisa

                    atualizar_grupos_pesquisa(curriculo_atualizado)

                    if novo:
                        count_novos += 1
                    else:
                        count_atualizados += 1
                    transaction.savepoint_commit(sid)
                    transaction.commit()
                else:
                    transaction.savepoint_rollback(sid)
            except (URLError, EmptyResponse) as e:
                transaction.savepoint_rollback(sid)
                exceptions[vinculo] = e
                count1_exceptions += 1
            except Exception as e:
                transaction.savepoint_rollback(sid)
                exceptions[vinculo] = e
                count2_exceptions += 1
                capture_exception(e)

        zip_file.close()

        if xml:
            temp = get_temp_storage()
            temp.delete('curriculos.zip')
            temp.save('curriculos.zip', tmp)

        tmp.close()

        mensagem = '\n\t ERROS '

        for servidor in exceptions:
            mensagem += f'\n{servidor} => {exceptions.get(servidor)!s}'

        mensagem += '\n\n'
        mensagem += f'\n{total} \t TOTAL '
        mensagem += f'\n{count_extraidos} \t Extraidos '
        mensagem += f'\n{count_novos} \t Novos '
        mensagem += f'\n{count_atualizados} \t Atualizados '
        mensagem += '\n{} \t Pessoas sem curriculo/ligação com o {} '.format(
            count_erros, Configuracao.get_valor_por_chave('comum', 'instituicao_sigla')
        )

        mensagem += f'\n{count1_exceptions} \t Exceções t1 (URLError, EmptyResponse) '
        mensagem += f'\n{count2_exceptions} \t Exceções t2 '

        # se tiver alguma exceção
        if count1_exceptions or count2_exceptions:
            mail_admins('[SUAP] Importação do CNPQ', mensagem)

        if origem_chamada:
            return count1_exceptions + count2_exceptions + count_erros
        return mensagem

    def getClient(self):
        URL = 'http://servicosweb.cnpq.br/srvcurriculo/WSCurriculo?wsdl'
        client = Client(URL)
        client.set_options(location='http://servicosweb.cnpq.br/srvcurriculo/WSCurriculo')
        return client

    def get_identificador(self, cpf):
        cpf = re.sub(r'\D', '', cpf)  # retira tudo que nao eh digito
        resposta = None
        try:
            resposta = self.getClient().service.getIdentificadorCNPq(cpf, '', '')
        except Exception as e:
            capture_exception(e)
        if not resposta:
            raise EmptyResponse
        if '<MENSAGEM><ERRO>' in str(resposta):
            raise CommandError(f'Erro {resposta}')
        return f'{resposta}'

    def get_data_atualizacao(self, identificador):
        resposta = None
        try:
            resposta = self.getClient().service.getDataAtualizacaoCV(identificador)
        except Exception as e:
            capture_exception(e)
        if not resposta:
            raise EmptyResponse
        if '<MENSAGEM><ERRO>' in str(resposta):
            raise CommandError(f'Erro {resposta}')
        return str(resposta)

    def get_curriculo(self, identificador, eh_servidor, zip_file=None):
        # salvando arquivo zip em memoria
        resposta = None
        try:
            resposta = self.getClient().service.getCurriculoCompactado(identificador)
        except Exception as e:
            capture_exception(e)
        if not resposta:
            raise EmptyResponse
        arquivo_zip = io.BytesIO()
        arquivo_zip.write(b64decode(resposta.encode('utf8')))
        if '_ERRO.xml' in str(arquivo_zip.getvalue()):
            raise CommandError(f'Erro {arquivo_zip.getvalue()}')
        curriculo = self.get_arquivo_xml(arquivo_zip, identificador)
        arquivo_zip.close()
        if eh_servidor and zip_file:
            with tempfile.NamedTemporaryFile() as unzipped_file:
                unzipped_file.write(curriculo)
                zip_file.write(unzipped_file.name, f'{identificador}.xml')
        return curriculo

    def get_arquivo_xml(self, filepath, identificador):
        # extraindo o conteudo do arquivo dentro do zip
        nome_xml = f'{identificador}.xml'
        arquivo_zip = zipfile.ZipFile(filepath, 'r')
        curriculo = arquivo_zip.read(nome_xml)
        arquivo_zip.close()
        return curriculo
