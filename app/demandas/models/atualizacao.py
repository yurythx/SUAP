from django.conf import settings
from django.contrib.auth.models import Group
from django.contrib.contenttypes.models import ContentType
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.urls import reverse

from comum.models import Comentario, User
from djtools.db import models
from djtools.db.models import ModelPlus
from djtools.utils import send_notification

from demandas.utils import Notificar


class Atualizacao(ModelPlus):
    FUNCIONALIDADE = 'Funcionalidade'
    MANUTENCAO = 'Manutenção'
    BUG = 'Bug'
    TIPO_CHOICES = ((FUNCIONALIDADE, 'Funcionalidade'), (MANUTENCAO, 'Manutenção'), (BUG, 'Bug'))

    descricao = models.CharFieldPlus('Título')
    detalhamento = models.TextField('Detalhamento', blank=True, null=True)
    tipo = models.CharFieldPlus(choices=TIPO_CHOICES)
    tags = models.ManyToManyField('demandas.Tag', verbose_name='Tags')
    grupos = models.ManyToManyField(Group, verbose_name='Grupos Envolvidos')
    data = models.DateFieldPlus('Data de Implantação')
    demanda = models.ForeignKeyPlus('demandas.Demanda', verbose_name='Demanda Vinculada', null=True, blank=True)
    responsaveis = models.ManyToManyField(
        User,
        related_name='atualizacao_responsaveis_set',
        verbose_name='Responsáveis',
        help_text='Vincule usuários desenvolvedores desta atualização.',
    )

    class Meta:
        verbose_name = 'Atualização'
        verbose_name_plural = 'Atualizações'
        ordering = ['-data']

    def __str__(self):
        return self.descricao

    def get_absolute_url(self):
        return reverse('demanda_atualizacao', kwargs={'atualizacao_id': self.id})

    def save(self, *args, **kwargs):
        pk = self.pk
        super().save(*args, **kwargs)
        if pk is None:
            self.notificar_interessados()

    def get_tags(self):
        lista = []
        for tag in self.tags.all():
            lista.append(tag.nome)
        return lista

    def notificar_interessados(self):
        for grupo in self.grupos.all():
            [self.notificar(user) for user in grupo.user_set.all()]

    def notificar(self, user):
        send_notification(
            'Atualização do Sistema',
            'Atualização: <b>{}</b>\n\n<p>{}</p>'.format(self.descricao, self.detalhamento or ''),
            settings.DEFAULT_FROM_EMAIL,
            [user.get_vinculo()],
            categoria='Atualização do Sistema',
        )


def altera_permissao_apos_salvar_outros_interessados(sender, **kwargs):
    group = Group.objects.get(name='Visualizador de Demandas')

    visualizador_demandas_sem_permissao = User.objects.filter(demanda_interessados_set__isnull=False).exclude(groups=group)

    for user in visualizador_demandas_sem_permissao:
        user.groups.add(group)


@receiver(post_save, sender=Comentario, dispatch_uid='enviar_email_ao_comentar')
def enviar_email_ao_comentar(sender, instance, **kwargs):
    if instance.content_type in ContentType.objects.filter(app_label='demandas', model='sugestaomelhoria'):
        sugestao_melhoria = instance.content_object
        comentario = instance

        Notificar.novo_comentario_em_sugestao_melhoria(sugestao_melhoria, comentario)

        # sugestao atualizada
        sugestao_melhoria.save()

        user_que_comentou_eh_demandante_da_sugestao = comentario.cadastrado_por in sugestao_melhoria.demandantes
        if user_que_comentou_eh_demandante_da_sugestao:
            if sugestao_melhoria.is_pendente and not sugestao_melhoria.responsavel:
                try:
                    sugestao_melhoria.atribuir_responsavel(comentario.cadastrado_por)
                except Exception:
                    pass

    elif instance.content_type in ContentType.objects.filter(app_label='demandas'):
        if not instance.texto.startswith('Etapa da demanda alterada para'):
            if not instance.desconsiderado:
                Notificar.novo_comentario(instance)
