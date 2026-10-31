import datetime
from functools import wraps

from djtools.utils import (
    tl,
)


def registra_atualizado_por(modelo):
    def salvar_atualizacao_por(original_save):
        @wraps(original_save)
        def atualiza_usuario(self, *args, **kwargs):
            if hasattr(self, 'ultima_atualizacao_por') and getattr(self, 'id', None) is not None and tl.get_user():
                self.ultima_atualizacao_por = tl.get_user()

                if hasattr(self, 'ultima_atualizacao_em'):
                    self.ultima_atualizacao_em = datetime.datetime.now()
            original_save(self, *args, **kwargs)

        return atualiza_usuario

    modelo.save = salvar_atualizacao_por(modelo.save)
    return modelo
