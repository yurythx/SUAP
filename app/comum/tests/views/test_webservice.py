"""Endpoint XML-RPC do ``comum`` (``/webservice/``, ``comum/webservice.py``).

É o endereço que o **terminal de ponto** e o cliente de cadastro de digitais consomem. Não é
tela: nenhum navegador chega aqui, então o e2e do módulo não o cobre. Três coisas governam o
arquivo:

* **a autorização é por IP, não por sessão.** Todas as funções, menos ``logout``,
  abrem com ``ponto.Maquina.objects.get(ip=get_client_ip(tl.get_request()), ativo=True)``. O IP
  vem do ``request`` que o middleware ``ThreadLocals`` guardou, então testar essas funções
  chamando-as direto é desonesto (``tl.get_request()`` devolveria ``None`` ou o request de
  *outro* teste). Elas são exercitadas pelo endpoint de verdade, com ``REMOTE_ADDR`` explícito —
  que é a fronteira real, em vez de mockar ``get_client_ip``;
* **o ``REMOTE_ADDR`` é sempre explícito**, inclusive nos testes de recusa. O padrão do client do
  Django é ``127.0.0.1``, e ``comum/tests/e2e/conftest.py`` cadastra uma ``Maquina`` ativa nesse
  IP: sob ``--reuse-db`` um teste de recusa que dependesse da ausência de registro passaria ou
  falharia conforme o e2e tivesse rodado antes;
* **o que há para afirmar é o contrato** — o dicionário que sai do envelope XML-RPC —, porque o
  terminal é um cliente de terceiros e não tolera mudança de forma.
"""

from __future__ import annotations

import xmlrpc.client
from collections.abc import Iterator
from typing import Any

import pytest
from django.contrib.auth.models import Permission
from django.test import Client
from django.test.utils import override_settings

from comum.models import User
from comum.tests.factories import PrestadorServicoFactory, UserFactory
from comum.webservice import comum_exposed
from ponto.models import MaquinaLog
from ponto.tests.factories import MaquinaFactory
from rh.tests.factories import PessoaFisicaFactory, ServidorFactory, SetorFactory

pytestmark = pytest.mark.django_db

WEBSERVICE = '/webservice/'

# IP do "terminal" destes testes. Fixo e fora do 127.0.0.1 de propósito (ver docstring).
IP_TERMINAL = '10.99.0.7'
IP_DESCONHECIDO = '10.99.0.200'


@pytest.fixture(autouse=True)
def _limpa_cache_de_perfil() -> Iterator[None]:
    """Zera os caches de processo ``User.VINCULOS`` / ``User.PESSOAS_FISICAS``.

    São dicionários de classe (``comum/models.py:344``) keyed por ``user.id``, e o rollback da
    transação recicla ids: sem limpar, o ``get_profile()`` de um teste devolveria a pessoa física
    de um usuário já desfeito. Infraestrutura, e local a este arquivo.
    """
    User.VINCULOS.clear()
    User.PESSOAS_FISICAS.clear()
    yield
    User.VINCULOS.clear()
    User.PESSOAS_FISICAS.clear()


def _chamar(client: Client, metodo: str, *args: Any, ip: str = IP_TERMINAL, **extra: Any) -> Any:
    """Faz uma chamada XML-RPC de verdade no endpoint e devolve o valor já desserializado."""
    envelope = xmlrpc.client.dumps(args, methodname=metodo)
    resposta = client.post(WEBSERVICE, data=envelope, content_type='text/xml', REMOTE_ADDR=ip, **extra)
    assert resposta.status_code == 200, f'o endpoint respondeu HTTP {resposta.status_code}'
    return xmlrpc.client.loads(resposta.content)[0][0]


def _com_permissoes(user: User, *codenames: str) -> User:
    """Dá ao usuário as permissões reais (nada de ``has_perm`` mockado)."""
    user.user_permissions.add(*Permission.objects.filter(codename__in=codenames))
    return user


