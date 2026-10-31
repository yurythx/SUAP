"""As seis rotas de preferência de notificação só enxergam a preferência de quem pediu.

``PreferenciaNotificacao`` tem dono explícito (``vinculo``), e a listagem que hospeda estes
botões sempre soube disso (``PreferenciaNotificacaoAdmin.get_queryset`` filtra por
``vinculo=request.user.get_vinculo()``). As views por trás dos botões é que resolviam a
preferência só pelo ``pk`` — qualquer usuário autenticado silenciava a notificação de qualquer
outro chutando número (#17386).

Os dois lados são afirmados sobre as mesmas seis rotas, de propósito. Só o negativo passaria
verde com a correção errada no sentido oposto: se ``get_vinculo()`` devolvesse ``None``, ou se o
``vinculo`` da preferência apontasse para outro vínculo da mesma pessoa, tudo daria 404 e o
recurso estaria morto com o teste no verde. O positivo é o que prende o invariante
``preferencia.vinculo == user.get_vinculo()``.

As duas famílias de rota respondem diferente, e é assim que devem responder: a de item único
devolve 404 (o objeto não existe para quem pediu) e a em lote redireciona ignorando o ``pk``
alheio. O que vale em ambas é o banco, não o status — por isso todo teste confere o campo de B
pelo ORM.
"""

from __future__ import annotations

import pytest
from django.contrib.auth.models import Group
from django.test import Client

from comum.models import CategoriaNotificacao, Preferencia, PreferenciaNotificacao
from comum.tests.factories import CategoriaNotificacaoFactory, PreferenciaFactory, PreferenciaNotificacaoFactory
from rh.tests.factories import ServidorFactory

pytestmark = pytest.mark.django_db

INDIVIDUAIS = [
    ('/comum/atualizar_via_suap/{pk}/', 'via_suap'),
    ('/comum/atualizar_via_email/{pk}/', 'via_email'),
]
# O valor de partida é sempre aquele que a rota mudaria: desativar parte do canal ligado, ativar
# do desligado. Com o valor já no destino, os asserts dos dois lados passariam sem provar nada.
EM_LOTE = [
    ('/comum/desativar_via_suap_em_lote/', 'via_suap', True),
    ('/comum/desativar_via_email_em_lote/', 'via_email', True),
    ('/comum/ativar_via_suap_em_lote/', 'via_suap', False),
    ('/comum/ativar_via_email_em_lote/', 'via_email', False),
]


@pytest.fixture
def preferencias(sync_permissions):
    """``(usuário A, usuário B, preferência de B)`` — dois servidores, a preferência é de B.

    Só dois ``ServidorFactory`` (~140 ms cada, e cada um cria ``User`` e ``Vinculo``): o que o
    fluxo pede é um dono e um estranho, não o substrato inteiro.
    """
    servidor_a = ServidorFactory()
    servidor_b = ServidorFactory()
    preferencia_b = PreferenciaNotificacaoFactory(vinculo=servidor_b.get_vinculo())
    return servidor_a.get_user(), servidor_b.get_user(), preferencia_b


@pytest.mark.parametrize(('rota', 'campo'), INDIVIDUAIS)
def test_estranho_recebe_404_na_rota_de_item_unico(client: Client, preferencias, rota: str, campo: str) -> None:
    """A recebe 404 ao mexer na preferência de B, e o canal de B continua ligado."""
    user_a, _user_b, preferencia_b = preferencias
    client.force_login(user_a)

    resposta = client.get(rota.format(pk=preferencia_b.pk))

    assert resposta.status_code == 404, 'a view aceitou o pk de outra pessoa'
    preferencia_b.refresh_from_db()
    assert getattr(preferencia_b, campo), f'{campo} da preferência alheia foi desligado'


