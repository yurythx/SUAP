from django.db import models

from djtools.utils import eval_attr, to_ascii


class SearchField(models.TextField):
    """
    Campo utilizado para buscas, recebendo uma lista de atributos da instância
    (``attrs``) e os convertendo para valores de forma (``prepare_string``) a
    tornar as buscas mais eficientes.
    """

    @staticmethod
    def prepare_string(v):
        return str(to_ascii(v).upper().strip())

    def pre_save(self, model_instance, add):
        search_text = []
        if not hasattr(self, 'search_attrs'):
            return model_instance.__getattribute__(self.name)

        for attr_name in self.search_attrs:
            val = eval_attr(model_instance, attr_name)
            if val:  # Evitar string `NONE`
                val = self.prepare_string(val)
                search_text.append(val)
        return ' '.join(search_text)

    def __init__(self, *args, **kwargs):
        if 'attrs' in kwargs:
            self.search_attrs = kwargs.pop('attrs')
        kwargs.setdefault('blank', True)
        kwargs.setdefault('default', '')
        kwargs.setdefault('editable', False)
        super().__init__(*args, **kwargs)