class TestHandler:
    """O handler HTTP (``rpc_handler``) e o registro dos métodos no dispatcher."""

    def test_get_sem_corpo_lista_os_metodos_registrados(self, client):
        """Sem corpo o handler mostra a tela de apresentação — é ela que prova o registro."""
        resposta = client.get(WEBSERVICE, REMOTE_ADDR=IP_TERMINAL)

        assert resposta.status_code == 200
        corpo = resposta.content.decode()
        assert 'This is an XML-RPC Service' in corpo
        for _funcao, nome_exposto in comum_exposed:
            assert f'<strong>{nome_exposto}</strong>' in corpo, f'{nome_exposto} não está registrado no dispatcher'
        assert resposta['Content-length'] == str(len(resposta.content))

    def test_envelope_em_campo_body_do_post_tambem_e_despachado(self, client):
        """O ``'body' in request.POST`` é um atalho para testes; exercitá-lo prova que responde igual."""
        envelope = xmlrpc.client.dumps((), methodname='meu_ip')

        resposta = client.post(WEBSERVICE, data={'body': envelope}, REMOTE_ADDR=IP_TERMINAL)

        assert resposta.status_code == 200
        assert xmlrpc.client.loads(resposta.content)[0][0]['ip'] == IP_TERMINAL

    def test_chamada_anonima_nao_e_redirecionada_para_o_login(self, client):
        """O endpoint é anônimo por contrato: o terminal não tem sessão."""
        resultado = _chamar(client, 'meu_ip')

        assert resultado['ip'] == IP_TERMINAL

    def test_ip_declarado_pelo_cliente_no_cabecalho_prevalece_sobre_o_remote_addr(self, client):
        """``CLIENT_IP_HEADERS`` põe ``HTTP_X_REAL_IP`` antes do ``REMOTE_ADDR``.

        Mede a precedência: quem fala com o SUAP direto (sem o proxy reverso sobrescrever o
        cabeçalho) escolhe o IP com que será autorizado. Em produção o nginx sobrescreve o
        ``X-Real-IP`` com o ``$remote_addr`` (conferido na #17407).
        """
        MaquinaFactory(ip=IP_TERMINAL, cliente_ponto=True)

        resultado = _chamar(client, 'meu_ip', ip=IP_DESCONHECIDO, HTTP_X_REAL_IP=IP_TERMINAL)

        assert resultado['ip'] == IP_TERMINAL
        assert resultado['is_terminal_ponto'] is True


class TestLogin:
    """``login``/``logout``.

    O terminal autentica o operador localmente (digital) e chama ``login`` só com o username,
    antes de ``cadastrar_template`` (``Sincronizador.exportarDigital`` no ``suap-terminais``). Por
    isso a senha segue opcional, e o que segura a chamada é a máquina de cadastro de digitais.
    """

    @pytest.fixture
    def maquina_de_cadastro(self):
        return MaquinaFactory(ip=IP_TERMINAL, cliente_cadastro_impressao_digital=True)

    def test_usuario_inexistente(self, client, maquina_de_cadastro):
        assert _chamar(client, 'login', 'nao_existe_no_suap') == {'ok': False, 'msg': 'Usuário inválido'}

    def test_usuario_inativo(self, client, maquina_de_cadastro):
        user = UserFactory(is_active=False)

        assert _chamar(client, 'login', user.username) == {'ok': False, 'msg': 'Usuário inativo'}

    def test_senha_incorreta(self, client, maquina_de_cadastro):
        user = UserFactory()
        user.set_password('123')
        user.save()

        assert _chamar(client, 'login', user.username, 'outra_senha') == {'ok': False, 'msg': 'Senha incorreta'}

    def test_terminal_de_cadastro_loga_o_operador_sem_senha(self, client, maquina_de_cadastro):
        """Contrato do terminal: sem senha, a ``session_pk`` é o próprio username."""
        user = UserFactory()

        assert _chamar(client, 'login', user.username) == {'ok': True, 'msg': 'Login realizado com sucesso', 'session_pk': user.username}
        assert _chamar(client, 'login', user.username, '123')['ok'] is False

    @pytest.mark.parametrize(
        ('ip', 'maquina'),
        [
            (IP_DESCONHECIDO, None),
            (IP_TERMINAL, {'cliente_ponto': True}),
            (IP_TERMINAL, {'cliente_cadastro_impressao_digital': True, 'ativo': False}),
        ],
        ids=['maquina_desconhecida', 'maquina_sem_papel_de_cadastro', 'maquina_inativa'],
    )
    def test_fora_da_maquina_de_cadastro_o_login_e_recusado(self, client, ip, maquina):
        """Sem a máquina, o ``login`` não serve para enumerar usuários, nem com a senha certa."""
        if maquina:
            MaquinaFactory(ip=IP_TERMINAL, **maquina)
        user = UserFactory()
        user.set_password('123')
        user.save()

        resultado = _chamar(client, 'login', user.username, '123', ip=ip)

        assert resultado == {'ok': False, 'msg': 'Máquina sem permissão para cadastro de impressões digitais'}

    def test_logout_e_sempre_ok(self, client):
        assert _chamar(client, 'logout', 'qualquer_chave') == {'ok': True}


