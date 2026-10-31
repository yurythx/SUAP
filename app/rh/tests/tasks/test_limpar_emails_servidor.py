from io import StringIO

import pytest
from django.core.management import CommandError, call_command

from comum.models import Configuracao, User
from rh.models import Servidor
from rh.tests.factories import ServidorFactory


class TestLimparEmailsServidor:
    @pytest.fixture(autouse=True)
    def _setup(self, db, sync_permissions):
        """O servidor cujos e-mails o comando limpa. Vinha do `admin` do `light_data`."""
        self.admin = ServidorFactory()

    def _configurar_dominios(self, valor):
        Configuracao.objects.update_or_create(app='comum', chave='dominios_institucionais', defaults={'valor': valor})
        Configuracao.clear_cache()

    def _definir_emails(self, email_institucional):
        Servidor.objects.filter(pk=self.admin.pk).update(
            email_institucional=email_institucional,
            email_academico='admin@academico.ifrn.edu.br',
            email_google_classroom='admin@classroom.ifrn.edu.br',
        )
        self.admin.vinculos.update(email_pessoal='admin.pessoal@gmail.com')
        User.objects.filter(username=self.admin.matricula).update(email=email_institucional)

    def _email_pessoal(self):
        return self.admin.get_vinculo().email_pessoal

    def _rodar(self, *args):
        saida = StringIO()
        call_command('limpar_emails_servidor', *args, '--no-ldap', stdout=saida, stderr=StringIO())
        return saida.getvalue()

    def test_exige_matricula_ou_all(self):
        with pytest.raises(CommandError):
            self._rodar()

    def test_all_exige_dominios_configurados(self):
        self._configurar_dominios('')
        with pytest.raises(CommandError):
            self._rodar('--all')

    def test_all_seleciona_apenas_dominio_de_terceiros(self):
        self._configurar_dominios('@ifrn.edu.br')
        self._definir_emails('servidor.cedido@ifpb.edu.br')
        assert self.admin.matricula in self._rodar('--all', '--dry-run')

    def test_all_ignora_email_do_dominio_proprio(self):
        self._configurar_dominios('@ifrn.edu.br')
        self._definir_emails('admin@ifrn.edu.br')
        assert self.admin.matricula not in self._rodar('--all', '--dry-run')

    def test_limpa_institucional_preservando_academico_e_google(self):
        self._configurar_dominios('@ifrn.edu.br')
        self._definir_emails('servidor.cedido@ifpb.edu.br')

        self._rodar('--all')

        servidor = Servidor.objects.get(pk=self.admin.pk)
        assert servidor.email_institucional == ''
        assert servidor.email_academico == 'admin@academico.ifrn.edu.br'
        assert servidor.email_google_classroom == 'admin@classroom.ifrn.edu.br'
        assert User.objects.get(username=self.admin.matricula).email == ''

    def test_preserva_email_pessoal_sem_a_flag(self):
        """É o e-mail de recuperação de senha do servidor: só sai com --secundario."""
        self._configurar_dominios('@ifrn.edu.br')
        self._definir_emails('servidor.cedido@ifpb.edu.br')

        self._rodar('--all')

        assert self._email_pessoal() == 'admin.pessoal@gmail.com'

    def test_secundario_limpa_o_email_pessoal_do_vinculo(self):
        self._configurar_dominios('@ifrn.edu.br')
        self._definir_emails('servidor.cedido@ifpb.edu.br')

        self._rodar('--all', '--secundario')

        assert self._email_pessoal() == ''
