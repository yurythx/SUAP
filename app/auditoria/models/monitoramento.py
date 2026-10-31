from collections import OrderedDict

from django.apps import apps
from django.db.models import Q
from django.db.models.query import QuerySet
from django.template.defaultfilters import slugify
from django.contrib.contenttypes.fields import GenericRelation
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse_lazy
from django_fsm import FSMIntegerField, transition
from djtools.db import models, transaction
from djtools.utils import get_datetime_now

from comum.models import Vinculo
from rh.models import Setor

from ..papeis import eh_auditor, eh_auditor_chefe, get_todos_chefes_setores, tenho_poder_de_chefe
from .recomendacao import Recomendacao
from .providencia import SolicitacaoProvidenciaStatus


class MonitoramentoStatus:
    REGISTRADO = 0
    EM_MONITORAMENTO = 1
    AGUARDANDO_REVISAO = 2
    EM_REVISAO = 3
    REVISADO = 4
    CONCLUIDO = 5
    FINALIZADO = 6
    CANCELADO = 7

    CHOICES = {
        REGISTRADO: 'Registrada',
        EM_MONITORAMENTO: 'Em monitoramento',
        AGUARDANDO_REVISAO: 'Aguardando revisão',
        EM_REVISAO: 'Em revisão',
        REVISADO: 'Revisado',
        CONCLUIDO: 'Atendida',
        FINALIZADO: 'Não atendida',
        CANCELADO: 'Cancelada',
    }

    @staticmethod
    def get_status_description(status_code):
        # Return the description for the status code with a default of None if not found
        return MonitoramentoStatus.CHOICES.get(status_code, None)

    SITUACOES_TERMINAIS = [
        CANCELADO,
    ]
    SITUACOES_FINAIS = [CONCLUIDO, FINALIZADO, *SITUACOES_TERMINAIS]
    SITUACOES_REVISIONAIS = [AGUARDANDO_REVISAO, EM_REVISAO, REVISADO]
    SITUACOES_EM_REVISAO = [AGUARDANDO_REVISAO, EM_REVISAO]

    SITUACOES_FLUXO_AUDITOR = OrderedDict()
    SITUACOES_FLUXO_AUDITOR[REGISTRADO] = [CHOICES[REGISTRADO], 'info']
    SITUACOES_FLUXO_AUDITOR[EM_MONITORAMENTO] = [CHOICES[EM_MONITORAMENTO], 'alert']
    SITUACOES_FLUXO_AUDITOR[AGUARDANDO_REVISAO] = [CHOICES[AGUARDANDO_REVISAO], 'alert']
    SITUACOES_FLUXO_AUDITOR[EM_REVISAO] = [CHOICES[EM_REVISAO], 'alert']
    SITUACOES_FLUXO_AUDITOR[REVISADO] = [CHOICES[REVISADO], 'alert']
    SITUACOES_FLUXO_AUDITOR[CONCLUIDO] = [CHOICES[CONCLUIDO], 'success']

    SITUACOES_FLUXO_AUDITADO = OrderedDict()
    SITUACOES_FLUXO_AUDITADO[REGISTRADO] = [CHOICES[REGISTRADO], 'info']
    SITUACOES_FLUXO_AUDITADO[EM_MONITORAMENTO] = [CHOICES[EM_MONITORAMENTO], 'alert']
    SITUACOES_FLUXO_AUDITADO[CONCLUIDO] = [CHOICES[CONCLUIDO], 'success']

    @staticmethod
    def get_fluxo_auditor(status):
        fluxo = list(MonitoramentoStatus.SITUACOES_FLUXO_AUDITOR.items())
        if status == MonitoramentoStatus.FINALIZADO:
            fluxo[-1] = (status, ['Não Atendida', 'alert'])
        return fluxo

    @staticmethod
    def get_fluxo_auditado(status):
        fluxo = list(MonitoramentoStatus.SITUACOES_FLUXO_AUDITADO.items())
        if status == MonitoramentoStatus.FINALIZADO:
            fluxo[-1] = (status, ['Não Atendida', 'alert'])
        return fluxo

    @staticmethod
    def get_fluxo(status, eh_auditor):
        if eh_auditor:
            return MonitoramentoStatus.get_fluxo_auditor(status)
        #
        return MonitoramentoStatus.get_fluxo_auditado(status)

    @staticmethod
    def get_display_and_class(status):
        """
        Retorna um par (display, classe) para o status informado.
        """
        if status in MonitoramentoStatus.SITUACOES_FLUXO_AUDITOR:
            # Se o status estiver no dicionário de fluxo, retorna o display e a classe correspondentes
            # ao status
            return MonitoramentoStatus.SITUACOES_FLUXO_AUDITOR[status]

        if status in MonitoramentoStatus.SITUACOES_TERMINAIS:
            return MonitoramentoStatus.CHOICES[status], 'error'

        return (status, 'default')


