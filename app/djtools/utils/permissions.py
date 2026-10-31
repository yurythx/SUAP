from django.contrib.auth.decorators import user_passes_test
from django.core.exceptions import PermissionDenied

from djtools.middleware import threadlocals as tl


def user_has_perm_or_without_request(perm, user=None):
    """
    Testa se o usuário tem a permissão caso haja um request no threadlocals.

    Args:
        perm ():
        user (User):

    Returns:
        *True* se existir um request.

    Note:
        Útil para ser utilizado no modelo, onde não se tem o request e também quando se deseja que quando não haja
        usuário logado seja "*True*" (exemplo: chamar função no shell do Django).
    """
    user = user or tl.get_user()
    if not user:
        return True
    return user.has_perm(perm)


def group_required(group, login_url=None, raise_exception=True):
    """
    Decora uma função para que seja testado se o usuário pertence ao grupo passado.

    Args:
        group (string): nome do grupo a testar;
        login_url (string): url para tela de login;
        raise_exception (bool): indica se é para disparar uma exceção se necessário;

    Raises:
        PermissionDenied caso o usuário não tenha permissão de acesso.

    Returns:
        Função decorada.
    """
    """Must be used as decorator."""

    def _in_group(user, group):
        from djtools.templatetags.filters import in_group

        allowed = in_group(user, group)
        # In case the 403 handler should be called raise the exception
        if user.is_authenticated and not allowed and raise_exception:
            raise PermissionDenied
        # As the last resort, show the login form
        return allowed

    return user_passes_test(lambda u: _in_group(u, group), login_url=login_url)


def permission_required(perms, login_url=None, raise_exception=True, logic_operator='or'):
    """
    Decoreito que especializa o **django.contrib.auth.decorators.permission_required** para chechar se o usuário pelo
    menos uma das permissões passadas.

    Args:
        perms (list ou string): lista contendo as permissões a serem testas;
        login_url (string): url para a tela de login;
        raise_exception (bool): indica se é para disparar uma exceção se necessário;
        logic_operator (string): operador lógico para executar em casa permissão, 'or' e 'and'.

    Raises:
        TypeError caso perms não seja uma lista ou uma string.
        PermissionDenied caso o usuário não passe nos testes da permissão.

    Returns:
        Função decorada.

    Note:
        Caso perms seja uma string ela será separada utilizando delimitador a virgula.
    """

    def check_perms(user):
        or_logic_operator = True
        allowed = False
        if logic_operator.lower() == 'and':
            or_logic_operator = False
            allowed = True

        def perform_logical_operation(value):
            if or_logic_operator:
                return allowed | value
            return allowed & value

        try:
            from collections.abc import Iterable
        except ImportError:  # Python 2.7 compatibility
            from collections.abc import Iterable

        # First check if it's instance of basestring because basestring is also iterable
        # is also iterable
        if isinstance(perms, str):
            perm_list = [p.strip() for p in perms.split(',')]
        elif isinstance(perms, Iterable):
            perm_list = [p.strip() for p in perms]
        else:
            raise TypeError('The first parameter must be a basestring or an iterable')

        if not user.is_authenticated:
            return False

        # First check if the user has the permission (even anon users)
        # permissions = perms.replace(',', 'or')
        # logging.info("PDP: check if %s has the permissions: %s" % (user, perms))
        for perm in perm_list:
            if user.has_perm(perm):
                allowed = perform_logical_operation(True)
            else:
                allowed = perform_logical_operation(False)

        # In case the 403 handler should be called raise the exception
        if not allowed and raise_exception:
            raise PermissionDenied

        return allowed

    return user_passes_test(check_perms, login_url=login_url)


def user_has_one_of_perms(user, perms):
    """
    Verifica se um usuário tem, no mínimo, uma das permissões passadas.

    Args:

        user (User): objeto do usuário a ser testado;
        perms (list): lista contendo as permissões a testar.

    Returns:
        True se o usuário tiver alguma das permissões passadas.

    """
    return any(user.has_perm(perm) for perm in perms)
