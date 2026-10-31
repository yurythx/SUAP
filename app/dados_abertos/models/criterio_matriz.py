from djtools.db import models
from djtools.db.models import ModelPlus
from django.utils.translation import gettext_lazy as _


class CriterioMatriz(ModelPlus):
    SEARCH_FIELDS = [
        'nome',
    ]

    nome = models.CharFieldPlus(_('Nome'), max_length=800, unique=True)
    ativo = models.BooleanField(_('Ativo'), default=True)

    data_cadastro = models.DateTimeFieldPlus(_('Data de Cadastro'), auto_now_add=True, null=True, blank=True)
    data_atualizacao = models.DateTimeFieldPlus(_('Data de Atualização'), auto_now=True, null=True, blank=True)

    class Meta:
        verbose_name = _('Critério da Matriz')
        verbose_name_plural = _('Critérios da Matriz')

    def __str__(self):
        return self.nome