class MonitoramentoQueryset(QuerySet):
    def get_model(self):
        return apps.get_model('auditoria', 'OrigemDemanda')

    def registrados(self):
        return self.filter(status=MonitoramentoStatus.REGISTRADO)

    def emitidos(self):
        return self.exclude(status=MonitoramentoStatus.REGISTRADO)

    def iniciados(self):
        return self.exclude(status__in=[MonitoramentoStatus.REGISTRADO, MonitoramentoStatus.CANCELADO])

    def em_andamento(self):
        return self.filter(Q(status__in=MonitoramentoStatus.SITUACOES_REVISIONAIS) | Q(status=MonitoramentoStatus.EM_MONITORAMENTO))

    def em_monitoramento(self):
        return self.filter(status=MonitoramentoStatus.EM_MONITORAMENTO)

    def concluidos(self):
        return self.filter(status=MonitoramentoStatus.CONCLUIDO)

    def finalizados(self):
        return self.filter(status=MonitoramentoStatus.FINALIZADO)

    def cancelados(self):
        return self.filter(status=MonitoramentoStatus.CANCELADO)

    def aguardando_revisao(self):
        return self.filter(status=MonitoramentoStatus.AGUARDANDO_REVISAO)

    def em_revisao(self):
        return self.filter(status=MonitoramentoStatus.EM_REVISAO)

    def revisado(self):
        return self.filter(status=MonitoramentoStatus.REVISADO)

    def em_processo_de_revisao(self):
        return self.filter(status__in=MonitoramentoStatus.SITUACOES_EM_REVISAO)

    def ativos(self):
        return self.exclude(status__in=[MonitoramentoStatus.CANCELADO, MonitoramentoStatus.REGISTRADO])

    def concluidos_ou_finalizados(self):
        return self.filter(status__in=[MonitoramentoStatus.CONCLUIDO, MonitoramentoStatus.FINALIZADO])

    def recomendacoes_a_monitorar(self):
        qs = self.registrados().distinct('recomendacao')
        ids = qs.values_list('recomendacao', flat=True)
        return Recomendacao.objects.filter(id__in=ids).distinct()

    def sem_pendencias(self):
        return self.exclude(ultima_solicitacao__status=SolicitacaoProvidenciaStatus.STATUS_AGUARDANDO_POSICIONAMENTO)

    def beneficios(self):
        from .beneficio import Beneficio

        return Beneficio.objects.filter(
            content_type=ContentType.objects.get_for_model(Monitoramento), object_id__in=self.values_list('id', flat=True)
        )

    def expirados(self):
        return self.filter(
            ultima_solicitacao__status=SolicitacaoProvidenciaStatus.STATUS_EXPIRADA, status=MonitoramentoStatus.EM_MONITORAMENTO
        ).distinct()


