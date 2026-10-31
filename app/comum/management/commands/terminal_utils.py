"""
Created on 12/03/2018

@author: misael
"""

import fnmatch
import os
import shutil

from django.utils import termcolors


class Terminal:
    """
    Terminal oferece recursos de terminal e também de armazenamento de log em disco.
    """

    def __init__(self):
        print('Chamando construtor de Terminal....')
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
            self.internal_log.append(str(message))

        if show:
            if opts:
                print(termcolors.make_style(fg=color, opts=(opts))(f'{message}\n'))
            else:
                print(termcolors.make_style(fg=color)(f'{message}\n'))

    def log_title(self, title):
        self.add_empty_line()
        self.log('-' * len(title))
        self.log(title)
        self.log('-' * len(title))

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
        text_file.write('\n'.join(content))
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
