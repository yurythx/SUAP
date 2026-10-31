# Inventário de call-sites — mover 8 campos de Pessoa/PessoaFisica → Vinculo

Data: 2026-07-02. Levantado por fan-out de subagentes (fuzzy, revisar antes de agir).
Fatias detalhadas (file:line, read/write, fonte-de-vínculo): `inv-*.md` neste diretório.

## Total consolidado

| Categoria | Sites reais | AMBIGUOUS (só pessoa/pf, sem papel/user) |
|---|---|---|
| Atributo `.py` — email | 68 | 16 |
| Atributo `.py` — email_secundario | 116 | 25 |
| Atributo `.py` — foto (55 via `get_foto_*_url`) | 82 | 11 |
| Atributo `.py` — raca/setores_adicionais/sistema_origem/povo_indigena | 36 | 6 |
| Atributo `.py` — **deficiencia** | **0** | 0 |
| ORM-traversal `.py` (`pessoa_fisica__campo` em filter/values/annotate) | 53 | — |
| Templates `.html` (todos os campos) | 299 | 110 |
| **TOTAL** | **≈654** | **≈168+** |

- **WRITE sites** (atribuição/`.set/.add`): ≈40 no `.py` (email_secundario 20 é o maior); templates quase só READ (widgets de form pontuais).
- **deficiencia**: nenhum call-site real — só RemoveField após backfill.

## Achados que mudam a estratégia

1. **Chokepoints de proxy (colapsam muitos sites de papel):**
   - `AbstractFuncionario.__getattr__`/`__getattribute__` (rh) delega `servidor.email`/`servidor.foto` → `pessoa_fisica`. `servidor` É papel e tem `get_vinculo()`, então atualizar o proxy p/ rotear a `self.get_vinculo().<campo>` conserta dezenas de sites SEM edição por-site (e respeita a regra "vínculo via papel").
   - Provável proxy análogo em edu (`Aluno`/`Professor` não têm `foto` próprio → resolvem via pessoa_fisica).
   - `User.get_profile()` retorna PessoaFisica; `User.get_vinculo()` existe → sites `user.get_profile().campo` podem virar `user.get_vinculo().campo`.
2. **Métodos helper de foto:** a maioria dos acessos a foto passa por `get_foto_75x100_url()`/`get_foto_150x200_url()` (métodos hoje na PessoaFisica). Mover foto p/ Vinculo exige recriar esses métodos no `Vinculo` (e/ou `get_email`), e rotear via `<papel/user>.get_vinculo()`.
3. **ORM-traversals (53)** são categoria à parte: `filter(pessoa_fisica__email=x)` vira join via Vinculo — reescrita de query, não de atributo; algumas podem não ter tradução limpa.
4. **Templates falham em silêncio (299 sites, 110 ambíguos):** após RemoveField, `{{ pessoa.email }}` esquecido renderiza vazio, sem erro. É o maior foco de risco e o menos automatizável/verificável.

## Decisões em aberto (bloqueiam o plano)

- **Política p/ sites AMBIGUOUS (≈168):** têm só `pessoa`/`pessoa_fisica` em escopo, sem papel/user. Opções: (a) refactor threading o papel/user até o site; (b) um accessor explícito de "vínculo da pessoa" com critério definido (contradiz parcialmente a regra); (c) caso a caso.
- **Escopo do MR:** ≈654 sites + 299 templates de risco silencioso não cabem num MR atômico revisável. Mesmo numa branch só, precisa ser fatiado por campo/app com testes.

## Confiabilidade

Números são limite superior fuzzy (classificação por heurística de subagente). Antes de reescrever qualquer fatia, revalidar os sites daquele campo contra as tabelas `inv-*.md`.
