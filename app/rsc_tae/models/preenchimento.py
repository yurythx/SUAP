from djtools.db import models
from django.db.models.functions import Now
from django.utils.translation import gettext_lazy as _


class RolSaberCompetenciaPreenchimento(models.ModelPlus):
    vinculo = models.ForeignKeyPlus('comum.Vinculo', verbose_name=_('Vínculo'), on_delete=models.CASCADE)
    rol_saber_competencia = models.ForeignKeyPlus(
        'rsc_tae.RolSaberCompetencia',
        verbose_name=_('Rol de Saber e Competência'),
        on_delete=models.CASCADE,
    )
    quantidade = models.PositiveIntegerField(_('Quantidade'), default=0)

    data_cadastro = models.DateTimeField(_('Data de cadastro'), auto_now_add=True, db_default=Now())
    data_alteracao = models.DateTimeField(_('Data de alteração'), auto_now=True, db_default=Now())

    class Meta:
        verbose_name = _('Preenchimento do Rol de Saber e Competência')
        verbose_name_plural = _('Preenchimentos do Rol de Saber e Competência')
        constraints = [models.UniqueConstraint(fields=['vinculo', 'rol_saber_competencia'], name='uq_rsc_tae_rol_preench_vinculo_item')]

    @property
    def pontuacao_total(self):
        return self.rol_saber_competencia.pontuacao_unidade * self.quantidade
