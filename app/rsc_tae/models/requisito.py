from djtools.db import models
from django.db.models.functions import Now
from django.utils.translation import gettext_lazy as _


class Requisito(models.ModelPlus):
    numero = models.PositiveIntegerField(
        _('Número'),
        unique=True,
        help_text=_('Número do requisito (1 a 6).'),
    )
    descricao = models.CharField(
        _('Descrição'),
        max_length=300,
        help_text=_('Descrição completa do requisito conforme Art. 3º do Decreto RSC-PCCTAE.'),
    )
    descricao_curta = models.CharField(
        _('Descrição curta'),
        max_length=100,
        help_text=_('Rótulo resumido do requisito (ex: "I - Comissões e Representações").'),
    )
    numeral_romano = models.CharField(
        _('Numeral romano'),
        max_length=10,
        help_text=_('Numeral romano do requisito (I, II, III…).'),
    )
    ativo = models.BooleanField(_('Ativo'), default=True)
    data_cadastro = models.DateTimeField(_('Data de cadastro'), auto_now_add=True, db_default=Now())
    data_alteracao = models.DateTimeField(_('Data de alteração'), auto_now=True, db_default=Now())

    class Meta:
        verbose_name = _('Requisito')
        verbose_name_plural = _('Requisitos')
        ordering = ('numero',)

    def __str__(self):
        return self.descricao_curta or self.descricao
