# Design — Vínculo Entrega ↔ Especificação

**Data:** 2026-06-18
**Branch:** demanda_2227
**Módulo:** `demandas`

## Contexto

O módulo `demandas` modela o ciclo de uma Demanda. A "definição de pronto"
(`DoD`, classe `Consolidacao`) de cada Demanda contém uma lista ordenada de
`Especificacao` (campos `nome`, `atividades`, `ordem`, `gitlab_issue_url`) — a
unidade de trabalho a ser entregue.

A `Entrega` (introduzida na branch `demanda_2227`) representa um pacote enviado
ao cliente para homologação. Hoje ela descreve o que foi entregue apenas por
texto livre (`titulo`, `descricao`, `notas`), sem qualquer relação com as
especificações que efetivamente compõem aquele pacote.

**Problema:** uma especificação *é* aquilo que será entregue. Faltando o vínculo,
não há rastreabilidade de quais especificações foram incluídas em cada entrega
(entregas parciais, re-entregas após reprovação, etc.).

## Decisões

| Tema | Decisão |
|------|---------|
| Papel do vínculo | **Só rastreabilidade.** Não acopla o ciclo de vida da especificação. Aprovar/reprovar entrega NÃO altera a especificação. |
| Obrigatoriedade | **Opcional.** Permite entregas avulsas (hotfix/ajuste) sem espec formal. |
| Texto livre | `descricao`/`notas` **permanecem** — complementam, não substituem o vínculo. |
| Cardinalidade | **ManyToMany.** Uma entrega tem N especificações; uma especificação pode reaparecer em várias entregas (re-entrega após reprovação). |

## Solução

### 1. Modelo — `demandas/models/entrega.py`

Adicionar a `Entrega`:

```python
especificacoes = models.ManyToManyField(
    'demandas.Especificacao',
    verbose_name='Especificações entregues',
    blank=True,
    related_name='entregas',
    help_text='Especificações do DoD incluídas neste pacote de entrega.',
)
```

- M2M (não FK), `blank=True` → opcional. Tabela de associação pura, sem campos
  extras (coerente com "só rastreabilidade").
- `related_name='entregas'` permite `especificacao.entregas.all()`.

### 2. Migration

Nova migration aditiva (somente a tabela M2M). Sem risco a dados existentes.

### 3. Service — `EntregaService.criar`

Novo parâmetro `especificacoes: Iterable[Especificacao] | None = None`. Após
`entrega.save()` (M2M exige PK), dentro da transação atômica existente:

```python
if especificacoes:
    entrega.especificacoes.set(especificacoes)
```

### 4. Form — `EntregaForm`

- Campo `especificacoes` declarado explicitamente como
  `MultipleModelChoiceFieldPlus`, `required=False`, widget
  `CheckboxSelectMultiple`.
- Queryset escopado à demanda em `__init__`:
  `Especificacao.objects.filter(dod__demanda=self.demanda)`.
- Se a demanda não possui especificações, **remover** o campo (`del
  self.fields['especificacoes']`) para não renderizar caixa vazia.
- A view `criar_enrega` passa `especificacoes=form.cleaned_data.get('especificacoes')`
  ao service (a view usa o service, não `form.save()`).

### 5. Template — `demandas/templates/tabs/entregas.html`

- No bloco da entrega pendente: exibir as especificações vinculadas (read-only)
  como lista/badges de `nome` (condicional a existirem).
- No histórico de entregas: idem, de forma compacta (opcional/condicional).

### 6. Testes

- **Modelo:** roundtrip M2M (`entrega.especificacoes.set([...])`) e reverse
  (`especificacao.entregas`). Sem necessidade de salvar além do mínimo.
- **Form:** queryset escopado ao DoD da demanda; campo opcional; campo é removido
  quando a demanda não tem especificações.
- **Service:** `EntregaService.criar(..., especificacoes=[...])` vincula
  corretamente; sem especificações não cria vínculos.

## Fora de escopo (YAGNI)

- Alterar status/ciclo de vida da `Especificacao` ao aprovar/reprovar entrega.
- Expor `especificacoes` no schema da API Ninja de entregas
  (`api/schemas/demandas.py`, `api/endpoints/entregas.py`) — possível follow-up
  separado.
- Edição do vínculo após a criação da entrega (por ora, definido só na criação).
