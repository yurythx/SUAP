from django.core.exceptions import ValidationError
from django.db import models
from django.urls import reverse_lazy
from django_fsm import FSMIntegerField, transition

from auditoria.utils import dias_uteis_auditoria
from rh.models import Servidor

from ..papeis import eh_auditor_chefe, sou_chefe_auditoria_hoje
from .planejamento import PlanejamentoAnual, PlanejamentoMensal


class StatusAfastamento(models.IntegerChoices):
    PENDENTE = 0, 'Pendente'
    HOMOLOGADO = 1, 'Homologado'
    REJEITADO = 2, 'Rejeitado'


class AfastamentoPlanejadoQuerySet(models.QuerySet):
    def homologados(self):
        return self.filter(status=StatusAfastamento.HOMOLOGADO)

    def rejeitados(self):
        return self.filter(status=StatusAfastamento.REJEITADO)

    def pendentes(self):
        return self.filter(status=StatusAfastamento.PENDENTE)


class AfastamentoPlanejadoManager(models.Manager):
    def get_queryset(self):
        return AfastamentoPlanejadoQuerySet(self.model, using=self._db)

    def pendentes(self):
        return self.get_queryset().pendentes()

    def homologados(self):
        return self.get_queryset().homologados()

    def rejeitados(self):
        return self.get_queryset().rejeitados()


class TipoAfastamento(models.Model):
    SEARCH_FIELDS = ['nome']
    nome = models.CharField(max_length=100, unique=True, verbose_name='Nome do Tipo de Afastamento')
    descricao = models.TextField(blank=True, null=True, verbose_name='Descrição')
    ativo = models.BooleanField(default=True, verbose_name='Ativo')

    def __str__(self):
        return self.nome

    class Meta:
        verbose_name = 'Tipo de Afastamento'
        verbose_name_plural = 'Tipos de Afastamento'


class AfastamentoPlanejado(models.Model):
    planejamento = models.ForeignKey(PlanejamentoMensal, on_delete=models.CASCADE, related_name='afastamentos')
    tipo_afastamento = models.ForeignKey(TipoAfastamento, on_delete=models.CASCADE, related_name='afastamentos', verbose_name='Tipo de Afastamento')
    data_inicio = models.DateField()
    data_fim = models.DateField()
    motivo = models.CharField(max_length=255)
    atualizado_em = models.DateTimeField(auto_now=True)
    justificativa_rejeicao = models.TextField(blank=True, null=True, verbose_name='Justificativa de Rejeição')
    status = FSMIntegerField(default=StatusAfastamento.PENDENTE, choices=StatusAfastamento.choices, protected=True, verbose_name='Status')
    criado_em = models.DateTimeField(auto_now_add=True)

    importado = models.BooleanField(default=False, help_text='Indica se este afastamento foi importado de outros módulos do Suap')

    objects = AfastamentoPlanejadoManager()

    class Meta:
        verbose_name = 'Afastamento Planejado'
        verbose_name_plural = 'Afastamentos Planejados'

    def __str__(self):
        return f'{self.auditor} - {self.tipo_afastamento} ({self.data_inicio:%d/%m} a {self.data_fim:%d/%m})'

    def clean(self):
        if self.data_inicio and self.data_fim and self.data_fim < self.data_inicio:
            raise ValidationError('A data final deve ser posterior ou igual à data inicial.')

    @property
    def esta_homologado(self):
        return self.status == StatusAfastamento.HOMOLOGADO

    @property
    def esta_rejeitado(self):
        return self.status == StatusAfastamento.REJEITADO

    @property
    def esta_pendente(self):
        return self.status == StatusAfastamento.PENDENTE

    @property
    def auditor(self) -> Servidor:
        return self.planejamento.planejamento_anual.auditor

    @property
    def planejamento_anual(self) -> PlanejamentoAnual:
        return self.planejamento.planejamento_anual

    @property
    def ano(self):
        return self.planejamento.planejamento_anual.ano

    @property
    def jornada_diaria(self):
        return self.auditor.jornada_trabalho.get_jornada_trabalho_diaria()

    def pode_editar(self, user):
        if user.eh_servidor:
            servidor_logado: Servidor = user.get_relacionamento()
            return self.auditor == servidor_logado and self.esta_pendente and self.planejamento_anual.esta_em_rascunho
        return False

    def pode_homologar(self, user):
        if eh_auditor_chefe(user):
            return self.planejamento_anual.esta_em_homologacao and self.esta_pendente
        return False

    def pode_remover(self, user):
        return self.pode_editar(user)

    def get_link_para_afastamento(self, user):
        if sou_chefe_auditoria_hoje(user) and self.planejamento_anual.esta_em_homologacao:
            return reverse_lazy('auditoria:avaliar_afastamento', args=[self.pk])
        return reverse_lazy('auditoria:editar_afastamento', args=[self.pk])

    def dias_uteis(self, jornada_diaria: int | None = None) -> int:
        jornada_diaria = jornada_diaria or self.jornada_diaria
        return dias_uteis_auditoria(self.data_inicio, self.data_fim, self.auditor.setor.uo, jornada_diaria)

    def duracao_em_horas(self):
        jornada = self.jornada_diaria
        return self.dias_uteis(jornada) * jornada

    @transition(field=status, source=[StatusAfastamento.PENDENTE, StatusAfastamento.HOMOLOGADO], target=StatusAfastamento.HOMOLOGADO)
    def homologar(self):
        planejamento_anual = self.planejamento.planejamento_anual
        # Se todos os afastamentos estiverem homologados e o anual estiver em homologação, aprova
        if planejamento_anual.pode_ser_aprovado(afastamento_atual=self) and planejamento_anual.esta_em_homologacao:
            # Atualiza os valores planejados (agregado anual)
            planejamento_anual.atualizar_valores()
            planejamento_anual.aprovar()
            planejamento_anual.save()

    @transition(field=status, source=StatusAfastamento.PENDENTE, target=StatusAfastamento.REJEITADO)
    def rejeitar(self, justificativa: str):
        self.justificativa_rejeicao = justificativa
