from djtools.db import models
from django.utils.translation import gettext_lazy as _


class Etapa(models.ModelPlus):
    titulo = models.CharFieldPlus(_('Título'), max_length=200)
    ordem = models.PositiveIntegerFieldPlus(_('Ordem'))
    descricao = models.TextField(_('Descrição'), blank=True)
    dispara_analise_lai = models.BooleanFieldPlus(
        _('Dispara análise do LAI'),
        default=False,
        help_text=_('Quando o PDA atinge esta etapa, todos os seus datasets pendentes entram em análise do Responsável LAI.'),
    )
    pulavel = models.BooleanFieldPlus(
        _('Pulável'),
        default=False,
        help_text=_('Quando marcada, esta etapa pode ser dispensada (pulada) no fluxo de um PDA, mediante justificativa.'),
    )

    data_cadastro = models.DateTimeFieldPlus(_('Data de Cadastro'), auto_now_add=True, null=True, blank=True)
    data_atualizacao = models.DateTimeFieldPlus(_('Data de Atualização'), auto_now=True, null=True, blank=True)

    class Meta:
        verbose_name = _('Etapa')
        verbose_name_plural = _('Etapas')
        ordering = ['ordem']

    def __str__(self):
        return f'{self.ordem}. {self.titulo}'
