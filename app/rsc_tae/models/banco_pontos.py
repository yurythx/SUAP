from decimal import Decimal

from django.db.models.functions import Now
from django.utils.translation import gettext_lazy as _

from djtools.db import models


class BancoPontosRSCTae(models.ModelPlus):
    """Banco de pontos excedentes por servidor (Art. 3º, §2º do Decreto RSC-PCCTAE).

    Cada servidor tem no máximo um banco. O saldo representa pontos obtidos em
    concessões anteriores que ultrapassaram o mínimo exigido e que podem ser
    aproveitados no próximo requerimento RSC.
    """

    vinculo = models.OneToOneField(
        'comum.Vinculo',
        verbose_name=_('Servidor'),
        on_delete=models.PROTECT,
        related_name='rsc_tae_banco_pontos',
    )
    saldo = models.DecimalField(
        _('Saldo atual'),
        max_digits=10,
        decimal_places=2,
        default=Decimal('0'),
    )
    data_atualizacao = models.DateTimeField(_('Última atualização'), auto_now=True, db_default=Now())

    class Meta:
        verbose_name = _('Banco de Pontos RSC-TAE')
        verbose_name_plural = _('Banco de Pontos RSC-TAE')
        ordering = ('vinculo__pessoa__nome',)

    def __str__(self):
        try:
            nome = self.vinculo.pessoa.nome
        except Exception:
            nome = f'vínculo #{self.vinculo_id}'
        return f'{nome} — saldo: {self.saldo}'

    @classmethod
    def get_or_create_for_vinculo(cls, vinculo):
        banco, _ = cls.objects.get_or_create(vinculo=vinculo)
        return banco

    def creditar(self, valor, tipo=None, processo=None, descricao='', realizado_por=None):
        """Credita pontos ao banco dentro de uma transação e registra o movimento."""
        from django.db import transaction

        valor = Decimal(str(valor))
        if valor <= 0:
            return

        tipo = tipo or MovimentoBancoPontosRSCTae.TIPO_CREDITO_DEFERIMENTO

        with transaction.atomic():
            banco = BancoPontosRSCTae.objects.select_for_update().get(pk=self.pk)
            banco.saldo = (banco.saldo or Decimal('0')) + valor
            banco.save(update_fields=['saldo', 'data_atualizacao'])
            MovimentoBancoPontosRSCTae.objects.create(
                banco=banco,
                tipo=tipo,
                valor=valor,
                saldo_apos=banco.saldo,
                processo=processo,
                descricao=descricao,
                realizado_por_vinculo=realizado_por,
            )
        self.saldo = banco.saldo

    def debitar(self, valor, tipo=None, processo=None, descricao='', realizado_por=None):
        """Debita pontos do banco dentro de uma transação e registra o movimento.

        O saldo nunca fica negativo: se `valor` exceder o saldo disponível,
        debita apenas o saldo existente.
        """
        from django.db import transaction

        valor = Decimal(str(valor))
        if valor <= 0:
            return

        tipo = tipo or MovimentoBancoPontosRSCTae.TIPO_DEBITO_UTILIZACAO

        with transaction.atomic():
            banco = BancoPontosRSCTae.objects.select_for_update().get(pk=self.pk)
            saldo_atual = banco.saldo or Decimal('0')
            valor_efetivo = min(valor, saldo_atual)
            banco.saldo = saldo_atual - valor_efetivo
            banco.save(update_fields=['saldo', 'data_atualizacao'])
            if valor_efetivo > 0:
                MovimentoBancoPontosRSCTae.objects.create(
                    banco=banco,
                    tipo=tipo,
                    valor=valor_efetivo,
                    saldo_apos=banco.saldo,
                    processo=processo,
                    descricao=descricao,
                    realizado_por_vinculo=realizado_por,
                )
        self.saldo = banco.saldo


class MovimentoBancoPontosRSCTae(models.ModelPlus):
    """Registro imutável de cada entrada e saída do banco de pontos.

    Cada linha representa um único evento; o campo ``saldo_apos`` permite
    reconstituir o extrato sem precisar refazer todos os cálculos.
    """

    TIPO_CREDITO_DEFERIMENTO = 1
    TIPO_DEBITO_UTILIZACAO = 2
    TIPO_AJUSTE_CREDITO = 3
    TIPO_AJUSTE_DEBITO = 4
    TIPO_DEVOLUCAO_INDEFERIMENTO = 5

    TIPO_CHOICES = (
        (TIPO_CREDITO_DEFERIMENTO, 'Crédito por deferimento'),
        (TIPO_DEBITO_UTILIZACAO, 'Débito por utilização em novo processo'),
        (TIPO_AJUSTE_CREDITO, 'Ajuste de crédito (manual)'),
        (TIPO_AJUSTE_DEBITO, 'Ajuste de débito (manual)'),
        (TIPO_DEVOLUCAO_INDEFERIMENTO, 'Devolução por indeferimento do processo'),
    )

    TIPOS_CREDITO = {TIPO_CREDITO_DEFERIMENTO, TIPO_AJUSTE_CREDITO, TIPO_DEVOLUCAO_INDEFERIMENTO}
    TIPOS_DEBITO = {TIPO_DEBITO_UTILIZACAO, TIPO_AJUSTE_DEBITO}

    banco = models.ForeignKeyPlus(
        BancoPontosRSCTae,
        verbose_name=_('Banco'),
        on_delete=models.CASCADE,
        related_name='movimentos',
    )
    tipo = models.PositiveSmallIntegerField(_('Tipo'), choices=TIPO_CHOICES)
    valor = models.DecimalField(_('Valor'), max_digits=10, decimal_places=2)
    saldo_apos = models.DecimalField(_('Saldo após'), max_digits=10, decimal_places=2)
    processo = models.ForeignKeyPlus(
        'rsc_tae.ProcessoRSCTae',
        verbose_name=_('Processo'),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='movimentos_banco_pontos',
    )
    descricao = models.TextField(_('Descrição'), blank=True)
    realizado_por_vinculo = models.ForeignKeyPlus(
        'comum.Vinculo',
        verbose_name=_('Realizado por'),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='rsc_tae_movimentos_banco_pontos_set',
    )
    data_movimento = models.DateTimeField(_('Data do movimento'), auto_now_add=True, db_default=Now())

    class Meta:
        verbose_name = _('Movimento do Banco de Pontos RSC-TAE')
        verbose_name_plural = _('Movimentos do Banco de Pontos RSC-TAE')
        ordering = ('-data_movimento',)

    def __str__(self):
        return f'Movimento #{self.pk} — {self.get_tipo_display()} — {self.valor}'

    @property
    def eh_credito(self):
        return self.tipo in self.TIPOS_CREDITO

    @property
    def eh_debito(self):
        return self.tipo in self.TIPOS_DEBITO
