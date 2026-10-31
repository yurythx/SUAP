from collections import OrderedDict

from django.apps import apps
from django.contrib.contenttypes.models import ContentType
from django.db.models import Q
from django.template.defaultfilters import slugify
from django.urls import reverse_lazy
from django_fsm import FSMIntegerField, transition
from djtools.db import models, transaction
from djtools.utils import get_datetime_now
from comum.models import User, Vinculo

from .providencia import SolicitacaoProvidenciaStatus
from .documento import Documento, DocumentoManager, DocumentoQueryset
from ..papeis import eh_auditor, tenho_poder_de_chefe
from ..utils import setores_que_respondo_como_chefe


class TipoManifestacao(models.TextChoices):
    SOLICITACAO_PRORROGACAO = 'SP', 'Solicitação de Prorrogação'
    SOLICITACAO_REVISAO = 'SR', 'Solicitação de Revisão'
    ENCAMINHAMENTO_PROVIDENCIAS = 'EP', 'Encaminhamento de Providências'
    SOLICITACAO_CANCELAMENTO = 'SC', 'Solicitação de Cancelamento de Recomendação'
    REJEICAO_EXPRESSA = 'RE', 'Rejeição expressa'
    AUSENCIA_MANIFESTACAO = 'AM', 'Ausência de Manifestação'

    @staticmethod
    def get_label(value):
        # Procura pelo valor fornecido nos valores definidos e retorna o label correspondente
        try:
            return TipoManifestacao.labels[TipoManifestacao.values.index(value)]
        except ValueError:
            return None  # Retorna None se o valor não for encontrado


class ManifestacaoStatus:
    REGISTRADA = 0
    ENVIADA = 1
    RECEBIDA = 2
    ANALISADA = 3

    CHOICES = {
        REGISTRADA: 'Registrada',
        ENVIADA: 'Enviada',
        RECEBIDA: 'Em análise',
        ANALISADA: 'Analisada',
    }

    @staticmethod
    def get_status_description(status_code):
        # Return the description for the status code with a default of None if not found
        return ManifestacaoStatus.CHOICES.get(status_code, None)

    SITUACOES_FLUXO = OrderedDict()
    SITUACOES_FLUXO[REGISTRADA] = ['Registrada', 'alert']
    SITUACOES_FLUXO[ENVIADA] = ['Enviada', 'info']
    SITUACOES_FLUXO[RECEBIDA] = ['Em análise', 'alert']
    SITUACOES_FLUXO[ANALISADA] = ['Analisada', 'success']


class ManifestacaoQueryset(models.QuerySet):
    def manifestacoes_para_monitoramento(self, monitoramento):
        return self.filter(monitoramento_id=monitoramento.id)

    def manifestacoes_que_posso_visualizar(self, user):
        if eh_auditor(user):
            return self.exclude(status=ManifestacaoStatus.REGISTRADA)
        else:
            setores = setores_que_respondo_como_chefe(user)
            return self.filter(solicitacao_providencia__setor__in=setores)

    def registradas(self):
        return self.filter(status=ManifestacaoStatus.REGISTRADA)

    def nao_registradas(self):
        return self.exclude(status=ManifestacaoStatus.REGISTRADA)

    def enviadas(self):
        return self.filter(status=ManifestacaoStatus.ENVIADA)

    def nao_analisadas(self):
        return self.exclude(status=ManifestacaoStatus.ANALISADA)

    def aguardando_analise(self):
        return self.filter(status=ManifestacaoStatus.RECEBIDA)

    def analisadas(self):
        return self.filter(Q(status=ManifestacaoStatus.ANALISADA))

    def manifestacoes_do_auditado(self):
        return self.exclude(tipo=TipoManifestacao.AUSENCIA_MANIFESTACAO)

    def manifestacoes_auditoria(self):
        return self.filter(tipo=TipoManifestacao.AUSENCIA_MANIFESTACAO)

    def manifestacoes_a_enviar(self):
        """
        Seleciona manifestações que podem ser enviadas,
        garantindo que a solicitação de providência vinculada não esteja expirada.
        """
        return self.registradas().filter(solicitacao_providencia__status=SolicitacaoProvidenciaStatus.STATUS_CIENTE)


