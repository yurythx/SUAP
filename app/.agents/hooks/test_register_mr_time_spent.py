#!/usr/bin/env -S uv run --quiet python3
"""Checagem de ``horas_ativas`` — a única lógica não trivial do hook de time spent.

Fica em ``.claude/`` (diretório oculto), então o pytest do projeto não coleta.
Rode direto:  ``.agents/hooks/test_register_mr_time_spent.py``
"""

from __future__ import annotations

import importlib.util
import io
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

_spec = importlib.util.spec_from_file_location('hook', Path(__file__).with_name('register_mr_time_spent.py'))
hook = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(hook)


HUMANO = {'type': 'user'}
FERRAMENTA = {'type': 'user', 'toolUseResult': {'stdout': 'ok'}}
DIGITANDO = {'type': 'queue-operation', 'operation': 'enqueue', 'content': 'roda os testes'}
AVISO_TAREFA = {'type': 'queue-operation', 'operation': 'enqueue', 'content': '<task-notification>\n<task-id>x</task-id>'}
# Formato real (transcrição do Claude Code), com id/rótulo inventados.
EXPIRA_MONITOR = {
    'type': 'queue-operation',
    'operation': 'enqueue',
    'content': '<task-notification>\n<task-id>abc123</task-id>\n<summary>Monitor event: "espera do merge"</summary>\n'
    '<event>[Monitor expired after 30m with 0 events delivered. Re-arm it if you still need the watch.]</event>\n</task-notification>',
}
EVENTO_MONITOR = {
    'type': 'queue-operation',
    'operation': 'enqueue',
    'content': '<task-notification>\n<task-id>abc123</task-id>\n<summary>Monitor event: "espera do merge"</summary>\n'
    '<event>MR !1 merged</event>\n</task-notification>',
}


def _serie(*intervalos: tuple[float, dict | str]) -> list[tuple[datetime, bool]]:
    """Eventos separados por ``(minutos, registro_de_quem_fala_em_seguida)``.

    Aceita o registro cru (dict) ou só o ``type`` (str), e classifica pelo mesmo
    ``evento_do_agente`` que o hook usa — assim o teste cobre a classificação de graça.
    """
    agora = datetime(2026, 8, 3, 12, 0)
    eventos = [(agora, hook.evento_do_agente(HUMANO))]
    for minutos, registro in intervalos:
        agora += timedelta(minutes=minutos)
        eventos.append((agora, hook.evento_do_agente({'type': registro} if isinstance(registro, str) else registro)))
    return eventos


def _classificacao() -> None:
    """Quem é 'o agente'. Cada engano aqui subestima o tempo — nunca o contrário."""
    assert hook.evento_do_agente({'type': 'assistant'}) is True
    assert hook.evento_do_agente({'type': 'system'}) is True
    assert hook.evento_do_agente(HUMANO) is False, 'sua mensagem não é trabalho do agente'
    assert hook.evento_do_agente(FERRAMENTA) is True, 'resultado de ferramenta chega como user e É trabalho'
    assert hook.evento_do_agente(DIGITANDO) is False, 'digitar não é o agente'
    assert hook.evento_do_agente(AVISO_TAREFA) is True, 'aviso de tarefa fecha espera por pipeline/subagente'
    assert hook.evento_do_agente({'type': 'attachment'}) is False
    assert hook.evento_do_agente(EXPIRA_MONITOR) is False, 'expiração do Monitor só diz que a espera acabou'
    assert hook.evento_do_agente(EVENTO_MONITOR) is True, 'evento de Monitor com conteúdo acorda o agente'


