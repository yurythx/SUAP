from dados_abertos.enums import SituacaoPDA, TipoVersao
from djtools.db import models
from djtools.db.models import ModelPlus
from django.utils.translation import gettext_lazy as _


class VersaoPDA(ModelPlus):
    pda = models.ForeignKeyPlus(
        'dados_abertos.PlanoDadosAbertos',
        verbose_name=_('PDA'),
        related_name='versoes',
        on_delete=models.CASCADE,
    )
    major = models.PositiveIntegerField(_('Major'), default=1)
    minor = models.PositiveIntegerField(_('Minor'), default=0)
    patch = models.PositiveIntegerField(_('Patch'), default=0)
    tipo = models.PositiveSmallIntegerField(_('Tipo de versão'), choices=TipoVersao.get_choices())
    situacao_no_momento = models.PositiveSmallIntegerField(_('Situação no momento'), choices=SituacaoPDA.get_choices())
    dados_snapshot = models.FileInformationField(_('Snapshot dos dados'), default=dict, blank=True)
    justificativa = models.TextField(_('Justificativa da versão'), max_length=2000, blank=True)
    criado_por = models.CurrentUserField(verbose_name=_('Criado por'))
    data_criacao = models.DateTimeFieldPlus(_('Data de criação'), auto_now_add=True)

    class Meta:
        verbose_name = _('Versão do PDA')
        verbose_name_plural = _('Versões do PDA')
        unique_together = ('pda', 'major', 'minor', 'patch')
        ordering = ['-major', '-minor', '-patch']

    @property
    def numero_formatado(self):
        return f'{self.major}.{self.minor}.{self.patch}'

    def __str__(self):
        return f'v{self.numero_formatado}'
