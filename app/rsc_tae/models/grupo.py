from djtools.db import models
from django.db.models.functions import Now
from django.utils.translation import gettext_lazy as _


class GrupoSaberCompetencia(models.ModelPlus):
    requisito = models.ForeignKeyPlus(
        'rsc_tae.Requisito',
        verbose_name=_('Requisito'),
        on_delete=models.PROTECT,
        related_name='grupos',
        help_text=_('Eixo de requisito conforme Art. 3º do Decreto RSC-PCCTAE (I a VI).'),
    )
    numero = models.PositiveIntegerField(
        _('Número do grupo'),
        help_text=_('Número do grupo de complexidade dentro do requisito (ex: Grupo 1, 2, 3…).'),
    )
    pontuacao_unidade = models.DecimalField(
        _('Pontuação por unidade'),
        max_digits=5,
        decimal_places=3,
        help_text=_('Pontuação atribuída por unidade de medida, conforme Anexo II.'),
    )
    descricao = models.CharField(
        _('Descrição'),
        max_length=300,
        blank=True,
        help_text=_('Descrição opcional do grupo.'),
    )
    data_cadastro = models.DateTimeField(_('Data de cadastro'), auto_now_add=True, db_default=Now())
    data_alteracao = models.DateTimeField(_('Data de alteração'), auto_now=True, db_default=Now())

    class Meta:
        verbose_name = _('Grupo de Saber e Competência')
        verbose_name_plural = _('Grupos de Saber e Competências')
        ordering = ('requisito__numero', 'numero')
        constraints = [
            models.UniqueConstraint(
                fields=['requisito', 'numero'],
                name='uq_rsc_tae_grupo_requisito_numero',
            )
        ]

    @property
    def requisito_label_curto(self):
        if self.requisito_id:
            return str(self.requisito.descricao_curta)
        return ''

    def __str__(self):
        req_label = str(self.requisito) if self.requisito_id else f'Req. {self.requisito_id}'
        return f'{req_label} — Grupo {self.numero} ({self.pontuacao_unidade} pts)'
