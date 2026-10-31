# Especialista de Ponto Eletrônico — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produzir o comando `/suap:ponto-expert` — documento markdown que faz uma sessão assumir o papel de especialista no módulo `ponto`, com 15 seções, profundidade escalonada, mapa de influência cross-módulo e FAQ de usuários.

**Architecture:** Documento markdown único versionado em `.claude/commands/suap/ponto-expert.md` (comando de projeto auto-descoberto). Conteúdo extraído por leitura sistemática do código real (núcleo linha-a-linha; periféricos por esqueleto). Espelha `professor-titular-expert.md`/`progressao-docente-expert.md`.

**Tech Stack:** Markdown; fontes em `ponto/` (Django/djtools). Sem código de aplicação — deliverable é prompt/documentação.

---

## Natureza do plano (leia antes de executar)

Deliverable é documentação extraída do código (não TDD de código). Adaptação:

- **"Teste" de cada task = verificação por evidência** (`grep`/`sed`) confirmando que os identificadores citados (classes, status, papéis, rotas, tasks, integrações) **existem no código**.
- **Nada inventado**: o que não estiver claro → escrever **"(a confirmar no código)"**.
- **pt-BR**; **um commit por task** na branch `feat/ponto-expert`.
- Os blocos de conteúdo são **gabaritos de estrutura**; a prosa é redigida na execução a partir das linhas-fonte indicadas.
- **Profundidade escalonada**: núcleo (§3 Frequência, §4 Abono, §5 Estado, §10 Influência, §14 FAQ) → leitura detalhada; periféricos (§6-9) → esqueleto (classes/campos/métodos-chave).

## Fatos confirmados (âncoras)

**App:** `ponto` — `verbose_name='Ponto'`, `area='Gestão de Pessoas'`, `icon='hourglass-start'`.

**Models (linhas em `models.py`):** `Frequencia`(55) · `VersaoTerminal`(2181) · `Maquina`(2188) · `MaquinaLog`(2257) · `Liberacao`(2288) · `Observacao`(2471) · `DocumentoAnexo`(2490) · `AbonoChefia`(2513) · `SolicitacaoAbonoParcial`(3051) · `SolicitacaoAbonoParcialGravidez`(3590) · `SolicitacaoRevisaoAbonoChefia`(3647) · `TipoAfastamento`(3711) · `Afastamento`(3730) · `HorarioCompensacao`(3814) · `Recesso*`(4199–5573) · `SaldoExterno`(5574) · `DebitoExternoCadastro`(6044) · `DebitoExterno`(6521) · `RelatorioPontoPessoaDiaInfo`(6623).

**Estados (não-linear):** Frequência classifica **inconsistências** (`INCONSISTENCIA_*` l.56-64) e resolve por **abono** (`SITUACAO_INCONSISTENCIA_*_ABONO` l.162-171) e **débito** (`SITUACAO_INCONSISTENCIA_*_DEBITO` l.173-185). Abono de chefia e abono parcial têm seus próprios ciclos (confirmar constantes em `AbonoChefia` l.2513 e `SolicitacaoAbonoParcial` l.3051).

**Papéis (`permissions.yaml`):** Aposentado, Auditor, Chefe de Setor, Coordenador PRONATEC(+Sistêmico), Coordenador de Gestão de Pessoas(+Sistêmico), Coordenador de TI campus/sistêmico, Gerenciador de Frequência de Terceirizados, Gerenciador de Prestador de Serviço, Prestador de Serviço, Servidor, Visualizador de Informações de Servidores, Cadastrador de Saldos e Débitos Externos.

**Async:** `tasks.py` (djtools `@task`: `relatorio_frequencia_cargo_emprego`, `relatorio_frequencia_setor`, …) · `signals.py` (`post_save` `AbonoChefia` → `processa_abono_chefia_salvo`).

**Depende de:** `rh`, `comum`, `djtools`. **Dependentes reversos:** `terminais`, `pgd`/`pgd2`, `pit_rit`, `ae`, `acompanhamentofuncional`, `chaves`, `auditoria`, `comum`.

