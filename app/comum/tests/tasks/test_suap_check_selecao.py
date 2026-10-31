"""Seleção de testes por módulo e dependência do ``suap_check`` — sem banco."""

import json
import subprocess

import pytest
from coverage import CoverageData

from comum.management.commands import suap_check
from comum.management.commands.suap_check import (
    COBERTURA_SO_DADOS,
    SUFIXO_ACEITA_NENHUM_TESTE,
    candidatos_e2e,
    candidatos_unitario,
    distribuir_shards,
    get_changed_files,
    modulos_afetados,
    motivo_fallback,
    carregar_duracoes_e2e,
    pesos_em_segundos,
)

# `auth` é chave do JSON real mas não é diretório do repo: nunca pode virar caminho do pytest.
DEPENDENCIAS = {
    'auth': ['materiais'],
    'compras': ['comum', 'materiais', 'processo_eletronico', 'rh'],
    'edu': ['comum', 'rh'],
    'erros': ['comum', 'demandas'],
    'materiais': ['comum', 'rh'],
}
CANDIDATOS = {'compras', 'demandas', 'edu', 'erros', 'materiais'}


def test_candidatos_unitario_sao_diretorios_de_topo_com_arquivo_de_teste():
    arquivos = [
        'eventos/test_models.py',
        'edu/tests/test_diarios.py',
        'edu/tests/helpers.py',
        'almoxarifado/features/test_initial_data.py',
        'processmining/tests/test_a.py',
        'ae/tests/e2e/test_ae.py',
        'rsc/tests.py',
        'protocolo/models.py',
        'suap/settings_test.py',
        'tests/test_servidor_save.py',
        'bin/scripts/test_papeis.py',
        '.agents/hooks/test_x.py',
        'test_na_raiz.py',
    ]

    assert candidatos_unitario(arquivos) == {'almoxarifado', 'edu', 'eventos', 'processmining'}


def test_candidatos_e2e_sao_modulos_com_tests_e2e():
    arquivos = [
        'edu/tests/e2e/test_diretoria.py',
        'edu/tests/e2e/conftest.py',
        'erros/tests/e2e/test_navegacao.py',
        'ae/tests/test_models.py',
        'tests/e2e/test_login.py',
        'ponto/tests/e2e/conftest.py',
    ]

    assert candidatos_e2e(arquivos) == {'edu', 'erros'}


@pytest.mark.parametrize(
    ('arquivos', 'esperado'),
    [
        (['docs/x.md', 'rh/models.py'], 'rh/models.py'),
        (['comum/views.py'], 'comum/views.py'),
        (['djtools/e2e_ui.py'], 'djtools/e2e_ui.py'),
        (['conftest.py'], 'conftest.py'),
        (['remanejamento/conftest.py'], None),
        (['suap/settings_base.py', 'pyproject.toml', 'uv.lock'], None),
        (['', 'edu/models.py'], None),
    ],
)
def test_motivo_fallback(arquivos, esperado):
    assert motivo_fallback(arquivos) == esperado


@pytest.mark.parametrize(
    ('arquivos', 'esperado'),
    [
        (['materiais/models.py'], {'materiais', 'compras'}),
        (['demandas/views.py'], {'demandas', 'erros'}),
        (['comum/models.py'], CANDIDATOS),
        (['rh/models.py'], CANDIDATOS),
        (['djtools/utils.py'], CANDIDATOS),
        (['conftest.py'], CANDIDATOS),
        (['suap/settings_base.py'], set()),
        (['pyproject.toml', 'uv.lock'], set()),
        (['docs/x.md', '.gitlab-ci.yml'], set()),
        (['tests/test_servidor_save.py', 'bin/scripts/test_papeis.py'], set()),
        (['suap/settings_base.py', 'materiais/x.py'], {'materiais', 'compras'}),
        (['processo_eletronico/models.py'], {'compras'}),
        ([], set()),
    ],
)
def test_modulos_afetados(arquivos, esperado):
    assert modulos_afetados(arquivos, DEPENDENCIAS, CANDIDATOS) == esperado


def test_modulos_afetados_nao_devolve_rotulo_que_nao_e_candidato():
    assert 'auth' not in modulos_afetados(['materiais/models.py'], DEPENDENCIAS, CANDIDATOS)