@pytest.mark.parametrize(('rota', 'campo', 'valor_inicial'), EM_LOTE)
def test_estranho_e_ignorado_na_rota_em_lote(client: Client, preferencias, rota: str, campo: str, valor_inicial: bool) -> None:
    """A rota em lote não rejeita o pk alheio — simplesmente não o encontra, e não grava nada.

    O canal parte do estado que a rota mudaria (ver ``EM_LOTE``): sem isso o assert passaria por
    acidente, afirmando um estado que já era o inicial.
    """
    user_a, _user_b, preferencia_b = preferencias
    setattr(preferencia_b, campo, valor_inicial)
    preferencia_b.save()
    client.force_login(user_a)

    resposta = client.get(rota, {'ids': str(preferencia_b.pk)})

    assert resposta.status_code == 302, f'a rota em lote devolveu {resposta.status_code} em vez de redirecionar de volta'
    preferencia_b.refresh_from_db()
    assert getattr(preferencia_b, campo) is valor_inicial, f'{campo} da preferência alheia mudou'


@pytest.mark.parametrize(('rota', 'campo'), INDIVIDUAIS)
def test_dono_continua_alternando_pela_rota_de_item_unico(client: Client, preferencias, rota: str, campo: str) -> None:
    """O dono desliga o próprio canal — o filtro por vínculo não pode fechar a porta legítima."""
    _user_a, user_b, preferencia_b = preferencias
    client.force_login(user_b)

    resposta = client.get(rota.format(pk=preferencia_b.pk))

    assert resposta.status_code == 302, f'a view devolveu {resposta.status_code} para o próprio dono'
    preferencia_b.refresh_from_db()
    assert not getattr(preferencia_b, campo), f'o dono pediu para desligar {campo} e nada foi gravado'


@pytest.mark.parametrize(('rota', 'campo', 'valor_inicial'), EM_LOTE)
def test_dono_continua_alternando_pela_rota_em_lote(client: Client, preferencias, rota: str, campo: str, valor_inicial: bool) -> None:
    """Mesma prova pelas quatro rotas em lote, que é onde o ``ids`` da query string entra."""
    _user_a, user_b, preferencia_b = preferencias
    setattr(preferencia_b, campo, valor_inicial)
    preferencia_b.save()
    client.force_login(user_b)

    resposta = client.get(rota, {'ids': str(preferencia_b.pk)})

    assert resposta.status_code == 302, f'a rota em lote devolveu {resposta.status_code} para o próprio dono'
    preferencia_b.refresh_from_db()
    assert getattr(preferencia_b, campo) is not valor_inicial, f'o dono pediu a mudança de {campo} e nada foi gravado'


def test_lote_altera_a_propria_preferencia_sem_tocar_na_alheia(client: Client, preferencias) -> None:
    """Com os dois pks na mesma query string, só o do requisitante é gravado.

    É o caso que separa "filtrou pelo dono" de "errou o pk": uma rota em lote que ignorasse o
    ``ids`` inteiro ao encontrar um estranho também passaria nos testes acima.
    """
    user_a, _user_b, preferencia_b = preferencias
    preferencia_a = PreferenciaNotificacaoFactory(vinculo=user_a.get_vinculo(), categoria=preferencia_b.categoria)
    client.force_login(user_a)

    resposta = client.get('/comum/desativar_via_suap_em_lote/', {'ids': f'{preferencia_a.pk},{preferencia_b.pk}'})

    assert resposta.status_code == 302
    assert not PreferenciaNotificacao.objects.get(pk=preferencia_a.pk).via_suap, 'a própria preferência não foi desligada'
    assert PreferenciaNotificacao.objects.get(pk=preferencia_b.pk).via_suap, 'a preferência alheia foi desligada junto'


# ``CategoriaNotificacao.ativa`` é global: não há dono a filtrar, o gate é permissão (#17405).
# Cada rota parte do valor que ela mudaria, senão o assert negativo passaria por acidente.
CATEGORIA = [
    ('/comum/ativar_categoria_notificacao/{pk}/', False),
    ('/comum/desativar_categoria_notificacao/{pk}/', True),
]


