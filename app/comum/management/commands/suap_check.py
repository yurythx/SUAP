import glob
import json
import os
import shlex
import shutil
import subprocess
import sys
import time
from collections.abc import Iterable, Mapping
from fnmatch import fnmatch

from django.apps import apps
from django.core.management import color_style
from django.template.defaultfilters import slugify

from djtools.management.commands import BaseCommandPlus

areas = {}
for app_config in apps.get_app_configs():
    area = getattr(app_config, 'area', None)
    if area:
        area = slugify(area)
        if area not in areas:
            areas[area] = set()
        areas[area].add(app_config.name)


_changed_files_cache = None


def get_changed_files() -> list[str]:
    """Retorna lista de arquivos alterados (git diff --name-only origin/master..). Resultado cacheado.

    ``check=True``: se o git falhar (ex.: sem remote configurado), levanta em vez de tratar a
    linha de erro do stderr como nome de arquivo — o que faria a seleção dar silenciosamente vazia.
    """
    global _changed_files_cache
    if _changed_files_cache is not None:
        return _changed_files_cache
    resultado = subprocess.run(['git', 'diff', '--name-only', 'origin/master..'], capture_output=True, text=True, check=True)
    _changed_files_cache = [linha for linha in resultado.stdout.splitlines() if linha]
    return _changed_files_cache


# Seleção de testes por módulo e dependência (SUAP_APPS=dependentes). Ver
# docs/superpowers/specs/2026-09-14-ci-testes-por-dependencia-design.md.
#
# Mudança nestes lugares afeta todo módulo, então roda todos os candidatos.
FALLBACK_DIRETORIOS = frozenset({'djtools', 'comum', 'rh'})
FALLBACK_ARQUIVOS = frozenset({'conftest.py'})
# `tests` e `bin` são dos jobs transversais; `suap/settings_test.py` casa `*_test.py` sem ser teste.
NAO_CANDIDATOS_UNITARIO = frozenset({'tests', 'bin', 'suap'})

# Anexado ao comando de teste quando a seleção é por nome de arquivo (não garante coleta real):
# `os.system` roda via `/bin/sh -c`, então troca o exit code 5 do pytest ("nada coletado") por 0.
SUFIXO_ACEITA_NENHUM_TESTE = '; rc=$?; [ $rc -eq 5 ] && exit 0 || exit $rc'

# Cobertura no job: o pytest só grava dados. Relatório com `source = ["."]` analisa todo `.py` do repo,
# executado ou não — medido: 3,5 min de relatório num job de 31 testes. `--cov=.` (e não
# `--cov=<diretório>`) mantém os caminhos do XML relativos à raiz, que é o que o GitLab casa no diff.
COBERTURA_SO_DADOS = '--cov=. --cov-report='

# `SUAP_CHECK` -> método do command, para os modos que só delegam (mantém o `handle` enxuto).
EXECUTORES_DE_TESTE = {'django': 'executar_django', 'e2e': 'executar_e2e', 'e2e-transversal': 'executar_e2e_transversal'}

# Módulo -> (sufixo, padrões de nome de arquivo) da parte que vira a suíte `<modulo>-<sufixo>`; o resto
# do diretório fica em `<modulo>`, então arquivo novo nunca some. Só vale para parte que roda sozinha,
# num banco novo: o `seed_de_rotas` do edu não depende dos fluxos (`edu/tests/e2e/seed_rotas.py`). No
# saude e no pesquisa as partes separadas só usam o seed de sessão — medido rodando cada uma sozinha. O
# resto é cadeia: o saude 12-14 e 99 leem o prontuário que o `test_01` cria; o pesquisa 01-11 é uma
# esteira que o 15 e o smoke de rotas (17) consomem. As rotas do smoke cujo alvo vem da parte separada
# moram num arquivo dela, junto de quem cria o alvo (saude 17, pesquisa 18). Arquivo novo entra pelo
# nome: se depender da cadeia, não pode casar os padrões.
DIVISOES_E2E = {
    'edu': ('rotas', ('test_*_rotas_*.py',)),
    'saude': ('2', ('test_10_*.py', 'test_11_*.py', 'test_15_*.py', 'test_16_*.py', 'test_17_*.py')),
    'pesquisa': ('2', ('test_12_*.py', 'test_13_*.py', 'test_14_*.py', 'test_16_*.py', 'test_18_*.py')),
}

