from decimal import Decimal
from unittest import mock

import pytest

from comum.models import Ano
from djtools.forms import FormPlus
from financeiro.models import ClassificacaoInstitucional
from rh.models import Setor
from django.core.exceptions import ValidationError

from plan_estrategico.forms import (
    EmitirCDOForm,
    ReforcoEmpenhoForm,
    RequisicaoAnulacaoEmpenhoForm,
    configurar_textos_encaminhamento_cdo,
    validar_destino_emissao_cdo,
    validar_setor_destino_cdo,
)
from plan_estrategico.models import (
    AtividadeEtapa,
    NaturezaDespesaPlanoAtividade,
    NotaEmpenho,
    PlanoAtividade,
    RequisicaoDespesa,
    UnidadeGestora,
)


pytestmark = pytest.mark.django_db


class ReforcoEmpenhoFormTest:
    def get_nota_empenho(self):
        requisicao = RequisicaoDespesa(
            tipo_requisicao=RequisicaoDespesa.TIPO_DOTACAO_EMPENHO,
            status=RequisicaoDespesa.STATUS_AGUARDANDO_EMISSAO_EMPENHO,
            valor_inicial=Decimal('20000.00'),
        )
        requisicao.plano_atividade = PlanoAtividade(ano_base=Ano(ano=2025))
        requisicao.atividade = AtividadeEtapa()
        requisicao.atividade.unidade_gestora = UnidadeGestora(codigo_ug=158155)

        nota_empenho = NotaEmpenho(numero_empenho='158155264352025NE000123', valor=Decimal('20000.00'))
        nota_empenho.requisicao = requisicao
        nota_empenho.naturezadespesa = NaturezaDespesaPlanoAtividade()
        return nota_empenho

    def get_form(self, dados=None, total_das_linhas=Decimal('19000.00')):
        nota_empenho = self.get_nota_empenho()
        with (
            mock.patch.object(
                ClassificacaoInstitucional.objects,
                'get',
                return_value=ClassificacaoInstitucional(codigo='26435'),
            ),
            mock.patch.object(RequisicaoDespesa, 'total_naturezas_despesa', return_value=total_das_linhas),
        ):
            form = ReforcoEmpenhoForm(dados, nota_empenho=nota_empenho, request=mock.Mock())
            if dados:
                form.is_valid()
        return nota_empenho, form

    def get_dados(self, valor):
        return {'unidade': '', 'unidade_orcamentaria': '', 'ano': '2025', 'documento_siafi': '000999', 'valor': valor}

    def test_reforco_e_lancado_em_uma_nova_linha(self):
        nota_empenho, form = self.get_form()

        assert form.instance is not nota_empenho
        assert form.instance.pk is None

    def test_nova_linha_herda_natureza_de_despesa_e_numero_do_empenho(self):
        nota_empenho, form = self.get_form()

        assert form.instance.numero_empenho == nota_empenho.numero_empenho
        assert form.instance.naturezadespesa is nota_empenho.naturezadespesa
        assert form.instance.requisicao is nota_empenho.requisicao

    def test_recusa_reforco_sem_valor_positivo(self):
        _, form = self.get_form(self.get_dados('0,00'))

        assert form.errors['valor'] == ['O valor do reforço deve ser maior que zero.']

    def test_recusa_reforco_que_ultrapassa_o_valor_da_requisicao(self):
        _, form = self.get_form(self.get_dados('1500,00'))

        assert form.errors['valor'] == ['Valor maior que o disponível: R$ 1.000,00']

    def test_aceita_reforco_ate_o_valor_da_requisicao(self):
        _, form = self.get_form(self.get_dados('1000,00'))

        assert 'valor' not in form.errors

    def test_recusa_reforco_quando_as_linhas_ja_consomem_o_valor_da_requisicao(self):
        _, form = self.get_form(self.get_dados('0,01'), total_das_linhas=Decimal('20000.00'))

        assert form.errors['valor'] == ['Valor maior que o disponível: R$ 0,00']


