from django.apps import apps

from djtools.management.commands import BaseCommandPlus

User = apps.get_model('comum', 'User')
UsuarioGrupoSetor = apps.get_model('comum', 'UsuarioGrupoSetor')


class Command(BaseCommandPlus):
    help = 'Remove, em lote, os grupos dos usuários inativos.'

    def handle(self, *args: object, **options: object) -> None:
        usuarios_inativos = User.objects.filter(is_active=False)
        UsuarioGrupoSetor.objects.filter(usuario_grupo__user__in=usuarios_inativos).delete()
        User.groups.through.objects.filter(user__in=usuarios_inativos).delete()
