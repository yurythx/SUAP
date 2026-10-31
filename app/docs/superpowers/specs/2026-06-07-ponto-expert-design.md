# Spec — Especialista de Ponto Eletrônico (`/suap:ponto-expert`)

- **Data:** 2026-06-07
- **Autor:** Fernando (via Claude Code + Superpowers)
- **Status:** Aprovado para implementação (writing-plans)
- **Módulo-alvo:** `ponto/` (SUAP) — área Gestão de Pessoas → Administração de Pessoal → Ponto

## 1. Objetivo

Criar uma skill "especialista" no padrão dos experts `suap:*` (ex.:
`progressao-docente-expert`) que domine o módulo de **Ponto Eletrônico** do SUAP,
para uso em **demandas, correções de erros e respostas a perguntas frequentes de
usuários**. Requisito central: **análise profunda do módulo E dos módulos
relacionados**, deixando claro **como um influencia o outro**.

## 2. Decisões de design (brainstorming)

| Eixo | Decisão |
|------|---------|
| **Profundidade** | Especialista **único** (`ponto-expert`) com **profundidade escalonada**: núcleo fundo + periféricos como referência enxuta. |
| **Cross-módulo** | **Mapa de influência focado**: pontos de integração concretos (FK, signal, webservice, task) e "como um influencia o outro", sem virar expert dos outros módulos. |
| **Packaging** | Canônico em `<repo>/.claude/commands/suap/ponto-expert.md` (comando de projeto → `/suap:ponto-expert`); symlink user-level opcional. |
| **Formato** | Markdown, termina com `$ARGUMENTS`, espelha professor-titular/progressao-docente. |
| **Método** | Leitura sistemática do código real; "(a confirmar no código)" onde não estiver claro. |

## 3. Contexto levantado (âncoras)

- **App:** `ponto` — `verbose_name='Ponto'`, `area='Gestão de Pessoas'`, `icon='hourglass-start'`.
- **Tamanho:** `models.py` 6810, `views.py` 3722, `forms.py` 3261, `compensacao.py` 3243, `admin.py` 1231 (≈18.8k linhas). `Frequencia` (model núcleo) ≈2.100 linhas.
- **Subdomínios (classes de model):** `Frequencia` (núcleo); REP/terminais (`VersaoTerminal`, `Maquina`, `MaquinaLog`, `Liberacao`); Abono (`AbonoChefia`, `SolicitacaoAbonoParcial`, `SolicitacaoAbonoParcialGravidez`, `SolicitacaoRevisaoAbonoChefia`, `Observacao`, `DocumentoAnexo`); Afastamento (`TipoAfastamento`, `Afastamento`); Compensação/Recesso (`HorarioCompensacao`, dezenas de `Recesso*`); Saldo/Débito externo (`SaldoExterno`, `DebitoExternoCadastro`, `DebitoExterno`).
- **Menu (usuário):** Afastamentos · Compensação de Horários (Saldos/Débitos Externos, Compensações Específicas, Informar/Informes) · Liberações · Observações · Abonos (chefia, revisões, abono parcial) · Relatórios (frequências por servidor/cargo/setor).
- **Depende de:** `rh` (servidores/horários/afastamentos SIAPE), `comum`, `djtools`.
- **Dependentes reversos (importam `ponto`):** `terminais` (REP), `pgd`/`pgd2` (teletrabalho), `pit_rit`, `ae`, `acompanhamentofuncional`, `chaves`, `auditoria`, `comum`.
- **Infra:** `webservice.py`, `tasks.py` (Celery), `signals.py`, `enums.py`, `exceptions.py`, `compensacao.py`, `features/` (BDD), `management/`, `fixtures/`.

## 4. Outline (15 seções, profundidade escalonada)

### Camada FUNDA
1. **Propósito e Contexto** — área/app config/atores + glossário (frequência, marcação, abono, compensação, recesso, débito, liberação).
2. **Estrutura de Arquivos** — árvore anotada.
3. **Frequência / Registro de ponto** — `Frequencia`: campos, status/constantes, cálculo de horas/saldo, marcações, métodos-chave.
4. **Abono / Homologação** — `AbonoChefia`, `SolicitacaoAbonoParcial(+Gravidez)`, `SolicitacaoRevisaoAbonoChefia`, `Observacao`, `DocumentoAnexo`.
5. **Motor de Estado** — máquinas de estado de Frequência, Abono de chefia, Solicitação de abono parcial e escolhas de Recesso: diagrama ASCII + tabela `Estado × Ação × Ator × Pré-condições × Transição` + matriz Ator×Ação.

### Camada de REFERÊNCIA (estruturada, enxuta)
6. **Compensação / Recesso** — `HorarioCompensacao`, modelos-chave `Recesso*` e os fluxos (informar compensação, opções escolhidas), sem esmiuçar cada classe.
7. **Afastamentos** — `TipoAfastamento`, `Afastamento` (+ relação com SIAPE).
8. **Saldo / Débito Externo** — `SaldoExterno`, `DebitoExterno(Cadastro)`.
9. **REP / Terminais & Webservice** — `Maquina`, `MaquinaLog`, `Liberacao`, `VersaoTerminal`, `webservice.py` (como as marcações entram).

### TRANSVERSAIS
10. **Mapa de Influência Cross-Módulo** ⭐ — tabela "Módulo ↔ Ponto" com **ponto de integração concreto** (FK/signal/webservice/task) e **direção da influência**: `rh`, `comum`, `terminais`, `pgd`/`pgd2`, e dependentes reversos (`pit_rit`, `ae`, `acompanhamentofuncional`, `auditoria`).
11. **RBAC** — papéis e permissões (`permissions.yaml`), incl. permissões custom.
12. **Tarefas Assíncronas** — `tasks.py`/Celery, `beat`, `signals.py` (gatilhos e efeitos).
13. **Regras de Negócio Críticas** — tolerância/jornada, banco de horas/compensação, prazos de homologação de abono, regras de recesso, débito.
14. **FAQ de Usuários** ⭐ — dúvidas comuns ancoradas no comportamento real (ex.: frequência inconsistente, como solicitar abono, marcação não apareceu, como compensar horas, isenção por PGD).
15. **Como Atuar como Especialista** — gatilhos de vocabulário, regras de ouro (respeitar motor de estado, usar verificações reais de permissão, ler antes de sugerir) + `$ARGUMENTS`.

## 5. Critérios de sucesso

- Arquivo em `<repo>/.claude/commands/suap/ponto-expert.md`, disponível como `/suap:ponto-expert`.
- 15 seções preenchidas a partir do código real.
- Seção 5 entrega diagrama + tabela Estado×Ação×Ator×Transição + matriz Ator×Ação para as entidades com ciclo de vida.
- Seção 10 (influência) lista pontos de integração **verificáveis** (FK/signal/webservice/task) por módulo relacionado.
- Seção 14 (FAQ) com respostas ancoradas em comportamento real (sem inventar).
- Termina com `$ARGUMENTS`.

## 6. Fora de escopo

- Documentar internamente, com profundidade, os módulos relacionados (apenas a interface/influência com o ponto).
- Alterações no código do `ponto` (o especialista é documentação/prompt).
- Testes do módulo.

## 7. Riscos / observações

- Módulo muito grande: priorizar fidelidade do núcleo; periféricos por esqueleto.
- O motor de estado pode envolver múltiplas entidades (Frequência, Abono, Abono parcial, Recesso) — manter tabelas separadas por entidade.
- Subdomínio Compensação/Recesso é extenso e entrelaçado; manter como referência e marcar "(a confirmar)" onde o fluxo não estiver claro.
