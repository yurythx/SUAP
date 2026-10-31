#!/usr/bin/env -S uv run --quiet python3
"""Registra o tempo gasto (horas de trabalho medidas) ao criar OU atualizar MRs.

**No Claude Code, sob pedido.** Chamado com ``--sob-pedido`` — e só o ``.claude/settings.json``
passa essa flag —, só registra quando o comando pede, com ``REGISTRAR_TEMPO=True`` prefixado
ao ``glab``::

    REGISTRAR_TEMPO=True glab mr create --source-branch ... --yes

Sem o prefixo, não registra nada — nem rede, nem varredura de transcrição (ver
``pediu_registro_de_tempo``). O pedido viaja no texto do comando porque é só isso que este
script enxerga: ele roda num processo à parte, e um ``export`` no shell do agente não chega
até aqui. Pela ferramenta MCP do GitLab não há texto de comando, então por ela, no Claude
Code, o registro fica desligado.

**Codex e OpenCode não mudam.** Os dois chamam este mesmo script **sem** argumentos, e sem
``--sob-pedido`` não há portão: registram em todo MR, como sempre. Manter a flag fora dos
adaptadores deles é contrato — ver ``_somente_claude_pede`` no teste.

Fonte única de verdade, compartilhada entre Claude Code (PostToolUse em
``.claude/settings.json``, matcher ``create_merge_request|update_merge_request|Bash``) e
OpenCode (``.opencode/plugin/register-mr-time-spent.ts``: hook ``execute.after`` no 2.x,
``tool.execute.after`` no 1.x).
Ambos invocam este script passando, via stdin, o mesmo JSON ``{tool_input, tool_response}``
da ferramenta de criação/atualização de MR.

Dois caminhos chegam até aqui: a ferramenta MCP do GitLab, que entrega ``iid`` e
``project_id`` no ``tool_response``, e o CLI ``glab``, cujo ``Bash`` só deixa a URL do MR
na saída — ver ``contexto_glab``. O matcher de hook do Claude Code só casa nome de
ferramenta, então casar ``Bash`` significa que este script roda a cada comando de shell:
ele desiste antes de qualquer git ou rede quando o comando não é ``glab mr create|update``.

Cálculo do esforço — **tempo ativo medido**, não estimativa:
  - Soma os intervalos entre eventos consecutivos das transcrições do agente
    (``~/.claude/projects/<slug-do-cwd>/**/*.jsonl``), descartando espera: o intervalo só
    conta inteiro quando o agente produziu os eventos das duas pontas (teto
    ``TOOL_MAX_S``); com qualquer ponta humana, entra limitado a ``IDLE_MAX_S``. Assim
    sessão retomada horas depois não vira hora trabalhada, e uma suíte de testes de
    20 min vira. Só contam eventos posteriores ao ponto de partida da branch
    (``merge-base``), senão o diretório do repositório principal — que acumula todas as
    sessões já feitas nele — inflaria o total.
  - Quem é "o agente" não é o campo ``type`` sozinho (ver ``evento_do_agente``): resultado
    de ferramenta e aviso de tarefa em segundo plano chegam com tipo de humano, e tratá-los
    como espera zerava justamente o relógio que este script existe para medir. A varredura
    é recursiva porque a transcrição de cada subagente mora em
    ``<sessao>/subagents/*.jsonl`` — num porte de módulo elas passam da principal em bytes.
    Como tudo entra numa linha do tempo única e ordenada, trabalho de subagente que corre
    em paralelo com o do agente principal colapsa no mesmo intervalo em vez de somar duas
    vezes.
  - Sem transcrição (é o caso do OpenCode, que não a expõe), cai no *backfiring* por
    LOC: horas = linhas adicionadas no diff ÷ 50 (taxa Python/Django).

Registra apenas o **delta** via ``/spend`` numa nota do MR (API GitLab): lê o
``time_stats.total_time_spent`` do MR e registra só o incremento até a medição atual —
assim updates do MR não fazem double-count (delta ≤ 0 → não registra).
Resiliente por design: qualquer falha resulta em exit 0 — nunca bloqueia a criação/
atualização do MR. Mas **não é silenciosa**: o motivo vai para stderr, porque falha muda
sem rastro significa meses de MRs sem tempo registrado sem ninguém notar.

Credenciais, em ordem: ``GITLAB_TOKEN`` → token embutido no remote HTTPS → token do
``glab`` CLI. O host vem do remote (HTTPS ou SSH) ou de ``GITLAB_HOST``. O token do
``glab`` é OAuth, que o header ``PRIVATE-TOKEN`` recusa, então a chamada de API tenta
``PRIVATE-TOKEN`` e, em 401/403, repete com ``Authorization: Bearer``.

Uso isolado para teste:  ``echo '<payload>' | register_mr_time_spent.py --dry-run``
Só o tempo ativo medido:  ``register_mr_time_spent.py --horas [branch-base]``
"""

