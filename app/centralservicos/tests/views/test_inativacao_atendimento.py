from unittest import mock

import pytest
from django.contrib import admin
from django.core.exceptions import ValidationError
from django.test import RequestFactory
from django.urls import reverse
from django.utils import timezone

from centralservicos.admin import MonitoramentoAdmin
from centralservicos.forms import CentroAtendimentoForm, GrupoAtendimentoForm, GrupoInteressadoForm
from centralservicos.models import Chamado, CentroAtendimento, GrupoAtendimento, Monitoramento


class TestInativacaoCentroAtendimento:
    @pytest.fixture(autouse=True)
    def _setup(self, centralservicos_context):
        self.context = centralservicos_context

    def test_nao_permite_inativar_centro_atendimento_com_servico_ativo_vinculado(self):
        centro = self.context.centro_atendimento
        centro.ativo = False

        with pytest.raises(ValidationError):
            centro.full_clean()

    def test_permite_inativar_centro_atendimento_sem_servico_ativo_vinculado(self):
        servico = self.context.servico
        servico.ativo = False
        servico.save()

        centro = self.context.centro_atendimento
        centro.ativo = False
        centro.full_clean()
        centro.save()

        centro.refresh_from_db()
        assert centro.ativo is False


class TestInativacaoGrupoAtendimento:
    @pytest.fixture(autouse=True)
    def _setup(self, centralservicos_context):
        self.context = centralservicos_context
        self.grupo = GrupoAtendimento.objects.get(centro_atendimento=self.context.centro_atendimento)

    def test_nao_permite_inativar_grupo_atendimento_com_servico_ativo_vinculado_ao_centro(self):
        grupo = self.grupo
        grupo.ativo = False

        with pytest.raises(ValidationError):
            grupo.full_clean()

    def test_permite_inativar_grupo_atendimento_sem_servico_ativo_vinculado_ao_centro(self):
        servico = self.context.servico
        servico.ativo = False
        servico.save()

        grupo = self.grupo
        grupo.ativo = False
        grupo.full_clean()
        grupo.save()

        grupo.refresh_from_db()
        assert grupo.ativo is False


class TestFormularioAdminInativacao:
    @pytest.fixture(autouse=True)
    def _setup(self, centralservicos_context):
        self.context = centralservicos_context
        self.grupo = GrupoAtendimento.objects.get(centro_atendimento=self.context.centro_atendimento)

    def test_form_centro_atendimento_recusa_inativacao_com_servico_ativo(self):
        centro = self.context.centro_atendimento
        form = CentroAtendimentoForm(
            instance=centro,
            data={'nome': centro.nome, 'eh_local': centro.eh_local, 'area': centro.area_id, 'ativo': False},
        )

        assert form.is_valid() is False
        assert 'Não é possível inativar' in str(form.errors)

    def test_form_grupo_atendimento_recusa_inativacao_com_servico_ativo(self):
        grupo = self.grupo
        form = GrupoAtendimentoForm(
            instance=grupo,
            data={
                'nome': grupo.nome,
                'campus': grupo.campus_id,
                'centro_atendimento': grupo.centro_atendimento_id,
                'responsaveis': [str(self.context.servidor_atendente.get_user().pk)],
                'ativo': False,
            },
        )

        assert form.is_valid() is False
        assert 'Não é possível inativar' in str(form.errors)


class TestRoteamentoChamadoParaGrupoInativo:
    @pytest.fixture(autouse=True)
    def _setup(self, centralservicos_context):
        self.context = centralservicos_context
        self.grupo = GrupoAtendimento.objects.get(centro_atendimento=self.context.centro_atendimento)

    def _novo_chamado(self):
        chamado = Chamado(
            descricao='Chamado de teste para roteamento de grupo inativo.',
            servico=self.context.servico,
            aberto_em=timezone.now(),
            aberto_por=self.context.servidor_solicitante.get_user(),
            interessado=self.context.servidor_solicitante.get_user(),
            requisitante=self.context.servidor_solicitante.get_user(),
            campus=self.context.campus_referencia,
            meio_abertura=Chamado.MEIO_ABERTURA_TELEFONE,
        )
        chamado.centro_atendimento = self.context.centro_atendimento
        return chamado

    def test_nao_permite_abrir_chamado_quando_unico_grupo_de_atendimento_do_campus_esta_inativo(self):
        self.grupo.ativo = False
        self.grupo.save()

        with pytest.raises(ValidationError):
            self._novo_chamado().save()

    def test_permite_abrir_chamado_quando_grupo_de_atendimento_do_campus_esta_ativo(self):
        quantidade_antes = Chamado.objects.count()

        self._novo_chamado().save()

        assert Chamado.objects.count() == quantidade_antes + 1


