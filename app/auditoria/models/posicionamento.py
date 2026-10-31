from django.apps import apps
from django.core.exceptions import ValidationError
from django.db.models.query import QuerySet
from django.urls import reverse_lazy
from django_fsm import FSMIntegerField, transition

from comum.models import Vinculo
from djtools.db import models, transaction
from djtools.utils import get_datetime_now

from ..papeis import eh_auditor, eh_auditor_chefe
from .documento import Documento, DocumentoManager, DocumentoQueryset
from .manifestacao import TipoManifestacao


class TipoPosicionamento(models.TextChoices):
    ATENDIMENTO = 'AT', 'Atendimento'
    REITERACAO = 'RT', 'Reiteração'
    PRORROGACAO_PRAZO = 'PP', 'Prorrogação de prazo de atendimento'
    REVISAO = 'RV', 'Revisão'
    CANCELAMENTO = 'CN', 'Cancelamento'
    FINALIZAR_MONITORAMENTO = 'FM', 'Finalizar monitoramento'
    REJEITAR_SOLICITACAO = 'RS', 'Rejeitar Solicitação'

    @staticmethod
    def get_label(value):
        # Procura pelo valor fornecido nos valores definidos e retorna o label correspondente
        try:
            return TipoPosicionamento.labels[TipoPosicionamento.values.index(value)]
        except ValueError:
            return None  # Retorna None se o valor não for encontrado


class TipoPosicionamentoValido(models.Model):
    tipo_manifestacao = models.CharField(max_length=2, choices=TipoManifestacao.choices, verbose_name='Tipo de manifestação')
    tipo_posicionamento = models.CharField(max_length=2, choices=TipoPosicionamento.choices, verbose_name='Tipo de posicionamento')
    ativo = models.BooleanField(default=True)

    class Meta:
        unique_together = ['tipo_manifestacao', 'tipo_posicionamento']
        verbose_name = 'Tipo de Posicionamento'
        verbose_name_plural = 'Tipos de Posicionamentos'


class Motivacao(models.Model):
    tipo_posicionamento = models.CharField(max_length=2, choices=TipoPosicionamento.choices, verbose_name='Tipo de posicionamento')
    motivo = models.CharField(max_length=255)
    ativo = models.BooleanField(default=True)

    class Meta:
        unique_together = ['tipo_posicionamento', 'motivo']
        verbose_name = 'Motivação'
        verbose_name_plural = 'Motivações'

    def __str__(self) -> str:
        return self.motivo


class PosicionamentoStatus(models.IntegerChoices):
    REGISTRADO = 0, 'Registrado'
    REVISAO_PENDENTE = 1, 'Esperando Revisão'
    EM_REVISAO = 2, 'Em revisão'
    REVISADO = 3, 'Revisado'
    SUPERVISAO_PENDENTE = 4, 'Esperando revisão da chefia'
    EM_SUPERREVISAO = 5, 'Em revisão pela chefia'
    SUPERVISIONADO = 6, 'Revisado pela chefia'
    PUBLICADO = 7, 'Publicado'
    REVOGADO = 8, 'Revogado'
    ARQUIVADO = 9, 'Arquivado'


class PosicionamentoQueryset(QuerySet):
    def get_model(self):
        return apps.get_model('auditoria', 'Posicionamento')

    def aguardando_revisao(self):
        return self.filter(status=PosicionamentoStatus.REVISAO_PENDENTE)

    def em_revisao(self):
        return self.filter(status=PosicionamentoStatus.EM_REVISAO)

    def revisado(self):
        return self.filter(status=PosicionamentoStatus.REVISADO)

    def ativos(self):
        return self.exclude(status__in=[PosicionamentoStatus.ARQUIVADO, PosicionamentoStatus.REVOGADO])

    def atendidos(self):
        return self.filter(tipo=TipoPosicionamento.ATENDIMENTO)


class PosicionamentoManager(models.Manager):
    def get_queryset(self):
        return PosicionamentoQueryset(self.model, using=self._db)

    def aguardando_revisao(self):
        return self.get_queryset().aguardando_revisao()

    def em_revisao(self):
        return self.get_queryset().em_revisao()

    def revisado(self):
        return self.get_queryset().revisado()

    def ativos(self):
        return self.get_queryset().ativos()


