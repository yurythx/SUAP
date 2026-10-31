from django.contrib.auth.backends import ModelBackend

from comum.exceptions import UserMustResetPassword
from comum.models import User


class ModelBackendPlus(ModelBackend):
    """
    Authenticates against settings.AUTH_USER_MODEL.
    """

    def authenticate(self, request, username=None, password=None, **kwargs):
        if username is None:
            username = kwargs.get(User.USERNAME_FIELD)
        if username is None or password is None:
            return
        try:
            user = User._default_manager.get_by_natural_key(username)
        except User.DoesNotExist:
            # Run the default password hasher once to reduce the timing
            # difference between an existing and a nonexistent user (#20760).
            User().set_password(password)
        else:
            if user.forcar_troca_senha:
                _vinculo = user.get_vinculo()
                if _vinculo and _vinculo.email_notificacao:
                    exception = UserMustResetPassword(
                        'É necessário alterar sua senha antes do próximo login. Preencha o formulário de alteração de senha e clique em "Enviar".'
                    )
                    raise exception
                else:
                    exception = UserMustResetPassword(
                        'É necessário alterar sua senha antes do próximo login, mas você não possui um e-mail secundário cadastrado. Por favor, entre em contato com o coordenação de TI do seu campus para resolver essa situação.'
                    )
                    exception.redirect_url = '/'
                    raise exception
            if user.check_password(password):
                return user
