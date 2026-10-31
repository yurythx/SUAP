import pytest
from django.contrib.auth.models import Group

import datetime

from comum.models import Ocupacao, OcupacaoPrestador
from comum.tests.factories import PrestadorServicoFactory
from rh.tests.factories import (
    CargoEmpregoFactory,
    JornadaTrabalhoFactory,
    PessoaJuridicaFactory,
    ServidorFactory,
    SetorFactory,
    SetorSiapeFactory,
    SituacaoFactory,
)

SENHA = '123'


class RHBase:
    """Base reaproveitada por herança pelos testes de RH.

    Monta o substrato mínimo com as factories e o expõe como atributos (`self.servidor_a`,
    `self.setor_a1_suap`, `self.prestador_1`...), no lugar do antigo fixture `suap_data`.
    As subclasses usam essas peças para montar os seus próprios cenários.

    O nome NÃO casa com os padrões de coleta do pytest (`Test*`/`*Test`/`*TestCase`), de
    modo que a base não é coletada como classe de teste — evitando que os testes herdados
    rodem repetidamente em cada subclasse.
    """

    @pytest.fixture(autouse=True)
    def _auto_setup(self, db, sync_permissions):
        # Tabelas-tipo: as mesmas linhas que o `ServidorFactory` usa nas suas sub-factories,
        # expostas aqui porque as subclasses montam servidores extras com elas.
        self.cargo_emprego_a = CargoEmpregoFactory()
        # Dois cargos distintos: o `CargoEmpregoFactory` tem código fixo, e o importador de
        # PCA busca o cargo por código — com um só, metade dos registros era descartada.
        self.cargo_emprego_b = CargoEmpregoFactory(codigo='02', nome='Cargo B')
        self.jornada_trabalho = JornadaTrabalhoFactory()
        self.situacao_ativo_permanente = SituacaoFactory()

        # A1 e B1 são irmãos do mesmo campus: o `setor_b1_suap` entra como setor ADICIONAL
        # de um vínculo, e campus solto mudaria o que os testes exercitam.
        campus = SetorFactory(sigla='CAMPUS')
        self.setor_a1_suap = SetorFactory(sigla='A1', superior=campus)
        self.setor_b1_suap = SetorFactory(sigla='B1', superior=campus)
        self.setor_a1_siape = SetorSiapeFactory(sigla='A1')

        self.servidor_a = self._com_senha(ServidorFactory(setor=self.setor_a1_suap))
        self.servidor_b = self._com_senha(ServidorFactory(setor=self.setor_a1_suap))
        self.servidor_c = self._com_senha(ServidorFactory(setor=self.setor_b1_suap))

        self.pessoa_juridica = PessoaJuridicaFactory()
        self.prestador_1 = PrestadorServicoFactory(setor=self.setor_a1_suap)
        # Ocupação ATIVA: é ela que mantém o prestador como não-externo
        # (`PessoaFisica.save` decide `eh_usuarioexterno` por isto).
        OcupacaoPrestador.objects.create(
            prestador=self.prestador_1,
            ocupacao=Ocupacao.objects.get_or_create(codigo='', descricao='Teste Ocupação')[0],
            empresa=self.pessoa_juridica,
            data_inicio=datetime.date(2010, 1, 1),
            data_fim=datetime.date(2100, 1, 1),
        )

        self.servidor_a.get_user().groups.add(Group.objects.get_or_create(name='Coordenador de Gestão de Pessoas Sistêmico')[0])

    @staticmethod
    def _com_senha(servidor):
        """Os testes herdados autenticam de verdade; o `ServidorFactory` não define senha."""
        user = servidor.get_user()
        user.set_password(SENHA)
        user.save()
        return servidor


class TestServidorView(RHBase):
    """Fluxo: o coordenador de RH visualiza e edita a ficha de um servidor."""

    def test_ver_e_editar_servidor(self, client):
        client.login(username=self.servidor_a.get_user().username, password=SENHA)

        res_ver = client.get(f'/rh/servidor/{self.servidor_a.matricula}/')
        assert res_ver.status_code == 200
        assert self.servidor_a.matricula in res_ver.content.decode()

        res_editar = client.get(f'/admin/rh/servidor/{self.servidor_a.pk:d}/change/')
        assert res_editar.status_code == 200
        assert self.servidor_a.matricula in res_editar.content.decode()