from __future__ import annotations

import itertools
import json
import os
import re
import shlex
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

BACKFIRING_LOC_POR_HORA = 50
IDLE_MAX_S = 300
TOOL_MAX_S = 3600
# Trecho fixo do <event> da notificação de expiração do Monitor (ver ``evento_do_agente``).
EXPIRACAO_MONITOR = 'Monitor expired after'
TIPOS_DO_AGENTE = ('assistant', 'system')
MARCADOR_NOTA = '⏱️ **Tempo de trabalho registrado**'
PARAMETRO_REGISTRO = 'REGISTRAR_TEMPO'
# Liga o portão opt-in. Passada SÓ por ``.claude/settings.json``: o Codex e o OpenCode
# chamam este script sem argumentos e mantêm o registro sempre ligado.
FLAG_SOB_PEDIDO = '--sob-pedido'
EXCLUI_TRECHOS = ('/migrations/', 'uv.lock', 'package-lock.json', 'yarn.lock')
EXCLUI_SUFIXOS = ('.json', '.svg', '.lock', '.po', '.mo', '.map', '.min.js', '.min.css')


def _log(mensagem: str) -> None:
    """Rastro em stderr. Falha sem rastro = MRs sem tempo registrado por meses."""
    print(f'[register_mr_time_spent] {mensagem}', file=sys.stderr)


def _try_json(texto: str | None) -> dict:
    try:
        return json.loads(texto) if texto and texto.strip() else {}
    except ValueError, TypeError:
        return {}


def _run_git(args: list[str]) -> str:
    try:
        res = subprocess.run(['git', *args], capture_output=True, text=True, timeout=30, check=False)
    except OSError, subprocess.SubprocessError:
        return ''
    return res.stdout if res.returncode == 0 else ''


def _eh_codigo(caminho: str) -> bool:
    if any(t in caminho for t in EXCLUI_TRECHOS):
        return False
    return not caminho.endswith(EXCLUI_SUFIXOS)


def loc_adicionadas(target: str, source: str) -> int:
    """Soma as linhas adicionadas no diff ``target...source``, ignorando ruído não-código."""
    total = 0
    for linha in _run_git(['diff', '--numstat', f'{target}...{source}']).splitlines():
        partes = linha.split('\t')
        if len(partes) == 3 and partes[0].isdigit() and _eh_codigo(partes[2]):
            total += int(partes[0])
    return total


def dir_transcricoes(payload: dict) -> Path | None:
    """Diretório das transcrições do agente para o cwd atual, ou ``None`` se não houver.

    O Claude Code manda ``transcript_path`` no payload do hook; quando não manda (ou
    quando o chamador é o OpenCode), o diretório é derivado do cwd pela mesma regra de
    slug que o Claude Code usa: ``/`` e ``.`` viram ``-``.
    """
    tp = payload.get('transcript_path')
    if tp:
        return Path(tp).parent
    cwd = payload.get('cwd') or os.environ.get('CLAUDE_PROJECT_DIR') or os.getcwd()
    diretorio = Path.home() / '.claude' / 'projects' / re.sub(r'[/.]', '-', str(cwd))
    return diretorio if diretorio.is_dir() else None


