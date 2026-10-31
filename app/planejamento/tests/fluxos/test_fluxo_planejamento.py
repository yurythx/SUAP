"""Testes de fluxo do Planejamento anual.

Cada teste cobre uma etapa do pipeline pelo endpoint real (admin ou views de
acompanhamento), partindo do estado montado pelas fixtures (`conftest.py`).
Os testes são independentes entre si.
"""

from types import SimpleNamespace

import pytest

from djtools.choices import Situacao
from financeiro.models import CategoriaEconomicaDespesa, ElementoDespesa, GrupoNaturezaDespesa, ModalidadeAplicacao, NaturezaDespesa
from planejamento.enums import TipoUnidade
from planejamento.models import (
    Acao,
    AcaoExecucao,
    AcaoProposta,
    Atividade,
    Configuracao,
    Dimensao,
    Meta,
    NaturezaDespesa as Natureza,
    ObjetivoEstrategico,
    OrigemRecurso,
    OrigemRecursoUA,
    UnidadeAdministrativa,
    UnidadeMedida,
)


@pytest.mark.django_db(databases='__all__')
class TestFluxoPlanejamento:
    # --- Cadastros estruturantes -------------------------------------------

    def test_cadastrar_configuracao(self, coordenador, ano):
        """Abre a configuração do planejamento para um ano-base."""
        dados = {
            'ano_base': ano.pk,
            'data_geral_inicial': '01/01/2012',
            'data_geral_final': '01/12/2012',
            'data_metas_inicial': '01/06/2011',
            'data_metas_final': '01/07/2011',
            'data_acoes_inicial': '02/07/2011',
            'data_acoes_final': '02/08/2011',
            'data_validacao_inicial': '02/10/2011',
            'data_validacao_final': '02/12/2011',
            'data_planilhas_inicial': '01/12/2011',
            'data_planilhas_final': '20/12/2011',
        }

        coordenador.post('/admin/planejamento/configuracao/add/', dados)

        assert Configuracao.objects.filter(ano_base=ano).exists()

    def test_cadastrar_unidade_administrativa(self, coordenador, configuracao, setor):
        antes = UnidadeAdministrativa.objects.count()
        dados = {
            'configuracao': configuracao.pk,
            'tipo': TipoUnidade.CAMPUS,
            'codigo_simec': '654321',
            'codigo_simec_digito': '3',
            'setor_equivalente': setor.pk,
            'orcamento': '100',
        }

        coordenador.post('/admin/planejamento/unidadeadministrativa/add/', dados)

        assert UnidadeAdministrativa.objects.count() == antes + 1

    def test_cadastrar_dimensao(self, coordenador, setor):
        dados = {
            'descricao': 'Dimensao Teste',
            'sigla': 'SIGLA T',
            'setor_sistemico': setor.pk,
            'codigo': '99',
        }

        coordenador.post('/admin/planejamento/dimensao/add/', dados)

        assert Dimensao.objects.filter(descricao='Dimensao Teste').exists()

    def test_cadastrar_objetivo_estrategico(self, coordenador, configuracao, dimensao):
        dados = {
            'data_cadastro': '11/06/2011',
            'macro_projeto_institucional': 'macro projeto institucional teste',
            'descricao': 'objetivo teste',
            'configuracao': configuracao.pk,
            'dimensao': dimensao.pk,
            'codigo': '99',
        }

        coordenador.post('/admin/planejamento/objetivoestrategico/add/', dados)

        assert ObjetivoEstrategico.objects.filter(descricao='objetivo teste').exists()

    def test_cadastrar_meta(self, coordenador, objetivo_estrategico):
        unidade = UnidadeMedida.objects.get_or_create(nome='Acesso Teste')[0]
        url = f'/admin/planejamento/meta/add/?objetivo=estrategico={objetivo_estrategico.pk}'
        dados = {
            'data_cadastro': '11/07/2011',
            'data_cadastro_inicio': '10:00:00',
            'objetivo_estrategico': objetivo_estrategico.pk,
            'titulo': 'Meta Teste',
            'justificativa': 'Meta criada para teste',
            'unidade_medida': unidade.pk,
            'data_inicial': '01/01/2012',
            'data_final': '01/12/2012',
            'codigo': '99',
        }

        coordenador.post(url, dados)

        assert Meta.objects.filter(titulo='Meta Teste').exists()

    # --- Ações -------------------------------------------------------------

    def test_cadastrar_acao_proposta(self, coordenador, meta, recursos):
        unidade = UnidadeMedida.objects.get_or_create(nome='Acao Teste')[0]
        url = f'/admin/planejamento/acaoproposta/add/?meta={meta.pk}'
        dados = {
            'metaunidadeacaoproposta_set-TOTAL_FORMS': '0',
            'metaunidadeacaoproposta_set-INITIAL_FORMS': '0',
            'metaunidadeacaoproposta_set-MAX_NUM_FORMS': '',
            'data_inicial': '12/06/2011',
            'data_final': '12/08/2011',
            'meta': meta.pk,
            'titulo': 'Acao Proposta Teste',
            'codigo': '99',
            'acao_orcamento': recursos.acao.pk,
            'fonte_financiamento': recursos.fonte.pk,
            'unidade_medida': unidade.pk,
        }

        coordenador.post(url, dados)

        assert AcaoProposta.objects.filter(titulo='Acao Proposta Teste').exists()

    def test_importar_acao_proposta(self, coordenador, meta_unidade, meta_unidade_acao_proposta, recursos, setor):
        antes = Acao.objects.count()
        url = f'/admin/planejamento/acao/add/?metaunidade_acoespropostas/{meta_unidade_acao_proposta.pk}/'
        dados = {
            'data_cadastro': '12/06/2011',
            'data_cadastro_inicio': '10:00:00',
            'meta_unidade': meta_unidade.pk,
            'titulo': 'Acao importada',
            'detalhamento': 'acao teste',
            'unidade_medida': UnidadeMedida.objects.get_or_create(nome='Bolsa')[0].pk,
            'quantidade': '5',
            'setor_responsavel': setor.pk,
            'acao_orcamento': recursos.acao.pk,
            'fonte_financiamento': recursos.fonte.pk,
            'codigo': '2',
            'data_inicial': '01/01/2012',
            'data_final': '01/12/2012',
            'acao_indutora': '',
            'status': Situacao.DEFERIDA,
        }

        coordenador.post(url, dados)

        assert Acao.objects.count() == antes + 1

    def test_cadastrar_acao(self, coordenador, meta_unidade, recursos, setor):
        antes = Acao.objects.count()
        url = f'/admin/planejamento/acao/add/?meta_unidade={meta_unidade.pk}'
        dados = {
            'data_cadastro': '12/06/2011',
            'data_cadastro_inicio': '10:00:00',
            'meta_unidade': meta_unidade.pk,
            'titulo': 'Acao Teste',
            'detalhamento': 'acao teste',
            'unidade_medida': UnidadeMedida.objects.get_or_create(nome='Bolsa')[0].pk,
            'quantidade': '5',
            'setor_responsavel': setor.pk,
            'acao_orcamento': recursos.acao.pk,
            'fonte_financiamento': recursos.fonte.pk,
            'codigo': '',
            'data_inicial': '01/01/2012',
            'data_final': '01/12/2012',
            'acao_indutora': '',
            'status': Situacao.PENDENTE,
        }

        coordenador.post(url, dados)

        assert Acao.objects.count() == antes + 1

    def test_cadastrar_atividade(self, coordenador, acao, configuracao, unidade_administrativa, despesas):
        antes = Atividade.objects.count()
        url = f'/admin/planejamento/atividade/add/?acao={acao.pk}'
        dados = {
            'acao': acao.pk,
            'descricao': 'Atividade',
            'detalhamento': 'detalhamento sobre a atividade',
            'unidade_medida': UnidadeMedida.objects.get_or_create(nome='Atendimento')[0].pk,
            'quantidade': '3',
            'valor_unitario': '10.00',
            'elemento_despesa': despesas.natureza_planejamento.pk,
            'tipo_recurso': despesas.origem_recurso.pk,
        }

        coordenador.post(url, dados)

        assert Atividade.objects.count() == antes + 1

    # --- Acompanhamento ----------------------------------------------------

    def test_registrar_execucao(self, coordenador, acao):
        url = f'/planejamento/acompanhamento/acao/{acao.pk}/#fcad'

        coordenador.post(url, {'acao': acao.pk, 'texto': 'Acao concluida', 'percentual': '100'})

        assert AcaoExecucao.objects.filter(acao=acao).exists()

    def test_validar_acao(self, coordenador, acao):
        meta_unidade = acao.meta_unidade
        url = f'/planejamento/acao/{meta_unidade.pk}/validar/{acao.pk}/'

        resposta = coordenador.post(
            url,
            {'acao': acao.pk, 'comentario_acao': 'Acao própria para o planejamento', 'status_acao': Situacao.DEFERIDA},
            follow=True,
        )

        assert 'Ação validada com sucesso' in resposta.content.decode()
        acao.refresh_from_db()
        assert acao.status == Situacao.DEFERIDA


