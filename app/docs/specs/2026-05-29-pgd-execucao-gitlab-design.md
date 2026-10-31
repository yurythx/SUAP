# Design — Lançamento automático de execuções do PGD a partir de issues/MRs do GitLab

- **Data:** 2026-05-29
- **Revisão:** 2026-06-01 — desenho enxuto: removido o model intermediário `RascunhoExecucaoGitLab`;
  o RIT é criado direto no seu estado de rascunho nativo (`EM_CADASTRO_RIT`). Ver "Histórico de revisão".
- **Status:** Aprovado (brainstorming + análise do backend) — pronto para plano de implementação
- **Módulo alvo:** `pgd2/` (o `pgd/` está deprecated)

## Problema

O trabalho real chega como issues no GitLab. Cada trabalho concluído deveria, conforme o tema,
ser lançado no PGD do SUAP como execução de uma entrega que o gestor planejou para o servidor.
Hoje esse lançamento é manual (form `cadastrar_entrega_rit`) e custoso, então deixa de ser feito
com regularidade. Queremos automatizar o lançamento mantendo o servidor no controle do que entra
no seu PGD.

## Mapeamento de domínio (pgd2)

A "entrega que o gestor planejou para você" e a "execução" são, respectivamente:

- **Entrega planejada:** `pgd2.models.PlanoIndividualTrabalhoEntregas` (`models.py:8576`).
- **Execução (o que vamos lançar):** `pgd2.models.RelatorioIndividualTrabalho` — RIT (`models.py:8828`),
  com FK `entrega_pit → PlanoIndividualTrabalhoEntregas` (`editable=False, null=True`).

Cadeia do dono:
`rh.Servidor → SolicitacaoAdesaoServidor (adesao) → PlanoIndividualTrabalho (PIT) → PlanoIndividualTrabalhoEntregas → RelatorioIndividualTrabalho (RIT)`.

Campos do RIT que vamos preencher: `titulo`, `descricao`, `data_inicio`, `data_fim`,
`tempo_executado` (horas), `perc_executada_em_teletrabalho`, `tempo_executada_em_teletrabalho`
(derivado, `editable=False`), `quantidade_progresso`, `anexo` (fora do 1º corte).

### A entrega do PIT é uma categoria de trabalho, descrita na Entrega PES

Cada `PlanoIndividualTrabalhoEntregas` é uma **categoria de trabalho com horas planejadas** (ex.:
*Demandas de desenvolvimento de sistemas* 40h, *Atendimento de erros e chamados* 50h, *Revisão de
Código* 20h). O significado de cada categoria **não está no `descricao` do PIT** (que é magro), e sim
na **Entrega PES vinculada** — `PlanoIndividualTrabalhoEntregas.entrega_pes →
PlanoEntregasSetorialEntregas` (`models.py:2347`), que carrega:

- `titulo` — ex.: *Atendimento de erros e chamados*
- `descricao` — o que a categoria absorve (SLA, prazos, etc.)
- `criterios_avaliacao` (`models.py:2367`) — faixas Excelente/Bom/Normal/Insuficiente
- `metrica` ∈ {`PERCENTUAL`, `QUANTIDADE`} + `meta` (`models.py:2358`) — como a execução é medida

**Implicação para a inferência:** mapear issue → entrega é **casar o conteúdo da issue/MR contra a
descrição + critérios da Entrega PES de cada categoria** (não há "balde sem descrição"; toda categoria
é descrita). Um bug → *Atendimento de erros e chamados*; uma feature → *Demandas de desenvolvimento*;
um review → *Revisão de Código*. As horas executadas acumulam **por categoria** ao longo do mês.

**Granularidade: uma RIT por MR (decisão).** O motor já agrega **vários RITs por entrega**:
`calcular_pit_execucao` (`models.py:5752`) faz `tempo_executado = Sum(rits.tempo_executado)` e
`qtd_executado = Sum(rits.quantidade_progresso)` por categoria. Logo, em vez de empilhar todas as issues
do mês num único RIT (hábito manual, motivado só pelo tédio de cadastrar um a um), **cada MR vira sua
própria RIT** — o que encaixa na chave `(projeto, MR)` já adotada (idempotência) e dá rastreabilidade
1:1. O total da categoria (horas e quantidade) emerge da soma. Como o lançamento é automático, o tédio
que justificava o lump deixa de existir.

