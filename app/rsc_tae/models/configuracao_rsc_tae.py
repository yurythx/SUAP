from djtools.db import models
from tinymce.models import HTMLField
from django.utils.translation import gettext_lazy as _


class ConfiguracaoRSCTae(models.ModelPlus):
    """
    Configurações gerais para o RSC TAE.
    """

    titulo = models.CharField(
        verbose_name=_('Título da configuração'),
        max_length=200,
        default='Configuração RSC-TAE',
        help_text=_('Nome descritivo para identificar este conjunto de configurações.'),
    )
    texto_instrucao_preenchimento = HTMLField(
        verbose_name=_('Texto de instrução para preenchimento'),
        blank=True,
        help_text=_('Texto de instrução para o preenchimento do processo, exibido para os usuários durante o preenchimento.'),
    )
    texto_instrucao_avaliacao = HTMLField(
        verbose_name=_('Texto de instrução para avaliação'),
        blank=True,
        help_text=_('Texto de instrução para a avaliação do processo, exibido para os avaliadores durante a avaliação.'),
    )

    # ------------------------------------------------------------------ #
    # SLAs por etapa (em dias corridos)                                    #
    # ------------------------------------------------------------------ #
    dias_prazo_preenchimento = models.PositiveIntegerField(
        verbose_name=_('Prazo para preenchimento pelo servidor (dias)'),
        default=30,
        help_text=_(
            'Quantidade de dias corridos que o servidor tem para concluir o preenchimento após a abertura do processo ou retorno de correção.'
        ),
    )
    dias_prazo_validacao_rh = models.PositiveIntegerField(
        verbose_name=_('Prazo para validação pelo RH (dias)'),
        default=10,
        help_text=_(
            'Quantidade de dias corridos que o RH tem para validar ou devolver o documento preliminar após o servidor concluir o preenchimento.'
        ),
    )
    dias_prazo_correcao = models.PositiveIntegerField(
        verbose_name=_('Prazo para correção pelo servidor (dias)'),
        default=15,
        help_text=_(
            'Quantidade de dias corridos que o servidor tem para corrigir e reenviar o processo após solicitação de correção pelo RH ou avaliadores.'
        ),
    )
    dias_prazo_avaliacao = models.PositiveIntegerField(
        verbose_name=_('Prazo para avaliação pelos avaliadores (dias)'),
        default=20,
        help_text=_('Quantidade de dias corridos que os avaliadores têm para finalizar a avaliação após o processo entrar em "Em Análise".'),
    )
    dias_uteis_prazo_avaliador = models.PositiveIntegerField(
        verbose_name=_('Prazo por avaliador auxiliar (dias úteis)'),
        default=10,
        help_text=_('Dias úteis que cada avaliador auxiliar tem para concluir a avaliação a partir da notificação do sorteio (Art. 18, IV).'),
    )
    quantidade_deliberacoes_item = models.PositiveIntegerField(
        verbose_name=_('Deliberações por item com divergência (CRSC)'),
        default=4,
        help_text=_(
            'Número de deliberações de membros da comissão necessárias para consolidar a nota de um item com '
            'divergência. Ao atingir esta quantidade, a nota final é a pontuação mais votada (maior, em caso de empate).'
        ),
    )

    # ------------------------------------------------------------------ #
    # Sinalização na listagem de processos                                 #
    # ------------------------------------------------------------------ #
    situacoes_exercicio_externo = models.ManyToManyFieldPlus(
        'rh.Situacao',
        verbose_name=_('Situações de exercício externo ao órgão'),
        blank=True,
        related_name='configuracoes_rsc_tae_exercicio_externo',
        help_text=_(
            'Situações funcionais do SIAPE em que o servidor está em exercício fora do IFRN — por exemplo '
            '"03 - Cedido/Requisitado" e "08 - Ativo em outro órgão". Usada apenas para sinalizar o processo na '
            'listagem, visível ao RH sistêmico e à CRSC; não altera o fluxo nem o sorteio de avaliadores. '
            'Enquanto nenhuma situação for marcada, nenhum processo é sinalizado.'
        ),
    )

    class Meta:
        verbose_name = _('Configuração do RSC-TAE')
        verbose_name_plural = _('Configurações do RSC-TAE')

    def __str__(self):
        return self.titulo or 'Configuração RSC-TAE'