class ValidarSetorDestinoCdoTest:
    def get_requisicao(self, ordenador=True, anuencia=True, ua_vinculada=RequisicaoDespesa.UA_PRINCIPAL):
        unidade_gestora = UnidadeGestora(
            setor_ordenador_despesa=Setor(pk=1) if ordenador else None,
            setor_anuencia_despesa=Setor(pk=2) if anuencia else None,
            ug_secundaria='158155',
        )
        unidade_gestora._state.fields_cache['setor_equivalente'] = Setor(pk=3, sigla='CNAT', nome='Campus Natal')
        return RequisicaoDespesa(unidade_gestora=unidade_gestora, ua_vinculada=ua_vinculada)

    def test_setores_configurados(self):
        with (
            mock.patch.object(UnidadeGestora, 'possui_diretor_geral', return_value=False),
            mock.patch.object(UnidadeGestora, 'possui_anuente', return_value=True),
        ):
            validar_setor_destino_cdo(self.get_requisicao())

    def test_sem_anuente_quando_precisa(self):
        with (
            mock.patch.object(UnidadeGestora, 'possui_diretor_geral', return_value=False),
            mock.patch.object(UnidadeGestora, 'possui_anuente', return_value=False),
            pytest.raises(ValidationError, match='Não há servidor com função de Diretor, Diretor-Geral ou Reitor'),
        ):
            validar_setor_destino_cdo(self.get_requisicao())

    def test_sem_ordenador(self):
        with (
            mock.patch.object(UnidadeGestora, 'possui_diretor_geral', return_value=True),
            pytest.raises(ValidationError, match='Setor responsável ordenador de despesa'),
        ):
            validar_setor_destino_cdo(self.get_requisicao(ordenador=False))

    def test_sem_setor_anuencia_segue_para_autorizacao(self):
        with (
            mock.patch.object(UnidadeGestora, 'possui_diretor_geral', return_value=False),
            mock.patch.object(UnidadeGestora, 'possui_anuente', return_value=False),
        ):
            validar_setor_destino_cdo(self.get_requisicao(anuencia=False))

    def test_sem_anuencia_quando_nao_precisa(self):
        with mock.patch.object(UnidadeGestora, 'possui_diretor_geral', return_value=True):
            validar_setor_destino_cdo(self.get_requisicao(anuencia=False))

    def test_ug_secundaria_nao_encontrada(self):
        requisicao = self.get_requisicao(ua_vinculada=RequisicaoDespesa.UA_SECUNDARIA)
        with mock.patch.object(UnidadeGestora, 'get_ug_secundaria', return_value=None), pytest.raises(ValidationError, match='UG Secundária'):
            validar_setor_destino_cdo(requisicao)

    def test_autorizacao_declarada_dispensa_anuencia_e_ordenador(self):
        requisicao = self.get_requisicao(ordenador=False, anuencia=False)
        requisicao.unidade_gestora.setor_financeiro = Setor(pk=4)
        with mock.patch.object(UnidadeGestora, 'possui_diretor_geral', return_value=False) as possui_diretor_geral:
            validar_destino_emissao_cdo(requisicao, autorizacao_declarada=True)
        assert not possui_diretor_geral.called

    def test_autorizacao_declarada_sem_setor_financeiro(self):
        with pytest.raises(ValidationError, match='O setor financeiro não está configurado'):
            validar_destino_emissao_cdo(self.get_requisicao(), autorizacao_declarada=True)

    def test_sem_autorizacao_declarada_valida_anuencia_e_ordenador(self):
        with (
            mock.patch.object(UnidadeGestora, 'possui_diretor_geral', return_value=False),
            pytest.raises(ValidationError, match='Setor responsável ordenador de despesa'),
        ):
            validar_destino_emissao_cdo(self.get_requisicao(ordenador=False), autorizacao_declarada=False)


