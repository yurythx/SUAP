"""Fluxo: quem está em cada grupo — gerenciamento, entrada, saída, vínculo de setor e consulta.

Grupo é o mecanismo de autorização do SUAP inteiro: ``sync_permissions`` traduz
``<app>/permissions.yaml`` em grupos, e é por grupo que as ~90 aplicações decidem o que cada
servidor vê. Estas telas são o painel de controle desse mecanismo — é daqui que se põe e se tira
alguém de um grupo, com motivo e prazo registrados.

A regressão que este arquivo pega é a cara: uma mudança em ``GerenciamentoGrupo``,
``UsuarioGrupo`` ou nos sinais de ``comum/utils.py`` quebra a concessão de acesso de todo o SUAP,
e o sintoma aparece longe daqui — numa tela de outro módulo que passou a responder 403. Os testes
afirmam as duas pontas: a mensagem da tela e o vínculo no banco.

Nada aqui toca os papéis compartilhados da suíte: o alvo é um servidor descartável que nunca
loga, num grupo do YAML do ``comum`` que nasce vazio (ver ``conftest.GRUPO_GERENCIADO``).
"""

from __future__ import annotations

import uuid

import pytest

from djtools.e2e_ui import Tela

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

# Rotas como constantes de módulo, com `{campo}` no lugar do `<int:pk>`: é esta string literal
# que o gate `bin/scripts/paridade_e2e.py comum --rotas` colhe. NUNCA escreva
# `'/comum/rota/{}/'.format(x)` na chamada: a regra UP032 do ruff reescreve o `str.format`
# literal como f-string e o gate deixa de enxergar a rota (armadilha 17 da receita).
# Query string vai concatenada, nunca embutida: o padrão do gate é ancorado em `$`.
GERENCIAMENTO_GRUPO = '/comum/gerenciamento_grupo/'
GRUPOS_USUARIOS = '/comum/grupos_usuarios/'
# Rota REAL, com espaço e acento no path (`comum/urls.py:49`) — um alias de
# `gerenciamento_grupo`. Escrita aqui na forma crua, sem percent-encoding: é assim que o gate a
# declara (o `re.escape` dele escapa o espaço, mas casa o caractere literal) e é assim que o
# Playwright a aceita, codificando na hora de navegar.
ATRIBUICOES_A_SETORES = '/comum/atribuições a setores/'
ADICIONAR_USUARIO_GRUPO = '/comum/adicionar_usuario_grupo/{grupo}/'
REMOVER_USUARIO_GRUPO = '/comum/remover_usuario_grupo/{usuario_grupo}/'
ADICIONAR_SETOR_USUARIO_GRUPO = '/comum/adicionar_setor_usuario_grupo/{usuario_grupo}/'
GRUPOS_USUARIO = '/comum/grupos_usuario/{usuario}/'
HISTORICO_GRUPOS = '/comum/usuario/{usuario}/historico_grupos/'
VISUALIZAR_MENUS_DO_GRUPO = '/comum/visualizar_menus_do_grupo/{grupo}/'

# O grupo cujos menus a tela de menus exibe. Medido: `Avaliador de Sala` resolve 7 entradas de
# `menu.yaml` a partir das suas permissões, enquanto os dois grupos inertes desta fatia resolvem
# zero — e uma tela vazia não afirma que o cruzamento permissão→menu funciona.
GRUPO_COM_MENUS = 'Avaliador de Sala'

# Setor SUAP usado no vínculo de setor do grupo. Qualquer setor da árvore serve para este fluxo —
# é o mesmo que o conftest usa na automatização, onde a escolha sim importa (lá precisa ser um
# setor sem servidores).
SIGLA_SETOR = 'C1'


def _filtro_do_grupo(grupo) -> str:
    """Query string que leva a tela de grupos ao grupo do teste.

    ``modulo`` é obrigatório: sem ele a tela só mostra o aviso "Você precisa filtrar". ``grupo``
    também é, e não por conveniência — sem ele a view escolhe ``grupos_gerenciados[0]`` de uma
    queryset sem ordenação, e o teste passaria a exercitar o grupo que o banco devolver primeiro.
    """
    return f'?modulo=comum&grupo={grupo.pk}'


