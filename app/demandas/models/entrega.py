from django.core.exceptions import ValidationError
from django.utils import timezone
from reversion import revisions as reversion
from djtools.db import models
from djtools.db.models import ModelPlus


class StatusEntrega(models.TextChoices):
    """
    Ciclo de vida de uma Entrega.

    ENVIADA   → estado inicial, aguardando o demandante validar (a demanda fica "Em homologação")
    APROVADA  → demandante aprovou
    REPROVADA → demandante rejeitou; demanda retorna para desenvolvimento
    EXPIRADA  → histórico: prazo vencido no fluxo antigo, que expirava a entrega automaticamente
    CANCELADA → entrega cancelada antes de resposta (pela equipe ou ao tirar a demanda de homologação)
    """

    ENVIADA = 'ENVIADA', 'Enviada'
    APROVADA = 'APROVADA', 'Aprovada'
    REPROVADA = 'REPROVADA', 'Reprovada'
    EXPIRADA = 'EXPIRADA', 'Expirada'
    CANCELADA = 'CANCELADA', 'Cancelada'

    @classmethod
    def status_terminais(cls):
        """Status que encerram o ciclo da entrega."""
        return [cls.APROVADA, cls.REPROVADA, cls.EXPIRADA, cls.CANCELADA]


# ---------------------------------------------------------------------------
# ENTREGA
# ---------------------------------------------------------------------------


