"""Testa que as properties de chokepoint em AbstractRelacionamento
roteiam os campos triviais para o VÍNCULO do papel, não para pessoa_fisica.

Tasks S1.1 e S2.1 do plano docs/superpowers/plans/2026-07-02-migrar-callsites-campos-vinculo.md.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from django.conf import settings

from comum.models import PovoIndigena, Raca
from rh.tests.test_base import RHBase

DEFAULT_FOTO = '/static/comum/img/default.jpg'


class TestVinculoPropertiesPapel(RHBase):
    """Servidor.raca/povo_indigena/sistema_origem/setores_adicionais devem
    ler do VÍNCULO do papel, não de pessoa_fisica via __getattr__.
    """

    @pytest.fixture(autouse=True)
    def _setup_vinculo_campos(self):
        self.raca_obj = Raca.objects.create(descricao='Parda-Teste', codigo_siape=99)
        self.povo_obj = PovoIndigena.objects.create(nome='Povo-Teste', codigo_educacenso='999')
        self.vinculo = self.servidor_a.get_vinculo()
        self.vinculo.raca = self.raca_obj
        self.vinculo.povo_indigena = self.povo_obj
        self.vinculo.sistema_origem = 'SIAPE-TESTE'
        self.vinculo.save()
        # M2M add é imediato — sem save() adicional
        self.vinculo.setores_adicionais.add(self.setor_b1_suap)

    def test_raca_le_do_vinculo(self):
        assert self.servidor_a.raca == self.raca_obj

    def test_povo_indigena_le_do_vinculo(self):
        assert self.servidor_a.povo_indigena == self.povo_obj

    def test_sistema_origem_le_do_vinculo(self):
        assert self.servidor_a.sistema_origem == 'SIAPE-TESTE'

    def test_setores_adicionais_le_do_vinculo(self):
        assert set(self.servidor_a.setores_adicionais.all()) == {self.setor_b1_suap}


class TestFotoVinculo(RHBase):
    """S2.1 — Vinculo.get_foto_*_url e delegadores no papel (AbstractRelacionamento).

    Servidor.foto/get_foto_*_url deve rotear pelo VÍNCULO do papel.
    """

    @pytest.fixture(autouse=True)
    def _setup_foto(self):
        self.vinculo = self.servidor_a.get_vinculo()
        # Seta foto como string simples — ImageWithThumbsField aceita path direto em testes
        self.vinculo.foto = 'fotos/1.jpg'
        self.vinculo.save()

    def test_foto_sem_foto_retorna_default(self):
        """Vínculo sem foto → get_foto_url() retorna default."""
        v = self.servidor_b.get_vinculo()
        v.foto = None
        v.save()
        assert v.get_foto_url() == DEFAULT_FOTO
        assert v.get_foto_75x100_url() == DEFAULT_FOTO
        assert v.get_foto_150x200_url() == DEFAULT_FOTO

    def test_servidor_foto_le_do_vinculo(self):
        assert self.servidor_a.foto == self.vinculo.foto

    def test_vinculo_get_foto_url_com_foto(self):
        url = self.vinculo.get_foto_url()
        assert url != DEFAULT_FOTO

    def test_vinculo_get_foto_75x100_url_com_foto(self):
        url = self.vinculo.get_foto_75x100_url()
        assert url != DEFAULT_FOTO

    def test_vinculo_get_foto_150x200_url_com_foto(self):
        url = self.vinculo.get_foto_150x200_url()
        assert url != DEFAULT_FOTO

    def test_servidor_get_foto_75x100_url_delega_vinculo(self):
        assert self.servidor_a.get_foto_75x100_url() == self.vinculo.get_foto_75x100_url()

    def test_servidor_get_foto_150x200_url_delega_vinculo(self):
        assert self.servidor_a.get_foto_150x200_url() == self.vinculo.get_foto_150x200_url()

    def test_servidor_get_foto_url_delega_vinculo(self):
        assert self.servidor_a.get_foto_url() == self.vinculo.get_foto_url()

    def test_url_publica_usa_uuid_e_o_view_resolve(self, client):
        """A URL pública é resolvível: get_url_publica() lê Vinculo.uuid (campo, não método)
        e djtools.views.arquivo_uuid consegue buscar o vínculo por esse uuid.
        """
        path = f'/djtools/arquivo/comum/vinculo/{self.vinculo.uuid}/foto/75x100/'
        assert self.servidor_a.get_foto_75x100_url_publica() == f'{settings.SITE_URL}{path}'
        # 302 para o storage; 403 significaria que a view não achou o vínculo pelo uuid
        assert client.get(path).status_code == 302


class TestFotoVinculoAluno:
    """S2.2 — Vinculo.get_foto_*_url delega ao relacionamento quando eh_aluno().

    Usa mock leve: sem DB, sem substrato.
    """

    def test_vinculo_aluno_get_foto_75x100_url_usa_foto_do_aluno(self):
        """Vínculo de aluno retorna foto do Aluno, não vinculo.foto (que seria None)."""
        url_aluno = '/media/professores/75x100_1.jpg'
        aluno_mock = MagicMock()
        aluno_mock.get_foto_75x100_url.return_value = url_aluno

        from comum.models import Vinculo

        v = MagicMock(spec=Vinculo)
        v.eh_aluno.return_value = True
        v.relacionamento = aluno_mock
        v.foto = None
        # chama o método real passando v como self
        result = Vinculo.get_foto_75x100_url(v)
        assert result == url_aluno
        assert result != DEFAULT_FOTO

    def test_vinculo_aluno_get_foto_150x200_url_usa_foto_do_aluno(self):
        url_aluno = '/media/professores/150x200_1.jpg'
        aluno_mock = MagicMock()
        aluno_mock.get_foto_150x200_url.return_value = url_aluno

        from comum.models import Vinculo

        v = MagicMock(spec=Vinculo)
        v.eh_aluno.return_value = True
        v.relacionamento = aluno_mock
        v.foto = None
        assert Vinculo.get_foto_150x200_url(v) == url_aluno

    def test_vinculo_aluno_get_foto_url_usa_foto_do_aluno(self):
        url_aluno = '/media/professores/75x100_1.jpg'
        aluno_mock = MagicMock()
        aluno_mock.get_foto_75x100_url.return_value = url_aluno

        from comum.models import Vinculo

        v = MagicMock(spec=Vinculo)
        v.eh_aluno.return_value = True
        v.relacionamento = aluno_mock
        v.foto = None
        assert Vinculo.get_foto_url(v) == url_aluno


# --- S3.1: email_notificacao property DERIVADA (institucional do papel, senão email_pessoal) ---


class TestEmailNotificacaoS31(RHBase):
    """S3.1 — email_notificacao virou property derivada: retorna o e-mail institucional
    do papel e, na ausência dele, o email_pessoal do vínculo (não é mais campo armazenado).
    """

    def test_property_prioriza_institucional(self):
        """Com institucional no papel, email_notificacao retorna o institucional."""
        vinculo = self.servidor_a.get_vinculo()
        vinculo.relacionamento.email_institucional = 'inst@ifrn.edu.br'
        vinculo.email_pessoal = 'pessoal@x'
        assert vinculo.email_notificacao == 'inst@ifrn.edu.br'

    def test_property_fallback_para_email_pessoal(self):
        """Sem institucional, email_notificacao cai para o email_pessoal do vínculo."""
        vinculo = self.servidor_a.get_vinculo()
        vinculo.relacionamento.email_institucional = ''
        vinculo.email_pessoal = 'pessoal@x'
        assert vinculo.email_notificacao == 'pessoal@x'

    def test_prestador_sem_institucional_usa_email_pessoal(self):
        """Prestador sem institucional: email_notificacao cai para email_pessoal do vínculo."""
        vinculo_p = self.prestador_1.get_vinculo()
        vinculo_p.email_pessoal = 'novo_prestador@x'
        assert vinculo_p.email_notificacao == 'novo_prestador@x'


# --- S4.1: email_pessoal property (campo do vínculo) + resolver email_notificacao por papel ----------


class TestEmailPessoalS41(RHBase):
    """S4.1 — property email_pessoal lê o CAMPO do vínculo; email_notificacao (resolvedor
    único que substituiu get_email) roteia pelo papel: institucional-first, senão email_pessoal.
    """

    @pytest.fixture(autouse=True)
    def _setup_email_pessoal(self):
        self.vinculo = self.servidor_a.get_vinculo()
        # Valor discriminatório: diferente do pf.email ('servidor.a@mail.gov')
        self.vinculo.email_pessoal = 'pessoal_vinculo@x'
        self.vinculo.save()

    def test_property_email_pessoal_le_campo_vinculo(self):
        """servidor.email_pessoal == vinculo.email_pessoal (campo), não pf.email."""
        assert self.servidor_a.email_pessoal == 'pessoal_vinculo@x'

    def test_servidor_sem_institucional_usa_email_pessoal(self):
        """Servidor sem e-mails institucionais: email_notificacao usa email_pessoal do vínculo."""
        vinculo = self.servidor_a.get_vinculo()
        vinculo.relacionamento.email_institucional = ''
        vinculo.relacionamento.email_academico = ''
        vinculo.relacionamento.email_google_classroom = ''
        assert vinculo.email_notificacao == 'pessoal_vinculo@x'

    def test_aluno_sem_institucional_usa_email_pessoal(self):
        """Aluno (via mock): sem e-mails institucionais, email_notificacao usa email_pessoal."""
        from unittest.mock import MagicMock
        from comum.models import Vinculo

        aluno_mock = MagicMock(email_institucional='', email_academico='', email_google_classroom='', email='')
        v = MagicMock(spec=Vinculo, email_pessoal='aluno_vinculo@x', relacionamento=aluno_mock)
        assert Vinculo.email_notificacao.fget(v) == 'aluno_vinculo@x'

    def test_pj_sem_email_proprio_usa_email_pessoal(self):
        """PJ sem e-mail próprio: email_notificacao cai para email_pessoal do vínculo."""
        vinculo_pj = self.pessoa_juridica.get_vinculo()
        vinculo_pj.relacionamento.email = ''
        vinculo_pj.email_pessoal = 'pj_vinculo@x'
        assert vinculo_pj.email_notificacao == 'pj_vinculo@x'


class TestUserEmailInstitucional(RHBase):
    """user_post_save espelha o e-mail do vínculo em User.email, que é lido pelas
    notificações gerais (estagios, api) — logo precisa ser institucional-primeiro,
    a mesma escolha que o comando sync_emails grava.
    """

    def test_user_email_recebe_o_institucional(self):
        self.servidor_a.email_institucional = 'inst@ifrn.edu.br'
        vinculo = self.servidor_a.get_vinculo()
        vinculo.email_pessoal = 'pessoal@externo.com'
        vinculo.save(update_fields=['email_pessoal'])
        self.servidor_a.save()  # dispara user_post_save
        user = self.servidor_a.get_user()
        user.refresh_from_db()
        assert user.email == 'inst@ifrn.edu.br'
