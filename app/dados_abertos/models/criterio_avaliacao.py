from djtools.db import models
from djtools.db.models import ModelPlus
from django.utils.translation import gettext_lazy as _


class CriterioAvaliacao(ModelPlus):
    nome = models.CharFieldPlus(_('Nome'), max_length=500, blank=False, null=False)
    ativo = models.BooleanFieldPlus(_('Ativo'), default=True)
    peso = models.PositiveIntegerFieldPlus(_('Peso'), blank=True, null=True)
    data_cadastro = models.DateTimeFieldPlus(_('Data de Cadastro'), auto_now_add=True, null=True, blank=True)
    data_atualizacao = models.DateTimeFieldPlus(_('Data de Atualização'), auto_now=True, null=True, blank=True)

    class Meta:
        verbose_name = _('Critério')
        verbose_name_plural = _('Critérios')

    def __str__(self):
        return self.nome
