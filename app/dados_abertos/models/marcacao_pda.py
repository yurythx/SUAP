from djtools.db import models
from djtools.db.models import ModelPlus
from django.utils.translation import gettext_lazy as _


class MarcacaoPDA(ModelPlus):
    """
    Irá gerenciar as marcações do PDA para substituição de variáveis no template do documento. Ex.: {{ nome_orgao }}, {{ data_atualizacao }}, etc.
     - A marcação deve ser única para evitar confusão na substituição.
     - O campo template_base pode ser usado para indicar um valor padrão ou um exemplo de como a marcação deve ser formatada, mas não é obrigatório.
    """

    SEARCH_FIELDS = ['marcacao', 'template_base']

    marcacao = models.CharFieldPlus(_('Marcação'), max_length=255, unique=True)
    template_base = models.CharFieldPlus(_('Template Base'), blank=True)

    data_cadastro = models.DateTimeFieldPlus(_('Data de Cadastro'), auto_now_add=True, null=True, blank=True)
    data_atualizacao = models.DateTimeFieldPlus(_('Data de Atualização'), auto_now=True, null=True, blank=True)

    class Meta:
        verbose_name = _('Marcação do PDA')
        verbose_name_plural = _('Marcações do PDA')

    def __str__(self):
        return self.marcacao
