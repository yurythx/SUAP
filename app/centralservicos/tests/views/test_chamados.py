from django.contrib.messages import get_messages
from django.urls import reverse
import pytest

from centralservicos.models import AtendimentoAtribuicao, CentroAtendimento, Chamado, GrupoAtendimento, HistoricoStatus, StatusChamado
from rh.tests.factories import ServidorFactory


STATUS_EM_ATENDIMENTO = 2
STATUS_RESOLVIDO = 3


class TestFluxoDeChamados:
    @pytest.fixture(autouse=True)
    def _setup(self, centralservicos_context):
        self.context = centralservicos_context
        self.client = centralservicos_context.client

    @staticmethod
    def _assert_no_validation_errors(response):
        page = response.content.decode()
        assert 'errorlist' not in page

    def _login_como_solicitante(self):
        self.client.logout()
        assert self.client.login(user=self.context.servidor_solicitante.get_user())

    def _login_como_atendente(self):
        self.client.logout()
        assert self.client.login(user=self.context.servidor_atendente.get_user())

    def test_abertura_de_chamado_sem_unidade_organizacional_e_barrada(self):
        """Sem UO não há campus padrão e a abertura é negada (``_validar_abertura_de_chamado``).

        É a única das quatro negativas da validação que não dá para exercitar no e2e: o middleware
        ``djtools/middleware/usuario_sem_setor.py`` desloga o servidor cujo setor SUAP está sem
        campus **antes** de a view rodar. Aqui o ``get_uo`` é trocado por ``None`` — o mesmo que um
        usuário sem ocupação ativa produziria — e o que se afirma é o 403 da view.
        """
        from unittest import mock

        self._login_como_solicitante()
        url = reverse('centralservicos_abrir_chamado', args=[self.context.servico.id])

        with mock.patch('centralservicos.views.get_uo', return_value=None):
            response = self.client.get(url)

        assert response.status_code == 403, 'serviço sem unidade organizacional deveria barrar a abertura'

    def test_chamado_criado_por_orm_sem_aberto_em_recebe_data_limite(self):
        """Chamado criado por código não pode estourar no cálculo da data limite.

        ``Chamado.save()`` calcula ``data_limite_atendimento`` **antes** do insert e soma
        ``timedelta`` a ``aberto_em``; como o campo é ``auto_now_add``, quem cria por ORM (fixture,
        comando, importação) não o preenche — e o cálculo levantava
        ``TypeError: unsupported operand type(s) for +: 'NoneType' and 'datetime.timedelta'``.
        A tela sempre manda o momento da abertura; este é o outro caminho.
        """
        interessado = self.context.servidor_solicitante.get_user()
        chamado = Chamado(
            descricao='Chamado criado por ORM, sem aberto_em explícito.',
            servico=self.context.servico,
            aberto_por=interessado,
            requisitante=interessado,
            interessado=interessado,
            campus=self.context.campus_referencia,
            meio_abertura=Chamado.MEIO_ABERTURA_WEB,
        )
        chamado.centro_atendimento = self.context.centro_atendimento
        chamado.save()

        assert chamado.pk is not None, 'o chamado não foi criado'
        assert chamado.aberto_em is not None, 'o insert deveria preencher aberto_em (auto_now_add)'
        assert chamado.data_limite_atendimento is not None, 'a data limite não foi calculada'
        assert chamado.data_limite_atendimento >= chamado.aberto_em, 'a data limite não pode ser anterior à abertura'

    def test_solicitante_consegue_abrir_chamado_para_servico_disponivel(self):
        self._login_como_solicitante()

        selecionar_servico_url = reverse('centralservicos_selecionar_servico_abertura', args=[self.context.area.slug])
        response = self.client.get(selecionar_servico_url)

        assert response.status_code == 200
        assert f'Abrir chamado para {self.context.area.nome}' in response.content.decode()

        abrir_chamado_url = reverse('centralservicos_abrir_chamado', args=[self.context.servico.id])
        response = self.client.get(abrir_chamado_url)

        assert response.status_code == 200
        assert self.context.servico.nome in response.content.decode()

        data = {
            'descricao': 'Nihil illo? Sunt purus, iusto, erat litora, adipisci eu amet!',
            'interessado': self.context.servidor_solicitante.get_user().pk,
            'requisitante': self.context.servidor_solicitante.get_user().pk,
            'uo': self.context.campus_referencia.pk,
            'centro_atendimento': self.context.centro_atendimento.pk,
            'meio_abertura': Chamado.MEIO_ABERTURA_TELEFONE,
            'chamadoanexo_set-TOTAL_FORMS': '0',
            'chamadoanexo_set-INITIAL_FORMS': '0',
            'chamadoanexo_set-TOTAL_FORM_COUNT': '',
        }

        quantidade_antes = Chamado.objects.count()
        self.client.post(abrir_chamado_url, data)

        assert Chamado.objects.count() == quantidade_antes + 1, 'Deve criar novo chamado quando formulario valido'

    def test_atendente_pode_assumir_colocar_em_atendimento_e_resolver_chamado(self):
        chamado = self.context.chamado
        base_conhecimento = self.context.base_conhecimento

        atribuicao = chamado.get_atendimento_atribuicao_atual()
        assert atribuicao.atribuido_para is None, 'Chamado inicia sem atendente atribuido'

        self._login_como_atendente()

        assumir_url = reverse('centralservicos_auto_atribuir_chamado', args=[chamado.id])
        self.client.post(assumir_url)
        chamado = Chamado.objects.get(pk=chamado.pk)

        atribuicao = chamado.get_atendimento_atribuicao_atual()
        assert atribuicao.atribuido_para == self.context.servidor_atendente.get_user(), 'Assumir chamado define atendente atual'

        colocar_em_atendimento_url = reverse('centralservicos_colocar_em_atendimento', args=[chamado.id])
        response = self.client.post(colocar_em_atendimento_url)

        self._assert_no_validation_errors(response)
        status_recente = HistoricoStatus.objects.latest('data_hora')
        assert status_recente.status == STATUS_EM_ATENDIMENTO, 'Colocar em atendimento grava historico correto'

        resolver_url = reverse('centralservicos_resolver_chamado', args=[chamado.id])
        response = self.client.post(
            resolver_url,
            {
                'bases_conhecimento': [base_conhecimento.id],
                'comentario': 'Facere aliquam, et adipisci fugit corporis, ridiculus accusantium eros.',
            },
        )

        self._assert_no_validation_errors(response)
        assert response.status_code == 302
        assert response.headers['Location'] == chamado.get_absolute_url(), 'Resolver chamado deve redirecionar para detalhe'

        status_recente = HistoricoStatus.objects.latest('data_hora')
        assert status_recente.status == STATUS_RESOLVIDO, 'Resolver chamado grava status resolvido no historico'


