# CONTEXT — SUAP

Sistema Unificado de Administração Pública do IFRN. Monólito Django ≈90 apps que cobre o ciclo de vida acadêmico, gestão de pessoas e administração pública. Este documento dá a um leitor (humano ou agente) o vocabulário e as restrições mínimas antes de tocar no código.

Para detalhes operacionais (comandos, layout de apps, hooks, conventions ruff/pyright), ver `CLAUDE.md`. Este arquivo descreve **domínio e decisões** — não substitui `CLAUDE.md`.

## Atores

- **Aluno** — identificado por `Matricula`, vinculado a um `Curso`/`Matriz Curricular`. Tem `Vinculo` próprio.
- **Servidor** — docente ou técnico-administrativo. Sincronizado a partir do **SIAPE/SIAPEnet** (federal). Tem `Vinculo`.
- **Terceirizado / Prestador de serviço** — entra via `comum`, sem dados SIAPE.
- **Usuário externo** — autenticado pelo **Gov.br**; participa de processos eletrônicos sem ter `Servidor` ou `Aluno`.
- **Bot / agente automatizado** — identidade via token de API (`django-ninja`) ou job Celery; opera com `Vinculo` técnico.

Toda identidade dentro do sistema é projetada sobre um **`Vinculo`** (em `comum`). O mesmo `PessoaFisica` pode ter múltiplos vínculos (ex.: ex-aluno que vira servidor). Decisões de permissão e auditoria amarram no `Vinculo`, não no `User`.

## Subsistemas

| App | Papel | Depende de |
|-----|-------|------------|
| `comum` | Identidade (`PessoaFisica`, `Vinculo`, `Configuracao`), login, healthcheck, webservice XML-RPC, handlers 4xx/5xx globais. | `djtools` |
| `djtools` | Framework SUAP — `ModelPlus`, `ModelAdminPlus`, forms/tables custom, PDF, middleware, helpers de async. **Carrega antes** de `django.contrib.admin`. | — |
| `rh` | Pessoas (servidores, prestadores), setores, lotações. Integra SIAPE/SIAPEnet via `importador_ws`. | `comum` |
| `edu` | Núcleo acadêmico — alunos, cursos, matrizes, diários, faltas, requerimentos, procedimentos (abono, trancamento, aproveitamento). | `rh`, `comum` |
| `processo_eletronico` | Tramitação de processos administrativos, integração com Barramento (PEN/Gov). | `comum`, `rh` |
| `protocolo` | Documentos e fluxos de protocolo (antecessor parcial de `processo_eletronico`). | `comum` |
| `beat`, `cron` | Agendamento Celery + jobs cron. | `djtools` |

A dependência canônica entre apps fica em `module_dependencies.json` (validada por `python manage.py module_dependencies --check --all`). Quando este arquivo conflita com o `CONTEXT`, **o JSON manda** — atualize o `CONTEXT`.

## Invariantes globais

1. **`Vinculo` é a identidade canônica.** Permissões, auditoria, ownership amarram em `Vinculo`, não em `User`.
2. **Toda model herda de `djtools.db.models.ModelPlus`**, não de `django.db.models.Model`. O comportamento extra (campos automáticos, hooks de admin, integração com tables/PDF) presume essa cadeia. Ver ADR-0001.
3. **Migrations não rodam em testes.** Schema vem dos models atuais (`--no-migrations`). Migrations existem só para deploy. Ver ADR-0002.
4. **Ordem de apps é reescrita em `makemigrations`/`migrate`/`sync`** para `PRE_INSTALLED_APPS_SUAP + APPS_SUAP + POS_INSTALLED_APPS_SUAP`. Em runtime, a ordem é a do `settings_base.py`. Ver ADR-0003.
5. **Idioma é pt-BR.** Identificadores, comentários, mensagens, commits, docstrings. Misturar inglês contamina a busca e os relatórios — só use inglês quando o termo for técnico canônico (HTTP, SQL, OAuth).
6. **URLs são auto-descobertas.** Cada app com `urls.py` é montado em `/{app}/`. Não registre manualmente.

## Integrações externas

- **SIAPE / SIAPEnet** — federal, dados de servidores. Acesso via SOAP. Fault codes `0030` e `0002` significam "sem dados" (não erro). Ver `rh/importador_ws.py`.
- **Gov.br** — OAuth2 / SAML para autenticação de externos.
- **Barramento PEN** — interoperabilidade de processos administrativos entre órgãos federais. Ver `processo_eletronico/barramento`.
- **Sentry** — observabilidade. Issues referenciadas como `SUAP-XXX`. Skill `sentry-fix` automatiza correção.
- **GitLab self-hosted** (`gitlab.ifrn.edu.br/cosinf/suap`) — MRs e issues. Skill `mr-format` padroniza descrições.

## Tabus / armadilhas conhecidas

Decisões que parecem refactoráveis mas têm motivo. Antes de tocar, ler o ADR ou perguntar.

- Não trocar `ModelPlus` por `models.Model` "para padronizar". Ver ADR-0001.
- Não adicionar `pytest --migrations` na suíte. Ver ADR-0002.
- Não mover ordem de `INSTALLED_APPS` em `settings_base.py` esperando que ela valha em runtime de `makemigrations`. Ver ADR-0003.
- Não atribuir M2M com `=`; usar `.set()`. Bug recorrente em forms (ex.: SUAP-T8J).
- Não confiar em `hasattr(obj, 'fk_field')` para detectar FK pendurado em registro deletado — `DoesNotExist` não é `AttributeError`. Usar `try/except`. Bug recorrente (ex.: SUAP-T42).

## Como navegar

- Comandos, lint, layout de app, hooks → `CLAUDE.md`.
- Decisões de arquitetura → `docs/adr/`.
- Vocabulário de domínio → `docs/glossario.md`.
- Skills de agente → `.agents/skills/<nome>/SKILL.md` (fonte única, lidas nativamente por Codex/OpenCode/Antigravity; o Claude Code as enxerga por symlink em `.claude/skills/`).
- Issue tracking e triagem → `docs/agents/issue-tracker.md`, `docs/agents/triage-labels.md`.
