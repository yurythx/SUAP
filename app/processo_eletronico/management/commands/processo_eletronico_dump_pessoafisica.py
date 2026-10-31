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
            default='/tmp/processo_eletronico',
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
        keys = rows[0].keys()
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

    def exportar_processo_interessados(self):
        query = """
            select p.id, p.nome, count(1) as qt from pessoa p
            inner join processo_eletronico_processo_interessados i on i.pessoa_id = p.id
            inner join processo_eletronico_processo processo on processo.id = i.processo_id
            group by p.id, p.nome
            order by p.id;
        """
        self.log('INFO: Iniciando a exportacao dos interressados dos processos.')
        self.run_sql('processo_interessados_pessoa', query)
        self.add_empty_line()
        self.log('INFO: Todos os interessados dos processos foram exportados.')

    def exportar_processo_acompanhantes(self):
        query = """
            select p.id, p.nome, count(1) as qt from pessoa p
            inner join processo_eletronico_processo_pessoas_acompanhando_processo i on i.pessoa_id = p.id
            inner join processo_eletronico_processo processo on processo.id = i.processo_id
            group by p.id, p.nome
            order by p.id;
        """
        self.log('INFO: Iniciando a exportacao dos acompanhantes dos processos.')
        self.run_sql('processo_acompanhantes_pessoa', query)
        self.add_empty_line()
        self.log('INFO: Todos os acompanhantes dos processos foram exportados.')

    def exportar_comentario_processos(self):
        query = """
            select p.id, p.nome, count(1) as qt from pessoa p
            inner join processo_eletronico_comentarioprocesso i on i.pessoa_id = p.id
            inner join processo_eletronico_processo processo on processo.id = i.processo_id
            group by p.id, p.nome
            order by p.id;
        """
        self.log('INFO: Iniciando a exportacao das pessoas que comentaram nos processos.')
        self.run_sql('processo_comentarios_pessoa', query)
        self.add_empty_line()
        self.log('INFO: Todos que comentaram nos processos foram exportados.')

    def exportar_remetente_tramite(self):
        query = """
            select p.id, p.nome, count(1) as qt from pessoa p
            inner join processo_eletronico_tramite t on t.remetente_pessoa_id = p.id
            group by p.id, p.nome
            order by p.id;
        """
        self.log('INFO: Iniciando a exportacao dos remetentes nos tramites.')
        self.run_sql('tramite_remetente_pessoa', query)
        self.add_empty_line()
        self.log('INFO: Todos que remetentes nos tramites foram exportados.')

    def exportar_destinatario_tramite(self):
        query = """
            select p.id, p.nome, count(1) as qt from pessoa p
            inner join processo_eletronico_tramite t on t.destinatario_pessoa_id = p.id
            group by p.id, p.nome
            order by p.id;
        """
        self.log('INFO: Iniciando a exportacao dos destinatários nos tramites.')
        self.run_sql('tramite_destinario_pessoa', query)
        self.add_empty_line()
        self.log('INFO: Todos que destinatários nos tramites foram exportados.')

    def exportar_remetente_solicitacao_despacho(self):
        query = """
            select p.id, p.nome, count(1) as qt from pessoa p
            inner join processo_eletronico_solicitacaodespacho sd on sd.remetente_pessoa_id = p.id
            group by p.id, p.nome
            order by p.id;
        """
        self.log('INFO: Iniciando a exportacao dos remetentes nas solicitações de despacho.')
        self.run_sql('tramite_solicitacoes_despacho_pessoa', query)
        self.add_empty_line()
        self.log('INFO: Todos que remetentes nas solicitações de despacho foram exportados.')

    def exportar_requerimento_digitalizado(self):
        query = """
            select p.id, p.nome, count(1) as qt from pessoa p
            inner join processo_eletronico_requerimento r on r.interessado_id = p.id
            group by p.id, p.nome
            order by p.id;
        """
        self.log('INFO: Iniciando a exportacao das pessoas nos compartilhametos de requerimentos digitalizados.')
        self.run_sql('exportar_requerimento_digitalizado_pessoa', query)
        self.add_empty_line()
        self.log('INFO: Todos as pessoas que possuem compartilhamentos nos requerimentos digitalizados foram exportados.')

    def exportar_pessoas_para_distribuir(self):
        query = """
            select p.id, p.nome, count(1) as qt from pessoa p
            inner join processo_eletronico_solicitacaoassinaturacomanexacaoprocesso  sd on sd.pessoa_para_distribuir_id = p.id
            group by p.id, p.nome
            order by p.id;
        """
        self.log('INFO: Iniciando a exportacao das pessoas para distribuir das solicitações de assinatura com anexação de processo.')
        self.run_sql('exportar_pessoas_para_distribuir', query)
        self.add_empty_line()
        self.log('INFO: Todos as pessoas das solicitações de assinatura com anexação foram exportados.')

    def run(self):
        self.exportar_processo_interessados()
        self.exportar_processo_acompanhantes()
        self.exportar_comentario_processos()
        self.exportar_remetente_tramite()
        self.exportar_destinatario_tramite()
        self.exportar_remetente_solicitacao_despacho()
        self.exportar_requerimento_digitalizado()
        self.exportar_pessoas_para_distribuir()
        self.export_to_csv('processo_eletronico_pessoa_md5sum', self.data, path=self.wordir)

    def handle(self, *args, **options):
        self.wordir = options.get('directory')
        self.log_title(f'Processo Eletronico - {__name__}')

        self.add_empty_line()
        self.log(
            'O objetivo deste command eh varrer todos os modelos do módulo de processo eletronico\n'
            'e informar a quantidade de pessoa física associada a campos que vínculada a essa tabela.\n'
            'Por exemplo, quantos processos uma dada pessoa fisica esta vinculada como interessada.\n'
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
        self.log_title('Exportando os campos relativos a pessoas fisica nos modelos do processo eletronico')
        self.run()
        elapsed_time = datetime.datetime.now()
        self.log('Fim do processamento: {}'.format(elapsed_time.strftime('%d/%m/%Y - %H:%M:%S')))
        print(f'Duration: {elapsed_time - start_time}')
