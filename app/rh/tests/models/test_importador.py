"""Testes de fluxo da ingestão de dados do SIAPE (`ImportadorSIAPE`).

Cobrem o caminho principal de importação de RH, em dois níveis:

* A importação completa do zip de teste pelo motor de `rh.importacao_siape`, que
  identifica os layouts pelos `.REF` de `rh/refs` e processa as tabelas acessórias
  (bancos, situações, regimes, cargos, ocorrências, ...). Os arquivos de teste vivem
  em `rh/tests/arquivos_siape_novo`.
* As rotinas de criação/atualização de servidores (`importar_servidor1` /
  `importar_servidor2`), exercitadas com registros SIAPE montados em memória
  pelas factories do `conftest` — cria servidor, situação, cargo, ocorrências
  de exclusão e reativação.

Mais cenários de falha em `TestImportadorSIAPEFalhas`: registro de servidor
malformado (engolido, não derruba o lote) e registro de tabela acessória fora do
padrão.
"""

from datetime import date
from unittest import mock

import pytest
from django.apps import apps

from rh.importacao_siape.execucao_lotes import PendenciasDeCargo
from rh.importador import ImportadorSIAPE
from rh.tests.siape import (
    executar_importacao,
    importador_com_tabelas,
    registro_servidor1,
    registro_servidor2,
    registro_servidor3,
)

Banco = apps.get_model('rh', 'banco')
CargoEmprego = apps.get_model('rh', 'cargoemprego')
CargoEmpregoPendente = apps.get_model('rh', 'cargoempregopendente')
DiplomaLegal = apps.get_model('rh', 'diplomalegal')
EstadoCivil = apps.get_model('comum', 'estadocivil')
GrupoCargoEmprego = apps.get_model('rh', 'grupocargoemprego')
JornadaTrabalho = apps.get_model('rh', 'jornadatrabalho')
NivelEscolaridade = apps.get_model('rh', 'nivelescolaridade')
Ocorrencia = apps.get_model('rh', 'ocorrencia')
Pais = apps.get_model('comum', 'pais')
RegimeJuridico = apps.get_model('rh', 'regimejuridico')
Servidor = apps.get_model('rh', 'servidor')
ServidorOcorrencia = apps.get_model('rh', 'servidorocorrencia')
Situacao = apps.get_model('rh', 'situacao')
SubgrupoOcorrencia = apps.get_model('rh', 'subgrupoocorrencia')
Titulacao = apps.get_model('rh', 'titulacao')

pytestmark = pytest.mark.usefixtures('importacao_serial', 'limpar_importacoes')


