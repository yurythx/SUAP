from unittest.mock import MagicMock, patch

from comum.management.commands.remover_grupos_usuarios_inativos import Command


def test_remove_grupos_e_vinculos_setoriais_em_lote():
    usuarios_inativos = MagicMock()

    with (
        patch('comum.management.commands.remover_grupos_usuarios_inativos.User') as User,
        patch('comum.management.commands.remover_grupos_usuarios_inativos.UsuarioGrupoSetor') as UsuarioGrupoSetor,
    ):
        User.objects.filter.return_value = usuarios_inativos

        Command().handle()

        User.objects.filter.assert_called_once_with(is_active=False)
        UsuarioGrupoSetor.objects.filter.assert_called_once_with(usuario_grupo__user__in=usuarios_inativos)
        UsuarioGrupoSetor.objects.filter.return_value.delete.assert_called_once_with()
        User.groups.through.objects.filter.assert_called_once_with(user__in=usuarios_inativos)
        User.groups.through.objects.filter.return_value.delete.assert_called_once_with()
