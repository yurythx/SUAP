from dados_abertos.enums import Situacao_GrupoTrabalho
from djtools.db import models
from djtools.db.models import ModelPlus
from django.utils.translation import gettext_lazy as _


class GrupoTrabalho(ModelPlus):
    pda = models.ForeignKeyPlus('dados_abertos.PlanoDadosAbertos', on_delete=models.CASCADE, related_name='grupos_trabalho', verbose_name=_('PDA'))
    descricao = models.CharFieldPlus(_('Descrição'), max_length=800)
    situacao = models.IntegerFieldPlus(_('Situação'), choices=Situacao_GrupoTrabalho.get_choices(), default=Situacao_GrupoTrabalho.ATIVO)
    data_cadastro = models.DateTimeFieldPlus(_('Data de Cadastro'), auto_now_add=True)
    data_atualizacao = models.DateTimeFieldPlus(_('Data de Atualização'), auto_now=True, null=True, blank=True)
    data_finalizado = models.DateTimeFieldPlus(_('Data de Finalização das Atividades'), blank=True, null=True)

    class Meta:
        verbose_name = _('Grupo de Trabalho')
        verbose_name_plural = _('Grupos de Trabalho')

    def __str__(self):
        return self.descricao