@pytest.mark.django_db(databases='__all__')
class TestImportadorSIAPERun:
    """Importação completa + ingestão de servidores sobre os dados carregados."""

    # --- carga das tabelas acessórias a partir dos arquivos -------------------

    def test_run_carrega_bancos(self):
        executar_importacao()
        assert Banco.objects.filter(codigo='001', sigla='B.B.').exists()

    def test_run_carrega_situacoes(self):
        executar_importacao()
        assert set(Situacao.objects.values_list('codigo', flat=True)) >= {'01', '02'}

    def test_run_carrega_regime_juridico(self):
        executar_importacao()
        assert RegimeJuridico.objects.filter(sigla='EST').exists()

    def test_run_carrega_grupo_e_cargo_emprego(self):
        executar_importacao()
        # cargo_emprego depende do grupo_cargo_emprego importado antes (ordem importa)
        assert GrupoCargoEmprego.objects.filter(codigo='707').exists()
        cargo = CargoEmprego.objects.get(codigo='707001')
        assert cargo.grupo_cargo_emprego.codigo == '707'

    def test_run_carrega_demais_tabelas_acessorias(self):
        executar_importacao()
        assert EstadoCivil.objects.exists()
        assert JornadaTrabalho.objects.filter(codigo='40').exists()
        assert NivelEscolaridade.objects.exists()
        assert Titulacao.objects.filter(codigo='23').exists()
        assert DiplomaLegal.objects.exists()
        assert Ocorrencia.objects.exists()
        assert Pais.objects.get(codigo='024').iso_alfa3 == 'BRA'

    # --- importar_servidor1: criação e ciclo de vida do servidor -------------

    def test_importar_servidor1_cria_servidor(self):
        importador = importador_com_tabelas()
        importador.importar_servidor1([registro_servidor1()])

        servidor = Servidor.objects.get(matricula='10')
        assert servidor.ativo is True
        assert servidor.sistema_origem == 'SIAPE'
        assert servidor.nome.upper() == 'NOME SOBRENOME DO TERCEIRO-NOME'
        assert servidor.situacao == Situacao.objects.get(codigo='01')
        assert servidor.regime_juridico == RegimeJuridico.objects.get(sigla='EST')
        assert servidor.cargo_emprego == CargoEmprego.objects.get(codigo='707001')

    def test_importar_servidor1_servidor_novo_nasce_sem_setor(self):
        importador = importador_com_tabelas()
        # Regra: servidores novos entram com setor (árvore SUAP) vazio, só com lotação
        importador.importar_servidor1([registro_servidor1()])

        servidor = Servidor.objects.get(matricula='10')
        assert servidor.setor is None

    def test_importar_servidor1_exclusao_inativa_e_registra_ocorrencia(self):
        importador = importador_com_tabelas()
        registro = registro_servidor1(
            **{
                'IT-CO-GRUPO-OCOR-EXCLUSAO': '02',
                'IT-CO-OCOR-EXCLUSAO': '001',
                'IT-DA-OCOR-EXCLUSAO-SERV': '20110601',
                'IT-CO-DIPL-EXCLUSAO': '02',
                'IT-DA-PUBL-DIPL-EXCLUSAO': '20110602',
                'IT-NU-DIPL-EXCLUSAO': '0966/2011',
            }
        )
        importador.importar_servidor1([registro])

        servidor = Servidor.objects.get(matricula='10')
        assert servidor.ativo is False
        ocorrencia = ServidorOcorrencia.objects.get(servidor=servidor, subgrupo__descricao='EXCLUSAO')
        assert ocorrencia.diploma_legal_num == '0966/2011'

    def test_importar_servidor1_reativa_servidor_inativo(self):
        importador = importador_com_tabelas()
        # Servidor já existente e inativo, sem ocorrência de exclusão no novo registro -> reativa
        importador.importar_servidor1([registro_servidor1()])
        Servidor.objects.filter(matricula='10').update(ativo=False)

        importador.importar_servidor1([registro_servidor1()])

        assert Servidor.objects.get(matricula='10').ativo is True

    def test_importar_servidor1_registro_invalido_nao_derruba_lote(self):
        importador = importador_com_tabelas()
        # Um registro quebrado é capturado/logado (sentry) e os demais seguem importando
        invalido = registro_servidor1(**{'GR-MATRICULA': '264350000010', 'IT-CO-SITUACAO-SERVIDOR': 'ZZ'})
        valido = registro_servidor1(**{'GR-MATRICULA': '264350000020', 'IT-NU-CPF': '20020020023'})

        with mock.patch('rh.importador.capture_exception') as captura:
            importador.importar_servidor1([invalido, valido])

        assert captura.called
        assert not Servidor.objects.filter(matricula='10').exists()
        assert Servidor.objects.filter(matricula='20').exists()

    # --- importar_servidor2: dados complementares ----------------------------

    def test_importar_servidor2_complementa_dados_pessoais(self):
        importador = importador_com_tabelas()
        importador.importar_servidor1([registro_servidor1()])
        importador.importar_servidor2([registro_servidor2()])

        servidor = Servidor.objects.get(matricula='10')
        assert servidor.pessoa_fisica.nascimento_data == date(1982, 7, 29)
        assert servidor.pessoa_fisica.sexo == 'F'
        assert servidor.nivel_escolaridade == NivelEscolaridade.objects.get(codigo='13')
        assert servidor.jornada_trabalho == JornadaTrabalho.objects.get(codigo='40')
        assert servidor.data_cadastro_siape == date(2005, 10, 11)

    # --- importar_servidor3: titulação ----------------------------------------

    def test_importar_servidor3_so_codigo_conhecido_altera_a_titulacao(self):
        importador = importador_com_tabelas()
        importador.importar_servidor1([registro_servidor1()])

        def importar_titulacao(codigo):
            importador.importar_servidor3([registro_servidor3(**{'IT-CO-TITULACAO-FORMACAO-RH': codigo})])
            return Servidor.objects.get(matricula='10').titulacao

        assert importar_titulacao('25') == Titulacao.objects.get(codigo='25')
        # zerado ou ainda sem cadastro na tabela de titulações: mantém a cadastrada
        assert importar_titulacao('00') == Titulacao.objects.get(codigo='25')
        assert importar_titulacao('99') == Titulacao.objects.get(codigo='25')
        assert importar_titulacao('23') == Titulacao.objects.get(codigo='23')


