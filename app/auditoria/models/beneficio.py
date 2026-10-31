from collections import OrderedDict

from django.apps import apps
from django.contrib.contenttypes.fields import GenericForeignKey, GenericRelation
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db.models import Sum
from django.urls import reverse_lazy
from django_fsm import FSMIntegerField, transition

from auditoria.papeis import sou_chefe_auditoria_hoje
from comum.models import Vinculo
from djtools.db import models

from .alcance_estrategico import AlcanceEstrategico
from .documento import Documento, DocumentoManager, DocumentoQueryset
from .servico import TipoServico
from .unidade_afetada import UnidadeAfetada

"""
UNIDADE_AFETADA_CHOICES = [
        ('INST', 'Institucional'),
        ('ORG_COL', 'Órgãos Colegiados'),
        ('ADM_SUP', 'Administração Superior'),
        ('UNI_JUR', 'Unidade Jurisdicionada - Campus'),
    ]

    ALCANCE_ESTRATEGICO_CHOICES = [
        ('MEIO', 'Área Meio - pessoas, infraestrutura ou processos internos'),
        ('FIM', 'Área Fim - resultado, missão ou visão'),
    ]

"""


class TipoBeneficio(models.IntegerChoices):
    FINANCEIRO = 1, 'Financeiro'
    QUALITATIVO = 2, 'Qualitativo'

    @staticmethod
    def get_label(value):
        try:
            return TipoBeneficio.labels[TipoBeneficio.values.index(value)]
        except Exception:
            return None

    @staticmethod
    def as_dict():
        return dict(TipoBeneficio.choices)


class ClasseBeneficio(models.ModelPlus):
    SEARCH_FIELDS = ['tipo', 'descricao']
    tipo = models.IntegerField(choices=TipoBeneficio.choices, verbose_name='Tipo de benefício')
    descricao = models.CharField(verbose_name='Descrição', max_length=255)

    class Meta:
        verbose_name = 'Classe do Benefício'
        verbose_name_plural = 'Classes dos Benefícios'


class BeneficioStatus:
    PLANEJADO = 0
    EM_MONITORAMENTO = 1
    CONCLUIDO = 2
    FINALIZADO = 3
    CANCELADO = 4

    CHOICES = {
        PLANEJADO: 'Planejado',
        EM_MONITORAMENTO: 'Em Monitoramento',
        CONCLUIDO: 'Concluído',
        FINALIZADO: 'Finalizado',
        CANCELADO: 'Cancelado',
    }

    SITUACOES_FINAIS = [CONCLUIDO, FINALIZADO]
    SITUACOES_INATIVAS = [
        CANCELADO,
    ]
    SITUACOES_ATIVAS = [PLANEJADO, EM_MONITORAMENTO]
    SITUACOES_EM_EXECUCAO = [
        EM_MONITORAMENTO,
    ]

    SITUACOES_FLUXO = OrderedDict()
    SITUACOES_FLUXO[PLANEJADO] = [CHOICES[PLANEJADO], 'info']
    SITUACOES_FLUXO[EM_MONITORAMENTO] = [CHOICES[EM_MONITORAMENTO], 'alert']
    SITUACOES_FLUXO[CONCLUIDO] = [CHOICES[CONCLUIDO], 'success']


