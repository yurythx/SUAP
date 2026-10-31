from decimal import Decimal

from django.db.models.functions import Now
from django.utils.translation import gettext_lazy as _

from djtools.db import models

from rsc_tae.enums import MotivoIndeferimento, SituacaoProcesso


class VotoDeliberacaoFinalRSCTae(models.ModelPlus):
    """Voto de um membro da comissão na deliberação final do processo.

    Cada membro registra um voto (deferido/indeferido + pontuação + justificativa). Ao atingir
    o quórum (ConfiguracaoRSCTae.quantidade_deliberacoes_item), o resultado é definido por maioria
    simples e a decisão consolidada (DeliberacaoCRSCRSCTae) é gerada. Em caso de empate, o processo
    aguarda o voto de minerva do presidente.
    """

    RESULTADO_CHOICES = (
        (SituacaoProcesso.DEFERIDO, 'Deferido'),
        (SituacaoProcesso.INDEFERIDO, 'Indeferido'),
    )

    processo = models.ForeignKeyPlus(
        'rsc_tae.ProcessoRSCTae',
        verbose_name=_('Processo'),
        on_delete=models.CASCADE,
        related_name='votos_deliberacao_final',
    )
    deliberado_por_vinculo = models.ForeignKeyPlus(
        'comum.Vinculo',
        verbose_name=_('Deliberado por'),
        on_delete=models.PROTECT,
        related_name='rsc_tae_votos_deliberacao_final_set',
    )
    resultado = models.PositiveIntegerField(_('Resultado'), choices=RESULTADO_CHOICES)
    pontuacao_final = models.DecimalField(
        _('Pontuação final (voto)'),
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text=_('Pontuação final do processo atribuída pelo membro. Ao indeferir, conta como 0.'),
    )
    justificativa = models.TextField(_('Justificativa'), blank=True)
    motivos_indeferimento = models.JSONField(
        _('Motivos do indeferimento'),
        default=list,
        blank=True,
        help_text=_('Códigos de MotivoIndeferimento marcados pelo membro ao votar pelo indeferimento (constatações do parecer).'),
    )
    desempate = models.BooleanField(
        _('Voto de desempate'),
        default=False,
        help_text=_('Voto de desempate do presidente, registrado apenas quando os membros empatam a deliberação final.'),
    )
    ip = models.GenericIPAddressField(_('IP'), null=True, blank=True)
    user_agent = models.CharField(_('User-Agent'), max_length=255, blank=True)
    data_deliberacao = models.DateTimeField(_('Data do voto'), auto_now=True, db_default=Now())

    # Assinatura de integridade — gerada no momento do registro do voto (padrão SHA-256).
    assinatura_hash = models.CharField(
        _('Hash da assinatura'),
        max_length=64,
        null=True,
        blank=True,
        help_text=_('SHA-256 do voto no momento do registro. Permite detectar alterações posteriores.'),
    )
    assinatura_conteudo = models.TextField(
        _('Conteúdo da assinatura'),
        null=True,
        blank=True,
        help_text=_('JSON com os dados do voto (membro, resultado, pontuação, justificativa) que geraram o hash.'),
    )

    class Meta:
        verbose_name = _('Voto da Deliberação Final (RSC-TAE)')
        verbose_name_plural = _('Votos da Deliberação Final (RSC-TAE)')
        ordering = ('processo', 'data_deliberacao')
        constraints = [
            models.UniqueConstraint(
                fields=['processo', 'deliberado_por_vinculo', 'desempate'],
                name='uq_rsc_tae_voto_deliberacao_final_membro',
            )
        ]

    @property
    def pontuacao_efetiva(self):
        """Pontuação (final) que este voto representa: 0 se indeferido, senão a informada."""
        if self.resultado == SituacaoProcesso.INDEFERIDO:
            return Decimal('0')
        return self.pontuacao_final or Decimal('0')

    @property
    def motivos_indeferimento_display(self) -> list[str]:
        """Rótulos dos motivos de indeferimento marcados neste voto (para exibição)."""
        labels = dict(MotivoIndeferimento.LABELS)
        return [labels[int(m)] for m in (self.motivos_indeferimento or []) if int(m) in labels]

    def gerar_assinatura(self):
        """Gera e persiste o hash SHA-256 do voto (integridade/conferência posterior)."""
        import hashlib
        import json

        self.refresh_from_db()
        conteudo = {
            'voto_id': self.pk,
            'processo_id': self.processo_id,
            'deliberado_por_vinculo_id': self.deliberado_por_vinculo_id,
            'deliberado_por_nome': str(self.deliberado_por_vinculo.pessoa.nome),
            'resultado': 'DEFERIDO' if self.resultado == SituacaoProcesso.DEFERIDO else 'INDEFERIDO',
            'pontuacao_final': str(self.pontuacao_final if self.pontuacao_final is not None else ''),
            'justificativa': self.justificativa or '',
            'motivos_indeferimento': sorted(int(m) for m in (self.motivos_indeferimento or [])),
            'desempate': bool(self.desempate),
            'data_deliberacao': self.data_deliberacao.isoformat() if self.data_deliberacao else None,
        }
        conteudo_json = json.dumps(conteudo, sort_keys=True, ensure_ascii=False, default=str)
        hash_valor = hashlib.sha256(conteudo_json.encode('utf-8')).hexdigest()
        VotoDeliberacaoFinalRSCTae.objects.filter(pk=self.pk).update(assinatura_conteudo=conteudo_json, assinatura_hash=hash_valor)
        self.assinatura_conteudo = conteudo_json
        self.assinatura_hash = hash_valor
        return conteudo_json, hash_valor

    def __str__(self):
        return f'Voto final #{self.pk} — processo {self.processo_id}'
