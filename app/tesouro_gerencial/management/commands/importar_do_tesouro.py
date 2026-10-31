import argparse
import email
import os
import zipfile
from datetime import date, datetime, timedelta
from imaplib import IMAP4_SSL

from dateutil.parser import parse
from sentry_sdk import capture_exception

from comum.models import Configuracao
from djtools.management.commands import BaseCommandPlus
from tesouro_gerencial.importador import ImportadorExecNE, ImportadorGRU, ImportadorNotaCredito, ImportadorNotaDotacao, ImportadorRAP
from tesouro_gerencial.models import HistoricoImportacao, Importacao


class Command(BaseCommandPlus):
    PASTA_DOWNLOAD = '/tmp'

    NOTA_CREDITO = 'CREDITOS'
    DOCUMENTOS = 'DOCUMENTOS'
    RAP = 'RAP'
    RECEITA_GRU = 'GRU'
    NOTA_DOTACAO = 'DOTACOES'
    TIPOS_CHOICES = {
        NOTA_CREDITO: ImportadorNotaCredito,
        DOCUMENTOS: ImportadorExecNE,
        RAP: ImportadorRAP,
        RECEITA_GRU: ImportadorGRU,
        NOTA_DOTACAO: ImportadorNotaDotacao,
    }

    PREFIXOS_ARQUIVOS = {
        Importacao.TIPO_MOV_CREDITO: ImportadorNotaCredito,
        Importacao.TIPO_EXEC_NE: ImportadorExecNE,
        Importacao.TIPO_RAP: ImportadorRAP,
        Importacao.TIPO_GRU: ImportadorGRU,
        Importacao.TIPO_NOTAS_DOTACAO: ImportadorNotaDotacao,
    }

    def add_arguments(self, parser):
        def validar_data(date):
            formato = '%d/%m/%Y'
            try:
                return datetime.strptime(date, formato)
            except ValueError:
                msg = f"Data inválida: '{date}' deve estar no formato '{formato}'."
                raise argparse.ArgumentTypeError(msg)

        parser.add_argument(
            '--date', '-d', nargs='?', type=validar_data, help='Data da mensagem de email que deve ser importada - formato DD/MM/AAAA'
        )
        parser.add_argument('--file', '-f', nargs='?', type=str, help='Arquivo a ser importado')
        parser.add_argument('--type', '-t', nargs='?', type=str, choices=self.TIPOS_CHOICES.keys(), help='Tipos de scrapping do arquivo')
        parser.add_argument('--encoding', '-enc', nargs='?', type=str, help='Encoding do arquivo de scrapping')
        parser.add_argument('--delimiter', '-del', nargs='?', type=str, help='Delimiter do arquivo de scrapping')

    def handle(self, *args, **options):
        verbosity = int(options.get('verbosity', 1)) >= 1 and 1 or 0

        file = options.get('file')
        type_file = options.get('type')
        encoding = options.get('encoding') or 'utf-16'
        delimiter = options.get('delimiter')
        if file or type_file:
            if not file:
                raise argparse.ArgumentTypeError('Deve-se informar o caminho do arquivo a ser importado')
            elif not type_file:
                raise argparse.ArgumentTypeError('Deve-se informar o tipo de scrapping do arquivo')

            ClasseImportador = self.TIPOS_CHOICES[type_file]
            importador = ClasseImportador(arquivos=[file], tipo_log=verbosity, encoding=encoding)
            if delimiter:
                importador.delimiter = delimiter
            importador.run()
            return

        data_email = options.get('date')
        dados_email = self.baixar_arquivos_email(data_email)
        if dados_email:
            arquivos_csv = []
            for arquivo in os.scandir(self.PASTA_DOWNLOAD):
                if os.path.splitext(arquivo)[1] == '.csv':
                    arquivos_csv.append(arquivo)

            historico_importacao, _ = HistoricoImportacao.objects.get_or_create(data__date=date.today())
            for tipo, importador_class in self.PREFIXOS_ARQUIVOS.items():
                if tipo in dados_email:
                    data_email = parse(dados_email[tipo]['DATE'])
                    assunto_email = dados_email[tipo]['SUBJECT']
                    arquivos = self.get_arquivos_por_nome(arquivos_csv, tipo)
                    if not Importacao.objects.filter(data_email=data_email, assunto_email=assunto_email, tipo=tipo).exists():
                        importacao = Importacao()
                        importacao.historico = historico_importacao
                        importacao.data_email = data_email
                        importacao.assunto_email = assunto_email
                        importacao.tipo = tipo
                        ClasseImportador = importador_class
                        importador = ClasseImportador(arquivos=arquivos, tipo_log=verbosity, encoding=encoding)
                        nrows = importador.run()
                        importacao.qtd = nrows
                        importacao.save()
                    for arquivo in arquivos:
                        if os.path.isfile(arquivo):
                            os.remove(arquivo)

    def get_arquivos_por_nome(self, arquivos, parte_nome):
        return [arquivo for arquivo in arquivos if parte_nome in arquivo.name]

    def baixar_arquivos_email(self, data_email):
        def decode_header(header_string):
            try:
                decoded_seq = email.header.decode_header(header_string)
                return str(email.header.make_header(decoded_seq))
            except Exception:
                return header_string

        servidor_email = Configuracao.get_valor_por_chave(app='tesouro_gerencial', chave='servidor_email')
        login_email = Configuracao.get_valor_por_chave(app='tesouro_gerencial', chave='email')
        senha_email = Configuracao.get_valor_por_chave(app='tesouro_gerencial', chave='senha_email')

        mail = IMAP4_SSL(servidor_email)
        mail.login(login_email, senha_email)
        dados_email = {}
        try:
            mail.select('INBOX', readonly=True)
            if not data_email:
                data_email = date.today()
                # Se for segunda-feira pegue o e-mail de sábado
                if data_email.weekday() == 0:
                    data_email = data_email - timedelta(2)
                # Se for domingo pegue o e-mail de sábado
                if data_email.weekday() == 6:
                    data_email = data_email - timedelta(1)

            _typ, [msg_ids] = mail.search(None, f'(SENTSINCE {data_email.strftime("%d-%b-%Y")})', '(FROM naoresponda@serpro.gov.br)')
            for num in msg_ids.split():
                _typ, msg_data = mail.fetch(num, '(RFC822)')
                for response_part in msg_data:
                    if isinstance(response_part, tuple):
                        msg = email.message_from_bytes(response_part[1])
                        assunto_email = decode_header(msg['subject'])
                        data_email = parse(decode_header(msg['date']))
                        if Importacao.objects.filter(assunto_email=assunto_email, data_email=data_email).exists():
                            self.stderr.write(f'\nSUBJECT: {assunto_email} --> JÁ IMPORTADO!!')
                            continue

                        if assunto_email not in self.PREFIXOS_ARQUIVOS:
                            self.stderr.write(f'\nSUBJECT: {assunto_email} --> NÃO EXISTE IMPORTADOR!!')
                            continue

                        att_path = 'No attachment found.'
                        for part in msg.walk():
                            if part.get_content_maintype() == 'multipart':
                                continue
                            if part.get('Content-Disposition') is None:
                                continue

                            filename = decode_header(part.get_filename())
                            att_path = os.path.join(self.PASTA_DOWNLOAD, filename)
                            if not os.path.isfile(att_path):
                                fp = open(att_path, 'wb')
                                fp.write(part.get_payload(decode=True))
                                fp.close()

                        zip_file = open(att_path, 'rb')
                        zipfile.ZipFile(zip_file).extractall(self.PASTA_DOWNLOAD)
                        zip_file.close()
                        os.remove(zip_file.name)
                        nome_arquivo_sem_ext = os.path.splitext(os.path.basename(zip_file.name))[0]
                        dados_email[nome_arquivo_sem_ext] = {}
                        self.stdout.write('')
                        for header in ['subject', 'to', 'from', 'date']:
                            key = header.upper()
                            value = decode_header(msg[key])
                            dados_email[nome_arquivo_sem_ext][key] = value
                            self.stdout.write(f'{key:8}: {value}')

                        self.stdout.write(f'{"ANEXO":8}: {att_path}')
        except Exception as error:
            capture_exception(error)
            raise error

        finally:
            try:
                mail.close()
            finally:
                mail.logout()

        return dados_email