class TestTerminais:
    """``meu_ip`` e os quatro ``is_terminal_*``: autorização por IP."""

    def test_maquina_registrada_expoe_os_papeis_que_tem(self, client):
        MaquinaFactory(
            ip=IP_TERMINAL,
            cliente_ponto=True,
            cliente_cadastro_impressao_digital=True,
            cliente_chaves=False,
            cliente_refeitorio=True,
        )

        resultado = _chamar(client, 'meu_ip')

        assert resultado == {
            'ip': IP_TERMINAL,
            'is_terminal_ponto': True,
            'is_terminal_cadastro': True,
            'is_terminal_chaves': False,
            'is_terminal_refeitorio': True,
        }

    def test_maquina_desconhecida_nao_tem_papel_algum(self, client):
        MaquinaFactory(ip=IP_TERMINAL, cliente_ponto=True)

        resultado = _chamar(client, 'meu_ip', ip=IP_DESCONHECIDO)

        assert resultado['ip'] == IP_DESCONHECIDO
        assert not any(resultado[chave] for chave in resultado if chave != 'ip')

    def test_maquina_inativa_e_tratada_como_desconhecida(self, client):
        """``ativo=None`` é "ainda não aceita pelo administrador" — não vale como terminal."""
        MaquinaFactory(ip=IP_TERMINAL, ativo=None, cliente_ponto=True)

        assert _chamar(client, 'meu_ip')['is_terminal_ponto'] is False

    def test_cada_is_terminal_responde_com_seu_proprio_ok(self, client):
        """``meu_ip`` descarta o ``ok``; quem chama a função direto o recebe."""
        MaquinaFactory(ip=IP_TERMINAL, cliente_chaves=True)

        assert _chamar(client, 'is_terminal_chaves') == {'ok': True, 'is_terminal_chaves': True}
        assert _chamar(client, 'is_terminal_ponto') == {'ok': True, 'is_terminal_ponto': False}
        assert _chamar(client, 'is_terminal_cadastro') == {'ok': True, 'is_terminal_cadastro': False}
        assert _chamar(client, 'is_terminal_refeitorio') == {'ok': True, 'is_terminal_refeitorio': False}
        assert _chamar(client, 'is_terminal_chaves', ip=IP_DESCONHECIDO) == {'ok': False, 'is_terminal_chaves': False}