def test_modulos_afetados_so_um_nivel():
    dependencias = {'a': ['b'], 'b': ['c']}

    assert modulos_afetados(['c/x.py'], dependencias, {'a', 'b', 'c'}) == {'b', 'c'}


PESOS_ATUAIS = {
    'edu': 105,
    'almoxarifado': 36,
    'remanejamento': 35,
    'processo_eletronico': 26,
    'erros': 20,
    'ae': 17,
    'documento_eletronico': 13,
    'eventos': 5,
}


def test_distribuir_shards_isola_a_suite_mais_pesada():
    shards = distribuir_shards(PESOS_ATUAIS, 3)

    assert shards[0] == ['edu']
    assert sorted(s for shard in shards for s in shard) == sorted(PESOS_ATUAIS)


def test_distribuir_shards_e_deterministico():
    assert distribuir_shards(PESOS_ATUAIS, 3) == distribuir_shards(dict(reversed(PESOS_ATUAIS.items())), 3)


def test_distribuir_shards_com_um_shard_so():
    assert distribuir_shards({'b': 1, 'a': 1}, 1) == [['a', 'b']]


def test_distribuir_shards_sem_suites():
    assert distribuir_shards({}, 3) == [[], [], []]


def test_distribuir_shards_espalha_suites_de_peso_zero():
    assert distribuir_shards({'a': 0, 'b': 0, 'c': 0}, 3) == [['a'], ['b'], ['c']]


def test_pesos_em_segundos_usa_a_duracao_medida_quando_existe():
    assert pesos_em_segundos({'edu': 112}, {'edu': 2424.0}) == {'edu': 2424}


def test_pesos_em_segundos_estima_suite_nova_na_escala_de_segundos():
    """A suíte sem medição tem de sair comparável às medidas, e não na escala da contagem.

    É a regressão que importa: com peso em contagem (2) contra segundos (900), a suíte nova
    seria sempre a mais leve e cairia sempre no mesmo shard.
    """
    pesos = pesos_em_segundos({'edu': 100, 'nova': 50}, {'edu': 900.0})

    assert pesos == {'edu': 900, 'nova': 450}


def test_pesos_em_segundos_sem_nenhuma_medicao_preserva_a_ordenacao_por_contagem():
    """Arquivo ausente/vazio: fator uniforme não muda empacotamento — é o comportamento de antes."""
    contagens = {'ae': 141, 'edu': 112, 'remanejamento': 52}

    pesos = pesos_em_segundos(contagens, {})

    assert distribuir_shards(pesos, 2) == distribuir_shards(contagens, 2)


def test_gravar_duracoes_cria_o_artifacts_que_ainda_nao_existe(tmp_path, monkeypatch):
    """Shard todo verde não tem `artifacts/`: o `--output` do Playwright só o cria em falha.

    Regressão do job 435997 — 5 suítes verdes e o job vermelho na gravação.
    """
    monkeypatch.chdir(tmp_path)
    comando = suap_check.Command()
    comando.duracoes_e2e = {'erros': 210.2}

    comando.gravar_duracoes_e2e(2)

    assert json.loads((tmp_path / 'artifacts' / 'e2e-duracoes-2.json').read_text()) == {'erros': 210.2}


