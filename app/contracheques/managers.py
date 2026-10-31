from django.apps import apps
from django.db import models


class ContraChequeQueryset(models.QuerySet):
    def fita_espelho(self):
        ContraCheque = apps.get_model('contracheques', 'ContraCheque')
        return self.filter(tipo_importacao=ContraCheque.IMPORTACAO_FITA_ESPELHO)

    def webservice(self):
        ContraCheque = apps.get_model('contracheques', 'ContraCheque')
        return self.filter(tipo_importacao=ContraCheque.IMPORTACAO_WS)

    def ativos(self):
        return self.filter(excluido=False)
