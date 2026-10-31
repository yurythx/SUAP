"""Substrato dos testes do ``comum``.

Reproduz, com as factories do ``rh``, a fatia do antigo fixture `suap_data` que estes
testes realmente usam: dois campi, quatro servidores distribuídos entre eles, um
superusuário e um prestador de serviço — todos com a senha ``SENHA``, porque os testes
autenticam de verdade pelo ``client.login``.

A topologia importa e é a mesma do fixture antigo: `servidor_a` e o `admin` no campus A,
`servidor_b` no campus B, `servidor_c` num segundo setor do campus A e `servidor_d` num
segundo setor do campus B. As telas de agendamento de sala decidem permissão por campus,
então juntar todo mundo num campus só apagaria justamente o que elas testam.
"""

import datetime
from types import SimpleNamespace

import pytest

from comum.models import Ocupacao, OcupacaoPrestador
from comum.tests.factories import PrestadorServicoFactory
from rh.tests.factories import PessoaJuridicaFactory, ServidorFactory, SetorFactory

SENHA = '123'


def _ator(servidor):
    """Prepara o servidor para os testes: senha e e-mail pessoal.

    O ``ServidorFactory`` não define senha e estes testes fazem login de verdade. O
    e-mail pessoal também não é decoração: as notificações do agendamento de sala são
    enviadas para o `email_pessoal` do vínculo, então sem ele o `mail.outbox` fica vazio
    e o teste de envio não testa nada.
    """
    user = servidor.get_user()
    user.set_password(SENHA)
    user.save()
    vinculo = servidor.get_vinculo()
    vinculo.email_pessoal = f'{servidor.matricula}@mail.gov'
    vinculo.save(update_fields=['email_pessoal'])
    return servidor


@pytest.fixture
def atores(request, db, sync_permissions):
    """Servidores, admin e prestador do substrato.

    Expõe tudo como atributo da instância de teste (`self.servidor_a`...) quando pedido
    de dentro de uma classe, que é como o `suap_data` era consumido aqui — assim a troca
    nos testes é só o nome no ``usefixtures``.
    """
    setor_campus_a = SetorFactory(sigla='A0')
    setor_a1 = SetorFactory(sigla='A1', superior=setor_campus_a)
    setor_a2 = SetorFactory(sigla='A2', superior=setor_campus_a)
    setor_campus_b = SetorFactory(sigla='B0')
    setor_b1 = SetorFactory(sigla='B1', superior=setor_campus_b)
    setor_b2 = SetorFactory(sigla='B2', superior=setor_campus_b)

    admin = _ator(ServidorFactory(setor=setor_a1))
    user_admin = admin.get_user()
    user_admin.is_superuser = True
    user_admin.is_staff = True
    user_admin.save(update_fields=['is_superuser', 'is_staff'])

    prestador_1 = PrestadorServicoFactory(setor=setor_campus_a)
    user_prestador = prestador_1.get_user()
    user_prestador.set_password(SENHA)
    user_prestador.save()
    # Ocupação ATIVA: é ela que mantém o prestador como não-externo
    # (`PessoaFisica.save` decide `eh_usuarioexterno` por isto).
    OcupacaoPrestador.objects.create(
        prestador=prestador_1,
        ocupacao=Ocupacao.objects.get_or_create(codigo='', descricao='Teste Ocupação')[0],
        empresa=PessoaJuridicaFactory(),
        data_inicio=datetime.date(2010, 1, 1),
        data_fim=datetime.date(2100, 1, 1),
    )

    dados = SimpleNamespace(
        admin=admin,
        prestador_1=prestador_1,
        servidor_a=_ator(ServidorFactory(setor=setor_a1)),
        servidor_b=_ator(ServidorFactory(setor=setor_b1)),
        servidor_c=_ator(ServidorFactory(setor=setor_a2)),
        servidor_d=_ator(ServidorFactory(setor=setor_b2)),
        setor_a0_suap=setor_campus_a,
        setor_a1_suap=setor_a1,
        setor_a2_suap=setor_a2,
        setor_b0_suap=setor_campus_b,
        setor_b1_suap=setor_b1,
        setor_b2_suap=setor_b2,
        campus_a_suap=setor_campus_a.uo,
        campus_b_suap=setor_campus_b.uo,
    )

    if request.instance is not None:
        for nome, valor in vars(dados).items():
            setattr(request.instance, nome, valor)
    return dados
