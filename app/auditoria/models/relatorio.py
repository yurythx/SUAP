from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db.models import Q
from django.urls import reverse_lazy

from comum.models import Ano, Vinculo
from djtools.db import models
from djtools.utils import get_datetime_now
from rh.models import Setor

from ..papeis import eh_auditor
from .acao import Acao
from .nucleo import NucleoAuditoria


class Relatorio(models.ModelPlus):
    SEARCH_FIELDS = ['numero', 'ano__ano', 'nucleo__nome']
    #
    numero = models.IntegerField(verbose_name='Número do relatório', blank=False, null=False)
    ano = models.ForeignKeyPlus(Ano, verbose_name='Ano do relatório', null=False, blank=False, on_delete=models.CASCADE)
    ano_paint = models.ForeignKeyPlus(
        Ano, verbose_name='Ano/Paint', null=False, blank=False, on_delete=models.CASCADE, related_name='%(app_label)s_%(class)s_paint'
    )
    # Dados da Ação
    acao = models.ForeignKey(Acao, verbose_name='Ação', on_delete=models.CASCADE, related_name='relatorios', null=False, blank=False)
    #
    nucleo = models.ForeignKey(NucleoAuditoria, verbose_name='Núcleo de auditoria', null=False, blank=False, on_delete=models.CASCADE)
    equipe = models.ManyToManyFieldPlus(Vinculo, verbose_name='Equipe de trabalho', related_name='%(app_label)s_%(class)s_equipe')
    unidades_auditadas = models.ManyToManyFieldPlus(Setor, verbose_name='Unidades auditadas', related_name='%(app_label)s_%(class)s_unidades')
    # Período  de abrangência do relatório
    data_inicio = models.DateField(verbose_name='Data inicial', null=False, blank=False)
    data_fim = models.DateField(verbose_name='Data final', null=False, blank=False)
    #
    modificado_em = models.DateTimeField(auto_now=True, verbose_name='Modificado em')

    class Meta:
        verbose_name = 'Relatório'
        verbose_name_plural = 'Relatórios'
        unique_together = ('numero', 'ano', 'nucleo')

    def __str__(self) -> str:
        return f'{self.identificador}'

    def get_absolute_url(self):
        return reverse_lazy('auditoria:visualizar_relatorio', kwargs={'relatorio_id': self.pk})

    @property
    def identificador(self):
        return f'{self.numero}/{self.ano} - {self.nucleo}'

    def pode_editar(self, user):
        return eh_auditor(user)

    def pode_remover_documento(self, user):
        return eh_auditor(user)

    def adicionar_documento(self, documento, user):
        content_type = ContentType.objects.get_for_model(documento)
        RelatorioDocumento.objects.get_or_create(
            relatorio=self, object_id=documento.id, content_type=content_type, defaults={'incluido_por': user.get_vinculo(), 'object': documento}
        )

    def remover_documento(self, documento, user):
        content_type = ContentType.objects.get_for_model(documento)
        relatorio_documento = RelatorioDocumento.objects.filter(content_type=content_type, object_id=documento.id).first()
        if relatorio_documento:
            relatorio_documento.remover_documento(user)
            relatorio_documento.save()

    def _verificar_unidades_removidas(self, unidades):
        # Verifica se alguma recomendação associada tem uma unidade removida
        for recomendacao in self.recomendacoes.all():
            if any(unidade in unidades for unidade in recomendacao.unidades.all()):
                raise ValueError(f'Não é possível remover a unidade porque está associada à recomendação {recomendacao}.')

    def save(self, *args, **kwargs):
        if self.pk:  # Verifica se o relatório já existe
            old_unidades = set(Relatorio.objects.get(pk=self.pk).unidades_auditadas.all())
            new_unidades = set(self.unidades_auditadas.all())
            removed_unidades = old_unidades - new_unidades
            if removed_unidades:
                self._verificar_unidades_removidas(removed_unidades)
        #
        super().save(*args, **kwargs)


class RelatorioDocumentoQueryset(models.QuerySet):
    def removidos(self):
        return self.filter(removido_em__isnull=False)


class RelatorioDocumentoManager(models.Manager):
    def get_queryset(self):
        return RelatorioDocumentoQueryset(self.model, using=self._db)

    def removidos(self):
        return self.get_queryset().removidos()


class RelatorioDocumento(models.ModelPlus):
    relatorio = models.ForeignKey(Relatorio, on_delete=models.CASCADE, related_name='documentos')
    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        limit_choices_to=Q(app_label='documento_eletronico', model='documentotexto')
        | Q(app_label='documento_eletronico', model='documentodigitalizado'),
    )
    object_id = models.PositiveIntegerField()
    object = GenericForeignKey('content_type', 'object_id')
    # Dado da adição
    incluido_por = models.ForeignKey(Vinculo, verbose_name='Criado por', on_delete=models.CASCADE, related_name='%(app_label)s_%(class)s_criado_por')
    incluido_em = models.DateTimeField(auto_now_add=True, verbose_name='Criado em')
    # Dados da remoção
    removido_em = models.DateTimeField(verbose_name='Removido em', null=True, blank=True)
    removido_por = models.ForeignKey(
        Vinculo, verbose_name='Removido por', on_delete=models.CASCADE, null=True, blank=True, related_name='%(app_label)s_%(class)s_removido_por'
    )
    justificativa_remocao = models.CharFieldPlus(verbose_name='Justificava de Remoção', null=True, blank=True)

    objects = RelatorioDocumentoManager()

    @property
    def get_status_display(self):
        return self.object.get_status_display() if self.object.eh_documento_texto else ''

    @property
    def identificador(self):
        return f'{self.object.identificador_numero}/{self.object.identificador_ano}'

    @property
    def documento(self):
        return self.object

    @property
    def removido(self):
        return self.removido_em is not None

    def get_absolute_url(self):
        return reverse_lazy('auditoria:visualizar_relatorio', kwargs={'relatorio_id': self.pk})

    def pode_editar_informacoes(self, user):
        if self.documento.eh_documento_texto:
            return False
        return self.pode_remover_documento(user)

    def pode_remover_documento(self, user):
        return not self.removido and self.relatorio.pode_remover_documento(user)

    def adicionar_documento(self, documento, user):
        content_type = ContentType.objects.get_for_model(documento)
        self.content_type = content_type
        self.object_id = documento.id
        self.object = documento
        self.adicionado_por = user.get_vinculo()
        self.save()

    def remover_documento(self, user):
        self.removido_por = user.get_vinculo()
        self.removido_em = get_datetime_now()

    def __getattr__(self, name):
        try:
            return super().__getattr__(name)
        except AttributeError:
            return getattr(self.object, name)
