from django.contrib.auth import get_permission_codename

from djtools.middleware import threadlocals as tl


def get_delete_permission_for_model(model):
    """
    Obtem a string da permissão de delete para um modelo.

    Args:
        model (Model): modelo a gerar a permissão.

    Returns:
        String com a permissão solicitada.
    """
    return model._meta.app_label + '.' + get_permission_codename('delete', model._meta)


def has_delete_permission(model=None, obj=None, user=None):
    """
    Verifica se o usuário tem permissão de 'delete' para o modelo passado ou para o objeto.

    Args:
        model (Model): modelo a verificar permissão;
        obj (Objeto): objeto para verificar se tem permissão;
        user (User): usuário a testar permissão.

    Returns:
        True se o usuário tiver permissão de 'delete'.

    Note:
        Além das permissões normais é verificado se foi implementado o método can_delete(user) no modelo, se isso
        ocorrer o método é invocado também.
    """
    user = user or tl.get_user()
    if not user:
        return False
    if model is None and obj:
        model = obj.__class__

    if not user.has_perm(get_delete_permission_for_model(model)):
        return False
    if hasattr(obj, 'can_delete'):
        return obj.can_delete(user=user)
    return True


def get_change_permission_for_model(model):
    """
    Obtem a string da permissão de edit para um modelo.

    Args:
        model (Model): modelo a gerar a permissão.

    Returns:
        String com a permissão solicitada.
    """
    return model._meta.app_label + '.' + get_permission_codename('change', model._meta)


def has_change_permission(model, obj=None, user=None):
    """
    Verifica se o usuário tem permissão de 'change' para o modelo passado.

    Args:
        model (Model): modelo a verificar permissão;
        obj (Objeto): objeto para verificar se tem permissão;
        user (User): usuário a testar permissão.

    Returns:
        True se o usuário tiver permissão de 'change'.
    """
    user = user or tl.get_user()
    if not user:
        return False
    if model is None and obj:
        model = obj.__class__

    if not user.has_perm(get_change_permission_for_model(model)):
        return False
    if hasattr(obj, 'can_change'):
        return obj.can_change(user=user)
    return True


def get_view_permission_for_model(model):
    """
    Obtem a string da permissão de view para um modelo.

    Args:
        model (Model): modelo a gerar a permissão.

    Returns:
        String com a permissão solicitada.
    """
    return model._meta.app_label + '.' + get_permission_codename('view', model._meta)


def has_view_permission(model, obj=None, user=None):
    """
    Verifica se o usuário tem permissão de 'view' para o modelo passado.

    Args:
        model (Model): modelo a verificar permissão;
        user (User): usuário a testar permissão.

    Returns:
        True se o usuário tiver permissão de 'view'.
    """
    user = user or tl.get_user()
    if not user:
        return False
    if model is None and obj:
        model = obj.__class__

    if not user.has_perm(get_view_permission_for_model(model)) and not user.has_perm(get_change_permission_for_model(model)):
        return False
    if hasattr(obj, 'can_view'):
        return obj.can_view(user=user)
    return True


def get_add_permission_for_model(model):
    """
    Obtem a string da permissão de add para um modelo.

    Args:
        model (Model): modelo a gerar a permissão.

    Returns:
        String com a permissão solicitada.
    """
    return model._meta.app_label + '.' + get_permission_codename('add', model._meta)


def has_add_permission(model, user=None):
    """
    Verifica se o usuário tem permissão de 'add' para o modelo passado.

    Args:
        model (Model): modelo a verificar permissão;
        user (User): usuário a testar permissão.

    Returns:
        True se o usuário tiver permissão de 'add'.
    """
    user = user or tl.get_user()
    if not user:
        return False
    return user.has_perm(get_add_permission_for_model(model))


#################
# ChainedSelect #
#################
