import datetime
import json
import logging
import socket

import tqdm
from django.conf import settings

from djtools.history import signals
from djtools.management.commands import BaseCommandPlus
from edu.models import Log

log = logging.getLogger('history')


class Command(BaseCommandPlus):
    def add_arguments(self, parser):
        futuro = (datetime.date.today() + datetime.timedelta(weeks=52 * 100)).strftime('%Y-%m-%d')
        parser.add_argument(
            '--data_inicio',
            '-dt_inicio',
            dest='data_inicio',
            action='store',
            default='2001-01-01',
            help='Data de início da verificação. Formato: AAAA-MM-DD',
        )
        parser.add_argument(
            '--data_fim', '-dt_fim', dest='data_fim', action='store', default=futuro, help='Data de término da verificação. Formato: AAAA-MM-DD'
        )

    def get_request_data(self, obj):
        user = obj.user
        host_name = getattr(settings, 'SERVER_ALIAS', None) or socket.gethostname()
        return {
            'last_update': str(obj.dt.isoformat()),
            'author': {'user_id': str(getattr(user, 'id', '-')), 'username': str(getattr(user, 'username', '-'))},
            'user_agent': 'manage.py edu_migrar_logs_history',
            'ip_address': '-',
            'url': '-',
            'server': str(host_name),
        }

    def handle(self, *args, **options):
        data_inicio = options.get('data_inicio')
        data_fim = options.get('data_fim')

        status_map = {
            Log.CADASTRO: signals.STATUS_CREATED,
            Log.EDICAO: signals.STATUS_UPDATED,
            Log.EXCLUSAO: signals.STATUS_DELETED,
            Log.VISUALIZACAO: signals.STATUS_VIEWED,
        }

        objs = Log.objects.filter(dt__gte=data_inicio)
        objs = objs.filter(dt__lte=data_fim).order_by('dt')
        for obj in tqdm.tqdm(objs):
            diff = []
            for reg in obj.registrodiferenca_set.all():
                diff.append({'old_value': reg.valor_anterior, 'new_value': reg.valor_atual, 'field': reg.campo})
            record = {
                'model': f'{obj.app}.{obj.modelo}',
                'pk': str(obj.ref),
                'status': status_map[obj.tipo],
                'diff': diff,
                'request': self.get_request_data(obj),
            }
            log.info(json.dumps(record))