**`quantidade_progresso = 1` sempre (decisão).** Um MR = um trabalho, então cada RIT lança `1`,
independentemente da `metrica` da entrega — sem ramificação por métrica no serviço/skill. O total da
categoria (`qtd_executado`) sai da soma dos RITs (`models.py:5758`). **Entregas `PERCENTUAL`:** a soma
pode ultrapassar 100% e **isso é aceitável** — o SUAP contabiliza o excedente como horas extras; não há
tratamento especial a fazer. (O form manual valida `<= 100` por RIT individual, `forms.py:1664`; como
lançamos `1`, nunca esbarramos nesse limite por RIT.)

### O RIT já tem estado de rascunho nativo (descoberta-chave da revisão)

O ciclo de vida do RIT é controlado por `PlanoIndividualTrabalho.situacao_rit`:

```
EM_CADASTRO_RIT  →  AGUARDANDO_PARECER_RIT  →  HOMOLOGADO_RIT
   (editável)        (servidor enviou o mês)     (chefe validou)
```

Enquanto `situacao_rit == EM_CADASTRO_RIT` (`models.py:4071`), o servidor **cria, edita e remove RITs
livremente** (`pode_editar_entrega_rit`, `models.py:8862`; remoção em `remover_entrega_rit`,
`views.py:3752`). O ato de **enviar o RIT do mês** (solicitar parecer) é a confirmação do servidor; a
**homologação do chefe** é a validação final.

Ou seja: **`EM_CADASTRO_RIT` já é o "rascunho"** e o **envio mensal do RIT é a validação que o servidor
já é obrigado a fazer**. Não precisamos de um model paralelo de rascunho com máquina de estados própria —
basta criar o RIT direto nesse estado e deixá-lo editável até o servidor enviar o mês.

Lançamento manual atual: view `cadastrar_entrega_rit(request, entrega_pit_id)` (`views.py:3711`) +
form `RelatorioIndividualTrabalhoCadastrarForm` (`forms.py:1664`), com guarda
`pit.pode_cadastrar_entrega_rit(...)` (`models.py:6451`) e validação de período. O serviço novo reusa
exatamente esse caminho.

Não existe API django-ninja *inbound* para o pgd2 (os `api_pgd2*.py` são integração *outbound* com a
API externa do governo). Qualquer caminho exige construir endpoint/serviço novo.

## Decisões de design

| Decisão | Escolha | Razão |
|---|---|---|
| Como mapear issue → entrega planejada | **Claude casa o conteúdo da issue contra a descrição + critérios da Entrega PES de cada categoria**, com confirmação do servidor | O significado da entrega vive na Entrega PES; servidor confirma antes de gravar |
| Granularidade do RIT | **Uma RIT por MR** (não empilhar tudo num RIT) | `calcular_pit_execucao` soma `tempo_executado`/`quantidade_progresso` de vários RITs; encaixa na chave `(projeto, MR)`; rastreabilidade 1:1; automação remove o tédio que justificava o lump |
| Quando a issue não casa com nenhuma categoria | **Avisa e não grava** | Servidor escolhe manual; sem RIT errado |
| Origem das horas (`tempo_executado`) | **Claude estima a partir do trabalho** (diff/commits), servidor confirma | Não há fonte confiável de horas numa issue/PR |
| Onde fica o estado de rascunho | **No próprio RIT, em `EM_CADASTRO_RIT`** (sem model intermediário) | O domínio já oferece um estado editável; mirror-model seria duplicação |
| Qual é a validação | **O envio mensal do RIT pelo servidor → homologação do chefe** (fluxo nativo) | O servidor já é obrigado a revisar e enviar o RIT do mês |
| Momento da gravação | **Cria o RIT na confirmação do PR**, em `EM_CADASTRO_RIT` | Contexto fresco com o servidor no loop; fica editável até o envio do mês; merge não precisa recriar |
| Qual PIT recebe o RIT | **Todos os PITs abertos são candidatos**; default é o corrente, label de mês/ano da issue escolhe outro | Equipe organiza issues com label `mes/ano`; permite lançar em mês não-corrente sem travar |
| Atualização do mesmo MR | **Upsert** (re-run atualiza o RIT existente) | Idempotência simples; servidor edita livremente e re-run regrava (trade-off aceito) |
| Idempotência / rastreabilidade | **2 campos no RIT** (`gitlab_project_id`, `gitlab_mr_iid`) + unique parcial | `get_or_create` por `(projeto, MR)`; liga RIT ↔ MR sem model extra |
| Reestimação no merge se o diff cresceu | **Fora do 1º corte** | O servidor ajusta as horas na revisão de fim de mês; reintroduzível sem mudar schema |
| Escopo | **Toda a equipe de desenvolvimento** | Feature do SUAP, não script pessoal |
| Arquitetura | **A — SUAP como fonte da verdade** | Reusa plumbing MCP/ninja existente; estado auditável e consultável no SUAP |

