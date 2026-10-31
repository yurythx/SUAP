from django.utils.translation import gettext_lazy as _

from djtools.db import models
from djtools.db.models import ModelPlus

from ..enums import ResultadoAtualizacao


class AtualizacaoBaseDados(ModelPlus):
    """Registro de uma tentativa de atualização automática de uma base de dados.

    Existe uma linha por base por execução da rotina, inclusive quando nada foi publicado: é o
    histórico que responde "esta base cumpre a periodicidade que prometemos?" e diagnostica fonte
    fora do ar sem abrir log de servidor.
    """

    base_dados = models.ForeignKeyPlus(
        'dados_abertos.BaseDados',
        on_delete=models.CASCADE,
        related_name='atualizacoes',
        verbose_name=_('Base de Dados'),
    )
    resultado = models.IntegerField(_('Resultado'), choices=ResultadoAtualizacao.get_choices())
    detalhe = models.TextField(_('Detalhe'), blank=True, help_text=_('Mensagem de erro ou observação sobre a tentativa.'))
    recursos_atualizados = models.PositiveIntegerFieldPlus(_('Recursos atualizados'), default=0)
    data = models.DateTimeFieldPlus(_('Data'), auto_now_add=True)

    class Meta:
        verbose_name = _('Atualização de Base de Dados')
        verbose_name_plural = _('Atualizações de Bases de Dados')
        ordering = ('-data',)
        indexes = [models.Index(fields=['base_dados', '-data'])]

    def __str__(self):
        return f'{self.base_dados} — {self.get_resultado_display()}'

    @property
    def classe_resultado(self) -> str:
        """Classe de status do Design System para o desfecho da execução."""
        return ResultadoAtualizacao.CLASSES.get(self.resultado, 'status-default')

    def get_absolute_url(self) -> str:
        """Aba "atualizacoes" da visualização da base: o registro só faz sentido no contexto dela."""
        return f'{self.base_dados.get_absolute_url()}?tab=atualizacoes'
