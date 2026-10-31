# Máquinas de estado do fluxo de monitoramento (auditoria)

Spec das transições das três máquinas FSM (`django_fsm`, `FSMIntegerField(protected=True)`)
que governam o fluxo de monitoramento, e do acoplamento entre elas. Objetivo: revisar
deadlocks (estado de onde não se sai por um evento esperado).

> **Acoplamento.** As três máquinas não transicionam isoladas:
> - `Posicionamento.handle_post_transition` (`models/posicionamento.py`) dispara, por
>   *string* (`getattr(monitoramento, nome)()`), transições do **Monitoramento** conforme
>   o **status do próprio posicionamento** (dicts `actions` em `handle_atendimento` /
>   `handle_reiterar` / `handle_finalizar` / `handle_cancelar`) e publica a **Manifestação**
>   (`notify_manifestacao`), que por sua vez move a **Solicitação**.
> - `Manifestacao.publicar` (`models/manifestacao.py:336`) move a **Solicitação**:
>   `reabrir=True` → `reabrir_para_ciencia`; `reabrir=False` → `finalizar`.
> - `Recomendacao.handle_status_monitoramentos` (`models/recomendacao.py:501`) agrega o
>   status dos seus **Monitoramentos** e dispara as transições da **Recomendação**.
> - `ProrrogacaoPrazo.save` (`models/prazo.py`) publica a manifestação no deferimento.

---

## 1. SolicitacaoProvidencia (`models/providencia.py`)

Estados (`SolicitacaoProvidenciaStatus`): `ESPERANDO=1`, `CIENTE=2`, `CANCELADA=3`,
`EXPIRADA=4`, `FINALIZAR=5`, `AGUARDANDO_POSICIONAMENTO=6`.