@pytest.mark.parametrize(('rota', 'valor_inicial'), CATEGORIA)
def test_sem_permissao_nao_alterna_categoria_de_notificacao(client: Client, sync_permissions, rota: str, valor_inicial: bool) -> None:
    """Servidor comum, só autenticado, recebe 403 e a categoria de todo mundo fica como estava."""
    categoria = CategoriaNotificacaoFactory(ativa=valor_inicial)
    client.force_login(ServidorFactory().get_user())

    resposta = client.get(rota.format(pk=categoria.pk))

    assert resposta.status_code == 403, f'a rota devolveu {resposta.status_code} para quem não tem a permissão'
    assert CategoriaNotificacao.objects.get(pk=categoria.pk).ativa is valor_inicial, 'a categoria global mudou sem permissão'


@pytest.mark.parametrize(('rota', 'valor_inicial'), CATEGORIA)
def test_coordenador_de_ti_alterna_categoria_de_notificacao(client: Client, sync_permissions, rota: str, valor_inicial: bool) -> None:
    """Quem administra a listagem (*Coordenador de TI sistêmico*) continua alternando a categoria."""
    categoria = CategoriaNotificacaoFactory(ativa=valor_inicial)
    user = ServidorFactory().get_user()
    user.groups.add(Group.objects.get(name='Coordenador de TI sistêmico'))
    client.force_login(user)

    resposta = client.get(rota.format(pk=categoria.pk))

    assert resposta.status_code == 302, f'a rota devolveu {resposta.status_code} para quem tem a permissão'
    assert CategoriaNotificacao.objects.get(pk=categoria.pk).ativa is not valor_inicial, 'a alternância não foi gravada'


# O ``ids`` chega da query string como texto livre. Sem ele a view redirecionava para si mesma
# sem a query e a segunda passada estourava ``AttributeError``; com pedaço vazio ou não numérico o
# ``pk__in`` levantava ``ValueError`` (#17406). O pk alheio no último caso prova que o descarte do
# lixo não reabre o IDOR de #17386.
IDS_INVALIDOS = [
    pytest.param(None, id='ausente'),
    pytest.param('', id='vazio'),
    pytest.param(',,abc', id='so-lixo'),
    pytest.param('{pk_alheio},,abc', id='alheio-com-lixo'),
]


@pytest.mark.parametrize('ids', IDS_INVALIDOS)
@pytest.mark.parametrize(('rota', 'campo', 'valor_inicial'), EM_LOTE)
def test_lote_com_ids_ausente_ou_invalido_redireciona_sem_gravar(
    client: Client, preferencias, rota: str, campo: str, valor_inicial: bool, ids: str | None
) -> None:
    """``ids`` ausente, vazio ou com lixo vira lista vazia: 302 e nada gravado, em vez de 500."""
    user_a, user_b, preferencia_b = preferencias
    preferencia_a = PreferenciaNotificacaoFactory(vinculo=user_a.get_vinculo(), categoria=preferencia_b.categoria, **{campo: valor_inicial})
    setattr(preferencia_b, campo, valor_inicial)
    preferencia_b.save()
    client.force_login(user_b)

    resposta = client.get(rota, {} if ids is None else {'ids': ids.format(pk_alheio=preferencia_a.pk)})

    assert resposta.status_code == 302, f'a rota em lote devolveu {resposta.status_code} em vez de redirecionar de volta'
    assert getattr(PreferenciaNotificacao.objects.get(pk=preferencia_b.pk), campo) is valor_inicial, f'{campo} mudou sem pk válido do dono'
    assert getattr(PreferenciaNotificacao.objects.get(pk=preferencia_a.pk), campo) is valor_inicial, f'{campo} da preferência alheia mudou'