def evento_do_agente(registro: dict) -> bool:
    """Se este evento foi produzido pelo agente trabalhando (e não por uma pessoa).

    O campo ``type`` sozinho engana, e engana **sempre para o mesmo lado** — o de
    subestimar. Dois casos, ambos medidos numa sessão real:

    - ``user`` é o tipo tanto da sua mensagem quanto do **resultado de uma ferramenta**
      (80 de 93 registros numa sessão de porte de módulo). Tratar todos como humano fazia
      o par ``assistant`` → ``user``, o mais comum da transcrição, cair no teto de espera:
      a suíte de 20 min que a docstring promete contar inteira contava 5 min;
    - ``queue-operation`` é o tipo tanto de você digitando quanto do ``<task-notification>``
      que a máquina enfileira ao terminar tarefa em segundo plano. O segundo fecha o
      intervalo em que o agente esperou pipeline ou subagente — relógio ocupado, não espera.
      Exceção: a notificação de **expiração do Monitor** (``Monitor expired after …``) só avisa
      que o watch acabou sem trazer nada — é ociosidade, vale como lado humano. Sem isso, um
      loop que rearma o Monitor a cada 30 min vira uma cadeia agente → agente de 1 h por ciclo.

    Três casos, então: (1) tipos do agente e resultado de ferramenta contam; (2) ``task-notification``
    de conclusão/evento com conteúdo conta; (3) ``task-notification`` de expiração de Monitor não.

    Discriminar por ``toolUseResult``/conteúdo é o que separa os dois sem contar como
    trabalho a pausa em que você foi almoçar.
    """
    tipo = str(registro.get('type') or '')
    if tipo in TIPOS_DO_AGENTE:
        return True
    if tipo == 'user':
        return 'toolUseResult' in registro
    if tipo == 'queue-operation':
        conteudo = str(registro.get('content') or '').lstrip()
        return conteudo.startswith('<task-notification>') and EXPIRACAO_MONITOR not in conteudo
    return False


def _eventos(diretorio: Path, desde: datetime | None) -> list[tuple[datetime, bool]]:
    """``(momento, é_do_agente)`` de cada evento das transcrições, em ordem cronológica.

    ``rglob`` e não ``glob``: a transcrição de cada subagente fica em
    ``<sessao>/subagents/*.jsonl``, e ignorá-las descartava o grosso do trabalho de um
    porte de módulo — os dois subagentes desta branch geraram 2 MB contra 852 KB da sessão
    principal.
    """
    eventos = []
    for arquivo in diretorio.rglob('*.jsonl'):
        for linha in arquivo.read_text(errors='ignore').splitlines():
            registro = _try_json(linha)
            marca = registro.get('timestamp')
            quando = _parse_iso(marca) if isinstance(marca, str) else None
            if quando and (desde is None or quando >= desde):
                eventos.append((quando, evento_do_agente(registro)))
    return sorted(eventos)


def _parse_iso(texto: str) -> datetime | None:
    try:
        return datetime.fromisoformat(texto)
    except ValueError:
        return None


def inicio_da_branch(target: str, source: str) -> datetime | None:
    """Data do ``merge-base`` — piso do que conta como trabalho desta branch."""
    base = _run_git(['merge-base', target, source]).strip()
    return _parse_iso(_run_git(['log', '-1', '--format=%cI', base]).strip()) if base else None


def horas_ativas(eventos: list[tuple[datetime, bool]]) -> float:
    """Tempo ativo: soma dos intervalos entre eventos, cada um com um teto.

    O teto depende de **quem** produziu os eventos nas duas pontas, porque os dois
    silêncios não significam a mesma coisa. Só conta como trabalho o intervalo em que o
    agente falou antes E depois (``evento_do_agente``): aí ele estava rodando o intervalo
    inteiro, e uma suíte de testes de 20 min é trabalho de verdade (teto ``TOOL_MAX_S``,
    só para anomalia). Qualquer ponta humana significa espera — inclusive o caso
    ``user`` → ``assistant``, que é a sessão retomada horas depois de você digitar — e
    entra limitado a ``IDLE_MAX_S``.
    """
    total = 0.0
    for (inicio, antes_do_agente), (fim, depois_do_agente) in itertools.pairwise(eventos):
        do_agente = antes_do_agente and depois_do_agente
        total += min((fim - inicio).total_seconds(), TOOL_MAX_S if do_agente else IDLE_MAX_S)
    return total / 3600


