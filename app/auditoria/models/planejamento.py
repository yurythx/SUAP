import calendar
from datetime import date
from typing import TYPE_CHECKING

from django.core.validators import MinValueValidator
from django.urls import reverse_lazy
from django_fsm import FSMIntegerField, transition

from djtools.choices import Meses
from djtools.db import models
from rh.models import Servidor

from ..papeis import eh_auditor_chefe, sou_chefe_auditoria_hoje
from ..utils import horas_afastadas_no_periodo
from .paint import Paint

if TYPE_CHECKING:
    from .afastamento import AfastamentoPlanejado


class StatusPlanejamento(models.IntegerChoices):
    RASCUNHO = 0, 'Rascunho'
    ENVIADO = 1, 'Enviado'
    EM_HOMOLOGACAO = 2, 'Em Homologação'
    APROVADO = 3, 'Aprovado'
    REPROVADO = 4, 'Reprovado'
    CANCELADO = 5, 'Cancelado'


class PlanejamentoAnualQuerySet(models.QuerySet):
    def aprovados(self):
        return self.filter(status=StatusPlanejamento.APROVADO)

    def reprovados(self):
        return self.filter(status=StatusPlanejamento.REPROVADO)

    def cancelados(self):
        return self.filter(status=StatusPlanejamento.CANCELADO)

    def em_homologacao(self):
        return self.filter(status=StatusPlanejamento.EM_HOMOLOGACAO)

    def enviados(self):
        return self.filter(status=StatusPlanejamento.ENVIADO)

    def rascunho(self):
        return self.filter(status=StatusPlanejamento.RASCUNHO)


class PlanejamentoAnualManager(models.Manager):
    def get_queryset(self):
        return PlanejamentoAnualQuerySet(self.model, using=self._db)

    def aprovados(self):
        return self.get_queryset().aprovados()

    def reprovados(self):
        return self.get_queryset().reprovados()

    def cancelados(self):
        return self.get_queryset().cancelados()

    def em_homologacao(self):
        return self.get_queryset().em_homologacao()

    def enviados(self):
        return self.get_queryset().enviados()

    def rascunho(self):
        return self.get_queryset().rascunho()


