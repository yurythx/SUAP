# Passo 1 da unificação de PessoaFisica: mover campos para Vínculo

**Data:** 2026-07-01
**Status:** aprovado (aguardando plano de implementação)
**Contexto do projeto:** primeiro passo executável da unificação de `PessoaFisica`
(1 pessoa civil real = 1 PF + N Vínculos). Ver `docs/superpowers/specs/2026-05-25-pessoa-fisica-unificada-design.md`.

## Sumário

Adicionar 8 campos ao modelo `comum.Vinculo` e copiar (backfill) os valores atuais
vindos de `Pessoa` / `PessoaFisica`. Passo **aditivo, reversível, sem breaking change**:
não remove campos, não altera call-sites, não introduz `UNIQUE`/codemod.

## Contexto e decisão de sequenciamento

O plano original (2026-05-25) sequenciava: MR1 dedup → MR2 novos campos no Vínculo →
MR3 codemod → MR4 remoção. O **MR1 (!18214) foi fechado em 2026-06-02 sem merge**;
a migration de dedup não está no `master`.

Decisão do usuário (2026-07-01): **fazer o field-move como primeiro passo**, sem
depender do dedup. Justificativa: adicionar campos ao `Vinculo` + backfill-cópia é
ortogonal ao dedup — `Vinculo.email_pessoal = vinculo.pessoa.email` é correto haja ou
não deduplicação, sem perda de dado. O dedup fica para um passo posterior.

Estado atual do dado: **hoje cada `Pessoa` tem exatamente 1 `Vinculo`** (a multiplicidade
N:1 só passa a existir depois da unificação). Logo o backfill é 1:1 trivial: itera
`Vinculo` e puxa de `vinculo.pessoa`.

## Onde os campos vivem hoje

- `email`, `email_secundario`, `setores_adicionais`, `sistema_origem` → modelo base
  `Pessoa` (`rh/models/pessoa/pessoa.py`), **compartilhado com `PessoaJuridica`**.
- `foto`, `raca`, `povo_indigena`, `deficiencia` → `PessoaFisica`
  (`rh/models/pessoa/pessoa_fisica.py`).
- `Vinculo` vive em `comum/models.py` e já referencia `rh.Pessoa` e `rh.Setor`.

## Campos a adicionar ao `Vinculo`

| Origem (modelo.campo) | Novo campo (`Vinculo`) | Tipo | Aplica a PJ? |
|---|---|---|---|
| `Pessoa.email` | `email_pessoal` | `EmailField(blank=True)` | Sim |
| `Pessoa.email_secundario` | `email_notificacao` | `EmailField(blank=True)` | Sim |
| `Pessoa.setores_adicionais` | `setores_adicionais` | `ManyToManyField('rh.Setor', blank=True, related_name=...)` | Sim |
| `Pessoa.sistema_origem` | `sistema_origem` | `CharField(max_length=50, blank=True, choices=...)` | Sim |
| `PessoaFisica.foto` | `foto` | `ImageWithThumbsField(storage=get_overwrite_storage(), use_id_for_name=True, upload_to='fotos', sizes=((75,100),(150,200)), null=True, blank=True)` | Não (só PF) |
| `PessoaFisica.raca` | `raca` | `ForeignKeyPlus('comum.Raca', null=True, on_delete=...)` | Não |
| `PessoaFisica.povo_indigena` | `povo_indigena` | `ForeignKeyPlus('comum.PovoIndigena', null=True, on_delete=...)` | Não |
| `PessoaFisica.deficiencia` | `deficiencia` | `ForeignKeyPlus('rh.Deficiencia', null=True, on_delete=...)` | Não |

Os tipos/choices/`on_delete` espelham exatamente as definições de origem.

**Escopo PJ (decisão do usuário):** o backfill roda para **todos** os vínculos,
inclusive `PessoaJuridica`. Os 4 campos de `Pessoa` são copiados para vínculos PJ; os 4
campos de `PessoaFisica` não se aplicam a PJ e ficam null nesses vínculos (PJ não tem
`pessoafisica`).