class MonitoramentoManager(models.Manager):
    def get_queryset(self):
        return MonitoramentoQueryset(self.model, using=self._db)

    def registrados(self):
        return self.get_queryset().registrados()

    def iniciados(self):
        return self.get_queryset().iniciados()

    def emitidos(self):
        return self.get_queryset().emitidos()

    def em_andamento(self):
        return self.get_queryset().em_andamento()

    def em_monitoramento(self):
        return self.get_queryset().em_monitoramento()

    def concluidos(self):
        return self.get_queryset().concluidos()

    def finalizados(self):
        return self.get_queryset().finalizados()

    def cancelados(self):
        return self.get_queryset().cancelados()

    def recomendacoes_a_monitorar(self):
        return self.get_queryset().recomendacoes_a_monitorar()

    def em_processo_de_revisao(self):
        return self.get_queryset().em_processo_de_revisao()

    def ativos(self):
        return self.get_queryset().ativos()

    def concluidos_ou_finalizados(self):
        return self.get_queryset().concluidos_ou_finalizados()

    def beneficios(self):
        return self.get_queryset().beneficios()

    def expirados(self):
        return self.get_queryset().expirados()


class Monitoramento(models.ModelPlus):
    recomendacao = models.ForeignKey(Recomendacao, on_delete=models.CASCADE, related_name='monitoramentos', verbose_name='Recomendação')
    unidade = models.ForeignKeyPlus(Setor, verbose_name='Unidade monitorada', on_delete=models.PROTECT)
    data_inicio = models.DateTimeField(verbose_name='Data de início do monitoramento', null=True, blank=True)
    data_conclusao = models.DateTimeField(verbose_name='Data de finalização do monitoramento', null=True, blank=True)
    status = FSMIntegerField(
        default=MonitoramentoStatus.REGISTRADO, choices=MonitoramentoStatus.CHOICES.items(), protected=True, verbose_name='Situação'
    )
    justificativa = models.TextField(verbose_name='Justificativa', null=True, blank=True)
    encerrado_por = models.ForeignKeyPlus(
        'comum.Vinculo', verbose_name='Cancelada por', null=True, related_name='%(app_label)s_%(class)s_encerrada_por'
    )
    ultima_solicitacao = models.OneToOneField('auditoria.SolicitacaoProvidencia', null=True, blank=True, on_delete=models.SET_NULL, related_name='+')

    beneficios = GenericRelation('auditoria.Beneficio', related_query_name='monitoramentos')
    objects = MonitoramentoManager()

    class Meta:
        unique_together = ('unidade', 'recomendacao')
        verbose_name = 'Monitoramento'
        verbose_name_plural = 'Monitoramentos'

    def __str__(self):
        return f'{self.recomendacao} - {self.unidade}'

    def get_absolute_url(self):
        return reverse_lazy('auditoria:visualizar_monitoramento', kwargs={'monitoramento_id': self.pk})

    def get_reference_object_url(self):
        return f'{self.recomendacao.get_absolute_url()}?tab={slugify(self.unidade)}'

    @property
    def acao(self):
        return self.recomendacao.acao

    @property
    def monitor(self):
        return self.recomendacao.monitor

    @property
    def revisor(self):
        return self.recomendacao.revisor

    @property
    def data_limite(self):
        return self.recomendacao.data_limite

    @property
    def manifestacoes_para_monitoramento(self):
        return self.manifestacoes.all()

    @property
    def registrado(self):
        return self.status == MonitoramentoStatus.REGISTRADO

    @property
    def em_monitoramento(self):
        return self.status == MonitoramentoStatus.EM_MONITORAMENTO

    @property
    def esperando_revisao(self):
        return self.status == MonitoramentoStatus.AGUARDANDO_REVISAO

    @property
    def em_revisao(self):
        return self.status == MonitoramentoStatus.EM_REVISAO

    @property
    def revisado(self):
        return self.status == MonitoramentoStatus.REVISADO

    @property
    def concluido(self):
        return self.status == MonitoramentoStatus.CONCLUIDO

    @property
    def finalizado(self):
        return self.status == MonitoramentoStatus.FINALIZADO

    @property
    def cancelado(self):
        return self.status == MonitoramentoStatus.CANCELADO

    @property
    def situacao_final(self):
        return self.status in MonitoramentoStatus.SITUACOES_FINAIS

    @property
    def situacao_terminal(self):
        return self.status in MonitoramentoStatus.SITUACOES_TERMINAIS

    @property
    def situacao_revisional(self):
        return self.status in MonitoramentoStatus.SITUACOES_REVISIONAIS

    @property
    def ativo(self):
        return self.em_monitoramento or self.situacao_revisional

    @property
    def prazo_atual(self):
        return self.ultima_solicitacao.prazo_atual if self.ultima_solicitacao else '-'

    @property
    def solicitacoes_ordenadas(self):
        return self.solicitacoes.all().order_by('prazo_atual')

    def ano_atendimento(self):
        return self.data_conclusao.year if self.concluido else '-'

    def manifestacoes_auditoria(self):
        return self.manifestacoes.manifestacoes_auditoria().all()

    def get_ultima_solicitacao(self):
        return self.solicitacoes.all().ultima_solicitacao_por(self)

    def get_ultima_manifestacao(self):
        return self.manifestacoes.all().order_by('-id').first()

    def get_ultima_manifestacao_pendente(self):
        return self.manifestacoes.aguardando_analise().order_by('-ultima_modificacao').first()

    def get_vinculos_chefes(self):
        return get_todos_chefes_setores([self.unidade])

    def pode_visualizar_monitoramento(self, user):
        sou_chefe = tenho_poder_de_chefe(user, self.unidade)
        if sou_chefe or user.is_superuser:
            return True
        vinculo = user.get_vinculo()
        return self.indicacoes.filter(servidor=vinculo, revogada=False).exists()

    def pode_excluir(self, user):
        return eh_auditor_chefe(user) or user.is_superuser

    def pode_designar_servidor(self, user):
        if self.indicacoes.ativas().exists():
            return False
        if not tenho_poder_de_chefe(user, self.unidade):
            return False
        return self.pode_adicionar_manifestacao(user)

    def pode_revogar(self, user):
        sou_chefe = tenho_poder_de_chefe(user, self.unidade)
        return sou_chefe

    def eh_monitor(self, user):
        return self.monitor == user.get_vinculo()

    def eh_revisor(self, user):
        return self.revisor == user.get_vinculo()

    def atribuir_revisor(self, vinculo: Vinculo):
        self.recomendacao.revisor = vinculo
        self.recomendacao.save()

    def em_prazo_manifestacao(self):
        return self.ultima_solicitacao.em_prazo_manifestacao()

    def pode_enviar_solicitacao(self, user):
        if self.ultima_solicitacao is None:
            return self.em_monitoramento
        return not self.ultima_solicitacao.ativa and self.pode_editar(user)

    def pode_editar_manifestacoes(self, user):
        # Verifica se o monitoramento está em andamento e dentro do prazo de manifestação
        if self.em_monitoramento and self.em_prazo_manifestacao():
            # Verifica se o usuário é chefe ou indicado (caso permitido)
            sou_chefe = tenho_poder_de_chefe(user, self.unidade)
            vinculo = user.get_vinculo()
            sou_indicado = self.indicacoes.filter(servidor=vinculo, revogada=False, tarefa_realizada=False).exists()
            if sou_chefe or sou_indicado:
                manifestacoes_correntes = self.manifestacoes.filter(solicitacao_providencia=self.ultima_solicitacao)
                return not manifestacoes_correntes.aguardando_analise().exists()
        return False

    def pode_adicionar_manifestacao(self, user):
        if self.em_monitoramento and self.em_prazo_manifestacao():
            # Verifica se o usuário é chefe ou indicado (caso permitido)
            sou_chefe = tenho_poder_de_chefe(user, self.unidade)
            vinculo = user.get_vinculo()
            sou_indicado = self.indicacoes.filter(servidor=vinculo, revogada=False, tarefa_realizada=False).exists()
            if sou_chefe or sou_indicado:
                manifestacoes_correntes = self.manifestacoes.filter(solicitacao_providencia=self.ultima_solicitacao)
                return not manifestacoes_correntes.nao_analisadas().exists()
        return False

    def pode_editar(self, user):
        if self.situacao_final or self.recomendacao.inativa:
            return False
        return self.eh_monitor(user) or eh_auditor_chefe(user)

    def pode_receber_manifestacao(self):
        return self.em_prazo_manifestacao() and not self.situacao_final

    def pode_cancelar(self, user):
        if self.em_monitoramento and self.pode_editar(user):
            return self.ultima_solicitacao and not self.ultima_solicitacao.aguardando_posicionamento
        return False

    def pode_iniciar_monitoramento(self, user):
        return self.registrado and self.pode_editar(user)

    def pode_finalizar(self, user):
        if self.em_monitoramento and self.ultima_solicitacao:
            return not self.ultima_solicitacao.ativa and self.pode_editar(user)
        return False

    @transition(field=status, source=MonitoramentoStatus.REGISTRADO, target=MonitoramentoStatus.EM_MONITORAMENTO)
    def iniciar_monitoramento(self):
        self.data_inicio = get_datetime_now()

    @transition(field=status, source=MonitoramentoStatus.CANCELADO, target=MonitoramentoStatus.EM_MONITORAMENTO)
    def reiniciar(self):
        self.data_conclusao = None
        self.encerrado_por = None
        self.justificativa = None

    @transition(
        field=status,
        source=[MonitoramentoStatus.EM_MONITORAMENTO, MonitoramentoStatus.EM_REVISAO],
        target=MonitoramentoStatus.AGUARDANDO_REVISAO,
    )
    def solicitar_revisao(self, *args, **kwargs):
        # Origem EM_REVISAO cobre a reabertura: ao remover a revisão em andamento, o
        # posicionamento volta a REVISAO_PENDENTE e o handler ressincroniza o monitoramento.
        pass

    @transition(field=status, source=MonitoramentoStatus.AGUARDANDO_REVISAO, target=MonitoramentoStatus.EM_REVISAO)
    def revisar(self, *args, **kwargs):
        pass

    @transition(field=status, source=MonitoramentoStatus.EM_REVISAO, target=MonitoramentoStatus.REVISADO)
    def concluir_revisao(self, *args, **kwargs):
        pass

    @transition(
        field=status, source=[MonitoramentoStatus.EM_MONITORAMENTO, MonitoramentoStatus.REVISADO], target=MonitoramentoStatus.EM_MONITORAMENTO
    )
    def reiterar(self):
        pass

    @transition(field=status, source=[MonitoramentoStatus.EM_MONITORAMENTO, MonitoramentoStatus.REVISADO], target=MonitoramentoStatus.CONCLUIDO)
    def concluir(self, user, justificativa: str = 'Solicitação Atendida'):
        self.data_conclusao = get_datetime_now()
        self.encerrado_por = user.get_vinculo()
        self.justificativa = justificativa

    @transition(field=status, source=MonitoramentoStatus.EM_MONITORAMENTO, target=MonitoramentoStatus.FINALIZADO)
    def finalizar(self, user, justificativa: str = 'Finalizado pela auditoria'):
        self.data_conclusao = get_datetime_now()
        self.encerrado_por = user.get_vinculo()
        self.justificativa = justificativa

    @transition(field=status, source='*', target=MonitoramentoStatus.CANCELADO)
    def cancelar(self, cancelado_por, justificativa='Cancelamento a pedido do gestor'):
        self.data_conclusao = get_datetime_now()
        self.encerrado_por = cancelado_por.get_vinculo()
        self.justificativa = justificativa
        if self.ultima_solicitacao and self.ultima_solicitacao.ativa:
            self.ultima_solicitacao.cancelar(cancelado_por, justificativa)
            self.ultima_solicitacao.save()

    def get_steps(self, user):
        if self.status in MonitoramentoStatus.SITUACOES_TERMINAIS:
            return None
        #
        sou_auditor = eh_auditor(user)
        fluxo = MonitoramentoStatus.get_fluxo(self.status, sou_auditor)
        status = self.status
        if not sou_auditor and self.status in MonitoramentoStatus.SITUACOES_REVISIONAIS:
            status = MonitoramentoStatus.EM_MONITORAMENTO
        #
        steps = '<ul class="steps">'
        for situacao, opcoes in fluxo:
            if situacao == status:
                steps += f'<li><span class="step-{slugify(opcoes[1])} active">{opcoes[0]}</span></li>'
            else:
                steps += f'<li><span class="step-{slugify(opcoes[1])}">{opcoes[0]}</span></li>'
        steps += '</ul>'
        return steps

    def get_ultima_movimentacao(self):
        if self.ultima_solicitacao:
            ultima_manifestacao = self.ultima_solicitacao.ultima_manifestacao()
            if ultima_manifestacao is None:
                return self.ultima_solicitacao
            posicionamento = ultima_manifestacao.posicionamentos.order_by('-id').first()
            return posicionamento or ultima_manifestacao
        return None

    def notificar_acesso(self, user):
        if self.ultima_solicitacao and self.ultima_solicitacao.esperando:
            return self.ultima_solicitacao.notificar_acesso(user)

    def has_changed(self, field_name):
        """
        Método auxiliar para detectar mudanças no campo especificado por field_name
        """
        if not self.pk:
            return False
        old_instance = self.__class__._default_manager.select_for_update().get(pk=self.pk)
        old_value = getattr(old_instance, field_name)
        return getattr(self, field_name) != old_value

    @transaction.atomic()
    def save(self, *args, **kwargs):
        has_changed = self.has_changed('status')
        super().save(*args, **kwargs)
        if has_changed:
            self.recomendacao.handle_status_monitoramentos()