def _contexto_glab() -> None:
    """Com matcher em ``Bash``, o filtro do comando é a única coisa entre o hook e todo
    comando de shell do repo virar registro de tempo. Um falso positivo aqui lança
    ``/spend`` num MR errado."""
    url = 'https://gitlab.ifrn.edu.br/cosinf/suap/-/merge_requests/18711'
    criar = {'tool_input': {'command': 'glab mr create --draft --target-branch master'}}

    assert hook.contexto_glab({**criar, 'tool_response': {'stdout': f'!18711 titulo\n{url}\n'}}) == ('18711', 'cosinf%2Fsuap')
    # glab manda o progresso para stderr — é lá que a URL costuma cair.
    assert hook.contexto_glab({**criar, 'tool_response': {'stdout': '', 'stderr': url}}) == ('18711', 'cosinf%2Fsuap')
    assert hook.contexto_glab({'tool_input': {'command': 'glab mr update 18711'}, 'tool_response': {'stdout': url}})[0] == '18711'
    # Grupo aninhado: o project_id é o caminho inteiro percent-encoded, não só o último nome.
    aninhado = 'https://gitlab.ifrn.edu.br/a/b/c/-/merge_requests/7'
    assert hook.contexto_glab({**criar, 'tool_response': {'stdout': aninhado}}) == ('7', 'a%2Fb%2Fc')

    vazio = ('', '')
    assert hook.contexto_glab({**criar, 'tool_response': {'stdout': 'erro: branch já tem MR'}}) == vazio, 'sem URL, nada a registrar'
    assert hook.contexto_glab({'tool_input': {'command': 'git push -u origin x'}, 'tool_response': {'stdout': url}}) == vazio, (
        'a URL pode aparecer na saída do push — só o comando glab autoriza registrar'
    )
    assert hook.contexto_glab({'tool_input': {'command': f'echo {url}'}, 'tool_response': {'stdout': url}}) == vazio
    assert hook.contexto_glab({'tool_input': {'command': 'glab mr list'}, 'tool_response': {'stdout': url}}) == vazio
    assert hook.contexto_glab({}) == vazio
    # Payload da ferramenta MCP não passa por aqui (não tem ``command``) e não pode estourar.
    assert hook.contexto_glab({'tool_input': {'iid': '1', 'project_id': '8'}}) == vazio

    # E o caminho completo: extrair_contexto tem de preferir o MCP e cair no glab só sem ele.
    assert hook.extrair_contexto({'tool_input': {'iid': '1', 'project_id': '8'}})[:2] == ('1', '8')
    assert hook.extrair_contexto({**criar, 'tool_response': {'stdout': url}})[:2] == ('18711', 'cosinf%2Fsuap')
    assert hook.extrair_contexto({'tool_input': {'command': 'ls'}, 'tool_response': {'stdout': ''}}) == ('', '', '', 'master')


def _payload_codex() -> None:
    """O PostToolUse do Codex entrega os mesmos campos, inclusive resposta JSON string."""
    objeto = {
        'cwd': '/workspace/suap',
        'transcript_path': '/workspace/.codex/rollout.jsonl',
        'tool_input': {'project_id': '8', 'target_branch': 'master'},
        'tool_response': {'iid': 42, 'project_id': 8},
    }
    assert hook.extrair_contexto(objeto)[:2] == ('42', '8')
    como_string = {**objeto, 'tool_response': '{"iid": 43, "project_id": 8}'}
    assert hook.extrair_contexto(como_string)[:2] == ('43', '8')


def _pedido_de_registro() -> None:
    """Registrar tempo é opt-in: só com ``REGISTRAR_TEMPO=True`` prefixado ao ``glab``.

    O hook roda num processo à parte e só enxerga o TEXTO do comando — um ``export`` no
    shell do agente não chega até ele. Por isso o pedido viaja como atribuição em linha.
    """

    def comando(texto: str) -> dict:
        return {'tool_input': {'command': texto}}

    assert hook.pediu_registro_de_tempo(comando('REGISTRAR_TEMPO=True glab mr create --yes')) is True
    assert hook.pediu_registro_de_tempo(comando('REGISTRAR_TEMPO=true glab mr update 18963')) is True, 'sem diferenciar caixa'
    assert hook.pediu_registro_de_tempo(comando('OUTRA=1 REGISTRAR_TEMPO=True glab mr create')) is True, 'entre outras atribuições'

    assert hook.pediu_registro_de_tempo(comando('glab mr create --yes')) is False, 'o padrão é NÃO registrar'
    assert hook.pediu_registro_de_tempo(comando('REGISTRAR_TEMPO=False glab mr create')) is False
    assert hook.pediu_registro_de_tempo(comando('REGISTRAR_TEMPO= glab mr create')) is False
    # O corpo de um MR pode citar o próprio parâmetro — o deste MR cita. Texto dentro de
    # um argumento não é pedido de registro: só a atribuição ANTES do glab conta.
    assert hook.pediu_registro_de_tempo(comando('glab mr create --description "use REGISTRAR_TEMPO=True"')) is False
    assert hook.pediu_registro_de_tempo(comando('echo REGISTRAR_TEMPO=True && glab mr create')) is False
    # Ferramenta MCP não tem texto de comando: não há como pedir, então fica desligado.
    assert hook.pediu_registro_de_tempo({'tool_input': {'iid': '1', 'project_id': '8'}}) is False
    assert hook.pediu_registro_de_tempo({}) is False
    # Aspas desbalanceadas não podem derrubar o hook — que nunca bloqueia o MR.
    assert hook.pediu_registro_de_tempo(comando('REGISTRAR_TEMPO=True glab mr create --title "sem fechar')) is False


