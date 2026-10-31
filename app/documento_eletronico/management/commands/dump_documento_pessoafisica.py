import argparse
import csv
import datetime
import hashlib
import json
import os

from django.apps import apps
from django.db import connection

from comum.management.commands.terminal_utils import Terminal
from djtools.management.commands import BaseCommandPlus

DocumentoDigitalizado = apps.get_model('documento_eletronico', 'DocumentoDigitalizado')


def get_model_table_name(app_label, model_name):
    model = apps.get_model(app_label=app_label, model_name=model_name)
    table_name = model._meta.db_table
    return table_name


class Command(Terminal, BaseCommandPlus):
    def __init__(self):
        Terminal.__init__(self)
        self.data = []
        self.cursor = connection.cursor()
        caminho_arquivo_corrente_sem_extensao = os.path.splitext(__file__)[0]
        self.log_file = f'{caminho_arquivo_corrente_sem_extensao}.log'

    def add_arguments(self, parser):
        parser.add_argument(
            '--directory',
            '--dir',
            nargs='?',
            type=str,
            default='/tmp/documento_eletronico',
            help='Path to the directory is intended to store the CSV file resulting from processing.',
        )
        parser.add_argument('--executar_command_via_migration', action=argparse.BooleanOptionalAction)

    def fetchall_as_dict(self):
        """
        Método que retorna uma lista de registros, onde cada registro é um dicionário.
        Ref: https://docs.djangoproject.com/en/2.0/topics/db/sql/#executing-custom-sql-directly
        """
        columns = [col[0] for col in self.cursor.description]
        return [dict(list(zip(columns, row, strict=False))) for row in self.cursor.fetchall()]

    def export_to_csv(self, filename, rows, path=None):
        path = path or f'{self.wordir}/pf/'
        if not os.path.exists(path):
            os.makedirs(path)
        #
        keys = rows[0].keys() if rows else []
        if keys:
            with open(f'{path}/{filename}.csv', 'w') as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=keys)
                writer.writeheader()
                writer.writerows(rows)

    def get_md5(self, data):
        return hashlib.md5(json.dumps(data, sort_keys=True).encode('utf-8')).hexdigest()

    def run_sql(self, label, query):
        self.cursor.execute(query)
        data = self.fetchall_as_dict()
        if data:
            self.data.append({'filename': f'{label}.csv', 'hash': self.get_md5(data)})
            self.export_to_csv(label, data)
        return data

    def exportar_documento_texto_interessados(self):
        query = """
            select p.id, p.nome, count(1) as qt from pessoa p
            inner join documento_eletronico_documentotexto_interessados i on i.pessoa_id = p.id
            inner join documento_eletronico_documentotexto d on d.id = i.documentotexto_id
            group by p.id, p.nome
            order by p.id;
        """
        self.log('INFO: Iniciando a exportacao dos interressados de documentos.')
        self.run_sql('documento_texto_interessados_pessoa', query)
        self.add_empty_line()
        self.log('INFO: Todos os interessados de documentos foram exportados.')

    def exportar_dono_do_documento(self):
        query = """
            select p.id, p.nome, count(1) as qt from pessoa p
            inner join documento_eletronico_documentodigitalizado d on d.dono_documento_id = p.id
            group by p.id, p.nome
            order by p.id
        """
        self.log('INFO: Iniciando a exportacao dos donos de documentos digitalizados.')
        self.run_sql('dono_documento_pessoa', query)
        self.add_empty_line()
        self.log('INFO: Todos os donos de documentos digitalizados foram exportadas.')

    def exportar_solicitacao_assinatura(self):
        query = """
            select p.id, p.nome, count(1) as qt
            from pessoa p
            inner join documento_eletronico_solicitacaoassinatura s on s.solicitado_id = p.id
            group by p.id, p.nome
            order by p.nome, p.id;
        """
        self.log('INFO: Iniciando a exportacao das pessoas que tiveram assinatura solicitadas.')
        self.run_sql('solicitacao_assinatura_pessoa', query)
        self.add_empty_line()
        self.log('INFO: Todas as pessoas com assinatura solicitadas foram exportadas.')

    def exportar_solicitacao_revisao_revisores(self):
        query = """
           select p.id, p.nome, count(1) as qt
           from pessoa p
           inner join documento_eletronico_solicitacaorevisao s on s.revisor_id = p.id
           group by p.id, p.nome
           order by p.nome, p.id;

        """
        self.log('INFO: Iniciando a exportacao das solicitações a revisores de documento texto.')
        self.run_sql('solicitacao_revisao_revisor_pessoa', query)
        self.add_empty_line()
        self.log('INFO: Todos os revisores de documento texto foram exportadas.')

    def exportar_solicitacao_revisao_avaliadores(self):
        query = """
           select p.id, p.nome, count(1) as qt
           from pessoa p
           inner join documento_eletronico_solicitacaorevisao s on s.avaliador_id = p.id
           group by p.id, p.nome
           order by p.nome, p.id;

        """
        self.log('INFO: Iniciando a exportacao das solicitações a avaliadores de documento texto.')
        self.run_sql('-solicitacao_revisao_avaliador_pessoa', query)
        self.add_empty_line()
        self.log('INFO: Todos os avaliadores dde documento texto foram exportados.')

    def exportar_assinatura(self):
        query = """
            select p.id, p.nome, count(1) as qt
            from pessoa p
            inner join documento_eletronico_assinatura a on a.pessoa_id = p.id
            group by p.id, p.nome
            order by p.nome, p.id;
        """
        self.log('INFO: Iniciando a exportação das pessoas que assinaram documento texto.')
        self.run_sql('assinatura_pessoa', query)
        self.add_empty_line()
        self.log('INFO: Todos as pessoas que assinaram documento texto foram exportadas.')

    def expotar_compartilhamento_documento_pessoa_permitida(self):
        query = """
            select p.id, p.nome, count(1) as qt
            from pessoa p
            inner join documento_eletronico_compartilhamentodocumentopessoa cp on cp.pessoa_permitida_id = p.id
            group by p.id, p.nome
            order by p.nome, p.id;

        """
        self.log('INFO: Iniciando a exportação dos compartilhamento de documento com pessoa.')
        self.run_sql('compartilhamento_documento_pessoa_permitida', query)
        self.add_empty_line()
        self.log('INFO: Todos as pessoas com documentos compartihados foram exportados.')

    def expotar_compartilhamento_documento_digitalizado_solicitante(self):
        model_name = get_model_table_name('documento_eletronico', 'CompartilhamentoDocumentoDigitalizadoPessoa')
        query = f"""
        select p.id, p.nome, count(1) as qt
        from pessoa p
        inner join {model_name} cp on cp.pessoa_permitida_id = p.id
        group by p.id, p.nome
        order by p.nome, p.id;
        """
        self.log('INFO: Iniciando a exportação dos solicitantes de compartilhamento de documento digitalizado.')
        self.run_sql('compartilhamento_documento_solicitante_pessoa', query)
        self.add_empty_line()
        self.log('INFO: Todos os solicitantes de compartilhamento de documento digitalizados foram exportados.')

    def expotar_solicitacao_compartilhamento_documento_digitalizado_solicitante(self):
        model_name = get_model_table_name('documento_eletronico', 'SolicitacaoCompartilhamentoDocumentoDigitalizadoPessoa')
        query = f"""
        select p.id, p.nome, count(1) as qt
        from pessoa p
        inner join {model_name} cp on cp.pessoa_solicitante_id = p.id
        group by p.id, p.nome
        order by p.nome, p.id;
        """
        self.log('INFO: Iniciando a exportação das solicitações de compartilhamento de documento digitalizado.')
        self.run_sql('solicitacao_compartilhamento_documento_solicitante_pessoa', query)
        self.add_empty_line()
        self.log('INFO: Todos as solicitações de compartilhamento de documento digitalizadis foram exportadas.')

    def expotar_compartilhamento_setor_pessoa(self):
        query = """
        select p.id, p.nome, count(1) as qt
        from pessoa p
        inner join documento_eletronico_compartilhamentosetorpessoa cp on cp.pessoa_permitida_id = p.id
        group by p.id, p.nome
        order by p.nome, p.id;
        """
        self.log('INFO: Iniciando dos compartilhamento de setor com pessoa.')
        self.run_sql('compartilhamento_setor_pessoa', query)
        self.add_empty_line()
        self.log('INFO: Todos os compartilhamentos de setor com pessoa foram exportadas.')

    def run(self):
        self.exportar_documento_texto_interessados()
        self.exportar_dono_do_documento()
        self.exportar_solicitacao_assinatura()
        self.exportar_solicitacao_revisao_revisores()
        self.exportar_solicitacao_revisao_avaliadores()
        self.exportar_assinatura()
        self.expotar_compartilhamento_documento_pessoa_permitida()
        self.expotar_compartilhamento_documento_digitalizado_solicitante()
        self.expotar_solicitacao_compartilhamento_documento_digitalizado_solicitante()
        self.expotar_compartilhamento_setor_pessoa()
        self.export_to_csv('documento_eletronico_pessoa_md5sum', self.data, path=self.wordir)

    def handle(self, *args, **options):
        self.wordir = options.get('directory')
        self.log_title(f'Documento Eletronico - {__name__}')

        self.add_empty_line()
        self.log(
            'O objetivo deste command eh varrer todos os modelos do módulo de documento eletronico\n'
            'e informar a quantidade de pessoa física associada a campos que vínculada a essa tabela.\n'
            'Por exemplo, quantos documentos: uma dada pessoa fisica esta vinculada como dono do documento.\n'
            f'A saída do processamento será gravada em {self.wordir}.'
        )

        executar_command = options.get('executar_command_via_migration')
        if executar_command is None:
            executar_command = self.ask_yes_or_no('Deseja continuar')

        if not executar_command:
            self.add_empty_line()
            self.log('Processamento abortado.')
            return

        start_time = datetime.datetime.now()
        self.log('Inicio do processamento: {}'.format(start_time.strftime('%d/%m/%Y - %H:%M:%S')))
        self.add_empty_line()
        self.log_title('Exportando os campos relativos a pessoas fisica nos modelos do documento eletronico')
        self.run()
        elapsed_time = datetime.datetime.now()
        self.log('Fim do processamento: {}'.format(elapsed_time.strftime('%d/%m/%Y - %H:%M:%S')))
        print(f'Duration: {elapsed_time - start_time}')
