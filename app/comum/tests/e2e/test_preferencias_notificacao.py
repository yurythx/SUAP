"""Fluxo: preferências de notificação — por onde cada usuário recebe o que o SUAP manda.

``PreferenciaNotificacao`` é o interruptor por categoria de cada pessoa: SUAP, e-mail, ou os
dois. Quem o aciona é a listagem ``/admin/comum/preferencianotificacao/``, que **não** grava
nada: cada botão e cada ação em massa redireciona para uma das seis rotas de ``comum/urls.py``
que ligam/desligam e voltam para a listagem.

A regressão que este arquivo pega é uma que ninguém vê acontecer: as seis views protegem o
mesmo invariante — não dá para desligar os dois canais ao mesmo tempo — e, se ele cair, a
categoria simplesmente para de notificar. Nada quebra, nada aparece em log; o aviso é que não
chega.

As seis rotas são exercitadas por dois caminhos, de propósito: as de item único pelo botão da
linha (que é como o usuário as alcança) e as em lote pelas duas pontas — a ação em massa do
admin, que prova o caminho real, e o ``GET`` direto, que prova a view fora dele.

Os dois últimos testes são da 5ª fatia e estão aqui, e não num arquivo paralelo, porque são o
mesmo fluxo um degrau acima: a **categoria** (que liga e desliga a notificação para todo mundo,
de uma vez) e a **preferência padrão do usuário** (o canal que vale para as categorias novas). As
três telas são as mesmas duas listagens do admin, e separá-las só duplicaria o cenário.
"""

from __future__ import annotations

import pytest

from djtools.e2e_ui import Tela

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

# Rotas como constantes de módulo — ver a nota da armadilha 17 em `test_grupos.py`.
ATUALIZAR_VIA_SUAP = '/comum/atualizar_via_suap/{preferencia}/'
ATUALIZAR_VIA_EMAIL = '/comum/atualizar_via_email/{preferencia}/'
ATIVAR_VIA_SUAP_EM_LOTE = '/comum/ativar_via_suap_em_lote/'
ATIVAR_VIA_EMAIL_EM_LOTE = '/comum/ativar_via_email_em_lote/'
DESATIVAR_VIA_SUAP_EM_LOTE = '/comum/desativar_via_suap_em_lote/'
DESATIVAR_VIA_EMAIL_EM_LOTE = '/comum/desativar_via_email_em_lote/'
ATIVAR_CATEGORIA = '/comum/ativar_categoria_notificacao/{categoria}/'
DESATIVAR_CATEGORIA = '/comum/desativar_categoria_notificacao/{categoria}/'
ATUALIZAR_PREFERENCIA_PADRAO = '/comum/atualizar_preferencia_padrao/'

# A listagem que hospeda os dois gestos. Rota do admin, então fora do gate de `comum/urls.py` —
# mas é ela que o `menu.yaml` publica como "Usuários::Notificações::Preferências".
LISTAGEM = '/admin/comum/preferencianotificacao/'

# A listagem das categorias. Exige `comum.view_categorianotificacao`, que nenhum papel de
# `PAPEIS` carrega — quem a abre é o superusuário do seed base (`logado_comum('admin')`).
LISTAGEM_CATEGORIAS = '/admin/comum/categorianotificacao/'


@pytest.mark.parametrize(
    ('canal', 'campo', 'rota'),
    [('E-mail', 'via_email', ATUALIZAR_VIA_EMAIL), ('SUAP', 'via_suap', ATUALIZAR_VIA_SUAP)],
)
def test_desliga_um_canal_pelo_botao_da_linha(logado_comum, preferencia_notificacao, canal, campo, rota):
    """Desliga o canal pelo botão que a própria linha oferece, e o botão leva à rota esperada.

    Os dois canais são o mesmo gesto a menos do par (rótulo, campo), então viram um
    ``parametrize`` e não dois testes (regra 2 da receita) — o que se está verificando é
    exatamente esse par.

    O botão é localizado pelo ``href`` **e** pelo rótulo, não por um dos dois: a listagem do admin
    monta esses links à mão (``PreferenciaNotificacaoAdmin.get_opcoes``), então o par
    (texto, rota) é o contrato inteiro — um pk errado ali desligaria a notificação de outra
    categoria sem nenhum sintoma visível, e clicar só pelo texto passaria por cima disso.
    """
    from playwright.sync_api import expect

    _categoria, preferencia = preferencia_notificacao

    tela = Tela(logado_comum('solicitante')).ir(LISTAGEM)
    botao = tela.loc(f'//a[@href="{rota.format(preferencia=preferencia.pk)}" and contains(., "Desativar Envio via {canal}")]').first
    expect(botao).to_be_visible()
    botao.click()

    tela.sucesso('Preferência atualizada com sucesso.')
    preferencia.refresh_from_db()
    assert not getattr(preferencia, campo), f'a UI disse que atualizou, mas {campo} continua ligado'