**Referência de formato:** `~/.claude/commands/suap/progressao-docente-expert.md` (15→`$ARGUMENTS`).

---

## File Structure
- **Create:** `.claude/commands/suap/ponto-expert.md` — o documento (deliverable único).
- **Opcional (Task 9):** symlink `~/.claude/commands/suap/ponto-expert.md` → arquivo do repo.
- Código de `ponto/` é **somente leitura** (fonte).

---

## Task 1: Scaffold + §1-2 (Propósito/Contexto, Estrutura)
**Files:** Create `.claude/commands/suap/ponto-expert.md`; Read `ponto/apps.py`, `ponto/menu.yaml`, `ls ponto/`.
- [ ] **Step 1: Ler contexto** — `sed -n '1,20p' ponto/apps.py`; `grep -nE '^[^ ].*:$' ponto/menu.yaml | head -40`; `ls -1 ponto/`.
- [ ] **Step 2: Escrever cabeçalho + §1 (área/app config/atores/glossário) + §2 (árvore anotada).** Cabeçalho: `# Especialista no Módulo Ponto Eletrônico (SUAP)` + frase de assunção de papel. Glossário: frequência, marcação, abono (chefia/parcial), compensação, recesso, débito externo, liberação, REP.
- [ ] **Step 3: Verificar** — `grep -nE 'verbose_name|area|icon' ponto/apps.py` (confere §1).
- [ ] **Step 4: Commit** — `git add . && git commit -m "docs(ponto): expert - scaffold + secoes 1-2"`.

## Task 2: §3 Frequência / Registro (núcleo, detalhado)
**Files:** Modify o `.md`; Read `ponto/models.py:55-2180` (em blocos), `ponto/utils.py`, `ponto/enums.py`.
- [ ] **Step 1: Ler** — `sed -n '55,700p'`, `'700,1400p'`, `'1400,2180p' ponto/models.py`; `cat ponto/enums.py`.
- [ ] **Step 2: Escrever §3** — `Frequencia`: propósito; constantes de inconsistência (`INCONSISTENCIA_*`); situações de abono/débito (`SITUACAO_INCONSISTENCIA_*`); campos principais; cálculo de horas/jornada/saldo; marcações/registros; métodos-chave (assinatura + 1 linha). Resumir, não copiar corpo.
- [ ] **Step 3: Verificar** — `grep -nE 'INCONSISTENCIA_|SITUACAO_INCONSISTENCIA_' ponto/models.py | head` (todos os citados existem).
- [ ] **Step 4: Commit** — `"docs(ponto): expert - secao 3 (frequencia/registro)"`.

## Task 3: §4 Abono / Homologação (núcleo)
**Files:** Modify o `.md`; Read `ponto/models.py` 2471-3710.
- [ ] **Step 1: Ler** — `sed -n '2471,2513p'` (Observacao/DocumentoAnexo), `'2513,3051p'` (AbonoChefia), `'3051,3710p'` (SolicitacaoAbonoParcial(+Gravidez), SolicitacaoRevisaoAbonoChefia).
- [ ] **Step 2: Escrever §4** — cada model: campos, constantes de status/situação, métodos-chave (incl. `AbonoChefia.processa_abono_chefia_salvo`). Foco no fluxo de homologação (servidor solicita → chefia abona/revisa).
- [ ] **Step 3: Verificar** — `grep -nE '^class (AbonoChefia|SolicitacaoAbonoParcial|SolicitacaoAbonoParcialGravidez|SolicitacaoRevisaoAbonoChefia|Observacao|DocumentoAnexo)\b' ponto/models.py` (6 classes).
- [ ] **Step 4: Commit** — `"docs(ponto): expert - secao 4 (abono/homologacao)"`.

