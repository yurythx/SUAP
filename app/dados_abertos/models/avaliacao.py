from dados_abertos.enums import ValorAvaliacao
from djtools.db import models
from djtools.db.models import ModelPlus
from django.utils.translation import gettext_lazy as _


class Avaliacao(ModelPlus):
    consulta_publica = models.ForeignKeyPlus(
        'dados_abertos.ConsultaPublica', on_delete=models.CASCADE, related_name='avaliacoes', verbose_name=_('Consulta Pública')
    )
    base_dados = models.ForeignKeyPlus(
        'dados_abertos.BaseDados', on_delete=models.CASCADE, related_name='avaliacoes', verbose_name=_('Base de Dados')
    )
    nota = models.PositiveIntegerFieldPlus(
        _('Nota'), blank=False, null=False, choices=ValorAvaliacao.get_choices(), default=ValorAvaliacao.NAO_SE_APLICA
    )
    finalizada = models.BooleanField(_('Finalizada'), default=False, null=True, blank=True)
    data_cadastro = models.DateTimeField(_('Data de Cadastro'), auto_now_add=True)
    data_atualizacao = models.DateTimeField(_('Data de Atualização'), auto_now=True)

    class Meta:
        verbose_name = _('Avaliação da Consulta Pública')
        verbose_name_plural = _('Avaliações das Consultas Públicas')

    def __str__(self):
        return f'Avaliação da {self.base_dados} na {self.consulta_publica}'
