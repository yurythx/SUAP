// Time-spent plugin for SUAP (OpenCode)
//
// Adaptador do nucleo compartilhado (.agents/hooks/register_mr_time_spent.py,
// o mesmo do .claude/settings.json): apos a criacao OU atualizacao de um MR — pela
// ferramenta GitLab OU pelo CLI `glab` rodando no shell — registra o tempo de
// trabalho via /spend numa nota do MR (no update, so o delta vs. o que ja foi
// lancado).
// Reaproveita o MESMO script Python para manter uma unica fonte de verdade entre
// Claude Code e OpenCode.
//
// Dois caminhos de entrada, iguais aos do Claude Code:
//   - tool MCP do GitLab: o iid/project_id vem no resultado da ferramenta;
//   - `glab mr create|update` no shell: so existe a URL do MR impressa pelo comando,
//     de onde o lado Python (contexto_glab) extrai iid e project_id.
// O filtro do comando aparece DUAS vezes de proposito (aqui e no Python): aqui ele
// evita gastar um processo Python a cada chamada de shell; no Python ele e a defesa
// real, porque o matcher do Claude Code so sabe casar nome de ferramenta.
//
// ATENCAO: o script mede o tempo ativo pelas transcricoes do agente, que o OpenCode
// nao expoe — aqui ele sempre cai no backfiring por LOC (~50 LOC/hora). Para ter a
// medicao real, passe tambem `transcript_path` (ou `cwd`) no payload abaixo, apontando
// para transcricoes no formato JSONL com `timestamp` e `type` por evento.
//
// Roda depois da ferramenta porque o MR (e seu iid) so existe apos a chamada.
// E fire-and-forget: nunca lanca erro nem bloqueia. Falhas do script sao silenciosas
// (ele sempre sai com exit 0).
//
// Formato duplo: `setup` e a API do OpenCode 2.x; `server` e a do 1.x (a imagem do
// CI, bin/ci/Dockerfile.opencode). Cada loader le so a chave dele e ignora a outra.

import { spawnSync } from "node:child_process"
import { join } from "node:path"

// Monta o mesmo payload JSON que o hook do Claude Code recebe via stdin:
// { tool_input: <args da ferramenta>, tool_response: <resultado com iid> }.
function registrar(directory: string, toolInput: unknown, toolResponse: unknown): void {
  const script = join(directory, ".agents/hooks/register_mr_time_spent.py")
  spawnSync(script, {
    input: JSON.stringify({ tool_input: toolInput, tool_response: toolResponse }),
    cwd: directory,
    env: { ...process.env, CLAUDE_PROJECT_DIR: directory },
    encoding: "utf8",
  })
}

// Criacao E atualizacao de merge request pela tool MCP (gitlab_create_merge_request /
// gitlab_update_merge_request; o regex tolera prefixos do servidor MCP). No update,
// o script registra so o delta.
function ehMr(tool: unknown): boolean {
  return typeof tool === "string" && /(create|update)_merge_request/.test(tool)
}

// Mesmo filtro do lado Python. Precisa ser o comando do `glab` de verdade: a URL de
// um MR aparece na saida de um `git push` tambem, e registrar tempo a partir dela
// lancaria /spend num MR alheio.
function ehGlabMr(command: unknown): boolean {
  return typeof command === "string" && /\bglab\s+mr\s+(create|update)\b/.test(command)
}

function textos(partes: unknown[]): string {
  return partes.filter((p) => typeof p === "string").join("\n")
}

// Texto dos blocos de conteudo de um resultado v2 (`string` ou `[{type, text}]`).
function textoDoConteudo(content: unknown): string {
  if (typeof content === "string") return content
  return Array.isArray(content) ? textos(content.map((c: any) => c?.text)) : ""
}

export default {
  id: "suap.register-mr-time-spent",

  // OpenCode 2.x: o shell chama `shell`; o resultado vem em `event.result`
  // ({ output, content }). Na tool MCP, `content` sao os blocos crus, o mesmo formato
  // que o Claude Code entrega e que o lado Python desembrulha.
  setup: async (ctx: any) => {
    const directory: string = ctx.location.directory
    await ctx.tool.hook("execute.after", (event: any) => {
      try {
        if (event.status !== "completed") return
        const result = event.result ?? {}
        if (event.tool === "shell") {
          if (!ehGlabMr(event.input?.command)) return
          registrar(directory, event.input, textos([result.output?.output, textoDoConteudo(result.content)]))
        } else if (ehMr(event.tool)) {
          registrar(directory, event.input ?? {}, result.content ?? result.output ?? {})
        }
      } catch {}
    })
  },

  // OpenCode 1.x
  server: async ({ directory }: { directory: string }) => ({
    "tool.execute.after": async (input: any, output: any) => {
      const toolName: string = input?.tool ?? ""
      const ehBash = /(^|[_.])bash$/.test(toolName)
      if (!ehMr(toolName) && !ehBash) return
      const toolInput = output?.args ?? input?.args ?? {}
      if (ehBash && !ehGlabMr(toolInput?.command)) return
      // No bash o resultado e texto solto: entrega a saida crua, que o lado Python
      // aceita tanto como dict {stdout, stderr} quanto como string.
      registrar(directory, toolInput, ehBash ? saidaBash(output) : parseResponse(output))
    },
  }),
}

// A saida do bash no OpenCode 1.x ora vem em `output`, ora em `metadata.stdout/stderr`.
// Junta tudo: o `glab` manda o progresso para stderr, e e la que a URL costuma cair.
function saidaBash(output: any): string {
  const meta = output?.metadata ?? {}
  return textos([output?.output, meta.stdout, meta.stderr, output])
}

// O resultado de uma tool MCP no OpenCode 1.x pode vir como objeto ou string JSON em
// campos distintos. Normaliza para o objeto com { iid, project_id }.
function parseResponse(output: any): any {
  const raw = output?.metadata ?? output?.result ?? output?.output ?? output
  if (typeof raw === "string") {
    try {
      return JSON.parse(raw)
    } catch {
      return {}
    }
  }
  return raw ?? {}
}
