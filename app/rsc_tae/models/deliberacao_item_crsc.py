from django.db.models.functions import Now
from django.utils.translation import gettext_lazy as _

from djtools.db import models


class DeliberacaoItemCRSCRSCTae(models.ModelPlus):
    """Voto de um membro da comissão sobre uma divergência de avaliação por anexo.

    Cada membro da comissão registra um voto por anexo com divergência. Ao atingir a
    quantidade configurada de votos (ConfiguracaoRSCTae.quantidade_deliberacoes_item),
    a nota do item é consolidada pela maioria (pontuação mais votada; maior em caso de empate).

    Uma divergência existe quando:
    - Ao menos um avaliador indeferiu o anexo, ou
    - Ao menos um avaliador alterou a pontuação validada, ou
    - Os avaliadores discordam entre si (um defere, outro indefere).
    """

    DECISAO_DEFERIR = 2
    DECISAO_INDEFERIR = 3

    DECISAO_CHOICES = (
        (DECISAO_DEFERIR, 'Deferir'),
        (DECISAO_INDEFERIR, 'Indeferir'),
    )

    processo = models.ForeignKeyPlus(
        'rsc_tae.ProcessoRSCTae',
        verbose_name=_('Processo'),
        on_delete=models.CASCADE,
        related_name='deliberacoes_item_crsc',
    )
    anexo = models.ForeignKeyPlus(
        'rsc_tae.RolSaberCompetenciaAnexo',
        verbose_name=_('Anexo'),
        on_delete=models.CASCADE,
        related_name='deliberacoes_crsc',
    )
    decisao = models.PositiveSmallIntegerField(
        _('Decisão da CRSC'),
        choices=DECISAO_CHOICES,
    )
    pontuacao_crsc = models.DecimalField(
        _('Pontuação (unidades) do voto'),
        max_digits=7,
        decimal_places=2,
        null=True,
        blank=True,
        help_text=_('Unidades reconhecidas pelo membro para este anexo. Ao indeferir, conta como 0.'),
    )
    justificativa = models.TextField(
        _('Justificativa'),
        blank=True,
        help_text=_('Obrigatória quando a CRSC diverge dos avaliadores auxiliares.'),
    )
    deliberado_por_vinculo = models.ForeignKeyPlus(
        'comum.Vinculo',
        verbose_name=_('Deliberado por'),
        on_delete=models.PROTECT,
        related_name='rsc_tae_deliberacoes_item_crsc_set',
    )
    desempate = models.BooleanField(
        _('Voto de desempate'),
        default=False,
        help_text=_('Voto de desempate do presidente, registrado apenas quando os membros empatam a deliberação do item.'),
    )
    data_deliberacao = models.DateTimeField(
        _('Data da deliberação'),
        auto_now=True,
        db_default=Now(),
    )

    # Assinatura de integridade — gerada no momento do registro do voto (padrão SHA-256).
    assinatura_hash = models.CharField(
        _('Hash da assinatura'),
        max_length=64,
        null=True,
        blank=True,
        help_text=_('SHA-256 do voto de item no momento do registro. Permite detectar alterações posteriores.'),
    )
    assinatura_conteudo = models.TextField(
        _('Conteúdo da assinatura'),
        null=True,
        blank=True,
        help_text=_('JSON com os dados do voto de item (membro, anexo, decisão, pontuação, justificativa) que geraram o hash.'),
    )

    class Meta:
        verbose_name = _('Deliberação de Item pela CRSC (RSC-TAE)')
        verbose_name_plural = _('Deliberações de Itens pela CRSC (RSC-TAE)')
        ordering = ('processo', 'anexo', 'data_deliberacao')
        constraints = [
            models.UniqueConstraint(
                fields=['processo', 'anexo', 'deliberado_por_vinculo', 'desempate'],
                name='uq_rsc_tae_deliberacao_item_crsc_membro',
            )
        ]

    @property
    def pontuacao_efetiva(self):
        """Pontuação (unidades) que este voto representa: 0 se indeferido, senão a informada."""
        from decimal import Decimal

        if self.decisao == self.DECISAO_INDEFERIR:
            return Decimal('0')
        return self.pontuacao_crsc or Decimal('0')

    def gerar_assinatura(self):
        """Gera e persiste o hash SHA-256 do voto de item (integridade/conferência posterior)."""
        import hashlib
        import json

        self.refresh_from_db()
        conteudo = {
            'deliberacao_item_id': self.pk,
            'processo_id': self.processo_id,
            'anexo_id': self.anexo_id,
            'deliberado_por_vinculo_id': self.deliberado_por_vinculo_id,
            'deliberado_por_nome': str(self.deliberado_por_vinculo.pessoa.nome),
            'decisao': self.get_decisao_display(),
            'pontuacao_crsc': str(self.pontuacao_crsc if self.pontuacao_crsc is not None else ''),
            'justificativa': self.justificativa or '',
            'desempate': bool(self.desempate),
            'data_deliberacao': self.data_deliberacao.isoformat() if self.data_deliberacao else None,
        }
        conteudo_json = json.dumps(conteudo, sort_keys=True, ensure_ascii=False, default=str)
        hash_valor = hashlib.sha256(conteudo_json.encode('utf-8')).hexdigest()
        DeliberacaoItemCRSCRSCTae.objects.filter(pk=self.pk).update(assinatura_conteudo=conteudo_json, assinatura_hash=hash_valor)
        self.assinatura_conteudo = conteudo_json
        self.assinatura_hash = hash_valor
        return conteudo_json, hash_valor

    def __str__(self):
        return f'Voto item #{self.pk} — processo {self.processo_id} — anexo {self.anexo_id}'
