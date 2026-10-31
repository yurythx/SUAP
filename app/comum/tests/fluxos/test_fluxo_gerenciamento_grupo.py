"""Fluxo: o gerenciador **local** de um grupo só manda no próprio campus.

Quem distribui as permissões do SUAP não é só o superusuário: um ``GerenciamentoGrupo`` diz
que "o grupo X gerencia os grupos Y e Z", e o campo ``eh_local`` decide se esse poder vale
para a instituição inteira ou apenas para o campus de quem gerencia. É o arranjo que permite
delegar a gestão de acessos aos campi sem lhes dar o sistema todo.

O fluxo percorrido, trocando de ator:

1. O gerenciador local abre a tela de gerenciamento filtrada pelo módulo e pelo campus.
2. Adiciona ao grupo um servidor do **seu** campus, com motivo e prazo — e o histórico grava
   as duas coisas.
3. Tenta adicionar um servidor de **outro** campus: o formulário nem oferece o usuário.
4. Tenta remover do grupo o servidor do outro campus: é barrado.
5. Remove o do próprio campus: sai do grupo, e o histórico do usuário registra a passagem.

Por que este fluxo e não outro: a suíte e2e do módulo anda o ciclo de usuário em grupo, mas
sempre com um gestor que é superusuário — o ramo `else` de ``gerenciamento_grupo`` (o do
gerenciador comum), o recorte por campus do ``AdicionarUsuarioGrupoFormFactory`` e a recusa de
``remover_usuario_grupo`` para usuário de outro campus não são executados por teste nenhum.
"""

from __future__ import annotations

import datetime

import pytest
from django.contrib.auth.models import Group

from comum.models import GerenciamentoGrupo, HistoricoUsuarioGrupo, User, UsuarioGrupo
from rh.tests.factories import ServidorFactory, SetorFactory

GERENCIAMENTO_GRUPO = '/comum/gerenciamento_grupo/'
ADICIONAR_USUARIO_GRUPO = '/comum/adicionar_usuario_grupo/{grupo}/'
REMOVER_USUARIO_GRUPO = '/comum/remover_usuario_grupo/{usuario_grupo}/'
HISTORICO_GRUPOS = '/comum/usuario/{usuario}/historico_grupos/'

# Dois grupos inertes do `permissions.yaml` do comum: nenhum servidor nasce neles, então
# adicionar e remover gente aqui não muda a permissão de mais ninguém na suíte.
GRUPO_GERIDO = 'Atualizador de Digital'
GRUPO_GERENCIADOR = 'Cadastrador de Digital'


def _recarregar(user: User) -> User:
    """Relê o usuário e derruba o cache de grupos do processo.

    Sem isto a checagem de gerenciamento roda sobre a lista de grupos que o usuário tinha
    quando foi instanciado, e a view responde 403 por um motivo que não está no teste.
    """
    recarregado = User.objects.get(pk=user.pk)
    recarregado.get_groups_cached(force=True)
    return recarregado


def _dados_da_inclusao(usuario: User, prazo: datetime.date, motivo: str) -> dict[str, object]:
    return {
        'user': [usuario.pk],
        'motivo': motivo,
        'prazo': prazo.strftime('%d/%m/%Y'),
        'checagem_obrigatoria': 'on',
    }