# Duração medida de cada suíte e2e, em segundos — é o PESO com que os shards são montados.
# Promovido à mão do artifact do noturno (ver `executar_e2e`), como a baseline de cobertura.
# Ausente ou incompleto não quebra nada: quem não está aqui é estimado pela contagem.
ARQUIVO_DURACOES_E2E = 'e2e_duracoes.json'
# Só vale quando NÃO há nenhuma medição: com o arquivo vazio, todo peso vira `contagem * k`, que
# é a ordenação de antes (fator uniforme não muda empacotamento) — isto é, o mesmo comportamento
# de hoje até a primeira promoção.
SEGUNDOS_POR_TESTE_PADRAO = 10.0

# Duração de cada teste unitário (node id -> segundos), lida pelo pytest-split para repartir o
# `unitario-modulo` entre os shards. Promovida à mão do noturno, como a do e2e: juntar os
# `artifacts/unitario-duracoes-*.json` dos shards VERDES (`jq -s add ... > unitario_duracoes.json`) —
# com `-x`, um shard vermelho parou no meio. Ausente, o pytest-split reparte pela contagem.
ARQUIVO_DURACOES_UNITARIO = 'unitario_duracoes.json'


def _eh_arquivo_de_teste(caminho: str) -> bool:
    """Replica o ``python_files`` do pytest (``test_*.py`` e ``*_test.py``)."""
    nome = caminho.rsplit('/', 1)[-1]
    return nome.endswith('.py') and (nome.startswith('test_') or nome.endswith('_test.py'))


def candidatos_unitario(arquivos_versionados: Iterable[str]) -> set[str]:
    """Diretórios de topo com arquivo de teste unitário, fora ocultos, transversais e ``suap``.

    Arquivos em ``*/tests/e2e/`` não contam: um módulo só com e2e, selecionado sozinho, faria o
    ``pytest -m "not e2e"`` sair com código 5 (nada coletado).
    """
    candidatos = set()
    for caminho in arquivos_versionados:
        topo, separador, _resto = caminho.partition('/')
        if not separador or topo.startswith('.') or topo in NAO_CANDIDATOS_UNITARIO or '/tests/e2e/' in caminho:
            continue
        if _eh_arquivo_de_teste(caminho):
            candidatos.add(topo)
    return candidatos


def candidatos_e2e(arquivos_versionados: Iterable[str]) -> set[str]:
    """Módulos com arquivo de teste em ``<modulo>/tests/e2e/`` (o ``tests/e2e`` da raiz não casa)."""
    candidatos = set()
    for caminho in arquivos_versionados:
        partes = caminho.split('/')
        if len(partes) >= 4 and partes[1:3] == ['tests', 'e2e'] and _eh_arquivo_de_teste(caminho):
            candidatos.add(partes[0])
    return candidatos


def motivo_fallback(arquivos: Iterable[str]) -> str | None:
    """Primeiro arquivo do diff que obriga a rodar todos os candidatos, ou ``None``."""
    for caminho in arquivos:
        if caminho in FALLBACK_ARQUIVOS or ('/' in caminho and caminho.split('/')[0] in FALLBACK_DIRETORIOS):
            return caminho
    return None


def modulos_afetados(arquivos: Iterable[str], dependencias: Mapping[str, Iterable[str]], candidatos: set[str]) -> set[str]:
    """Candidatos que o diff pode quebrar: diretórios tocados e seus dependentes DIRETOS.

    ``dependencias`` é o ``module_dependencies.json`` (módulo -> de quem ele depende); aqui ele é
    invertido. Fallback devolve todos os candidatos.
    """
    arquivos = [caminho for caminho in arquivos if caminho]
    if motivo_fallback(arquivos):
        return set(candidatos)
    dependentes: dict[str, set[str]] = {}
    for modulo, deps in dependencias.items():
        for dep in deps:
            dependentes.setdefault(dep, set()).add(modulo)
    selecionados = set()
    for topo in {caminho.split('/')[0] for caminho in arquivos}:
        selecionados |= {topo, *dependentes.get(topo, ())}
    return selecionados & candidatos


def modulos_tocados(arquivos: Iterable[str], candidatos: set[str]) -> set[str]:
    """Candidatos cujo diretório o diff toca. Sem dependentes nem fallback: é a regra do e2e em MR (SUAP_APPS=tocados)."""
    return {caminho.split('/')[0] for caminho in arquivos if caminho} & candidatos