@pytest.mark.parametrize(
    ('canal', 'campo', 'rota_ativar'),
    [('E-mail', 'via_email', ATIVAR_VIA_EMAIL_EM_LOTE), ('SUAP', 'via_suap', ATIVAR_VIA_SUAP_EM_LOTE)],
)
def test_desliga_em_lote_pela_acao_do_admin_e_religa_pela_rota(logado_comum, preferencia_notificacao, canal, campo, rota_ativar):
    """Desliga o canal pela ação em massa e o religa chamando a rota em lote diretamente.

    Os dois sentidos num teste só porque o segundo repõe o que o primeiro desfez — e o banco de
    e2e é reusado entre execuções, então deixar a preferência desligada mudaria o ponto de
    partida da próxima.

    A ida é pela ação em massa do admin, que é o único lugar do SUAP que monta a URL com
    ``?ids=`` (``PreferenciaNotificacaoAdmin.ativar_via_email`` e irmãs). A volta é por
    ``Tela.buscar``: um ``GET`` pela sessão do browser, sem seguir o redirect. Sem referer a view
    redireciona para si mesma **sem a query string**; a segunda passada, sem ``ids``, dava 500 até
    #17406 (hoje só redireciona). O que se afirma aqui é o 302 e o banco, não a tela seguinte.
    """
    _categoria, preferencia = preferencia_notificacao

    tela = Tela(logado_comum('solicitante')).ir(LISTAGEM)
    tela.selecionar_item(str(_categoria))
    tela.preencher('Ação', 'lista', f'Desativar Envio via {canal}')
    tela.clicar_acao('Aplicar')

    tela.sucesso('Preferências atualizadas com sucesso.')
    preferencia.refresh_from_db()
    assert not getattr(preferencia, campo), f'a ação em massa não desligou {campo}'

    resposta = tela.buscar(rota_ativar + f'?ids={preferencia.pk}')

    assert resposta.status == 302, f'a rota em lote devolveu {resposta.status} em vez de redirecionar de volta'
    preferencia.refresh_from_db()
    assert getattr(preferencia, campo), f'a rota em lote não religou {campo}'


def test_nao_desliga_os_dois_canais_da_mesma_categoria(logado_comum, preferencia_notificacao):
    """Com um canal já desligado, a tela recusa desligar o outro — o invariante da notificação.

    É a única regra de negócio das seis views, e a que some sem sintoma: desligados os dois
    canais, a categoria para de notificar e ninguém recebe erro. A recusa é do lado do SUAP
    (``httprr(..., 'error')``), não do formulário, então o que se afirma é o banner de erro
    **e** que o campo continua ligado.
    """
    _categoria, preferencia = preferencia_notificacao
    preferencia.via_email = False
    preferencia.save()

    tela = Tela(logado_comum('solicitante')).ir(LISTAGEM)
    tela.clicar_link('Desativar Envio via SUAP')

    tela.erro('Não é possível inativar as duas formas de Notificação.')
    preferencia.refresh_from_db()
    assert preferencia.via_suap, 'o SUAP recusou pela mensagem, mas desligou o canal assim mesmo'


def test_desativa_em_lote_respeita_o_invariante(logado_comum, preferencia_notificacao):
    """A rota em lote não desliga o último canal — mesma regra, outro caminho de código.

    Vale um teste próprio porque a regra está duplicada: a view de item único devolve mensagem de
    erro, a em lote simplesmente **pula** a preferência que ficaria sem canal
    (``if preferencia.via_suap:``). São dois trechos independentes que só permanecem coerentes
    por vigilância.
    """
    _categoria, preferencia = preferencia_notificacao
    tela = Tela(logado_comum('solicitante')).ir(LISTAGEM)

    # Só o SUAP ligado: desligá-lo em lote deixaria a categoria muda.
    preferencia.via_email = False
    preferencia.save()
    resposta = tela.buscar(DESATIVAR_VIA_SUAP_EM_LOTE + f'?ids={preferencia.pk}')

    assert resposta.status == 302, f'a rota em lote devolveu {resposta.status} em vez de redirecionar de volta'
    preferencia.refresh_from_db()
    assert preferencia.via_suap, 'a rota em lote desligou o último canal da categoria'

    # Agora o espelho: só o e-mail ligado.
    preferencia.via_email = True
    preferencia.via_suap = False
    preferencia.save()
    resposta = tela.buscar(DESATIVAR_VIA_EMAIL_EM_LOTE + f'?ids={preferencia.pk}')

    assert resposta.status == 302, f'a rota em lote devolveu {resposta.status} em vez de redirecionar de volta'
    preferencia.refresh_from_db()
    assert preferencia.via_email, 'a rota em lote desligou o último canal da categoria'


