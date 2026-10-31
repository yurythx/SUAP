---
name: carga-horaria
description: >
  Mostra a carga horária (esforço) da tarefa atual pelo tempo de trabalho ativo medido
  nas transcrições do agente — o mesmo número que o hook de time spent registra no MR.
  Trigger: /carga-horaria, "calcula o esforço", "quanto tempo levou".
trigger: /carga-horaria
---

Mostra o esforço da branch atual em **horas de trabalho efetivamente gastas**, medidas —
não estimadas.

## Como medir

```bash
.agents/hooks/register_mr_time_spent.py --horas master
```

O argumento é a branch base (o `merge-base` com ela é o piso do que conta). Passe a mesma
base que o MR usa — omitir assume `master`. Imprime, por exemplo, `1h 20m — tempo ativo
medido (412 eventos, espera acima de 5 min descartada)`. Apresente esse número ao usuário
e, se ele pedir detalhe, explique a regra abaixo. **Não registre nada no MR** — isso é
função do hook, que roda sozinho ao criar ou atualizar o MR e usa exatamente esta mesma
medição.

## A regra da medição

O tempo sai dos carimbos de tempo das transcrições compatíveis do agente
(`~/.claude/projects/<slug-do-cwd>/**/*.jsonl` ou `transcript_path` no payload), somando os intervalos entre eventos
consecutivos posteriores ao `merge-base` da branch. O teto de cada intervalo depende de
quem produziu os eventos nas **duas** pontas:

| Pontas do intervalo | Significado | Teto |
| --- | --- | --- |
| agente (`assistant`/`system`) dos dois lados | ele estava rodando o intervalo inteiro | 1 h (só anomalia) |
| qualquer ponta humana (`user`, `queue-operation`, …) | espera pela pessoa | 5 min |

É por isso que uma suíte de testes de 20 min vira trabalho, e sessão retomada no dia
seguinte não vira — inclusive quando quem responde depois da pausa é o agente
(`user` → `assistant`), que é exatamente a cara de uma retomada.

## Limites
- **Não** registra time spent no MR diretamente — quem registra é o hook
  `register_mr_time_spent.py` (Claude Code via `.claude/settings.json`; OpenCode via
  `.opencode/plugin/register-mr-time-spent.ts`; Codex via
  `.codex/hooks/register_mr_time_spent.py`).
- Conta **todas as sessões do diretório de trabalho** posteriores ao `merge-base`. Um
  worktree por tarefa (o fluxo daqui) faz isso equivaler a "esta branch"; duas branches no
  mesmo diretório misturam os tempos.
- Sem transcrição compatível, o hook cai no *backfiring* por LOC (≈50 LOC/hora).
  O Codex encaminha `transcript_path` quando disponível, mas o formato da transcrição não
  é uma API estável; o diagnóstico impresso informa quando o fallback foi usado.
