# SUAP MCP — Fase 2: Modelo DecisaoEspecificacao

**Data:** 2026-05-24
**Escopo:** Novo modelo Django `DecisaoEspecificacao` no app `demandas`. Append-only, sem lógica de API ou MCP — isso vem nas Fases 3 e 4.
**Próximo passo:** Fase 3 — endpoints Ninja de leitura.

---

## 1. Modelo

**Arquivo:** `demandas/models/decisao_especificacao.py` (novo)

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

### Decisões de campo

| Campo | Tipo | Decisão |
|---|---|---|
| `demanda` | `ForeignKeyPlus(CASCADE)` | Decisões são deletadas com a demanda |
| `autor` | `ForeignKeyPlus(PROTECT)` | Preserva histórico mesmo se usuário for removido |
| `criado_em` | `DateTimeField(auto_now_add=True)` | Imutável após criação |
| `decisao` | `TextField` | Sem limite — decisões arquiteturais podem ser longas |
| `contexto` | `JSONField(default=dict)` | Metadados estruturados (tool, branch, mr_iid, etc.) |
| `origem` | `CharField(choices)` | `manual` ou `agente` |

### Sem `@reversion.register()`

O modelo é append-only por design — o histórico é o próprio conjunto de registros ordenados por `criado_em`. Reversion não agrega valor e adiciona overhead de write.

### `related_name='decisoes_especificacao'`

Permite `demanda.decisoes_especificacao.all()` — necessário para o endpoint `append_spec_decision` da Fase 4 e para o contexto do agente na Fase 3.

---

## 2. Migrations

Há dois `0042_*` paralelos no branch (resultado de merge com master):
- `0042_add_subdemanda_fields` (branch `demanda_2227`)
- `0042_alter_ambientehomologacao_usuarios` (master)

### Passo 1 — Merge migration

```bash
python manage.py makemigrations --merge demandas -n merge_0042
```

Gera `0043_merge_0042.py` com `dependencies` em ambos os `0042_*`. Sem operações.

### Passo 2 — Migration do modelo

```bash
python manage.py makemigrations demandas
```

Gera `0044_decisaoespecificacao.py` dependendo de `0043_merge_0042`.

Ambas as migrations são geradas automaticamente — sem edição manual.

---

## 3. Registro no `__init__.py`

**Arquivo modificado:** `demandas/models/__init__.py`

Adicionar a linha de exportação seguindo o padrão existente de todos os outros modelos:

```python
from demandas.models.decisao_especificacao import DecisaoEspecificacao
```

---

## 4. Admin

**Arquivo modificado:** `demandas/admin.py`

```python
from demandas.models.decisao_especificacao import DecisaoEspecificacao


@admin.register(DecisaoEspecificacao)
class DecisaoEspecificacaoAdmin(ModelAdminPlus):
    list_display = ('demanda', 'autor', 'origem', 'criado_em', 'decisao_resumida')
    list_filter = ('origem',)
    readonly_fields = ('demanda', 'autor', 'criado_em', 'contexto', 'origem', 'decisao')

    def decisao_resumida(self, obj):
        return obj.decisao[:80]
    decisao_resumida.short_description = 'Decisão'
```

Todos os campos são `readonly_fields` — o admin é somente leitura. Criação de decisões acontece via API (Fase 4), nunca pelo admin.

---

## 5. Testes

**Arquivo novo:** `demandas/tests/test_decisao_especificacao.py`

Cobertura mínima:
- Criação com `origem='manual'` — campos preenchidos corretamente
- Criação com `origem='agente'` e `contexto` JSON
- `__str__` trunca em 60 chars
- `related_name` funciona: `demanda.decisoes_especificacao.count()`
- `criado_em` é imutável (`auto_now_add`)
- Delete da demanda cascadeia para as decisões
- Delete do autor é bloqueado por `PROTECT`

---

## Resumo

| Artefato | Ação |
|---|---|
| `demandas/models/decisao_especificacao.py` | Criar |
| `demandas/models/__init__.py` | Modificar — adicionar export |
| `demandas/admin.py` | Modificar — registrar admin readonly |
| `demandas/migrations/0043_merge_0042.py` | Gerar via `makemigrations --merge` |
| `demandas/migrations/0044_decisaoespecificacao.py` | Gerar via `makemigrations` |
| `demandas/tests/test_decisao_especificacao.py` | Criar |