class TestAssumirChamado:
    """``auto_atribuir_chamado`` segue a mesma regra do botão "Assumir" (``Chamado.pode_assumir``).

    A permissão ``add_auto_atribuicao`` vem do grupo "Atendente da Central de Serviços", que todo
    atendente de qualquer grupo de atendimento tem; sem a checagem na view, um atendente de outro
    grupo assumia pela URL o chamado que nem aparece para ele, inclusive um chamado cancelado.
    """

    @pytest.fixture(autouse=True)
    def _setup(self, centralservicos_context):
        self.context = centralservicos_context
        self.client = centralservicos_context.client
        self.chamado = centralservicos_context.chamado
        self.url = reverse('centralservicos_auto_atribuir_chamado', args=[self.chamado.id])

    def _atendente_de_outro_grupo(self):
        """Atendente de um grupo de outro centro: tem ``add_auto_atribuicao``, mas não atende o chamado."""
        outro_centro = CentroAtendimento.objects.create(nome='Centro de Atendimento 02', eh_local=True, area=self.context.area)
        outro_grupo = GrupoAtendimento.objects.create(
            nome='Grupo Atendimento 02', campus=self.context.campus_referencia, centro_atendimento=outro_centro
        )
        usuario = ServidorFactory(setor=self.context.servidor_atendente.setor).get_user()
        outro_grupo.responsaveis.add(usuario)
        outro_grupo.atendentes.add(usuario)
        assert usuario.has_perm('centralservicos.add_auto_atribuicao'), 'o atendente de outro grupo deveria ter a permissão da URL'
        return usuario

    def _login(self, usuario):
        self.client.logout()
        assert self.client.login(user=usuario)

    def _atribuicoes(self):
        return list(AtendimentoAtribuicao.objects.filter(chamado=self.chamado).values_list('id', 'atribuido_para_id', 'cancelado_em'))

    def test_atendente_do_grupo_do_chamado_assume(self):
        atendente = self.context.servidor_atendente.get_user()
        self._login(atendente)

        response = self.client.get(self.url)

        assert response.status_code == 302
        assert self.chamado.get_atendimento_atribuicao_atual().atribuido_para == atendente, 'o atendente do grupo deveria assumir o chamado'

    def test_atendente_de_outro_grupo_nao_assume_pela_url(self):
        atribuicoes_antes = self._atribuicoes()
        self._login(self._atendente_de_outro_grupo())

        response = self.client.get(self.url)

        assert response.status_code == 302
        assert self._atribuicoes() == atribuicoes_antes, 'o atendente de outro grupo não pode mudar a atribuição do chamado'
        assert self.chamado.get_atendimento_atribuicao_atual().atribuido_para is None
        assert [m.level_tag for m in get_messages(response.wsgi_request)] == ['error']

    def test_chamado_cancelado_nao_pode_ser_assumido(self):
        Chamado.objects.filter(pk=self.chamado.pk).update(status=StatusChamado.CANCELADO)
        atribuicoes_antes = self._atribuicoes()
        self._login(self.context.servidor_atendente.get_user())

        response = self.client.get(self.url)

        assert response.status_code == 302
        assert self._atribuicoes() == atribuicoes_antes, 'chamado cancelado não pode ganhar atendente'
        assert [m.level_tag for m in get_messages(response.wsgi_request)] == ['error']
