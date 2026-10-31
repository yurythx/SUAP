"""Reaproveitamento de cenários Behave já executados com sucesso.

Este módulo implementa o mecanismo ``--reuse-successful-scenarios``, que
permite **pular cenários que já passaram** em execuções anteriores quando
o banco de teste é mantido entre execuções (``--keepdb-with-data``).

Motivação
---------
Em suítes BDD grandes, re-executar todos os cenários após corrigir apenas
um ou dois é custoso.  Com o reuso ativado, cenários bem-sucedidos são
registrados em ``successful_scenarios.json`` e automaticamente ignorados
(``scenario.skip``) nas execuções seguintes, até que o arquivo seja
apagado ou o banco seja recriado.

Pré-requisito
-------------
A flag **requer** ``--keepdb-with-data``, pois o banco precisa conter os
dados gerados pelos cenários anteriores para que os cenários subsequentes
(que dependem desses dados) continuem funcionando.

Arquivo de estado
-----------------
O estado é persistido em ``<artifacts>/successful_scenarios.json`` como um
array JSON de objetos::

    [
        {
            'app': 'avaliacao_integrada',
            'feature': 'features/001.AVALIACAO_INTEGRADA.cadastro_gerais.feature',
            'scenario': 'Adicionando os usuários necessários para os testes',
        },
        ...,
    ]

Chave de identificação
~~~~~~~~~~~~~~~~~~~~~~
Cada cenário é identificado univocamente pela string::

    <app_label>::<feature_relativo>::<scenario_name>

Onde ``feature_relativo`` é o caminho do ``.feature`` **sem** o prefixo
``<app_label>/`` (evita duplicidade).

Fluxo de integração
-------------------
::

    environment_base.before_all()
        └─ load_reuse_state(context)         # carrega JSON → context.reuse_state

    environment_base.before_scenario()
        └─ maybe_skip_reused_scenario()      # skip se cenário já passou

    environment_base.after_scenario()
        └─ mark_scenario_success()           # grava cenário que passou

    environment_base.after_all()
        └─ print_reuse_summary()             # imprime caminho do JSON

    runner.BehaveTestRunner.__init__()
        └─ resolve_reuse_successful_scenarios()  # valida uso com keepdb-with-data

    runner.BehaveTestRunner.add_arguments()
        └─ add_reuse_successful_scenarios_argument()  # registra --reuse-...

Exemplo de uso
--------------
::

    # Primeira execução — todos os cenários rodam, os bem-sucedidos são gravados:
    python manage.py test_behave --keepdb-with-data --reuse-successful-scenarios app

    # Segunda execução — cenários já bem-sucedidos são pulados:
    python manage.py test_behave --keepdb-with-data --reuse-successful-scenarios app

    # Para forçar re-execução de todos, apague o arquivo de estado:
    rm /tmp/artifacts/successful_scenarios.json
"""

from __future__ import annotations

import json
import os
import re
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from argparse import ArgumentParser
    from behave.model import Scenario
    from behave.runner import Context


# ---------------------------------------------------------------------------
# Registro de argumentos CLI
# ---------------------------------------------------------------------------


def add_reuse_successful_scenarios_argument(parser: ArgumentParser) -> None:
    """Registra a flag ``--reuse-successful-scenarios`` no parser do runner.

    Chamado por ``BehaveTestRunner.add_arguments()`` para expor a opção ao
    comando ``test_behave``.

    Args:
        parser: ``ArgumentParser`` principal do runner.
    """
    parser.add_argument(
        '--reuse-successful-scenarios',
        dest='reuse_successful_scenarios',
        action='store_true',
        help='Reaproveita cenários já executados com sucesso (requer --keepdb-with-data).',
    )


def resolve_reuse_successful_scenarios(kwargs: dict, keepdb_with_data: bool) -> bool:
    """Extrai e valida a flag ``--reuse-successful-scenarios`` dos kwargs do runner.

    Chamado em ``BehaveTestRunner.__init__()`` para resolver o valor final
    da flag e garantir que ela só seja usada com ``--keepdb-with-data``.

    Args:
        kwargs: Dicionário de argumentos do runner (a chave
            ``'reuse_successful_scenarios'`` é consumida via ``pop``).
        keepdb_with_data: ``True`` se ``--keepdb-with-data`` está ativo.

    Returns:
        ``True`` se o reuso está habilitado.

    Raises:
        RuntimeError: Se a flag for usada sem ``--keepdb-with-data``.
    """
    reuse_successful_scenarios = kwargs.pop('reuse_successful_scenarios', False)
    if reuse_successful_scenarios and not keepdb_with_data:
        raise RuntimeError('--reuse-successful-scenarios requer --keepdb-with-data.')
    return bool(reuse_successful_scenarios)


# ---------------------------------------------------------------------------
# Detecção de modo ativo
# ---------------------------------------------------------------------------


