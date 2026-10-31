# {{Módulo}}

> {{Uma frase: o que este módulo faz e para quem.}}

## Visão geral

{{2–4 frases: propósito de negócio, por que existe, papel dentro do SUAP. Sem detalhe técnico profundo — isso vai no HLA.}}

## Responsabilidades

- {{O que o módulo É responsável por}}
- {{...}}

**Fora de escopo:** {{o que NÃO é responsabilidade deste módulo / fica em outro app}}

## Atores e papéis

Quem interage com o módulo e o que cada um pode fazer. Derive de `permissions.yaml`,
grupos/decorators (`@login_required`, `@permission_required`, `@group_required`) e de
**papéis relacionais** (FK/campos de função em models) — marque estes como derivados.

| Ator (papel de negócio) | Grupo/permissão (código) | O que pode fazer |
|---|---|---|
| {{ex: Coordenador de curso}} | {{grupo `X` / `app.perm`}} | {{...}} |
| {{ex: Elaborador}} | {{_derivado_ — `ModeloFK.funcao`}} | {{... ⚠️ REVISAR: papel relacional, não é grupo}} |

_Módulo sem ator direto (interno/assíncrono):_ `_N/A — acionado por outros módulos / tasks_`

## Estrutura interna

Preencha só as camadas que existem (SUAP é Django clássico; regras de negócio costumam
viver nos **métodos dos models** — "fat models"). Marque `_N/A_` o que não houver.

| Camada | Local | Conteúdo principal |
|---|---|---|
| Models | `{{modulo}}/models.py` ou `models/` | {{entidades + máquinas de estado}} |
| Views | `{{modulo}}/views.py` ou `views/` | {{views funcionais/CBV; entrypoints das URLs}} |
| URLs | `{{modulo}}/urls.py` | {{rotas sob `/{{modulo}}/`}} |
| API | `{{modulo}}/api.py` | {{endpoints django-ninja, se houver}} |
| Forms | `{{modulo}}/forms.py` | {{`ModelFormPlus`/`FormPlus`}} |
| Admin | `{{modulo}}/admin.py` | {{`ModelAdminPlus` registrados}} |
| Tasks | `{{modulo}}/tasks.py` | {{Celery (`@task`/`@shared_task`); `beat.py`/`cron`}} |
| Commands | `{{modulo}}/management/commands/` | {{commands relevantes}} |
| Outros | `signals.py`, `utils.py`, `templatetags/` | {{...}} |

## Endpoints principais

| Método | Rota | View / operation | Permissão |
|---|---|---|---|
| {{GET}} | {{/{{modulo}}/...}} | {{view ou operation_id}} | {{`@permission_required(...)` / grupo / `auth=JWTAuth()`}} |

_Se o módulo não expõe rotas:_ `_N/A — módulo interno_`

## Modelos de domínio

| Modelo | Descrição | Relações-chave |
|---|---|---|
| {{Nome}} | {{1 linha}} | {{FK/M2M relevantes}} |

ERD completo: ver {{[modelo-de-dados.md](modelo-de-dados.md) ou [modelo-de-dados/](modelo-de-dados/)}}.

## Regras de negócio chave

- {{Regra/método importante e onde vive (`models.py` método X, `utils.py`)}}
- {{> ⚠️ REVISAR: regra que o código não deixa explícita}}

## Jobs / Tasks Celery

| Task | Decorator | Dispara | Idempotência |
|---|---|---|---|
| {{nome}} | {{@task / @shared_task}} | {{gatilho / beat}} | {{sim/não — como}} |

_Sem tasks:_ `_N/A_`

## Dependências

- **Módulos internos:** {{apps que este importa — confira `module_dependencies.json`}}
- **Integrações:** {{documento_eletronico, processo_eletronico, MinIO, Redis, ... (condicionais via `settings.INSTALLED_APPS` quando for o caso)}}

## Configuração

| Origem | Chave | Uso |
|---|---|---|
| {{env / `settings`}} | {{NOME}} | {{para quê}} |
| {{`comum.Configuracao` (app `{{modulo}}`)}} | {{chave}} | {{para quê}} |

_Sem configuração própria:_ `_N/A_`

## Como testar

```bash
pytest {{modulo}}/tests/
```

## Links

- Arquitetura: [HLA.md](HLA.md)
- Glossário: [GLOSSARIO.md](GLOSSARIO.md)
- Fluxos: [fluxos/](fluxos/) (índice em [HLA.md → Fluxos principais](HLA.md#4-fluxos-principais))
- Modelo de dados: {{[modelo-de-dados.md](modelo-de-dados.md) ou [modelo-de-dados/](modelo-de-dados/)}}
- Fronteiras: [FRONTEIRA.md](FRONTEIRA.md)
- {{Docs relacionados, se houver}}

---
_Gerado/atualizado via subagent `documentador` em {{AAAA-MM-DD}}._