class ManifestacaoManager(models.Manager):
    def get_queryset(self):
        return ManifestacaoQueryset(self.model, using=self._db)

    def manifestacoes_para_monitoramento(self, monitoramento):
        return self.get_queryset().manifestacoes_para_monitoramento(monitoramento)

    def manifestacoes_que_posso_visualizar(self, user):
        return self.get_queryset().manifestacoes_que_posso_visualizar(user)

    def nao_registradas(self):
        return self.get_queryset().nao_registradas()

    def registradas(self):
        return self.get_queryset().registradas()

    def enviadas(self):
        return self.get_queryset().enviadas()

    def nao_analisadas(self):
        return self.get_queryset().nao_analisadas()

    def analisadas(self):
        return self.get_queryset().analisadas()

    def aguardando_analise(self):
        return self.get_queryset().aguardando_analise()

    def manifestacoes_do_auditado(self):
        return self.get_queryset().manifestacoes_do_auditado()

    def manifestacoes_auditoria(self):
        return self.get_queryset().manifestacoes_auditoria()

    def manifestacoes_a_enviar(self):
        return self.get_queryset().manifestacoes_a_enviar()


class Manifestacao(models.ModelPlus):
    monitoramento = models.ForeignKey('auditoria.Monitoramento', on_delete=models.CASCADE, related_name='manifestacoes')
    solicitacao_providencia = models.ForeignKey('auditoria.SolicitacaoProvidencia', on_delete=models.CASCADE, related_name='manifestacoes')
    anterior = models.OneToOneField('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='próxima_manifestação')
    tipo = models.CharField(choices=TipoManifestacao.choices, max_length=2, verbose_name='Tipo de manifestação')
    #
    texto = models.TextField(verbose_name='Manifestação do auditado', null=False, blank=False)
    #
    # Dados da manifestação
    criado_em = models.DateTimeFieldPlus('Data de inclusão', auto_now_add=True, editable=False)
    incluido_por = models.CurrentUserField(
        verbose_name='Usuário de Inclusão', related_name='%(app_label)s_%(class)s_incluido_por', null=False, editable=False
    )
    enviada_por = models.ForeignKey(
        Vinculo,
        verbose_name='Enviado por',
        related_name='%(app_label)s_%(class)s_enviado_por',
        null=True,
        blank=True,
        on_delete=models.CASCADE,
    )
    enviada_em = models.DateTimeField(null=True, blank=True, verbose_name='Enviado em')
    recebida_por = models.ForeignKey(
        Vinculo,
        verbose_name='Enviado por',
        related_name='%(app_label)s_%(class)s_recebida_por',
        null=True,
        blank=True,
        on_delete=models.CASCADE,
    )
    recebida_em = models.DateTimeField(null=True, blank=True, verbose_name='Recebida em')
    ultima_modificacao = models.DateTimeField(auto_now=True, verbose_name='Última modificação')
    status = FSMIntegerField(default=ManifestacaoStatus.REGISTRADA, choices=ManifestacaoStatus.CHOICES.items(), protected=True)

    objects = ManifestacaoManager()

    class Meta:
        verbose_name = 'Manifestação'
        verbose_name_plural = 'Manifestações'
        ordering = ('id',)

    def __str__(self):
        return f'Manifestação #{self.id}'

    @property
    def content_object(self):
        return self.monitoramento

    @property
    def ultima_movimentacao_em(self):
        return self.recebida_em or (self.enviada_em or self.criado_em)

    def __getattr__(self, name):
        """
        Delegates attribute access to content_object if not found in Manifestacao
        """
        if hasattr(self.content_object, name):
            return getattr(self.content_object, name)
        raise AttributeError(f"'{self.__class__.__name__}' object and its content object have no attribute '{name}'")

    def get_absolute_url(self):
        return reverse_lazy('auditoria:visualizar_manifestacao', kwargs={'manifestacao_id': self.pk})

    @property
    def eh_da_auditoria(self):
        return self.tipo == TipoManifestacao.AUSENCIA_MANIFESTACAO

    @property
    def eh_do_auditado(self):
        return self.tipo != TipoManifestacao.AUSENCIA_MANIFESTACAO

    @property
    def registrada(self):
        return self.status == ManifestacaoStatus.REGISTRADA

    @property
    def enviada(self):
        return self.status == ManifestacaoStatus.ENVIADA

    @property
    def recebida(self):
        return self.status == ManifestacaoStatus.RECEBIDA

    @property
    def analisada(self):
        return self.status == ManifestacaoStatus.ANALISADA

    @property
    def prorrogacao_prazo(self):
        return self.tipo == TipoManifestacao.SOLICITACAO_PRORROGACAO

    @property
    def prazo_solicitado(self):
        return self.prorrogacao.prazo_solicitado if self.prorrogacao_prazo else None

    @property
    def prazo_atual(self):
        return self.solicitacao_providencia.prazo_atual

    @property
    def revisor(self) -> Vinculo:
        return self.content_object.revisor

    @property
    def auditor(self) -> Vinculo:
        return self.content_object.monitor

    @property
    def unidade(self):
        return self.content_object.unidade

    @property
    def data_limite(self):
        return self.content_object.data_limite

    def eh_monitoramento(self):
        return self.content_type.model == 'monitoramento'

    def get_content_object_url(self, user):
        if eh_auditor(user):
            url = self.content_object.recomendacao.get_absolute_url()
            return f'{url}?tab={slugify(self.unidade)}'
        else:
            return self.content_object.get_absolute_url()

    def pode_visualizar(self, user):
        if self.monitoramento.pode_visualizar_monitoramento(user):
            return True
        return eh_auditor(user) and not self.registrada

    def pode_editar_como_auditado(self, user, apenas_como_chefe=True):
        if apenas_como_chefe:
            return self.solicitacao_providencia.pode_editar_como_auditado(user)
        return self.monitoramento.pode_editar_manifestacoes(user)

    def pode_editar_como_auditor(self, user):
        return self.solicitacao_providencia.pode_editar_como_auditor(user)

    def pode_adicionar_documento(self, user):
        permite_por_status = self.registrada or (self.prorrogacao_prazo and self.enviada)
        return permite_por_status and self.pode_editar_como_auditado(user, apenas_como_chefe=False)

    def pode_remover_documento(self, user):
        permite_por_status = self.registrada or (self.prorrogacao_prazo and self.enviada)
        return self.pode_editar_como_auditado(user, apenas_como_chefe=False) and permite_por_status

    def pode_enviar(self, user):
        if self.solicitacao_providencia.cancelada or self.solicitacao_providencia.expirada:
            return False
        return self.registrada and self.pode_editar_como_auditado(user, apenas_como_chefe=True)

    def envio_restrito_a_chefia(self, user: User) -> bool:
        """Indica se o usuário edita a manifestação registrada, mas não pode enviá-la por não ser chefe.

        O servidor indicado pela chefia registra a manifestação, mas só o chefe do setor a envia
        (``pode_enviar``). Sem o botão, a tela precisa dizer por que (decisão em #13431).
        """
        if not self.registrada or tenho_poder_de_chefe(user, self.solicitacao_providencia.setor):
            return False
        return self.pode_editar_como_auditado(user, apenas_como_chefe=False)

    #
    def pode_receber(self, user):
        return self.enviada and self.pode_editar_como_auditor(user)

    def pode_editar_manifestacao(self, user):
        return (self.registrada or self.enviada) and self.pode_editar_como_auditado(user, apenas_como_chefe=False)

    def pode_remover(self, user):
        if self.eh_da_auditoria:
            return self.pode_editar_como_auditor(user)
        return self.pode_editar_manifestacao(user)

    def pode_adicionar_posicionamento(self, user):
        if self.recebida and self.solicitacao_providencia.pode_editar_como_auditor(user):
            return not self.posicionamentos.ativos().exists()
        return False

    def pode_reclassificar(self, user):
        return not self.posicionamentos.exists() and self.pode_adicionar_posicionamento(user)

    def get_data_inclusao(self):
        return f'Incluído em {self.criado_em.strftime("%d/%m/%Y %H:%M")}'

    def get_documento(self):
        return self.documento

    def remover(self, user, justificativa):
        self.removido_por = user.get_vinculo()
        self.data_hora_remocao = get_datetime_now()
        self.justificativa_remocao = justificativa
        self.save()

    @transition(field=status, source=ManifestacaoStatus.REGISTRADA, target=ManifestacaoStatus.ENVIADA)
    def enviar(self, user):
        self.enviada_por = user.get_vinculo()
        self.enviada_em = get_datetime_now()
        self.solicitacao_providencia.aguardar_posicionamento()
        self.solicitacao_providencia.save()

    @transition(field=status, source=ManifestacaoStatus.ENVIADA, target=ManifestacaoStatus.RECEBIDA)
    def receber(self, user):
        self.recebida_por = user.get_vinculo()
        self.recebida_em = get_datetime_now()

    @transition(field=status, source=ManifestacaoStatus.RECEBIDA, target=ManifestacaoStatus.ANALISADA)
    def publicar(self, publicado_por=None, reabrir=True, justificativa='Finalização automática.'):
        if reabrir:
            if self.solicitacao_providencia.aguardando_posicionamento:
                self.solicitacao_providencia.reabrir_para_ciencia()
                self.solicitacao_providencia.save()
        elif self.solicitacao_providencia.ativa:
            self.solicitacao_providencia.finalizar(user=publicado_por, justificativa=justificativa)
            self.solicitacao_providencia.save()

    def adicionar_documento(self, documento, user):
        content_type = ContentType.objects.get_for_model(documento)
        ManifestacaoDocumento.objects.get_or_create(
            manifestacao=self, object_id=documento.id, content_type=content_type, defaults={'incluido_por': user.get_vinculo(), 'object': documento}
        )

    def remover_documento(self, documento, user):
        content_type = ContentType.objects.get_for_model(documento)
        relatorio_documento = ManifestacaoDocumento.objects.filter(content_type=content_type, object_id=documento.id).first()
        if relatorio_documento:
            relatorio_documento.remover_documento(user)
            relatorio_documento.save()

    def save(self, *args, **kwargs):
        if not self.pk:
            anterior = Manifestacao.objects.filter(solicitacao_providencia=self.solicitacao_providencia).order_by('-id').first()
            self.anterior = anterior
        #
        super().save(*args, **kwargs)

    @transaction.atomic()
    def delete(self, *args, **kwargs):
        Manifestacao.objects.filter(anterior=self).update(anterior=self.anterior)
        super().delete(*args, **kwargs)


class ManifestacaoDocumentoQueryset(DocumentoQueryset):
    def get_model(self):
        return apps.get_model('auditoria', 'ManifestacaoDocumento')


class ManifestacaoDocumentoManager(DocumentoManager):
    def get_queryset(self):
        return ManifestacaoDocumentoQueryset(self.model, using=self._db)


class ManifestacaoDocumento(Documento):
    manifestacao = models.ForeignKey(Manifestacao, on_delete=models.CASCADE, related_name='documentos')
    objects = ManifestacaoDocumentoManager()

    def pode_remover_documento(self, user):
        return not self.removido and self.manifestacao.pode_remover_documento(user)