def _motivo_sem_registro() -> None:
    """A mensagem de "não registrado" tem de corresponder ao caso.

    Uma mensagem única — "prefixe o glab com REGISTRAR_TEMPO=True" — dizia isso até a quem
    JÁ tinha escrito o parâmetro (só que depois de ``cd``, ``env`` ou ``export``), e até a
    quem usou a ferramenta MCP, que nem passa pelo ``glab``.
    """

    def motivo(texto: str | None) -> str:
        return hook.motivo_sem_registro({'tool_input': {} if texto is None else {'command': texto}})

    assert 'MCP' in motivo(None)
    for fora_de_posicao in ('env REGISTRAR_TEMPO=True glab mr create', 'cd /x && REGISTRAR_TEMPO=True glab mr create'):
        assert 'fora da posição' in motivo(fora_de_posicao), fora_de_posicao
    assert 'opt-in' in motivo('glab mr create --yes')
    # Citar o parâmetro num argumento (ex.: na descrição do MR) não é "posição errada" — é
    # só texto. Confundir os dois acusaria de erro quem não tentou nada.
    citado = motivo('glab mr create --description "use REGISTRAR_TEMPO=True"')
    assert 'opt-in' in citado, citado
    assert 'fora da posição' not in citado, citado


def _portao_no_main() -> None:
    """O portão só existe com ``--sob-pedido``, e aí barra ANTES das credenciais.

    O opt-in é só do Claude Code: é o ``.claude/settings.json`` que passa a flag. O Codex e
    o OpenCode chamam este mesmo script sem argumentos e têm de continuar registrando
    sempre, como antes — daí o primeiro caso.

    Checado pelo efeito observável — se ``credenciais`` foi chamada — e não pelo retorno,
    que é ``None`` em todos os caminhos.

    ``source_branch`` vai no payload para o teste não depender do git: sem ele,
    ``extrair_contexto`` lê ``git branch --show-current``, que sai vazio com HEAD destacado
    (o caso do CI). O ``main`` desistia antes do portão e o caso prefixado falhava.
    """
    url = 'https://gitlab.ifrn.edu.br/cosinf/suap/-/merge_requests/18711'
    chamadas: list[bool] = []
    original = hook.credenciais
    hook.credenciais = lambda: (chamadas.append(True), ('', ''))[1]
    casos = (
        (False, 'glab mr create --yes', [True]),  # Codex/OpenCode: sem flag, registra como antes
        (True, 'glab mr create --yes', []),  # Claude Code sem pedido: não registra
        (True, 'REGISTRAR_TEMPO=True glab mr create --yes', [True]),  # Claude Code com pedido
    )
    try:
        for sob_pedido, comando, esperado in casos:
            chamadas.clear()
            payload = {'tool_input': {'command': comando, 'source_branch': 'qualquer'}, 'tool_response': {'stdout': url}}
            sys.stdin = io.StringIO(json.dumps(payload))
            hook.main(dry_run=True, sob_pedido=sob_pedido)
            assert chamadas == esperado, f'sob_pedido={sob_pedido} {comando!r}: credenciais {chamadas}, esperado {esperado}'
    finally:
        hook.credenciais = original
        sys.stdin = sys.__stdin__


