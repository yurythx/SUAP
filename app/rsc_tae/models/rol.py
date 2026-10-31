from decimal import Decimal

from djtools.db import models
from django.db.models.functions import Now
from django.utils.translation import gettext_lazy as _


class RolSaberCompetencia(models.ModelPlus):
    SEARCH_FIELDS = ('nome',)

    numero = models.PositiveIntegerFieldPlus(_('Número'))
    grupo = models.ForeignKeyPlus(
        'rsc_tae.GrupoSaberCompetencia',
        verbose_name=_('Grupo'),
        on_delete=models.PROTECT,
        null=True,
        related_name='itens',
        help_text=_('Grupo de complexidade (requisito + grupo), conforme Anexo II.'),
    )
    titulo = models.CharField(_('Título'), max_length=600, null=True, blank=False)
    descricao = models.TextField(_('Descrição'))
    documentos_comprobatorios = models.TextField(_('Documentos comprobatórios'), null=True, blank=True)
    unidade_medida = models.CharField(_('Unidade de medida'), max_length=300)

    # configurações dos itens
    item_temporal = models.BooleanField(
        _('Item temporal'), default=False, help_text=_('Indica se o item é temporal e que a quantidade de meses será calculado automaticamente.')
    )

    PAPEL_TITULAR = 'titular'
    PAPEL_SUBSTITUTO = 'substituto'
    PAPEL_CHOICES = (
        (PAPEL_TITULAR, 'Titular'),
        (PAPEL_SUBSTITUTO, 'Substituto'),
    )

    aceita_papel = models.BooleanField(
        _('Aceita papel (titular/substituto)'),
        default=False,
        help_text=_(
            'Item cuja pontuação por unidade muda conforme o papel: titular usa a taxa do grupo; substituto usa pontuacao_unidade_substituto.'
        ),
    )
    pontuacao_unidade_substituto = models.DecimalField(
        _('Pontuação por unidade (substituto)'),
        max_digits=5,
        decimal_places=3,
        null=True,
        blank=True,
        help_text=_('Taxa por unidade quando o papel do comprovante é substituto. Só usada quando aceita_papel=True.'),
    )

    ativo = models.BooleanField(_('Ativo'), default=True)
    data_cadastro = models.DateTimeField(_('Data de cadastro'), auto_now_add=True, db_default=Now())
    data_alteracao = models.DateTimeField(_('Data de alteração'), auto_now=True, db_default=Now())

    class Meta:
        verbose_name = _('Rol de Saber e Competência')
        verbose_name_plural = _('Róis de Saber e Competências')
        ordering = ('grupo__requisito__numero', 'grupo__numero', 'numero')

    @property
    def pontuacao_unidade(self):
        if self.grupo_id:
            return self.grupo.pontuacao_unidade
        return Decimal('0')

    @property
    def requisito(self):
        if self.grupo_id:
            return self.grupo.requisito
        return None

    @property
    def requisito_numero(self):
        req = self.requisito
        if req:
            return req.numero
        return None

    @property
    def requisito_label_curto(self):
        if self.grupo_id:
            return self.grupo.requisito_label_curto
        return ''

    @property
    def grupo_numero(self):
        if self.grupo_id:
            return self.grupo.numero
        return None

    def __str__(self):
        if self.titulo:
            return f'{self.numero} - {self.titulo}'
        return str(self.descricao)