def test_ciclo_da_categoria_de_notificacao(logado_comum, preferencia_notificacao):
    """Desliga e religa uma categoria inteira pela listagem do admin.

    ``CategoriaNotificacao.ativa`` é o interruptor coletivo: ele fica **acima** da preferência de
    cada pessoa, e desligado tira a categoria da listagem de preferências de todo mundo
    (``PreferenciaNotificacaoAdmin.get_queryset`` filtra por ``categoria__ativa=True``). É a
    diferença entre "este usuário não quer receber" e "o SUAP parou de mandar" — e, de novo, o
    sintoma da quebra é o silêncio.

    Os dois sentidos num teste porque o segundo repõe o que o primeiro desfez, e porque a tela
    troca o botão conforme o estado: a ida sai de "Desativar" e a volta só existe depois dela.

    A listagem é aberta **filtrada** pelo sufixo aleatório do assunto: ela ordena por assunto e
    pagina, e o banco de e2e é reusado — sem o filtro, a categoria do teste cairia numa página
    qualquer a partir de um certo número de execuções. O botão é então localizado pelo ``href``
    **e** pelo rótulo, como nos demais: ``get_opcoes`` monta esses links à mão, e um ``pk``
    errado ali desligaria a categoria de outra linha.
    """
    from comum.models import CategoriaNotificacao

    categoria, _preferencia = preferencia_notificacao
    sufixo = categoria.assunto.split()[-1]

    tela = Tela(logado_comum('admin')).ir(LISTAGEM_CATEGORIAS + f'?q={sufixo}')
    tela.loc(f'//a[@href="{DESATIVAR_CATEGORIA.format(categoria=categoria.pk)}" and contains(., "Desativar")]').first.click()

    tela.sucesso('A Categoria de Notificações foi desativada com sucesso.')
    assert not CategoriaNotificacao.objects.get(pk=categoria.pk).ativa, 'a UI disse que desativou, mas a categoria continua ativa'

    tela.ir(LISTAGEM_CATEGORIAS + f'?q={sufixo}')
    tela.loc(f'//a[@href="{ATIVAR_CATEGORIA.format(categoria=categoria.pk)}" and contains(., "Ativar")]').first.click()

    tela.sucesso('A Categoria de Notificações foi ativada com sucesso.')
    assert CategoriaNotificacao.objects.get(pk=categoria.pk).ativa, 'a UI disse que ativou, mas a categoria continua inativa'


def test_ciclo_da_preferencia_padrao_de_envio(logado_efemero, usuario_do_inicio):
    """Desliga e religa o canal PADRÃO do usuário, e a mesma tela recusa desligar os dois.

    ``Preferencia`` é o canal que vale para toda categoria **nova**: é dela que
    ``send_notification`` copia ``via_suap``/``via_email`` ao criar a ``PreferenciaNotificacao``
    de uma categoria que o usuário ainda não viu. Uma regressão aqui não apaga nada — só faz as
    notificações futuras nascerem mudas.

    A regra é a mesma das seis views por categoria (não dá para desligar os dois canais), mas o
    **código é outro**, com a mensagem duplicada e uma terceira cópia dela para o caminho AJAX.
    Três trechos independentes que só permanecem coerentes por vigilância.

    Roda sobre o papel descartável ``dono_do_inicio``: a preferência padrão é do usuário e o
    banco de e2e é reusado, então deixá-la desligada num papel compartilhado mudaria a barra de
    ações — e o que chega por e-mail — de todas as outras fatias.
    """
    from comum.models import Preferencia

    usuario = usuario_do_inicio.get_user()
    tela = Tela(logado_efemero('dono_do_inicio')).ir(LISTAGEM)
    # O par (botão, rota) é o contrato: a barra de ações monta esses links à mão
    # (`PreferenciaNotificacaoAdmin.get_action_bar`), com o canal na query string.
    with tela.pagina.expect_response(lambda resposta: ATUALIZAR_PREFERENCIA_PADRAO in resposta.url) as captura:
        tela.clicar_botao('Desativar Envio Padrão via SUAP')

    assert captura.value.status == 302, f'a rota da preferência padrão devolveu {captura.value.status} em vez de redirecionar de volta'
    tela.sucesso('Preferência atualizada com sucesso.')
    assert not Preferencia.objects.get(usuario=usuario).via_suap, 'a UI disse que atualizou, mas o envio padrão via SUAP continua ligado'

    # Com o SUAP já desligado, desligar o e-mail deixaria o usuário sem canal nenhum.
    tela.clicar_botao('Desativar Envio Padrão via E-mail')

    tela.erro('Não é possível inativar as duas formas de Notificação.')
    assert Preferencia.objects.get(usuario=usuario).via_email, 'o SUAP recusou pela mensagem, mas desligou o último canal'

    tela.clicar_botao('Ativar Envio Padrão via SUAP')

    tela.sucesso('Preferência atualizada com sucesso.')
    assert Preferencia.objects.get(usuario=usuario).via_suap, 'a volta do envio padrão via SUAP não foi gravada'