@reversion.register()
class Entrega(ModelPlus):
    """
    Representa um pacote entregue ao demandante para validação (homologação).

    Uma Demanda pode ter várias Entregas ao longo do seu ciclo de vida,
    mas apenas uma pode estar no status ENVIADA por vez. Enquanto ela existe,
    a demanda está "Em homologação" — a etapa é consequência da entrega
    (ver docs/specs/2026-10-21-demandas-fluxo-entrega-homologacao.md).

    Permite responder perguntas antes impossíveis:
      - Quantas entregas esta demanda já teve?
      - Qual foi a última entrega enviada?
      - Há entrega aguardando homologação?
      - Qual entrega foi reprovada e por quê?
      - Quantos dias o cliente levou para homologar?
    """

    demanda = models.ForeignKeyPlus(
        'demandas.Demanda',
        verbose_name='Demanda',
        on_delete=models.CASCADE,
        related_name='entregas',
    )

    # ── Identificação ────────────────────────────────────────────────────────
    titulo = models.CharFieldPlus(
        'Título',
        max_length=200,
        help_text='Identificação curta do pacote entregue. Ex.: "Versão com correção do relatório X".',
    )
    descricao = models.TextField(
        'Descrição',
        blank=True,
        help_text='Resumo do que está sendo entregue neste pacote.',
    )
    notas = models.TextField(
        'Notas da Entrega',
        blank=True,
        help_text='Observações detalhadas para o cliente: o que testar, fluxos principais, dados de exemplo.',
    )

    # ── Status ───────────────────────────────────────────────────────────────
    status = models.CharFieldPlus(
        'Status',
        max_length=20,
        choices=StatusEntrega.choices,
        default=StatusEntrega.ENVIADA,
        db_index=True,
    )

    # ── Ambiente de validação ────────────────────────────────────────────────
    ambiente_homologacao = models.ForeignKeyPlus(
        'demandas.AmbienteHomologacao',
        verbose_name='Ambiente de Homologação',
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
        related_name='entregas',
    )
    url_validacao = models.CharFieldPlus(
        'URL para Validação',
        null=True,
        blank=True,
        help_text='Endereço onde o cliente irá validar esta entrega.',
    )
    senha_homologacao = models.CharFieldPlus(
        'Senha de Acesso',
        null=True,
        blank=True,
        help_text='Senha de acesso ao ambiente de validação, se necessário.',
    )

    # ── Prazos e datas ───────────────────────────────────────────────────────
    prazo_feedback = models.DateField(
        'Prazo para Feedback',
        null=True,
        blank=True,
        help_text='Data limite para o demandante aprovar ou reprovar esta entrega. É também a previsão da etapa "Em homologação".',
    )
    enviada_em = models.DateTimeField(
        'Enviada em',
        auto_now_add=True,
        help_text='Data e hora em que a entrega foi registrada.',
    )
    homologada_em = models.DateTimeField('Homologada em', null=True, blank=True)
    reprovada_em = models.DateTimeField('Reprovada em', null=True, blank=True)
    expirada_em = models.DateTimeField('Expirada em', null=True, blank=True)
    cancelada_em = models.DateTimeField('Cancelada em', null=True, blank=True)

    conclui_demanda = models.BooleanField(
        'Conclui a demanda?',
        default=False,
        help_text='Só para demandas sem especificações: se aprovada, a entrega leva a demanda a "Homologada". '
        'Com especificações, quem decide é a cobertura (todas vinculadas a entregas aprovadas).',
    )

    # ── Resultado ────────────────────────────────────────────────────────────
    motivo_rejeicao = models.TextField(
        'Motivo da Rejeição',
        blank=True,
        help_text='Preenchido pelo cliente ao reprovar a entrega.',
    )

    # ── Integração com GitLab ────────────────────────────────────────────────
    branch = models.CharFieldPlus(
        'Branch',
        null=True,
        blank=True,
        help_text='Branch que originou esta entrega.',
    )
    id_merge_request = models.PositiveIntegerField(
        'ID do Merge Request',
        null=True,
        blank=True,
        help_text='Identificador do MR no GitLab associado a esta entrega.',
    )
    pipeline_id = models.PositiveIntegerField(
        'ID do Pipeline',
        null=True,
        blank=True,
        help_text='Identificador do pipeline de implantação no GitLab.',
    )
    versionamento = models.CharFieldPlus(
        'Tag / Release',
        null=True,
        blank=True,
        help_text='Tag ou release que identifica esta entrega no repositório. Ex.: v2.3.1.',
    )

    # ── Rastreabilidade ──────────────────────────────────────────────────────
    cadastrada_por = models.ForeignKeyPlus(
        'comum.User',
        verbose_name='Cadastrada por',
        on_delete=models.PROTECT,
        related_name='entregas_cadastradas',
    )

    especificacoes = models.ManyToManyField(
        'demandas.Especificacao',
        verbose_name='Especificações entregues',
        blank=True,
        related_name='entregas',
        help_text='Especificações do DoD incluídas neste pacote de entrega.',
    )

    class Meta:
        verbose_name = 'Entrega'
        verbose_name_plural = 'Entregas'
        ordering = ['-enviada_em']

    def __str__(self):
        return f'Entrega #{self.pk} — {self.titulo} [{self.get_status_display()}]'

    def get_absolute_url(self):
        return f'/demandas/entrega/{self.pk}/'

    # ── Propriedades de estado ───────────────────────────────────────────────

    @property
    def esta_pendente(self) -> bool:
        """Entrega aguardando resposta do cliente."""
        return self.status == StatusEntrega.ENVIADA

    @property
    def esta_aprovada(self) -> bool:
        return self.status == StatusEntrega.APROVADA

    @property
    def esta_reprovada(self) -> bool:
        return self.status == StatusEntrega.REPROVADA

    @property
    def esta_encerrada(self) -> bool:
        """Entrega em status terminal (não pode mais ser alterada)."""
        return self.status in StatusEntrega.status_terminais()

    @property
    def prazo_vencido(self) -> bool:
        """Prazo de feedback passou e a entrega ainda está pendente."""
        if self.prazo_feedback and self.esta_pendente:
            return timezone.now().date() > self.prazo_feedback
        return False

    @property
    def dias_aguardando(self) -> int | None:
        """Dias desde o envio até hoje (se pendente) ou até a resposta (se encerrada)."""
        from django.utils import timezone

        if not self.enviada_em:
            return None
        if self.homologada_em:
            delta = self.homologada_em - self.enviada_em
        elif self.reprovada_em:
            delta = self.reprovada_em - self.enviada_em
        elif self.expirada_em:
            delta = self.expirada_em - self.enviada_em
        else:
            delta = timezone.now() - self.enviada_em
        return delta.days

    @property
    def dias_em_atraso(self) -> int | None:
        """Dias de atraso além do prazo de feedback (apenas se vencido e pendente)."""
        if self.prazo_vencido:
            return (timezone.now().date() - self.prazo_feedback).days
        return None

    # ── Validações ───────────────────────────────────────────────────────────

    def clean(self):
        super().clean()

        # Impede criação de nova entrega ENVIADA se já existe uma ativa para a demanda
        if self.status == StatusEntrega.ENVIADA:
            qs = Entrega.objects.filter(demanda=self.demanda, status=StatusEntrega.ENVIADA)
            if self.pk:
                qs = qs.exclude(pk=self.pk)
            if qs.exists():
                raise ValidationError('Já existe uma entrega pendente para esta demanda. Encerre a entrega atual antes de registrar uma nova.')

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    # ── Encerramento ─────────────────────────────────────────────────────────
    # As regras de negócio (quem pode, para onde vai a demanda, comentários e
    # notificações) ficam no EntregaService; aqui só o registro do encerramento.

    _CAMPO_DATA_ENCERRAMENTO = {
        StatusEntrega.APROVADA: 'homologada_em',
        StatusEntrega.REPROVADA: 'reprovada_em',
        StatusEntrega.CANCELADA: 'cancelada_em',
    }

    def encerrar(self, status: StatusEntrega, usuario, observacao: str = '') -> None:
        """Leva a entrega pendente a um status terminal e registra no histórico."""
        if self.esta_encerrada:
            raise ValidationError('Esta entrega já está encerrada.')
        self.status = status
        setattr(self, self._CAMPO_DATA_ENCERRAMENTO[status], timezone.now())
        self.save()
        HistoricoEntrega.objects.create(entrega=self, usuario=usuario, acao=status.label, observacao=observacao)


