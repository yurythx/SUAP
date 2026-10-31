from djtools.db import models
from django.utils.translation import gettext_lazy as _

from ..enums import CondicaoAcaoAutomatica


class Acao(models.ModelPlus):
    etapa = models.ForeignKeyPlus('dados_abertos.Etapa', verbose_name=_('Etapa'), related_name='acoes', on_delete=models.CASCADE)
    titulo = models.CharFieldPlus(_('Título'), max_length=200)
    descricao = models.TextField(_('Descrição'), blank=True)
    obrigatoria = models.BooleanField(_('Obrigatória'), default=True)
    ordem = models.PositiveIntegerFieldPlus(_('Ordem'), default=1)
    condicao_automatica = models.CharFieldPlus(
        _('Condição automática'),
        max_length=40,
        blank=True,
        choices=CondicaoAcaoAutomatica.get_choices(),
        help_text=_('Se definida, a ação é marcada automaticamente quando a condição é satisfeita no PDA (não editável manualmente).'),
    )

    data_cadastro = models.DateTimeFieldPlus(_('Data de Cadastro'), auto_now_add=True, null=True, blank=True)
    data_atualizacao = models.DateTimeFieldPlus(_('Data de Atualização'), auto_now=True, null=True, blank=True)

    class Meta:
        verbose_name = _('Ação')
        verbose_name_plural = _('Ações')
        ordering = ['etapa__ordem', 'ordem']

    def __str__(self):
        return f'{self.etapa.ordem}.{self.ordem} - {self.titulo}'