def is_reuse_successful_scenarios_enabled(context: Context) -> bool:
    """Verifica se o reuso de cenários está ativo no contexto Behave atual.

    A detecção usa duas estratégias (em ordem de prioridade):

    1. **Via ``context.config.userdata``**: o runner pode injetar
       ``reuse_successful_scenarios=True`` no userdata da configuração
       Behave.  Aceita valores string (``'1'``, ``'true'``, ``'yes'``,
       ``'on'``) ou booleanos.

    2. **Fallback via ``sys.argv``**: verifica se
       ``--reuse-successful-scenarios`` está presente nos argumentos de
       linha de comando.  Útil quando o userdata não foi configurado.

    Args:
        context: Contexto Behave corrente.

    Returns:
        ``True`` se o reuso está habilitado.
    """
    userdata = getattr(getattr(context, 'config', None), 'userdata', None)
    if userdata:
        value = userdata.get('reuse_successful_scenarios')
        if isinstance(value, str):
            return value.strip().lower() in {'1', 'true', 'yes', 'on'}
        if value is not None:
            return bool(value)
    return '--reuse-successful-scenarios' in sys.argv


# ---------------------------------------------------------------------------
# Extração de credenciais de login dos steps do cenário
# ---------------------------------------------------------------------------

_LOGIN_STEP_RE = re.compile(
    r'realizo o login com o usu[aá]rio "([^"]+)" e senha "([^"]+)"',
    re.IGNORECASE,
)


def _extract_login_from_steps(scenario: Scenario) -> dict[str, str] | None:
    """Extrai credenciais de login dos steps de um cenário Behave.

    Percorre os steps do cenário procurando por::

        Quando realizo o login com o usuário "..." e senha "..."

    Se encontrado, retorna ``{'usuario': ..., 'senha': ...}``.
    Se o cenário tiver múltiplos steps de login, retorna o **último**
    (que representa a sessão ativa ao final do cenário).

    Args:
        scenario: Instância do cenário Behave com ``.steps``.

    Returns:
        Dicionário com credenciais ou ``None`` se não houver step de login.
    """
    login_info = None
    for step in getattr(scenario, 'steps', []):
        match = _LOGIN_STEP_RE.search(step.name)
        if match:
            login_info = {'usuario': match.group(1), 'senha': match.group(2)}
    return login_info


# ---------------------------------------------------------------------------
# Chave de identificação de cenário
# ---------------------------------------------------------------------------


def _reuse_file_path(context: Context) -> str:
    """Retorna o caminho absoluto do arquivo ``successful_scenarios.json``.

    O arquivo fica em ``context.artifact_path`` (normalmente ``/tmp/artifacts/``).
    """
    return os.path.join(context.artifact_path, 'successful_scenarios.json')


def _scenario_key(scenario: Scenario) -> tuple[str, str, str]:
    """Gera a chave única de identificação de um cenário.

    A chave tem o formato ``<app_label>::<feature_relativo>::<scenario_name>``,
    onde ``feature_relativo`` é o caminho do ``.feature`` sem o prefixo
    redundante ``<app_label>/``.

    Args:
        scenario: Instância do cenário Behave.

    Returns:
        Tupla ``(key, app_label, feature_rel)`` onde:
            - ``key``: string de identificação completa.
            - ``app_label``: label da app Django (primeiro segmento do path).
            - ``feature_rel``: caminho relativo do feature file (sem prefixo app).
    """
    app_label = scenario.feature.filename.split('/')[0]
    feature_rel = scenario.feature.filename
    feature_prefix = f'{app_label}/'
    feature_rel = feature_rel.removeprefix(feature_prefix)
    key = f'{app_label}::{feature_rel}::{scenario.name}'
    return key, app_label, feature_rel


def _normalize_key(app_label: str, feature: str, scenario_name: str) -> str:
    """Normaliza componentes de um registro JSON na mesma chave de ``_scenario_key``.

    Aplica a mesma lógica de remoção do prefixo ``<app_label>/`` do feature
    path para garantir consistência entre dados lidos do JSON e dados gerados
    em runtime.

    Args:
        app_label: Label da app.
        feature: Caminho do feature (pode conter o prefixo da app).
        scenario_name: Nome do cenário.

    Returns:
        Chave normalizada ``<app>::<feature_rel>::<scenario>``.
    """
    feature_prefix = f'{app_label}/' if app_label else ''
    if feature_prefix and feature.startswith(feature_prefix):
        feature = feature[len(feature_prefix) :]
    return f'{app_label}::{feature}::{scenario_name}'


# ---------------------------------------------------------------------------
# Carga e persistência de estado
# ---------------------------------------------------------------------------


