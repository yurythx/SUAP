"""Recuperação de senha usa SOMENTE o email_pessoal do vínculo — nunca o institucional.

`Vinculo.email_notificacao` é property institucional-primeiro (padrão das notificações
gerais); recuperação de senha/2FA NÃO pode usar o institucional (mesma senha do SUAP).
`TrocarSenha.save()` é o único caminho de recuperação testável no nível de model.
"""

import pytest
from comum.models import TrocarSenha
from rh.tests.test_base import RHBase


@pytest.mark.usefixtures('atores')
class TestRecuperacaoSenhaEmailPessoal(RHBase):
    def _preparar(self, email_pessoal: str, email_institucional: str) -> str:
        self.servidor_a.email_institucional = email_institucional
        self.servidor_a.save(update_fields=['email_institucional'])
        vinculo = self.servidor_a.get_vinculo()
        vinculo.email_pessoal = email_pessoal
        vinculo.save(update_fields=['email_pessoal'])
        return self.servidor_a.get_user().username

    def test_usa_email_pessoal_ignorando_institucional(self):
        username = self._preparar(email_pessoal='pessoal@externo.com', email_institucional='servidor@ifrn.edu.br')
        obj = TrocarSenha(username=username)
        obj.save()
        assert obj.email == 'pessoal@externo.com'

    def test_sem_email_pessoal_levanta_mesmo_com_institucional(self):
        username = self._preparar(email_pessoal='', email_institucional='servidor@ifrn.edu.br')
        with pytest.raises(ValueError, match='sem email alternativo'):
            TrocarSenha(username=username).save()
