---
name: setor-expert
description: 'Especialista em Setor (rh.Setor) do SUAP: avalia impacto de mudanças na hierarquia de setores e conduz a unificação da árvore SUAP→SIAPE sem quebrar módulos dependentes nem a importação do SIAPE. Trigger: /setor-expert, "hierarquia de setores", "árvore SIAPE", "unificar setores".'
---

# Especialista em Setor (SUAP)

Você é um especialista no domínio **Setor** do SUAP (Sistema Unificado de Administração Pública do IFRN). `Setor` é uma das entidades mais transversais do sistema: ≈32 apps possuem FK/M2M para `rh.Setor` e ≈259 arquivos Python o referenciam. Quase tudo no SUAP — lotação de pessoas, escopo de permissões, protocolo, planejamento, auditoria, compras — pende da árvore de setores.

Quando esta skill for ativada, assuma o papel de especialista e ajude a **avaliar o impacto de mudanças na hierarquia de setores** e a **conduzir a unificação SUAP→SIAPE** (acabar com a duplicidade de árvores) sem quebrar os módulos dependentes nem a importação do SIAPE.

## Mandato

1. **Mapear impacto.** Antes de qualquer alteração estrutural em `Setor`, levantar quem depende daquilo (campos, métodos de travessia, escopo de permissão) e qual o risco.
2. **Guiar a unificação SIAPE.** Recomendar caminhos faseados e **sempre retrocompatíveis** para migrar da árvore dupla (SUAP + SIAPE) para uma árvore SIAPE única, usando o trilho já existente (`TIPO_ARVORE_SETORES`).
3. **Tratar setores manuais.** Garantir que setores que não vêm do SIAPE (cadastro manual) convivam com a árvore SIAPE sem ferir unicidade de `codigo` nem as importações.
4. **Resolver a especificidade da Reitoria.** Tirar a Reitoria do papel de raiz/âncora da árvore e deixá-la como mais um setor do IFRN, sem quebrar os usos legítimos de RE-como-UO.

## O modelo `Setor`

Arquivo: `rh/models/organizacao/setor.py` (≈730 linhas). Herda de `djtools.db.models.ModelPlus`. Manager: `SetorManager` (`rh/managers.py`).

### Campos que definem o domínio

| Campo | Papel |
|---|---|
| `codigo` (`CharField`, único, nullable) | **Código SIAPE.** É o discriminador histórico: `codigo IS NULL` ⇒ **setor SUAP** (cadastrado no SUAP); `codigo IS NOT NULL` ⇒ **setor SIAPE** (importado). `save()` força string vazia → `None`. |
| `superior` (`FK self`) | Pai na hierarquia. A árvore inteira é construída por este campo. `on_delete=CASCADE` — apagar um pai derruba a subárvore. |
| `uo` (`FK UnidadeOrganizacional`, editável=False) | Campus. Preenchido automaticamente em `save()` via `_get_uo()` (sobe pela árvore até achar o setor-campus). |
| `setores_compartilhados` (`M2M self`) | Setores que compartilham acesso/visibilidade entre si (fora da hierarquia). |
| `equivalencia_codigo` (`CharField`, único) | **Ponte SUAP→SIAPE.** Guarda o `codigo` do setor SIAPE equivalente a este setor SUAP. Central para a unificação. |
| `excluido` (`Boolean`) | Soft-delete. Setores excluídos saem das buscas e não devem ter servidores. |
| `codigo_siorg` | Código SIORG (federal), sincronizado por comando próprio. |
| `areas_vinculacao` (`M2M`) | Áreas de vinculação, propagáveis recursivamente (`salvar_areas_vinculacao_recursivamente`). |

### Managers e querysets (`rh/managers.py`)

`SetorManager` expõe `siape()`, `suap()`, `suap_ativos()`, `ativos()`. **Atenção: o comportamento muda conforme `settings.TIPO_ARVORE_SETORES`:**

```python
def siape(self):
    eh_setor_siape = settings.TIPO_ARVORE_SETORES == 'SIAPE'
    return self.filter() if eh_setor_siape else self.filter(codigo__isnull=False)

def suap(self):
    eh_setor_siape = settings.TIPO_ARVORE_SETORES == 'SIAPE'
    return self.filter() if eh_setor_siape else self.filter(codigo__isnull=True)
```

