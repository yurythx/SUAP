from types import SimpleNamespace

import pytest
from django.db import connection

from comum.models import Configuracao, Municipio, Ocupacao, Vinculo
from comum.tests.seed_academico import seed_academico
from rh.models import Pessoa, TipoUnidadeOrganizacional, UnidadeOrganizacional
from rh.tests.factories import ServidorFactory, SetorFactory

DB_MODULE_PREFIXES = ('edu.tests._suap_edu_legacy',)

DB_MODULES = {
    'edu.tests.test_suap_edu_legacy_base',
}

SENHA = '123'
SIGLA_REITORIA_EDU = 'RE-EDU'


def _requires_implicit_db(module_name):
    return module_name in DB_MODULES or module_name.startswith(DB_MODULE_PREFIXES)


@pytest.fixture(autouse=True)
def auto_db(request):
    module = getattr(request.node, 'module', None)
    module_name = module.__name__ if module else ''
    if _requires_implicit_db(module_name):
        request.getfixturevalue('db')


def _desalinhar_pessoa_de_vinculo() -> None:
    """Põe a sequência de `Pessoa` mil ids à frente da de `Vinculo`.

    Num banco novo cada servidor cria pessoa e vínculo em sequência, e os dois ids andam
    juntos: um POST que mande `vinculo.pessoa.pk` onde o form espera `vinculo.pk` passa
    por coincidência isolado e só quebra sob xdist, quando outro módulo já consumiu a
    sequência de um e não a do outro. Desalinhando aqui, a troca de id falha sempre.
    """
    with connection.cursor() as cursor:
        cursor.execute(
            'SELECT setval(pg_get_serial_sequence(%s, %s), GREATEST(nextval(pg_get_serial_sequence(%s, %s)), nextval(pg_get_serial_sequence(%s, %s))) + 1000)',
            [Pessoa._meta.db_table, 'id', Pessoa._meta.db_table, 'id', Vinculo._meta.db_table, 'id'],
        )


def _com_senha(servidor):
    """Os fluxos do `edu` autenticam de verdade; o `ServidorFactory` não define senha."""
    user = servidor.get_user()
    user.set_password(SENHA)
    user.save()
    return servidor


@pytest.fixture
def atores_edu(db, sync_permissions, suap_client):
    """Substrato dos fluxos legados do `edu`, no lugar do antigo `suap_data`.

    São quatro servidores (cada um recebe um grupo diferente em `EduTestCase`) e dois
    setores com campus: o `a0`, que é a unidade das planilhas, e o `re`, que faz papel de
    reitoria no certificado do ENEM.

    Chama `seed_academico()` pelas tabelas-tipo do acadêmico (`Turno`, `NivelEnsino`,
    `Modalidade`, `SituacaoMatricula`...): têm id constante e eram semeadas pelo
    `light_data`, não pelo `sync_permissions`.
    """
    seed_academico()
    _desalinhar_pessoa_de_vinculo()

    tipo_reitoria, _ = TipoUnidadeOrganizacional.objects.get_or_create(id=UnidadeOrganizacional.TIPO_REITORIA, defaults={'descricao': 'Reitoria'})
    tipo_campus, _ = TipoUnidadeOrganizacional.objects.get_or_create(id=UnidadeOrganizacional.TIPO_CAMPUS_PRODUTIVO, defaults={'descricao': 'Campus'})
    # O certificado do ENEM imprime o endereço da unidade, e `retornar(Municipio)` do
    # `EduTestCase` faz `latest('id')`: sem nenhum município o fluxo estoura.
    municipio, _ = Municipio.objects.get_or_create(nome='Natal', uf='RN', codigo='NAT')
    endereco = {'endereco': 'Rua Dr. Nilo Bezerra Ramalho, 1692, Tirol', 'cep': '59015-300', 'municipio': municipio}

    # Sigla PRÓPRIA para a reitoria: o certificado do ENEM resolve a unidade por
    # `UnidadeOrganizacional.objects.suap().get(sigla=get_sigla_reitoria())`, e outros
    # módulos (p.ex. `documento_eletronico`) COMMITAM uma UO de sigla 'RE'. Com a sigla
    # padrão o `get()` achava duas linhas e estourava `MultipleObjectsReturned`.
    Configuracao.objects.update_or_create(app='comum', chave='reitoria_sigla', defaults={'valor': SIGLA_REITORIA_EDU})

    setor_raiz = SetorFactory(sigla='RAIZ-EDU')
    setor_re = SetorFactory(sigla=SIGLA_REITORIA_EDU, superior=setor_raiz, campus=False)
    setor_a0 = SetorFactory(sigla='A0-EDU', superior=setor_raiz, campus=False)
    for setor, sigla, t in ((setor_re, SIGLA_REITORIA_EDU, tipo_reitoria), (setor_a0, 'A0-EDU', tipo_campus)):
        UnidadeOrganizacional.objects.suap().create(
            setor=setor, nome=sigla, sigla=sigla, codigo_protocolo=f'3{setor.id}'.zfill(5), tipo=t, **endereco
        )
        setor.refresh_from_db()

    # A configuração `professor_externo_ocupacao_padrao` do `EduTestCase` guardava o valor
    # fixo '1' e funcionava só porque o `suap_data` criava esta ocupação primeiro, ficando
    # com o id 1. Agora o teste lê o id real desta linha.
    ocupacao_professor_externo, _ = Ocupacao.objects.get_or_create(codigo='', defaults={'descricao': 'Teste Ocupação'})

    return SimpleNamespace(
        client=suap_client,
        ocupacao_professor_externo=ocupacao_professor_externo,
        servidor_a=_com_senha(ServidorFactory(setor=setor_a0)),
        servidor_b=_com_senha(ServidorFactory(setor=setor_a0)),
        servidor_c=_com_senha(ServidorFactory(setor=setor_a0)),
        servidor_d=_com_senha(ServidorFactory(setor=setor_a0)),
        setor_raiz_suap=setor_raiz,
        setor_a0_suap=setor_a0,
        setor_re_suap=setor_re,
    )
