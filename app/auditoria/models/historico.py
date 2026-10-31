from comum.models import Vinculo
from djtools.db import models


class Historico(models.ModelPlus):
    usuario = models.CurrentUserField(verbose_name='Usuário')
    descricao = models.CharFieldPlus(verbose_name='Descrição')
    destinatarios = models.ManyToManyFieldPlus(Vinculo, verbose_name='Destinatários', blank=True)
    criado_em = models.DateTimeFieldPlus(auto_now_add=True)

    class Meta:
        abstract = True
        ordering = ['-criado_em']

    def __str__(self):
        return f'{self.descricao}: por {self.usuario} em {self.criado_em}'


class HistoricoRecomendacao(Historico):
    recomendacao = models.ForeignKeyPlus('auditoria.Recomendacao', verbose_name='Recomendação', on_delete=models.CASCADE, null=False, blank=False)

    class Meta:
        verbose_name = 'Histórico de Recomendação'
        verbose_name_plural = 'Históricos de Recomendações'
        ordering = ['-criado_em']


class HistoricoRelatorioAuditoria(models.ModelPlus):
    relatorio = models.ForeignKeyPlus(
        'auditoria.Relatorio', verbose_name='Relatório', on_delete=models.CASCADE, null=False, blank=False, related_name='historico'
    )
    campo_editado = models.CharField(max_length=255)
    valor_antigo = models.TextField()
    valor_novo = models.TextField()
    modificado_em = models.DateTimeField(auto_now_add=True)
    modificado_por = models.CurrentUserField(on_delete=models.SET_NULL, null=True, related_name='%(app_label)s_%(class)s_modificado_por')

    class Meta:
        verbose_name = 'Histórico de alterações do relatório'
        verbose_name_plural = 'Históricos de alterações dos relatórios'
        ordering = ['-modificado_em']

    def __str__(self):
        return f"Relatório {self.relatorio}:  {self.modificado_por} alterou o campo '{self.campo_editado}'"


class HistoricoBeneficio(Historico):
    beneficio = models.ForeignKeyPlus('auditoria.Beneficio', verbose_name='Benefício', on_delete=models.CASCADE, null=False, blank=False)

    class Meta:
        verbose_name = 'Histórico de Benefício'
        verbose_name_plural = 'Históricos de Benefícios'
        ordering = ['-criado_em']