class Posicionamento(models.Model):
    #
    manifestacao = models.ForeignKey('auditoria.Manifestacao', on_delete=models.CASCADE, related_name='posicionamentos', null=False, blank=False)
    tipo = models.CharField(max_length=2, choices=TipoPosicionamento.choices, verbose_name='Tipo de posicionamento')
    motivacao = models.ForeignKey(Motivacao, on_delete=models.CASCADE, related_name='posicionamentos', null=False, blank=False)
    outros = models.TextField(blank=True, null=True)
    #
    parecer = models.TextField(blank=True, null=True, verbose_name='Parecer da Auditoria')
    # Dados
    criado_em = models.DateTimeFieldPlus('Data de inclusão', auto_now_add=True)
    incluido_por = models.CurrentUserField(
        verbose_name='Usuário de inclusão', related_name='%(app_label)s_%(class)s_incluido_por', null=False, editable=False
    )
    ultima_modificacao = models.DateTimeField(auto_now=True, verbose_name='Última modificação')
    publicado_por = models.ForeignKey(
        Vinculo, verbose_name='Pubicado por', related_name='%(app_label)s_%(class)s_publicado_por', null=True, blank=True, on_delete=models.CASCADE
    )
    publicado_em = models.DateTimeField(verbose_name='Públicado em', null=True, blank=True)
    ciencia_em = models.DateTimeField(verbose_name='Ciência em', null=True, blank=True, help_text='Data da ciência do auditado')

    # Status
    status = FSMIntegerField(default=PosicionamentoStatus.REGISTRADO, choices=PosicionamentoStatus.choices, protected=True)

    tipo_handlers = {
        TipoPosicionamento.ATENDIMENTO: 'handle_atendimento',
        TipoPosicionamento.REITERACAO: 'handle_reiterar',
        TipoPosicionamento.FINALIZAR_MONITORAMENTO: 'handle_finalizar',
        TipoPosicionamento.CANCELAMENTO: 'handle_cancelar',
        TipoPosicionamento.REVISAO: 'handle_reiterar',
        # Rejeitar a solicitação do gestor (revisão/cancelamento/prorrogação): a demanda
        # original permanece, então reabre a solicitação para nova ciência — mesmo efeito
        # de estado da reiteração. Sem handler, a solicitação ficava presa em
        # "Aguardando Posicionamento" após o posicionamento publicado.
        TipoPosicionamento.REJEITAR_SOLICITACAO: 'handle_reiterar',
    }

    objects = PosicionamentoManager()

    class Meta:
        verbose_name = 'Posicionamento'
        verbose_name_plural = 'Posicionamentos'

    def __str__(self):
        return f'Posicionamento #{self.id}'

    @property
    def ultima_movimentacao_em(self):
        return self.publicado_em or self.ultima_modificacao

    @staticmethod
    def update_related_object(instance: Posicionamento, actions, **kwargs):
        """Executa ações no monitoramento com base no estado do posicionamento.

        Args:
            instance (Posicionamento): A instância do posicionamento.
            actions (dict): Um dicionário mapeando os estados aos métodos correspondentes do monitoramento.
            kargs: extra parameters....

        Returns:
            bool: True se houve mudança no monitoramento, False caso contrário.
        """
        for state_check, method_name in actions.items():
            if getattr(instance, state_check):
                getattr(instance.referencia, method_name)(**kwargs)
                instance.referencia.save()
                return True
        #
        return False

    @classmethod
    def handle_cancelar(cls, instance: Posicionamento) -> None:
        actions = {'publicado': 'cancelar'}
        if instance.publicado:
            justificativa = 'Cancelamento do monitoramento por solicitação do auditado.'
            # Notifica a manifestação sobre o cancelamento
            instance.notify_manifestacao(publicado_por=instance.incluido_por, reabrir=False, justificativa=justificativa)
        return cls.update_related_object(instance, actions, cancelado_por=instance.incluido_por)

    @classmethod
    def handle_reiterar(cls, instance: Posicionamento) -> None:
        actions = {'esperando_revisao': 'solicitar_revisao', 'em_revisao': 'revisar', 'revisado': 'concluir_revisao', 'publicado': 'reiterar'}
        if instance.publicado:
            instance.notify_manifestacao(reabrir=True)
        return cls.update_related_object(instance, actions)

    @classmethod
    def handle_atendimento(cls, instance: Posicionamento):
        actions = {'esperando_revisao': 'solicitar_revisao', 'em_revisao': 'revisar', 'revisado': 'concluir_revisao', 'publicado': 'concluir'}
        if instance.publicado:
            justificativa = 'Finalização por atendimento das providências.'
            instance.notify_manifestacao(publicado_por=instance.incluido_por, reabrir=False, justificativa=justificativa)
        return cls.update_related_object(instance, actions, user=instance.incluido_por)

    @classmethod
    def handle_finalizar(cls, instance: Posicionamento):
        actions = {'esperando_revisao': 'solicitar_revisao', 'em_revisao': 'revisar', 'revisado': 'concluir_revisao', 'publicado': 'finalizar'}
        if instance.publicado:
            justificativa = 'Finalização do monitoramento por não atendimento das providências.'
            instance.notify_manifestacao(publicado_por=instance.incluido_por, reabrir=False, justificativa=justificativa)
        return cls.update_related_object(instance, actions, user=instance.incluido_por, justificativa=instance.parecer)

    @property
    def revisor(self) -> Vinculo:
        return self.manifestacao.revisor

    @property
    def referencia(self):
        return self.manifestacao.content_object

    @property
    def solicitacao_providencia(self):
        return self.manifestacao.solicitacao_providencia

    @property
    def registrado(self):
        return self.status == PosicionamentoStatus.REGISTRADO

    @property
    def esperando_revisao(self):
        return self.status == PosicionamentoStatus.REVISAO_PENDENTE

    @property
    def em_revisao(self):
        return self.status == PosicionamentoStatus.EM_REVISAO

    @property
    def revisado(self):
        return self.status == PosicionamentoStatus.REVISADO

    @property
    def publicado(self):
        return self.status == PosicionamentoStatus.PUBLICADO

    @property
    def revogado(self):
        return self.status == PosicionamentoStatus.REVOGADO

    @property
    def arquivado(self):
        return self.status == PosicionamentoStatus.ARQUIVADO

    @property
    def prorrogacao_prazo(self):
        return self.tipo == TipoPosicionamento.PRORROGACAO_PRAZO

    @property
    def editavel(self):
        return self.status in [PosicionamentoStatus.REGISTRADO, PosicionamentoStatus.REVISADO, PosicionamentoStatus.SUPERVISIONADO]

    def get_absolute_url(self):
        return reverse_lazy('auditoria:visualizar_posicionamento', kwargs={'posicionamento_id': self.pk})

    def eh_revisor(self, user):
        return self.referencia.eh_revisor(user)

    def eh_monitor(self, user):
        return self.referencia.eh_monitor(user)

    def get_motivo(self):
        return self.outros or self.motivacao

    def pode_publicar(self, user):
        return self.pode_editar(user) and not self.manifestacao.analisada

    def pode_visualizar(self, user):
        if eh_auditor_chefe(user):
            return True
        #
        if self.publicado:
            return self.manifestacao.pode_visualizar(user)
        return self.eh_monitor(user) if self.registrado else eh_auditor(user)

    def pode_editar(self, user):
        return self.editavel and self.manifestacao.pode_editar_como_auditor(user)

    def pode_solicitar_revisao(self, user):
        return self.registrado and self.manifestacao.pode_editar_como_auditor(user)

    def pode_revisar(self, user):
        return self.esperando_revisao and (self.referencia.eh_revisor(user))

    def atribuir_revisor(self, revisor: Vinculo):
        self.referencia.atribuir_revisor(revisor)

    def pode_remover_documento(self, user):
        return self.pode_editar(user)

    @transition(field=status, source=PosicionamentoStatus.REGISTRADO, target=PosicionamentoStatus.REVISAO_PENDENTE)
    def solicitar_revisao(self):
        pass

    @transition(field=status, source=PosicionamentoStatus.REVISAO_PENDENTE, target=PosicionamentoStatus.EM_REVISAO)
    def colocar_em_revisao(self):
        pass

    @transition(field=status, source=PosicionamentoStatus.EM_REVISAO, target=PosicionamentoStatus.REVISADO)
    def concluir_revisao(self):
        pass

    @transition(field=status, source=PosicionamentoStatus.EM_REVISAO, target=PosicionamentoStatus.REVISAO_PENDENTE)
    def reabrir_revisao(self):
        # Volta o posicionamento para "esperando revisão" quando a revisão em andamento é
        # removida, permitindo designar/registrar uma nova revisão (evita travar em EM_REVISAO).
        pass

    @transition(field=status, source=PosicionamentoStatus.REVISADO, target=PosicionamentoStatus.SUPERVISAO_PENDENTE)
    def solicitar_supervisao(self):
        pass

    @transition(field=status, source=PosicionamentoStatus.SUPERVISAO_PENDENTE, target=PosicionamentoStatus.EM_SUPERREVISAO)
    def colocar_em_supervisao(self):
        pass

    @transition(field=status, source=PosicionamentoStatus.EM_SUPERREVISAO, target=PosicionamentoStatus.SUPERVISIONADO)
    def concluir_supervisao(self):
        pass

    @transition(
        field=status,
        source=[PosicionamentoStatus.REGISTRADO, PosicionamentoStatus.REVISADO, PosicionamentoStatus.SUPERVISIONADO],
        target=PosicionamentoStatus.PUBLICADO,
    )
    def publicar(self, user):
        self.publicado_por = user.get_vinculo()
        self.publicado_em = get_datetime_now()

    @transition(field=status, source=PosicionamentoStatus.PUBLICADO, target=PosicionamentoStatus.REVOGADO)
    def revogar(self):
        pass

    @transition(
        field=status,
        source=[
            PosicionamentoStatus.REGISTRADO,
            PosicionamentoStatus.REVISAO_PENDENTE,
            PosicionamentoStatus.EM_REVISAO,
            PosicionamentoStatus.REVISADO,
        ],
        target=PosicionamentoStatus.ARQUIVADO,
    )
    def arquivar(self):
        pass

    def verificar_tipos(self):
        tipos_validos = TipoPosicionamentoValido.objects.filter(tipo_manifestacao=self.manifestacao.tipo)
        tipos_validos = [tipo.tipo_posicionamento for tipo in tipos_validos]
        #
        if self.tipo not in tipos_validos:
            raise ValidationError({'tipo': f'O tipo de posicionamento {self.tipo} não é válido para a manifestação {self.manifestacao.tipo}'})
        #
        if self.motivacao not in Motivacao.objects.filter(tipo_posicionamento=self.tipo):
            raise ValidationError({'motivo': f'O motivo "{self.motivacao}" não é válido para o tipo de posicionamento "{self.tipo}"'})

    def arquivar_nao_publicados(self):
        inativos = Posicionamento.objects.filter(manifestacao=self.manifestacao).exclude(pk=self.id)
        for inativo in inativos:
            inativo.arquivar()
            inativo.save()

    def notify_manifestacao(self, publicado_por=None, reabrir=True, justificativa=None):
        publicado_por = publicado_por or self.publicado_por
        self.manifestacao.publicar(publicado_por, reabrir, justificativa)
        self.manifestacao.save()
        self.arquivar_nao_publicados()

    def notificar_acesso_auditado(self, user):
        if self.ciencia_em is None:
            self.ciencia_em = get_datetime_now()
            self.save()
            return True
        return False

    def has_changed(self, field_name):
        """
        Método auxiliar para detectar mudanças no campo especificado por field_name
        """
        if not self.pk:
            return False
        old_instance = self.__class__._default_manager.select_for_update().get(pk=self.pk)
        old_value = getattr(old_instance, field_name)
        return getattr(self, field_name) != old_value

    def handle_post_transition(self):
        handler_name = self.tipo_handlers.get(self.tipo)
        handler = getattr(self.__class__, handler_name, None) if handler_name else None
        return handler(self) if handler is not None else False

    @transaction.atomic()
    def save(self, *args, **kwargs):
        has_changed = self.has_changed('status')
        super().save(*args, **kwargs)
        if has_changed:
            self.handle_post_transition()