def distribuir_shards(pesos: Mapping[str, int], total: int) -> list[list[str]]:
    """Distribuição gulosa e determinística: mais pesada primeiro, sempre no shard menos carregado."""
    shards: list[list[str]] = [[] for _ in range(total)]
    cargas = [0] * total
    for suite in sorted(pesos, key=lambda nome: (-pesos[nome], nome)):
        indice = cargas.index(min(cargas))
        shards[indice].append(suite)
        # ponytail: peso 0 conta como 1, senão suítes sem teste coletado iriam todas para o shard 1.
        cargas[indice] += max(pesos[suite], 1)
    return shards


def argumentos_shard_unitario(geral: bool) -> str:
    """Opções do pytest-split para este shard (``CI_NODE_INDEX``/``CI_NODE_TOTAL``); vazio fora do ``parallel``.

    ``least_duration`` e não o padrão (``duration_based_chunks``): com a seleção pequena de um MR, os
    blocos contíguos do padrão saem desequilibrados. No ``geral`` o shard também mede: lê uma cópia
    do arquivo promovido (o split usa a medição vigente) e, com ``--clean-durations``, reescreve nela
    só os testes que rodou — os N arquivos ficam disjuntos e juntá-los é uma união simples.
    """
    total = int(os.environ.get('CI_NODE_TOTAL', '1'))
    if total <= 1:
        return ''
    indice = os.environ['CI_NODE_INDEX']
    opcoes = f'--splits {total} --group {indice} --splitting-algorithm least_duration'
    if not geral:
        return f'{opcoes} --durations-path {ARQUIVO_DURACOES_UNITARIO}'
    medidas = f'artifacts/unitario-duracoes-{indice}.json'
    os.makedirs('artifacts', exist_ok=True)
    if os.path.exists(ARQUIVO_DURACOES_UNITARIO):
        shutil.copyfile(ARQUIVO_DURACOES_UNITARIO, medidas)
    return f'{opcoes} --durations-path {medidas} --store-durations --clean-durations'


def arquivos_versionados() -> list[str]:
    """Arquivos rastreados pelo git (ignora .venv, artefatos e afins)."""
    return subprocess.run(['git', 'ls-files'], capture_output=True, text=True, check=True).stdout.splitlines()


def carregar_dependencias() -> dict[str, list[str]]:
    with open('module_dependencies.json') as arquivo:
        return json.load(arquivo)


def suites_e2e(modulos: Iterable[str], arquivos_versionados: Iterable[str]) -> dict[str, list[str]]:
    """Rótulo da suíte -> caminhos do pytest. Módulo sem divisão é o diretório; com divisão, listas de arquivos."""
    arquivos_versionados = list(arquivos_versionados)
    suites: dict[str, list[str]] = {}
    for modulo in sorted(modulos):
        if modulo not in DIVISOES_E2E:
            suites[modulo] = [f'{modulo}/tests/e2e']
            continue
        sufixo, padroes = DIVISOES_E2E[modulo]
        arquivos = sorted(c for c in arquivos_versionados if c.startswith(f'{modulo}/tests/e2e/') and _eh_arquivo_de_teste(c))
        separados = [c for c in arquivos if any(fnmatch(c.rsplit('/', 1)[-1], padrao) for padrao in padroes)]
        # Parte vazia fica de fora: `pytest` sem caminho coletaria o repositório inteiro.
        partes = {modulo: [c for c in arquivos if c not in separados], f'{modulo}-{sufixo}': separados}
        suites.update({rotulo: caminhos for rotulo, caminhos in partes.items() if caminhos})
    return suites


def pesos_por_suite(nodeids: Iterable[str], suites: Mapping[str, list[str]]) -> dict[str, int]:
    """Testes coletados por suíte (parametrização conta) — proxy de duração para distribuir os shards."""
    pesos = dict.fromkeys(suites, 0)
    for nodeid in nodeids:
        arquivo = nodeid.split('::', 1)[0]
        for rotulo, caminhos in suites.items():
            if any(arquivo == caminho or arquivo.startswith(f'{caminho}/') for caminho in caminhos):
                pesos[rotulo] += 1
                break
    return pesos


def carregar_duracoes_e2e(caminho: str = ARQUIVO_DURACOES_E2E) -> dict[str, float]:
    """Durações medidas por suíte. Arquivo ausente é o caso normal antes da primeira promoção."""
    try:
        with open(caminho) as arquivo:
            return json.load(arquivo)
    except FileNotFoundError:
        return {}


