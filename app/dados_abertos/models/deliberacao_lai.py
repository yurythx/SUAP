from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from djtools.db import models
from djtools.db.models import ModelPlus

from ..enums import TipoEventoLAI


class DeliberacaoLAI(ModelPlus):
    """Linha do tempo de um dataset no ciclo de deliberação LAI, dentro de um PDA.

    Um registro por evento — envio, liberação, devolução, reenvio após ajustes e reabertura por
    edição de conteúdo. Guarda o que foi pedido pelo Responsável LAI e o que o gestor respondeu,
    de modo que as rodadas anteriores permaneçam legíveis.

    O nome da classe é mantido (apesar de o model ter deixado de ser só "deliberação") porque a
    permissão ``deliberar_lai`` é declarada aqui e referenciada como ``deliberacaolai`` no
    ``permissions.yaml``: renomear moveria a permissão e quebraria os grupos já sincronizados.
    """

    pda_base_dados = models.ForeignKeyPlus(
        'dados_abertos.PDABaseDados',
        on_delete=models.CASCADE,
        related_name='eventos_lai',
        verbose_name=_('Base de Dados no PDA'),
    )
    tipo = models.IntegerField(_('Evento'), choices=TipoEventoLAI.get_choices())
    texto = models.TextField(
        _('Parecer/Resposta'),
        blank=True,
        help_text=_('Parecer do Responsável LAI na devolução, ou a resposta do gestor no reenvio.'),
    )
    autor = models.ForeignKeyPlus(
        'comum.Vinculo',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_('Autor'),
        help_text=_('Vazio nos eventos automáticos (envio pela etapa e reabertura por edição).'),
    )
    data = models.DateTimeFieldPlus(_('Data'), auto_now_add=True)
    ip = models.GenericIPAddressField(_('IP'), null=True, blank=True)
    user_agent = models.TextField(_('User agent'), blank=True)

    class Meta:
        verbose_name = _('Evento LAI')
        verbose_name_plural = _('Eventos LAI')
        ordering = ('-data', '-id')
        permissions = [('deliberar_lai', 'Pode deliberar sobre a liberação LAI de datasets')]

    def __str__(self):
        return f'{self.get_tipo_display()} — {self.pda_base_dados}'

    def get_absolute_url(self) -> str:
        """Aba "lai" da visualização da base: o registro só faz sentido no contexto dela."""
        return f'{self.pda_base_dados.base_dados.get_absolute_url()}?tab=lai'

    @property
    def automatico(self) -> bool:
        return self.tipo in TipoEventoLAI.AUTOMATICOS

    @property
    def classe_timeline(self) -> str:
        """Classe do item na timeline do Design System."""
        return TipoEventoLAI.CLASSES.get(self.tipo, 'info')

    def clean(self):
        super().clean()
        if self.tipo in TipoEventoLAI.EXIGEM_TEXTO and not (self.texto or '').strip():
            rotulo = _('O parecer é obrigatório ao devolver o dataset para ajustes.')
            if self.tipo == TipoEventoLAI.REENVIO:
                rotulo = _('Descreva o que foi ajustado antes de reenviar ao Responsável LAI.')
            raise ValidationError({'texto': rotulo})
