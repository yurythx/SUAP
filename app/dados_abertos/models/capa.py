from djtools.db import models
from djtools.db.models import ModelPlus
from django.utils.translation import gettext_lazy as _


class Capa(ModelPlus):
    SEARCH_FIELDS = ['nome']

    pda = models.ForeignKeyPlus(
        'dados_abertos.PlanoDadosAbertos',
        on_delete=models.CASCADE,
        related_name='capa',
        verbose_name=_('PDA'),
    )
    nome = models.CharFieldPlus(
        max_length=255, blank=True, verbose_name=_('Nome da imagem'), help_text=_('Texto alternativo para a imagem de capa (para acessibilidade).')
    )
    imagem = models.ImageFieldPlus(upload_to='pda_capas/', verbose_name=_('Imagem de capa'), help_text=_('Imagem representativa do PDA (opcional).'))

    data_cadastro = models.DateTimeFieldPlus(_('Data de Cadastro'), auto_now_add=True, null=True, blank=True)
    data_atualizacao = models.DateTimeFieldPlus(_('Data de Atualização'), auto_now=True, null=True, blank=True)

    class Meta:
        verbose_name = _('Capa do Plano de Dados Abertos')
        verbose_name_plural = _('Capas dos Planos de Dados Abertos')

    def __str__(self):
        return f'Capa do {self.pda}'
