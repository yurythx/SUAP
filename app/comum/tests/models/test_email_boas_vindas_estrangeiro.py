from types import SimpleNamespace
from unittest.mock import patch

from comum.models import User


def test_email_boas_vindas_estrangeiro_orienta_cadastro_de_senha_local() -> None:
    usuario = User(username='20260001', eh_estrangeiro=True, eh_usuarioexterno=False)
    pessoa = SimpleNamespace(email='', nome='Aluno Estrangeiro')
    vinculo = SimpleNamespace(email_pessoal='', email_notificacao='aluno@example.org')

    with (
        patch.object(usuario, 'get_profile', return_value=pessoa),
        patch.object(usuario, 'get_vinculo', return_value=vinculo),
        patch('comum.models.Configuracao.get_valor_por_chave', return_value='IFRN'),
        patch('comum.models.render_to_string', return_value='mensagem') as renderizar,
        patch('comum.models.send_mail') as enviar,
    ):
        usuario.enviar_email_boas_vindas()

    contexto = renderizar.call_args.args[1]
    assert contexto['eh_estrangeiro'] is True
    assert contexto['login_url'].endswith('/comum/solicitar_trocar_senha/')
    enviar.assert_called_once()
