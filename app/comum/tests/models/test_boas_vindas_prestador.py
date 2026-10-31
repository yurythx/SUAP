"""O e-mail de boas-vindas do usuário externo precisa sair com destinatário.

`enviar_email_boas_vindas()` resolve o destinatário por `vinculo.email_pessoal`; se o
cadastro só gravar esse campo depois do envio, o guard `if email:` derruba a mensagem em
silêncio e o usuário nunca recebe as instruções de primeiro acesso.
"""

from unittest.mock import patch

import pytest
from comum.models import PrestadorServico


@pytest.mark.django_db
class TestBoasVindasPrestador:
    def _cadastrar(self, **pessoa_fisica):
        dados = {
            'pessoa_fisica': {
                'cpf': '731.731.731-47',
                'nome_registro': 'Fulano Externo',
                'email_secundario': 'fulano@externo.com',
                'email': 'fulano@externo.com',
                **pessoa_fisica,
            },
            'ativo': True,
        }
        with patch('comum.models.send_mail') as send_mail, patch('comum.models.sync_ldap_user'), patch('comum.models.sync_ldap_setor'):
            retorno = PrestadorServico.update_or_create(dados)
        return retorno['prestador'], send_mail

    def test_envia_boas_vindas_para_o_email_informado(self):
        prestador, send_mail = self._cadastrar()
        assert send_mail.called, 'e-mail de boas-vindas não foi enviado'
        assert send_mail.call_args.args[-1] == ['fulano@externo.com']
        assert prestador.get_vinculo().email_pessoal == 'fulano@externo.com'

    def test_sem_email_nao_envia(self):
        _, send_mail = self._cadastrar(email_secundario='', email='')
        assert not send_mail.called