def _somente_claude_pede() -> None:
    """O isolamento é contrato: só a configuração do Claude Code liga o portão.

    Se a flag vazasse para o adaptador do Codex ou para o plugin do OpenCode, eles passariam
    a exigir o prefixo em silêncio e deixariam de registrar tempo.
    """
    raiz = Path(__file__).resolve().parents[2]
    configuracao = json.loads((raiz / '.claude/settings.json').read_text())
    comandos = [h['command'] for grupo in configuracao['hooks']['PostToolUse'] for h in grupo['hooks']]
    registro = [c for c in comandos if 'register_mr_time_spent.py' in c]
    assert registro, 'o hook de tempo sumiu do .claude/settings.json'
    assert all(hook.FLAG_SOB_PEDIDO in c for c in registro), registro
    for outro in ('.codex/hooks/register_mr_time_spent.py', '.opencode/plugin/register-mr-time-spent.ts'):
        assert hook.FLAG_SOB_PEDIDO not in (raiz / outro).read_text(), f'{outro} não pode ligar o portão'


def main() -> None:
    _classificacao()
    _contexto_glab()
    _payload_codex()
    _pedido_de_registro()
    _motivo_sem_registro()
    _portao_no_main()
    _somente_claude_pede()
    assert hook.horas_ativas([]) == 0
    assert hook.horas_ativas(_serie()) == 0, 'um evento só não é tempo trabalhado'
    # Agente nas duas pontas: ferramenta longa conta inteira (o 1º intervalo abre em 'user').
    assert hook.horas_ativas(_serie((1, 'assistant'), (30, 'system'), (30, 'assistant'))) == 1 / 60 + 1.0
    # Espera pela pessoa: a pausa de 3 h entra limitada a IDLE_MAX_S, não inteira.
    assert hook.horas_ativas(_serie((180, HUMANO))) == hook.IDLE_MAX_S / 3600
    assert hook.horas_ativas(_serie((180, DIGITANDO))) == hook.IDLE_MAX_S / 3600, 'digitar não é o agente'
    # Sessão retomada: você digitou e o agente só respondeu horas depois — isso é espera.
    assert hook.horas_ativas(_serie((180, 'assistant'))) == hook.IDLE_MAX_S / 3600
    # Anomalia com o agente nas duas pontas fica no teto de ferramenta.
    assert hook.horas_ativas(_serie((1, 'assistant'), (600, 'assistant'))) == 1 / 60 + hook.TOOL_MAX_S / 3600
    assert hook.horas_ativas(_serie((1, 'assistant'), (2, 'system'), (180, HUMANO))) == 3 / 60 + hook.IDLE_MAX_S / 3600
    # As três regressões que zeravam o relógio do agente:
    # 1. suíte de 20 min — o resultado chega como 'user' e o intervalo é trabalho inteiro.
    assert hook.horas_ativas(_serie((1, 'assistant'), (20, FERRAMENTA))) == 21 / 60
    # 2. espera por pipeline/subagente — fecha em 'queue-operation' e conta inteira.
    assert hook.horas_ativas(_serie((1, 'assistant'), (45, AVISO_TAREFA))) == 46 / 60
    # 3. mas o aviso de tarefa não converte a pausa ANTERIOR humana em trabalho.
    assert hook.horas_ativas(_serie((180, HUMANO), (45, AVISO_TAREFA))) == hook.IDLE_MAX_S / 3600 + hook.IDLE_MAX_S / 3600
    # 4. rearmes ociosos do Monitor: cada ciclo [expiração → resposta curta] custa 5 min (espera
    # limitada) + 1 min (resposta), não 30 min + 1. 1 min inicial + 3 ciclos de 6 min = 19 min.
    ocioso = hook.horas_ativas(_serie((1, 'assistant'), *[(30, EXPIRA_MONITOR), (1, 'assistant')] * 3))
    assert round(ocioso * 60) == 19, ocioso * 60
    # Controle: agente em segundo plano que termina após 20 min continua sendo trabalho.
    concluido = {**AVISO_TAREFA, 'content': AVISO_TAREFA['content'] + '\n<summary>Agent "x" completed</summary>'}
    assert hook.horas_ativas(_serie((1, 'assistant'), (20, concluido))) == 21 / 60
    assert hook.formatar_horas(1.5) == ('1h 30m', 90)
    assert hook.formatar_horas(0) == ('0m', 0)
    print('ok')


if __name__ == '__main__':
    main()