## Migração

Uma migration em `comum/migrations/` (ex.: `0114_vinculo_campos_pessoa`):

1. **Schema:** `AddField` para os 7 campos escalares/FK + a M2M `setores_adicionais`
   (Django cria a through-table automaticamente).
2. **Data (`RunPython`):** backfill, iterando `Vinculo`:
   - Campos de `Pessoa` (todos os vínculos):
     - `email_pessoal   = vinculo.pessoa.email`
     - `email_notificacao = vinculo.pessoa.email_secundario`
     - `sistema_origem  = vinculo.pessoa.sistema_origem`
   - Campos de `PessoaFisica` (só quando existir): `pf = getattr(vinculo.pessoa, 'pessoafisica', None)`; se `pf`, copia `foto`, `raca_id`, `povo_indigena_id`, `deficiencia_id`.
   - M2M `setores_adicionais`: copia as linhas do through de `vinculo.pessoa.setores_adicionais`.
   - **Reverse:** limpa os 8 campos (escalares → valor vazio/null; M2M → `.clear()`). No-op seguro.
   - Usar `apps.get_model` (migration state), não import direto dos modelos.

## Detalhes técnicos a tratar no plano

1. **Colisão de `related_name`:** `Vinculo.setor` (FK) já gera o reverse `setor.vinculo_set`.
   A nova M2M `setores_adicionais` para `rh.Setor` precisa de um `related_name` próprio
   (ou `'+'`) para não colidir com esse reverse.
2. **`foto` com `use_id_for_name=True`:** o backfill copia a string do path, que continua
   apontando para o mesmo arquivo físico da `PessoaFisica` (leitura ok). Uploads futuros
   diretamente no `Vinculo` passariam a usar `vinculo.id`. Requer novos imports em
   `comum/models.py`: `ImageWithThumbsField` e `get_overwrite_storage` (mesma origem usada
   em `rh/models/pessoa/pessoa_fisica.py`).
3. **FKs cross-app:** sem nova dependência de app — `Vinculo` já referencia `rh.Pessoa` e
   `rh.Setor`. `raca`/`povo_indigena` são do próprio `comum`; `deficiencia` é `rh`.

## Teto assumido (deliberado)

`ponytail:` **sem dual-write.** Leitura e escrita continuam em `Pessoa`/`PessoaFisica`
como fonte da verdade. As cópias no `Vinculo` são um **snapshot** para o passo seguinte
(codemod) começar a ler/escrever do `Vinculo`. Se este passo permanecer semanas em produção
antes do codemod, as cópias podem ficar defasadas (stale) diante de edições em `Pessoa`.
Upgrade path: adicionar um signal `post_save` de sync `Pessoa`/`PessoaFisica` → `Vinculo`.
Não faz parte deste passo.

## Testes

Um `comum/tests/.../test_*.py` (pytest) que:

1. Cria uma `Pessoa`+`PessoaFisica` com um `Vinculo`, preenchendo os campos de origem
   (incluindo ≥1 setor adicional e FKs `raca`/`deficiencia`).
2. Cria uma `PessoaJuridica` com `Vinculo` (sem `pessoafisica`).
3. Roda o backfill.
4. Assere: os 8 campos copiados no vínculo da PF; os 4 campos de `Pessoa` copiados no
   vínculo da PJ; os 4 campos de `PessoaFisica` ficam null no vínculo da PJ; a M2M
   `setores_adicionais` reflete os setores da Pessoa.

## Fora de escopo deste passo

- `RemoveField` dos campos em `Pessoa`/`PessoaFisica`.
- `UNIQUE` em `documento_identificador`.
- Codemod libcst de call-sites (leitura/escrita passam a usar `Vinculo`).
- Signals de recálculo das flags `eh_*`.
- Deduplicação de PFs (antigo MR1).
- Dual-write / sync de consistência.