class PosicionamentoDocumentoQueryset(DocumentoQueryset):
    def get_model(self):
        return apps.get_model('auditoria', 'PosicionamentoDocumento')


class PosicionamentoDocumentoManager(DocumentoManager):
    def get_queryset(self):
        return PosicionamentoDocumentoQueryset(self.model, using=self._db)


class PosicionamentoDocumento(Documento):
    posicionamento = models.ForeignKey(Posicionamento, on_delete=models.CASCADE, related_name='documentos')
    objects = PosicionamentoDocumentoManager()

    def pode_remover_documento(self, user):
        return not self.removido and self.posicionamento.pode_remover_documento(user)


class ParecerChoices(models.IntegerChoices):
    CONCORDO = 1, 'Concordo'
    DIVERGENTE = 2, 'Divergente'


class RevisaoStatus(models.IntegerChoices):
    EM_REVISAO = 0, 'Em Revisão'
    ENVIADO = 1, 'Enviado'


class RevisaoPosicionamento(models.Model):
    posicionamento = models.ForeignKey(Posicionamento, on_delete=models.CASCADE, related_name='revisoes')
    tipo = models.CharField(max_length=2, choices=TipoPosicionamento.choices, verbose_name='Posicionamento do Revisor')
    parecer = models.IntegerField(choices=ParecerChoices.choices, verbose_name='Parecer do Revisor')
    comentario = models.TextField(blank=True, verbose_name='Comentário do Revisor')
    revisor = models.ForeignKey(Vinculo, on_delete=models.CASCADE, related_name='revisoes_posicionamento')
    criado_em = models.DateTimeFieldPlus('Data de Inclusão', auto_now_add=True)
    ultima_modificacao = models.DateTimeField(auto_now=True, verbose_name='Última modificação')
    status = FSMIntegerField(default=RevisaoStatus.EM_REVISAO, choices=RevisaoStatus.choices, protected=True)

    def __str__(self):
        return f'{self.revisor} - {self.get_parecer_display()}'

    @property
    def em_revisao(self):
        return self.status == RevisaoStatus.EM_REVISAO

    @property
    def enviado(self):
        return self.status == RevisaoStatus.ENVIADO

    def eh_revisor(self, user):
        return self.revisor == user.get_vinculo()

    def pode_visualizar(self, user):
        if self.em_revisao:
            return self.eh_revisor(user) or eh_auditor_chefe(user)
        return eh_auditor(user)

    def pode_enviar(self, user):
        return self.em_revisao and self.eh_revisor(user)

    def pode_remover(self, user):
        return self.em_revisao and (self.eh_revisor(user) or eh_auditor_chefe(user))

    @transition(field=status, source=RevisaoStatus.EM_REVISAO, target=RevisaoStatus.ENVIADO)
    def enviar(self):
        self.posicionamento.concluir_revisao()
        self.posicionamento.save()

    def colocar_em_revisao(self):
        self.posicionamento.colocar_em_revisao()
        self.posicionamento.save()

    @transaction.atomic()
    def save(self, *args, **kwargs):
        is_insert = self.pk is None
        if is_insert:
            self.colocar_em_revisao()
        super().save(*args, **kwargs)

    @transaction.atomic()
    def delete(self, *args, **kwargs):
        posicionamento = self.posicionamento
        super().delete(*args, **kwargs)
        # Sem revisão restante e ainda em revisão: reabre o posicionamento para nova revisão
        # (o save dispara o handler, que ressincroniza o monitoramento para AGUARDANDO_REVISAO).
        if posicionamento.em_revisao and not posicionamento.revisoes.exists():
            posicionamento.reabrir_revisao()
            posicionamento.save()


class RevisaoChefia(models.Model):
    revisao_posicionamento = models.OneToOneField(RevisaoPosicionamento, on_delete=models.CASCADE, related_name='revisao_chefia')
    tipo = models.CharField(max_length=2, choices=TipoPosicionamento.choices, verbose_name='Posicionamento da chefia')
    chefia = models.ForeignKey(Vinculo, on_delete=models.CASCADE, related_name='revisoes_chefia')
    comentario_chefia = models.TextField(blank=True, verbose_name='Comentário da Chefia')
    criado_em = models.DateTimeFieldPlus('Data de Inclusão', auto_now_add=True)
    ultima_modificacao = models.DateTimeField(auto_now=True, verbose_name='Última modificação')
    status = FSMIntegerField(default=RevisaoStatus.EM_REVISAO, choices=RevisaoStatus.choices, protected=True)

    def __str__(self):
        return f'Parecer final de {self.chefia}: {self.get_parecer_final_display()}'

    @transition(field=status, source=RevisaoStatus.EM_REVISAO, target=RevisaoStatus.ENVIADO)
    def enviar(self):
        pass
