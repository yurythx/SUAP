from django.conf import settings

from djtools.db import models
from djtools.db.models import ModelPlus


class DecisaoEspecificacao(ModelPlus):
    ORIGEM_MANUAL = 'manual'
    ORIGEM_AGENTE = 'agente'
    ORIGEM_AGENTE_CI = 'agente-ci'
    ORIGEM_CHOICES = (
        (ORIGEM_MANUAL, 'Manual'),
        (ORIGEM_AGENTE, 'Agente'),
        (ORIGEM_AGENTE_CI, 'Agente CI'),
    )

    demanda = models.ForeignKeyPlus(
        'demandas.Demanda',
        verbose_name='Demanda',
        on_delete=models.CASCADE,
        related_name='decisoes_especificacao',
    )
    autor = models.ForeignKeyPlus(
        settings.AUTH_USER_MODEL,
        verbose_name='Autor',
        on_delete=models.PROTECT,
    )
    criado_em = models.DateTimeField('Criado em', auto_now_add=True)
    decisao = models.TextField('Decisão')
    contexto = models.JSONField('Contexto', default=dict, blank=True)
    origem = models.CharFieldPlus(
        'Origem',
        max_length=10,
        choices=ORIGEM_CHOICES,
        default=ORIGEM_MANUAL,
    )

    class Meta:
        verbose_name = 'Decisão de Especificação'
        verbose_name_plural = 'Decisões de Especificação'
        ordering = ['criado_em']

    def __str__(self) -> str:
        return f'{self.demanda} — {self.decisao[:60]}'