## Arquitetura (Abordagem A, enxuta)

Fronteiras de responsabilidade:

- **SUAP** é dono do estado e das regras (campos de proveniência no RIT + serviço + endpoints).
- **Claude** é dono de inferir e estimar (fase PR).
- **CI** é orquestração leve (opcional no 1º corte): comentário de confirmação e limpeza de RIT órfão.

### Componentes

**1. Campos de proveniência no `RelatorioIndividualTrabalho` (novo)**

Dois campos nullable, `editable=False`, no model existente (`models.py:8828`):

- `gitlab_project_id` (`PositiveIntegerFieldPlus`, null/blank)
- `gitlab_mr_iid` (`PositiveIntegerFieldPlus`, null/blank)

Restrição de unicidade **parcial** — `UniqueConstraint(fields=['gitlab_project_id', 'gitlab_mr_iid'],
condition=Q(gitlab_mr_iid__isnull=False), name='uniq_rit_gitlab_mr')` — para não colidir com os
milhares de RITs manuais (ambos NULL). Permite `get_or_create` idempotente por `(projeto, MR)`.

Sem máquina de estados, sem campos espelhados: o estado é o `situacao_rit` do PIT; o conteúdo é o
próprio RIT.

**2. Serviço `pgd2/services.py`**

- `resolver_servidor_por_gitlab_username(username)` → `rh.Servidor` (reusa
  `demandas.AnalistaDesenvolvedor.username_gitlab`; erro tratado se não mapeado).
- `get_entregas_disponiveis_para_servidor(servidor)` → entregas `homologado=True, cancelado=False`
  de **todos os PITs abertos** do servidor em que `pode_cadastrar_entrega_rit(valida_apenas_o_basico=True)`
  permite (insumo da inferência). Cada entrega vem com **o conteúdo da Entrega PES** (`pes_titulo`,
  `pes_descricao`, `pes_criterios_avaliacao`, `metrica`, `meta`) — é contra isso que a skill casa a issue —
  e **anotada com o período do PIT** (título + `data_inicio`/`data_fim` do `periodo_pit_rit`) para casar
  com o label de mês/ano da issue. Não filtra só o corrente — `PeriodoPitRit.get_periodo_pit_atual()`
  (`models.py:785`) serve apenas de default da inferência.
- `lancar_rit_via_gitlab(entrega_pit, dados, gitlab_project_id, gitlab_mr_iid)` →
  **idempotente** por `(projeto, MR)`: se já existe RIT para esse MR e o mês ainda está em
  `EM_CADASTRO_RIT`, atualiza; se não existe, cria. Reusa a regra do form manual (cálculo de
  `tempo_executada_em_teletrabalho` + `pit.calcular_pit()`). Roda `pode_cadastrar_entrega_rit` contra
  o servidor; se o mês já foi enviado (`situacao_rit != EM_CADASTRO_RIT`), levanta `PermissionDenied`.

**3. Endpoints ninja (`api/endpoints/pgd2.py`, `TrustedAppAuth`)** — caem de 3 para 2:

- `GET .../execucao-gitlab/entregas-disponiveis?gitlab_username=` → lista as entregas elegíveis a RIT
  do servidor (insumo da inferência).
- `POST .../execucao-gitlab/lancar-rit` → upsert do RIT por `(projeto, MR)`; valida que a entrega
  pertence ao servidor e que `pode_cadastrar_entrega_rit` permite; cria/atualiza o RIT em
  `EM_CADASTRO_RIT`.

(O endpoint `efetivar` do desenho anterior **desaparece** — não há transição rascunho→RIT a efetivar.)

**4. Resolução autor→servidor** — reusa `demandas.AnalistaDesenvolvedor.username_gitlab` para mapear
o autor do MR → `rh.Servidor`. Sem mapeamento → erro tratado.

**5. Lado Claude (PR)** — comando/skill que lê issue + diff via MCP GitLab, chama `entregas-disponiveis`,
**casa o conteúdo da issue contra a `pes_descricao` + `pes_criterios_avaliacao` de cada categoria** para
inferir a entrega, estima horas, define `quantidade_progresso` conforme a `metrica` da entrega, mostra
resumo no terminal, o servidor confirma e grava o RIT via um MCP tool novo `lancar_rit_execucao_gitlab`
(espelha `upsert_mr_suap_meta`), que chama `POST lancar-rit`. A escolha do **PIT/mês** segue o **label de
mês/ano da issue** (ex.: `2026-06`), casando com o período anotado em cada entrega; sem label, usa o PIT
corrente.

