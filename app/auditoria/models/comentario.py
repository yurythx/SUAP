from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType

from djtools.db import models


class Comentario(models.ModelPlus):
    texto = models.TextField(verbose_name='Comentário', null=False, blank=False)
    cadastrado_por = models.CurrentUserField(verbose_name='Cadastrado por', related_name='%(app_label)s_%(class)s_cadastrado_por')
    criado_em = models.DateTimeFieldPlus(verbose_name='Data de Inclusão', auto_now_add=True, editable=False)
    modificado_em = models.DateTimeFieldPlus(auto_now=True, verbose_name='Modificada em')
    desconsiderado = models.BooleanField(default=False)
    #
    resposta = models.ForeignKey('self', null=True, blank=True, on_delete=models.CASCADE)

    # Fk Genérica para uso por qualquer modelo
    content_type = models.ForeignKeyPlus(ContentType, on_delete=models.CASCADE, related_name='%(app_label)s_%(class)s_content_type')
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey('content_type', 'object_id')

    class Meta:
        verbose_name = 'Comentário'
        verbose_name_plural = 'Comentários'
        ordering = ('id',)

    def ultimo(self):
        qs = self.content_object.comentarios
        return not qs.filter(pk__gt=self.pk).exists()

    def desconsiderar(self):
        self.desconsiderado = True

    def pode_editar(self, user):
        return self.cadastrado_por == user

    def pode_excluir(self, user):
        return self.pode_editar(user) and self.ultimo()

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if hasattr(self.content_object, 'comentario_post_save'):
            self.content_object.comentario_post_save(self)

    def __str__(self):
        return f'{self.cadastrado_por} - {self.texto}'