class TestDisponibilidadeCentroAtendimentoParaAbrirChamado:
    @pytest.fixture(autouse=True)
    def _setup(self, centralservicos_context):
        self.context = centralservicos_context
        self.grupo = GrupoAtendimento.objects.get(centro_atendimento=self.context.centro_atendimento)

    def test_lista_centro_atendimento_ativo_com_grupo_ativo_no_campus(self):
        centros = self.context.servico.get_centros_atendimento(self.context.campus_referencia.id)

        assert self.context.centro_atendimento in centros

    def test_nao_lista_centro_atendimento_inativo(self):
        centro = self.context.centro_atendimento
        centro.ativo = False
        centro.save()

        centros = self.context.servico.get_centros_atendimento(self.context.campus_referencia.id)

        assert centro not in centros

    def test_nao_lista_centro_atendimento_local_sem_grupo_ativo_no_campus(self):
        self.grupo.ativo = False
        self.grupo.save()

        centros = self.context.servico.get_centros_atendimento(self.context.campus_referencia.id)

        assert self.context.centro_atendimento not in centros

    def test_lista_centro_atendimento_nao_local_com_grupo_ativo(self):
        centro_nao_local = CentroAtendimento.objects.create(nome='Centro Não Local 01', eh_local=False, area=self.context.area)
        self.context.servico.centros_atendimento.add(centro_nao_local)
        GrupoAtendimento.objects.create(nome='Grupo Não Local 01', campus=self.context.campus_referencia, centro_atendimento=centro_nao_local)

        centros = self.context.servico.get_centros_atendimento(self.context.campus_referencia.id)

        assert centro_nao_local in centros

    def test_nao_lista_centro_atendimento_nao_local_sem_grupo_ativo(self):
        centro_nao_local = CentroAtendimento.objects.create(nome='Centro Não Local 01', eh_local=False, area=self.context.area)
        self.context.servico.centros_atendimento.add(centro_nao_local)
        grupo_nao_local = GrupoAtendimento.objects.create(
            nome='Grupo Não Local 01', campus=self.context.campus_referencia, centro_atendimento=centro_nao_local
        )
        grupo_nao_local.ativo = False
        grupo_nao_local.save()

        centros = self.context.servico.get_centros_atendimento(self.context.campus_referencia.id)

        assert centro_nao_local not in centros


class TestCampusDisponiveisParaAtendimento:
    @pytest.fixture(autouse=True)
    def _setup(self, centralservicos_context):
        self.context = centralservicos_context
        self.grupo = GrupoAtendimento.objects.get(centro_atendimento=self.context.centro_atendimento)

    def test_lista_campus_com_grupo_de_atendimento_ativo(self):
        campi = self.context.servico.get_campus_disponiveis_para_atendimento()

        assert self.context.campus_referencia in campi

    def test_nao_lista_campus_quando_grupo_de_atendimento_esta_inativo(self):
        self.grupo.ativo = False
        self.grupo.save()

        campi = self.context.servico.get_campus_disponiveis_para_atendimento()

        assert self.context.campus_referencia not in campi

    def test_nao_lista_campus_quando_centro_atendimento_esta_inativo(self):
        centro = self.context.centro_atendimento
        centro.ativo = False
        centro.save()

        campi = self.context.servico.get_campus_disponiveis_para_atendimento()

        assert self.context.campus_referencia not in campi


