import datetime
import importlib
import os

# Evita o erro "UnicodeEncodeError: 'ascii' codec can't encode character u'\xe9' in position 53: ordinal not in range(128)"
import sys

from django.db import connection

from comum.management.commands.terminal_utils import Terminal
from djtools.management.commands import BaseCommandPlus

importlib.reload(sys)
default_encoding = sys.getdefaultencoding()
sys.setdefaultencoding('utf8')


class Command(Terminal, BaseCommandPlus):
    def __init__(self):
        Terminal.__init__(self)
        self.cursor = connection.cursor()

        # Dados que podem ser redefinidos caso seja necessário executar este mesmo command em momento posterior.
        self.estagio_consulta = 'ANTES'
        caminho_arquivo_corrente_sem_extensao = os.path.splitext(__file__)[0]
        self.log_file = f'{caminho_arquivo_corrente_sem_extensao}.log'

    def fetchall_as_dict(self):
        """
        Método que retorna uma lista de registros, onde cada registro é um dicionário.
        Ref: https://docs.djangoproject.com/en/2.0/topics/db/sql/#executing-custom-sql-directly
        """
        columns = [col[0] for col in self.cursor.description]
        return [dict(list(zip(columns, row, strict=False))) for row in self.cursor.fetchall()]

    def consultar_dados_sobre_documentos_alvo_processamento(self):
        self.cursor.execute(
            """
                                SELECT  COUNT(*) as qtd_docs_total,
                                        SUM(CASE WHEN cabecalho_base_original_id IS NOT NULL THEN 1 ELSE 0 END) AS qtd_docs_com_referencia_cabecalho,
                                        SUM(CASE WHEN cabecalho_base_original_id IS NULL THEN 1 ELSE 0 END) as qtd_docs_sem_referencia_cabecalho,
                                        SUM(CASE WHEN cabecalho_base_original_id IS NULL AND EXISTS (SELECT * FROM documento_eletronico_assinaturadocumentotexto WHERE documento_id = dt.id) THEN 1 ELSE 0 END) as qtd_docs_sem_referencia_cabecalho_e_com_assinatura,
                                        SUM(CASE WHEN cabecalho_base_original_id IS NULL AND NOT EXISTS (SELECT * FROM documento_eletronico_assinaturadocumentotexto WHERE documento_id = dt.id) THEN 1 ELSE 0 END) as qtd_docs_sem_referencia_cabecalho_e_sem_assinatura
                                FROM    documento_eletronico_documentotexto dt;
                            """
        )
        row = self.fetchall_as_dict()[0]

        self.log('Documentos (entidade DocumentoTexto):')
        self.log(' - Total: {}'.format(row['qtd_docs_total']))
        self.log(' - Com Ref. de Cabeçalho/Rodapé: {}'.format(row['qtd_docs_com_referencia_cabecalho']))
        self.log(' - Sem Ref. de Cabeçalho/Rodapé: {}'.format(row['qtd_docs_sem_referencia_cabecalho']))
        self.log(' - Sem Ref. de Cabeçalho/Rodapé e Assinados: {}'.format(row['qtd_docs_sem_referencia_cabecalho_e_com_assinatura']))
        self.log(' - Sem Ref. de Cabeçalho/Rodapé e Não Assinados: {}'.format(row['qtd_docs_sem_referencia_cabecalho_e_sem_assinatura']))

    def consultar_tamanho_banco_e_tabelas(self):
        self.cursor.execute('SELECT current_database() as nome_banco, pg_size_pretty(pg_database_size(current_database())) as tamanho_banco;')
        row = self.fetchall_as_dict()[0]
        self.log('Banco de Dados:')
        self.log(' - Nome: {}'.format(row['nome_banco']))
        self.log(' - Tamanho: {}'.format(row['tamanho_banco']))

        self.cursor.execute(
            """
                                SELECT  -- oid,
                                        -- table_schema,
                                        table_name,
                                        rows_number,
                                        -- Size In Bytes
                                        index_bytes,
                                        toast_bytes,
                                        table_bytes,
                                        total_bytes,
                                        -- Size In MB, GB, TB
                                        pg_size_pretty(index_bytes) AS index_size,
                                        pg_size_pretty(toast_bytes) AS toast_size,
                                        pg_size_pretty(table_bytes) AS table_size,
                                        pg_size_pretty(total_bytes) AS total_size
                                FROM    (
                                            SELECT  *,
                                                    total_bytes - index_bytes - COALESCE(toast_bytes,0) AS table_bytes
                                            FROM    (
                                                      SELECT  c.oid,
                                                              nspname AS table_schema,
                                                              relname AS table_name,
                                                              c.reltuples AS rows_number,
                                                              pg_indexes_size(c.oid) AS index_bytes,
                                                              -- Toast is a mechanism PostgreSQL uses to keep physical data rows from exceeding the size of a data block (typically 8KB).
                                                              -- https://www.postgresql.org/docs/8.3/static/storage-toast.html
                                                              pg_total_relation_size(c.reltoastrelid) AS toast_bytes,
                                                              pg_total_relation_size(c.oid) AS total_bytes
                                                      FROM    pg_class c
                                                      LEFT    JOIN pg_namespace n ON n.oid = c.relnamespace
                                                      WHERE   relkind = 'r'
                                                              -- AND relname LIKE '%documento_ele%'
                                                    ) x
                                        ) y
                                WHERE   table_name IN ('documento_eletronico_documentotexto', 'documento_eletronico_tipodocumentotextohistoricoconteudo')
                                ORDER    BY total_bytes DESC;
                            """
        )
        rows = self.fetchall_as_dict()
        self.add_empty_line()
        self.log('Tabelas envolvidas na otimizacão: ')
        for row in rows:
            self.log(' - Nome: {},  Tamanho: {}'.format(row['table_name'], row['total_size']))

    def handle(self, *args, **options):
        self.log_title(f'Documento Eletrônico - {__name__}')

        self.add_empty_line()
        self.log(
            f'O objetivo deste command é exibir algumas informações acerca do banco de dados {self.estagio_consulta} da execução dos '
            'commands que realizam a otimização dos documentos eletrônicos.'
        )

        self.add_empty_line()
        self.log('Início do processamento: {}'.format(datetime.datetime.now().strftime('%d/%m/%Y - %H:%M:%S')))

        self.add_empty_line()
        self.log(f'Dados do banco {self.estagio_consulta} de executar a otimização')
        self.add_separator()

        self.consultar_tamanho_banco_e_tabelas()

        self.add_empty_line()
        self.consultar_dados_sobre_documentos_alvo_processamento()

        self.add_empty_line()
        self.log('Fim do processamento: {}'.format(datetime.datetime.now().strftime('%d/%m/%Y - %H:%M:%S')))
        self.save_log(self.log_file)
        self.log(f'Log da operação salvo com sucesso em {self.log_file}', color='green', opts=('bold',))

        self.cursor.close()
        sys.setdefaultencoding(default_encoding)
