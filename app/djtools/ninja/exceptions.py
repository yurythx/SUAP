from ninja.errors import HttpError


class AccessDenied(HttpError):
    def __init__(self, message='Acesso negado'):
        super().__init__(403, message)
