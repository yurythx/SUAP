"""
Email backend that writes messages to console instead of sending them.
"""

import datetime
import json
import logging

from django.conf import settings
from django.core.mail.backends.console import EmailBackend as EB

from djtools.models import EmailEnviadoLog

log = logging.getLogger('email')


def get_now_formatted():
    # timespec='microseconds' garante a fração sempre presente; sem ele, isoformat() omite
    # a fração quando microsecond == 0, gerando timestamp inválido para o parser do fluentbit (%L).
    return datetime.datetime.utcnow().isoformat(timespec='microseconds')


class EmailBackend(EB):
    def send_messages(self, email_messages):
        """Write all messages to the stream in a thread-safe way."""
        if not email_messages:
            return
        msg_count = 0
        lista = []
        with self._lock:
            try:
                stream_created = self.open()
                for message in email_messages:
                    self.write_message(message)
                    self.stream.flush()  # flush after each message
                    lista.append({'from_email': message.from_email, 'to': ', '.join(message.to), 'message': message.body})
                    if 'db' in settings.EMAIL_LOGGING:
                        EmailEnviadoLog.objects.create(
                            assunto=message.subject, destinatarios=', '.join(message.to), conteudo=settings.DEBUG and message.body or ''
                        )
                    if 'file' in settings.EMAIL_LOGGING:
                        record = {'to': message.to, 'subject': message.subject, 'datetime': get_now_formatted()}
                        log.info(json.dumps(record))
                    msg_count += 1
                with open('deploy/emails.json', 'w') as f:
                    f.write(json.dumps(lista))
                if stream_created:
                    self.close()
            except Exception:
                if not self.fail_silently:
                    raise
        return msg_count