## Task 4: §5 Motor de Estado (ênfase)
**Files:** Modify o `.md`; Read transições em `ponto/models.py` (abono/frequência) + `ponto/views.py`/`forms.py` onde mudam situação.
- [ ] **Step 1: Mapear** — `grep -nE 'situacao *=|status *=|\.abonar|homolog|processa_abono|def pode_' ponto/models.py ponto/views.py | head -50`.
- [ ] **Step 2: Escrever §5** — três blocos (cada entidade com ciclo próprio): **5.1 Frequência** (classificação de inconsistência → resolução por abono/débito; NÃO é FSM linear — documentar como matriz de situações), **5.2 AbonoChefia** (solicitado→abonado/revisado), **5.3 SolicitacaoAbonoParcial** (solicitar→deferir/indeferir). Para cada: diagrama ASCII + tabela `Estado/Situação × Ação × Ator × Pré-condições × Resultado`. Encerrar com **matriz Ator×Ação** (Servidor, Chefe de Setor, Coord. GP, Auditor). Citar evidência (linha). "(a confirmar)" onde não claro.
- [ ] **Step 3: Verificar** — `sed -n '162,185p' ponto/models.py` (situações citadas existem); estados de abono conferem com §4.
- [ ] **Step 4: Commit** — `"docs(ponto): expert - secao 5 (motor de estado)"`.

## Task 5: §6 Compensação/Recesso + §7 Afastamentos (referência)
**Files:** Modify o `.md`; Read `ponto/models.py` 3711-3814 e 3814-5573 (esqueleto), `ponto/compensacao.py` (cabeçalhos).
- [ ] **Step 1: Ler esqueleto** — `grep -nE '^class |^    def |^    [a-z_]+ = ' ponto/models.py | sed -n '/3711/,/5573/p'` (ajustar); `grep -nE '^class |^def |^    def ' ponto/compensacao.py | head -40`.
- [ ] **Step 2: Escrever §6 (Compensação/Recesso)** — `HorarioCompensacao` + famílias `Recesso*` (agrupar: opção, período, dia, escolha) + papel de `compensacao.py`. Enxuto: o que é, como se relaciona com Frequência/saldo. §7 (Afastamentos): `TipoAfastamento`, `Afastamento` + relação SIAPE.
- [ ] **Step 3: Verificar** — `grep -cE '^class Recesso' ponto/models.py` (nº famílias citado bate ou marcado "(a confirmar)").
- [ ] **Step 4: Commit** — `"docs(ponto): expert - secoes 6-7 (compensacao/recesso, afastamentos)"`.

## Task 6: §8 Saldo/Débito Externo + §9 REP/Terminais & Webservice (referência)
**Files:** Modify o `.md`; Read `ponto/models.py` 5574-6622 (esqueleto) e 2181-2470, `ponto/webservice.py`.
- [ ] **Step 1: Ler** — `sed -n '5574,6622p' ponto/models.py` (esqueleto via grep); `sed -n '2181,2470p' ponto/models.py`; `cat ponto/webservice.py`.
- [ ] **Step 2: Escrever §8** (`SaldoExterno`, `DebitoExternoCadastro`, `DebitoExterno` — o que são, como afetam o saldo do servidor) e **§9** (`VersaoTerminal`, `Maquina`, `MaquinaLog`, `Liberacao` + `webservice.py`: como as marcações dos REP entram no sistema).
- [ ] **Step 3: Verificar** — `grep -nE '^class (SaldoExterno|DebitoExterno|DebitoExternoCadastro|Maquina|MaquinaLog|Liberacao|VersaoTerminal)\b' ponto/models.py`.
- [ ] **Step 4: Commit** — `"docs(ponto): expert - secoes 8-9 (saldo/debito, rep/terminais)"`.

## Task 7: §10 Mapa de Influência Cross-Módulo (ênfase)
**Files:** Modify o `.md`; Read imports de `ponto` + dependentes reversos.
- [ ] **Step 1: Mapear integrações** — `grep -rhnE 'from (rh|comum|terminais|pgd|pgd2|pit_rit)\b' ponto/*.py | sort -u | head -40`; `grep -rlE 'from ponto[ .]|import ponto\b' --include='*.py' . | grep -v '^ponto/' | sed -E 's|/.*||' | sort -u`; `grep -nE 'ForeignKey|OneToOne|ManyToMany' ponto/models.py | grep -E 'rh\.|comum\.' | head`.
- [ ] **Step 2: Escrever §10** — tabela `| Módulo | Direção | Ponto de integração (FK/signal/webservice/task) | Como influencia o ponto |` para: `rh` (Servidor/horários/afastamentos SIAPE), `comum`, `terminais` (REP/coleta de marcações), `pgd`/`pgd2` (teletrabalho/isenção de ponto), e dependentes reversos (`pit_rit`, `ae`, `acompanhamentofuncional`, `auditoria`). Cada linha cita a evidência.
- [ ] **Step 3: Verificar** — cada módulo citado aparece nos imports/reverse-deps da Step 1; sem módulo inventado.
- [ ] **Step 4: Commit** — `"docs(ponto): expert - secao 10 (mapa de influencia cross-modulo)"`.