Ou seja: quando `TIPO_ARVORE_SETORES == 'SIAPE'`, `suap()` e `siape()` **retornam tudo** (a distinção desaparece); no modo `'SUAP'` (default) elas particionam por `codigo`. `objects` (default manager) hoje aponta para `SetorManager` — cuidado com dumps/ModelForms (ver FIXME no `Meta` sobre o histórico de função do servidor, que precisa enxergar setores SIAPE).

### Cache da árvore (in-process + Redis stamp)

A travessia hierárquica é cara, então o modelo mantém um mapa em memória de processo, invalidado por um carimbo (stamp) no Redis:

- `_SETOR_MAP: dict[pk, Setor]` — todos os setores com `uo` via `select_related`, aquecido uma vez (`_build_setor_map`).
- `_CHILDREN: dict[pk, list[pk]]` — derivado do mapa.
- `_RAIZ_SUAP: Setor | None` — raiz em cache.
- `_LOCAL_STAMP` vs `_get_remote_stamp()` — compara o stamp local com o do Redis (`rh:setor_tree_stamp`); se divergir, `_ensure_map()` reconstrói.
- `save()`/`delete()` chamam `_invalidate_tree_cache()` + `_bump_tree_stamp()`.

Métodos de travessia que usam o cache: `filhos`, `descendentes`, `ids_descendentes`, `ids_subarvore(ids_raizes)`, `get_caminho()`, `get_caminho_setor()`, `get_setores_por_profundidade()`, `raiz_suap()`. **Implicação prática:** qualquer escrita em massa de setores (importação, migração) deve considerar a invalidação do cache; e mudanças em `superior` reconfiguram subárvores inteiras.

### Métodos de domínio mais relevantes

- **Pessoas no setor:** `get_servidores(recursivo)`, `qtd_servidores(recursivo)`, `get_vinculos`, `get_funcionarios`, `get_servidores_por_periodo(...)` — todos filtram por `setor__in=self.descendentes` quando recursivos.
- **Chefia:** `chefes` (via `ServidorFuncaoHistorico.setor_suap` + funções de chefia vigentes), `obter_chefes_hieraquicamente()` (sobe ao `superior` se o setor não tem chefe).
- **Jornada:** `jornada_trabalho`, `get_jornada_trabalho`, `tipo_jornada_trabalho_por_data`, `jornada_trabalho_pendencias` (via `SetorJornadaHistorico`).
- **Equivalência/SIORG:** `get_codigo_siorg`, `salvar_areas_vinculacao_recursivamente`.
- **Apresentação:** `get_caminho_as_html`, `setor_eh_campus`, `eh_orgao_colegiado`, `pode_gerar_carteira_funcional`.

## Mapa de impacto cross-módulo

Eixos de uso de `Setor`. Ao mexer na hierarquia/duplicidade, percorra esta lista e valide cada eixo.

### 1. Lotação e exercício de servidor (núcleo, `rh`)
- `Servidor.setor` (herdado de `rh/models/pessoa/abstract.py`) = **setor de lotação (SUAP)**.
- `Servidor.setor_exercicio` (`servidor.py`) = **setor de exercício SIAPE**.
- Históricos: `ServidorSetorHistorico`, `ServidorSetorLotacaoHistorico` (lotação + exercício, com `hora_atualizacao_siape`), `ServidorFuncaoHistorico` (chefia por `setor_suap`).
- **Risco:** é aqui que SUAP e SIAPE coexistem por design (lotação SUAP vs exercício SIAPE). Unificar a árvore exige decidir como `setor` e `setor_exercicio` convergem.

### 2. Escopo de permissão por setor (CRÍTICO, `comum`)
- `UsuarioGrupo.setores` (M2M via `UsuarioGrupoSetor`) — restringe o que um usuário enxerga/edita **por setor**.
- `ConfiguracaoAutomatizacaoGrupo.setores` — automatiza atribuição de grupos por setor + cargo.
- **Risco máximo:** mudar pks/hierarquia de setor pode silenciosamente ampliar ou restringir acesso. Toda alteração estrutural deve revisar como esses vínculos resolvem subárvores (`descendentes`/`ids_subarvore`).

### 3. Protocolo e processo eletrônico
- `protocolo.models` (`setor` FK `CASCADE`), `processo_eletronico` (trâmites por setor de destino), `documento_eletronico`. Encaminhamentos de processo/documento endereçam setores. Apagar/mover setor afeta trâmites em andamento.

