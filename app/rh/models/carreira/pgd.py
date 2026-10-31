from djtools.db import models


class ModalidadePGD(models.ModelPlus):
    SEARCH_FIELDS = ['nome']
    nome = models.CharFieldPlus('Nome', max_length=100, unique=True)

    class Meta:
        verbose_name = 'Modalidade PGD WS'
        verbose_name_plural = 'Modalidades PGD WS'

    def __str__(self):
        return self.nome
