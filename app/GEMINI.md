@AGENTS.md
@.agents/rules/suap.md

# Gemini CLI / Antigravity

A orientação do projeto (comandos, arquitetura, convenções, testes com `pytest`) vive em
`AGENTS.md`, e os guardrails operacionais vivem em `.agents/rules/suap.md` (diretório nativo de rules do Antigravity), importados acima para o Gemini CLI.
Este arquivo guarda notas e configurações específicas para o Gemini CLI e Antigravity.

## Roteamento de Modelos por Risco

Aplica o critério de `## Roteamento de modelos por risco` (`AGENTS.md` — *"um erro passaria despercebido?"*) aos modelos Gemini disponíveis no Antigravity (**conta Google AI Pro**) e aos tiers de despacho de subagentes (`invoke_subagent`):

| Risco | Exemplos de Tarefas / Subagentes | Modelo Gemini (UI / CLI) | Subagente (`invoke_subagent`) |
|---|---|---|---|
| Baixo | Busca/exploração (`research`), fan-out somente leitura, leituras de código, triagem inicial, ajustes triviais de formatação/texto | `Gemini 3.8 Flash` (`Low` / `Medium`) | `flash_lite` ou `flash` |
| Médio | Execução de plano já aprovado, escrita/ajuste de testes com factories, correções pontuais validadas por testes, `suap-frontend` (classes validadas por grep), `documentador` (revisado no MR) | `Gemini 3.8 Flash` (`High`) ou `Gemini 4 Argon` (`Medium`) | `flash` ou `inherit` |
| Alto | Diagnóstico e planejamento arquitetural (`/plan`), auth, permissões, migrations, dados de produção, segurança, semântica de queries ORM/SQL, revisão de código (`code-review`, `security-reviewer`, `migration-reviewer`, `query-perf-reviewer`), `e2e-tester` (`--rotas` é cego a `/admin/`), `documentador-usuario` | `Gemini 4 Argon` (`High` / `Medium`) | `pro` (ou `inherit` em sessão Argon) |

- **Disponibilidade na conta Google AI Pro (paga)**: os modelos Gemini ativos no seletor são **Gemini 3.8 Flash** (workhorse rápido) e **Gemini 4 Argon** (raciocínio avançado de fronteira, disponível no app Antigravity, CLI e extensões IDE). Versões anteriores (`3.7 Flash`, `3.6 Flash`, `3.1 Pro`) são restritas ao plano Enterprise.
- **Nível de raciocínio (*Thinking level* / `/effort`)**: ambos suportam `Low`, `Medium` e `High`. Ajuste o nível de raciocínio (`High` → `Medium`) como alavanca menor de latência/cota antes de rebaixar o modelo em tarefas de maior risco.
- **Planejamento vs. Execução**: tarefas que combinam investigação/planejamento de risco alto (`/plan`) com posterior codificação mecânica beneficiam-se de `Gemini 4 Argon` na fase de diagnóstico/plano e `Gemini 3.8 Flash (High)` na fase de implementação guiada pelo plano aprovado.
- **Subagentes**: na ferramenta `invoke_subagent`, o argumento `Model` aceita `inherit`, `flash_lite`, `flash` ou `pro`. Não fixe `model:` no frontmatter de `.agents/agents/*.md`: o arquivo é compartilhado com os outros harnesses.
- **Relato obrigatório ao concluir cada resposta/tarefa**: informe sempre o modelo (e nível de raciocínio) utilizado e avalie se, para a atividade executada, ele era o mais adequado ou se outro modelo/nível seria mais indicado pela tabela acima.

## Testes, subagentes e hooks

- Testes: siga `## Testes` de `AGENTS.md` (importado acima); não há regra de teste própria do Gemini/Antigravity.
- Subagentes: o Antigravity lê `.agents/agents/*.md` nativamente — é o corpo canônico compartilhado com os outros harnesses (catálogo em `## Subagents` do `AGENTS.md`). Não crie cópia nem acrescente ali frontmatter de modelo: o frontmatter é neutro (`name`, `description`) e o modelo vai no argumento `Model` do `invoke_subagent`, pela tabela acima.
- Hooks: o único hook do projeto no Antigravity é o `Stop` de `.agents/hooks.json`, que roda o C901 (regra estrita: ≤ 10 em toda função tocada) ao encerrar a tarefa e devolve o agente ao loop se algo passar de 10. Para checar antes, rode `.agents/hooks/check_complexity.py` (sem argumentos ou com os arquivos) e trate exit 1 como "não checou", não como aprovação; modos e diferença para `bin/scripts/complexidade-nova.py` estão em `AGENTS.md`. O Antigravity não tem gate de commit: rode antes `uv run ruff format . && uv run ruff check . --fix --unsafe-fixes && git add -u && uv run pre-commit run --from-ref origin/master --to-ref HEAD` (definido em `.agents/hooks/commit_gate.py`).
- Esforço: `uv run .agents/hooks/register_mr_time_spent.py --horas` (ver skill `carga-horaria`).