def calcular_horas(payload: dict, target: str, source: str) -> tuple[float, str]:
    """Retorna ``(horas, descrição_da_fonte)`` — tempo ativo medido; sem ele, backfiring."""
    diretorio = dir_transcricoes(payload)
    # ponytail: conta todas as sessões do diretório posteriores ao merge-base. Um worktree
    # por tarefa (o fluxo daqui) torna isso ≈ "esta branch"; trabalhar em duas branches no
    # mesmo diretório mistura os tempos — aí só separando por sessionId.
    eventos = _eventos(diretorio, inicio_da_branch(target, source)) if diretorio else []
    horas = horas_ativas(eventos)
    if horas:
        return horas, f'tempo ativo medido ({len(eventos)} eventos, espera acima de {IDLE_MAX_S // 60} min descartada)'
    _log(f'sem transcrição utilizável em {diretorio or "(diretório não encontrado)"}; caindo no backfiring por LOC')
    loc = loc_adicionadas(target, source)
    return loc / BACKFIRING_LOC_POR_HORA, f'backfiring ({loc} LOC ÷ {BACKFIRING_LOC_POR_HORA})'


def formatar_horas(horas: float) -> tuple[str, int]:
    """Converte horas decimais em ``('Xh Ym', total_minutos)``."""
    total_min = round(horas * 60)
    h, m = divmod(total_min, 60)
    partes = []
    if h:
        partes.append(f'{h}h')
    if m or not h:
        partes.append(f'{m}m')
    return ' '.join(partes), total_min


def _token_do_glab(host: str) -> str:
    """Token guardado pelo ``glab`` CLI — fallback quando o remote é SSH e não há env.

    ``--host`` (e não ``-h``, que no ``glab`` é ``--help`` e devolve a tela de ajuda
    inteira). Só a primeira linha, por segurança: qualquer aviso extra no stdout iria
    para dentro do header HTTP e estouraria em ``latin-1``.
    """
    try:
        res = subprocess.run(['glab', 'config', 'get', 'token', '--host', host], capture_output=True, text=True, timeout=15, check=False)
    except OSError, subprocess.SubprocessError:
        return ''
    if res.returncode != 0:
        return ''
    primeira = res.stdout.strip().splitlines()[0].strip() if res.stdout.strip() else ''
    return primeira if primeira.isascii() and ' ' not in primeira else ''


def credenciais() -> tuple[str, str]:
    """``(host, token)`` a partir do env, do remote ``origin`` (HTTPS ou SSH) ou do ``glab``."""
    remote = _run_git(['remote', 'get-url', 'origin']).strip()
    https = re.search(r'https?://(?:[^:/@]+:)?([^@/]+)@([^/]+)/', remote)
    # Remote SSH (`git@host:grupo/projeto.git`) não carrega token, mas carrega o host.
    ssh = re.search(r'^(?:ssh://)?[^@/]+@([^:/]+)[:/]', remote)
    host = (https.group(2) if https else '') or os.environ.get('GITLAB_HOST', '') or (ssh.group(1) if ssh else '')
    token = os.environ.get('GITLAB_TOKEN') or (https.group(1) if https else '') or (_token_do_glab(host) if host else '')
    if not token:
        _log(f'sem credencial para {host or "host desconhecido"}: defina GITLAB_TOKEN ou autentique o glab')
    return host, token


def _desembrulhar_mcp(tr: object) -> dict:
    """Normaliza o ``tool_response`` da ferramenta MCP no dict plano com ``iid``.

    O formato varia por ferramenta:
      - Claude Code entrega os *content blocks* direto numa **lista**:
        ``[{'type': 'text', 'text': '<json>'}]``;
      - às vezes embrulhados em ``{'content': [...]}``;
      - o OpenCode entrega o objeto plano, e o payload pode vir como string JSON.

    Qualquer forma inesperada vira ``{}``: o chamador desiste por falta de ``iid``
    e loga, em vez de estourar. Era esse o bug — a lista chegava crua em
    ``.get('iid')`` e derrubava o hook com ``AttributeError``.
    """
    if isinstance(tr, str):
        tr = _try_json(tr)
    if isinstance(tr, dict) and isinstance(tr.get('content'), list):
        tr = tr['content']
    if isinstance(tr, list) and tr and isinstance(tr[0], dict):
        tr = _try_json(tr[0].get('text'))
    return tr if isinstance(tr, dict) else {}


