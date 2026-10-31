from django.db import models

import djtools.forms.fields as formfields
from djtools.utils import tl


class ForeignKeyPlus(models.ForeignKey):
    """
    Deixa o widget padrão o ModelChoiceFieldPlus quando se tem mais de 50 registros.
    """

    def __init__(self, *args, **kwargs):
        kwargs.setdefault('on_delete', models.CASCADE)
        super().__init__(*args, **kwargs)

    def formfield(self, **kwargs):
        kwargs.setdefault('form_class', formfields.ModelChoiceFieldPlus)
        return super(self.__class__, self).formfield(**kwargs)


class CurrentUserField(models.ForeignKey):
    """
    Utilizado para armazenar o usuário autenticado.
    """

    def __init__(self, *args, **kwargs):
        from comum.models import User

        kwargs.setdefault('on_delete', models.CASCADE)
        kwargs.setdefault('editable', False)
        self.null_attr_value = kwargs.setdefault('null', True)

        kwargs.setdefault('blank', True)
        kwargs.setdefault('to', User)
        kwargs.setdefault('default', tl.get_user)
        super().__init__(*args, **kwargs)

    def deconstruct(self):
        name, path, args, kwargs = super().deconstruct()
        kwargs['null'] = self.null_attr_value
        return name, path, args, kwargs

    def get_default(self):
        # Valor cru do default (a instância de usuário ou None), antes de a
        # ForeignKey convertê-lo em pk. tl.get_user() devolve request.user, que em
        # requisição anônima (ou por vazamento de threadlocal entre testes) é um
        # AnonymousUser: não é uma FK válida e quebraria o INSERT com "Field 'id'
        # expected a number". Trata como ausência de usuário.
        value = models.Field.get_default(self)
        if value is not None and not getattr(value, 'is_authenticated', False):
            return None
        return super().get_default()


class OneToOneFieldPlus(models.OneToOneField):
    """
    Deixa o widget padrão o ModelChoiceFieldPlus.
    """

    def __init__(self, *args, **kwargs):
        kwargs.setdefault('on_delete', models.CASCADE)
        super().__init__(*args, **kwargs)

    def formfield(self, **kwargs):
        kwargs.setdefault('form_class', formfields.ModelChoiceFieldPlus)
        return super(self.__class__, self).formfield(**kwargs)


class ManyToManyFieldPlus(models.ManyToManyField):
    """
    Deixa o widget padrão o MultipleModelChoiceFieldPlus.
    """

    def formfield(self, **kwargs):
        kwargs.setdefault('form_class', formfields.MultipleModelChoiceFieldPlus)
        return super(self.__class__, self).formfield(**kwargs)
