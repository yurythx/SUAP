// Pre-commit enforcement plugin for SUAP
// Poe as checagens do CI na frente de todo `git commit` (--no-verify/-n pulam).
// A regra vive no nucleo compartilhado .agents/hooks/commit_gate.py, o mesmo que o
// Claude Code e o Codex usam; aqui so filtramos barato e delegamos.
//
// Formato duplo: `setup` e a API do OpenCode 2.x; `server` e a do 1.x (a imagem do
// CI, bin/ci/Dockerfile.opencode). Cada loader le so a chave dele e ignora a outra.

import { spawnSync } from "node:child_process"
import { join } from "node:path"

// Comando com as checagens na frente, ou undefined se o gate nao se aplica. Se alguma
// checagem falhar, o && para e o commit nao acontece.
function comPreCommit(directory: string, command: unknown): string | undefined {
  if (typeof command !== "string" || !/\bgit\b[\s\S]*\bcommit\b/.test(command)) return
  const res = spawnSync("python3", [join(directory, ".agents/hooks/commit_gate.py")], {
    input: JSON.stringify({ tool_input: { command } }),
    cwd: directory,
    encoding: "utf8",
  })
  if (res.status !== 0 || !res.stdout?.trim()) return
  const novo = JSON.parse(res.stdout).hookSpecificOutput?.updatedInput?.command
  return typeof novo === "string" ? novo : undefined
}

export default {
  id: "suap.pre-commit",

  // OpenCode 2.x: a ferramenta de shell chama `shell` e os args vem em `event.input`.
  // Hook v2 nunca lanca: o adapter transforma rejeicao em defeito e derruba o turno.
  setup: async (ctx: any) => {
    const directory: string = ctx.location.directory
    await ctx.tool.hook("execute.before", (event: any) => {
      try {
        if (event.tool !== "shell") return
        const command = comPreCommit(directory, event.input?.command)
        if (command) event.input = { ...event.input, command }
      } catch {}
    })
  },

  // OpenCode 1.x
  server: async ({ directory }: { directory: string }) => ({
    "tool.execute.before": async (input: any, output: any) => {
      if (input.tool !== "bash") return
      if (!output.args) return
      const command = comPreCommit(directory, output.args.command)
      if (command) output.args.command = command
    },
  }),
}
