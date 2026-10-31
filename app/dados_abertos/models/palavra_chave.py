from djtools.db import models
from djtools.db.models import ModelPlus
from django.utils.translation import gettext_lazy as _


class PalavraChave(ModelPlus):
    SEARCH_FIELDS = ['termo']

    termo = models.CharFieldPlus(_('Palavra-chave'), max_length=100, unique=True)

    data_cadastro = models.DateTimeFieldPlus(_('Data de Cadastro'), auto_now_add=True, null=True, blank=True)
    data_atualizacao = models.DateTimeFieldPlus(_('Data de Atualização'), auto_now=True, null=True, blank=True)

    class Meta:
        verbose_name = _('Palavra-chave')
        verbose_name_plural = _('Palavras-chave')

    def __str__(self):
        return self.termo
