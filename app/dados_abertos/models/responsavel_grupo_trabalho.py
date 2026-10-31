from djtools.db import models
from djtools.db.models import ModelPlus
from django.utils.translation import gettext_lazy as _


class ResponsavelGrupoTrabalho(ModelPlus):
    grupo_trabalho = models.ForeignKey('dados_abertos.GrupoTrabalho', verbose_name=_('Grupo de Trabalho'), on_delete=models.CASCADE)
    responsavel = models.ForeignKeyPlus('comum.Vinculo', verbose_name=_('Responsável'), on_delete=models.CASCADE, null=True, blank=False)
    data_cadastro = models.DateTimeField(_('Data de Cadastro'), auto_now_add=True)
    data_atualizacao = models.DateTimeField(_('Data de Atualização'), auto_now=True, null=True, blank=True)
    ativo = models.BooleanField(_('Ativo?'), default=True)

    class Meta:
        verbose_name = _('Responsável')
        verbose_name_plural = _('Responsáveis')

    def __str__(self):
        return self.responsavel.nome
