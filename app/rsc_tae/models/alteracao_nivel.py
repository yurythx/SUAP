from django.db.models.functions import Now
from django.utils.translation import gettext_lazy as _

from djtools.db import models


class AlteracaoNivelRSCTae(models.ModelPlus):
    """Registra cada alteração do nível RSC pretendido feita pelo servidor.

    A alteração só é permitida enquanto o processo está nas mãos do servidor
    (Aguardando Preenchimento/Correção) — antes da assinatura de conclusão, que é
    regenerada ao reconcluir e passa a cobrir o novo nível. Este log preserva a
    trilha de auditoria: qual era o nível, para qual mudou, quem mudou e por quê.
    """

    processo = models.ForeignKeyPlus(
        'rsc_tae.ProcessoRSCTae',
        verbose_name=_('Processo'),
        on_delete=models.CASCADE,
        related_name='alteracoes_nivel',
    )
    nivel_anterior = models.ForeignKeyPlus(
        'rsc_tae.Nivel',
        verbose_name=_('Nível anterior'),
        on_delete=models.PROTECT,
        related_name='+',
    )
    nivel_novo = models.ForeignKeyPlus(
        'rsc_tae.Nivel',
        verbose_name=_('Nível novo'),
        on_delete=models.PROTECT,
        related_name='+',
    )
    motivo = models.TextField(_('Motivo da alteração'))
    alterado_por_vinculo = models.ForeignKeyPlus(
        'comum.Vinculo',
        verbose_name=_('Alterado por (vínculo)'),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='rsc_tae_alteracoes_nivel_set',
    )
    ip = models.GenericIPAddressField(_('IP'), null=True, blank=True)
    user_agent = models.CharField(_('User-Agent'), max_length=255, blank=True)
    data_alteracao = models.DateTimeField(_('Data da alteração'), auto_now_add=True, db_default=Now())

    class Meta:
        verbose_name = _('Alteração de nível pretendido (RSC TAE)')
        verbose_name_plural = _('Alterações de nível pretendido (RSC TAE)')
        ordering = ('-data_alteracao',)

    def __str__(self):
        return f'Processo {self.processo_id}: RSC-{self.nivel_anterior.ordem_romana} → RSC-{self.nivel_novo.ordem_romana}'