class RequisicaoAnulacaoEmpenhoFormCleanTest:
    def clean(self, cleaned_data, campos=('empenho', 'processo')):
        form = object.__new__(RequisicaoAnulacaoEmpenhoForm)
        form.fields = dict.fromkeys(campos)
        with (
            mock.patch.object(FormPlus, 'clean', return_value=cleaned_data),
            mock.patch('plan_estrategico.forms.validar_setor_destino_cdo') as validar,
        ):
            form.clean()
        return validar

    def get_empenho(self):
        return mock.Mock(requisicao=mock.Mock(unidade_gestora=UnidadeGestora()))

    def test_valida_setores_no_ultimo_passo(self):
        validar = self.clean({'empenho': self.get_empenho(), 'ua_vinculada': RequisicaoDespesa.UA_SECUNDARIA})
        validar.assert_called_once()
        assert validar.call_args.args[0].ua_vinculada == RequisicaoDespesa.UA_SECUNDARIA

    def test_nao_valida_no_primeiro_passo(self):
        assert not self.clean({'empenho': self.get_empenho()}, campos=('empenho',)).called

    def test_nao_valida_quando_autorizacao_declarada(self):
        validar = self.clean({'empenho': self.get_empenho(), 'autorizacao_ordenador_declarada_no_processo': True})
        assert not validar.called


class TextosEncaminhamentoCdoTest:
    def configurar(self, precisa_anuencia: bool, setor_destino: Setor | None = None, setor_financeiro: Setor | None = None, **kwargs):
        requisicao = mock.Mock()
        requisicao.precisa_anuencia.return_value = precisa_anuencia
        requisicao.get_setor_destino_apos_cdo.return_value = setor_destino
        requisicao.unidade_gestora.setor_financeiro = setor_financeiro
        form = mock.Mock(instance=requisicao, initial={})
        configurar_textos_encaminhamento_cdo(form, 'CDO', **kwargs)
        return form

    def test_com_anuencia(self):
        form = self.configurar(precisa_anuencia=True, setor_destino=Setor(sigla='DAP', nome='Diretoria de Administração'))
        assert form.initial['despacho'] == 'Ao DAP para anuência da realização da respectiva despesa.'
        assert form.despacho_inicial == form.initial['despacho']
        assert 'para anuência da despesa' in form.INFO

    def test_sem_anuencia(self):
        form = self.configurar(precisa_anuencia=False, setor_destino=Setor(sigla='GABIN', nome='Gabinete'))
        assert form.initial['despacho'] == 'Ao GABIN para autorização do ordenador de despesa para a realização da respectiva despesa.'
        assert 'para autorização do ordenador de despesa' in form.INFO

    def test_setor_nao_configurado(self):
        form = self.configurar(precisa_anuencia=False)
        assert form.initial['despacho'].startswith('Ao (setor não configurado)')

    def test_cita_o_setor_financeiro_quando_permite_autorizacao_declarada(self):
        setor_financeiro = Setor(sigla='COFIN', nome='Coordenação de Finanças')
        form = self.configurar(precisa_anuencia=True, setor_destino=Setor(sigla='DAP'), setor_financeiro=setor_financeiro)
        assert 'setor financeiro' not in form.INFO

        form = self.configurar(
            precisa_anuencia=True, setor_destino=Setor(sigla='DAP'), setor_financeiro=setor_financeiro, permite_autorizacao_declarada=True
        )
        assert form.INFO.endswith(
            f'Se for declarada a autorização do ordenador de despesa no processo, o processo será encaminhado ao setor financeiro ({setor_financeiro}).'
        )


class EmitirCDOFormDespachoTest:
    def get_despacho(self, despacho: str, declarada: bool) -> str:
        form = object.__new__(EmitirCDOForm)
        form.despacho_inicial = 'Ao GABIN para autorização do ordenador de despesa para a realização da respectiva despesa.'
        form.cleaned_data = {'despacho': despacho, 'autorizacao_ordenador_declarada_no_processo': declarada}
        return form.get_despacho()

    def test_troca_despacho_sugerido_quando_autorizacao_declarada(self):
        despacho = 'Ao GABIN para autorização do ordenador de despesa para a realização da respectiva despesa.'
        assert self.get_despacho(despacho, declarada=True) == EmitirCDOForm.DESPACHO_AUTORIZACAO_DECLARADA

    def test_mantem_despacho_editado_quando_autorizacao_declarada(self):
        assert self.get_despacho('Despacho próprio', declarada=True) == 'Despacho próprio'

    def test_mantem_despacho_sugerido_sem_autorizacao_declarada(self):
        despacho = 'Ao GABIN para autorização do ordenador de despesa para a realização da respectiva despesa.'
        assert self.get_despacho(despacho, declarada=False) == despacho
