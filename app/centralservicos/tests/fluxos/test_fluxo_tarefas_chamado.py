"""Fluxo das tarefas vinculadas a um chamado (#17792, #17794).

Regra: o chamado só chega a Resolvido (e, daí, a Fechado) sem tarefa pendente — aberta, em andamento
ou suspensa. Finalizar a última tarefa não muda a situação do chamado: libera o atendente para
resolvê-lo. Nenhuma via de encerramento contorna essa regra, e uma tarefa que ficou pendente num
chamado já encerrado continua podendo ser finalizada ou cancelada.
"""

from django.apps.registry import apps
from django.urls import reverse
from django.utils import timezone
import pytest

from centralservicos.models import Chamado, StatusChamado, TarefaChamado
from centralservicos.tests.factories import TarefaFactory
from rh.tests.factories import ServidorFactory

Group = apps.get_model('auth', 'Group')


class TestFluxoTarefasChamado:
    @pytest.fixture(autouse=True)
    def _setup(self, centralservicos_context):
        self.ctx = centralservicos_context
        self.client = centralservicos_context.client
        self.atendente = self.ctx.servidor_atendente.get_user()
        self.grupo = self.ctx.chamado.get_atendimento_atribuicao_atual().grupo_atendimento

        self.colega = ServidorFactory(setor=self.ctx.servidor_atendente.setor).get_user()
        self.colega.groups.add(Group.objects.get(name='Atendente da Central de Serviços'))
        self.grupo.atendentes.add(self.colega)

        self.tarefa = TarefaFactory(servico=self.ctx.servico)
        self.chamado = self._em_atendimento(self.ctx.chamado)

    def _em_atendimento(self, chamado: Chamado) -> Chamado:
        chamado.atribuir_atendente(self.grupo, self.atendente, self.atendente)
        chamado.colocar_em_atendimento(self.atendente)
        return Chamado.objects.get(pk=chamado.pk)

    def _novo_chamado_em_atendimento(self) -> Chamado:
        solicitante = self.ctx.servidor_solicitante.get_user()
        chamado = Chamado(
            descricao='Outro chamado do mesmo serviço.',
            servico=self.ctx.servico,
            aberto_em=timezone.now(),
            aberto_por=solicitante,
            interessado=solicitante,
            requisitante=solicitante,
            campus=self.ctx.campus_referencia,
            meio_abertura=Chamado.MEIO_ABERTURA_TELEFONE,
        )
        chamado.centro_atendimento = self.ctx.centro_atendimento
        chamado.save()
        return self._em_atendimento(chamado)

    def _login(self, user):
        self.client.logout()
        assert self.client.login(user=user)

    def _vincular(self, chamado: Chamado, responsavel) -> TarefaChamado:
        self._login(self.atendente)
        response = self.client.post(
            reverse('centralservicos_vincular_tarefa_chamado', args=[chamado.id]),
            {'tarefa': self.tarefa.id, 'responsavel': responsavel.id, 'situacao': TarefaChamado.SITUACAO_ABERTA},
        )
        assert response.status_code == 302, 'a tarefa deveria ter sido vinculada'
        return TarefaChamado.objects.filter(chamado=chamado).latest('id')

    def _alterar(self, tarefa_chamado: TarefaChamado, user, situacao: str):
        self._login(user)
        return self.client.post(
            reverse('centralservicos_editar_tarefa_chamado', args=[tarefa_chamado.id]),
            {'situacao': situacao, 'responsavel': tarefa_chamado.responsavel_id},
        )

    def _resolver(self, chamado: Chamado, outros: list[Chamado] | None = None):
        self._login(self.atendente)
        dados = {'bases_conhecimento': [self.ctx.base_conhecimento.id], 'comentario': 'Resolvido.'}
        if outros:
            dados['outros_chamados_a_resolver'] = [c.id for c in outros]
        return self.client.post(reverse('centralservicos_resolver_chamado', args=[chamado.id]), dados)

    def _status(self, chamado: Chamado) -> int:
        return Chamado.objects.get(pk=chamado.pk).status

    def _situacao(self, tarefa_chamado: TarefaChamado) -> str:
        return TarefaChamado.objects.get(pk=tarefa_chamado.pk).situacao

    def test_finalizar_tarefa_com_outra_pendente_nao_encerra_nem_libera_o_chamado(self):
        tarefa_do_atendente = self._vincular(self.chamado, self.atendente)
        self._vincular(self.chamado, self.colega)

        response = self._alterar(tarefa_do_atendente, self.atendente, TarefaChamado.SITUACAO_FINALIZADA)

        assert response.status_code == 302
        assert self._situacao(tarefa_do_atendente) == TarefaChamado.SITUACAO_FINALIZADA
        assert self._status(self.chamado) == StatusChamado.get_status_em_atendimento(), 'finalizar uma tarefa não pode encerrar o chamado'
        assert self._resolver(self.chamado).status_code == 403, 'com tarefa pendente o chamado não pode ser resolvido'
        assert self._status(self.chamado) == StatusChamado.get_status_em_atendimento()

    def test_finalizar_a_ultima_tarefa_libera_a_resolucao_do_chamado(self):
        tarefa_do_atendente = self._vincular(self.chamado, self.atendente)
        tarefa_do_colega = self._vincular(self.chamado, self.colega)

        self._alterar(tarefa_do_atendente, self.atendente, TarefaChamado.SITUACAO_FINALIZADA)
        self._alterar(tarefa_do_colega, self.colega, TarefaChamado.SITUACAO_CANCELADA)

        assert self._status(self.chamado) == StatusChamado.get_status_em_atendimento(), (
            'o chamado não se resolve sozinho: quem resolve é o atendente, com as bases de conhecimento'
        )
        assert self._resolver(self.chamado).status_code == 302
        assert self._status(self.chamado) == StatusChamado.get_status_resolvido()

    def test_resolver_em_conjunto_nao_resolve_outro_chamado_com_tarefa_pendente(self):
        outro_chamado = self._novo_chamado_em_atendimento()
        tarefa_pendente = self._vincular(outro_chamado, self.colega)

        response = self._resolver(self.chamado, outros=[outro_chamado])

        assert response.status_code == 302
        assert self._status(self.chamado) == StatusChamado.get_status_resolvido()
        assert self._status(outro_chamado) == StatusChamado.get_status_em_atendimento(), (
            'o chamado com tarefa pendente não pode ser resolvido junto com o principal'
        )
        assert self._situacao(tarefa_pendente) == TarefaChamado.SITUACAO_ABERTA

    def test_criar_processo_nao_e_oferecido_com_tarefa_pendente(self):
        self.atendente.groups.add(Group.objects.get(name='Operador de Processo Eletrônico'))
        assert self.chamado.pode_criar_processo(type(self.atendente).objects.get(pk=self.atendente.pk)), 'pré-condição: sem tarefa, pode criar'
        self._vincular(self.chamado, self.colega)

        response = self.client.get(f'/centralservicos/criar_processo_de_chamado/{self.chamado.id}/')

        assert response.status_code == 302, 'criar processo resolve e fecha o chamado: não pode haver tarefa pendente'
        assert self._status(self.chamado) == StatusChamado.get_status_em_atendimento()

    def test_cancelar_o_chamado_cancela_as_tarefas_pendentes(self):
        tarefa_pendente = self._vincular(self.chamado, self.colega)
        tarefa_finalizada = self._vincular(self.chamado, self.atendente)
        self._alterar(tarefa_finalizada, self.atendente, TarefaChamado.SITUACAO_FINALIZADA)

        self._login(self.atendente)
        response = self.client.post(reverse('centralservicos_cancelar_chamado', args=[self.chamado.id]), {'observacao': 'Não procede.'})

        assert response.status_code == 302
        assert self._status(self.chamado) == StatusChamado.get_status_cancelado()
        assert self._situacao(tarefa_pendente) == TarefaChamado.SITUACAO_CANCELADA, 'tarefa de chamado cancelado não pode ficar pendente'
        assert self._situacao(tarefa_finalizada) == TarefaChamado.SITUACAO_FINALIZADA
        assert not TarefaChamado.get_tarefas_vinculadas_ativas(self.colega).exists()

    def test_chamado_resolvido_nao_recebe_nem_reabre_tarefa(self):
        tarefa = self._vincular(self.chamado, self.atendente)
        self._alterar(tarefa, self.atendente, TarefaChamado.SITUACAO_FINALIZADA)
        self._resolver(self.chamado)
        assert self._status(self.chamado) == StatusChamado.get_status_resolvido()

        self._login(self.atendente)
        response = self.client.get(reverse('centralservicos_vincular_tarefa_chamado', args=[self.chamado.id]))
        assert response.status_code == 403, 'chamado resolvido não recebe tarefa nova'

        self._alterar(tarefa, self.atendente, TarefaChamado.SITUACAO_ABERTA)
        assert self._situacao(tarefa) == TarefaChamado.SITUACAO_FINALIZADA, 'tarefa de chamado resolvido não volta a ficar pendente'

    def test_tarefa_pendente_em_chamado_fechado_pode_ser_finalizada_pelo_responsavel_fora_do_grupo(self):
        """#17794: o responsável saiu do grupo de atendimento atual e o chamado já foi fechado."""
        tarefa = self._vincular(self.chamado, self.colega)
        Chamado.objects.filter(pk=self.chamado.pk).update(status=StatusChamado.get_status_fechado())  # dado legado
        self.grupo.atendentes.remove(self.colega)

        response = self._alterar(tarefa, self.colega, TarefaChamado.SITUACAO_FINALIZADA)

        assert response.status_code == 302, 'o responsável atual da tarefa tem de continuar válido no formulário'
        assert self._situacao(tarefa) == TarefaChamado.SITUACAO_FINALIZADA

    def test_tarefa_pendente_em_chamado_fechado_pode_ser_encerrada_pelo_atendente_do_chamado(self):
        """#17794: o atendente do chamado encerra a tarefa que ficou pendente com outro responsável."""
        tarefa = self._vincular(self.chamado, self.colega)
        Chamado.objects.filter(pk=self.chamado.pk).update(status=StatusChamado.get_status_fechado())  # dado legado

        response = self._alterar(tarefa, self.atendente, TarefaChamado.SITUACAO_CANCELADA)

        assert response.status_code == 302
        assert self._situacao(tarefa) == TarefaChamado.SITUACAO_CANCELADA
        assert TarefaChamado.objects.get(pk=tarefa.pk).responsavel == self.colega, 'encerrar a tarefa não troca o responsável'

    def test_outro_atendente_do_grupo_nao_altera_tarefa_alheia(self):
        tarefa = self._vincular(self.chamado, self.atendente)

        response = self._alterar(tarefa, self.colega, TarefaChamado.SITUACAO_FINALIZADA)

        assert response.status_code == 403
        assert self._situacao(tarefa) == TarefaChamado.SITUACAO_ABERTA
