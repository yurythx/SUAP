---
name: migration-check
description: >
  Detecta migrações Django ausentes antes de qualquer commit ou MR.
  Executa makemigrations --check --dry-run em todos os apps alterados e
  lista quais precisam de migração gerada — antes que o job `checagem-codigo` do CI
  a acuse (o `pre-commit` não checa migrações).
  Trigger: /migration-check, "checar migrações", "verificar migrations",
  "faltam migrations".
trigger: /migration-check
allowed-tools:
  - Bash
  - Read
  - Grep
  - Glob
---

# Migration Check — Detector de Migrações Ausentes

Detecta se alterações em `models.py` requerem migrações não geradas, **antes** de o gate do `pre-commit` bloquear o commit no CI.

`allowed-tools` é metadado para clientes que o suportam. No Codex, use as ferramentas
locais equivalentes de leitura, busca e shell; esta skill não depende de MCP externo.

## Quando usar

- Antes de qualquer `git commit` que toque `models.py`, `models/*.py` ou arquivos com classes `Model`
- Ao revisar um MR com alterações de modelos
- Quando o CI reportar `Your models in app(s): X have changes that are not yet reflected in a migration`

## Workflow

### Passo 1: Identificar apps alteradas

```bash
# Arquivos alterados em relação ao master
git diff --name-only origin/master..HEAD | grep '\.py$' | grep -v migrations
```

Extrair apps únicas: `{app}/models.py` → app = primeiro segmento do path.

### Passo 2: Checar migrações pendentes

```bash
source .venv/bin/activate

# Checar TODOS os apps de uma vez
python manage.py makemigrations --check --dry-run 2>&1
```

Interpretar saída:
- `No changes detected` → nenhuma migração ausente
- `Migrations for '{app}': ...` → app precisa de migração
- Erro de import → problema no model, reportar separadamente

### Passo 3: Checar migrações existentes não aplicadas

```bash
python manage.py migrate --check 2>&1
```

Isso detecta migrações geradas mas não aplicadas no banco local de dev.

### Passo 4: Reportar resultado

**Se tudo OK:**

```
✅ Migration check: nenhuma migração ausente nos apps alterados.
```

**Se há migrações ausentes:**

```
❌ Migrações ausentes detectadas:

Apps que precisam de `makemigrations`:
- edu: campo `novo_campo` adicionado em `Matricula`
- rh: tabela `CargoTemporario` alterada

Executar para gerar:
  python manage.py makemigrations edu rh

Depois revisar o arquivo gerado e incluir no commit.
```

**Se há migrações não aplicadas no banco local:**

```
⚠️  Migrações pendentes no banco local (apenas dev):
  python manage.py migrate

  Nota: no ambiente de testes o banco é pré-construído (MIGRATE=False),
  então isso não afeta `test_suap`.
```

## Integração com pre-commit

O gate do `pre-commit` (`pre-commit run --from-ref origin/master --to-ref HEAD`) **não verifica migrações** — essa checagem é feita no CI pelo `checagem-codigo`. Use este skill **antes** do commit para antecipar falhas de CI.

## Gotchas SUAP

- `USUARIOGRUPO_AS_ABSTRACT=1` é necessário para rodar `makemigrations` corretamente em alguns apps. Já é setado pelo `test_suap`, mas pode ser necessário exportar manualmente se rodar direto.
- Apps em `INSTALLED_APPS_SUAP` têm ordem de carregamento controlada por `suap/__init__.py` — sempre use `python manage.py makemigrations` (não `django-admin`) para respeitar essa ordem.
- Nunca comitar migrações geradas automaticamente sem revisar o conteúdo — confirmar que o `operations` reflete exatamente o que foi alterado no model.

## Constraints

- **NUNCA** executar `makemigrations` sem `--check` ou `--dry-run` sem confirmação explícita do usuário
- **NUNCA** executar `migrate` sem confirmação — pode afetar dados locais
- Apenas reportar; a decisão de gerar e comitar é sempre do desenvolvedor
