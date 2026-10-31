"""Validação do código de cargo emprego (`CargoEmprego.clean`).

O código não é identificador livre: no SIAPE ele é uma chave composta de 3 dígitos do
grupo + 3 do cargo, e o importador depende dessa composição para derivar o grupo e para
resolver o cargo do servidor. Cargos que não existem no SIAPE usam código local não
numérico, que nunca colide com esse espaço.

Os cenários aqui cobrem o formulário de cadastro manual do admin — é ele quem chama
`full_clean()`. O importador grava direto pelo ORM e não passa por esta validação.
"""

import pytest
from django.core.exceptions import ValidationError

from rh.models import CargoEmprego, GrupoCargoEmprego


@pytest.fixture
def grupo(db):
    return GrupoCargoEmprego.objects.create(codigo='701', nome='PLANO DE CARREIRA DOS CARGOS TAE-IFE', sigla='PCIFE')


def _cargo(grupo, **kwargs):
    campos = {'nome': 'CARGO DE TESTE', 'sigla_escolaridade': 'NS', 'cargo_suap': True, 'cargo_siape': False}
    campos.update(kwargs)
    return CargoEmprego(grupo_cargo_emprego=grupo, **campos)


@pytest.mark.django_db(databases='__all__')
class TestCargoEmpregoClean:
    # --- código do SIAPE: 3 dígitos do grupo + 3 do cargo --------------------

    def test_aceita_codigo_siape_coerente_com_o_grupo(self, grupo):
        _cargo(grupo, codigo='701999').clean()  # não levanta

    def test_recusa_prefixo_divergente_do_grupo(self, grupo):
        # 999999 não seria encontrado pelo importador ao resolver o cargo do servidor
        with pytest.raises(ValidationError) as erro:
            _cargo(grupo, codigo='999999').clean()

        assert 'codigo' in erro.value.message_dict
        assert '701' in erro.value.message_dict['codigo'][0]

    @pytest.mark.parametrize('codigo', ['70199', '7019999'])
    def test_recusa_codigo_numerico_com_tamanho_errado(self, grupo, codigo):
        with pytest.raises(ValidationError) as erro:
            _cargo(grupo, codigo=codigo).clean()

        assert 'codigo' in erro.value.message_dict

    def test_normaliza_espacos_e_caixa(self, grupo):
        cargo = _cargo(grupo, codigo='  701999  ')
        cargo.clean()
        assert cargo.codigo == '701999'

    def test_recusa_codigo_vazio(self, grupo):
        with pytest.raises(ValidationError) as erro:
            _cargo(grupo, codigo='').clean()

        assert 'codigo' in erro.value.message_dict

    # --- código local: cargo que não existe no SIAPE ------------------------

    def test_aceita_codigo_local_nao_numerico(self, grupo):
        # fora do espaço do SIAPE (integralmente numérico), logo sem risco de colisão
        _cargo(grupo, codigo='X01-IFRN').clean()

    def test_recusa_codigo_local_marcado_como_confirmado_pelo_siape(self, grupo):
        with pytest.raises(ValidationError) as erro:
            _cargo(grupo, codigo='X01-IFRN', cargo_siape=True).clean()

        assert 'codigo' in erro.value.message_dict

    def test_nao_estoura_quando_o_grupo_nao_foi_informado(self):
        # o campo obrigatório já é acusado pelo formulário; o clean sai antes de tocar no
        # grupo, senão acessá-lo levantaria RelatedObjectDoesNotExist em vez de ValidationError
        CargoEmprego(nome='X', sigla_escolaridade='NS', codigo='701999', cargo_suap=True, cargo_siape=False).clean()

    # --- registros sob o contrato do importador -----------------------------

    def test_nao_revalida_cargo_do_siape_ja_gravado(self, grupo):
        """Cargo legado fora do padrão não pode travar a edição dos campos do SUAP.

        `codigo` fica readonly num cargo do SIAPE, então um erro chaveado nele sequer
        viraria mensagem de campo: o ModelForm levantaria ValueError.
        """
        legado = CargoEmprego.objects.create(
            codigo='99',  # fora do padrão, gravado direto pelo ORM como o importador faz
            nome='CARGO LEGADO',
            grupo_cargo_emprego=grupo,
            sigla_escolaridade='NS',
            cargo_suap=False,
            cargo_siape=True,
        )

        legado.nome_amigavel = 'Apelido novo'
        legado.clean()  # não levanta: o código é do importador, não do formulário

    def test_valida_cargo_do_siape_na_criacao(self, grupo):
        # a saída acima vale só para registro já gravado; criar pelo admin sempre valida
        with pytest.raises(ValidationError):
            _cargo(grupo, codigo='99', cargo_suap=False, cargo_siape=True).clean()

    def test_continua_validando_cargo_gerenciado_pelo_suap(self, grupo):
        gerenciado = CargoEmprego.objects.create(
            codigo='701999',
            nome='CARGO DO SUAP',
            grupo_cargo_emprego=grupo,
            sigla_escolaridade='NS',
            cargo_suap=True,
            cargo_siape=False,
        )

        gerenciado.codigo = '999999'
        with pytest.raises(ValidationError):
            gerenciado.clean()
