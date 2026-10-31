from datetime import datetime

import pytest
from django.contrib.messages import get_messages
from django.http import HttpResponse
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from centralservicos.models import Chamado, Comunicacao, HistoricoStatus, StatusChamado
from centralservicos.tests.builders import CentralServicosContext
from comum.models import User


class TestArquivamentoDeComentarios:
    @pytest.fixture(autouse=True)
    def _setup(self, centralservicos_context: CentralServicosContext) -> None:
        self.context = centralservicos_context
        self.client = centralservicos_context.client
        self.chamado = centralservicos_context.chamado
        Chamado.objects.filter(pk=self.chamado.pk).update(status=StatusChamado.get_status_em_atendimento())
        self.chamado = Chamado.objects.get(pk=self.chamado.pk)
        HistoricoStatus.objects.create(
            chamado=self.chamado,
            usuario=centralservicos_context.servidor_atendente.get_user(),
            status=StatusChamado.get_status_em_atendimento(),
        )

    def _login(self, usuario: User) -> None:
        self.client.logout()
        assert self.client.login(user=usuario)

    def _criar_comunicacao(
        self,
        remetente: User,
        texto: str = 'Comentário para teste.',
        tipo: str = Comunicacao.TIPO_COMENTARIO,
        escondida_em: datetime | None = None,
        desconsiderada_em: datetime | None = None,
    ) -> Comunicacao:
        comunicacao = Comunicacao(
            chamado=self.chamado,
            remetente=remetente,
            texto=texto,
            tipo=tipo,
            escondida_em=escondida_em,
            desconsiderada_em=desconsiderada_em,
        )
        comunicacao.save(suspender_notificacao=True)
        return comunicacao

    def _visualizar_chamado(self) -> HttpResponse:
        return self.client.get(reverse('centralservicos_visualizar_chamado', args=[self.chamado.id]))

    def test_remetente_autorizado_pode_arquivar_comentario(self) -> None:
        usuario = self.context.servidor_solicitante.get_user()
        comentario = self._criar_comunicacao(usuario)
        self._login(usuario)

        response = self.client.post(reverse('centralservicos_arquivar_comentario', args=[comentario.id]))

        comentario.refresh_from_db()
        assert comentario.escondida_em is not None
        assert response.status_code == 302
        assert response.headers['Location'] == f'{self.chamado.get_absolute_url()}?tab=linha_tempo'
        assert 'Comentário arquivado com sucesso.' in [str(message) for message in get_messages(response.wsgi_request)]

    def test_remetente_autorizado_pode_desarquivar_comentario(self) -> None:
        usuario = self.context.servidor_solicitante.get_user()
        comentario = self._criar_comunicacao(usuario, escondida_em=timezone.now())
        self._login(usuario)

        response = self.client.post(reverse('centralservicos_desarquivar_comentario', args=[comentario.id]))

        comentario.refresh_from_db()
        assert comentario.escondida_em is None
        assert response.status_code == 302
        assert response.headers['Location'] == f'{self.chamado.get_absolute_url()}?tab=linha_tempo'
        assert 'Comentário desarquivado com sucesso.' in [str(message) for message in get_messages(response.wsgi_request)]

    def test_outro_usuario_nao_pode_arquivar_nem_desarquivar_comentario(self) -> None:
        autor = self.context.servidor_solicitante.get_user()
        outro_usuario = self.context.servidor_atendente.get_user()
        comentario = self._criar_comunicacao(autor)
        self._login(outro_usuario)

        response = self.client.post(reverse('centralservicos_arquivar_comentario', args=[comentario.id]))
        assert response.status_code == 403
        comentario.refresh_from_db()
        assert comentario.escondida_em is None

        comentario.escondida_em = timezone.now()
        comentario.save(update_fields=['escondida_em'])
        response = self.client.post(reverse('centralservicos_desarquivar_comentario', args=[comentario.id]))
        assert response.status_code == 403
        comentario.refresh_from_db()
        assert comentario.escondida_em is not None

    @pytest.mark.parametrize('nome_rota', ['centralservicos_arquivar_comentario', 'centralservicos_desarquivar_comentario'])
    def test_nota_interna_nao_pode_ser_alterada_pelas_rotas(self, nome_rota: str) -> None:
        usuario = self.context.servidor_solicitante.get_user()
        nota = self._criar_comunicacao(usuario, tipo=Comunicacao.TIPO_NOTA_INTERNA, escondida_em=timezone.now())
        self._login(usuario)

        response = self.client.post(reverse(nome_rota, args=[nota.id]))

        assert response.status_code == 404

    @pytest.mark.parametrize('nome_rota', ['centralservicos_arquivar_comentario', 'centralservicos_desarquivar_comentario'])
    def test_remetente_sem_permissao_contextual_nao_pode_alterar_comentario(self, nome_rota: str) -> None:
        usuario = self.context.servidor_solicitante.get_user()
        comentario = self._criar_comunicacao(usuario, escondida_em=timezone.now())
        Chamado.objects.filter(pk=self.chamado.pk).update(status=StatusChamado.get_status_resolvido())
        self._login(usuario)

        response = self.client.post(reverse(nome_rota, args=[comentario.id]))

        assert response.status_code == 403

    @pytest.mark.parametrize(
        ('nome_rota', 'arquivado'),
        [
            ('centralservicos_arquivar_comentario', False),
            ('centralservicos_desarquivar_comentario', True),
        ],
    )
    def test_get_nao_altera_comentario(self, nome_rota: str, arquivado: bool) -> None:
        usuario = self.context.servidor_solicitante.get_user()
        comentario = self._criar_comunicacao(usuario, escondida_em=timezone.now() if arquivado else None)
        self._login(usuario)

        response = self.client.get(reverse(nome_rota, args=[comentario.id]))

        comentario.refresh_from_db()
        assert response.status_code == 405
        assert (comentario.escondida_em is not None) is arquivado

    @pytest.mark.parametrize(
        ('nome_rota', 'arquivado'),
        [
            ('centralservicos_arquivar_comentario', False),
            ('centralservicos_desarquivar_comentario', True),
        ],
    )
    def test_post_sem_token_csrf_nao_altera_comentario(self, nome_rota: str, arquivado: bool) -> None:
        usuario = self.context.servidor_solicitante.get_user()
        comentario = self._criar_comunicacao(usuario, escondida_em=timezone.now() if arquivado else None)
        client = Client(enforce_csrf_checks=True)
        client.force_login(usuario)

        response = client.post(reverse(nome_rota, args=[comentario.id]))

        comentario.refresh_from_db()
        assert response.status_code == 403
        assert (comentario.escondida_em is not None) is arquivado

    def test_comentario_ativo_exibe_somente_acao_de_arquivar(self) -> None:
        usuario = self.context.servidor_solicitante.get_user()
        comentario = self._criar_comunicacao(usuario)
        self._login(usuario)

        response = self._visualizar_chamado()
        pagina = response.content.decode()

        assert response.status_code == 200
        assert 'Arquivar comentário' in pagina
        assert f'action="{reverse("centralservicos_arquivar_comentario", args=[comentario.id])}"' in pagina
        assert 'name="csrfmiddlewaretoken"' in pagina
        assert 'Desconsiderar comentário' not in pagina
        assert 'class="timeline-arquivados"' not in pagina

    def test_comentario_arquivado_inicia_oculto_e_pode_ser_desarquivado(self) -> None:
        usuario = self.context.servidor_solicitante.get_user()
        comentario = self._criar_comunicacao(usuario, escondida_em=timezone.now())
        self._login(usuario)

        response = self._visualizar_chamado()
        pagina = response.content.decode()

        assert response.status_code == 200
        assert 'data-comentario-arquivado class="d-none"' in pagina
        assert 'Comentário arquivado em' in pagina
        assert 'Desarquivar comentário' in pagina
        assert f'action="{reverse("centralservicos_desarquivar_comentario", args=[comentario.id])}"' in pagina
        assert 'name="csrfmiddlewaretoken"' in pagina
        assert 'aria-pressed="false">Exibir comentários arquivados' in pagina
        assert 'Esconder comentários arquivados' in pagina
        assert '.attr("aria-pressed", exibir ? "true" : "false")' in pagina

    def test_comentario_desconsiderado_permanece_apenas_como_historico(self) -> None:
        usuario = self.context.servidor_solicitante.get_user()
        self._criar_comunicacao(usuario, desconsiderada_em=timezone.now())
        self._login(usuario)

        response = self._visualizar_chamado()
        pagina = response.content.decode()

        assert response.status_code == 200
        assert 'Comentário desconsiderado em' in pagina
        assert 'Arquivar comentário' not in pagina
        assert 'Desarquivar comentário' not in pagina
        assert 'Desconsiderar comentário' not in pagina
