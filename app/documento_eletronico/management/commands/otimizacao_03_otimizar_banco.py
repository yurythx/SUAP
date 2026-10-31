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
        caminho_arquivo_corrente_sem_extensao = os.path.splitext(__file__)[0]
        self.log_file = f'{caminho_arquivo_corrente_sem_extensao}.log'

    def handle(self, *args, **options):
        self.log_title(f'Documento Eletrônico - {__name__}')

        self.add_empty_line()
        self.log(
            'O objetivo deste command é ZERAR o conteúdo dos atributos "cabecalho" e "rodape" SOMENTE dos documentos\n'
            'para os quais existem uma referência de cabeçalho e rodapé, otimizando assim o tamanho ocupado pelos\n'
            'documentos no banco de dados.'
        )

        self.add_empty_line()
        self.log('Recomendamos que, antes de executar este command, seja feito um backup completo do banco de dados.')

        if not self.ask_yes_or_no('Está ciente da necessidade do backup do banco?') or not self.ask_yes_or_no('Deseja continuar?'):
            self.add_empty_line()
            self.log('Processamento abortado.')
            return

        self.add_empty_line()
        self.log('Início do processamento: {}'.format(datetime.datetime.now().strftime('%d/%m/%Y - %H:%M:%S')))

        cursor = connection.cursor()

        self.add_separator()
        self.log(
            'ZERANDO as colunas "cabecalho" e "rodape", da tabela documento_eletronico_documentotexto, SOMENTE dos '
            'registros que tem referência de cabeçalho e rodapé.'
        )
        cursor.execute(
            """
                          UPDATE  documento_eletronico_documentotexto
                          SET     cabecalho = '', rodape = ''
                          WHERE   cabecalho_base_original_id IS NOT NULL
                                  AND rodape_base_original_id IS NOT NULL
                      """
        )
        self.log(f'Registros atualizados: {cursor.cursor.rowcount}')

        self.add_empty_line()
        self.log('Executando o comando VACUUM FULL na tabela documento_eletronico_documentotexto, para liberar o espaço não mais utilizado.')
        cursor.execute('VACUUM FULL documento_eletronico_documentotexto')

        connection._commit()

        self.add_empty_line()
        self.log('Otimização realizada COM SUCESSO!')

        self.add_empty_line()
        self.log('Fim do processamento: {}'.format(datetime.datetime.now().strftime('%d/%m/%Y - %H:%M:%S')))
        self.save_log(self.log_file)
        self.log(f'Log da operação salvo com sucesso em {self.log_file}', color='green', opts=('bold',))

        sys.setdefaultencoding(default_encoding)
