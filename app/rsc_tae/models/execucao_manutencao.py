from django.utils.translation import gettext_lazy as _

from djtools.db import models


class ExecucaoManutencaoRSCTae(models.ModelPlus):
    """Auditoria de um command executado pela tela de manutenção (/rsc_tae/manutencao/).

    Cada linha registra quem executou, quando, qual command da allowlist, com quais
    argumentos, se teve sucesso e a saída capturada (stdout + stderr).
    """

    comando = models.CharField(_('Comando'), max_length=100)
    argumentos = models.CharField(_('Argumentos'), max_length=500, blank=True)
    executado_por_vinculo = models.ForeignKeyPlus(
        'comum.Vinculo',
        verbose_name=_('Executado por'),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='rsc_tae_execucoes_manutencao_set',
    )
    data_execucao = models.DateTimeFieldPlus(_('Data da execução'), auto_now_add=True)
    sucesso = models.BooleanField(_('Sucesso'), default=False)
    saida = models.TextField(_('Saída'), blank=True)

    class Meta:
        verbose_name = _('Execução de Manutenção (RSC-TAE)')
        verbose_name_plural = _('Execuções de Manutenção (RSC-TAE)')
        ordering = ('-data_execucao',)

    @property
    def label(self) -> str:
        """Rótulo amigável do command (para exibição), sem expor o nome real do management command."""
        from rsc_tae.manutencao_comandos import label_por_nome

        return label_por_nome(self.comando)

    def __str__(self):
        return f'{self.label} {self.argumentos}'.strip()
