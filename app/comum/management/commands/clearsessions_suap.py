import datetime
import os

import tqdm
from django.conf import settings
from django.contrib.sessions.backends.cache import SessionStore
from django.core.cache import caches
from django_redis import get_redis_connection

from comum.models import SessionInfo
from djtools.management.commands import BaseCommandPlus
from djtools.utils import datetime_to_ordinal


class Command(BaseCommandPlus):
    help = 'Remove expired session files (default clearsessions django command only works with database backend, see command help attribute)'

    def add_arguments(self, parser):
        parser.add_argument('-a', '--all', action='store_true', help='Limpa todos as sessões')

    def _limpar_sessoes_arquivo(self, file_min_mtime):
        """Remove os arquivos de sessão expirados (backend de arquivo). Retorna (total, removidos)."""
        total_files, removed_files = 0, 0
        for file_ in os.listdir(settings.SESSION_FILE_PATH):
            if not file_.startswith(settings.SESSION_COOKIE_NAME):
                continue
            total_files += 1
            file_path = os.path.join(settings.SESSION_FILE_PATH, file_)
            if os.path.getmtime(file_path) < file_min_mtime:
                os.remove(file_path)
                removed_files += 1
        return total_files, removed_files

    def handle(self, *args, **options):
        verbosity = options.get('verbosity', 3)
        todos = options.get('all', False)
        if todos:
            relativedelta = datetime.datetime.now() + datetime.timedelta(seconds=settings.SESSION_COOKIE_AGE)
        else:
            relativedelta = datetime.datetime.now() - datetime.timedelta(seconds=settings.SESSION_COOKIE_AGE)
        file_min_mtime = datetime_to_ordinal(relativedelta)

        total_files, removed_files = 0, 0
        if not settings.USE_REDIS:
            total_files, removed_files = self._limpar_sessoes_arquivo(file_min_mtime)

        _cache = caches[settings.SESSION_CACHE_ALIAS]

        if settings.USE_REDIS:
            contador = get_redis_connection(settings.SESSION_CACHE_ALIAS).dbsize()
        else:
            contador = 0

        qs = SessionInfo.objects.filter(date_time__lte=relativedelta, expired=False)
        limpos = 0

        if verbosity:
            qs = tqdm.tqdm(qs)

        for session_info in qs:
            SessionStore(session_key=session_info.session_id).delete()
            session_info.expired = True
            session_info.save()
            limpos += 1

        if todos and settings.USE_REDIS:
            limpos += _cache.clear()

        if verbosity:
            if settings.USE_REDIS:
                self.stdout.write(self.style.SQL_COLTYPE(f'{limpos}/{contador} sessões do redis finalizadas'))
            else:
                self.stdout.write(self.style.SQL_COLTYPE(f'{removed_files}/{total_files} sessões de arquivo finalizadas'))
