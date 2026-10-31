from djtools.db import models
from django.db.models.functions import Now
from django.urls import reverse
from django.utils.translation import gettext_lazy as _


class ComissaoRSCTae(models.ModelPlus):
    """Comissão analisadora de processos RSC-TAE.

    Apenas uma comissão pode estar ativa por vez. Ao ativar uma comissão,
    as demais são automaticamente desativadas.
    """

    nome = models.CharFieldPlus(_('Nome'), max_length=200)
    descricao = models.TextField(_('Descrição'), blank=True)
    data_inicio = models.DateFieldPlus(_('Data de início'))
    data_fim = models.DateFieldPlus(_('Data de término'), null=True, blank=True)
    ativa = models.BooleanFieldPlus(
        _('Ativa'),
        default=False,
        help_text=_('Apenas uma comissão pode estar ativa por vez. Os membros desta comissão serão os candidatos a avaliadores.'),
    )
    data_cadastro = models.DateTimeFieldPlus(_('Data de cadastro'), auto_now_add=True, db_default=Now())
    data_alteracao = models.DateTimeFieldPlus(_('Data de alteração'), auto_now=True, db_default=Now())

    class Meta:
        verbose_name = _('Comissão RSC-TAE')
        verbose_name_plural = _('Comissões RSC-TAE')
        ordering = ('-data_inicio',)

    def __str__(self):
        status = ' (ativa)' if self.ativa else ''
        return f'{self.nome}{status}'

    def get_absolute_url(self):
        return reverse('rsc_tae:visualizar_comissao', kwargs={'comissao_id': self.pk})

    def save(self, *args, **kwargs):
        # Garante unicidade da comissão ativa
        if self.ativa:
            ComissaoRSCTae.objects.exclude(pk=self.pk).filter(ativa=True).update(ativa=False)
        super().save(*args, **kwargs)


class CategoriaMembroComissaoRSCTae(models.ModelPlus):
    """Origem/representação do membro na comissão — CONSUP, DIGPE, CIS-PCCTAE etc.

    Cadastro livre, e não um choices fixo: hoje são três, mas nada impede a criação de outras, e
    cada categoria cadastrada vira um card no painel da comissão.
    """

    nome = models.CharFieldPlus(_('Nome'), max_length=100, unique=True, help_text=_('Sigla ou nome exibido no card, ex.: CONSUP.'))
    descricao = models.TextField(_('Descrição'), blank=True)
    ordem = models.PositiveIntegerField(
        _('Ordem'),
        default=0,
        help_text=_('Posição do card no painel da comissão, da menor para a maior. Empate é desfeito pelo nome.'),
    )
    data_cadastro = models.DateTimeFieldPlus(_('Data de cadastro'), auto_now_add=True, db_default=Now())

    class Meta:
        verbose_name = _('Categoria de membro da comissão RSC-TAE')
        verbose_name_plural = _('Categorias de membros da comissão RSC-TAE')
        ordering = ('ordem', 'nome')

    def __str__(self):
        return self.nome


class MembroComissaoRSCTae(models.ModelPlus):
    """Membro de uma comissão analisadora RSC-TAE."""

    comissao = models.ForeignKeyPlus(
        ComissaoRSCTae,
        verbose_name=_('Comissão'),
        on_delete=models.CASCADE,
        related_name='membros',
    )
    vinculo = models.ForeignKeyPlus(
        'comum.Vinculo',
        verbose_name=_('Usuário'),
        on_delete=models.CASCADE,
        related_name='rsc_tae_comissoes_set',
    )
    ativo = models.BooleanFieldPlus(
        _('Ativo'),
        default=True,
        help_text=_('Apenas membros ativos e sem afastamentos são elegíveis ao sorteio de avaliadores.'),
    )
    categoria = models.ForeignKeyPlus(
        CategoriaMembroComissaoRSCTae,
        verbose_name=_('Categoria'),
        # Obrigatória no formulário (a cota de deliberações por categoria não tem balde sem ela) e
        # nullable no banco, para os cadastros legados sobreviverem — eles aparecem no relatório do
        # command `verificar_cota_categoria_crsc`.
        null=True,
        # PROTECT e não SET_NULL: apagar uma categoria em uso jogaria os membros silenciosamente
        # para "Sem categoria". Aqui o admin bloqueia e obriga a reatribuir antes.
        on_delete=models.PROTECT,
        related_name='membros',
        help_text=_('Origem/representação do membro. Define em qual card ele aparece no painel da comissão.'),
    )
    presidente = models.BooleanFieldPlus(
        _('Presidente'),
        default=False,
        help_text=_(
            'Presidente(s) da comissão. Apenas presidentes podem registrar o voto de desempate quando membros empatam a deliberação de um item ou do processo.'
        ),
    )
    data_cadastro = models.DateTimeFieldPlus(_('Data de cadastro'), auto_now_add=True, db_default=Now())

    class Meta:
        verbose_name = _('Membro da comissão RSC-TAE')
        verbose_name_plural = _('Membros da comissão RSC-TAE')
        ordering = ('vinculo__pessoa__nome',)
        constraints = [
            models.UniqueConstraint(
                fields=['comissao', 'vinculo'],
                name='uq_rsc_tae_membro_comissao',
            )
        ]

    def __str__(self):
        return f'{self.vinculo} — {self.comissao}'
