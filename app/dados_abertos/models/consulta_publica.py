from djtools.db import models
from djtools.db.models import ModelPlus
from django.utils.translation import gettext_lazy as _


class ConsultaPublica(ModelPlus):
    pda = models.ForeignKeyPlus('dados_abertos.PlanoDadosAbertos', on_delete=models.CASCADE, related_name='consultas_publicas', verbose_name=_('PDA'))
    titulo = models.CharFieldPlus(_('Título da Consulta Pública'), max_length=255)
    descricao = models.TextField(_('Descrição'), blank=True)
    data_inicio = models.DateFieldPlus(_('Data de Início'))
    data_fim = models.DateFieldPlus(_('Data de Fim'))

    data_cadastro = models.DateTimeFieldPlus(_('Data de Cadastro'), auto_now_add=True, null=True, blank=True)
    data_atualizacao = models.DateTimeFieldPlus(_('Data de Atualização'), auto_now=True, null=True, blank=True)

    class Meta:
        verbose_name = _('Consulta Pública do PDA')
        verbose_name_plural = _('Consultas Públicas do PDA')

    def __str__(self):
        return self.titulo