@pytest.mark.django_db
@pytest.mark.usefixtures('sync_permissions')
class TestFluxoGerenciamentoLocalDeGrupo:
    def test_gerenciador_local_so_mexe_em_gente_do_proprio_campus(self, client) -> None:
        setor_local = SetorFactory(sigla='GL0')
        setor_remoto = SetorFactory(sigla='GR0')
        campus_local = setor_local.uo

        grupo_gerido = Group.objects.get(name=GRUPO_GERIDO)
        grupo_gerenciador = Group.objects.get(name=GRUPO_GERENCIADOR)
        gerenciamento = GerenciamentoGrupo.objects.create(grupo_gerenciador=grupo_gerenciador, eh_local=True)
        gerenciamento.grupos_gerenciados.add(grupo_gerido)

        gestor = ServidorFactory(setor=setor_local)
        gestor_user = gestor.get_user()
        gestor_user.groups.add(grupo_gerenciador)
        gestor_user = _recarregar(gestor_user)

        colega = ServidorFactory(setor=setor_local)
        forasteiro = ServidorFactory(setor=setor_remoto)

        client.force_login(gestor_user)

        # 1. A tela de gerenciamento, filtrada pelo módulo, mostra só o que ele gerencia.
        resposta = client.get(GERENCIAMENTO_GRUPO, {'modulo': 'comum', 'grupo': grupo_gerido.pk})
        assert resposta.status_code == 200
        assert list(resposta.context['grupos_gerenciados']) == [grupo_gerido], (
            'o gerenciador enxergou grupos além dos que o GerenciamentoGrupo lhe delega'
        )
        assert resposta.context['gerenciamento_do_grupo_eh_local'] is True
        assert resposta.context['contador_dict'][grupo_gerido] == 0, 'o grupo deveria começar vazio'

        # 2. Adiciona o colega do próprio campus, com motivo e prazo.
        prazo = datetime.date.today() + datetime.timedelta(days=30)
        motivo = 'Assumiu o atendimento da biometria do campus.'
        resposta = client.post(
            ADICIONAR_USUARIO_GRUPO.format(grupo=grupo_gerido.pk),
            _dados_da_inclusao(colega.get_user(), prazo, motivo),
            follow=True,
        )
        assert resposta.status_code == 200
        assert colega.get_user().groups.filter(pk=grupo_gerido.pk).exists(), 'o colega do campus não entrou no grupo'
        historico = HistoricoUsuarioGrupo.objects.get(usuario=colega.get_user(), grupo=grupo_gerido, operacao='I')
        assert motivo in historico.motivo
        assert historico.prazo == prazo, 'o prazo informado não chegou ao histórico'
        assert historico.incluido_por == gestor_user

        # A tela, agora recortada pelo campus, conta o recém-incluído.
        filtros = {'modulo': 'comum', 'campus': campus_local.sigla, 'grupo': grupo_gerido.pk}
        resposta = client.get(GERENCIAMENTO_GRUPO, filtros)
        assert resposta.status_code == 200
        assert resposta.context['contador_dict'][grupo_gerido] == grupo_gerido.user_set.filter(vinculo__setor__uo=campus_local).count()
        usuarios_no_campus = {usuario_grupo.user_id for usuario_grupo in resposta.context['usuarios_grupo']}
        assert usuarios_no_campus == {colega.get_user().pk}

        # 3. O servidor de outro campus nem é ofertado no formulário do gerenciador local.
        resposta = client.post(
            ADICIONAR_USUARIO_GRUPO.format(grupo=grupo_gerido.pk),
            _dados_da_inclusao(forasteiro.get_user(), prazo, 'Tentativa de inclusão fora do campus.'),
        )
        assert resposta.status_code == 200, 'o formulário deveria ser reexibido com o erro, não redirecionar'
        assert not forasteiro.get_user().groups.filter(pk=grupo_gerido.pk).exists(), (
            'gerenciador local adicionou ao grupo um servidor de outro campus'
        )

        # 4. Remover gente de outro campus é barrado, mesmo com o grupo sob gerência.
        forasteiro_user = forasteiro.get_user()
        forasteiro_user.groups.add(grupo_gerido)
        vinculo_forasteiro = UsuarioGrupo.objects.get(user=forasteiro_user, group=grupo_gerido)
        resposta = client.get(REMOVER_USUARIO_GRUPO.format(usuario_grupo=vinculo_forasteiro.pk))
        assert resposta.status_code == 403
        assert UsuarioGrupo.objects.filter(pk=vinculo_forasteiro.pk).exists(), 'gerenciador local removeu do grupo um servidor de outro campus'

        # 5. Remover o do próprio campus funciona, e o histórico do usuário guarda a passagem.
        vinculo_colega = UsuarioGrupo.objects.get(user=colega.get_user(), group=grupo_gerido)
        resposta = client.get(REMOVER_USUARIO_GRUPO.format(usuario_grupo=vinculo_colega.pk), follow=True)
        assert resposta.status_code == 200
        assert not UsuarioGrupo.objects.filter(pk=vinculo_colega.pk).exists()
        assert not colega.get_user().groups.filter(pk=grupo_gerido.pk).exists(), 'o vínculo sumiu mas o grupo continuou no usuário'

        resposta = client.get(HISTORICO_GRUPOS.format(usuario=colega.get_user().pk))
        assert resposta.status_code == 200
        assert resposta.context['usuario'] == colega.get_user()

    def test_quem_nao_gerencia_grupo_nenhum_nao_abre_a_tela(self, client) -> None:
        """``GerenciamentoGrupo.user_can_manage`` é a porta da tela — e ela é fechada."""
        servidor = ServidorFactory(setor=SetorFactory(sigla='GL1'))
        client.force_login(_recarregar(servidor.get_user()))

        resposta = client.get(GERENCIAMENTO_GRUPO)

        assert resposta.status_code == 403

    def test_usuario_sai_sozinho_do_grupo_pela_minha_conta(self, client) -> None:
        """Sair de um grupo é o único caso em que não se exige gerência: é a própria pessoa.

        O ramo ``sou_eu_mesmo`` de ``remover_usuario_grupo`` existe para a tela "Minha Conta",
        onde cada um larga os grupos de que não precisa mais.
        """
        servidor = ServidorFactory(setor=SetorFactory(sigla='GL2'))
        grupo = Group.objects.get(name=GRUPO_GERIDO)
        user = servidor.get_user()
        user.groups.add(grupo)
        user = _recarregar(user)
        vinculo = UsuarioGrupo.objects.get(user=user, group=grupo)

        client.force_login(user)
        resposta = client.get(REMOVER_USUARIO_GRUPO.format(usuario_grupo=vinculo.pk))

        assert resposta.status_code == 302
        assert resposta.url == '/comum/minha_conta/', 'quem sai sozinho do grupo deve voltar para a Minha Conta'
        assert not UsuarioGrupo.objects.filter(pk=vinculo.pk).exists()