def test_gravar_duracoes_sem_medicao_nao_escreve(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    suap_check.Command().gravar_duracoes_e2e(1)

    assert not (tmp_path / 'artifacts').exists()


def test_duracoes_versionadas_apontam_para_suites_que_existem():
    """Rótulo errado no arquivo não explode: a suíte só cai na estimativa, em silêncio.

    Por isso o guarda é aqui: todo rótulo medido tem de ser uma suíte que o `suites_e2e` monta
    hoje — senão a medição promovida não vale para nada.
    """
    versionados = suap_check.arquivos_versionados()
    suites = suap_check.suites_e2e(candidatos_e2e(versionados), versionados)

    for rotulo in carregar_duracoes_e2e():
        assert rotulo in suites, f'{rotulo}: não é suíte e2e montada por suites_e2e'


def test_pesos_em_segundos_ignora_medicao_de_suite_que_nao_roda_mais():
    """Rótulo aposentado no arquivo não entra na média nem vira shard."""
    pesos = pesos_em_segundos({'nova': 10}, {'extinta': 5000.0})

    assert pesos == {'nova': 100}


VERSIONADOS = [
    'compras/tests/test_compras.py',
    'materiais/tests/test_materiais.py',
    'edu/tests/test_edu.py',
    'edu/tests/e2e/test_edu_e2e.py',
    'erros/tests/e2e/test_erros_e2e.py',
    'ae/tests/e2e/test_ae_e2e.py',
    'tests/test_servidor_save.py',
]


TESTES_POR_CAMINHO = {'edu/tests/e2e/test_edu_e2e.py': 10, 'edu/tests/e2e/test_15_rotas_edu.py': 8, 'erros/tests/e2e': 3, 'ae/tests/e2e': 2}
COLETAS = []


def coletor_falso(caminhos):
    """Node ids fictícios (``TESTES_POR_CAMINHO`` por caminho) e registro de cada coleta pedida."""
    caminhos = list(caminhos)
    COLETAS.append(caminhos)
    return [f'{caminho}::test_{i}[chromium]' for caminho in caminhos for i in range(TESTES_POR_CAMINHO[caminho])]


@pytest.fixture
def xmls(monkeypatch):
    """Grava os diretórios pedidos ao XML de cobertura em vez de gerá-lo (senão escreveria em artifacts/ do repo)."""
    pedidos = []
    monkeypatch.setattr(suap_check.Command, 'gerar_xml_cobertura', lambda self, diretorios: pedidos.append(sorted(diretorios)))
    return pedidos


@pytest.fixture
def executados(monkeypatch, xmls):
    """Troca o I/O do command por dados fixos e grava os comandos em vez de executá-los."""
    comandos = []
    monkeypatch.setattr(suap_check.Command, 'run_command', lambda self, cmd: comandos.append(cmd))
    monkeypatch.setattr(suap_check, 'arquivos_versionados', lambda: VERSIONADOS)
    monkeypatch.setattr(suap_check, 'carregar_dependencias', lambda: DEPENDENCIAS)
    monkeypatch.setattr(suap_check, 'coletar_testes_e2e', coletor_falso)
    # Sem isto o teste leria o `e2e_duracoes.json` do repositório e os shards mudariam de
    # composição a cada promoção de medições — o que estes testes afirmam é o comando, não o peso.
    monkeypatch.setattr(suap_check, 'carregar_duracoes_e2e', dict)
    monkeypatch.delenv('CI_NODE_INDEX', raising=False)
    monkeypatch.delenv('CI_NODE_TOTAL', raising=False)
    return comandos


def test_django_dependentes_roda_modulo_e_dependentes(executados, xmls, monkeypatch):
    monkeypatch.setenv('SUAP_APPS', 'dependentes')
    monkeypatch.setattr(suap_check, 'get_changed_files', lambda: ['materiais/models.py'])

    suap_check.Command().executar_django()

    assert len(executados) == 1
    assert '-m "not e2e"' in executados[0]
    assert ' compras materiais' in executados[0]
    assert executados[0].endswith(SUFIXO_ACEITA_NENHUM_TESTE)
    assert f' {COBERTURA_SO_DADOS} ' in executados[0]
    assert 'term-missing' not in executados[0]
    assert xmls == [['compras', 'materiais']]


def test_django_dependentes_sem_modulo_afetado_nao_chama_pytest(executados, xmls, monkeypatch):
    monkeypatch.setenv('SUAP_APPS', 'dependentes')
    monkeypatch.setattr(suap_check, 'get_changed_files', lambda: ['suap/settings_base.py', 'docs/x.md'])

    suap_check.Command().executar_django()

    assert executados == []
    assert xmls == []


def test_django_geral_roda_todos_os_candidatos_sem_transversais_nem_xml(executados, xmls, monkeypatch):
    monkeypatch.setenv('SUAP_APPS', 'geral')

    suap_check.Command().executar_django()

    assert ' compras edu materiais' in executados[0]
    assert executados[0].endswith(SUFIXO_ACEITA_NENHUM_TESTE)
    assert f' {COBERTURA_SO_DADOS} ' in executados[0]
    assert xmls == []


def test_django_dependentes_em_shard_reparte_pelo_pytest_split_sem_medir(executados, monkeypatch):
    monkeypatch.setenv('SUAP_APPS', 'dependentes')
    monkeypatch.setenv('CI_NODE_TOTAL', '3')
    monkeypatch.setenv('CI_NODE_INDEX', '2')
    monkeypatch.setattr(suap_check, 'get_changed_files', lambda: ['materiais/models.py'])

    suap_check.Command().executar_django()

    assert '--splits 3 --group 2 --splitting-algorithm least_duration --durations-path unitario_duracoes.json ' in executados[0]
    assert '--store-durations' not in executados[0]
    # Grupo vazio (MR com poucos testes) sai com exit 5, que este caminho aceita.
    assert executados[0].endswith(SUFIXO_ACEITA_NENHUM_TESTE)


def test_django_geral_em_shard_mede_numa_copia_das_duracoes_promovidas(executados, monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    (tmp_path / 'unitario_duracoes.json').write_text('{"edu/tests/test_x.py::test_a": 1.5}')
    monkeypatch.setenv('SUAP_APPS', 'geral')
    monkeypatch.setenv('CI_NODE_TOTAL', '3')
    monkeypatch.setenv('CI_NODE_INDEX', '3')

    suap_check.Command().executar_django()

    medidas = 'artifacts/unitario-duracoes-3.json'
    assert (
        f'--splits 3 --group 3 --splitting-algorithm least_duration --durations-path {medidas} --store-durations --clean-durations ' in executados[0]
    )
    assert (tmp_path / medidas).read_text() == '{"edu/tests/test_x.py::test_a": 1.5}'


def test_django_lista_literal_nao_reparte_mesmo_em_shard(executados, xmls, monkeypatch):
    monkeypatch.setenv('SUAP_APPS', 'tests bin')
    monkeypatch.setenv('CI_NODE_TOTAL', '3')
    monkeypatch.setenv('CI_NODE_INDEX', '1')

    suap_check.Command().executar_django()

    assert '--splits' not in executados[0]


def test_django_lista_literal_mantem_caminhos_e_gera_xml_so_deles(executados, xmls, monkeypatch):
    monkeypatch.setenv('SUAP_APPS', 'tests bin')

    suap_check.Command().executar_django()

    assert executados[0].endswith(' tests bin')
    assert SUFIXO_ACEITA_NENHUM_TESTE not in executados[0]
    assert f' {COBERTURA_SO_DADOS} ' in executados[0]
    assert xmls == [['bin', 'tests']]


def test_django_gera_xml_mesmo_com_pytest_vermelho(executados, xmls, monkeypatch):
    monkeypatch.setenv('SUAP_APPS', 'dependentes')
    monkeypatch.setattr(suap_check, 'get_changed_files', lambda: ['materiais/models.py'])

    def run_command(self, cmd):
        raise Exception('pytest falhou')

    monkeypatch.setattr(suap_check.Command, 'run_command', run_command)

    with pytest.raises(Exception, match='pytest falhou'):
        suap_check.Command().executar_django()

    assert xmls == [['compras', 'materiais']]


def test_gerar_xml_cobertura_so_inclui_diretorios_pedidos(tmp_path, monkeypatch):
    (tmp_path / 'pkg_a' / 'sub').mkdir(parents=True)
    (tmp_path / 'pkg_b').mkdir()
    for arquivo in ('pkg_a/mod.py', 'pkg_a/sub/mod2.py', 'pkg_b/mod.py'):
        (tmp_path / arquivo).write_text('x = 1\ny = 2\n')
    dados = CoverageData(basename=str(tmp_path / '.coverage'))
    dados.add_lines({str(tmp_path / arquivo): [1, 2] for arquivo in ('pkg_a/mod.py', 'pkg_a/sub/mod2.py', 'pkg_b/mod.py')})
    dados.write()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('COVERAGE_FILE', str(tmp_path / '.coverage'))

    suap_check.Command().gerar_xml_cobertura({'pkg_a'})

    xml = (tmp_path / 'artifacts' / 'coverage.xml').read_text()
    assert 'filename="pkg_a/mod.py"' in xml
    assert 'filename="pkg_a/sub/mod2.py"' in xml
    assert 'pkg_b' not in xml


def test_gerar_xml_cobertura_junta_dados_de_workers_nao_combinados(tmp_path, monkeypatch):
    """Com ``-x`` o xdist é interrompido antes de o pytest-cov juntar os dados: só sobram os arquivos dos workers."""
    (tmp_path / 'pkg_a').mkdir()
    (tmp_path / 'pkg_a' / 'mod.py').write_text('x = 1\ny = 2\n')
    for worker in ('gw0', 'gw1'):
        dados = CoverageData(basename=str(tmp_path / '.coverage'), suffix=worker)
        dados.add_lines({str(tmp_path / 'pkg_a' / 'mod.py'): [1] if worker == 'gw0' else [2]})
        dados.write()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('COVERAGE_FILE', str(tmp_path / '.coverage'))

    suap_check.Command().gerar_xml_cobertura({'pkg_a'})

    xml = (tmp_path / 'artifacts' / 'coverage.xml').read_text()
    assert 'filename="pkg_a/mod.py"' in xml
    assert 'line-rate="1"' in xml


def test_gerar_xml_cobertura_sem_dados_nao_falha(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('COVERAGE_FILE', str(tmp_path / '.coverage'))

    suap_check.Command().gerar_xml_cobertura({'pkg_a'})

    assert not (tmp_path / 'artifacts' / 'coverage.xml').exists()


def test_e2e_geral_roda_so_as_suites_do_shard_com_cobertura(executados, monkeypatch):
    monkeypatch.setenv('SUAP_APPS', 'geral')
    monkeypatch.setenv('CI_NODE_TOTAL', '2')
    monkeypatch.setenv('CI_NODE_INDEX', '2')

    suap_check.Command().executar_e2e()

    assert [cmd.split('pytest ')[1].split()[0] for cmd in executados] == ['erros/tests/e2e', 'ae/tests/e2e']
    assert executados[0].startswith('COVERAGE_FILE=artifacts/.coverage.e2e-erros pytest ')
    assert '--cov=.' in executados[0]
    assert '--output=artifacts/e2e-erros' in executados[0]


def test_e2e_dependentes_roda_sem_cobertura(executados, monkeypatch):
    monkeypatch.setenv('SUAP_APPS', 'dependentes')
    monkeypatch.setattr(suap_check, 'get_changed_files', lambda: ['demandas/models.py'])

    suap_check.Command().executar_e2e()

    assert len(executados) == 1
    assert executados[0].startswith('pytest erros/tests/e2e -m e2e ')
    assert '--cov' not in executados[0]


def test_e2e_tocados_nao_roda_dependentes(executados, monkeypatch):
    """``erros`` depende de ``demandas``: no ``dependentes`` rodaria, no ``tocados`` não."""
    monkeypatch.setenv('SUAP_APPS', 'tocados')
    monkeypatch.setattr(suap_check, 'get_changed_files', lambda: ['demandas/models.py', 'ae/views.py'])

    suap_check.Command().executar_e2e()

    assert [cmd.split('pytest ')[1].split()[0] for cmd in executados] == ['ae/tests/e2e']


def test_e2e_tocados_sem_fallback_em_comum_e_djtools(executados, monkeypatch):
    monkeypatch.setenv('SUAP_APPS', 'tocados')
    monkeypatch.setattr(suap_check, 'get_changed_files', lambda: ['comum/models.py', 'djtools/e2e_ui.py', 'erros/tests/e2e/test_erros_e2e.py'])

    suap_check.Command().executar_e2e()

    assert [cmd.split('pytest ')[1].split()[0] for cmd in executados] == ['erros/tests/e2e']


def test_e2e_modulo_dividido_vira_duas_suites_em_shards_diferentes(executados, monkeypatch):
    monkeypatch.setenv('SUAP_APPS', 'geral')
    monkeypatch.setenv('CI_NODE_TOTAL', '3')
    monkeypatch.setenv('CI_NODE_INDEX', '2')
    monkeypatch.setattr(suap_check, 'arquivos_versionados', lambda: [*VERSIONADOS, 'edu/tests/e2e/test_15_rotas_edu.py'])

    suap_check.Command().executar_e2e()

    assert executados == [
        'COVERAGE_FILE=artifacts/.coverage.e2e-edu-rotas pytest edu/tests/e2e/test_15_rotas_edu.py -m e2e --tracing=retain-on-failure '
        '--video=retain-on-failure --output=artifacts/e2e-edu-rotas --cov=. --cov-report='
    ]


def test_e2e_sem_suite_selecionada_nao_coleta(executados, monkeypatch):
    monkeypatch.setenv('SUAP_APPS', 'dependentes')
    monkeypatch.setattr(suap_check, 'get_changed_files', lambda: ['suap/settings_base.py'])
    COLETAS.clear()

    suap_check.Command().executar_e2e()

    assert COLETAS == []
    assert executados == []


def test_e2e_shard_vazio_sai_sem_rodar(executados, monkeypatch):
    monkeypatch.setenv('SUAP_APPS', 'dependentes')
    monkeypatch.setenv('CI_NODE_TOTAL', '3')
    monkeypatch.setenv('CI_NODE_INDEX', '3')
    monkeypatch.setattr(suap_check, 'get_changed_files', lambda: ['demandas/models.py'])

    suap_check.Command().executar_e2e()

    assert executados == []


def test_e2e_suite_vermelha_nao_interrompe_as_demais(executados, monkeypatch):
    monkeypatch.setenv('SUAP_APPS', 'geral')
    monkeypatch.setenv('CI_NODE_TOTAL', '2')
    monkeypatch.setenv('CI_NODE_INDEX', '2')

    def run_command(self, cmd):
        executados.append(cmd)
        if 'erros/tests/e2e' in cmd:
            raise Exception('falhou')

    monkeypatch.setattr(suap_check.Command, 'run_command', run_command)

    with pytest.raises(Exception, match='erros'):
        suap_check.Command().executar_e2e()

    assert len(executados) == 2


COMANDO_E2E_TRANSVERSAL = 'pytest tests/e2e -m e2e --tracing=retain-on-failure --video=retain-on-failure --output=artifacts/e2e-transversal'


def test_e2e_transversal_roda_tests_e2e_sem_cobertura_no_mr(executados, monkeypatch):
    monkeypatch.setenv('SUAP_APPS', 'dependentes')

    suap_check.Command().executar_e2e_transversal()

    assert executados == [COMANDO_E2E_TRANSVERSAL]


def test_e2e_transversal_grava_cobertura_propria_no_geral(executados, monkeypatch):
    monkeypatch.setenv('SUAP_APPS', 'geral')

    suap_check.Command().executar_e2e_transversal()

    assert executados == [f'COVERAGE_FILE=artifacts/.coverage.e2e-transversal {COMANDO_E2E_TRANSVERSAL} --cov=. --cov-report=']


def test_e2e_transversal_vermelho_falha_o_command(executados, monkeypatch):
    monkeypatch.setenv('SUAP_APPS', 'dependentes')

    def run_command(self, cmd):
        raise Exception('pytest falhou')

    monkeypatch.setattr(suap_check.Command, 'run_command', run_command)

    with pytest.raises(Exception, match='Suíte e2e transversal com falha'):
        suap_check.Command().executar_e2e_transversal()


def test_handle_despacha_e2e_transversal(executados, monkeypatch):
    monkeypatch.setenv('SUAP_CHECK', 'e2e-transversal')
    monkeypatch.setenv('SUAP_APPS', 'dependentes')

    suap_check.Command().handle()

    assert executados == [COMANDO_E2E_TRANSVERSAL]


def test_suites_e2e_divide_so_o_modulo_declarado():
    arquivos = [
        'edu/tests/e2e/test_02_curso.py',
        'edu/tests/e2e/test_01_diretoria.py',
        'edu/tests/e2e/test_15_rotas_estrutura.py',
        'edu/tests/e2e/conftest.py',
        'edu/tests/e2e/seed_rotas.py',
        'edu/tests/e2e/test_smoke.py',
        'edu/tests/test_edu.py',
        'erros/tests/e2e/test_erros.py',
    ]

    assert suap_check.suites_e2e({'erros', 'edu'}, arquivos) == {
        'edu': ['edu/tests/e2e/test_01_diretoria.py', 'edu/tests/e2e/test_02_curso.py', 'edu/tests/e2e/test_smoke.py'],
        'edu-rotas': ['edu/tests/e2e/test_15_rotas_estrutura.py'],
        'erros': ['erros/tests/e2e'],
    }


CADEIA_SAUDE = {1, 2, 3, 4, 5, 6, 7, 8, 9, 12, 13, 14, 99}


@pytest.mark.parametrize(('modulo', 'cadeia'), [('saude', CADEIA_SAUDE), ('pesquisa', {*range(1, 12), 15, 17})])
def test_suites_e2e_nao_corta_cadeia(modulo, cadeia):
    """Os arquivos da cadeia ficam todos na 1ª parte; a 2ª roda sozinha, em banco novo."""
    versionados = suap_check.arquivos_versionados()
    suites = suap_check.suites_e2e({modulo}, versionados)

    def numeros(rotulo):
        nomes = [caminho.rsplit('/', 1)[-1].split('_')[1] for caminho in suites[rotulo]]
        return {int(nome) for nome in nomes if nome.isdigit()}

    assert cadeia <= numeros(modulo)
    assert numeros(f'{modulo}-2')
    assert not numeros(f'{modulo}-2') & cadeia


def test_suites_e2e_omite_parte_vazia_da_divisao():
    assert suap_check.suites_e2e({'edu'}, ['edu/tests/e2e/test_01_diretoria.py']) == {'edu': ['edu/tests/e2e/test_01_diretoria.py']}


def test_pesos_por_suite_conta_itens_coletados():
    suites = {'edu': ['edu/tests/e2e/test_1.py'], 'edu-rotas': ['edu/tests/e2e/test_10_rotas_x.py'], 'erros': ['erros/tests/e2e']}
    nodeids = [
        'edu/tests/e2e/test_1.py::test_a[chromium]',
        'edu/tests/e2e/test_10_rotas_x.py::test_rotas[chromium-diretor]',
        'edu/tests/e2e/test_10_rotas_x.py::test_rotas[chromium-aluno]',
        'erros/tests/e2e/sub/test_b.py::Classe::test_c[chromium]',
        'ae/tests/e2e/test_ae.py::test_fora[chromium]',
    ]

    assert suap_check.pesos_por_suite(nodeids, suites) == {'edu': 1, 'edu-rotas': 2, 'erros': 1}


def test_coletar_testes_e2e_devolve_so_node_ids(monkeypatch):
    saida = 'edu/tests/e2e/test_1.py::test_a[chromium]\n\n=== SUAP test resume ===\n1 test collected in 0.1s\n'
    chamadas = []

    def run(cmd, **kwargs):
        chamadas.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout=saida, stderr='')

    monkeypatch.setattr(suap_check.subprocess, 'run', run)

    assert suap_check.coletar_testes_e2e(['edu/tests/e2e/test_1.py']) == ['edu/tests/e2e/test_1.py::test_a[chromium]']
    assert chamadas == [['pytest', '--collect-only', '-q', '-m', 'e2e', 'edu/tests/e2e/test_1.py']]


@pytest.mark.parametrize(('codigo', 'falha'), [(5, False), (2, True)])
def test_coletar_testes_e2e_so_aceita_nada_coletado(monkeypatch, codigo, falha):
    monkeypatch.setattr(
        suap_check.subprocess, 'run', lambda cmd, **kwargs: subprocess.CompletedProcess(cmd, codigo, stdout='ERRO de import', stderr='')
    )

    if falha:
        with pytest.raises(Exception, match='ERRO de import'):
            suap_check.coletar_testes_e2e(['edu/tests/e2e'])
    else:
        assert suap_check.coletar_testes_e2e(['edu/tests/e2e']) == []


@pytest.mark.parametrize(('codigo', 'esperado'), [(0, 0), (1, 1), (5, 0)])
def test_sufixo_aceita_nenhum_teste_trata_exit_5_como_sucesso(codigo, esperado):
    resultado = subprocess.run(['sh', '-c', f'sh -c "exit {codigo}"{SUFIXO_ACEITA_NENHUM_TESTE}'], check=False)

    assert resultado.returncode == esperado


def test_get_changed_files_levanta_erro_quando_git_diff_falha(tmp_path, monkeypatch):
    """``git diff`` sem repositório válido (``GIT_DIR`` inexistente) precisa propagar, não virar seleção vazia."""
    monkeypatch.setattr(suap_check, '_changed_files_cache', None)
    monkeypatch.setenv('GIT_DIR', str(tmp_path / 'sem-repo'))

    with pytest.raises(subprocess.CalledProcessError):
        get_changed_files()
