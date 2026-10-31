from djtools.db import models
from django.db.models.functions import Now
from django.utils.translation import gettext_lazy as _

from rsc_tae.enums import SituacaoAvaliacaoItem


class AvaliacaoAnexoRSCTae(models.ModelPlus):
    anexo = models.ForeignKeyPlus(
        'rsc_tae.RolSaberCompetenciaAnexo',
        verbose_name=_('Anexo'),
        on_delete=models.CASCADE,
        related_name='avaliacoes',
    )

    avaliador_vinculo = models.ForeignKeyPlus(
        'comum.Vinculo',
        verbose_name=_('Avaliador (vínculo)'),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='rsc_tae_avaliacoes_anexo_set',
    )
    situacao = models.PositiveIntegerField(
        _('Situação'),
        choices=SituacaoAvaliacaoItem.get_choices(),
        default=SituacaoAvaliacaoItem.PENDENTE,
    )
    pontuacao_validada = models.DecimalField(
        _('Pontuação validada'),
        max_digits=7,
        decimal_places=2,
        null=True,
        blank=False,
        help_text=_('Pontuação validada para este arquivo. Se não houver ajuste, deve ser igual à pontuação do anexo.'),
    )
    observacao = models.TextField(_('Observação'), blank=True)

    avaliado_por = models.CurrentUserField(verbose_name=_('Avaliado por'), null=True, blank=True)
    ip_avaliacao = models.GenericIPAddressField(_('IP da avaliação'), null=True, blank=True)
    user_agent = models.CharField(_('User-Agent'), max_length=255, blank=True)

    data_cadastro = models.DateTimeField(_('Data de cadastro'), auto_now_add=True, db_default=Now())
    data_avaliacao = models.DateTimeField(_('Data de avaliação'), auto_now=True, db_default=Now())
    data_ultima_alteracao = models.DateTimeField(_('Data de última alteração'), auto_now=True, db_default=Now())

    class Meta:
        verbose_name = _('Avaliação do anexo (RSC TAE)')
        verbose_name_plural = _('Avaliações dos anexos (RSC TAE)')
        ordering = ('-data_avaliacao',)
        constraints = [
            models.UniqueConstraint(
                fields=['anexo', 'avaliador_vinculo'],
                name='uq_rsc_tae_avaliacao_anexo_por_avaliador',
                condition=models.Q(avaliador_vinculo__isnull=False),
            )
        ]

    def __str__(self):
        return f'Anexo {self.anexo_id} - {self.get_situacao_display()!s}'
