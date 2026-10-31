from djtools.db import models
from djtools.db.models import ModelPlus
from django.utils.translation import gettext_lazy as _
from ..enums import NotaAvaliacaoBaseDados


class AvaliacaoBaseDados(ModelPlus):
    base_dados = models.ForeignKeyPlus(
        'dados_abertos.BaseDados',
        verbose_name=_('Base de Dados'),
        on_delete=models.CASCADE,
        related_name='avaliacoes_base_dados',
        related_query_name='avaliacao_base_dados',
    )
    criterio_matriz = models.ForeignKeyPlus(
        'dados_abertos.CriterioMatriz',
        verbose_name=_('Critério da Matriz'),
        on_delete=models.CASCADE,
        related_name='avaliacoes',
    )
    nota = models.IntegerFieldPlus(_('Nota'), default=0, choices=NotaAvaliacaoBaseDados.get_choices())
    finalizado = models.BooleanField(_('Finalizado'), default=False)
    data_cadastro = models.DateTimeFieldPlus(_('Data de Cadastro'), auto_now_add=True)
    data_atualizacao = models.DateTimeFieldPlus(_('Data de Atualização'), auto_now=True)

    class Meta:
        verbose_name = _('Avaliação de Base de Dados')
        verbose_name_plural = _('Avaliações de Bases de Dados')

    def __str__(self):
        return f'Avaliação de {self.base_dados}'

    def get_absolute_url(self) -> str:
        """Aba "matriz" da visualização da base: o registro só faz sentido no contexto dela."""
        return f'{self.base_dados.get_absolute_url()}?tab=matriz'
