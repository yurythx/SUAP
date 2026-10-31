from django.db.models.functions import Now
from django.utils.translation import gettext_lazy as _

from djtools.db import models


class SorteioAvaliadorRSCTae(models.ModelPlus):
    """Registro auditável de cada sorteio e substituição de avaliador.

    Criado automaticamente por _sortear_avaliadores() e _substituir_avaliador()
    em views/_helpers.py. Nunca deve ser criado ou editado manualmente.
    """

    MOTIVO_INICIAL = 1
    MOTIVO_SUBSTITUICAO_RECUSA = 2
    MOTIVO_SUBSTITUICAO_IMPEDIMENTO = 3
    MOTIVO_SUBSTITUICAO_PRAZO = 4
    MOTIVO_SUBSTITUICAO_INATIVACAO = 5
    MOTIVO_REMANEJAMENTO_RH = 6
    MOTIVO_REMOCAO_ADMINISTRATIVA = 7

    MOTIVO_LABELS = (
        (MOTIVO_INICIAL, 'Sorteio inicial'),
        (MOTIVO_SUBSTITUICAO_RECUSA, 'Substituição por recusa'),
        (MOTIVO_SUBSTITUICAO_IMPEDIMENTO, 'Substituição por impedimento/suspeição'),
        (MOTIVO_SUBSTITUICAO_PRAZO, 'Substituição por expiração de prazo'),
        (MOTIVO_SUBSTITUICAO_INATIVACAO, 'Substituição por inativação/indisponibilidade'),
        (MOTIVO_REMANEJAMENTO_RH, 'Remanejamento pelo RH'),
        (MOTIVO_REMOCAO_ADMINISTRATIVA, 'Remoção administrativa (sem reposição)'),
    )

    processo = models.ForeignKeyPlus(
        'rsc_tae.ProcessoRSCTae',
        verbose_name=_('Processo'),
        on_delete=models.CASCADE,
        related_name='sorteios',
    )
    avaliador_sorteado = models.ForeignKeyPlus(
        'comum.Vinculo',
        verbose_name=_('Avaliador sorteado'),
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name='rsc_tae_sorteios_como_sorteado_set',
        help_text=_('Nulo na remoção administrativa, em que um avaliador sai sem que outro entre em seu lugar.'),
    )
    avaliador_substituido = models.ForeignKeyPlus(
        'comum.Vinculo',
        verbose_name=_('Avaliador substituído'),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='rsc_tae_sorteios_como_substituido_set',
        help_text=_('Preenchido nas substituições e nas remoções administrativas.'),
    )
    motivo = models.PositiveIntegerField(
        _('Motivo'),
        choices=MOTIVO_LABELS,
    )
    justificativa = models.TextField(_('Justificativa'), blank=True)
    realizado_por_vinculo = models.ForeignKeyPlus(
        'comum.Vinculo',
        verbose_name=_('Realizado por'),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='rsc_tae_sorteios_realizados_set',
    )
    data_sorteio = models.DateTimeFieldPlus(_('Data do sorteio'), auto_now_add=True, db_default=Now())

    class Meta:
        verbose_name = _('Sorteio de Avaliador (RSC-TAE)')
        verbose_name_plural = _('Histórico de Sorteios (RSC-TAE)')
        ordering = ('-data_sorteio',)

    def __str__(self):
        if self.avaliador_sorteado is None:
            return f'Remoção #{self.pk} — {self.processo} — {self.avaliador_substituido or "—"}'
        return f'Sorteio #{self.pk} — {self.processo} — {self.avaliador_sorteado}'

    @property
    def eh_substituicao(self):
        return self.motivo != self.MOTIVO_INICIAL
