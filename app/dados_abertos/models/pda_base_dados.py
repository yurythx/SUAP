from djtools.db import models
from djtools.db.models import ModelPlus
from django.utils.translation import gettext_lazy as _

from ..enums import Periodicidade, SituacaoLAI


class PDABaseDados(ModelPlus):
    """Relação entre um PDA e uma Base de Dados.

    Permite que a mesma BaseDados exista em diferentes PDAs,
    guardando metadados por PDA (herdada, revisão, consulta pública).
    """

    pda = models.ForeignKeyPlus(
        'dados_abertos.PlanoDadosAbertos',
        on_delete=models.CASCADE,
        related_name='bases_relacionadas',
        verbose_name=_('PDA'),
    )
    base_dados = models.ForeignKeyPlus(
        'dados_abertos.BaseDados',
        on_delete=models.CASCADE,
        related_name='relacoes_pda',
        verbose_name=_('Base de Dados'),
    )

    herdada = models.BooleanFieldPlus(
        _('Herdada'),
        default=False,
        help_text=_('Marque quando a base foi incorporada de um PDA anterior.'),
    )
    em_revisao = models.BooleanFieldPlus(
        _('Em revisão'),
        default=False,
        help_text=_('Marque quando a base (herdada ou não) estiver em processo de revisão.'),
    )
    submetida_consulta_publica = models.BooleanFieldPlus(
        _('Submetida à consulta pública'),
        default=False,
        help_text=_('Marque quando a base foi submetida à consulta pública no contexto deste PDA.'),
    )
    situacao_lai = models.IntegerField(
        _('Situação LAI'),
        choices=SituacaoLAI.get_choices(),
        default=SituacaoLAI.PENDENTE,
        help_text=_('Situação da deliberação do Responsável LAI para esta base neste PDA.'),
    )
    motivo_reabertura = models.CharFieldPlus(
        _('Motivo da reabertura'),
        max_length=255,
        blank=True,
        help_text=_('Preenchido quando a liberação é invalidada por edição do conteúdo.'),
    )

    # Campos do Cronograma de Abertura de Bases (Art. 4º, VI, b da Resolução nº 3/2017 do CGINDA)
    unidade_responsavel_abertura = models.ForeignKeyPlus(
        'rh.Setor',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_('Unidade Responsável pela Abertura'),
        help_text=_('Unidade organizacional responsável pela abertura desta base de dados.'),
    )
    responsavel_abertura = models.ForeignKeyPlus(
        'rh.Servidor',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_('Responsável'),
        help_text=_('Responsável pela abertura desta base.'),
    )
    meta_prazo_abertura = models.DateFieldPlus(
        _('Meta/Prazo de Abertura'),
        null=True,
        blank=True,
        help_text=_('Data prevista para publicação desta base de dados.'),
    )
    frequencia_atualizacao = models.IntegerField(
        _('Frequência de Atualização'),
        choices=Periodicidade.get_choices(),
        null=True,
        blank=True,
        help_text=_('Com que frequência os dados desta base serão atualizados após a publicação.'),
    )

    data_cadastro = models.DateTimeFieldPlus(_('Data de Cadastro'), auto_now_add=True, null=True, blank=True)
    data_atualizacao = models.DateTimeFieldPlus(_('Data de Atualização'), auto_now=True, null=True, blank=True)

    class Meta:
        verbose_name = _('Base de Dados no PDA')
        verbose_name_plural = _('Bases de Dados no PDA')
        unique_together = (('pda', 'base_dados'),)
        ordering = ('pda_id', 'base_dados_id')

    def __str__(self):
        return f'{self.base_dados} em {self.pda}'

    def get_absolute_url(self) -> str:
        """Aba "pdas" da visualização da base: o registro só faz sentido no contexto dela."""
        return f'{self.base_dados.get_absolute_url()}?tab=pdas'

    @property
    def devolvida_lai(self) -> bool:
        from ..enums import SituacaoLAI

        return self.situacao_lai == SituacaoLAI.DEVOLVIDO

    @property
    def classe_situacao_lai(self) -> str:
        """Classe de status do Design System correspondente à situação LAI atual."""
        from ..enums import SituacaoLAI

        return SituacaoLAI.CLASSES.get(self.situacao_lai, 'status-neutro')

    @property
    def rodada_atual(self) -> int:
        """Número da rodada de análise: a primeira é 1, e cada devolução abre a seguinte.

        Derivado dos eventos em vez de armazenado — não há como o contador divergir do histórico.
        """
        from ..enums import TipoEventoLAI

        # `.all()` aproveita o cache de prefetch_related('eventos_lai'); um `.filter().count()`
        # iria ao banco mesmo com os eventos já carregados, e o plano de ação lê esta property
        # dentro do laço das bases devolvidas — uma consulta por base.
        return sum(1 for evento in self.eventos_lai.all() if evento.tipo == TipoEventoLAI.DEVOLUCAO) + 1
