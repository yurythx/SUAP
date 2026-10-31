from djtools.db import models
from djtools.db.models import ModelPlus
from django.utils.translation import gettext_lazy as _


class ItemCronogramaElaboracao(ModelPlus):
    """Item do Cronograma de Elaboração e Sustentação do PDA.

    Representa uma linha do cronograma exigido pelo Art. 4º, VI, a da
    Resolução nº 3/2017 do CGINDA, referente às etapas adotadas para
    elaborar e sustentar o PDA.

    Colunas do modelo da CGU:
        Ação | Atividade | Unidade e Contato do Responsável | Meta/Prazo
    """

    pda = models.ForeignKeyPlus(
        'dados_abertos.PlanoDadosAbertos',
        on_delete=models.CASCADE,
        related_name='itens_cronograma_elaboracao',
        verbose_name=_('PDA'),
    )
    acao = models.CharFieldPlus(
        _('Ação'),
        max_length=300,
        help_text=_('Nome da ação a ser realizada (ex: Constituição do Grupo de Trabalho).'),
    )
    atividade = models.TextField(
        _('Atividade'),
        blank=True,
        help_text=_('Descrição detalhada da atividade a ser realizada.'),
    )
    responsavel = models.CharFieldPlus(
        _('Unidade e Contato do Responsável'),
        max_length=500,
        blank=True,
        help_text=_('Unidade organizacional e contato (nome/e-mail) do responsável.'),
    )
    meta_prazo = models.DateFieldPlus(
        _('Meta/Prazo'),
        null=True,
        blank=True,
        help_text=_('Data prevista para conclusão da ação.'),
    )
    ordem = models.IntegerField(
        _('Ordem'),
        default=0,
        help_text=_('Posição no cronograma (menor = primeiro).'),
    )

    data_cadastro = models.DateTimeFieldPlus(_('Data de Cadastro'), auto_now_add=True, null=True, blank=True)
    data_atualizacao = models.DateTimeFieldPlus(_('Data de Atualização'), auto_now=True, null=True, blank=True)

    class Meta:
        verbose_name = _('Item do Cronograma de Elaboração')
        verbose_name_plural = _('Itens do Cronograma de Elaboração')
        ordering = ('pda_id', 'ordem', 'acao')

    def __str__(self):
        return f'{self.acao} ({self.pda})'
