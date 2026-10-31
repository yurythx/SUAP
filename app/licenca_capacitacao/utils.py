def get_e(e):
    erro = e
    try:
        return e.messages[0]
    except Exception:
        return erro


def eh_servidor(user):
    return hasattr(user.get_relacionamento(), 'eh_servidor') and user.get_relacionamento().eh_servidor