| Transição | Origem → Destino | Disparada por |
|---|---|---|
| `informar_ciencia` | ESPERANDO → CIENTE | `notificar_acesso` (gestor/chefe acessa a solicitação/monitoramento) |
| `aguardar_posicionamento` | CIENTE → AGUARDANDO_POSICIONAMENTO | `Manifestacao.enviar` (gestor envia manifestação) |
| `reabrir_para_ciencia` | AGUARDANDO_POSICIONAMENTO → CIENTE | `Manifestacao.publicar(reabrir=True)` (posicionamento de atendimento parcial/reiteração/revisão/**rejeição**); view `remover_manifestacao` |
| `finalizar` | {CIENTE, AGUARDANDO_POSICIONAMENTO, EXPIRADA} → FINALIZAR | `Manifestacao.publicar(reabrir=False)` (atendimento/finalização/cancelamento); form de benefício |
| `expirar` | {ESPERANDO, CIENTE} → EXPIRADA | cron (`tasks.py`) + `atualizar_solicitacao` (prazo vencido). **Guard:** `pode_expirar = not aguardando_posicionamento` |
| `cancelar` | {ESPERANDO, CIENTE, EXPIRADA} → CANCELADA | `Monitoramento.cancelar` (quando `solicitacao.ativa`) |

Terminais: `CANCELADA`, `FINALIZAR`. Reentrante para o ciclo: `reabrir_para_ciencia`
devolve a CIENTE (a mesma solicitação é reusada na reiteração/rejeição).

---

## 2. Monitoramento (`models/monitoramento.py`)

Estados (`MonitoramentoStatus`): `REGISTRADO=0`, `EM_MONITORAMENTO=1`, `AGUARDANDO_REVISAO=2`,
`EM_REVISAO=3`, `REVISADO=4`, `CONCLUIDO=5`, `FINALIZADO=6`, `CANCELADO=7`.

| Transição | Origem → Destino | Disparada por |
|---|---|---|
| `iniciar_monitoramento` | REGISTRADO → EM_MONITORAMENTO | `MonitorarRecomendacaoForm._processar_unidade` |
| `reiniciar` | CANCELADO → EM_MONITORAMENTO | `Recomendacao.reiniciar_monitoramento` (sobre cancelados) |
| `solicitar_revisao` | EM_MONITORAMENTO → AGUARDANDO_REVISAO | handler, quando o posicionamento está `REVISAO_PENDENTE` (`actions['esperando_revisao']`) |
| `revisar` | AGUARDANDO_REVISAO → EM_REVISAO | handler, quando o posicionamento está `EM_REVISAO` (`actions['em_revisao']`) |
| `concluir_revisao` | EM_REVISAO → REVISADO | handler, quando o posicionamento está `REVISADO` (`actions['revisado']`) |
| `reiterar` | {EM_MONITORAMENTO, REVISADO} → EM_MONITORAMENTO | `handle_reiterar` (posicionamento PUBLICADO, tipos RT/RV/**RS**) |
| `concluir` | {EM_MONITORAMENTO, REVISADO} → CONCLUIDO | `handle_atendimento` (posicionamento PUBLICADO, tipo AT) |
| `finalizar` | EM_MONITORAMENTO → FINALIZADO | `handle_finalizar` (posicionamento PUBLICADO, tipo FM); view de benefícios |
| `cancelar` | `*` → CANCELADO | `Monitoramento.cancelar`: `handle_cancelar` (tipo CN), `Recomendacao.cancelar_monitoramentos`, view de cancelamento |

Terminais: `CONCLUIDO`, `FINALIZADO`, `CANCELADO`. As sub-fases de revisão
(`AGUARDANDO_REVISAO`/`EM_REVISAO`/`REVISADO`) andam em *lockstep* com o workflow de
revisão do **Posicionamento** (`REVISAO_PENDENTE→EM_REVISAO→REVISADO→PUBLICADO`).

---

## 3. Recomendacao (`models/recomendacao.py`, mixin `RecomendacaoStatusMixin`)

Estados (`RecomendacaoStatus`): `REGISTRADA=0`, `EM_MONITORAMENTO=1`, `PARCIALMENTE_ATENDIDA=2`,
`ATENDIDA=3`, `NAO_ATENDIDA=4`, `CANCELADA=5`, `EXPIRADA=6`, `CONSOLIDADA=7`.

| Transição | Origem → Destino | Disparada por |
|---|---|---|
| `registar` | {REGISTRADA, EXPIRADA} → REGISTRADA | `_tratar_renovacao_prazo` (nova data-limite após expiração) |
| `iniciar_monitoramento` | {REGISTRADA, EM_MONITORAMENTO} → EM_MONITORAMENTO | `handle_status_monitoramentos` (algum monitoramento iniciado) |
| `reiniciar_monitoramento` | {EXPIRADA, CANCELADA} → EM_MONITORAMENTO | view `reiniciar_monitoramento`; `_tratar_renovacao_prazo` |
| `marcar_como_parcialmente_atentida` | EM_MONITORAMENTO → PARCIALMENTE_ATENDIDA | `handle_status_monitoramentos` (há concluídos, ainda há em monitoramento) |
| `marcar_como_atendida` | {EM_MONITORAMENTO, PARCIALMENTE_ATENDIDA} → ATENDIDA | `handle_status_monitoramentos` (concluídos+cancelados == total) |
| `marcar_como_nao_atendida` | **EM_MONITORAMENTO** → NAO_ATENDIDA | `handle_status_monitoramentos` (0 em monitoramento, há finalizados/não-atendidos) |
| `consolidar` | {REGISTRADA, EM_MONITORAMENTO} → CONSOLIDADA | view de consolidação |
| `cancelar` | {REGISTRADA, EM_MONITORAMENTO} → CANCELADA | view de cancelamento; `handle_status_monitoramentos` (todos cancelados) |
| `expirar` | {REGISTRADA, EM_MONITORAMENTO, PARCIALMENTE_ATENDIDA, EXPIRADA} → EXPIRADA | `verificar_expiracao` → `_tratar_expiracao` (data-limite vencida) |

Terminais "ativos": `ATENDIDA`, `NAO_ATENDIDA`. Inativos: `CANCELADA`, `EXPIRADA`,
`CONSOLIDADA` (EXPIRADA/CANCELADA são reversíveis por `reiniciar_monitoramento`).

---

## 4. Candidatos a deadlock / anomalia (para revisar)

### 4.0 — `REJEITAR_SOLICITACAO` sem handler — **CORRIGIDO**
Publicar posicionamento de Rejeição (RS) não tinha handler em `tipo_handlers`, então a
manifestação ficava RECEBIDA e a solicitação presa em AGUARDANDO_POSICIONAMENTO. Corrigido
mapeando `RS → handle_reiterar` (reabre para ciência). Cobertura: `tests/test_fluxo_rejeicao.py`.

### 4.1 — Cancelar monitoramento com solicitação em AGUARDANDO_POSICIONAMENTO → exceção — **CORRIGIDO**
`SolicitacaoProvidencia.cancelar` aceitava origem `{ESPERANDO, CIENTE, EXPIRADA}` — **não**
incluía `AGUARDANDO_POSICIONAMENTO`. Mas `Monitoramento.cancelar` chama
`self.ultima_solicitacao.cancelar(...)` sempre que `solicitacao.ativa`, e `ativa` **inclui**
AGUARDANDO_POSICIONAMENTO (`providencia.py:130`). Cancelar um monitoramento cuja solicitação
aguardava posicionamento disparava `TransitionNotAllowed` (mitigado só na borda pelos
`pode_cancelar`, mas frágil no FSM). **Correção:** incluído `STATUS_AGUARDANDO_POSICIONAMENTO`
na origem de `cancelar`. Cobertura: `tests/test_deadlocks_maquina_estado.py`.

### 4.2 — `marcar_como_nao_atendida` a partir de PARCIALMENTE_ATENDIDA → exceção — **CORRIGIDO**
`Recomendacao.marcar_como_nao_atendida` tinha origem **somente** `EM_MONITORAMENTO`. Mas
`handle_status_monitoramentos` a chama no ramo `(self.em_monitoramento or
self.parcialmente_atendida) and em_monitoramento == 0 and nao_atendidos > 0`
(`recomendacao.py:515`). Recomendação em PARCIALMENTE_ATENDIDA (houve concluídos) cujos
monitoramentos restantes viram FINALIZADO disparava `marcar_como_nao_atendida` a partir de
PARCIALMENTE_ATENDIDA → `TransitionNotAllowed`, quebrando o `save`. **Correção:** origem
ampliada para `{EM_MONITORAMENTO, PARCIALMENTE_ATENDIDA}` (espelhando `marcar_como_atendida`).
Cobertura: `tests/test_deadlocks_maquina_estado.py`.

### 4.3 — Remover revisão em andamento trava o monitoramento em EM_REVISAO — **CORRIGIDO**
A view `remover_revisao_posicionamento` só fazia `revisao.delete()`, sem reverter o
posicionamento. Com a revisão removida, o `Posicionamento` ficava em `EM_REVISAO` e **não havia
como adicionar nova revisão** (`pode_revisar` exige `REVISAO_PENDENTE`, e não existia transição
de volta), travando o `Monitoramento` em `EM_REVISAO` (resgatável só por `cancelar`, origem `*`).
**Correção (reverter para revisão pendente):**
- nova transição `Posicionamento.reabrir_revisao` (`EM_REVISAO → REVISAO_PENDENTE`);
- origem de `Monitoramento.solicitar_revisao` ampliada para `{EM_MONITORAMENTO, EM_REVISAO}`, de
  modo que o handler ressincronize o monitoramento para `AGUARDANDO_REVISAO`;
- `RevisaoPosicionamento.delete`: se não resta revisão e o posicionamento está em revisão, chama
  `reabrir_revisao`. Assim uma nova revisão pode ser registrada.
Dados legados (posicionamentos já travados em EM_REVISAO sem revisão): comando
`corrigir_revisoes_travadas` (dry-run por padrão, `--apply` efetiva).
Cobertura: `tests/test_deadlocks_maquina_estado.py`.
> Nota: os estados de **supervisão** do posicionamento (`SUPERVISAO_PENDENTE/EM_SUPERREVISAO/
> SUPERVISIONADO`) são **código morto** (`solicitar/colocar_em/concluir_supervisao` sem
> chamadores) — não entram no fluxo, logo não são fonte de deadlock.

### 4.4 — `PRORROGA_PRAZO` (PP) sem handler em `tipo_handlers` — não-deadlock (esclarecido)
PP não está em `tipo_handlers`, mas **não é alcançável como deadlock**: PP só é escolhível para
manifestação de prorrogação, que o `PosicionamentoFormFactory` roteia para o
`ProrrogacaoPosicionamentoForm`, e esse form **publica na hora** (`form.save` → `publicar`), com a
manifestação avançada por `ProrrogacaoPrazo.save` (no deferimento) ou pelo handler de RS (no
indeferimento). Não há caminho que publique PP fora desse form. Permanece como acoplamento frágil
(documentado), não como bug.