class TestFormularioAberturaChamadoRespeitaInativacao:
    @pytest.fixture(autouse=True)
    def _setup(self, centralservicos_context):
        self.context = centralservicos_context
        self.client = centralservicos_context.client

    def test_servico_com_grupo_atendimento_inativo_nao_permite_abrir_chamado(self):
        centro = self.context.centro_atendimento
        # Inviabiliza todos os grupos de atendimento relacionados ao centro de atendimento.
        centro.ativo = False
        centro.save()

        self.client.logout()
        assert self.client.login(user=self.context.servidor_solicitante.get_user())

        abrir_chamado_url = reverse('centralservicos_abrir_chamado', args=[self.context.servico.id])
        response = self.client.get(abrir_chamado_url)

        assert response.status_code == 302  # redirect

    def test_centro_atendimento_inativo_nao_aparece_como_opcao_para_reclassificar_chamado(self):
        centro = self.context.centro_atendimento
        centro.ativo = False
        centro.save()

        self.client.logout()
        assert self.client.login(user=self.context.servidor_atendente.get_user())

        reclassificar_chamado_url = f'/centralservicos/reclassificar_chamado/{self.context.chamado.id}/'
        response = self.client.get(reclassificar_chamado_url)

        assert response.status_code == 200
        assert centro.nome not in response.content.decode()


class TestPermissaoChamadoInternoComGrupoInativo:
    @pytest.fixture(autouse=True)
    def _setup(self, centralservicos_context):
        self.context = centralservicos_context
        self.client = centralservicos_context.client
        self.grupo = GrupoAtendimento.objects.get(centro_atendimento=self.context.centro_atendimento)

        servico = self.context.servico
        servico.interno = True
        servico.save()

    def test_atendente_nao_abre_chamado_interno_quando_seu_unico_grupo_esta_inativo(self):
        self.grupo.ativo = False
        self.grupo.save()

        self.client.logout()
        assert self.client.login(user=self.context.servidor_atendente.get_user())

        abrir_chamado_url = reverse('centralservicos_abrir_chamado', args=[self.context.servico.id])
        response = self.client.get(abrir_chamado_url)

        assert response.status_code == 403

    def test_atendente_abre_chamado_interno_quando_seu_grupo_esta_ativo(self):
        self.client.logout()
        assert self.client.login(user=self.context.servidor_atendente.get_user())

        abrir_chamado_url = reverse('centralservicos_abrir_chamado', args=[self.context.servico.id])
        response = self.client.get(abrir_chamado_url)

        assert response.status_code == 200


class TestGrupoInativoNaoApareceEmNovosFormularios:
    @pytest.fixture(autouse=True)
    def _setup(self, centralservicos_context):
        self.context = centralservicos_context
        self.grupo = GrupoAtendimento.objects.get(centro_atendimento=self.context.centro_atendimento)
        self.atendente = self.context.servidor_atendente.get_user()

    def test_grupo_interessado_form_nao_lista_grupo_atendimento_inativo(self):
        self.grupo.ativo = False
        self.grupo.save()

        with mock.patch.object(GrupoInteressadoForm, 'request', RequestFactory().get('/'), create=True):
            GrupoInteressadoForm.request.user = self.atendente
            form = GrupoInteressadoForm()

        assert self.grupo not in form.fields['grupo_atendimento'].queryset

    def test_grupo_interessado_form_lista_grupo_atendimento_ativo(self):
        with mock.patch.object(GrupoInteressadoForm, 'request', RequestFactory().get('/'), create=True):
            GrupoInteressadoForm.request.user = self.atendente
            form = GrupoInteressadoForm()

        assert self.grupo in form.fields['grupo_atendimento'].queryset

    def test_monitoramento_admin_form_nao_lista_grupo_atendimento_inativo(self):
        self.grupo.ativo = False
        self.grupo.save()

        request = RequestFactory().get('/')
        request.user = self.atendente
        FormClass = MonitoramentoAdmin(Monitoramento, admin.site).get_form(request)

        assert self.grupo not in FormClass.base_fields['grupos'].queryset

    def test_monitoramento_admin_form_lista_grupo_atendimento_ativo(self):
        request = RequestFactory().get('/')
        request.user = self.atendente
        FormClass = MonitoramentoAdmin(Monitoramento, admin.site).get_form(request)

        assert self.grupo in FormClass.base_fields['grupos'].queryset
