"""Testes das travas do formulário de alteração do ProcessoRSCTae no admin.

O admin é a única porta que aceitava escrever ``situacao`` e ``avaliadores`` livremente:
sem passar por ``transicionar()`` (nenhum histórico gravado, processo indo para o topo da
fila em vez do fim) e sem limpar as avaliações de quem saía do M2M.

As travas aqui são de validação — os campos continuam editáveis. Remover avaliador passa a
ser recusado pelo formulário e apontado para o command, que faz a limpeza completa.
"""

import pytest
from django.contrib.admin.sites import AdminSite
from django.forms.models import model_to_dict
from django.test import RequestFactory

from rsc_tae.admin.processo import ProcessoRSCTaeAdmin
from rsc_tae.enums import SituacaoProcesso
from rsc_tae.forms import ProcessoRSCTaeAdminForm
from rsc_tae.models import HistoricoSituacaoProcessoRSCTae, Nivel, ProcessoRSCTae


@pytest.mark.django_db(databases='__all__')
class TestGuardasAdminProcesso:
    databases = '__all__'

    @pytest.fixture(autouse=True)
    def _setup(self, atores):
        nivel = Nivel.objects.create(nome='Nível Teste', numero_minimo_itens=0, pontuacao_minima=0)
        self.processo = ProcessoRSCTae.objects.create(
            vinculo=self.servidor_a.get_vinculo(),
            nivel_requisitado=nivel,
            situacao=SituacaoProcesso.EM_ANALISE,
        )
        self.tres = [self.servidor_b.get_vinculo(), self.servidor_c.get_vinculo(), self.servidor_d.get_vinculo()]
        self.processo.avaliadores.set(self.tres)

    def _form(self, **overrides):
        dados = {campo: valor for campo, valor in model_to_dict(self.processo).items() if valor is not None}
        # pks como string: é assim que chegam de um POST, e o MultipleModelChoiceFieldPlus
        # compara os valores enviados com os do queryset em texto.
        dados['avaliadores'] = [str(v.pk) for v in self.processo.avaliadores.all()]
        dados.update(overrides)
        return ProcessoRSCTaeAdminForm(data=dados, instance=self.processo)

    # ------------------------------------------------------------------ avaliadores

    def test_aceita_os_tres_avaliadores_atuais(self):
        assert self._form().is_valid()

    def test_rejeita_mais_de_tres_avaliadores(self):
        form = self._form(avaliadores=[str(v.pk) for v in [*self.tres, self.admin.get_vinculo()]])

        assert not form.is_valid()
        assert 'três' in str(form.errors['avaliadores'])

    def test_rejeita_remocao_apontando_o_comando(self):
        """Remover pelo M2M deixaria as avaliações do removido ativas — o command é quem limpa."""
        form = self._form(avaliadores=[str(v.pk) for v in self.tres[:2]])

        assert not form.is_valid()
        assert 'remover_avaliador_processo' in str(form.errors['avaliadores'])

    # ------------------------------------------------------------------ situação

    def test_rejeita_transicao_invalida(self):
        form = self._form(situacao=SituacaoProcesso.AGUARDANDO_PREENCHIMENTO)

        assert not form.is_valid()
        assert 'não é uma transição válida' in str(form.errors['situacao'])

    def test_aceita_transicao_valida(self):
        assert self._form(situacao=SituacaoProcesso.AGUARDANDO_CRSC).is_valid()

    def test_save_model_grava_historico_da_transicao(self):
        """Sem isso, a situação mudava sem registro e o processo ia para o topo da fila da etapa."""
        form = self._form(situacao=SituacaoProcesso.AGUARDANDO_CRSC)
        assert form.is_valid()

        request = RequestFactory().post('/')
        request.user = self.servidor_b.get_user()
        ProcessoRSCTaeAdmin(ProcessoRSCTae, AdminSite()).save_model(request, form.instance, form, change=True)

        self.processo.refresh_from_db()
        assert self.processo.situacao == SituacaoProcesso.AGUARDANDO_CRSC
        registro = HistoricoSituacaoProcessoRSCTae.objects.filter(processo=self.processo).latest('data_transicao')
        assert registro.situacao_anterior == SituacaoProcesso.EM_ANALISE
        assert registro.situacao_nova == SituacaoProcesso.AGUARDANDO_CRSC
        assert registro.realizado_por_vinculo_id == self.servidor_b.get_vinculo().id

    def test_save_model_sem_mudanca_de_situacao_nao_gera_historico(self):
        form = self._form()
        assert form.is_valid()

        request = RequestFactory().post('/')
        request.user = self.servidor_b.get_user()
        ProcessoRSCTaeAdmin(ProcessoRSCTae, AdminSite()).save_model(request, form.instance, form, change=True)

        assert not HistoricoSituacaoProcessoRSCTae.objects.filter(processo=self.processo).exists()

    def test_rejeita_transicao_para_estado_final(self):
        """Deferir é transição válida a partir da CRSC, mas só pelo rito colegiado — não pelo admin."""
        self.processo.situacao = SituacaoProcesso.AGUARDANDO_CRSC
        self.processo.save()

        form = self._form(situacao=SituacaoProcesso.DEFERIDO)

        assert not form.is_valid()
        assert 'deliberação' in str(form.errors['situacao'])

    def test_rejeita_saida_de_processo_finalizado(self):
        self.processo.situacao = SituacaoProcesso.DEFERIDO
        self.processo.save()

        form = self._form(situacao=SituacaoProcesso.AGUARDANDO_CRSC)

        assert not form.is_valid()
        assert 'reverter_deliberacao_final' in str(form.errors['situacao'])