@pytest.mark.django_db(databases='__all__')
class TestImportadorSIAPECargoEmpregoPendente:
    """Registro dos códigos de cargo que o SIAPE informa e o SUAP não tem cadastrados.

    O cargo do servidor é resolvido por lookup exato de `grupo + cargo` no cache. Quando
    falha, o vínculo fica nulo e o código, antes descartado, passa a ser registrado para a
    Gestão de Pessoas saber o que cadastrar.
    """

    CODIGO_AUSENTE = {'IT-CO-GRUPO-CARGO-EMPREGO': '707', 'IT-CO-CARGO-EMPREGO': '999'}

    def test_cargo_ausente_registra_pendencia(self):
        importador = importador_com_tabelas()
        importador.importar_servidor1([registro_servidor1(**self.CODIGO_AUSENTE)])

        pendencia = CargoEmpregoPendente.objects.get(codigo='707999')
        assert pendencia.grupo_codigo == '707'
        assert pendencia.qtd_servidores == 1
        # o vínculo do servidor fica nulo justamente porque o cargo não existe
        assert Servidor.objects.get(matricula='10').cargo_emprego is None

    def test_cargo_existente_nao_registra_pendencia(self):
        importador = importador_com_tabelas()
        # 707001 vem dos arquivos de teste e resolve normalmente
        importador.importar_servidor1([registro_servidor1()])

        assert not CargoEmpregoPendente.objects.exists()
        assert Servidor.objects.get(matricula='10').cargo_emprego == CargoEmprego.objects.get(codigo='707001')

    def test_grupo_cargo_zerado_nao_registra_pendencia(self):
        importador = importador_com_tabelas()
        # estagiário/pensionista chegam sem cargo no SIAPE: ausência legítima, não pendência
        registro = registro_servidor1(**{'IT-CO-GRUPO-CARGO-EMPREGO': '000', 'IT-CO-CARGO-EMPREGO': '000'})

        importador.importar_servidor1([registro])

        assert not CargoEmpregoPendente.objects.exists()

    def test_pendencia_conta_servidores_do_mesmo_codigo(self):
        importador = importador_com_tabelas()
        primeiro = registro_servidor1(**self.CODIGO_AUSENTE)
        segundo = registro_servidor1(**{**self.CODIGO_AUSENTE, 'GR-MATRICULA': '264350000020', 'IT-NU-CPF': '20020020023'})

        importador.importar_servidor1([primeiro, segundo])

        assert CargoEmpregoPendente.objects.get(codigo='707999').qtd_servidores == 2

    def test_pendencia_acumula_entre_arquivos_do_mesmo_layout(self):
        importador = importador_com_tabelas()
        # o layout de servidores pode vir quebrado em vários arquivos e importar_servidor1
        # é chamado uma vez por arquivo: a contagem precisa somar, não sobrescrever
        importador.importar_servidor1([registro_servidor1(**self.CODIGO_AUSENTE)])
        importador.importar_servidor1([registro_servidor1(**{**self.CODIGO_AUSENTE, 'GR-MATRICULA': '264350000020', 'IT-NU-CPF': '20020020023'})])

        assert CargoEmpregoPendente.objects.get(codigo='707999').qtd_servidores == 2

    def test_lotes_do_servidor1_somam_pendencias_e_gravam_uma_vez_no_fim(self):
        importador_com_tabelas()
        # o motor por lotes: cada lote com seu importador, sem gravar; o fim do layout soma e grava
        primeiro, segundo = ImportadorSIAPE(), ImportadorSIAPE()
        primeiro.importar_servidor1([registro_servidor1(**self.CODIGO_AUSENTE)], registrar_pendentes=False)
        segundo.importar_servidor1(
            [registro_servidor1(**{**self.CODIGO_AUSENTE, 'GR-MATRICULA': '264350000020', 'IT-NU-CPF': '20020020023'})], registrar_pendentes=False
        )
        assert not CargoEmpregoPendente.objects.exists()

        pendencias = PendenciasDeCargo()
        pendencias.somar(primeiro.cargos_emprego_pendentes)
        pendencias.somar(segundo.cargos_emprego_pendentes)
        pendencias.registrar()

        assert CargoEmpregoPendente.objects.get(codigo='707999').qtd_servidores == 2

    def test_pendencia_nao_duplica_entre_importacoes(self):
        importador = importador_com_tabelas()
        # a chave é o código: uma segunda importação regrava a mesma linha
        importador.importar_servidor1([registro_servidor1(**self.CODIGO_AUSENTE)])
        ImportadorSIAPE().importar_servidor1([registro_servidor1(**self.CODIGO_AUSENTE)])

        assert CargoEmpregoPendente.objects.filter(codigo='707999').count() == 1

    # --- reconciliação: a tabela de cargos chega e a pendência deixa de existir ---

    def _registro_tabela_cargo(self, codigo='707999', nome='CARGO QUE CHEGOU DEPOIS'):
        return {
            'GR-IDEN-CARGO-EMPREGO': codigo,
            'IT-NO-CARGO-EMPREGO': nome,
            'IT-SG-ESCOLARIDADE': 'NS',
            'IT-IN-STATUS-REGISTRO-TABELA': '0',
        }

    def test_tabela_de_cargos_remove_pendencia_correspondente(self):
        importador = importador_com_tabelas()
        importador.importar_servidor1([registro_servidor1(**self.CODIGO_AUSENTE)])
        assert CargoEmpregoPendente.objects.filter(codigo='707999').exists()

        importador.importar_cargo_emprego([self._registro_tabela_cargo()])

        assert not CargoEmpregoPendente.objects.filter(codigo='707999').exists()

    def test_cargo_manual_e_reconciliado_sem_duplicar(self):
        importador = importador_com_tabelas()
        """Cadastro antecipado à mão: a extração atualiza o mesmo registro e o confirma."""
        grupo = GrupoCargoEmprego.objects.get(codigo='707')
        manual = CargoEmprego.objects.create(
            codigo='707999',
            nome='PALPITE DA GP',
            nome_amigavel='Apelido definido no SUAP',
            grupo_cargo_emprego=grupo,
            sigla_escolaridade='NM',
            cargo_suap=True,
            cargo_siape=False,
        )

        importador.importar_cargo_emprego([self._registro_tabela_cargo()])

        manual.refresh_from_db()
        assert CargoEmprego.objects.filter(codigo='707999').count() == 1
        assert manual.nome == 'CARGO QUE CHEGOU DEPOIS'  # dado oficial sobrescreve o palpite
        assert manual.sigla_escolaridade == 'NS'
        assert manual.cargo_siape is True  # confirmado pela extração
        assert manual.cargo_suap is True  # segue gerenciável no SUAP
        assert manual.nome_amigavel == 'Apelido definido no SUAP'  # campo do SUAP preservado

    def test_cargo_manual_passa_a_resolver_o_servidor(self):
        importador_com_tabelas()
        """O cadastro manual basta: a extração seguinte religa o servidor sozinha."""
        CargoEmprego.objects.create(
            codigo='707999',
            nome='CARGO CADASTRADO A MAO',
            grupo_cargo_emprego=GrupoCargoEmprego.objects.get(codigo='707'),
            sigla_escolaridade='NS',
            cargo_suap=True,
            cargo_siape=False,
        )

        ImportadorSIAPE().importar_servidor1([registro_servidor1(**self.CODIGO_AUSENTE)])

        assert Servidor.objects.get(matricula='10').cargo_emprego.codigo == '707999'
        assert not CargoEmpregoPendente.objects.exists()

    # --- situação derivada, não armazenada ---

    def test_resolucao_e_derivada_da_existencia_do_cargo(self):
        importador = importador_com_tabelas()
        importador.importar_servidor1([registro_servidor1(**self.CODIGO_AUSENTE)])
        pendencia = CargoEmpregoPendente.objects.get(codigo='707999')
        assert pendencia.resolvida is False
        assert CargoEmpregoPendente.objects.nao_resolvidas().count() == 1

        CargoEmprego.objects.create(
            codigo='707999',
            nome='CARGO CADASTRADO A MAO',
            grupo_cargo_emprego=GrupoCargoEmprego.objects.get(codigo='707'),
            sigla_escolaridade='NS',
        )

        # sem regravar a pendência: a situação acompanha o cadastro do cargo
        assert pendencia.resolvida is True
        assert CargoEmpregoPendente.objects.resolvidas().count() == 1
        assert CargoEmpregoPendente.objects.nao_resolvidas().count() == 0


