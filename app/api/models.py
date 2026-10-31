from django.conf import settings
from django.db.models import Manager
from django.utils.translation import gettext_lazy as _
from oauth2_provider.models import AbstractApplication

from djtools.db import models


class AplicacaoOAuth2Manager(Manager):
    def get_queryset(self):
        return super().get_queryset().filter(active=True)


class AplicacaoOAuth2(AbstractApplication):
    """

    Trusted Apps:

        Apps com skip_authorization = True são consideradas trusted e apenas os
        administradores do SUAP podem tornar uma app trusted. Trusted apps podem ter scopes concedidos via atributo
        `granted_scopes`.

        Uma trusted app já tem acesso a uma série de serviços globais, tais como: consulta de servidores, setores,
        campi etc. Porém, permissões especiais via `granted_scopes` podem ser exigidas (ex: contracheques).

    Como Obter um AccessToken de uma app com client-credentials grant:

        curl -X POST -d "client_id=<client_id>&client_secret=<client_secret>&grant_type=client_credentials" <suap_url>/o/token/

    Fields:

        * `authorization_grant_type`:
            - foi redefinido para retirar GRANT_PASSWORD dos choices.
        * `granted_scopes`:
            - serve para definir os scopes, além dos DEFAULT_SCOPES, que a app tem acesso (só tem efeito caso a
              app tenha skip_authorization = True).
            - deixamos TextField para scopes para combinar com AbstractAccessToken.scope, o que evita migrations
              quando houver novos scopes mas exige que o programador trate os scopes disponíveis no form de edição.
    """

    GRANT_TYPES = (
        (AbstractApplication.GRANT_AUTHORIZATION_CODE, _('Authorization code')),
        (AbstractApplication.GRANT_IMPLICIT, _('Implicit')),
        (AbstractApplication.GRANT_CLIENT_CREDENTIALS, _('Client credentials')),
    )
    authorization_grant_type = models.CharField(max_length=32, choices=GRANT_TYPES)
    granted_scopes = models.TextField(blank=True)
    user = models.ForeignKeyPlus(
        settings.AUTH_USER_MODEL,
        related_name='%(app_label)s_%(class)s',
        null=True,
        blank=True,
        on_delete=models.CASCADE,
    )
    active = models.BooleanField(default=True, verbose_name='Ativo')
    keep_session = models.BooleanField(
        'Manter Sessão',
        default=False,
        blank=True,
        help_text='Marque essa opção caso deseje que o SUAP não feche a sessão depois de 10 seg do envio do token.',
    )
    # https://django-oauth-toolkit.readthedocs.io/en/latest/settings.html ALLOWED_REDIRECT_URI_SCHEMES
    allowed_schemes = models.TextField(verbose_name='Esquemas Permitidos', null=True, blank=True, help_text='Separados por espaço. Ex: "http https"')
    objects = AplicacaoOAuth2Manager()
    full = Manager()

    class Meta:
        ordering = ['id']
        verbose_name = 'Aplicação OAUTH2'
        verbose_name_plural = 'Aplicações OAUTH2'

    def get_absolute_url(self):
        return f'/admin/api/aplicacaooauth2/{self.pk}/view/'

    def __str__(self):
        return self.name

    def get_allowed_schemes(self):
        if self.allowed_schemes:
            return self.allowed_schemes.split()
        return super().get_allowed_schemes()