def pesos_em_segundos(contagens: Mapping[str, int], duracoes: Mapping[str, float]) -> dict[str, int]:
    """Peso de cada suíte em SEGUNDOS: a duração medida quando existe, a estimada quando não.

    A contagem de testes sozinha é um proxy ruim de duração — medido no pipeline 60931, três
    shards com pesos 193/181/173 levaram 14,9/40,4/30,9 min, porque um teste de ``ae`` custa
    ~4,6 s e um de ``edu``/``pesquisa`` ~13 s. O empacotamento estava certo; a régua é que era.

    Misturar as duas unidades no mesmo vetor seria pior que só contar: uma suíte nova de 100
    testes pesaria 100 contra os 2.400 segundos do ``edu`` e cairia sempre no mesmo shard. Por
    isso a estimativa também sai em segundos, pela média de segundos por teste das suítes já
    medidas.

    Essa média é deliberadamente grosseira: como a dispersão entre suítes é de ~3x, uma suíte
    ainda não medida pode ser mal pesada nessa proporção. É aceitável porque se corrige sozinha
    — na primeira vez que ela roda, ganha duração própria e a estimativa sai de cena.

    A duração é autocontida por suíte: cada ``rodar_suite_e2e`` é uma invocação de pytest sem
    ``--reuse-db``, então cada uma cria o próprio banco e o número não depende da posição da
    suíte dentro do shard.
    """
    testes_medidos = sum(contagem for rotulo, contagem in contagens.items() if rotulo in duracoes)
    segundos_medidos = sum(duracoes[rotulo] for rotulo in contagens if rotulo in duracoes)
    media = segundos_medidos / testes_medidos if testes_medidos else SEGUNDOS_POR_TESTE_PADRAO
    return {rotulo: round(duracoes.get(rotulo, contagem * media)) for rotulo, contagem in contagens.items()}


def coletar_testes_e2e(caminhos: Iterable[str]) -> list[str]:
    """Node ids e2e dos caminhos (``pytest --collect-only``, ~6 s sem banco).

    Contar ``def test_`` no arquivo subestimava as rotas do edu pela metade: são poucas funções
    parametrizadas em dezenas de URLs.
    """
    processo = subprocess.run(['pytest', '--collect-only', '-q', '-m', 'e2e', *caminhos], capture_output=True, text=True, check=False)
    # 5 = nada coletado (suíte só com testes fora do marcador); qualquer outro código é erro de coleta.
    if processo.returncode not in (0, 5):
        raise Exception(f'Falha ao coletar os testes e2e (código {processo.returncode}):\n{processo.stdout[-3000:]}{processo.stderr[-3000:]}')
    return [linha for linha in processo.stdout.splitlines() if '::' in linha]