# ---------------------------------------------------------------------------
# HISTÓRICO DE ENTREGA
# ---------------------------------------------------------------------------


class HistoricoEntrega(ModelPlus):
    """
    Auditoria das transições de status de uma Entrega.

    Mantém separado do Comentario da demanda para não misturar
    semânticas operacionais (sistema) com comunicação (usuários).
    """

    ACAO_ENVIADA = 'Enviada'
    ACAO_APROVADA = 'Aprovada'
    ACAO_REPROVADA = 'Reprovada'
    ACAO_EXPIRADA = 'Expirada'
    ACAO_CANCELADA = 'Cancelada'
    ACAO_EDITADA = 'Editada'

    ACAO_CHOICES = [
        (ACAO_ENVIADA, 'Enviada'),
        (ACAO_APROVADA, 'Aprovada'),
        (ACAO_REPROVADA, 'Reprovada'),
        (ACAO_EXPIRADA, 'Expirada'),
        (ACAO_CANCELADA, 'Cancelada'),
        (ACAO_EDITADA, 'Editada'),
    ]

    entrega = models.ForeignKeyPlus(Entrega, verbose_name='Entrega', on_delete=models.CASCADE, related_name='historico')
    data_hora = models.DateTimeField('Data e Hora', auto_now_add=True)
    usuario = models.ForeignKeyPlus('comum.User', verbose_name='Usuário', on_delete=models.PROTECT, null=True, blank=True)
    acao = models.CharFieldPlus('Ação', max_length=30, choices=ACAO_CHOICES)
    observacao = models.TextField('Observação', blank=True)

    class Meta:
        verbose_name = 'Histórico de Entrega'
        verbose_name_plural = 'Históricos de Entrega'
        ordering = ['data_hora']

    def __str__(self):
        return f'{self.entrega} — {self.acao} em {self.data_hora:%d/%m/%Y %H:%M}'
