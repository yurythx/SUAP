from djtools.db import models
from django.utils.translation import gettext_lazy as _


class MemorialDescritivoRSCTae(models.ModelPlus):
    processo = models.OneToOneField(
        'rsc_tae.ProcessoRSCTae',
        verbose_name=_('Processo RSC-TAE'),
        on_delete=models.CASCADE,
        related_name='memorial_descritivo',
    )
    introducao = models.TextField(
        _('Introdução'),
        blank=True,
        help_text=_('Texto introdutório do memorial, apresentado antes da descrição das atividades por requisito legal.'),
    )
    conclusao = models.TextField(
        _('Conclusão do Servidor'),
        blank=True,
        help_text=_(
            'Declare o total de pontos apurados, o nível de RSC pretendido e solicite a análise pela CRSC-PCCTAE. '
            'Conforme o Anexo IV do Decreto RSC-PCCTAE: "À vista das informações apresentadas, totalizo ___ pontos '
            'e atendo aos critérios legais e regulamentares para o nível ___ do RSC-PCCTAE. '
            'Solicito a análise pela CRSC-PCCTAE."'
        ),
    )
    data_cadastro = models.DateTimeFieldPlus(_('Data de cadastro'), auto_now_add=True)
    data_alteracao = models.DateTimeFieldPlus(_('Data de alteração'), auto_now=True)

    class Meta:
        verbose_name = _('Memorial Descritivo RSC-TAE')
        verbose_name_plural = _('Memoriais Descritivos RSC-TAE')

    def __str__(self):
        return f'Memorial Descritivo — {self.processo}'