def load_reuse_state(context: Context) -> None:
    """Carrega o estado de reuso do arquivo ``successful_scenarios.json``.

    Chamado em ``before_all()`` para popular ``context.reuse_state`` com a
    lista de cenários já bem-sucedidos e um set de chaves para lookup rápido.

    O estado é armazenado em ``context.reuse_state`` como::

        {'items': [{'app': ..., 'feature': ..., 'scenario': ...}, ...], 'keys': {'app::feature::scenario', ...}}

    Se o arquivo não existir ou houver erro de leitura, o estado é
    inicializado vazio (sem impedir a execução).

    Args:
        context: Contexto Behave (deve ter ``context.artifact_path`` definido).
    """
    os.makedirs(context.artifact_path, exist_ok=True)
    context.reuse_state = {'items': [], 'keys': set()}
    reuse_file = _reuse_file_path(context)
    try:
        if os.path.exists(reuse_file):
            with open(reuse_file) as f:
                items = json.load(f)
            if isinstance(items, list):
                context.reuse_state['items'] = items
                keys: set[str] = set()
                for item in items:
                    keys.add(
                        _normalize_key(
                            item.get('app', ''),
                            item.get('feature', ''),
                            item.get('scenario', ''),
                        )
                    )
                context.reuse_state['keys'] = keys
    except Exception as exc:
        sys.stderr.write(f'[WARN] Falha ao ler successful_scenarios.json: {exc}\n')
        sys.stderr.flush()


def mark_scenario_success(context: Context, scenario: Scenario) -> None:
    """Registra um cenário bem-sucedido e persiste no arquivo de reuso.

    Chamado em ``after_scenario()`` quando ``scenario.status == passed``.
    Adiciona o cenário à lista em memória e reescreve o arquivo JSON
    completo (append incremental).

    Se o cenário já estiver registrado (mesma chave), a operação é
    idempotente (não duplica).

    Args:
        context: Contexto Behave com ``reuse_state`` carregado.
        scenario: Cenário que passou.
    """
    if not getattr(context, 'reuse_state', None):
        return
    os.makedirs(context.artifact_path, exist_ok=True)
    key, app_label, feature_rel = _scenario_key(scenario)
    if key in context.reuse_state['keys']:
        return
    context.reuse_state['keys'].add(key)
    record = {'app': app_label, 'feature': feature_rel, 'scenario': scenario.name}
    # Persiste credenciais de login usadas no cenário (se houver) para
    # restauração automática de sessão quando o cenário for pulado.
    last_login = getattr(context, '_last_login', None)
    if last_login:
        record['login'] = last_login
    context.reuse_state['items'].append(record)
    reuse_file = _reuse_file_path(context)
    try:
        with open(reuse_file, mode='w') as f:
            json.dump(context.reuse_state['items'], f, ensure_ascii=False, indent=2)
    except Exception as exc:
        sys.stderr.write(f'[WARN] Falha ao gravar successful_scenarios.json: {exc}\n')
        sys.stderr.flush()


# ---------------------------------------------------------------------------
# Skip de cenários reutilizados
# ---------------------------------------------------------------------------


def maybe_skip_reused_scenario(context: Context, scenario: Scenario) -> bool:
    """Pula cenário já executado com sucesso quando o reuso está ativo.

    Chamado em ``before_scenario()``.  Se o cenário estiver registrado no
    estado de reuso, invoca ``scenario.skip()`` para que o Behave o ignore.

    Args:
        context: Contexto Behave com ``reuse_state`` carregado.
        scenario: Cenário prestes a ser executado.

    Returns:
        ``True`` se o cenário foi marcado para skip; ``False`` caso contrário.
    """
    if not is_reuse_successful_scenarios_enabled(context):
        return False
    if not getattr(context, 'reuse_state', None):
        return False
    key, app_label, _ = _scenario_key(scenario)
    if key not in context.reuse_state['keys']:
        return False
    # Preserva credenciais de login do cenário pulado para restauração
    # automática de sessão nos cenários subsequentes.
    # 1) Tenta obter do JSON (registros novos com campo 'login')
    login_found = False
    for item in context.reuse_state['items']:
        item_key = _normalize_key(
            item.get('app', ''),
            item.get('feature', ''),
            item.get('scenario', ''),
        )
        if item_key == key and item.get('login'):
            context._last_skipped_login = item['login']
            login_found = True
            break
    # 2) Fallback: extrai credenciais dos steps do cenário (.feature)
    if not login_found:
        login_info = _extract_login_from_steps(scenario)
        if login_info:
            context._last_skipped_login = login_info
    sys.stderr.write(
        f'[REUSE] Ignorando cenário "{scenario.name}" ({app_label}) '
        'pois --reuse-successful-scenarios está ativo e o cenário já foi executado '
        'com sucesso (registrado em successful_scenarios.json).\n'
    )
    sys.stderr.flush()
    scenario.skip('Reuso ativado: pulando cenário já executado com sucesso.')
    return True


# ---------------------------------------------------------------------------
# Diagnóstico
# ---------------------------------------------------------------------------


def print_reuse_summary(context: Context) -> None:
    """Imprime no stderr o caminho do arquivo de reuso, se existir.

    Chamado em ``after_all()`` para informar ao desenvolvedor onde o
    registro de cenários bem-sucedidos está salvo.

    Args:
        context: Contexto Behave com ``artifact_path`` definido.
    """
    reuse_file = _reuse_file_path(context)
    if os.path.exists(reuse_file):
        sys.stderr.write(f'\n[INFO] Cenários com sucesso registrados em: {reuse_file}\n')
        sys.stderr.flush()