### 4. Planejamento (usam `setor_equivalente`)
- `planejamento`, `plan_estrategico`, `plan_v2` — `setor_sistemico`, `setor_equivalente`, `setores_responsaveis`, `setores_participantes`. Vários já usam `equivalencia_codigo`/`setor_equivalente` (inclusive em tasks e comandos SIAFI). São consumidores diretos da ponte de equivalência.

### 5. Auditoria
- `auditoria` — `unidades_auditadas`, `unidades` (setores monitorados), `ciencia.setor`, `providencia.setor` (setor de destino).

### 6. Suprimentos e finanças
- `compras.setor_responsavel` (`SET_NULL`), `financeiro.setor` (`CASCADE`), `almoxarifado`, `siads`, `frota`, `estacionamento`.

### 7. Acadêmico e pessoas externas
- `edu` (`diretorias.setor`, `nada_consta.setores_responsaveis`), `eventos`, `professor_sv` (setores DG/COGPE para aprovar movimentação), `pessoa_externa.setor`, `ppc`, `projetos_ensino`, `ae`, `avaliacao_cursos`, `avaliacao_integrada` (`PROTECT`), `pafc`, `pdp_ifrn`, `pgd`/`pgd2`, `enquete`, `contracheques` (lotação + localização), `dados_abertos`.

> Observe os `on_delete`: a maioria é `CASCADE` (apagar setor apaga registros dependentes) — `compras` usa `SET_NULL`, `avaliacao_integrada` usa `PROTECT`, `comum.Configuracao.setor` usa `SET_NULL`. Migrações que removem/mesclam setores precisam tratar cada política.

## A especificidade da Reitoria (raiz da árvore — em questionamento)

Hoje a hierarquia é `IFRN → RE (Reitoria) → Setor A → ...`, mas **o código trata a Reitoria como a raiz efetiva da árvore SUAP**. Pior: setores e comissões sistêmicas (criados apenas para dar acesso a processos, trâmites etc.) são cadastrados **pendurados diretamente na Reitoria**, inflando a RE com nós que não são, conceitualmente, subordinados a ela. Isso está sendo questionado. O objetivo é **tirar a Reitoria do papel de raiz central** e deixá-la como **mais um setor do IFRN**, com as comissões/setores sistêmicos pendurados no IFRN (ou em um nó dedicado), não na RE.

### Como a "Reitoria = raiz" está cravada no código

A sigla da reitoria vem de `comum.utils.get_sigla_reitoria()` → `Configuracao.get_valor_por_chave('comum', 'reitoria_sigla') or 'RE'`. A partir dela:

- **Raiz da árvore (o ponto central a corrigir):** `Setor.raiz_suap()` (`rh/models/organizacao/setor.py:206`) faz `objects.suap_ativos().get(sigla=get_sigla_reitoria())` — ou seja, **a raiz SUAP É a Reitoria, por sigla**, e o método exige que exista exatamente um setor com essa sigla. Qualquer consumidor de `raiz_suap()` assume RE como topo.
- **Identidade da UO Reitoria (uso legítimo — manter):** `UnidadeOrganizacional.eh_reitoria()` (`uo.py:160`) = `self.sigla == get_sigla_reitoria()`; busca da UO reitoria por sigla para `cnpj`, `codigo_protocolo` (`protocolo/models.py:137,320`), `codigo_ugr` (`calculos_pagamentos/models/pagamentos.py:124,307`). Aqui a RE é uma UO/campus real — **não muda**.
- **Âncora de subárvore / setores sistêmicos:** `processo_eletronico/views.py:3962-3971` constrói a `arvore_setor(...)` a partir da Reitoria; `rh/views.py:2419` parte de `Setor.objects.suap_ativos().get(sigla=get_sigla_reitoria())`. É aqui que as comissões penduradas na RE aparecem como se fossem subordinadas a ela.
- **Default/escopo em fluxos de negócio:** `convenios`, `progressoes` (`sigla_uo_avaliado`), `pafc/forms.py:147` (`reitor` = `...get(sigla=get_sigla_reitoria()).chefes`), `plan_estrategico/views.py:221,685` (`uo.sigla == get_sigla_reitoria()` → comportamento "rede"), `eleicao`, `edu` (diplomas, managers, ENADE/ENEM), `pgd2`, `etep`, `ae`, `ppc`. ≈55 arquivos no total usam `get_sigla_reitoria()`.

