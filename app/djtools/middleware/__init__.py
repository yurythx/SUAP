from django.contrib.sessions.middleware import SessionMiddleware

from .session_middleware import process_response

SessionMiddleware.process_response = process_response