class Beneficio(models.ModelPlus):
    SEARCH_FIELDS = ['ano', 'tipo', 'classe', 'descricao']

    class OrigemBeneficio(models.IntegerChoices):
        RECOMENDACAO = 1, 'Recomendação'

    ano = models.IntegerField(verbose_name='Ano', help_text='Ano da adoção de providência pelo gestor')
    tipo = models.IntegerField(choices=TipoBeneficio.choices, verbose_name='Tipo de benefício')
    descricao = models.TextField(verbose_name='Descrição')
    classe = models.ForeignKey(ClasseBeneficio, verbose_name='Classe do benefício', on_delete=models.CASCADE)
    nexo_causal = models.TextField('Nexo Causal')

    # Origem do trabalho
    servico_auditoria = models.ForeignKey(TipoServico, verbose_name='Serviço de Auditoria', on_delete=models.CASCADE)
    servico_auditoria_outros = models.CharField(
        'Descrição de Outros', max_length=255, blank=True, null=True, help_text="Preencher somente se o serviço de auditoria for 'Outros'."
    )
    # Origem do benefício
    origem_beneficio = models.IntegerField(verbose_name='Origem do Benefício', choices=OrigemBeneficio.choices)
    #
    limit = (
        models.Q(app_label='auditoria', model='monitoramento')
        # Adicione outros modelos futuramente, como:
        # | models.Q(app_label='outro_app', model='outro_modelo')
    )
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE, limit_choices_to=limit, null=True, blank=True)
    object_id = models.PositiveIntegerField(null=True, blank=True)
    content_object = GenericForeignKey('content_type', 'object_id')
    documentos = GenericRelation('auditoria.BeneficioDocumento')
    status = FSMIntegerField(default=BeneficioStatus.PLANEJADO, choices=BeneficioStatus.CHOICES.items(), protected=True)

    monitor = models.ForeignKeyPlus('comum.Vinculo', verbose_name='Monitor', null=False, blank=False, related_name='%(app_label)s_%(class)s_monitor')

    # Cancelamento
    justificativa = models.TextField(verbose_name='Justificativa', null=True, blank=True)
    encerrado_por = models.ForeignKeyPlus(
        'comum.Vinculo', verbose_name='encerrado por', null=True, related_name='%(app_label)s_%(class)s_encerrado_por'
    )

    modificado_em = models.DateTimeField(auto_now=True, verbose_name='Modificada em')
    modificado_por = models.CurrentUserField(verbose_name='Modificado por', related_name='%(app_label)s_%(class)s_modificado_por')

    class Meta:
        verbose_name = 'Benefício'
        verbose_name_plural = 'Benefícios'
        constraints = [models.UniqueConstraint(fields=['content_type', 'object_id', 'classe'], name='unique_beneficio_por_classe_por_objeto')]

    def __str__(self):
        return f'Benefício #{self.id} - {self.content_object.unidade}'

    def get_absolute_url(self):
        return reverse_lazy('auditoria:visualizar_beneficio', kwargs={'beneficio_id': self.pk})

    @property
    def eh_financeiro(self):
        return self.tipo == TipoBeneficio.FINANCEIRO

    @property
    def eh_qualitativo(self):
        return self.tipo == TipoBeneficio.QUALITATIVO

    @property
    def detalhamento(self):
        if self.eh_financeiro:
            return getattr(self, 'auditoria_detalhamentofinanceiro', None)
        elif self.eh_qualitativo:
            return getattr(self, 'auditoria_detalhamentoqualitativo', None)
        return None

    @property
    def detalhamento_financeiro(self):
        return getattr(self, 'auditoria_detalhamentofinanceiro', None)

    @property
    def detalhamento_qualitativo(self):
        return getattr(self, 'auditoria_detalhamentoqualitativo', None)

    @property
    def natureza(self):
        if self.eh_financeiro:
            return self.detalhamento.natureza
        return 'Não se aplica'

    @property
    def planejado(self):
        return self.status == BeneficioStatus.PLANEJADO

    @property
    def em_monitoramento(self):
        return self.status == BeneficioStatus.EM_MONITORAMENTO

    @property
    def concluido(self):
        return self.status == BeneficioStatus.CONCLUIDO

    @property
    def cancelado(self):
        return self.status == BeneficioStatus.CANCELADO

    @property
    def finalizado(self):
        return self.status == BeneficioStatus.FINALIZADO

    @property
    def ativo(self):
        return self.status in BeneficioStatus.SITUACOES_ATIVAS

    @property
    def status_label(self):
        if self.eh_qualitativo and self.status == BeneficioStatus.CONCLUIDO:
            return 'Publicado'
        return BeneficioStatus.CHOICES[self.status]

    def save(self, *args, **kwargs):
        if self.origem_beneficio == self.OrigemBeneficio.RECOMENDACAO and not self.object_id:
            raise ValidationError('Selecione uma recomendação válida para a origem do benefício.')
        super().save(*args, **kwargs)

    def get_fluxo(self):
        if self.tipo == TipoBeneficio.QUALITATIVO:
            return [
                (BeneficioStatus.PLANEJADO, ['Registrado', 'info']),
                (BeneficioStatus.CONCLUIDO, ['Publicado', 'success']),
            ]
        fluxo = list(BeneficioStatus.SITUACOES_FLUXO.items())
        if self.status == BeneficioStatus.FINALIZADO:
            fluxo[-1] = (self.status, [BeneficioStatus.CHOICES[BeneficioStatus.FINALIZADO], 'alert'])
        return fluxo

    @transition(
        field=status,
        source=[BeneficioStatus.PLANEJADO, BeneficioStatus.CONCLUIDO, BeneficioStatus.EM_MONITORAMENTO],
        target=BeneficioStatus.EM_MONITORAMENTO,
    )
    def monitorar(self):
        if self.eh_qualitativo:
            raise ValidationError('Benefícios qualitativos não podem ser monitorados.')

    @transition(field=status, source=[BeneficioStatus.PLANEJADO, BeneficioStatus.EM_MONITORAMENTO], target=BeneficioStatus.CONCLUIDO)
    def concluir(self, user):
        self.encerrado_por = user.get_vinculo()

    @transition(field=status, source=BeneficioStatus.EM_MONITORAMENTO, target=BeneficioStatus.FINALIZADO)
    def finalizar(self, user, justificativa):
        if self.eh_qualitativo:
            raise ValidationError('Use a função `publicar` para concluir um benefício qualitativo.')
        self.encerrado_por = user.get_vinculo()
        self.justificativa = justificativa

    @transition(field=status, source=BeneficioStatus.EM_MONITORAMENTO, target=BeneficioStatus.CANCELADO)
    def cancelar(self, user, justificativa):
        self.encerrado_por = user.get_vinculo()
        self.justificativa = justificativa

    @transition(field=status, source=BeneficioStatus.CANCELADO, target=BeneficioStatus.EM_MONITORAMENTO)
    def reinicar_monitoramento(self):
        if self.eh_qualitativo:
            raise ValidationError('Use a função `publicar` para concluir um benefício qualitativo.')
        self.encerrado_por = None
        self.justificativa = None

    def pode_editar(self, user):
        return self.em_monitoramento and (sou_chefe_auditoria_hoje(user) or user.get_vinculo() == self.monitor)

    def pode_adicionar_documento(self, user):
        return self.pode_editar(user)

    def pode_remover_documento(self, user):
        return self.pode_editar(user)

    def pode_monitorar(self, user):
        return self.planejado and self.pode_editar(user)

    def pode_finalizar(self, user):
        return self.em_monitoramento and self.pode_editar(user)

    def pode_cancelar(self, user):
        return self.em_monitoramento and sou_chefe_auditoria_hoje(user)

    def pode_publicar(self, user):
        return self.eh_qualitativo and self.planejado and self.pode_editar(user)

    def pode_concluir(self, user):
        if not self.concluido and (sou_chefe_auditoria_hoje(user) or user.get_vinculo() == self.monitor):
            detalhamento = self.detalhamento_financeiro if self.eh_financeiro else self.detalhamento_qualitativo
            return detalhamento.pode_concluir()
        return False

    def pode_inicar_monitoramento(self, user):
        return self.planejado and (sou_chefe_auditoria_hoje(user) or user.get_vinculo() == self.monitor)

    def pode_reinicar_monitoramento(self, user):
        return self.cancelado and sou_chefe_auditoria_hoje(user)

    def adicionar_documento(self, documento, user):
        content_type = ContentType.objects.get_for_model(documento)
        return BeneficioDocumento.objects.get_or_create(
            beneficio=self, object_id=documento.id, content_type=content_type, defaults={'incluido_por': user.get_vinculo(), 'object': documento}
        )

    def remover_documento(self, documento, user):
        content_type = ContentType.objects.get_for_model(documento)
        relatorio_documento = BeneficioDocumento.objects.filter(content_type=content_type, object_id=documento.id).first()
        if relatorio_documento:
            relatorio_documento.remover_documento(user)
            relatorio_documento.save()

    def get_historico(self):
        return self.historicobeneficio_set.all()

    def get_reference_object_url(self):
        if self.origem_beneficio == self.OrigemBeneficio.RECOMENDACAO:
            return self.content_object.get_reference_object_url()
        return self.content_object.get_absolute_url()

    def clean(self):
        if self.classe_id:
            qs = Beneficio.objects.filter(content_type=self.content_type, object_id=self.object_id, classe=self.classe).exclude(pk=self.pk)
            if qs.exists():
                raise ValidationError('Já existe um benefício com essa classe para esse objeto.')


