from django.urls import reverse_lazy
from djtools.db import models
from comum.models import Ano
from djtools.utils import get_datetime_now
from django.db.models import Sum


class StatusPaint(models.IntegerChoices):
    PLANEJAMENTO = 0, 'Planejamento'
    CONSOLIDADO = 10, 'Consolidado'
    PUBLICADO = 20, 'Publicado'


class Paint(models.ModelPlus):
    ano = models.ForeignKeyPlus(Ano, verbose_name='Ano', on_delete=models.CASCADE)

    criado_por = models.CurrentUserField(verbose_name='Cadastrado Por', related_name='%(app_label)s_%(class)s_cadastrado_por')
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_por = models.ForeignKeyPlus(
        'comum.Vinculo',
        null=True,
        blank=True,
        verbose_name='Atualizado Por',
        on_delete=models.CASCADE,
        related_name='%(app_label)s_%(class)s_atualizado_por',
    )
    atualizado_em = models.DateTimeField(auto_now=True)

    status = models.PositiveSmallIntegerField(choices=StatusPaint.choices, default=StatusPaint.PLANEJAMENTO, verbose_name='Status')

    inicio_periodo_planejamento = models.DateField(null=True, blank=True, verbose_name='Início do Período de Planejamento Anual')

    fim_periodo_planejamento = models.DateField(null=True, blank=True, verbose_name='Fim do Período de Planejamento Anual')

    sincronizar_afastamentos_suap = models.BooleanField(
        default=True,
        verbose_name='Sincronizar Férias e Afastamentos do SUAP',
        help_text=(
            'Quando marcado, o cálculo da carga horária dos auditores busca as férias validadas e os afastamentos '
            'concedidos pelo RH. Desmarcado, os afastamentos já importados continuam valendo, mas nenhuma fonte nova '
            'é consultada — só contam os afastamentos declarados no planejamento.'
        ),
    )

    class Meta:
        verbose_name = 'Plano Anual de Auditoria Interna (PAINT)'
        verbose_name_plural = 'Planos Anuais de Auditoria Interna (PAINTs)'

    def __str__(self):
        return f'PAINT {self.ano}'

    def get_absolute_url(self):
        return reverse_lazy('auditoria:visualizar_paint', args=[self.pk])

    def esta_no_periodo_de_cadastro(self) -> bool:
        hoje = get_datetime_now().date()
        return (
            self.status == StatusPaint.PLANEJAMENTO
            and self.inicio_periodo_planejamento
            and self.fim_periodo_planejamento
            and self.inicio_periodo_planejamento <= hoje <= self.fim_periodo_planejamento
        )

    def carga_horaria_prevista(self) -> int:
        result = self.planejamentos_anuais.aggregate(total_ch=Sum('carga_horaria_prevista'))
        return result['total_ch'] or 0

    def carga_horaria_homologada(self) -> int:
        result = self.planejamentos_anuais.aggregate(total_ch=Sum('carga_horaria_homologada'))
        return result['total_ch'] or 0

    def carga_horaria_afastada_homologada(self) -> int:
        result = self.planejamentos_anuais.aggregate(total_ch=Sum('carga_horaria_afastada_homologada'))
        return result['total_ch'] or 0

    def carga_horaria_liquida(self) -> int:
        ch_consolidada: int = 0
        for planejamento in self.planejamentos_anuais.all():
            ch_consolidada += planejamento.carga_horaria_liquida
        return ch_consolidada

    def carga_horaria_afastada(self) -> int:
        ch_afastada: int = 0
        for planejamento in self.planejamentos_anuais.all():
            ch_afastada += planejamento.carga_horaria_afastada
        return ch_afastada
