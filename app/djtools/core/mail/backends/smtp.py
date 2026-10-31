"""
Default Email backend using smtp
"""

import datetime
import json
import logging
import sys

from django.conf import settings
from django.core.mail.backends.smtp import EmailBackend as EB

from djtools.models import EmailEnviadoLog

log = logging.getLogger('email')


def get_now_formatted():
    # timespec='microseconds' garante a fração sempre presente; sem ele, isoformat() omite
    # a fração quando microsecond == 0, gerando timestamp inválido para o parser do fluentbit (%L).
    return datetime.datetime.utcnow().isoformat(timespec='microseconds')


class EmailBackend(EB):
    def send_messages(self, email_messages):
        """
        Send one or more EmailMessage objects and return the number of email
        messages sent.
        """
        if not email_messages:
            return 0
        with self._lock:
            new_conn_created = self.open()
            if not self.connection or new_conn_created is None:
                # We failed silently on open().
                # Trying to send would be pointless.
                return 0
            num_sent = 0
            if settings.DEBUG_SMTP_CONNECTION:
                sys.stdout.write('==================================================\n')
                sys.stdout.write(f'SMTP connection opened to {self.host}:{self.port}\n')
                if self.username:
                    sys.stdout.write(f'Username: {self.username}\n')
                sys.stdout.write(f'Use TLS: {self.use_tls}, Use SSL: {self.use_ssl}\n')
                sys.stdout.flush()
                self.connection.set_debuglevel(2)
            for message in email_messages:
                sent = self._send(message)
                if sent:
                    try:  # Única parte alterada pelo suap
                        if 'db' in settings.EMAIL_LOGGING:
                            EmailEnviadoLog.objects.create(
                                assunto=message.subject, destinatarios=', '.join(message.to), conteudo=settings.DEBUG and message.body or ''
                            )
                        if 'file' in settings.EMAIL_LOGGING:
                            record = {'to': message.to, 'subject': message.subject, 'datetime': get_now_formatted()}
                            log.info(json.dumps(record))
                    except Exception:
                        pass
                    num_sent += 1
            if new_conn_created:
                self.close()
        return num_sent