def test_ciclo_do_usuario_no_grupo(logado_comum, grupo_gerenciado, servidores_comum):
    """Adiciona o usuário ao grupo pela tela, confere o cartão e o remove — o ciclo inteiro.

    Um teste só, e não três, porque no pytest cada teste é independente: "remover do grupo" não
    é um cenário que exista sem a adição anterior (regra 1 da receita).

    O motivo carrega um ``uuid``: ``HistoricoUsuarioGrupo`` e ``LogEntry`` são acumulativos — a
    suíte não dá flush e o CI roda com ``--reuse-db`` —, então a asserção tem de ser sobre o
    registro **desta** execução, nunca sobre uma contagem.
    """
    from comum.models import HistoricoUsuarioGrupo, UsuarioGrupo

    alvo = servidores_comum['alvo_grupo']
    motivo = f'Necessidade de serviço (e2e {uuid.uuid4().hex[:8]})'

    tela = Tela(logado_comum('gestor_grupos')).ir(GERENCIAMENTO_GRUPO + _filtro_do_grupo(grupo_gerenciado))
    tela.ver_titulo('Gerenciamento de grupos')
    tela.ver_texto('Nenhum usuário encontrado nesse grupo.')

    tela.ir(ADICIONAR_USUARIO_GRUPO.format(grupo=grupo_gerenciado.pk))
    tela.preencher_formulario(
        [
            ('Usuário', 'autocomplete multiplo', alvo.matricula),
            ('Motivo', 'textarea', motivo),
            # Prefixo curto de propósito: o rótulo real tem 300 caracteres e o XPath de checkbox
            # casa por `contains`.
            ('Confirmo que desejo adicionar', 'checkbox', 'marcar'),
        ]
    )
    tela.clicar_botao('Enviar')

    tela.sucesso('Usuário(s) adicionado(s) com sucesso.')
    usuario_grupo = UsuarioGrupo.objects.filter(user=alvo.get_user(), group=grupo_gerenciado).first()
    assert usuario_grupo, 'a UI disse que adicionou, mas o vínculo com o grupo não persistiu'
    assert HistoricoUsuarioGrupo.objects.filter(usuario=alvo.get_user(), grupo=grupo_gerenciado, motivo__contains=motivo).exists(), (
        'o histórico da inclusão não registrou o motivo informado'
    )

    tela.ir(GERENCIAMENTO_GRUPO + _filtro_do_grupo(grupo_gerenciado))
    tela.ver_texto(alvo.matricula)

    tela.ir(REMOVER_USUARIO_GRUPO.format(usuario_grupo=usuario_grupo.pk))
    tela.sucesso(f'Usuário foi removido do grupo {grupo_gerenciado} com sucesso.')
    assert not UsuarioGrupo.objects.filter(pk=usuario_grupo.pk).exists(), 'a UI disse que removeu, mas o vínculo continua no banco'


def test_alias_atribuicoes_a_setores_abre_o_gerenciamento(logado_comum, grupo_gerenciado):
    """A rota com espaço e acento (``comum/urls.py:49``) é um alias vivo de ``gerenciamento_grupo``.

    Vale um teste próprio porque é a única rota do módulo cujo path não é ASCII nem tem só
    ``[a-z_]``: qualquer mudança de servidor, de middleware de URL ou de normalização de path a
    derruba sozinha, e ela some do menu sem ninguém perceber — não há link para ela em lugar
    nenhum do repo.
    """
    tela = Tela(logado_comum('gestor_grupos')).ir(ATRIBUICOES_A_SETORES + _filtro_do_grupo(grupo_gerenciado))

    tela.ver_titulo('Gerenciamento de grupos')
    tela.ver_texto(grupo_gerenciado.name)


def test_vincular_setor_ao_usuario_do_grupo(logado_comum, usuario_no_grupo, grupo_gerenciado):
    """O popup "Vincular Setores" grava o ``UsuarioGrupoSetor`` e o cartão do grupo passa a exibi-lo.

    A rota é aberta com ``?_popup=1`` porque é como o SUAP a serve: a view responde
    ``httprr(..., close_popup=True)``, que sem o parâmetro cai no ramo do ``HttpResponseRedirect``
    para o ``HTTP_REFERER`` — e ``page.goto`` não manda referer. Com ele, a resposta é o script
    que fecha o fancybox, e o fato positivo a afirmar passa a ser o da tela de trás: o cartão do
    usuário ganhando a linha "Setores Vinculados".

    O vínculo por setor é o que o ``edu`` usa para resolver permissão por diretoria
    (``UsuarioGrupoSetor``), então quebrar isto tira acesso de coordenador de curso sem tocar em
    nenhum grupo.
    """
    from comum.models import UsuarioGrupoSetor

    tela = Tela(logado_comum('gestor_grupos')).ir(ADICIONAR_SETOR_USUARIO_GRUPO.format(usuario_grupo=usuario_no_grupo.pk) + '?_popup=1')
    tela.ver_titulo('Vincular Setores')
    tela.preencher('Setores', 'autocomplete multiplo', SIGLA_SETOR)
    tela.clicar_botao('Enviar')

    assert UsuarioGrupoSetor.objects.filter(usuario_grupo=usuario_no_grupo, setor__sigla=SIGLA_SETOR).exists(), (
        'o formulário fechou o popup, mas o vínculo de setor não persistiu'
    )
    tela.ir(GERENCIAMENTO_GRUPO + _filtro_do_grupo(grupo_gerenciado))
    tela.ver_texto('Setores Vinculados:')


