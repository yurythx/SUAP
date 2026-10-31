"""
Created on 25/02/2015

@author: misael
"""

import fnmatch
import os
import shutil
from abc import ABCMeta, abstractmethod

from django.db import connection
from django.utils import termcolors

from djtools.management.commands import BaseCommandPlus


class MediaCommand(BaseCommandPlus, metaclass=ABCMeta):
    """
    Essa classe foi criada visando oferecer um command intereativo e padronizado para a migração de toda a mídia exis-
    tente no SUAP.
    """

    def __init__(self, modulo, entidade, atributo, diretorio_antigo, diretorio_novo, fazer_perguntas=True):
        if not os.path.isdir(diretorio_antigo):
            raise Exception(f'Antigo diretório não existe ({diretorio_antigo})')

        # for dirpath, dirnames, files in os.walk(diretorio_antigo):
        #     if not files:
        #         print diretorio_antigo, dirnames, dirpath, files
        #         raise Exception('Antigo diretório não tem arquivos (%s)' % diretorio_antigo)

        BaseCommandPlus.__init__(self)
        self.modulo = modulo
        self.entidade = entidade
        self.atributo = atributo
        self.terminal = Terminal()
        self.diretorio_antigo = diretorio_antigo
        self.diretorio_novo = diretorio_novo
        self.fazer_perguntas = fazer_perguntas

    def execute_cmd(self, command):
        os.system(command)

    def execute_sql(self, command):
        cur = connection.cursor()
        cur.execute(command, None)  # o None é para o % não ser interpretado como interpolação nos LIKEs
        connection._commit()
        return cur.rowcount

    def handle(self, *args, **options):
        self.identificar_alvo_ajuste()
        self.emitir_alerta_backup()
        self.terminal.add_empty_line()

        if (not self.fazer_perguntas) or (self.pedir_permissao_para_executar_procedimento()):
            self.terminal.add_empty_line()
            self.executar_procedimento()

    def emitir_alerta_backup(self):
        self.terminal.log(f'ATENÇÃO: Antes de prosseguir realize o backup completo do diretório \n"{self.diretorio_antigo}".', color='red')
        self.terminal.log('Por questão de desempenho, ao invés de copiar os arquivos, eles serão movidos.', color='red')
        self.terminal.log('Por fim, arquivos do disco que não estiverem sendo referenciados no banco serão apagados.', color='red')

    def identificar_alvo_ajuste(self):
        self.terminal.add_separator()
        self.terminal.log(f'{self.modulo} - {self.entidade} - {self.atributo}')
        self.terminal.add_separator()
        self.terminal.log(f'Diretório antigo: {self.diretorio_antigo} ')
        self.terminal.log(f'Diretório novo: {self.diretorio_novo} ')
        self.terminal.add_separator()
        self.terminal.add_empty_line()

    def pedir_permissao_para_executar_procedimento(self):
        return self.terminal.ask_yes_or_no('O procedimento pode ser iniciado')

    @abstractmethod
    def executar_procedimento(self):
        pass


class Terminal:
    """
    Terminal oferece recursos de terminal e também de armazenamento de log em disco.
    """

    def __init__(self):
        self.internal_log = []

    def ask_yes_or_no(self, message):
        message = f'{message} (S/N)?'
        result = input(message).strip().upper() == 'S'

        if result:
            self.internal_log.append(message + ' S')
        else:
            self.internal_log.append(message + ' N')

        return result

    def log(self, message, color='white', opts=None, show=True):
        if isinstance(message, list):
            for m in message:
                self.internal_log.append(str(m))
        else:
            self.internal_log.append(message)

        if show:
            if opts:
                print(termcolors.make_style(fg=color, opts=(opts))(f'{message}\n'))
            else:
                print(termcolors.make_style(fg=color)(f'{message}\n'))

    def add_empty_line(self, show=True):
        self.log('', show=show)

    def add_separator(self, show=True):
        self.log('<<<<------------------------------------------------------------------------>>>>', show=show)

    def save_log(self, filename):
        FileUtils.create_text_file(filename, self.internal_log)

    def __str__(self):
        return '\n'.join(self.internal_log)


class FileUtils:
    """
    FileUtils tem por objetivo facilitar a manipulação de arquivos em disco.
    """

    @classmethod
    def get_file_names(cls, root_dir):
        result = []

        for root, _dirnames, filenames in os.walk(root_dir):
            for filename in fnmatch.filter(filenames, '*.*'):
                result.append(os.path.join(root, filename))

        return result

    @classmethod
    def copy_file(cls, origin, destiny):
        shutil.copy(origin, destiny)

    @classmethod
    def move(cls, origin, destiny):
        """
        Método que serve para mover/renomear arquivos e também diretórios completos.
        Args:
            origin: arquivo ou diretório
            destiny: arquivo ou diretório
        """
        shutil.move(origin, destiny)

    @classmethod
    def delete_dir(cls, directory):
        shutil.rmtree(directory)

    @classmethod
    def create_text_file(cls, filename, content):
        text_file = open(filename, 'w')
        text_file.writelines([f'{item}\n' for item in content])
        text_file.close()

    suffixes = ['B', 'KB', 'MB', 'GB', 'TB', 'PB']

    @classmethod
    def humansize(cls, nbytes):
        if nbytes == 0:
            return '0 B'
        i = 0
        while nbytes >= 1024 and i < len(cls.suffixes) - 1:
            nbytes /= 1024.0
            i += 1
        f = (f'{nbytes:.2f}').rstrip('0').rstrip('.')
        return f'{f} {cls.suffixes[i]}'

    @classmethod
    def filesize(cls, filename):
        return cls.humansize(os.path.getsize(filename))
