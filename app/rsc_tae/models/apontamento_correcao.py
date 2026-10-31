from djtools.db import models
from django.db.models.functions import Now
from django.utils.translation import gettext_lazy as _

from rsc_tae.enums import AreaCorrecao


class ApontamentoCorrecaoRSCTae(models.ModelPlus):
    """Apontamento feito pelo RH indicando uma área do processo que precisa de correção.

    Ao solicitar correção, o RH cria um apontamento por área marcada, com a descrição
    do problema. Os apontamentos não resolvidos são exibidos ao servidor como guia do
    que corrigir e são marcados como resolvidos quando ele reconclui o preenchimento.
    """

    processo = models.ForeignKeyPlus(
        'rsc_tae.ProcessoRSCTae',
        verbose_name=_('Processo'),
        on_delete=models.CASCADE,
        related_name='apontamentos_correcao',
    )
    area = models.PositiveIntegerField(_('Área'), choices=AreaCorrecao.get_choices())
    descricao = models.TextField(_('Descrição do problema'))

    criado_por_vinculo = models.ForeignKeyPlus(
        'comum.Vinculo',
        verbose_name=_('Criado por (vínculo)'),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='rsc_tae_apontamentos_correcao_set',
    )
    data_criacao = models.DateTimeField(_('Data de criação'), auto_now_add=True, db_default=Now())
    resolvido = models.BooleanField(_('Resolvido'), default=False)

    class Meta:
        verbose_name = _('Apontamento de correção (RSC TAE)')
        verbose_name_plural = _('Apontamentos de correção (RSC TAE)')
        ordering = ('-data_criacao',)

    def __str__(self):
        return f'{self.get_area_display()} — processo {self.processo_id}'