class IndicacaoServidorMonitoramentoQueryset(QuerySet):
    def get_model(self):
        return apps.get_model('auditoria', 'IndicacaoServidorMonitoramento')

    def pendentes(self):
        return self.filter(visualizado=False)

    def concluidas(self):
        return self.filter(tarefa_realizada=True)

    def ativas(self):
        return self.filter(revogada=False, tarefa_realizada=False)


class IndicacaoServidorMonitoramentoManager(models.Manager):
    def get_queryset(self):
        return IndicacaoServidorMonitoramentoQueryset(self.model, using=self._db)

    def pendentes(self):
        return self.get_queryset().pendentes()

    def concluidas(self):
        return self.get_queryset().concluidas()

    def ativas(self):
        return self.get_queryset().ativas()


class IndicacaoServidorMonitoramento(models.Model):
    monitoramento = models.ForeignKey(Monitoramento, on_delete=models.CASCADE, related_name='indicacoes')
    # Dados da indicação
    servidor = models.ForeignKey(Vinculo, on_delete=models.CASCADE, verbose_name='Servidor indicado')
    indicado_por = models.CurrentUserField(verbose_name='Indicado por', related_name='indicacoes_realizadas')
    data_indicacao = models.DateTimeField(auto_now_add=True, verbose_name='Data da indicação')
    instrucoes = models.TextField(verbose_name='Instruções', null=True, blank=True)
    # Dados da revogação
    revogado_por = models.ForeignKeyPlus(Vinculo, verbose_name='Revogado por', related_name='indicacoes_revogadas', null=True, blank=True)
    revogada = models.BooleanField(default=False, verbose_name='Permissão revogada')
    # Campos adicionados
    visualizado = models.BooleanField(default=False, verbose_name='Visualizado pelo servidor')
    data_visualizacao = models.DateTimeField(null=True, blank=True, verbose_name='Data da visualização')
    tarefa_realizada = models.BooleanField(default=False, verbose_name='Tarefa realizada')
    data_realizacao_tarefa = models.DateTimeField(null=True, blank=True, verbose_name='Data da realização da tarefa')

    objects = IndicacaoServidorMonitoramentoManager()

    def __str__(self):
        return f'{self.servidor.nome} - {self.monitoramento.recomendacao}'

    @property
    def ativa(self):
        return not self.revogada and not self.tarefa_realizada

    def pode_concluir(self, user):
        return self.servidor == user.get_vinculo() and not self.tarefa_realizada

    def marcar_como_visualizado(self):
        if not self.visualizado:
            self.visualizado = True
            self.data_visualizacao = get_datetime_now()
            self.save()
            return True
        return False

    def marcar_tarefa_como_realizada(self):
        if not self.tarefa_realizada:
            self.tarefa_realizada = True
            self.data_realizacao_tarefa = get_datetime_now()
            self.save()
            return True
        return False

    def revogar(self, user):
        if not self.revogada:
            self.revogado_por = user.get_vinculo()
            self.revogada = True
            return True
        return False