class TestGetDadosPessoa:
    """``get_dados_pessoa``: o que o terminal lê para reconhecer a pessoa."""

    def test_maquina_sem_registro_e_recusada(self, client):
        resultado = _chamar(client, 'get_dados_pessoa', 'qualquer', ip=IP_DESCONHECIDO)

        assert resultado == {'ok': False, 'msg': 'Máquina sem permissão para acessar o Web Service'}
        assert not MaquinaLog.objects.filter(operacao='comum_get_dados_pessoa').exists()

    def test_servidor_com_digital(self, client, sync_permissions):
        """Além do contrato, o acesso fica auditado: o dado pessoal e a digital saem com ``MaquinaLog`` (#17450)."""
        maquina = MaquinaFactory(ip=IP_TERMINAL)
        servidor = ServidorFactory(setor=SetorFactory(sigla='TI0'))
        pessoa = servidor.pessoa_fisica
        pessoa.template = b'DIGITAL-DO-SERVIDOR'
        pessoa.save()

        resultado = _chamar(client, 'get_dados_pessoa', servidor.matricula)

        assert resultado['ok'] is True
        assert resultado['msg'] == 'Pessoa encontrada'
        assert resultado['pessoa_id'] == pessoa.pk
        assert resultado['nome'] == pessoa.nome
        assert resultado['matricula'] == servidor.matricula
        assert resultado['login'] == servidor.matricula
        assert resultado['setor'] == 'TI0'
        assert resultado['tem_impressao_digital'] is True
        assert resultado['template'] == b'DIGITAL-DO-SERVIDOR'
        assert resultado['is_superuser'] is False
        assert resultado['operador_chave'] is False
        assert resultado['pode_cadastrar_digital_com_qualidade_media'] is False
        assert MaquinaLog.objects.filter(maquina=maquina, operacao='comum_get_dados_pessoa').count() == 1

    def test_pessoa_sem_matricula_de_servidor_vem_sem_matricula_e_sem_setor(self, client):
        """Prestador tem pessoa física e vínculo, mas não é ``Servidor``: o ``except`` zera os dois."""
        MaquinaFactory(ip=IP_TERMINAL)
        prestador = PrestadorServicoFactory(setor=SetorFactory(sigla='PS0'))

        resultado = _chamar(client, 'get_dados_pessoa', prestador.get_user().username)

        assert resultado['ok'] is True
        assert resultado['pessoa_id'] == prestador.pessoa_fisica.pk
        assert resultado['matricula'] == ''
        assert resultado['setor'] == ''
        assert resultado['login'] == ''
        assert resultado['tem_impressao_digital'] is False
        assert resultado['template'] == b''

    def test_superusuario_sem_pessoa_fisica_recebe_uma_pessoa_sintetica(self, client):
        MaquinaFactory(ip=IP_TERMINAL)
        admin = UserFactory(is_superuser=True)

        resultado = _chamar(client, 'get_dados_pessoa', admin.username)

        assert resultado['ok'] is True
        assert resultado['pessoa_id'] == -1
        assert resultado['nome'] == 'Administrador'
        assert resultado['cpf'] == ''
        assert resultado['is_superuser'] is True
        assert resultado['operador_chave'] is False
        assert resultado['pode_cadastrar_digital_com_qualidade_media'] is True
        assert resultado['tem_impressao_digital'] is False

    def test_usuario_comum_sem_pessoa_fisica_nao_e_encontrado(self, client):
        MaquinaFactory(ip=IP_TERMINAL)
        avulso = UserFactory()

        assert _chamar(client, 'get_dados_pessoa', avulso.username) == {'ok': False, 'msg': 'Pessoa não encontrada'}

    def test_login_inexistente_nao_e_encontrado(self, client):
        MaquinaFactory(ip=IP_TERMINAL)

        assert _chamar(client, 'get_dados_pessoa', 'nao_existe_no_suap') == {'ok': False, 'msg': 'Pessoa não encontrada'}