class Command(BaseCommandPlus):
    help = 'Verificações automáticas do código do SUAP'
    apps = ''
    modules = []

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        # Por instância e não de classe: dicionário mutável em atributo de classe vaza entre
        # invocações no mesmo processo (o que os testes fazem).
        self.duracoes_e2e: dict[str, float] = {}

    def add_arguments(self, parser):
        parser.add_argument('args', nargs='*', type=str)

    def get_apps(self, apps, n):
        import math

        tamanho = math.ceil(len(apps) / n)
        splitted_apps = []
        for i in range(n):
            splitted_apps.append(apps[i * tamanho : i * tamanho + tamanho])
        return splitted_apps

    def print_warning(self, val):
        self.stderr.write(val, style_func=self.style.WARNING)
        self.stderr.flush()
        sys.stderr.flush()

    def print_error(self, val):
        self.stderr.write(val, style_func=self.style.ERROR)
        self.stderr.flush()
        sys.stderr.flush()

    def print_success(self, val):
        self.stdout.write(val, style_func=self.style.SUCCESS)
        self.stdout.flush()
        sys.stdout.flush()

    def run_command(self, command):
        os.environ['PYTHONUNBUFFERED'] = '1'
        result = os.system(command)

        # testes falharam?
        if result:
            raise Exception(f'Falha no comando "{command}"')

    def get_modules(self):
        changed_files = get_changed_files()
        self.print_success('Arquivos afetados: ')
        for output in changed_files:
            self.print_success(output)

    def get_changed_modules(self):
        """Detecta módulos alterados no MR e retorna conjunto de apps a testar."""
        changed_files = get_changed_files()
        changed_dirs = set()
        for output in changed_files:
            if output:
                top_dir = output.split('/')[0]
                changed_dirs.add(top_dir)

        # Mapeamento: app_name -> area_slug (apenas apps com behave tests)
        app_to_area = {}
        for area_slug, app_names in areas.items():
            for app_name in app_names:
                app_to_area[app_name] = area_slug

        apps_to_test = set()
        for changed_dir in sorted(changed_dirs):
            if changed_dir in app_to_area:
                apps_to_test.add(changed_dir)

        if apps_to_test:
            self.print_success(f'>>> Módulos alterados: {", ".join(sorted(apps_to_test))}')
        else:
            self.print_success('>>> Nenhum módulo com behave tests foi alterado.')

        return apps_to_test

    def check_precommit(self):
        cmd = 'pre-commit run --from-ref origin/master --to-ref HEAD'
        self.print_success(f'>>> Checando por warnings do django com "{cmd}" ...')

        self.run_command(cmd)

    def check_problems(self):
        cmd = 'python manage.py check'
        self.print_success(f'>>> Checando problemas com "{cmd} ...')

        process = subprocess.Popen(shlex.split(cmd), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=False)
        output = ''
        for line in iter(process.stdout.readline, b''):
            output += line.rstrip().decode()

        self.print_success(output)
        if process.returncode:
            raise Exception('Erro ao rodar "{cmd}"')

        if 'RuntimeWarning' in output:
            raise Exception('Erro de RuntimeWarning. Por favor, corrija seu código.')

    def check_migrations(self):
        cmd = 'python manage.py makemigrations --dry-run --noinput --check'
        self.print_success(f'>>> Checando migrations com "{cmd} ...')

        self.run_command(cmd)

    def check_imports_migrations(self):
        cmd = '! find . -name "*.py" -type f | grep "migrations" | xargs grep -r "from .*models" | grep -v django'
        self.print_success('>>> Checando imports de migrações...')

        self.run_command(cmd)

    def check_permissions(self):
        cmd = 'python manage.py sync_permissions --check'
        self.print_success(f'>>> Checando permissões com "{cmd}" ...')

        self.run_command(cmd)

    def check_collectstatic(self):
        cmd = 'python manage.py collectstatic --no-input -c -v 0'
        self.print_success(f'>>> Checando arquivos estáticos com "{cmd}"...')

        self.run_command(cmd)

    def check_dependencies(self):
        cmd = 'python manage.py module_dependencies --check --all'
        self.print_success(f'>>> Checando dependências de módulos com "{cmd}"...')

        self.run_command(cmd)

    def check_celery(self):
        cmd = 'celery -A suap report > /dev/null'
        self.print_success(f'>>> Checando funcionamento do celery com "{cmd}"...')

        self.run_command(cmd)

    def test_django(
        self,
        apps: str = '',
        aceitar_nenhum_teste: bool = False,
        cobertura: str = '--cov=. --cov-report=term-missing --cov-report=xml:artifacts/coverage.xml',
        shard: str = '',
    ) -> None:
        # --cov-report=xml gera artifacts/coverage.xml (cobertura consumida pelo GitLab MR)
        # -m "not e2e" exclui os testes de browser, que moram em <modulo>/tests/e2e/ e
        # seriam coletados aqui junto com os unitários da app. Eles precisam de invocação
        # própria (job `e2e` do CI): sobem servidor e Chromium, e o
        # django_db_modify_db_settings deles é session-scoped, então uma run mista
        # disputaria o nome do banco de teste. Ver djtools/e2e_fixtures.py.
        # -n 3, não 4: os runners têm ~7,6 GB e os jobs rodam no ci.slice (teto de ~6 GB, sem
        # swap; cosinf/suap-runners). Cada worker do xdist chega a ~1,25 GB nos fluxos pesados
        # (edu, pesquisa, remanejamento): 4 workers + Postgres estouram o teto e o kernel mata um
        # worker no meio do job (4 OOM em cicd-2/cicd-3 em 24 e 25/09/2026).
        cmd = f'pytest -n 3 -x -m "not e2e" {cobertura} {shard} {apps}'
        if aceitar_nenhum_teste:
            # Seleção por nome de arquivo não garante coleta (ex.: módulo só com teste e2e
            # marcado, ou classes não reconhecidas pelo pytest); exit 5 = nada coletado, não é falha.
            cmd += SUFIXO_ACEITA_NENHUM_TESTE
        self.print_success(f'>>> Testes do django com "{cmd}"...')
        self.run_command(cmd)

    def test_behave(self, apps=''):
        cmd = 'python'
        if os.environ.get('SUAP_CHECK') == 'generate_doc':
            behave_format = 'plain'
        else:
            behave_format = 'progress'

        assert behave_format
        # if os.environ.get('SUAP_CHECK') == 'behave' and os.environ.get('JOB_ID'):
        #     cmd = 'coverage run'
        cmd += f' manage.py test_behave --behave_stop --noinput {apps}'
        self.print_success(f'>>> Testes do behave com "{cmd}"...')
        self.run_command(cmd)

    def selecionar(self, candidatos: set[str]) -> set[str]:
        """Aplica ``SUAP_APPS`` (``geral`` = todos; ``tocados`` = só os tocados; outro = recorte por dependência) e registra o motivo."""
        if os.environ.get('SUAP_APPS') == 'geral':
            return set(candidatos)
        arquivos = get_changed_files()
        if os.environ.get('SUAP_APPS') == 'tocados':
            selecionados = modulos_tocados(arquivos, candidatos)
            self.print_success(f'>>> Selecionados (só módulos tocados): {", ".join(sorted(selecionados)) or "nenhum"}')
            return selecionados
        motivo = motivo_fallback(arquivos)
        if motivo:
            self.print_success(f'>>> Fallback (todos os candidatos) por causa de: {motivo}')
        selecionados = modulos_afetados(arquivos, carregar_dependencias(), candidatos)
        self.print_success(f'>>> Selecionados: {", ".join(sorted(selecionados)) or "nenhum"}')
        return selecionados

    def executar_django(self) -> None:
        """``SUAP_CHECK=django``: ``dependentes``/``geral`` calculam os módulos; outro valor é lista literal de caminhos.

        O pytest só grava dados de cobertura. Fora do ``geral`` (noturno, cujos relatórios saem da soma no
        ``cobertura-combinada``), o XML é gerado depois só com os diretórios executados — mesmo com teste vermelho.
        """
        suap_apps = os.environ['SUAP_APPS']
        if suap_apps in ('dependentes', 'geral'):
            diretorios = self.selecionar(candidatos_unitario(arquivos_versionados()))
            if not diretorios:
                self.print_success('>>> Nenhum módulo com testes afetado.')
                return
            # Só aqui o shard: o grupo pode sair vazio (exit 5), e só este caminho aceita nenhum teste.
            apps, aceitar_nenhum_teste, shard = ' '.join(sorted(diretorios)), True, argumentos_shard_unitario(suap_apps == 'geral')
        else:
            diretorios, apps, aceitar_nenhum_teste, shard = set(suap_apps.split()), suap_apps, False, ''
        try:
            self.test_django(apps, aceitar_nenhum_teste=aceitar_nenhum_teste, cobertura=COBERTURA_SO_DADOS, shard=shard)
        finally:
            if suap_apps != 'geral':
                self.gerar_xml_cobertura(diretorios)

    def gerar_xml_cobertura(self, diretorios: Iterable[str]) -> None:
        """Gera ``artifacts/coverage.xml`` (anotações do diff no MR) só com os arquivos dos diretórios executados."""
        from coverage import Coverage
        from coverage.exceptions import NoDataError

        cobertura = Coverage()
        cobertura.load()
        # Com `-x`, o xdist é interrompido antes de o pytest-cov juntar os dados: sobram só os arquivos
        # dos workers (`<data_file>.<host>.<pid>...`). `keep=True` não apaga nada; sem restos, não muda nada.
        cobertura.combine(keep=True)
        try:
            cobertura.xml_report(include=[f'{diretorio}/*' for diretorio in sorted(diretorios)], outfile='artifacts/coverage.xml')
        except NoDataError:
            self.print_success('>>> Sem dados de cobertura dos diretórios executados; coverage.xml não gerado.')

    def executar_e2e(self) -> None:
        """``SUAP_CHECK=e2e``: seleciona as suítes, distribui entre os shards do job e roda as deste shard."""
        versionados = arquivos_versionados()
        suites = suites_e2e(self.selecionar(candidatos_e2e(versionados)), versionados)
        contagens = pesos_por_suite(coletar_testes_e2e(c for caminhos in suites.values() for c in caminhos), suites) if suites else {}
        duracoes = carregar_duracoes_e2e()
        pesos = pesos_em_segundos(contagens, duracoes)
        total = int(os.environ.get('CI_NODE_TOTAL', '1'))
        indice = int(os.environ.get('CI_NODE_INDEX', '1'))
        shards = distribuir_shards(pesos, total)
        for numero, rotulos in enumerate(shards, start=1):
            composicao = ', '.join(f'{s} ({pesos[s]}s{"" if s in duracoes else " estimado"})' for s in rotulos)
            self.print_success(f'>>> Shard {numero}/{total}: {composicao or "vazio"}')
        if not shards[indice - 1]:
            self.print_success('>>> Nenhuma suíte e2e neste shard.')
            return
        vermelhas = [rotulo for rotulo in shards[indice - 1] if not self.rodar_suite_e2e(rotulo, ' '.join(suites[rotulo]))]
        self.gravar_duracoes_e2e(indice)
        if vermelhas:
            raise Exception(f'Suítes e2e com falha: {", ".join(vermelhas)}')

    def gravar_duracoes_e2e(self, indice: int) -> None:
        """Despeja as durações medidas NESTE shard; o noturno produz um arquivo por shard.

        São N arquivos e não um porque cada shard é um job separado, e cada um só conhece as
        suítes que rodou. Promover é juntar os N e substituir o `ARQUIVO_DURACOES_E2E` — passo a
        mais que a baseline de cobertura não tem, daí a instrução dizer isso na cara.
        """
        if not self.duracoes_e2e:
            return
        destino = f'artifacts/e2e-duracoes-{indice}.json'
        try:
            # `artifacts/` pode não existir: quem o cria é o `--output` do Playwright, e com
            # `retain-on-failure` ele só escreve quando algum teste falha. Com o shard todo
            # verde o diretório não chega a nascer — foi o job 435997, verde em 5 suítes e
            # vermelho na gravação.
            os.makedirs('artifacts', exist_ok=True)
            with open(destino, 'w') as arquivo:
                json.dump(self.duracoes_e2e, arquivo, indent=2, sort_keys=True)
        except OSError as falha:
            # Medição é insumo de planejamento, não resultado de teste: perdê-la adia um
            # rebalanceamento, derrubar o job por ela reprova código que passou.
            self.print_warning(f'>>> Não foi possível gravar {destino}: {falha}')
            return
        self.print_success(f'>>> Durações medidas em {destino}.')
        self.print_success(f'>>> Para rebalancear os shards: junte os artifacts/e2e-duracoes-*.json dos shards em {ARQUIVO_DURACOES_E2E}.')

    def executar_e2e_transversal(self) -> None:
        """``SUAP_CHECK=e2e-transversal``: sempre ``tests/e2e``, sem seleção nem shard; cobertura só no ``geral``."""
        if not self.rodar_suite_e2e('transversal', 'tests/e2e'):
            raise Exception('Suíte e2e transversal com falha')

    def rodar_suite_e2e(self, rotulo: str, caminho: str) -> bool:
        """Uma invocação de pytest por suíte, isolada como no job por módulo antigo. Cobertura só no ``geral``."""
        cmd = f'pytest {caminho} -m e2e --tracing=retain-on-failure --video=retain-on-failure --output=artifacts/e2e-{rotulo}'
        if os.environ.get('SUAP_APPS') == 'geral':
            cmd = f'COVERAGE_FILE=artifacts/.coverage.e2e-{rotulo} {cmd} --cov=. --cov-report='
        self.print_success(f'>>> e2e de {rotulo} com "{cmd}"...')
        inicio = time.monotonic()
        try:
            self.run_command(cmd)
        except Exception:
            # Suíte vermelha não vira peso: com `--maxfail`, ela pode ter parado no meio, e o
            # número mediria a interrupção, não a suíte.
            return False
        self.duracoes_e2e[rotulo] = round(time.monotonic() - inicio, 1)
        return True

    def check_coverage(self):
        if not glob.glob('artifacts/.coverage.*') and not os.path.exists('artifacts/.coverage'):
            raise Exception('Nenhum dado de coverage encontrado. Execute SUAP_CHECK=django primeiro.')

        self.run_command('coverage xml -o artifacts/coverage.xml')

        from coverage import Coverage

        cov = Coverage()
        cov.load()
        data = cov.get_data()

        per_module = {}
        for fname in data.measured_files():
            mod = os.path.relpath(fname).split('/')[0]
            _fname, executable, excluded, missing, _fmt = cov.analysis2(fname)
            per_module.setdefault(mod, {'executable': 0, 'excluded': 0, 'missing': 0})
            per_module[mod]['executable'] += len(executable)
            per_module[mod]['excluded'] += len(excluded)
            per_module[mod]['missing'] += len(missing)

        current_pct = {
            mod: ((v['executable'] - v['excluded'] - v['missing']) / (v['executable'] - v['excluded']) * 100)
            if (v['executable'] - v['excluded'])
            else 0.0
            for mod, v in per_module.items()
        }

        try:
            with open('.coverage_baseline.json') as f:
                baseline = json.load(f)
        except FileNotFoundError, json.JSONDecodeError:
            baseline = {}

        suap_apps = os.environ.get('SUAP_APPS', 'geral')
        if suap_apps == 'geral':
            display_set = current_pct
        else:
            changed = self.get_changed_modules()
            display_set = {k: v for k, v in current_pct.items() if k in changed}

        filter_active = suap_apps != 'geral'

        COVERAGE_THRESHOLD = 5  # pp — drops below this are not regressions
        regressions, improvements, new_mods = [], [], []
        for mod, pct in sorted(display_set.items()):
            if mod not in baseline:
                new_mods.append((mod, pct))
            elif baseline[mod] - pct >= COVERAGE_THRESHOLD:
                regressions.append((mod, baseline[mod], pct))
            elif pct > baseline[mod]:
                improvements.append((mod, baseline[mod], pct))

        removed = [m for m in baseline if m not in display_set]

        self.print_success('=' * 60)
        self.print_success('RELATORIO DE COBERTURA POR MODULO')
        self.print_success('=' * 60)

        if regressions:
            self.print_error('')
            self.print_error('REGRESSOES (cobertura diminuiu):')
            for mod, base, cur in regressions:
                self.print_error(f'   {mod}: {base:.2f}% -> {cur:.2f}% (-{base - cur:.2f}pp)')

        if improvements:
            self.print_success('')
            self.print_success('MELHORIAS (cobertura aumentou):')
            for mod, base, cur in improvements:
                self.print_success(f'   {mod}: {base:.2f}% -> {cur:.2f}% (+{cur - base:.2f}pp)')

        if new_mods:
            self.print_success('')
            self.print_success('NOVOS MODULOS (sem baseline):')
            for mod, pct in new_mods:
                self.print_success(f'   {mod}: {pct:.2f}%')

        if removed and not filter_active:
            self.print_warning('')
            self.print_warning('MODULOS REMOVIDOS (no baseline mas sem cobertura):')
            for mod in removed:
                self.print_warning(f'   {mod}')

        stable = [
            (m, display_set[m])
            for m in sorted(display_set)
            if m in baseline and baseline[m] - display_set[m] < COVERAGE_THRESHOLD and display_set[m] <= baseline[m]
        ]
        if stable:
            self.print_success('')
            self.print_success('ESTAVEIS (sem mudanca):')
            for mod, pct in stable:
                self.print_success(f'   {mod}: {pct:.2f}%')

        self.print_success('')
        self.print_success('=' * 60)

        with open('artifacts/.coverage_current.json', 'w') as f:
            json.dump(current_pct, f, indent=2, sort_keys=True)

        self.print_success(
            '>>> Caso necessário copie artifacts/.coverage_current.json para .coverage_baseline.json para atualizar a baseline de cobertura.'
        )

        if regressions:
            raise Exception(f'Cobertura diminuiu em {len(regressions)} modulo(s).')

    def handle(self, *args, **options):
        self.style = color_style(True)
        try:
            if os.environ.get('SUAP_CHECK') == 'code':
                self.get_modules()
                self.check_celery()
                self.check_precommit()
                self.check_problems()
                self.check_dependencies()
                self.check_migrations()
                self.check_imports_migrations()
                self.check_permissions()
                self.check_collectstatic()
            elif os.environ.get('SUAP_CHECK') in EXECUTORES_DE_TESTE:
                getattr(self, EXECUTORES_DE_TESTE[os.environ['SUAP_CHECK']])()
            elif os.environ.get('SUAP_CHECK') == 'behave':
                self.test_behave(' '.join(sorted(areas[os.environ['SUAP_APPS']])))
            elif os.environ.get('SUAP_CHECK') == 'behave-changed':
                apps_to_test = self.get_changed_modules()
                if apps_to_test:
                    self.test_behave(' '.join(sorted(apps_to_test)))
            elif os.environ.get('SUAP_CHECK') == 'coverage':
                self.check_coverage()
            elif os.environ.get('SUAP_CHECK') == 'generate_doc':
                self.test_behave()
            else:
                self.get_modules()
                self.check_celery()
                self.check_precommit()
                self.check_problems()
                self.check_dependencies()
                self.check_migrations()
                self.check_imports_migrations()
                self.check_permissions()
                self.check_collectstatic()
                self.test_django()
                self.test_behave()
            self.print_success('Testes finalizados com sucesso.')

        except Exception as e:
            self.print_error(str(e))
            sys.exit(1)
