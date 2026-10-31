from djtools.db import models
from django.contrib.contenttypes.models import ContentType
from djtools.utils import get_datetime_now
from comum.models import User, Vinculo


class AcaoPermissao(models.IntegerChoices):
    VISUALIZAR = 1, 'Visualizar'
    ADICIONAR = 2, 'Adicionar'
    ALTERAR = 3, 'Alterar'
    EXCLUIR = 4, 'Excluir'
    GERENCIAR = 5, 'Gerenciar'


class PermissaoDeChefe(models.ModelPlus):
    vinculo_permitido = models.ForeignKey(
        Vinculo,
        verbose_name='Vinculo com Poder de Chefe',
        related_name='%(app_label)s_%(class)s_vinculo_permitido',
        on_delete=models.CASCADE,
    )

    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE, verbose_name='Modelo da auditoria')
    acao = models.PositiveSmallIntegerField(choices=AcaoPermissao.choices, default=AcaoPermissao.GERENCIAR, verbose_name='Ação')

    concedido_em = models.DateTimeField(auto_now_add=True, verbose_name='Data de concessão')
    concedido_por = models.ForeignKeyPlus(
        User,
        verbose_name='Concedido por',
        editable=False,
        null=False,
        blank=False,
        related_name='%(app_label)s_%(class)s_concedido_por_set',
    )

    revogado_em = models.DateTimeField(null=True, blank=True, verbose_name='Data de revogação')
    revogado_por = models.ForeignKey(
        User, verbose_name='Revogado por', null=True, blank=True, on_delete=models.SET_NULL, related_name='%(app_label)s_%(class)s_revogado_por_set'
    )
    motivo_revogacao = models.TextField(blank=True, default='', verbose_name='Motivo da revogação')

    class Meta:
        verbose_name = 'Permissão de Chefe'
        verbose_name_plural = 'Permissões de Chefes'
        constraints = [
            models.UniqueConstraint(
                fields=['vinculo_permitido', 'content_type', 'acao'],
                name='unica_perm_chefe_por_modelo',
            ),
        ]

    @property
    def ativa(self) -> bool:
        return bool(self.revogado_em is None)

    def revogar(self, por_usuario, motivo: str | None = None):
        if self.revogado_em:
            return
        self.revogado_em = get_datetime_now()
        self.revogado_por = por_usuario
        self.motivo_revogacao = motivo or ''
        self.save(update_fields=['revogado_em', 'revogado_por', 'motivo_revogacao'])