def contexto_glab(payload: dict) -> tuple[str, str]:
    """``(iid, project_id)`` lidos da URL que ``glab mr create`` imprime. ``('', '')`` se não é isso.

    O hook também casa a ferramenta ``Bash``, e o matcher de ``settings.json`` só enxerga o
    nome da ferramenta — filtrar o comando aqui é o que impede toda chamada de shell de
    virar registro de tempo. Por isso a checagem vem ANTES de qualquer git ou rede.

    ``project_id`` sai como caminho percent-encoded (``cosinf%2Fsuap``), que a API aceita no
    lugar do ID numérico: assim o script não fixa o número do projeto nem precisa de uma
    chamada extra para descobri-lo. A saída é varrida em stdout **e** stderr porque o
    ``glab`` manda o progresso para stderr, e é lá que a URL costuma cair.
    """
    comando = (payload.get('tool_input') or {}).get('command') or ''
    if not re.search(r'\bglab\s+mr\s+(create|update)\b', comando):
        return '', ''
    tr = payload.get('tool_response')
    saida = ' '.join(str(tr.get(c) or '') for c in ('stdout', 'stderr')) if isinstance(tr, dict) else str(tr or '')
    achado = re.search(r'https?://[^\s/]+/(\S+?)/-/merge_requests/(\d+)', saida)
    if not achado:
        _log('comando glab mr reconhecido, mas nenhuma URL de MR na saída; nada a fazer')
        return '', ''
    return achado.group(2), quote(achado.group(1), safe='')


def _eh_atribuicao(parte: str) -> bool:
    """``NOME=valor`` de shell. ``--label=x`` não é: o nome precisa ser identificador."""
    nome, igual, _ = parte.partition('=')
    return bool(igual) and nome.isidentifier()


def pediu_registro_de_tempo(payload: dict) -> bool:
    """O comando pediu o registro com ``REGISTRAR_TEMPO=True`` antes do ``glab mr``?

    Registrar tempo é **opt-in**: sem o pedido, o hook não faz nada. O pedido viaja no
    texto do comando porque é só isso que o hook enxerga — ele roda num processo à parte,
    então um ``export`` no shell do agente não chega até ele.

    Vale apenas a atribuição em linha que PRECEDE ``glab mr create|update``. Texto dentro de
    um argumento não conta: o corpo de um MR pode muito bem citar o próprio parâmetro. A
    ferramenta MCP não tem texto de comando, então nela o registro fica sempre desligado.
    """
    comando = (payload.get('tool_input') or {}).get('command')
    if not isinstance(comando, str):
        return False
    try:
        partes = shlex.split(comando)
    except ValueError:
        return False
    atribuicoes = {}
    while partes and _eh_atribuicao(partes[0]):
        nome, _, valor = partes.pop(0).partition('=')
        atribuicoes[nome] = valor
    if not (len(partes) >= 3 and partes[:2] == ['glab', 'mr'] and partes[2] in ('create', 'update')):
        return False
    return atribuicoes.get(PARAMETRO_REGISTRO, '').lower() == 'true'