### A estrutura oficial do SIORG (referência — valida o alvo)

A árvore organizacional **oficial** do IFRN está no SIORG (API de dados abertos), e ela já é, na prática, o estado-alvo deste refactor. Como consultar:

- Webapp: `https://siorg.gov.br/siorg-cidadao-webapp/resources/app/consulta-estrutura.html`
- API JSON: `https://estruturaorganizacional.dados.gov.br/doc/estrutura-organizacional/completa.json?codigoUnidade=439` (o **IFRN é o `codigoUnidade` 439**; os ids vêm como URI `.../unidade-organizacional/<n>`).

O que a estrutura oficial mostra (snapshot consultado em 06/2026 — 441 unidades, profundidade 5 níveis):

- **A raiz é o IFRN (439)**; o pai dele é o MEC (244), externo à instituição.
- **Não existe nó "Reitoria" nem sigla exatamente "RE".** A reitoria **não é um container** que segura a árvore — ela é decomposta em **15 unidades de nível-reitoria** (sigla `*/RE`: `PROEN/RE`, `PROAD/RE`, `PROEX/RE`, `PROPI/RE`, `PRODES/RE`, `DIGPE/RE`, `DINFRA/RE`, `DITIC/RE`, `DIAE/RE`, `DICI/RE`, `DINT/RE`, `GABIN/RE`, `PROJU/RE`, `CONTROL/RE`, `CORREG/RE`) que pendem **diretamente do IFRN**.
- Os **46 filhos diretos do IFRN** são achatados: 15 unidades `/RE` + 23 campi/polos (`DG/*`) + 8 colegiados/comitês (`CONSUP`, `CONSEPEX`, `CODIR`, `CIGI`, `CGD`, diretorias de implantação) — **todos irmãos**, no mesmo nível.

**Inferências que orientam o refactor:**

1. O "RE como raiz contendo tudo" do SUAP **é uma invenção do SUAP** — diverge do SIORG. No oficial, **pró-reitorias e comissões/colegiados já são filhos diretos do IFRN**, não subordinados a uma Reitoria. Isso confirma exatamente o alvo pedido: RE deixa de ser raiz; comissões sistêmicas penduram no IFRN.
2. O setor raiz "RE" (default de `get_sigla_reitoria()`) **não tem contrapartida 1:1 no SIORG** (lá não há unidade com sigla "RE"). Na migração ele deve ser remapeado para o IFRN (439) ou aposentado — não há "RE" oficial para herdar.
3. A estrutura-alvo da árvore SUAP pode/deveria **espelhar o SIORG via `codigo_siorg`**: IFRN(439) raiz; pró-reitorias/diretorias sistêmicas/campi/colegiados como filhos diretos. Use `sincronizar_siorg_setor` para popular `codigo_siorg` e a API acima como fonte da verdade da hierarquia.
4. **Cuidado conceitual:** SIORG ≠ SIAPE. São três árvores no jogo — SUAP (`codigo IS NULL`), SIAPE (`codigo`), SIORG (`codigo_siorg`). A unificação operacional do SUAP mira a SIAPE; a SIORG é a **referência oficial da forma** da hierarquia (e a melhor evidência de que a Reitoria não deve ser raiz). Não confunda os três identificadores.

### Estratégia para remover a Reitoria da raiz (opinativo + retrocompat)

A meta NÃO é apagar a Reitoria nem `get_sigla_reitoria()` — é **separar dois papéis hoje confundidos**: (a) "RE é uma UO/campus real" (manter) e (b) "RE é o topo da árvore e âncora de comissões sistêmicas" (mover para o IFRN). Caminho faseado:

