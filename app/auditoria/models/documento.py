from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db.models import Q
from django.db.models.query import QuerySet

from comum.models import Vinculo
from djtools.db import models
from djtools.utils import get_datetime_now


class DocumentoQueryset(QuerySet):
    def removidos(self):
        return self.exclude(removido_em__isnull=True)

    def nao_removidos(self):
        return self.filter(removido_em__isnull=True)


class DocumentoManager(models.Manager):
    def get_queryset(self):
        return DocumentoQueryset(self.model, using=self._db)

    def removidos(self):
        return self.get_queryset().removidos()

    def nao_removidos(self):
        return self.get_queryset().nao_removidos()


class Documento(models.Model):
    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        null=True,
        limit_choices_to=Q(app_label='documento_eletronico', model='documentotexto')
        | Q(app_label='documento_eletronico', model='documentodigitalizado'),
    )
    object_id = models.PositiveIntegerField(null=True)
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

    objects = DocumentoManager()

    class Meta:
        abstract = True

    def __str__(self) -> str:
        return f'{self.object}'

    @property
    def get_status_display(self):
        return self.object.get_status_display() if self.object.eh_documento_texto else ''

    @property
    def identificador(self):
        if self.object.identificador_numero and self.object.identificador_ano:
            return f'{self.object.identificador_numero}/{self.object.identificador_ano}'
        return self.object.id

    @property
    def documento(self):
        return self.object

    @property
    def removido(self):
        return self.removido_em is not None

    def pode_remover_documento(self, user):
        return not self.removido and self.object.pode_remover_documento(user)

    def adicionar_documento(self, documento, user):
        content_type = ContentType.objects.get_for_model(documento)
        self.content_type = content_type
        self.object_id = documento.id
        self.object = documento
        self.adicionado_por = user.get_vinculo()

    def remover_documento(self, user):
        self.removido_por = user.get_vinculo()
        self.removido_em = get_datetime_now()

    def __getattr__(self, name):
        try:
            return super().__getattr__(name)
        except AttributeError:
            return getattr(self.object, name)
