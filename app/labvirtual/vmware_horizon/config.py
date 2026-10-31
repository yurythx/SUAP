from .auth import Auth


class Config:
    def __init__(self, auth: Auth) -> None:
        self.auth: Auth = auth

    @property
    def base_endpoint(self):
        return f'{self.auth.REST_API}/config'

    def mount_url(self, endpoint: str, api_version: str = 'v1') -> str:
        return f'/config/{api_version}/{endpoint}'