class DetalhamentoBase(models.Model):
    beneficio = models.OneToOneField(
        Beneficio,
        on_delete=models.CASCADE,
        related_name='%(app_label)s_%(class)s',
    )

    criado_em = models.DateTimeField(auto_now_add=True, verbose_name='Criado em')
    atualizado_em = models.DateTimeField(auto_now=True, verbose_name='Atualizado em')
    criado_por = models.CurrentUserField(on_delete=models.SET_NULL, related_name='%(class)s_criados', verbose_name='Criado por')
    atualizado_por = models.CurrentUserField(on_delete=models.SET_NULL, related_name='%(class)s_atualizados', verbose_name='Atualizado por')

    class Meta:
        abstract = True


class NaturezaFinanceira(models.IntegerChoices):
    RECUPERADO = 1, 'Gasto Recuperado'
    EVITADO = 2, 'Gasto Evitado'


# Modelo de Detalhes de Benefício Financeiro
class DetalhamentoFinanceiro(DetalhamentoBase):
    valor_beneficio = models.DecimalField('Valor Benefício', max_digits=15, decimal_places=2, help_text='Valor total esperado do benefício')
    responsavel_calculo = models.ForeignKey(Vinculo, on_delete=models.SET_NULL, null=True, related_name='calculos_detalhamentos_financeiros')
    natureza = models.IntegerField(
        choices=NaturezaFinanceira.choices,
        default=NaturezaFinanceira.RECUPERADO,
        verbose_name='Natureza do benefício',
        help_text='Classificação do valor como gasto evitado ou recuperado',
    )
    metodologia_calculo = models.TextField('Metodologia de Cálculo', blank=True, null=True)

    def __str__(self):
        return f'#{self.beneficio} - Financeiro'

    def total_efetivo(self):
        total = self.parcelas.aggregate(total_efetivo=Sum('valor_efetivo'))['total_efetivo']
        return total or 0

    def verificar_monitoramento(self):
        """Verifica e altera automaticamente o status de monitoramento."""
        if self.beneficio.planejado:
            self.beneficio.monitorar()
            self.beneficio.save()

    def pode_concluir(self):
        return self.beneficio.ativo and self.total_efetivo() >= self.valor_beneficio

    def pode_editar(self, user):
        return self.beneficio.ativo and self.beneficio.pode_editar(user)

    def clean(self):
        if self.natureza not in (NaturezaFinanceira.RECUPERADO, NaturezaFinanceira.EVITADO):
            raise ValidationError('A natureza do benefício financeiro deve ser especificada.')


