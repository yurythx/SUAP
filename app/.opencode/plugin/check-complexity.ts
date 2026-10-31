// Cyclomatic complexity enforcement plugin for SUAP (OpenCode)
//
// Adaptador do nucleo compartilhado (.agents/hooks/check_complexity.py): apos editar
// um arquivo .py, reprova as funcoes TOCADAS com complexidade ciclomatica > 10
// (ruff C901, max-complexity 10). Funcoes legadas intocadas no mesmo arquivo sao
// ignoradas. Reaproveita o MESMO script Python para manter uma unica fonte de
// verdade entre Claude Code e OpenCode.
//
// Roda depois da ferramenta porque o arquivo precisa ja estar escrito no disco
// para o `git diff` (vs HEAD) e o `ruff` enxergarem a mudanca.
//
// Formato duplo: `setup` e a API do OpenCode 2.x; `server` e a do 1.x (a imagem do
// CI, bin/ci/Dockerfile.opencode). Cada loader le so a chave dele e ignora a outra.
// No 1.x o `throw` devolve o erro ao modelo (equivalente ao exit 2 do Claude Code).
// No 2.x so o `execute.before` pode falhar e um throw vira defeito que derruba o
// turno, entao o relatorio do ruff e anexado ao resultado da ferramenta.

import { spawnSync } from "node:child_process"
import { join } from "node:path"

// Roda o hook Python com o mesmo JSON que o Claude Code manda via stdin. Devolve a
// mensagem de bloqueio (exit 2) ou undefined se nada passou de 10.
function violacoes(directory: string, toolInput: object): string | undefined {
  const script = join(directory, ".agents/hooks/check_complexity.py")
  const res = spawnSync(script, {
    input: JSON.stringify({ tool_input: toolInput }),
    cwd: directory,
    env: { ...process.env, CLAUDE_PROJECT_DIR: directory },
    encoding: "utf8",
  })
  if (res.status !== 2) return
  return res.stderr?.trim() || "Complexidade ciclomatica > 10 em funcao tocada (regra C901)."
}

// v2: edit/write trazem `path`; patch traz o texto V4A, que o lado Python ja sabe
// destrinchar (`*** Update File: ...`) quando chega em `command`.
function toolInputV2(event: any): object | undefined {
  if (event.tool === "edit" || event.tool === "write") {
    const path = event.input?.path
    return typeof path === "string" && path.endsWith(".py") ? { file_path: path } : undefined
  }
  if (event.tool === "patch") {
    const patch = event.input?.patchText
    return typeof patch === "string" && patch.includes(".py") ? { command: patch } : undefined
  }
}

// Acrescenta texto ao que o modelo recebe sem perder o resultado original: sem
// `content`, o OpenCode serializaria `output`, entao isso vira o primeiro bloco.
function anexar(result: any, texto: string): void {
  const atual = result.content
  const blocos =
    typeof atual === "string"
      ? [{ type: "text", text: atual }]
      : Array.isArray(atual) && atual.length > 0
        ? [...atual]
        : [{ type: "text", text: JSON.stringify(result.output) }]
  result.content = [...blocos, { type: "text", text: texto }]
}

export default {
  id: "suap.check-complexity",

  // OpenCode 2.x
  setup: async (ctx: any) => {
    const directory: string = ctx.location.directory
    await ctx.tool.hook("execute.after", (event: any) => {
      try {
        if (event.status !== "completed") return
        const toolInput = toolInputV2(event)
        if (!toolInput) return
        const erro = violacoes(directory, toolInput)
        if (erro) anexar(event.result, `ERRO (bloqueio C901, corrija antes de seguir):\n${erro}`)
      } catch {}
    })
  },

  // OpenCode 1.x
  server: async ({ directory }: { directory: string }) => ({
    "tool.execute.after": async (input: any, output: any) => {
      if (input?.tool !== "edit" && input?.tool !== "write") return
      // Caminho do arquivo editado (defensivo quanto ao formato dos args)
      const filePath: unknown = output?.args?.filePath ?? input?.args?.filePath ?? output?.metadata?.filePath
      if (typeof filePath !== "string" || !filePath.endsWith(".py")) return
      const erro = violacoes(directory, { file_path: filePath })
      if (erro) throw new Error(erro)
    },
  }),
}