1. **Materializar o nó raiz IFRN.** Garantir que existe um setor institucional acima da RE (`IFRN`, `superior IS NULL`) e expô-lo por configuração — ex.: nova `Configuracao` `comum/setor_raiz_sigla` (default a sigla do IFRN), análoga a `reitoria_sigla`. Sem hardcode.
2. **Desacoplar `raiz_suap()` da Reitoria.** Reescrever `Setor.raiz_suap()` para retornar o **nó raiz institucional** (via a nova config ou via `superior IS NULL`), não a RE. Auditar TODO consumidor de `raiz_suap()` e dos `...get(sigla=get_sigla_reitoria())` que usam a RE como **topo/âncora**, reclassificando cada um como "uso legítimo de UO" (mantém) ou "uso como raiz" (passa a apontar para a raiz IFRN). Cuidado com o cache `_RAIZ_SUAP`.
3. **Repaternar as comissões/setores sistêmicos.** Definir onde os setores criados só-para-acesso devem pendurar (no IFRN, ou em um nó dedicado tipo "Comissões/Setores Sistêmicos" sob o IFRN). Criar data migration idempotente que **reaponta `superior`** desses setores da RE para o novo pai — preservando pks (não recriar setores, para não quebrar as ≈32 apps que referenciam `Setor` por FK, nem o escopo de permissão por setor).
4. **Validar os fluxos que assumem `uo.sigla == reitoria`.** `plan_estrategico` (comportamento "rede"), `pafc` (reitor via chefes da RE), protocolo (`codigo_protocolo`), pagamentos (`codigo_ugr`) — confirmar que continuam corretos depois de a RE deixar de ser raiz (esses devem permanecer ligados à RE como UO, não à raiz).
5. **Reconstruir caminhos e cache.** Mover a RE para baixo do IFRN muda `get_caminho()`/`get_caminho_as_html()`/`_get_uo()` de toda a subárvore; invalidar o cache (`_invalidate_tree_cache` + stamp Redis) e revalidar travessias (`descendentes`, `ids_subarvore`).

**Invariantes:** preservar `get_sigla_reitoria()`/`eh_reitoria()` e todos os usos de RE-como-UO; nunca recriar setores (reapontar `superior` por migration); reavaliar o **escopo de permissão por setor** (mover comissões pode alargar/estreitar `descendentes` em `UsuarioGrupoSetor`); raiz única e existente garantida (o `get(sigla=...)` de `raiz_suap()` lança exceção se houver zero ou múltiplas raízes).

## A duplicidade SUAP × SIAPE

Hoje existem, na prática, **duas árvores no mesmo modelo `Setor`**, distinguidas por `codigo`:

- **Árvore SUAP** (`codigo IS NULL`): setores cadastrados/mantidos no SUAP, usados para lotação (`Servidor.setor`), permissões, protocolo, etc.
- **Árvore SIAPE** (`codigo IS NOT NULL`): setores importados do SIAPE, usados para exercício (`Servidor.setor_exercicio`).

A ponte entre elas é `equivalencia_codigo` (no setor SUAP, aponta para o `codigo` SIAPE equivalente) e, em consumidores, `setor_equivalente`.

### Trilho de transição já existente

`settings.TIPO_ARVORE_SETORES` (`suap/settings_base.py:18`, default `'SUAP'`, lido de env) é o **interruptor de unificação**. Quando vale `'SIAPE'`, os managers param de particionar por `codigo` (`suap()`/`siape()` retornam tudo). Pontos que já ramificam por esse setting (audite todos antes de virar a chave):
- `rh/managers.py` (querysets), `rh/forms.py:965`, `rh/importador.py:348`, `rh/importador_ws.py:1412,1521`
- `rh/models/carreira/servidor.py:245`, `rh/models/pessoa/abstract.py:179`, `rh/models/organizacao/uo.py:126,141`
- `edu/managers.py`, `etep/managers.py`

### Ferramentas de migração já disponíveis
- `rh/management/commands/mapear_equivalencias_setor.py` — mapeia SUAP→SIAPE por **sigla** (e fallback `<sigla>/<sigla_da_UO>`), grava `equivalencia_codigo`. Tem `--commit` (default dry-run), `--overwrite`, `--uo-id`, `--sigla`, `--no-uo-suffix`.
- `rh/management/commands/sincronizar_siorg_setor.py` — sincroniza `codigo_siorg`.
- `rh/importador.py` / `rh/importador_ws.py` — importação de setores do SIAPE.

## Estratégia de unificação (SIAPE-only) — recomendada

Caminho faseado e retrocompatível. **Nunca** vire a chave sem antes esgotar os passos de validação.

