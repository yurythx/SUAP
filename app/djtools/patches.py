import django.http.response

MAX_REDIRECT_URL_LENGTH = 4096
django.http.response.MAX_URL_LENGTH = MAX_REDIRECT_URL_LENGTH
