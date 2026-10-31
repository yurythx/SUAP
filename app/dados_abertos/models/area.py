from djtools.db import models
from djtools.db.models import ModelPlus
from django.utils.translation import gettext_lazy as _


class Area(ModelPlus):
    SEARCH_FIELDS = ['nome', 'descricao']

    nome = models.CharFieldPlus(_('Nome'), max_length=255, unique=True)
    descricao = models.TextField(_('Descrição'), blank=True)

    data_cadastro = models.DateTimeFieldPlus(_('Data de Cadastro'), auto_now_add=True, null=True, blank=True)
    data_atualizacao = models.DateTimeFieldPlus(_('Data de Atualização'), auto_now=True, null=True, blank=True)

    class Meta:
        verbose_name = _('Área')
        verbose_name_plural = _('Áreas')

    def __str__(self):
        return self.nome
