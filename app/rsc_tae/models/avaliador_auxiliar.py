import datetime

from django.db.models.functions import Now
from django.utils.translation import gettext_lazy as _

from djtools.db import models


class AvaliadorAuxiliarRSCTae(models.ModelPlus):
    """Banco de avaliadores auxiliares habilitados para atuar no RSC-TAE.

    Um servidor é habilitado pela CRSC-PCCTAE após capacitação específica
    e permanece no banco até ser inativado. Apenas avaliadores com
    data_inativacao nula e ativo=True são elegíveis ao sorteio.
    """

    vinculo = models.ForeignKeyPlus(
        'comum.Vinculo',
        verbose_name=_('Servidor'),
        on_delete=models.PROTECT,
        related_name='rsc_tae_avaliador_auxiliar_set',
    )
    ativo = models.BooleanFieldPlus(
        _('Ativo'),
        default=True,
        help_text=_('Desmarcar equivale a inativar manualmente. Use "Inativar" para registrar a data.'),
    )
    data_habilitacao = models.DateFieldPlus(
        _('Data de habilitação'),
        help_text=_('Data em que o servidor foi habilitado pela CRSC após capacitação.'),
    )
    data_inativacao = models.DateFieldPlus(
        _('Data de inativação'),
        null=True,
        blank=True,
        help_text=_('Preenchida quando o avaliador é removido do banco. Nula = ainda ativo.'),
    )
    observacao = models.TextField(_('Observação'), blank=True)
    cadastrado_por_vinculo = models.ForeignKeyPlus(
        'comum.Vinculo',
        verbose_name=_('Cadastrado por'),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='rsc_tae_avaliadores_cadastrados_set',
    )
    data_cadastro = models.DateTimeFieldPlus(_('Data de cadastro'), auto_now_add=True, db_default=Now())
    data_alteracao = models.DateTimeFieldPlus(_('Data de alteração'), auto_now=True, db_default=Now())

    class Meta:
        verbose_name = _('Avaliador Auxiliar (RSC-TAE)')
        verbose_name_plural = _('Banco de Avaliadores Auxiliares (RSC-TAE)')
        ordering = ('vinculo__pessoa__nome',)
        constraints = [
            models.UniqueConstraint(
                fields=['vinculo'],
                condition=models.Q(data_inativacao__isnull=True),
                name='uq_rsc_tae_avaliador_auxiliar_ativo',
            )
        ]

    def __str__(self):
        status = '' if self.ativo else ' (inativo)'
        return f'{self.vinculo}{status}'

    @classmethod
    def aptos_para_sorteio(cls, excluir_vinculo_ids=None):
        """QuerySet de avaliadores aptos: ativos e não inativados.

        A filtragem por afastamentos/férias fica a cargo do chamador
        (_sortear_avaliadores em views/_helpers.py) para evitar
        dependência circular de views em models.
        """
        qs = cls.objects.filter(ativo=True, data_inativacao__isnull=True).select_related('vinculo__pessoa')
        if excluir_vinculo_ids:
            qs = qs.exclude(vinculo_id__in=excluir_vinculo_ids)
        return qs

    def inativar(self, data=None):
        """Inativa o avaliador registrando a data de inativação."""
        self.ativo = False
        self.data_inativacao = data or datetime.date.today()
        self.save(update_fields=['ativo', 'data_inativacao', 'data_alteracao'])