class TestCadastrarTemplate:
    """``cadastrar_template``: a gravação da impressão digital."""

    def _cenario(self, cadastro_liberado: bool = True) -> tuple[User, Any]:
        """Máquina + usuário operador + pessoa alvo. Sem permissão alguma no usuário."""
        MaquinaFactory(ip=IP_TERMINAL, cliente_cadastro_impressao_digital=cadastro_liberado)
        return UserFactory(), PessoaFisicaFactory()

    def test_maquina_sem_o_papel_de_cadastro_e_recusada(self, client):
        operador, pessoa = self._cenario(cadastro_liberado=False)

        resultado = _chamar(client, 'cadastrar_template', operador.username, pessoa.pk, xmlrpc.client.Binary(b'X'))

        assert resultado == {'ok': False, 'msg': 'Máquina sem permissão para cadastro de impressões digitais'}
        assert not MaquinaLog.objects.filter(operacao='comum_cadastrar_template').exists()

    def test_sessao_desconhecida_e_recusada(self, client):
        _operador, pessoa = self._cenario()

        resultado = _chamar(client, 'cadastrar_template', 'sessao_que_nao_existe', pessoa.pk, xmlrpc.client.Binary(b'X'))

        assert resultado == {'ok': False, 'msg': 'Sua sessão expirou. Faça o login novamente.'}

    def test_usuario_sem_permissao_e_recusado(self, client):
        operador, pessoa = self._cenario()

        resultado = _chamar(client, 'cadastrar_template', operador.username, pessoa.pk, xmlrpc.client.Binary(b'X'))

        assert resultado == {'ok': False, 'msg': 'Usuário sem permissões para cadastrar digitais'}
        pessoa.refresh_from_db()
        assert not pessoa.template

    def test_operador_com_digital_fraca_e_recusado(self, client, sync_permissions):
        """No terminal legado ele entra por senha local, nunca conferida com o SUAP (#17482)."""
        _operador, pessoa = self._cenario()
        operador = _com_permissoes(ServidorFactory(pessoa_fisica__tem_digital_fraca=True).get_user(), 'pode_cadastrar_digital')

        resultado = _chamar(client, 'cadastrar_template', operador.username, pessoa.pk, xmlrpc.client.Binary(b'X'))

        assert resultado == {'ok': False, 'msg': 'Operador com digital fraca não pode cadastrar digitais pelo terminal'}
        pessoa.refresh_from_db()
        assert not pessoa.template

    def test_pessoa_inexistente(self, client):
        operador, _pessoa = self._cenario()
        _com_permissoes(operador, 'pode_cadastrar_digital')

        resultado = _chamar(client, 'cadastrar_template', operador.username, -999_999_999, xmlrpc.client.Binary(b'X'))

        assert resultado == {'ok': False, 'msg': 'Pessoa não encontrada'}

    def test_id_do_vinculo_grava_a_digital_na_pessoa(self, client):
        """O dump dos terminais tem uma linha por vínculo, de id ``-vinculo.id``: a digital é da PF desse vínculo."""
        operador, _pessoa = self._cenario()
        _com_permissoes(operador, 'pode_cadastrar_digital')
        prestador = PrestadorServicoFactory()

        resultado = _chamar(client, 'cadastrar_template', operador.username, -prestador.get_vinculo().id, xmlrpc.client.Binary(b'DIGITAL'))

        assert resultado == {'ok': True, 'msg': 'Impressão digital cadastrada com sucesso'}
        prestador.pessoa_fisica.refresh_from_db()
        assert prestador.pessoa_fisica.get_template() == b'DIGITAL'

    def test_sobrescrever_digital_existente_exige_as_duas_permissoes(self, client):
        operador, pessoa = self._cenario()
        _com_permissoes(operador, 'pode_cadastrar_digital')
        pessoa.template = b'DIGITAL-ANTIGA'
        pessoa.save()

        resultado = _chamar(client, 'cadastrar_template', operador.username, pessoa.pk, xmlrpc.client.Binary(b'DIGITAL-NOVA'))

        assert resultado == {'ok': False, 'msg': 'Usuário sem permissões para sobrescrever digitais'}
        pessoa.refresh_from_db()
        assert pessoa.get_template() == b'DIGITAL-ANTIGA'

    def test_cadastro_grava_a_digital_recodificada_para_o_banco(self, client):
        """Com o leitor Griaule o template chega em ``latin-1`` e é gravado em ``utf-8``; a gravação fica auditada (#17450)."""
        operador, pessoa = self._cenario()
        _com_permissoes(operador, 'pode_cadastrar_digital')
        bruto = 'DIGITAL-Ç'.encode('latin-1')

        resultado = _chamar(client, 'cadastrar_template', operador.username, pessoa.pk, xmlrpc.client.Binary(bruto))

        assert resultado == {'ok': True, 'msg': 'Impressão digital cadastrada com sucesso'}
        pessoa.refresh_from_db()
        assert pessoa.get_template() == 'DIGITAL-Ç'.encode()
        assert pessoa.template_importado_terminal is True
        assert MaquinaLog.objects.filter(maquina__ip=IP_TERMINAL, operacao='comum_cadastrar_template').count() == 1

    @override_settings(USA_LEITOR_BIOMETRICO_GRIAULE=False)
    def test_sem_o_leitor_griaule_a_digital_e_gravada_como_veio(self, client):
        operador, pessoa = self._cenario()
        _com_permissoes(operador, 'pode_cadastrar_digital', 'pode_atualizar_digital')

        resultado = _chamar(client, 'cadastrar_template', operador.username, pessoa.pk, xmlrpc.client.Binary(b'\x01\x02BRUTO'))

        assert resultado['ok'] is True
        pessoa.refresh_from_db()
        assert pessoa.get_template() == b'\x01\x02BRUTO'

    def test_com_as_duas_permissoes_a_digital_existente_e_substituida(self, client):
        operador, pessoa = self._cenario()
        _com_permissoes(operador, 'pode_cadastrar_digital', 'pode_atualizar_digital')
        pessoa.template = b'DIGITAL-ANTIGA'
        pessoa.save()

        resultado = _chamar(client, 'cadastrar_template', operador.username, pessoa.pk, xmlrpc.client.Binary(b'DIGITAL-NOVA'))

        assert resultado['ok'] is True
        pessoa.refresh_from_db()
        assert pessoa.get_template() == b'DIGITAL-NOVA'
