from djtools.db import models
from django.utils.translation import gettext_lazy as _
from django.utils import timezone


class PDAAcao(models.ModelPlus):
    pda = models.ForeignKeyPlus(
        'dados_abertos.PlanoDadosAbertos', verbose_name=_('Plano de Dados Abertos'), related_name='acoes', on_delete=models.CASCADE
    )
    acao = models.ForeignKeyPlus('dados_abertos.Acao', verbose_name=_('Ação'), related_name='estado_nos_pdas', on_delete=models.CASCADE)
    concluida = models.BooleanFieldPlus(_('Concluída'), default=False)
    data_conclusao = models.DateTimeFieldPlus(_('Data de conclusão'), null=True, blank=True)

    data_cadastro = models.DateTimeFieldPlus(_('Data de Cadastro'), auto_now_add=True, null=True, blank=True)
    data_atualizacao = models.DateTimeFieldPlus(_('Data de Atualização'), auto_now=True, null=True, blank=True)

    class Meta:
        verbose_name = _('Ação do PDA')
        verbose_name_plural = _('Ações do PDA')
        unique_together = ('pda', 'acao')
        ordering = ['acao__etapa__ordem', 'acao__ordem']

    def __str__(self):
        return f'{self.pda} - {self.acao}'

    def marcar_concluida(self, user=None):
        self.concluida = True
        self.data_conclusao = timezone.now()
        self.save()
        self.pda.atualizar_etapa_atual()

    def marcar_pendente(self):
        self.concluida = False
        self.data_conclusao = None
        self.save()
        self.pda.atualizar_etapa_atual()
