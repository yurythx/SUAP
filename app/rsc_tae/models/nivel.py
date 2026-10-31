from djtools.db import models
from django.db.models.functions import Now
from django.utils.translation import gettext_lazy as _

from rsc_tae.enums import Ordem


class Nivel(models.ModelPlus):
    SEARCH_FIELDS = ('nome',)

    """
    Conforme Art. 5º do Decreto nº 13.048/2026 (RSC-PCCTAE):

    Nível     | Pontuação mínima | Nº mínimo de critérios | Requisito obrigatório (RN04)
    ----------|------------------|------------------------|-----------------------------
    RSC-I     | 10               | —                      | —
    RSC-II    | 15               | 2                      | —
    RSC-III   | 25               | 2                      | —
    RSC-IV    | 30               | 3                      | ao menos 1 de II, IV, V ou VI
    RSC-V     | 52               | 5                      | ao menos 1 de IV, V ou VI
    RSC-VI    | 75               | 7                      | ao menos 1 de VI
    """

    nome = models.CharField(_('Nome'), max_length=100)
    descricao = models.TextField(_('Descrição'), blank=True)
    ordem = models.PositiveIntegerField(_('Ordem'), default=0)
    valor_iq = models.DecimalField(_('Valor do IQ'), max_digits=5, decimal_places=3, default=0.00)
    numero_minimo_itens = models.PositiveIntegerField(_('Número mínimo de itens'), default=0)
    pontuacao_minima = models.DecimalField(_('Pontuação mínima'), max_digits=5, decimal_places=2, default=0.00)

    iq_requisito = models.ManyToManyFieldPlus(
        'rh.Titulacao',
        verbose_name=_('IQ Requisito'),
        related_name='niveis_como_iq_requisito',
        help_text=_('Titulações mínimas exigidas para o cálculo do IQ deste nível.'),
    )
    iq_equivalente = models.ManyToManyFieldPlus(
        'rh.Titulacao',
        verbose_name=_('IQ Equivalente'),
        related_name='niveis_como_iq_equivalente',
        help_text=_('Titulações equivalentes ao IQ deste nível.'),
    )

    requisitos_obrigatorios = models.ManyToManyFieldPlus(
        'rsc_tae.Requisito',
        verbose_name=_('Requisitos obrigatórios (RN04)'),
        blank=True,
        related_name='niveis_como_obrigatorio',
        help_text=_(
            'Ao menos um critério preenchido deve pertencer a um destes requisitos. Aplicável aos níveis IV, V e VI conforme o Decreto RSC-PCCTAE.'
        ),
    )

    ativo = models.BooleanField(_('Ativo'), default=True)
    data_cadastro = models.DateTimeField(_('Data de cadastro'), auto_now_add=True, db_default=Now())
    data_alteracao = models.DateTimeField(_('Data de alteração'), auto_now=True, db_default=Now())

    class Meta:
        verbose_name = _('Nível')
        verbose_name_plural = _('Níveis')
        ordering = ('ordem', 'nome')

    @property
    def ordem_romana(self):
        return dict(Ordem.LABELS).get(self.ordem, str(self.ordem))

    def __str__(self):
        return f'{self.nome}'