## Task 8: §11 RBAC + §12 Async + §13 Regras de Negócio
**Files:** Modify o `.md`; Read `ponto/permissions.yaml`, `ponto/tasks.py`, `ponto/signals.py`, `ponto/beat.py`(se existir), constantes de regra em `models.py`.
- [ ] **Step 1: Ler** — `cat ponto/permissions.yaml`; `cat ponto/tasks.py ponto/signals.py`; `ls ponto/beat.py 2>/dev/null && cat ponto/beat.py`.
- [ ] **Step 2: Escrever §11** (tabela Papel × Capacidades dos 14 papéis), **§12** (jobs `@task`, signals `post_save AbonoChefia`), **§13** (tolerância/jornada, banco de horas/compensação, prazos de homologação, recesso, débito).
- [ ] **Step 3: Verificar** — `grep -cE '^[A-Za-zÀ-ÿ].*:$' ponto/permissions.yaml` (nº papéis); `grep -nE '@task|receiver|post_save' ponto/tasks.py ponto/signals.py`.
- [ ] **Step 4: Commit** — `"docs(ponto): expert - secoes 11-13 (rbac/async/regras)"`.

## Task 9: §14 FAQ de Usuários + §15 Como Atuar + finalização
**Files:** Modify o `.md`; (opcional) symlink user-level.
- [ ] **Step 1: Escrever §14 (FAQ)** — perguntas frequentes ancoradas no comportamento real: "por que minha frequência está inconsistente?" (tipos `INCONSISTENCIA_*`), "como abonar/solicitar abono?" (fluxo §4), "minha marcação não apareceu" (REP/webservice §9), "como compensar horas / débito?" (§6/§8), "fui isento de ponto pelo PGD?" (§10). Cada resposta referencia a seção/código.
- [ ] **Step 2: Escrever §15 (Como Atuar)** — gatilhos de vocabulário (frequência, marcação, abono, compensação, recesso, débito, REP, terminal, homologação), regras de ouro (respeitar motor de estado §5, usar verificações reais de permissão, ler antes de sugerir). Terminar o arquivo **exatamente** com a linha `$ARGUMENTS`.
- [ ] **Step 3: Validação final** — `tail -n 1 .claude/commands/suap/ponto-expert.md` == `$ARGUMENTS`; `grep -cE '^## ' .claude/commands/suap/ponto-expert.md` >= 15; listar `(a confirmar no código)` para revisão.
- [ ] **Step 4: (Opcional) Symlink** — `ln -sf "$(pwd)/.claude/commands/suap/ponto-expert.md" ~/.claude/commands/suap/ponto-expert.md`.
- [ ] **Step 5: Commit** — `"docs(ponto): expert - secoes 14-15 + finalizacao"`.

---

## Self-Review (preencher na execução)
1. **Cobertura do spec:** §1-2→T1, §3→T2, §4→T3, §5→T4, §6-7→T5, §8-9→T6, §10→T7, §11-13→T8, §14-15→T9. ✓
2. **Placeholders:** sem TBD/TODO; "(a confirmar no código)" aceitável e listado.
3. **Consistência:** estados de §5 == constantes reais (`INCONSISTENCIA_*`/`SITUACAO_INCONSISTENCIA_*`/abono); papéis §11 == permissions.yaml; módulos §10 == imports/reverse-deps.
4. **Critérios do spec atendidos:** caminho, `/suap:ponto-expert`, termina com `$ARGUMENTS`.