class PlanejamentoAnual(models.Model):
    # - "Previstas": baseline do período (ex.: dias úteis * CH diária). É o teto bruto.
    # - "Líquidas previstas": baseline já descontando itens fixos/estruturais do período,
    #   antes de considerar afastamentos (ex.: recessos, feriados, férias já conhecidas etc.).
    # - "Afastadas planejadas": total de horas de afastamento consolidadas no plano anual
    #   (normalmente após aprovação/homologação).
    # - "Projetadas": soma de afastamentos vindos dos planos mensais (rascunhos/estimativas).
    # - "Ativas/Vigentes": o que efetivamente vale agora. Se o plano anual está APROVADO,
    #   valem as "planejadas"; caso contrário, usa-se a projeção dos meses.
    auditor = models.ForeignKey(Servidor, on_delete=models.CASCADE, related_name='planejamentos_anuais')
    paint = models.ForeignKey(Paint, on_delete=models.CASCADE, related_name='planejamentos_anuais')
    # Horas brutas previstas para o período (ex.: dias úteis * carga diária).
    carga_horaria_prevista = models.PositiveIntegerField(
        default=0,
        validators=[MinValueValidator(0)],
        verbose_name='Horas Previstas (Brutas)',
        help_text='Baseline bruta do período, antes de qualquer desconto.',
    )
    # Carga Horaria líquida homologadas para o paint.
    carga_horaria_homologada = models.PositiveIntegerField(
        default=0,
        validators=[MinValueValidator(0)],
        verbose_name='Horas Líquidas Homologadas',
        help_text='Horas líquidas homologadas para o próximo ano.',
    )

    # Total de horas de afastamento já planejado/consolidado no plano anual.
    # Em geral só passa a valer quando o status está APROVADO.
    carga_horaria_afastada_homologada = models.PositiveIntegerField(
        default=0,
        validators=[MinValueValidator(0)],
        verbose_name='Carga Horária Afastada Homologada',
        help_text='Afastamentos homologados no plano anual; usados quando o status for APROVADO.',
    )

    status = FSMIntegerField(default=StatusPlanejamento.RASCUNHO, choices=StatusPlanejamento.choices, protected=True, verbose_name='Status')
    criado_em = models.DateTimeField(auto_now_add=True)
    criado_por = models.CurrentUserField(verbose_name='Cadastrado Por', related_name='%(app_label)s_%(class)s_cadastrado_por')
    atualizado_por = models.ForeignKeyPlus(
        'comum.Vinculo',
        null=True,
        blank=True,
        verbose_name='Atualizado Por',
        on_delete=models.CASCADE,
        related_name='%(app_label)s_%(class)s_atualizado_por',
    )
    atualizado_em = models.DateTimeField(auto_now=True)

    objects = PlanejamentoAnualManager()

    class Meta:
        unique_together = ('auditor', 'paint')

    def __str__(self):
        return f'{self.auditor} - {self.paint.ano}'

    def get_absolute_url(self):
        return reverse_lazy('auditoria:planejamento_anual_auditor', kwargs={'planejamento_id': self.pk})

    @property
    def esta_em_rascunho(self):
        return self.status == StatusPlanejamento.RASCUNHO

    @property
    def enviado(self):
        return self.status == StatusPlanejamento.ENVIADO

    @property
    def esta_em_homologacao(self):
        return self.status == StatusPlanejamento.EM_HOMOLOGACAO

    @property
    def aprovado(self):
        return self.status == StatusPlanejamento.APROVADO

    @property
    def reprovado(self):
        return self.status == StatusPlanejamento.REPROVADO

    @property
    def ano(self) -> int:
        return self.paint.ano.ano

    @property
    def carga_horaria_afastada(self) -> int:
        """
        Soma dos afastamentos PROJETADOS nos planejamentos mensais.
        Útil quando o plano ainda não foi aprovado (status != APROVADO).
        """
        ch_total_afastadas_anual = sum(planejamento.carga_horaria_afastada for planejamento in self.planejamentos_mensais.all())
        return max(ch_total_afastadas_anual, 0)

    @property
    def carga_horaria_liquida_projetada(self) -> int:
        return max(self.carga_horaria_prevista - self.carga_horaria_afastada, 0)

    @property
    def carga_horaria_liquida(self) -> int:
        return self.carga_horaria_homologada if self.status == StatusPlanejamento.APROVADO else self.carga_horaria_liquida_projetada

    @property
    def ch_afastada_total(self):
        return self.horas_previstas - self.horas_liquidas_vigentes

    @property
    def pode_ser_reenviado(self):
        return self.reprovado and self.paint.periodo_planejamento_aberto()

    def pode_editar(self, user):
        if self.auditor == user.get_relacionamento():
            return self.status in [StatusPlanejamento.RASCUNHO, StatusPlanejamento.REPROVADO] and self.paint.esta_no_periodo_de_cadastro()
        elif eh_auditor_chefe(user):
            return self.status in [StatusPlanejamento.ENVIADO, StatusPlanejamento.EM_HOMOLOGACAO]
        return False

    def pode_retornar_para_rascunho(self, user) -> bool:
        if (self.reprovado or self.enviado) and self.auditor == user.get_relacionamento():
            return self.paint.esta_no_periodo_de_cadastro()
        return False

    def pode_enviar_para_homologacao(self, user) -> bool:
        if user.is_superuser:
            return self.esta_em_rascunho
        return self.esta_em_rascunho and self.auditor == user.get_relacionamento()

    def pode_analisar(self, user) -> bool:
        if self.enviado:
            return sou_chefe_auditoria_hoje(user) or user.is_superuser
        return False

    def pode_homologar(self, user) -> bool:
        if self.esta_em_homologacao:
            return sou_chefe_auditoria_hoje(user) or user.is_superuser
        return False

    def pode_concluir(self, user) -> bool:
        if self.esta_em_homologacao and sou_chefe_auditoria_hoje(user):
            return not self.planejamentos_mensais.pendentes().exists()
        return False

    def pode_ser_aprovado(self, afastamento_atual: AfastamentoPlanejado | None = None) -> bool:
        # Filtra afastamentos, não meses: excluir o mês do afastamento atual escondia
        # os demais pendentes desse mesmo mês e aprovava o planejamento antes da hora.
        from .afastamento import AfastamentoPlanejado, StatusAfastamento

        em_aberto = AfastamentoPlanejado.objects.filter(
            planejamento__planejamento_anual=self, status__in=[StatusAfastamento.PENDENTE, StatusAfastamento.REJEITADO]
        )
        if afastamento_atual:
            em_aberto = em_aberto.exclude(pk=afastamento_atual.pk)
        return not em_aberto.exists()

    @transition(field=status, source=StatusPlanejamento.RASCUNHO, target=StatusPlanejamento.ENVIADO)
    def enviar_para_aprovacao(self):
        pass

    @transition(field=status, source=StatusPlanejamento.ENVIADO, target=StatusPlanejamento.EM_HOMOLOGACAO)
    def analisar(self):
        pass

    @transition(field=status, source=StatusPlanejamento.EM_HOMOLOGACAO, target=StatusPlanejamento.APROVADO)
    def aprovar(self):
        pass

    @transition(field=status, source=StatusPlanejamento.EM_HOMOLOGACAO, target=StatusPlanejamento.REPROVADO)
    def reprovar(self):
        pass

    @transition(
        field=status,
        source=[StatusPlanejamento.RASCUNHO, StatusPlanejamento.ENVIADO, StatusPlanejamento.EM_HOMOLOGACAO],
        target=StatusPlanejamento.CANCELADO,
    )
    def cancelar(self):
        pass

    @transition(field=status, source=StatusPlanejamento.REPROVADO, target=StatusPlanejamento.RASCUNHO)
    def retornar_para_rascunho(self):
        pass

    def atualizar_valores(self):
        mensais = list(self.planejamentos_mensais.all())
        self.carga_horaria_homologada = sum(planejamento.carga_horaria_homologada for planejamento in mensais)
        self.carga_horaria_afastada_homologada = sum((mensal.carga_horaria_afastada_homologada) for mensal in mensais)

    def clean(self):
        # Validações coerentes com os novos nomes
        if self.carga_horaria_prevista < 0:
            raise models.ValidationError({'carga_horaria_prevista': 'Valor inválido.'})
        if self.carga_horaria_homologada > self.carga_horaria_prevista:
            raise models.ValidationError({'carga_horaria_homologada': 'Não pode exceder a carga horária prevista.'})
        if self.carga_horaria_afastada_homologada > self.carga_horaria_prevista:
            raise models.ValidationError({'carga_horaria_afastada_homologada': 'Não pode exceder a carga horária prevista.'})

    def importar_afastamentos_suap(self) -> dict:
        """
        Delega para o serviço de consolidação.
        Mantido no modelo para compatibilidade com código existente.
        """
        from ..services.afastamento_service import AfastamentoService

        service = AfastamentoService(self)
        return service.importar_afastamentos()

    def remover_afastamentos_suap(self) -> None:
        """Delega para o serviço de consolidação."""
        from ..services.afastamento_service import AfastamentoService

        service = AfastamentoService(self)
        service.remover_afastamentos_importados()

    def pode_consolidar(self) -> tuple[bool, str]:
        """Verifica se pode ser consolidado."""
        from ..services.afastamento_service import AfastamentoService

        service = AfastamentoService(self)
        return service.pode_consolidar()


