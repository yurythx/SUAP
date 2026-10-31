# Metadados dos models no banco — design

Data: 2026-10-17
Status: aguardando revisão

## Por quê

A análise exploratória de dados (Metabase ou qualquer cliente SQL) é feita sobre uma **cópia separada
do banco de produção**, sem o Django. O que dá sentido aos dados vive só no código Python: o rótulo de
um `choices`, o nome legível do campo, o `help_text`, o default aplicado em Python. Exemplo real:
`edu_componentecurricular.tipo` guarda `1..6`; que `1` é "Regular" só se descobre abrindo o Django.

Objetivo: o banco carregar esses metadados em tabelas comuns, de modo que quem analisa **veja o rótulo
direto no resultado da consulta** (JOIN) e encontre por SQL a descrição de tabelas e colunas.

## Pedido × suposições

- Pedido: metadados em **tabelas** no banco, inclusive em produção (a cópia herda); schema `public`;
  modelos novos em `djtools`. **Sem** comentários nativos do Postgres (`COMMENT ON`).
- Pedido: atributos a levar — descritivos (verbose_name do model e do field, docstring, help_text),
  `choices`, transições FSM, GenericForeignKey, `limit_choices_to`, `default`, `editable`,
  `auto_now`/`auto_now_add`.
- Suposição (minha): atualizar a cada deploy é frescor suficiente.

## Linha de base medida (introspecção, 2026-10-17)

2.209 models, 18.738 fields concretos próprios (sem herdados nem relações reversas).

| Atributo | Ocorrências |
|---|---|
| `verbose_name` explícito do field | ~14,9 mil |
| `help_text` | 1.608 |
| `verbose_name` do model | 1.894 de 2.209 |
| docstring real do model | 152 de 2.209 |
| `choices` | 1.155 (todos listas estáticas; valores int 585, str 546, bool 11, None 12; 1 agrupado) |
| `FSMIntegerField` (django_fsm) | 25 |
| `GenericForeignKey` | 24 |
| `limit_choices_to` | 27 |
| `default` | 2.903 (2.660 estáticos, 243 callables) |
| `editable=False` | 1.131 |
| FK sem constraint no banco | 0 (o Metabase já enxerga todas as FKs) |

Medição: carregar o Django e iterar `apps.get_models()` → `_meta.get_fields()` filtrando
`f.concrete and f.model is m`. Nenhum par de models não-proxy divide `db_table`.

## Metas

1. Quatro tabelas de consulta, modelos novos em `djtools` (detalhe em "Tabelas"):
   - **tabelas** — uma linha por tabela física: nome legível e docstring do model.
   - **campos** — dicionário de dados, uma linha por coluna, com descritivo e atributos estruturados.
   - **choices** — o JOIN que troca valor por rótulo.
   - **transições** — as transições dos campos FSM.
2. Geração automática a partir dos models, por um management command chamado dentro de
   `comum/management/commands/sync.py` (roda em todo deploy: `bin/ci/deploy.sh`, `deploy-remote.sh`).
   Vale para todas as instituições sem configuração. Roda também à mão, para popular uma cópia antiga.

## Não metas

- Comentários nativos (`COMMENT ON`, `db_comment`, `db_table_comment`).
- Editar os ~90 apps ou gerar migrations neles.
- Escrever docstrings que faltam.
- Configurar o Metabase (descrições, remapeamento).
- Expor metadados por tela, admin ou API.
- Atributos de formulário/internos: `widget_attrs`, `extra_attrs`, `validate_caracter`, `search_attrs`,
  validadores, `upload_to`, `ordering`, `permissions` do Meta.

## Anti-metas (falhou mesmo funcionando)

- Deploy abortado porque um model tem metadado estranho.
- Leitura do Metabase bloqueada enquanto o comando roda.
- JOIN de choices devolvendo linhas duplicadas.

## Restrições

- Escopo dos models: `apps.get_models()` com `managed=True`, não proxy e no banco `default` (exclui os
  de `ldapdb`). Field pertence à tabela do model que o declara (`f.model is m`), o que resolve herança
  multi-tabela. Tabelas `through` automáticas de M2M entram como qualquer model; as próprias tabelas
  `metadados_*` também.