@pytest.mark.django_db(databases='__all__')
class TestImportadorSIAPEPais:
    @staticmethod
    def _registro_pais(codigo: str, nome: str) -> dict[str, str]:
        return {'IT-CO-PAIS': codigo, 'IT-NO-PAIS': nome, 'IT-IN-STATUS-REGISTRO-TABELA': '0', 'IT-IN-PAIS-EQUIPARADO': 'N'}

    def test_pais_novo_nasce_com_iso_alfa3(self) -> None:
        ImportadorSIAPE().importar_pais([self._registro_pais('011', 'ARGENTINA')])

        assert Pais.objects.get(codigo='011').iso_alfa3 == 'ARG'

    def test_pais_existente_mantem_iso_alfa3_corrigido_no_admin(self) -> None:
        Pais.objects.create(codigo='011', nome='ARGENTINA', iso_alfa3='XYZ')

        ImportadorSIAPE().importar_pais([self._registro_pais('011', 'ARGENTINA')])

        assert Pais.objects.get(codigo='011').iso_alfa3 == 'XYZ'


@pytest.mark.django_db(databases='__all__')
class TestImportadorSIAPEFalhas:
    def test_importar_afastamentos_ignora_tipo_invalido(self):
        Afastamento = apps.get_model('rh', 'afastamentosiape')
        importador = ImportadorSIAPE()

        registro_invalido = {
            'IT-CO-AFASTAMENTO': '999',
            'IT-NO-AFASTAMENTO': 'AFASTAMENTO SEM TIPO',
            'IT-SG-AFASTAMENTO': 'XX',
            'IT-TP-AFASTAMENTO': '',  # vazio -> não importável
            'IT-IN-EXCLUI-PAGAMENTO': 'N',
            'IT-IN-STATUS-REGISTRO-TABELA': '0',
        }
        importador.importar_afastamentos([registro_invalido])

        assert not Afastamento.objects.filter(codigo='999').exists()
