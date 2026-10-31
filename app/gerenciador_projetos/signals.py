from django.db.models.signals import m2m_changed
from django.dispatch import receiver

from comum.models import User
from gerenciador_projetos.models import Projeto, Tarefa
from gerenciador_projetos.utils import Notificar


@receiver(m2m_changed, sender=Tarefa.atribuido_a.through)
def tarefa_atribuido_a_changed(sender, instance, action, pk_set, **kwargs):
    if action == 'post_add':
        # Recupera os atendentes adicionados recentemente
        atendentes = User.objects.filter(pk__in=pk_set)
        for user in atendentes:
            Notificar.usuario_atribuido_a_tarefa(instance, user)


@receiver(m2m_changed, sender=Projeto.membros.through)
def projeto_membro_atribuido_changed(sender, instance, action, pk_set, **kwargs):
    if action == 'post_add':
        # Recupera os usuarios adicionados recentemente
        usuarios = User.objects.filter(pk__in=pk_set)
        for usuario in usuarios:
            Notificar.usuario_vinculado_a_projeto(instance, usuario, 'membro')


@receiver(m2m_changed, sender=Projeto.interessados.through)
def projeto_interessado_atribuido_changed(sender, instance, action, pk_set, **kwargs):
    if action == 'post_add':
        # Recupera os usuarios adicionados recentemente
        usuarios = User.objects.filter(pk__in=pk_set)
        for usuario in usuarios:
            Notificar.usuario_vinculado_a_projeto(instance, usuario, 'interessado')


@receiver(m2m_changed, sender=Projeto.gerentes.through)
def projeto_geremte_atribuido_changed(sender, instance, action, pk_set, **kwargs):
    if action == 'post_add':
        # Recupera os usuarios adicionados recentemente
        usuarios = User.objects.filter(pk__in=pk_set)
        for usuario in usuarios:
            Notificar.usuario_vinculado_a_projeto(instance, usuario, 'gerente')