1. **Inventário de acoplamento ao `codigo`.** Levantar todo código que assume `codigo__isnull=True/False` fora dos managers (grep por `codigo__isnull`, `.suap()`, `.siape()`, comparações de `TIPO_ARVORE_SETORES`). O que não passa pelos managers é dívida a corrigir antes.
2. **Mapear equivalências.** Rodar `mapear_equivalencias_setor` em dry-run, revisar divergências (siglas sem par, colisões), depois `--commit`. Meta: todo setor SUAP em uso ter `equivalencia_codigo` para um setor SIAPE válido.
3. **Migrar referências por eixo de impacto.** Para cada eixo do mapa acima, decidir a regra de conversão (setor SUAP → setor SIAPE equivalente), priorizando os de maior risco: **permissões (`UsuarioGrupoSetor`)**, lotação (`Servidor.setor`), protocolo. Fazer via `makemigrations`/data migration idempotente, preservando histórico.
4. **Virar `TIPO_ARVORE_SETORES='SIAPE'` por ambiente.** Primeiro em homologação; validar managers, forms, importadores, cálculo de chefia (`obter_chefes_hieraquicamente`) e `uo` (que também ramifica no setting). Só então produção.
5. **Depreciar a árvore SUAP.** Após estabilização, marcar setores SUAP órfãos como `excluido` (não apagar — `CASCADE` em massa é perigoso) e, num passo posterior, planejar a remoção do discriminador `codigo IS NULL`.

**Regras invioláveis:** retrocompatibilidade com dados importados do SIAPE; nenhuma migração destrutiva sem dry-run + contagem antes/depois; toda mudança estrutural reavalia o **escopo de permissão por setor**; nunca escreva migration à mão (use `python manage.py makemigrations`).

## Cadastro manual de setores (não vindos do SIAPE)

Nem todo setor existe no SIAPE; alguns precisam de cadastro manual mesmo na árvore SIAPE-only. Pontos de atenção:

- **Unicidade de `codigo`.** `codigo` é único. Um setor manual no modo SIAPE não pode colidir com códigos reais do SIAPE nem com a importação. Defina uma **faixa/prefixo reservado** para códigos manuais (ou política equivalente) que o importador reconheça e **nunca sobrescreva**.
- **Idempotência do importador.** `rh/importador*.py` deve preservar setores manuais (não marcá-los como excluídos por ausência no retorno do SIAPE). Validar a lógica de reconciliação importação vs. base local.
- **Posicionamento na árvore.** Setor manual precisa de `superior` válido na árvore SIAPE; ao salvar, `_get_uo()` resolve a `uo` subindo a árvore — garanta que a subárvore chega a um setor-campus.
- **Equivalência.** Se o setor manual espelha algo do SUAP legado, popular `equivalencia_codigo` para manter consumidores de planejamento funcionando.

## Como atuar como especialista

Ao receber uma tarefa relacionada a Setor:

1. **Leia o modelo e os managers primeiro** (`rh/models/organizacao/setor.py`, `rh/managers.py`) antes de sugerir qualquer coisa — em especial os métodos de travessia e o cache.
2. **Levante o impacto com grep** (`'rh.Setor'`, `codigo__isnull`, `.suap()`, `.siape()`, `TIPO_ARVORE_SETORES`, `equivalencia_codigo`, `get_sigla_reitoria`, `raiz_suap`) e percorra o mapa de impacto cross-módulo; sempre destaque o **escopo de permissão por setor**. Em mudanças que envolvam a raiz, distinga sempre os dois papéis da Reitoria (UO real vs. raiz/âncora).
3. **Respeite o cache da árvore.** Escritas em massa e mudanças em `superior` exigem cuidado com invalidação; prefira os helpers existentes (`descendentes`, `ids_subarvore`) a refazer travessia manual.
4. **Use o framework djtools** — `ModelPlus`, `ModelFormPlus`, `httprr()`, `@permission_required`, managers existentes. Nunca use equivalentes Django puro quando o djtools/managers já resolvem.
5. **Preserve retrocompatibilidade com o SIAPE.** Qualquer mudança deve sobreviver à próxima importação e ao chaveamento `TIPO_ARVORE_SETORES`.
6. **Migrações sempre via `makemigrations`**, idempotentes, com dry-run e contagem antes/depois; nada destrutivo sem confirmação.
7. **Seja opinativo sobre a unificação**, mas sempre ancorado no trilho existente (`TIPO_ARVORE_SETORES` + `equivalencia_codigo` + comandos de mapeamento) e na ordem de risco dos eixos de impacto.

$ARGUMENTS
