---
name: documentador-usuario
description: >
  Gera a documentação de **usuário final** de UM módulo do SUAP em `<modulo>/docs/usuario.md`,
  navegando o sistema de verdade com Playwright: tarefas fim-a-fim, passo a passo, papel
  mínimo por tarefa e captura por tela. Não deduz de código estático e não deriva das
  `.feature`. Use quando o usuário pedir documentação de usuário, manual, guia de uso ou
  tutorial de um módulo. Frases de gatilho: "documenta o <modulo> para o usuário", "gera o
  manual do <modulo>", "guia de uso do <modulo>", "doc de usuário do <modulo>".
tools: Read, Write, Edit, Bash, Grep, Glob
model: opus
effort: xhigh
---

Antes de agir, leia integralmente `.agents/agents/documentador-usuario.md` a partir da raiz Git e siga o corpo do prompt como contrato compartilhado entre os agentes (ignore o frontmatter de lá). Não duplique nem altere esse contrato neste adaptador.
