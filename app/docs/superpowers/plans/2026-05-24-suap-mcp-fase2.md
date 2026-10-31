# SUAP MCP — Fase 2: Modelo DecisaoEspecificacao

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Criar o modelo Django `DecisaoEspecificacao` no app `demandas` com migrations e admin readonly.

**Architecture:** Novo arquivo `demandas/models/decisao_especificacao.py` seguindo o padrão one-model-per-file já estabelecido. Migrations em duas etapas: merge dos dois `0042_*` paralelos, depois migration do modelo. Admin é estritamente readonly — escrita via API (Fase 4). Testes estão pendentes (ver seção ao final) — a arquitetura de testes com pytest está sendo montada.

**Tech Stack:** Django 5.2, djtools (`ModelPlus`, `ForeignKeyPlus`, `CharFieldPlus`), `python manage.py` para migrations. Repositório: `/Users/diegosaraiva/Workspace/ifrn/suap`. Branch: `demanda_2227`.

---

## Mapa de Arquivos

| Arquivo | Ação | Responsabilidade |
|---|---|---|
| `demandas/models/decisao_especificacao.py` | Criar | Modelo `DecisaoEspecificacao` |
| `demandas/models/__init__.py` | Modificar | Exportar o novo modelo via `from .decisao_especificacao import *` |
| `demandas/migrations/0043_merge_0042.py` | Gerar | Merge das duas `0042_*` paralelas |
| `demandas/migrations/0044_decisaoespecificacao.py` | Gerar | Criação da tabela |
| `demandas/admin.py` | Modificar | Registrar `DecisaoEspecificacaoAdmin` readonly |

---

## Task 1: Modelo DecisaoEspecificacao + migrations

**Files:**
- Create: `demandas/models/decisao_especificacao.py`
- Modify: `demandas/models/__init__.py`
- Generate: `demandas/migrations/0043_merge_0042.py`
- Generate: `demandas/migrations/0044_decisaoespecificacao.py`

- [ ] **Step 1: Criar o modelo**

Criar `demandas/models/decisao_especificacao.py`:

```python
from django.conf import settings

from djtools.db import models
from djtools.db.models import ModelPlus


class DecisaoEspecificacao(ModelPlus):
    ORIGEM_MANUAL = 'manual'
    ORIGEM_AGENTE = 'agente'
    ORIGEM_CHOICES = (
        (ORIGEM_MANUAL, 'Manual'),
        (ORIGEM_AGENTE, 'Agente'),
    )

    demanda = models.ForeignKeyPlus(
        'demandas.Demanda',
        verbose_name='Demanda',
        on_delete=models.CASCADE,
        related_name='decisoes_especificacao',
    )
    autor = models.ForeignKeyPlus(
        settings.AUTH_USER_MODEL,
        verbose_name='Autor',
        on_delete=models.PROTECT,
    )
    criado_em = models.DateTimeField('Criado em', auto_now_add=True)
    decisao = models.TextField('Decisão')
    contexto = models.JSONField('Contexto', default=dict, blank=True)
    origem = models.CharFieldPlus(
        'Origem',
        max_length=10,
        choices=ORIGEM_CHOICES,
        default=ORIGEM_MANUAL,
    )

    class Meta:
        verbose_name = 'Decisão de Especificação'
        verbose_name_plural = 'Decisões de Especificação'
        ordering = ['criado_em']

    def __str__(self) -> str:
        return f'{self.demanda} — {self.decisao[:60]}'
```

- [ ] **Step 2: Adicionar export no `__init__.py`**

Editar `demandas/models/__init__.py` — adicionar esta linha ao final:

```python
from .decisao_especificacao import *
```

O arquivo completo ficará assim:

```python
# ruff: noqa: F403

from .demanda import *
from .consolidacao import *
from .sugestao import *
from .atualizacao import *
from .ambiente import *
from .priorizacao import *
from .entrega import *
from .decisao_especificacao import *
```

- [ ] **Step 3: Criar merge migration das duas 0042_\***

```bash
cd /Users/diegosaraiva/Workspace/ifrn/suap
python manage.py makemigrations --merge demandas -n merge_0042 --noinput
```

Esperado: criação de `demandas/migrations/0043_merge_0042.py` com conteúdo similar a:

```python
class Migration(migrations.Migration):
    dependencies = [
        ('demandas', '0042_add_subdemanda_fields'),
        ('demandas', '0042_alter_ambientehomologacao_usuarios'),
    ]
    operations = []
```

- [ ] **Step 4: Criar migration do modelo**

```bash
cd /Users/diegosaraiva/Workspace/ifrn/suap
python manage.py makemigrations demandas --noinput
```

Esperado: criação de `demandas/migrations/0044_decisaoespecificacao.py` com `CreateModel` para `DecisaoEspecificacao`.

Verificar que o arquivo foi criado:

```bash
ls demandas/migrations/0044*
```