@pytest.fixture
def despesas(configuracao, unidade_administrativa):
    """Naturezas de despesa e origens de recurso exigidas pela Atividade."""
    categoria = CategoriaEconomicaDespesa.objects.create(codigo='1', nome='categoria 01', descricao='primeira categoria')
    grupo = GrupoNaturezaDespesa.objects.create(codigo='1', nome='grupo 01', descricao='')
    modalidade = ModalidadeAplicacao.objects.create(codigo='1', nome='modalidade 01', descricao='')
    elemento = ElementoDespesa.objects.create(codigo='1', nome='elemento despesa 10', descricao='')
    natureza_financeiro = NaturezaDespesa.objects.create(
        categoria_economica_despesa=categoria,
        grupo_natureza_despesa=grupo,
        modalidade_aplicacao=modalidade,
        elemento_despesa=elemento,
        nome='Atividade para teste',
        codigo='',
        tipo='Capital',
    )
    origem_recurso = OrigemRecurso.objects.create(
        configuracao=configuracao,
        nome='recurso para teste',
        valor_capital='10000.00',
        valor_custeio='10000.00',
        visivel_campus=True,
    )
    OrigemRecursoUA.objects.create(origem_recurso=origem_recurso, unidade=unidade_administrativa, valor_capital='5000.00', valor_custeio='5000.00')
    natureza_planejamento = Natureza.objects.create(naturezadespesa=natureza_financeiro)
    return SimpleNamespace(natureza_planejamento=natureza_planejamento, origem_recurso=origem_recurso)
