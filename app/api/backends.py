from oauth2_provider.scopes import SettingsScopes
from oauth2_provider.settings import oauth2_settings


class SuapScopes(SettingsScopes):
    """
    Classe apontada por settings.OAUTH2_PROVIDER.SCOPES_BACKEND_CLASS e criada para customizar o comportamento de
    pegar os default scopes da app, retornando os definidos em settings.OAUTH2_PROVIDER.DEFAULT_SCOPES mais os
    definidos em app.granted_scopes, sendo este comportamento apenas para apps com skip_authorization True.
    """

    def get_default_scopes(self, application=None, request=None, *args, **kwargs):
        default_scopes = oauth2_settings._DEFAULT_SCOPES[:]
        if application.skip_authorization:
            return default_scopes + application.granted_scopes.split()
        return default_scopes