- [ ] **Step 5: Verificar que o app carrega sem erros**

```bash
cd /Users/diegosaraiva/Workspace/ifrn/suap
python manage.py check 2>&1 | grep -i "error" | head -10
```

Esperado: nenhuma linha de saída (zero erros).

- [ ] **Step 6: Commit**

```bash
cd /Users/diegosaraiva/Workspace/ifrn/suap
git add \
  demandas/models/decisao_especificacao.py \
  demandas/models/__init__.py \
  demandas/migrations/0043_merge_0042.py \
  demandas/migrations/0044_decisaoespecificacao.py
git commit -m "feat: add DecisaoEspecificacao model with migrations"
```

---

## Task 2: Admin readonly

**Files:**
- Modify: `demandas/admin.py`

- [ ] **Step 1: Adicionar a importação em `demandas/admin.py`**

Localizar o bloco `from .models import (` existente (linha ≈18) e adicionar `DecisaoEspecificacao` à lista:

```python
from .models import (
    AmbienteHomologacao,
    AnalistaDesenvolvedor,
    AreaAtuacaoDemanda,
    Atualizacao,
    Demanda,
    DecisaoEspecificacao,
    ProjetoGitlab,
    Situacao,
    SugestaoMelhoria,
    Tag,
    HistoricoEntrega,
    Entrega,
)
```

- [ ] **Step 2: Adicionar a classe admin ao final de `demandas/admin.py`**

Adicionar ao final do arquivo (após todas as classes existentes):

```python
@admin.register(DecisaoEspecificacao)
class DecisaoEspecificacaoAdmin(ModelAdminPlus):
    list_display = ('demanda', 'autor', 'origem', 'criado_em', 'decisao_resumida')
    list_filter = ('origem',)
    readonly_fields = ('demanda', 'autor', 'criado_em', 'contexto', 'origem', 'decisao')

    def decisao_resumida(self, obj):
        return obj.decisao[:80]

    decisao_resumida.short_description = 'Decisão'
```

- [ ] **Step 3: Verificar que o admin carrega sem erros**

```bash
cd /Users/diegosaraiva/Workspace/ifrn/suap
python manage.py check 2>&1 | grep -i "error" | head -10
```

Esperado: nenhuma linha de saída (zero erros).

- [ ] **Step 4: Commit**

```bash
cd /Users/diegosaraiva/Workspace/ifrn/suap
git add demandas/admin.py
git commit -m "feat: register DecisaoEspecificacao in admin as readonly"
```

---

## Testes (pendente — aguardando migração para pytest)

> Quando a arquitetura de testes com pytest estiver pronta, criar `demandas/tests/test_decisao_especificacao.py` cobrindo os 7 cenários abaixo. Usar o fixture de usuário autenticado e uma `Demanda` de setup.

### Cenários obrigatórios

| Cenário | O que verificar |
|---|---|
| Criação com `origem='manual'` | `pk` não nulo, `origem == 'manual'`, `contexto == {}`, `criado_em` preenchido |
| Criação com `origem='agente'` e `contexto` JSON | `origem == 'agente'`, `contexto['tool']` acessível |
| `__str__` trunca em 60 chars | `str(decisao)` contém os primeiros 60 chars, não contém o 61º |
| `related_name` funciona | `demanda.decisoes_especificacao.count() == 2` após criar 2 decisões |
| CASCADE na deleção da demanda | Deletar a demanda → `DecisaoEspecificacao.objects.filter(demanda_id=...).count() == 0` |
| PROTECT na deleção do autor | `user.delete()` levanta `ProtectedError` quando há decisão vinculada |
| `criado_em` é imutável | Alterar outro campo e salvar → `criado_em` não muda |

### Setup mínimo do fixture

```python
# Demanda pode ser criada com título e descrição apenas
demanda = Demanda.objects.create(
    titulo='Demanda de teste Fase 2',
    descricao='Descrição para testes do modelo DecisaoEspecificacao',
)

# Campos obrigatórios para criar uma DecisaoEspecificacao
DecisaoEspecificacao.objects.create(
    demanda=demanda,
    autor=user,         # usuário autenticado pelo fixture de pytest
    decisao='Texto da decisão',
)
```

### Constantes relevantes

```python
DecisaoEspecificacao.ORIGEM_MANUAL  # == 'manual'
DecisaoEspecificacao.ORIGEM_AGENTE  # == 'agente'
```

---

## Referência: campos do modelo

Para uso nas Fases 3 e 4 ao criar decisões via API:

```python
# Criação de uma decisão pelo agente (Fase 4)
DecisaoEspecificacao.objects.create(
    demanda=demanda,
    autor=request.user,              # JWT → django-reversion registra o dev correto
    decisao='Texto da decisão',
    origem=DecisaoEspecificacao.ORIGEM_AGENTE,
    contexto={
        'tool': 'append_spec_decision',
        'demanda_id': demanda.pk,
    },
)
```