class ParcelaFinanceira(models.Model):
    detalhamento = models.ForeignKey(
        DetalhamentoFinanceiro,
        on_delete=models.CASCADE,
        related_name='parcelas',
        verbose_name='Detalhamento Financeiro',
    )
    # Dados da parcela
    data_prevista = models.DateField('Data Prevista')
    valor_esperado = models.DecimalField('Valor Esperado', max_digits=15, decimal_places=2)
    cadastrado_por = models.CurrentUserField(verbose_name='Cadastrado por', related_name='%(app_label)s_%(class)s_cadastrado_por')
    # Dados do pagamento
    data_pagamento = models.DateField('Data Pagamento', null=True, blank=True)
    valor_efetivo = models.DecimalField('Valor Efetivo', max_digits=15, decimal_places=2, default=0)
    # Dados do pagamento
    criado_em = models.DateTimeFieldPlus(verbose_name='Data de Inclusão', auto_now_add=True, editable=False)
    modificado_em = models.DateTimeFieldPlus(auto_now=True, verbose_name='Modificada em')
    modificado_por = models.CurrentUserField(verbose_name='Modificado por', related_name='%(app_label)s_%(class)s_modificado_por')
    observacao = models.TextField('Observações', blank=True, null=True)

    class Meta:
        verbose_name = 'Parcela Financeira'
        verbose_name_plural = 'Parcelas Financeiras'
        ordering = ['data_prevista']

    def __str__(self):
        return f'Parcela de {self.valor_esperado} (Esperado) - {self.data_prevista}'

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self.detalhamento.verificar_monitoramento()


class DetalhamentoQualitativo(DetalhamentoBase):
    unidade_afetada = models.ForeignKey(UnidadeAfetada, on_delete=models.CASCADE, verbose_name='Unidade Afetada')
    alcance_estrategico = models.ForeignKey(AlcanceEstrategico, on_delete=models.CASCADE, verbose_name='Alcance Estratégico')
    criado_em = models.DateTimeFieldPlus(verbose_name='Data de Inclusão', auto_now_add=True, editable=False)
    modificado_em = models.DateTimeFieldPlus(auto_now=True, verbose_name='Modificada em')
    modificado_por = models.CurrentUserField(verbose_name='Modificado por', related_name='%(app_label)s_%(class)s_modificado_por')
    observacao = models.TextField('Observações', blank=True, null=True)

    def __str__(self):
        return f'Qualitativo - Benefício #{self.beneficio}'

    def pode_concluir(self):
        return True


class BeneficioDocumentoQueryset(DocumentoQueryset):
    def get_model(self):
        return apps.get_model('auditoria', 'BeneficioDocumento')


class BeneficioDocumentoManager(DocumentoManager):
    def get_queryset(self):
        return BeneficioDocumentoQueryset(self.model, using=self._db)


class BeneficioDocumento(Documento):
    beneficio = models.ForeignKey(Beneficio, on_delete=models.CASCADE, related_name='documentos')
    objects = BeneficioDocumentoManager()

    def pode_remover_documento(self, user):
        return not self.removido and self.beneficio.pode_remover_documento(user)