**6. Job CI (opcional, 1º corte leve)** — não precisa recriar nada no merge (o RIT já existe).
Pode, opcionalmente: (a) comentar no MR confirmando o RIT lançado; (b) no fechamento de MR **sem
merge**, remover o RIT órfão se ainda em `EM_CADASTRO_RIT` (mesmo caminho de `remover_entrega_rit` +
`calcular_pit`). Sem isso, o próprio servidor remove na revisão do mês.

## Fluxo de dados

### Fase PR (servidor no loop) — onde o RIT nasce

1. O servidor termina o trabalho e pede o PR.
2. Claude lê a issue ligada + diff do branch (MCP GitLab) e chama
   `GET entregas-disponiveis?gitlab_username=<servidor>`.
3. Claude infere a `entrega_pit` que melhor casa com o tema; estima `tempo_executado` pelo diff; monta
   `titulo` (título da issue/MR), `descricao` (resumo), `data_inicio` (1º commit do branch),
   `data_fim` (provisória: hoje), `quantidade_progresso`, `perc_executada_em_teletrabalho` (default).
4. Mostra o resumo. O servidor confirma ou ajusta (inclusive trocar a entrega — por isso
   `entregas-disponiveis` lista candidatos).
5. `POST lancar-rit` → SUAP cria/atualiza o RIT em `EM_CADASTRO_RIT`, chaveado por `(projeto, MR)`.
   O `open-pr` segue normal.

### Fase mês (validação nativa) — onde o servidor valida

1. Durante o mês, os RITs lançados ficam editáveis no PGD; o servidor ajusta horas/descrição,
   remove o que não vale, e **envia o RIT do mês** (solicita parecer). Esse envio é a confirmação.
2. O chefe homologa → execução validada. (Fluxo 100% nativo do PGD, sem código novo.)

### Bordas de merge/fechamento (opcional)

- **Merge:** nada obrigatório (o RIT já existe). Job pode comentar "RIT lançado".
- **MR fechado sem merge:** remover o RIT órfão se ainda em `EM_CADASTRO_RIT` (job/rotina), ou deixar
  o servidor remover na revisão do mês.

Datas: `data_inicio` = data do 1º commit do branch; `data_fim` = hoje na confirmação (servidor ajusta).

## Configuração

- Default de `perc_executada_em_teletrabalho` por `Configuracao` (a definir na implementação).
- (Reestimação no merge foi adiada; o `Configuracao` de limite de crescimento do diff não é mais
  necessário no 1º corte.)

## Casos de erro e bordas

| Situação | Tratamento |
|---|---|
| Autor do MR sem `username_gitlab` / sem servidor | Endpoint 4xx; no PR o Claude avisa e não grava |
| Inferência sem candidato | Claude não grava; avisa para escolher manual ou pedir ao gestor a entrega no PIT |
| Inferência ambígua (vários candidatos) | Claude lista top-N e o servidor escolhe na confirmação |
| Entrega de outro servidor no payload | Endpoint 403 (valida `entrega_pit.pit.adesao.servidor == servidor resolvido`) |
| Mês já enviado (`situacao_rit != EM_CADASTRO_RIT`) | `pode_cadastrar_entrega_rit` nega → 403; Claude/CI avisa para lançamento manual |
| Lançar 2× / re-run de pipeline | Idempotente por `(projeto, MR)`: atualiza o RIT existente, não duplica |
| PR fechado sem merge | RIT órfão em `EM_CADASTRO_RIT`: removido por job/rotina ou pelo servidor na revisão |
| RIT editado manualmente no SUAP | A edição manual prevalece; um novo `lancar-rit` do mesmo MR sobrescreve com o que vier (atenção: ver "Riscos") |

## Riscos / trade-offs assumidos

- **Criar no PR conta no PIT antes do merge:** o RIT entra no `calcular_pit` na hora; se o PR for
  fechado sem merge, infla a execução até ser removido. Mitigação: editável/removível + revisão mensal
  (+ limpeza opcional no fechamento). Aceito por decisão de design (contexto fresco no PR vale mais).
- **Upsert sobrescreve edição manual (aceito):** decisão é **upsert** — o servidor edita o RIT livremente
  no SUAP, e um re-run da skill para o mesmo MR **regrava** com o que vier. Trade-off aceito em troca de
  idempotência simples; na prática o re-run é raro e o servidor revê tudo no envio do mês. (Se incomodar
  no uso real, dá pra evoluir depois para upsert seletivo de campos sem mudar schema.)

## Testes

- **Serviço** `lancar_rit_via_gitlab`: cria o RIT com os campos corretos; idempotente por `(projeto, MR)`
  (2ª chamada atualiza, não duplica); dispara `calcular_pit`; respeita `pode_cadastrar_entrega_rit`
  (rejeita servidor errado e mês já enviado).