def test_grupos_e_historico_do_usuario(logado_comum, usuario_no_grupo, servidores_comum):
    """As duas telas de consulta por usuário: em que grupos está e como entrou neles.

    Consultadas pelo gestor, e não pelo próprio dono: as duas views aceitam os dois casos
    (``request.user != usuario and not user_can_manage`` ⇒ 403), e é o caminho do gestor que
    exercita ``GerenciamentoGrupo.user_can_manage`` — o do dono passaria mesmo com o
    gerenciamento quebrado.

    O histórico não é montado pelo teste: ele é efeito do ``m2m_changed`` de
    ``comum/utils.py:29``, que a fixture dispara ao pôr o usuário no grupo. É justamente esse
    encadeamento (entrar no grupo ⇒ virar registro auditável) que a tela prova.
    """
    alvo = servidores_comum['alvo_grupo']

    tela = Tela(logado_comum('gestor_grupos')).ir(GRUPOS_USUARIO.format(usuario=alvo.get_user().pk))
    tela.ver_texto(usuario_no_grupo.group.name)

    tela.ir(HISTORICO_GRUPOS.format(usuario=alvo.get_user().pk))
    tela.ver_texto(f'Adicionado(a) ao grupo {usuario_no_grupo.group.name}')


def test_menus_visiveis_para_o_grupo(logado_comum):
    """O popup que traduz as permissões de um grupo nos itens de menu que ele destrava.

    É o único lugar do SUAP onde o cruzamento permissão→menu fica visível: a view lê os
    ``menu.yaml`` do disco e cruza com as permissões do grupo. É o que permite a um gestor
    conferir o que está concedendo **antes** de conceder — e, como ela lê arquivo, quebra quando
    um ``menu.yaml`` qualquer muda de formato, não quando o ``comum`` muda.

    O grupo não é um dos inertes desta fatia de propósito: medido, ``Avaliador de Sala`` resolve
    7 entradas de menu a partir das suas permissões e os inertes resolvem zero — e tela vazia não
    afirma que o cruzamento funciona.
    """
    from django.contrib.auth.models import Group

    grupo_com_menus = Group.objects.get(name=GRUPO_COM_MENUS)

    tela = Tela(logado_comum('gestor_grupos')).ir(VISUALIZAR_MENUS_DO_GRUPO.format(grupo=grupo_com_menus.pk))

    tela.ver_titulo(f'Menus Visíveis para Grupo: {grupo_com_menus}')
    tela.ver_texto('Administração::Reservas de Salas::Indicadores')


def test_usuarios_do_grupo_por_modulo(logado_comum, usuario_no_grupo, servidores_comum):
    """A tela *Usuários::Grupos* do menu: quem está em cada grupo de um módulo.

    Monta o filtro de módulos varrendo o ``permissions.yaml`` de todas as apps e tirando o
    grupo gerenciador de cada uma. Até #17387 isso era ``set.remove`` e a tela respondia 500
    para qualquer usuário, porque há app sem ``<app> Administrador`` (o ``progressoes``). O
    teste abre a tela inteira — com o laço sobre todas as apps — e afirma o membro do grupo.
    """
    alvo = servidores_comum['alvo_grupo']
    perfil = alvo.get_user().get_profile()

    tela = Tela(logado_comum('gestor_grupos')).ir(GRUPOS_USUARIOS + _filtro_do_grupo(usuario_no_grupo.group))

    tela.ver_titulo('Grupos de Usuários')
    tela.ver_texto(perfil.nome_usual or perfil.nome)