@pytest.mark.parametrize(('rota', 'campo', 'valor_inicial'), EM_LOTE)
def test_lote_grava_o_pk_valido_mesmo_ao_lado_de_lixo(client: Client, preferencias, rota: str, campo: str, valor_inicial: bool) -> None:
    """O descarte é por pedaço: o pk legítimo ao lado de vazio e texto continua sendo gravado."""
    _user_a, user_b, preferencia_b = preferencias
    setattr(preferencia_b, campo, valor_inicial)
    preferencia_b.save()
    client.force_login(user_b)

    resposta = client.get(rota, {'ids': f'{preferencia_b.pk},,abc'})

    assert resposta.status_code == 302
    assert getattr(PreferenciaNotificacao.objects.get(pk=preferencia_b.pk), campo) is not valor_inicial, 'o pk válido foi descartado junto com o lixo'


# Preferência PADRÃO (#17390). Sem linha de ``Preferencia`` o usuário recebe pelos dois canais
# (defaults do model e ``User.eh_notificado_*``), e é a partir desse estado efetivo que
# ``atualizar_preferencia_padrao`` alterna. A barra de ações tem de anunciar essa mesma ação.
LISTAGEM = '/admin/comum/preferencianotificacao/'
PREFERENCIA_PADRAO = '/comum/atualizar_preferencia_padrao/?envio={envio}'
CANAIS = [('suap', 'via_suap', 'SUAP'), ('email', 'via_email', 'E-mail')]


@pytest.mark.parametrize(('envio', 'campo', 'nome'), CANAIS)
def test_sem_preferencia_o_botao_anuncia_o_que_o_clique_faz(client: Client, sync_permissions, envio: str, campo: str, nome: str) -> None:
    """Sem linha gravada, a barra oferece desativar o canal — e o clique de fato o desativa."""
    user = ServidorFactory().get_user()
    client.force_login(user)

    barra = client.get(LISTAGEM).content.decode()
    assert f'Desativar Envio Padrão via {nome}' in barra, f'sem preferência gravada, o canal {nome} está ligado e a barra não oferece desligá-lo'
    assert f'Padrão: Via {nome}' not in barra, 'a barra voltou a exibir o rótulo ambíguo, que se lê como "ativar"'

    client.get(PREFERENCIA_PADRAO.format(envio=envio))

    assert getattr(Preferencia.objects.get(usuario=user), campo) is False, 'o botão anunciou desativar, mas o canal ficou ligado'


@pytest.mark.parametrize(('envio', 'campo', 'nome'), CANAIS)
def test_com_preferencia_desligada_o_botao_religa_o_canal(client: Client, sync_permissions, envio: str, campo: str, nome: str) -> None:
    """Com o canal desligado numa linha existente, a barra oferece ativar e o clique religa."""
    user = ServidorFactory().get_user()
    PreferenciaFactory(usuario=user, **{campo: False})
    client.force_login(user)

    assert f'Ativar Envio Padrão via {nome}' in client.get(LISTAGEM).content.decode()

    client.get(PREFERENCIA_PADRAO.format(envio=envio))

    assert getattr(Preferencia.objects.get(usuario=user), campo) is True, 'a alternância do canal existente não foi gravada'


@pytest.mark.parametrize(('envio', 'campo', 'nome'), CANAIS)
def test_sem_preferencia_desligar_o_switch_da_minha_conta_desliga_o_canal(
    client: Client, sync_permissions, envio: str, campo: str, nome: str
) -> None:
    """``minha_conta.html`` mostra o switch ligado sem linha gravada; desmarcá-lo desliga o canal.

    Prende o segundo chamador da rota: "não alternar quando a linha nasce na requisição" deixaria
    este desmarcar sem efeito.
    """
    user = ServidorFactory().get_user()
    client.force_login(user)

    client.get(PREFERENCIA_PADRAO.format(envio=envio) + '&is_ajax=True')

    assert getattr(Preferencia.objects.get(usuario=user), campo) is False, f'o switch do canal {nome} foi desmarcado, mas o canal ficou ligado'
