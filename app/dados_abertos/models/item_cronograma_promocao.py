from djtools.db import models
from djtools.db.models import ModelPlus
from django.utils.translation import gettext_lazy as _


class ItemCronogramaPromocao(ModelPlus):
    """Item do Cronograma de Promoção, Fomento, Uso e Reúso das Bases.

    Representa uma linha do cronograma exigido pelo Art. 4º, VI, a da
    Resolução nº 3/2017 do CGINDA, referente às ações de promoção,
    fomento, uso e reúso efetivo das bases de dados pela sociedade e
    pelo governo.

    Colunas do modelo da CGU:
        Produto | Atividades | Unidade e Contato do Responsável | Data/Período
    """

    pda = models.ForeignKeyPlus(
        'dados_abertos.PlanoDadosAbertos',
        on_delete=models.CASCADE,
        related_name='itens_cronograma_promocao',
        verbose_name=_('PDA'),
    )
    produto = models.CharFieldPlus(
        _('Produto'),
        max_length=300,
        help_text=_('Nome do produto/resultado esperado (ex: Hackathon de Dados Abertos, Publicação de relatório).'),
    )
    atividades = models.TextField(
        _('Atividades'),
        blank=True,
        help_text=_('Descrição das atividades necessárias para gerar o produto.'),
    )
    responsavel = models.CharFieldPlus(
        _('Unidade e Contato do Responsável'),
        max_length=500,
        blank=True,
        help_text=_('Unidade organizacional e contato (nome/e-mail) do responsável.'),
    )
    data_periodo = models.CharFieldPlus(
        _('Data/Período'),
        max_length=100,
        blank=True,
        help_text=_('Data ou período de realização (ex: Janeiro/2025, Q1 2025, 2º semestre de 2025).'),
    )
    ordem = models.IntegerField(
        _('Ordem'),
        default=0,
        help_text=_('Posição no cronograma (menor = primeiro).'),
    )

    data_cadastro = models.DateTimeFieldPlus(_('Data de Cadastro'), auto_now_add=True, null=True, blank=True)
    data_atualizacao = models.DateTimeFieldPlus(_('Data de Atualização'), auto_now=True, null=True, blank=True)

    class Meta:
        verbose_name = _('Item do Cronograma de Promoção e Fomento')
        verbose_name_plural = _('Itens do Cronograma de Promoção e Fomento')
        ordering = ('pda_id', 'ordem', 'produto')

    def __str__(self):
        return f'{self.produto} ({self.pda})'
