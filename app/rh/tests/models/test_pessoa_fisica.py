from comum.models import OcupacaoPrestador
from rh.models import PessoaFisica
from rh.tests.test_base import RHBase


class PessoaFisicaTest(RHBase):
    def test_deve_manter_prestador_com_ocupacao_ativa_como_nao_externo(self):
        pessoa_fisica = self.prestador_1.pessoa_fisica

        pessoa_fisica.save()

        pessoa_fisica.refresh_from_db()

        assert pessoa_fisica.eh_prestador is True
        assert pessoa_fisica.eh_usuarioexterno is False

    def test_deve_marcar_prestador_sem_ocupacao_ativa_como_externo(self):
        pessoa_fisica = self.prestador_1.pessoa_fisica
        OcupacaoPrestador.objects.filter(prestador=self.prestador_1).delete()

        pessoa_fisica.save()

        pessoa_fisica.refresh_from_db()

        assert pessoa_fisica.eh_prestador is True
        assert pessoa_fisica.eh_usuarioexterno is True

    def test_deve_manter_nao_prestador_como_nao_externo(self):
        pessoa_fisica = self.servidor_a.pessoa_fisica

        pessoa_fisica.save()

        pessoa_fisica.refresh_from_db()

        assert PessoaFisica.objects.filter(pk=pessoa_fisica.pk, eh_prestador=False, eh_usuarioexterno=False).exists()
