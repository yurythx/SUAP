from unittest.mock import Mock, patch

from comum.forms import ChangePasswordForm


def test_alteracao_senha_estrangeiro_atualiza_ad_e_senha_local() -> None:
    usuario = Mock(eh_estrangeiro=True)
    usuario.get_vinculo.return_value.get_usuario_ldap.return_value = {'dn': 'CN=20260001'}
    ldap = Mock()
    ldap.has_write_permission.return_value = True
    ldap.change_password.return_value = True
    formulario = ChangePasswordForm(
        data={'password': 'SenhaSegura123', 'password_confirm': 'SenhaSegura123'},
        username='20260001',
    )

    with (
        patch('comum.forms.User.objects.filter') as filtrar_usuario,
        patch('comum.forms.get_ldap_conf', return_value=ldap),
    ):
        filtrar_usuario.return_value.first.return_value = usuario
        assert formulario.is_valid(), formulario.errors

    ldap.change_password.assert_called_once_with('20260001', 'SenhaSegura123')
    usuario.set_password.assert_called_once_with('SenhaSegura123')
    usuario.save.assert_called_once()
