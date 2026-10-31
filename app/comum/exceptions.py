class UserMustResetPassword(Exception):
    redirect_url = '/comum/solicitar_trocar_senha/'


class LoginException(Exception):
    pass


class BusinessRuleFailure(Exception):
    pass