- **Endpoints** (pytest + ninja): `TrustedAppAuth` exigido; `lancar-rit` faz upsert idempotente;
  resolução `username_gitlab → servidor` (mapeado, não-mapeado, ambíguo); 403 para entrega de outro
  servidor.
- **`entregas-disponiveis`**: filtra só entregas elegíveis a RIT do PIT vigente do servidor (não vaza de
  outro servidor/período).
- **Bordas**: autor não mapeado; mês já enviado; (se implementado) limpeza de RIT órfão.
- A qualidade da inferência/estimativa do Claude **não** é testada por unidade (lado não-determinístico);
  testamos o contrato dos endpoints que a cercam.

## Fora de escopo (primeiro corte)

- Reestimação automática de horas no merge (servidor ajusta no envio do mês).
- Suporte a servidores fora da equipe de desenvolvimento.
- Lançamento de anexo (`anexo`) automático.
- Estimativa de horas dentro do SUAP (mantida no Claude/CI).

## Histórico de revisão

**2026-06-01 — desenho enxuto.** Análise do backend mostrou que o RIT já possui estado de rascunho
nativo (`EM_CADASTRO_RIT`) e validação nativa (envio mensal + homologação). Em consequência:

- **Removido** o model `RascunhoExecucaoGitLab` (mirror + máquina `CONFIRMADO/EFETIVADO/DESCARTADO`).
- **Removido** o endpoint `efetivar` e a transição rascunho→RIT.
- **Substituído** por: criação direta do RIT em `EM_CADASTRO_RIT` + 2 campos de proveniência no RIT
  (`gitlab_project_id`, `gitlab_mr_iid`) com unique parcial para idempotência.
- **Adiada** a reestimação no merge (e o `Configuracao` de limite de diff).
- Momento confirmado: criar no PR (decisão do usuário); proveniência via campos no RIT (decisão do usuário).
- **Clarificação de domínio:** a entrega do PIT é uma **categoria de trabalho** cujo significado está na
  **Entrega PES vinculada** (`PlanoEntregasSetorialEntregas`, `models.py:2347`) — `descricao` +
  `criterios_avaliacao` + `metrica`/`meta`. A inferência casa a issue contra esse conteúdo (não há "balde
  sem descrição"); `entregas-disponiveis` passa a expor os campos da PES. A `metrica` guia o
  `quantidade_progresso`. (Corrige a hipótese equivocada de "bucket genérico vs. demanda".)
- **Granularidade: uma RIT por MR.** `calcular_pit_execucao` (`models.py:5752`) soma
  `tempo_executado`/`quantidade_progresso` de vários RITs por entrega → cada MR vira sua RIT (encaixa na
  chave `(projeto, MR)`); o total da categoria sai da soma. Substitui o hábito manual de empilhar todas
  as issues num RIT só. `quantidade_progresso = 1` por MR em entregas `QUANTIDADE`.

## Referências de código

- `pgd2/models.py:8828` — `RelatorioIndividualTrabalho` (RIT); FK `entrega_pit` (`8829`)
- `pgd2/models.py:8576` — `PlanoIndividualTrabalhoEntregas`
- `pgd2/models.py:6451` — `pode_cadastrar_entrega_rit(user, entrega_pit_id=None, valida_apenas_o_basico=False)`
- `pgd2/models.py:5473` — `calcular_pit`
- `pgd2/models.py:4308` — `get_entregas_pit_para_rit` (`cancelado=False, homologado=True`)
- `pgd2/models.py:4071` — `EM_CADASTRO_RIT`; `situacao_rit`
- `pgd2/models.py:2682` — `SolicitacaoAdesaoServidor.get_pits`
- `pgd2/models.py:785` — `PeriodoPitRit.get_periodo_pit_atual`
- `pgd2/views.py:3711` — `cadastrar_entrega_rit` (caminho que o serviço reusa)
- `pgd2/views.py:3752` — `remover_entrega_rit` (caminho de limpeza de RIT órfão)
- `pgd2/forms.py:1664` — `RelatorioIndividualTrabalhoCadastrarForm`
- `djtools/ninja/auth.py` — `TrustedAppAuth`
- `api/endpoints/terminais.py` — exemplo de endpoint POST com `TrustedAppAuth`
- `demandas/models.py` — `AnalistaDesenvolvedor.username_gitlab`, integração Demanda ↔ MR
- `.gitlab-ci.yml` — pipeline com jobs Claude Code (`SUAP_BOT_TOKEN`)
