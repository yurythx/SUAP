from django.utils.translation import gettext_lazy as _

from djtools.db import models
from djtools.db.models import ModelPlus


class PDAEtapa(ModelPlus):
    """Estado por-PDA de uma etapa.

    A existência de uma linha marca a etapa como **dispensada (pulada)** naquele PDA: o fluxo passa
    por cima dela (não bloqueia a ``etapa_atual``, não conta no progresso e suas ações automáticas não
    são sincronizadas). Reativar a etapa = remover a linha. Guarda auditoria (quem, quando, por quê).
    """

    pda = models.ForeignKeyPlus(
        'dados_abertos.PlanoDadosAbertos',
        verbose_name=_('Plano de Dados Abertos'),
        related_name='etapas_puladas',
        on_delete=models.CASCADE,
    )
    etapa = models.ForeignKeyPlus('dados_abertos.Etapa', verbose_name=_('Etapa'), on_delete=models.CASCADE)
    justificativa = models.TextField(_('Justificativa'), help_text=_('Motivo da dispensa da etapa.'))
    pulada_por = models.ForeignKeyPlus('comum.Vinculo', on_delete=models.SET_NULL, null=True, verbose_name=_('Pulada por'))
    data_pulada = models.DateTimeFieldPlus(_('Data da dispensa'), auto_now_add=True)
    ip = models.GenericIPAddressField(_('IP'), null=True, blank=True)
    user_agent = models.TextField(_('User agent'), blank=True)

    class Meta:
        verbose_name = _('Etapa dispensada do PDA')
        verbose_name_plural = _('Etapas dispensadas do PDA')
        unique_together = ('pda', 'etapa')
        ordering = ('etapa__ordem',)
        permissions = [('pular_etapa_pda', 'Pode pular (dispensar) etapas do PDA')]

    def __str__(self):
        return f'{self.pda} — dispensa da etapa {self.etapa}'
