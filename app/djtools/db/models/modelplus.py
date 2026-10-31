import base64
from typing import Any

from Crypto.Cipher import AES
from django.conf import settings
from django.db import models

from djtools.lps import MetaModelPlus
from djtools.templatetags.filters import getattr_anonymize

from .helpers import _search


class SUAPMetaModel(MetaModelPlus):
    def __new__(cls, name, *args, **kwargs):
        my_meta = super().__new__(cls, name, *args, **kwargs)
        my_meta._meta.default_permissions = ('add', 'change', 'delete', 'view')
        # view_permission_tuple = (('view_' + my_meta._meta.model_name, u'Pode visualizar {}'.format(my_meta._meta.verbose_name)),)
        # if my_meta._meta.permissions:
        #     if not view_permission_tuple[0] in [x for x, y in my_meta._meta.permissions]:
        #         my_meta._meta.permissions += view_permission_tuple
        # else:
        #     my_meta._meta.permissions = view_permission_tuple

        return my_meta


class ModelPlus(models.Model, metaclass=SUAPMetaModel):
    """A models.Model with facilities"""

    class Meta:
        abstract = True

    def __repr__(self):
        return f'{self.__class__.__module__}.{self.__class__.__name__} #{self.pk} - "{self.__str__()}"'

    def __str__(self):
        for f in self.__class__._meta.fields:
            if f.get_internal_type() in ['CharField', 'TextField']:
                value = getattr(self, f.name)
                if value:
                    return value
        return f'{self.__class__._meta.verbose_name} {self.pk}'

    @classmethod
    def search(cls, q, fields=None, max_fields=5):
        return _search(cls, q, fields=fields, max_fields=max_fields)

    @classmethod
    def _get_first_null_char_field(cls, instance, force_attr=None):
        if force_attr:
            return instance._meta.get_field(force_attr)

        for f in instance._meta.fields:
            if f.get_internal_type() in ['CharField', 'TextField'] and not getattr(instance, f.name):
                return f

        return None

    @classmethod
    def get_or_create(cls, fill_attr=None, **kwargs):
        """A short to objects.get_or_create
        By pass the kwargs arguments to objects.get_or_create class method,
        if its has created the object, this get_or_create will filled the fill_attr attribute, if is not None,
        with a message to update the objects.
        If fill_attr is None it will fill the first null char (or text) field.
        """

        o, created = cls.objects.get_or_create(**kwargs)
        if created:
            f = cls._get_first_null_char_field(o, fill_attr)
            if f:
                c = f'Atualize o cadastro de {cls._meta.verbose_name_plural}'
                c = c[: f.max_length]
                setattr(o, f.name, c)
                o.save()

        return o, created

    # @classmethod
    # def _case_ordering_relevance(cls, list_relevance):
    #     whens = []
    #     for cont, order_ in enumerate(list_relevance):
    #         whens.append(When(Q(order_), then=Value(cont)))
    #     case = Case(*whens, output_field=IntegerField(), default=cont+1)
    #     return case

    def _get_search_fields_optimized_content_to_save(self):
        """
        Esse método retorna o conteúdo que deverá ser armazenado no atributo search_fields_optimized. As classes filhas
        deverão sobreescrever esse método para personalizar essa informação.
        :return: texto
        """
        raise NotImplementedError('Método _get_search_fields_optimized_content_to_save não implementado.')

    def save(self, *args: Any, **kwargs: Any) -> None:
        # Ajustando as informações reduntantes que serão usadas para uma busca mais eficiente na entidade.
        if hasattr(self, 'search_fields_optimized'):
            # ponytail: cortado no tamanho da coluna: o conteúdo de busca de qualquer model pode passar do max_length, e o fim do texto
            # deixa de entrar na busca (ex.: a PF sobrevivente de uma mescla grande, cujos usernames vêm por último). Upgrade: TextField + trigram.
            self.search_fields_optimized = self._cortar_busca(self._get_search_fields_optimized_content_to_save())
        return super().save(*args, **kwargs)

    def _cortar_busca(self, conteudo: str) -> str:
        # o atributo pode não ser campo do próprio model: o Servidor o repassa da pessoa física (AbstractFuncionario.__getattr__)
        limite = next((campo.max_length for campo in self._meta.concrete_fields if campo.name == 'search_fields_optimized'), None)
        return conteudo[:limite] if limite else conteudo

    def getattr(self, campo, request=None, justification=None):
        return getattr_anonymize(self, campo, request, justification)


class EncryptedPKModel(ModelPlus):
    """Adds encrypted_pk property to children which returns the encrypted value of the primary key."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        setattr(self.__class__, f'encrypted_{self._meta.pk.name}', property(self.__class__._encrypted_pk))

    def _encrypted_pk(self):
        pk = self.pk
        return encrypt_val(pk)

    encrypted_pk = property(_encrypted_pk)

    class Meta:
        abstract = True


def encrypt_val(clear_text):
    enc_secret = AES.new(settings.SECRET_KEY[:32].encode(), mode=AES.MODE_ECB)
    tag_string = str(clear_text) + (AES.block_size - len(str(clear_text)) % AES.block_size) * '\0'
    cipher_text = base64.b64encode(enc_secret.encrypt(tag_string.encode())).hex()
    return cipher_text


def decrypt_val(cipher_text):
    dec_secret = AES.new(settings.SECRET_KEY[:32].encode(), mode=AES.MODE_ECB)
    unhex = bytearray.fromhex(cipher_text).decode()
    raw_decrypted = dec_secret.decrypt(base64.b64decode(unhex))
    clear_val = raw_decrypted.decode().rstrip('\0')
    return clear_val