class PlanejamentoMensalQuerySet(models.QuerySet):
    def pendentes(self):
        from .afastamento import StatusAfastamento

        return self.filter(afastamentos__status=StatusAfastamento.PENDENTE).distinct()

    def homologados(self):
        from .afastamento import StatusAfastamento

        return self.filter(afastamentos__status=StatusAfastamento.HOMOLOGADO).distinct()

    def rejeitados(self):
        from .afastamento import StatusAfastamento

        return self.filter(afastamentos__status=StatusAfastamento.REJEITADO).distinct()


class PlanejamentoMensalManager(models.Manager):
    def get_queryset(self):
        return PlanejamentoMensalQuerySet(self.model, using=self._db)

    def pendentes(self):
        return self.get_queryset().pendentes()

    def homologados(self):
        return self.get_queryset().homologados()

    def rejeitados(self):
        return self.get_queryset().rejeitados()


class PlanejamentoMensal(models.Model):
    planejamento_anual = models.ForeignKey(PlanejamentoAnual, on_delete=models.CASCADE, related_name='planejamentos_mensais')
    mes = models.PositiveSmallIntegerField(choices=Meses.get_choices(), verbose_name='Mês')
    carga_horaria_prevista = models.PositiveIntegerField(default=0, verbose_name='Carga Horária Prevista')
    carga_horaria_homologada = models.PositiveIntegerField(default=0, verbose_name='Carga Horária Homologada')
    criado_em = models.DateTimeField(auto_now_add=True)
    criado_por = models.CurrentUserField(verbose_name='Cadastrado Por', related_name='%(app_label)s_%(class)s_cadastrado_por')
    atualizado_em = models.DateTimeField(auto_now=True)
    atualizado_por = models.ForeignKeyPlus(
        'comum.Vinculo',
        null=True,
        blank=True,
        verbose_name='Atualizado Por',
        on_delete=models.CASCADE,
        related_name='%(app_label)s_%(class)s_atualizado_por',
    )

    objects = PlanejamentoMensalManager()

    class Meta:
        unique_together = ('planejamento_anual', 'mes')
        ordering = ['mes']

    def __str__(self):
        auditor = self.planejamento_anual.auditor
        ano = self.planejamento_anual.paint.ano
        return f'{auditor} - {self.get_mes_display()}/{ano}'

    @property
    def ano(self) -> int:
        return self.planejamento_anual.ano

    @property
    def auditor(self) -> Servidor:
        return self.planejamento_anual.auditor

    @property
    def jornada_trabalho(self):
        return self.auditor.jornada_trabalho.get_jornada_trabalho_diaria()

    @property
    def carga_horaria_afastada(self):
        return self._horas_afastadas(self.afastamentos.homologados() | self.afastamentos.pendentes())

    @property
    def carga_horaria_afastada_homologada(self):
        return self._horas_afastadas(self.afastamentos.homologados())

    def _horas_afastadas(self, afastamentos) -> float:
        """Horas afastadas do mês, contando cada dia uma única vez.

        Os afastamentos do mês podem cobrir o mesmo dia — tipicamente o que o
        auditor declarou e o que a sincronização importou do ``ferias``/SIAPE.
        Somar a duração de cada registro descontaria o dia repetido, então o
        cálculo é feito sobre a união dos dias cobertos.
        """
        primeiro_dia = date(self.ano, self.mes, 1)
        ultimo_dia = date(self.ano, self.mes, calendar.monthrange(self.ano, self.mes)[1])
        intervalos = [(afastamento.data_inicio, afastamento.data_fim) for afastamento in afastamentos]
        return horas_afastadas_no_periodo(intervalos, primeiro_dia, ultimo_dia, self.auditor.setor.uo, self.jornada_trabalho)

    @property
    def saldo(self):
        return max(self.carga_horaria_prevista - self.carga_horaria_afastada, 0)

    @property
    def carga_horaria_liquida(self):
        return self.carga_horaria_homologada if self.planejamento_anual.aprovado else self.saldo

    def pode_adicionar_afastamento(self, user) -> bool:
        if user.is_superuser or (user.eh_servidor and self.auditor == user.get_relacionamento()):
            return self.planejamento_anual.esta_em_rascunho
        return False
