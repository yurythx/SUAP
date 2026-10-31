import hashlib
import json

from django.core.exceptions import ValidationError
from django.db.models.functions import Now
from django.utils.translation import gettext_lazy as _

from djtools.db import models

from rsc_tae.enums import SituacaoProcesso


class DeliberacaoCRSCRSCTae(models.ModelPlus):
    """Decisão final da CRSC-PCCTAE/IFRN sobre o processo RSC-TAE.

    Criada por quem tem a permissão 'deliberar_crsc_processorsctae' após
    todos os avaliadores auxiliares finalizarem (estado AGUARDANDO_CRSC).
    A CRSC pode divergir da pontuação preliminar dos avaliadores.
    A justificativa é obrigatória no indeferimento, inclusive quando
    a pontuação mínima foi atingida (Art. 13, IV do regulamento).
    """

    RESULTADO_CHOICES = (
        (SituacaoProcesso.DEFERIDO, 'Deferido'),
        (SituacaoProcesso.INDEFERIDO, 'Indeferido'),
    )

    processo = models.OneToOneField(
        'rsc_tae.ProcessoRSCTae',
        verbose_name=_('Processo'),
        on_delete=models.CASCADE,
        related_name='deliberacao_crsc',
    )
    resultado = models.PositiveIntegerField(
        _('Resultado'),
        choices=RESULTADO_CHOICES,
    )
    pontuacao_final_crsc = models.DecimalField(
        _('Pontuação final (CRSC)'),
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text=_('Pontuação atribuída pela CRSC. Pode divergir da média dos avaliadores auxiliares.'),
    )
    justificativa = models.TextField(
        _('Justificativa'),
        blank=True,
        help_text=_('Obrigatória no indeferimento, inclusive quando a pontuação mínima foi atingida (Art. 13, IV).'),
    )
    motivos_indeferimento = models.JSONField(
        _('Motivos do indeferimento'),
        default=list,
        blank=True,
        help_text=_('União distinta dos códigos de MotivoIndeferimento marcados pelos votos de indeferimento — exibida no parecer conclusivo.'),
    )
    deliberado_por_vinculo = models.ForeignKeyPlus(
        'comum.Vinculo',
        verbose_name=_('Deliberado por'),
        on_delete=models.PROTECT,
        related_name='rsc_tae_deliberacoes_crsc_set',
    )
    finalizacao_manual = models.BooleanField(
        _('Finalização manual'),
        default=False,
        help_text=_(
            'Marca quando a deliberação foi consolidada manualmente a partir dos votos já existentes '
            '(ex.: reconsolidação após reversão da finalização), em vez de fechar automaticamente com o último voto.'
        ),
    )
    data_deliberacao = models.DateTimeFieldPlus(_('Data da deliberação'), auto_now_add=True, db_default=Now())
    ip_deliberacao = models.GenericIPAddressField(_('IP'), null=True, blank=True)
    user_agent = models.TextField(_('User-agent'), blank=True)

    # Assinatura de integridade — mesmo padrão SHA-256 usado em AvaliacaoProcessoRSCTae
    assinatura_hash = models.CharField(
        _('Hash da assinatura'),
        max_length=64,
        null=True,
        blank=True,
    )
    assinatura_conteudo = models.TextField(
        _('Conteúdo da assinatura'),
        null=True,
        blank=True,
        help_text=_('JSON com os dados no momento da deliberação. Permite detectar alterações posteriores.'),
    )

    class Meta:
        verbose_name = _('Deliberação da CRSC (RSC-TAE)')
        verbose_name_plural = _('Deliberações da CRSC (RSC-TAE)')
        ordering = ('-data_deliberacao',)

    def __str__(self):
        return f'Deliberação #{self.pk} — {self.processo} — {self.get_resultado_display()}'

    def clean(self):
        if self.resultado == SituacaoProcesso.INDEFERIDO and not (self.justificativa or '').strip():
            raise ValidationError(
                {
                    'justificativa': _(
                        'A justificativa é obrigatória no indeferimento, inclusive quando a pontuação mínima foi atingida (Art. 13, IV).'
                    )
                }
            )

    def gerar_assinatura(self):
        """Gera e persiste o hash SHA-256 do conteúdo desta deliberação."""
        processo = self.processo
        nivel = processo.nivel_requisitado

        conteudo = {
            'deliberacao_id': self.pk,
            'processo_id': processo.pk,
            'avaliado_vinculo_id': processo.vinculo_id,
            'avaliado_nome': str(processo.vinculo.pessoa.nome),
            'nivel_requisitado_id': nivel.pk,
            'nivel_requisitado_nome': str(nivel),
            'nivel_pontuacao_minima': str(nivel.pontuacao_minima),
            'resultado': 'DEFERIDO' if self.resultado == SituacaoProcesso.DEFERIDO else 'INDEFERIDO',
            'pontuacao_final_crsc': str(self.pontuacao_final_crsc or ''),
            'justificativa': self.justificativa or '',
            'motivos_indeferimento': sorted(int(m) for m in (self.motivos_indeferimento or [])),
            'deliberado_por_vinculo_id': self.deliberado_por_vinculo_id,
            'finalizacao_manual': bool(self.finalizacao_manual),
            'data_deliberacao': self.data_deliberacao.isoformat() if self.data_deliberacao else None,
        }

        conteudo_json = json.dumps(conteudo, sort_keys=True, ensure_ascii=False, default=str)
        hash_valor = hashlib.sha256(conteudo_json.encode('utf-8')).hexdigest()

        DeliberacaoCRSCRSCTae.objects.filter(pk=self.pk).update(
            assinatura_conteudo=conteudo_json,
            assinatura_hash=hash_valor,
        )
        return conteudo_json, hash_valor