def motivo_sem_registro(payload: dict) -> str:
    """Por que o tempo não foi registrado, na forma que ajuda a corrigir.

    Distingue três casos que uma mensagem única confundia: a ferramenta MCP (sem ``glab``,
    não há onde pôr o pedido); o parâmetro escrito fora da posição aceita (depois de ``cd``,
    ``env`` ou ``export``) — quem fez isso acha que pediu; e o comando sem pedido nenhum.

    A posição aceita continua estrita de propósito: é ela que impede um MR cuja descrição
    cita o parâmetro de disparar o registro. Por isso "fora da posição" só se aplica quando
    o parâmetro aparece como atribuição de verdade (token ``NOME=valor`` isolado) em algum
    ponto do comando — citar o nome dentro de um argumento (ex.: na descrição do MR) não é
    tentativa de pedido, e não deve ser acusado como tal.
    """
    comando = (payload.get('tool_input') or {}).get('command')
    if not isinstance(comando, str):
        return f'pela ferramenta MCP o registro não é suportado; use {PARAMETRO_REGISTRO}=True glab mr create|update'
    try:
        partes = shlex.split(comando)
    except ValueError:
        partes = []
    fora_de_posicao = any(_eh_atribuicao(p) and p.partition('=')[0] == PARAMETRO_REGISTRO for p in partes)
    if fora_de_posicao:
        return (
            f'{PARAMETRO_REGISTRO} foi encontrado, mas fora da posição aceita: precisa vir colado ao glab '
            f'({PARAMETRO_REGISTRO}=True glab mr ...), sem cd/&&, env ou export antes'
        )
    return f'registro é opt-in (prefixe o glab com {PARAMETRO_REGISTRO}=True)'


def extrair_contexto(payload: dict) -> tuple[str, str, str, str]:
    """``(iid, project_id, source_branch, target_branch)`` do payload da ferramenta."""
    ti = payload.get('tool_input') or {}
    tr = _desembrulhar_mcp(payload.get('tool_response'))
    iid = str(tr.get('iid') or ti.get('iid') or '')
    project_id = str(tr.get('project_id') or ti.get('project_id') or '')
    if not (iid and project_id):
        iid, project_id = contexto_glab(payload)
    target = ti.get('target_branch') or 'master'
    if not (iid and project_id):
        # Sai antes do git: com matcher em ``Bash``, isto roda a cada comando de shell.
        return iid, project_id, '', target
    source = ti.get('source_branch') or _run_git(['branch', '--show-current']).strip()
    return iid, project_id, source, target


def montar_corpo(fonte: str, total_tempo: str, delta_tempo: str) -> str:
    return (
        f'{MARCADOR_NOTA}\n\n'
        f'- Fonte da medição: {fonte}\n'
        f'- Tempo de trabalho acumulado: **{total_tempo}**\n'
        f'- Incremento registrado agora: **{delta_tempo}**\n\n'
        f'/spend {delta_tempo}'
    )


def _api(url: str, token: str, data: bytes | None = None) -> bytes | None:
    """GET (ou POST, se ``data``) na API do GitLab. ``None`` em qualquer falha, com log.

    Tenta ``PRIVATE-TOKEN`` (PAT) e, se levar 401/403, repete com
    ``Authorization: Bearer`` — é o que o token OAuth do ``glab`` exige.
    """
    for auth in ({'PRIVATE-TOKEN': token}, {'Authorization': f'Bearer {token}'}):
        cabecalhos = {**auth, 'Content-Type': 'application/json'} if data else dict(auth)
        req = urllib.request.Request(url, data=data, method='POST' if data else 'GET', headers=cabecalhos)  # noqa: S310 (host vem do remote git do projeto)
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:  # noqa: S310
                return resp.read()
        except urllib.error.HTTPError as exc:
            if exc.code not in (401, 403):
                _log(f'HTTP {exc.code} em {url}')
                return None
        except (urllib.error.URLError, OSError) as exc:
            _log(f'falha de rede em {url}: {exc}')
            return None
    _log(f'autenticação recusada em {url} (tentado PRIVATE-TOKEN e Bearer)')
    return None


def minutos_ja_registrados(host: str, token: str, project_id: str, iid: str) -> int | None:
    """Minutos já lançados no MR, lidos do ``time_stats`` do GitLab. ``None`` se não deu.

    NÃO dá para somar as notas deste hook: ao executar o quick action, o GitLab **remove**
    a linha ``/spend ...`` do corpo persistido, então a nota não guarda mais o valor. Era
    por isso que o delta lia sempre 0 e cada update do MR relançava o total inteiro.

    Como a fonte agora é o total do MR, tempo lançado à mão por uma pessoa também conta —
    o que é o comportamento desejável: o hook completa até a estimativa, nunca soma em
    cima. ``None`` (falha de leitura) faz o chamador desistir, em vez de arriscar
    double-count.
    """
    corpo = _api(f'https://{host}/api/v4/projects/{project_id}/merge_requests/{iid}', token)
    if corpo is None:
        return None
    try:
        dados = json.loads(corpo)
    except ValueError:
        _log('resposta não-JSON ao ler time_stats do MR')
        return None
    return round((dados.get('time_stats') or {}).get('total_time_spent', 0) / 60)


