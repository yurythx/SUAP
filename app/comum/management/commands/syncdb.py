import os

from django.core.management.commands import syncdb as _syncdb

os.environ['USUARIOGRUPO_AS_ABSTRACT'] = '1'


class Command(_syncdb.Command):
    pass
