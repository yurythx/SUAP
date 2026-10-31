from djtools.db import models
from djtools.db.models import ModelPlus
from django.utils.translation import gettext_lazy as _


class Licenca(ModelPlus):
    """
    Verificar licenças comumente utilizadas no CKAN
    """

    SEARCH_FIELDS = ['nome', 'descricao']

    nome = models.CharFieldPlus(_('Licença'), max_length=255, unique=True)
    descricao = models.TextField(_('Descrição'), blank=True)
    codigo_ckan = models.CharFieldPlus(
        _('Código no CKAN'),
        max_length=100,
        blank=True,
        help_text=_('Identificador da licença no CKAN (license_id), ex.: cc-by. Sem ele, a licença não é enviada ao portal.'),
    )

    data_cadastro = models.DateTimeFieldPlus(_('Data de Cadastro'), auto_now_add=True, null=True, blank=True)
    data_atualizacao = models.DateTimeFieldPlus(_('Data de Atualização'), auto_now=True, null=True, blank=True)

    class Meta:
        verbose_name = _('Licença')
        verbose_name_plural = _('Licenças')

    def __str__(self):
        if self.descricao:
            return f'{self.nome} - {self.descricao}'
        return self.nome