- Textos lazy (`gettext_lazy`) forçados para `str` com o idioma `pt-br` ativo.
- Docstring só quando real — o Django gera `Nome(campo, ...)` em `__doc__` quando o model não tem;
  essa não conta.
- Código novo segue o repo: pt-BR, tipagem nas defs tocadas, complexidade ciclomática ≤ 10.

## Tabelas

Nomes de tabela explícitos (`db_table`) com prefixo `metadados_`, para quem analisa achá-las juntas.
Colunas abaixo são o mínimo combinado; nomes exatos ficam com quem constrói. Chave natural entre
parênteses, com `UniqueConstraint`.

### `metadados_tabelas` (tabela)

app, model (label), verbose_name, verbose_name_plural, docstring.

### `metadados_campos` (tabela, coluna)

- identificação: app, model (label), nome do field, tipo Django (classe do field);
- descritivo: verbose_name, help_text;
- `default` em texto (repr do valor estático; para callable, o caminho `modulo.nome`) + indicador de
  callable;
- `editable`, `auto_now`, `auto_now_add`;
- relação: tabela alvo da FK; `limit_choices_to` em texto (dict/Q via repr; callable via nome — nunca
  avaliar, pode consultar o banco);
- GenericForeignKey: nas linhas das duas colunas do par (`ct_field`, `fk_field`), o nome do GFK, para
  saber que `tipo_relacionamento` + `id_relacionamento` formam uma referência.

### `metadados_choices` (tabela, coluna, valor)

| coluna | conteúdo |
|---|---|
| tabela, coluna | `db_table` do model, `f.column` |
| valor | texto na **representação textual do Postgres**, para casar com `coluna::text` |
| rotulo | rótulo do choice |
| ordem | posição na lista |
| grupo | rótulo do grupo, quando agrupado |

Conversão de `valor`: `'true'`/`'false'` para bool, `.value` para Enum/`Choices`, `str(v)` para o
resto (um `CharField` com choices inteiros casa igual). Valor `None` grava nulo (não casa por JOIN).
Campos de array com choices no `base_field` (`ChoiceArrayField`) registram os choices do elemento.

```sql
SELECT cc.*, c.rotulo AS tipo_rotulo
FROM edu_componentecurricular cc
LEFT JOIN metadados_choices c
  ON c.tabela = 'edu_componentecurricular' AND c.coluna = 'tipo' AND c.valor = cc.tipo::text;
```

### `metadados_transicoes` (tabela, coluna, nome, origem)

Para cada `FSMField`/`FSMIntegerField`: nome do método de transição, origem, destino
(`field.get_all_transitions(model)`). Origens `*`/`+` do django_fsm gravadas como vieram.

## Decisões de construção (minhas, conferir)

- **Models:** `models.Model` puro em `djtools/models.py` (como `PushSubscription`), sem `ModelPlus`:
  nada de permissões, History, admin, menu. Uma migration nova em `djtools`.
- **Colisão de chave** (duas definições para a mesma tabela/coluna, choice com valor repetido): fica a
  primeira, aviso no stdout.
- **Recriar:** `DELETE` + `bulk_create` numa transação, nunca `TRUNCATE` (`ACCESS EXCLUSIVE` bloquearia
  a leitura). Leitor concorrente vê o estado antigo ou o novo. Idempotência é de conteúdo; os ids mudam
  a cada execução.
- **Erro num model:** aviso e segue; o comando termina com um resumo (models processados, com erro e
  quais) no log do deploy. Não aborta o `sync`.
- **Quando roda:** sempre no `sync`, logo depois de `migrate`, inclusive em dev (~20 mil linhas, alguns
  segundos). `gerar_banco_mock` não muda.

## Testes

Um teste em `djtools/tests/tasks/` que roda o comando no banco de teste e verifica, num model real e
estável (ex.: `edu.ComponenteCurricular.tipo`): a linha de choice `1 → Regular`, a linha em
`metadados_campos` e a de `metadados_tabelas`. Segunda execução produz o mesmo conteúdo, sem duplicar.

## Fica com quem constrói

- Nomes do comando, dos models e das colunas.
- Como representar em texto `default` e `limit_choices_to` além do combinado.