def registrar_nota(host: str, token: str, project_id: str, iid: str, corpo: str, dry_run: bool) -> None:
    url = f'https://{host}/api/v4/projects/{project_id}/merge_requests/{iid}/notes'
    if dry_run:
        print(f'[dry-run] POST {url}\n{corpo}')
        return
    if _api(url, token, data=json.dumps({'body': corpo}).encode()) is None:
        _log('nota de tempo NÃO registrada (ver erro acima)')


def relatar_horas(target: str) -> None:
    """``--horas [base]``: só mostra o tempo ativo medido da branch atual (não toca no MR).

    A base entra porque o ``merge-base`` é o piso do que conta; usar ``master`` numa branch
    tirada de outra faria este número divergir do que o hook registra no MR.
    """
    source = _run_git(['branch', '--show-current']).strip()
    horas, fonte = calcular_horas({}, target, source)
    print(f'{formatar_horas(horas)[0]} — {fonte}')


def main(dry_run: bool, sob_pedido: bool = False) -> None:
    """Registra o tempo do MR descrito no payload.

    ``sob_pedido`` liga o portão opt-in (``REGISTRAR_TEMPO=True``). Só o Claude Code o liga,
    passando ``--sob-pedido`` em ``.claude/settings.json``; o Codex e o OpenCode chamam este
    script sem argumentos e seguem registrando sempre.
    """
    payload = _try_json(sys.stdin.read())
    iid, project_id, source, target = extrair_contexto(payload)
    if not (iid and project_id and source):
        # Bash que não é ``glab mr`` não é assunto deste hook: logar aqui encheria o
        # transcript de ruído a cada comando de shell. O caso ruim — ``glab mr`` sem URL
        # na saída — já deixa rastro em ``contexto_glab``.
        if 'command' not in (payload.get('tool_input') or {}):
            _log(f'contexto incompleto no payload (iid={iid!r}, project_id={project_id!r}, branch={source!r}); nada a fazer')
        return
    # Opt-in (só com --sob-pedido). Vem antes das credenciais e da medição de propósito:
    # sem o pedido, nenhuma rede é tocada e nenhuma transcrição é varrida.
    if sob_pedido and not pediu_registro_de_tempo(payload):
        _log(f'tempo não registrado no MR !{iid}: {motivo_sem_registro(payload)}')
        return
    host, token = credenciais()
    if not (host and token):
        return
    horas, fonte = calcular_horas(payload, target, source)
    total_tempo, total_min = formatar_horas(horas)
    # Delta: só o incremento até a estimativa atual; evita double-count em updates do MR.
    ja_min = 0 if dry_run else minutos_ja_registrados(host, token, project_id, iid)
    if ja_min is None:
        _log('não foi possível ler o tempo já registrado; nada lançado (evita double-count)')
        return
    delta_tempo, delta_min = formatar_horas((total_min - ja_min) / 60)
    if delta_min < 1:
        _log(f'nada a lançar: {total_tempo} já coberto pelos {ja_min} min registrados')
        return
    registrar_nota(host, token, project_id, iid, montar_corpo(fonte, total_tempo, delta_tempo), dry_run)


if __name__ == '__main__':
    try:
        argumentos = sys.argv[1:]
        if '--horas' in argumentos:
            base = [a for a in argumentos if not a.startswith('-')]
            relatar_horas(base[0] if base else 'master')
        else:
            main('--dry-run' in argumentos, sob_pedido=FLAG_SOB_PEDIDO in argumentos)
    except Exception as exc:
        # Nunca bloqueia o MR — mas deixa rastro, senão a falha some.
        _log(f'erro inesperado: {type(exc).__name__}: {exc}')
    sys.exit(0)
