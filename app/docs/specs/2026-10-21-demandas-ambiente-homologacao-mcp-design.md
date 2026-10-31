# Design — Ambiente de homologação de uma demanda criado pelo suap-mcp

- **Data:** 2026-10-21
- **Status:** Aprovado para começar pelas fatias 1 e 2 (leitura); as de escrita aguardam as decisões do fim.
- **Módulos:** `demandas/` e `api/endpoints/demandas.py` (SUAP); `src/suap_mcp/modules/demandas/` (suap-mcp)
- **Base analisada:** `master` em `293893287b`; suap-mcp `main` em `40aaae2`

## Problema

Quem trabalha numa demanda pelo suap-mcp chega a abrir o MR (`open_mr_for_demanda`), mas não
consegue subir o ambiente de homologação que o demandante usa para validar. Hoje o caminho
passa pelo admin do SUAP, por dois botões em telas diferentes e por uma task que fica sondando
o log do GitLab por até 30 minutos. A pergunta é: como o MCP pode criar e acompanhar esse
ambiente sem dar a um agente mais poder, nem mais custo de infraestrutura, do que a tela já dá
a um analista?

O padrão a seguir é o de `propor_revisao_especificacao`: um endpoint no SUAP (`/api/ti/demandas/...`)
que aplica as regras da tela, mais uma tool fina no MCP com `confirm` e dry-run por padrão.

## Como o ambiente é criado hoje

### 1. Quem pode

- As permissões `add/change/view/delete_ambientehomologacao` existem só no grupo **Analista**
  (`demandas/permissions.yaml:6`). O menu *Tec. da Informação › Desenvolvimento › Ambientes de
  homologação* aponta para `/admin/demandas/ambientehomologacao/` (`demandas/menu.yaml:20`).
- O grupo **Desenvolvedor** não tem essas permissões. Mesmo assim, a aba Homologação mostra a ele
  o botão "Configurar Ambiente de Homologação" (`tabs/homologacao.html:17`), que leva a uma view
  que exige `add_ambientehomologacao` e devolve 403.
- A tela de ciclo de vida (`ambientehomologacao`, `views.py:2394`) exige `add_ambientehomologacao`
  e **não** confere quem criou o ambiente: qualquer analista atualiza, remove ou destrói o ambiente
  de qualquer outro.
- `acessar_ambiente_via_demanda` (`views.py:2417`) exige só `view_demanda` e não confere se o
  ambiente `pk` é o da demanda `demanda_pk`. Na prática, qualquer pessoa que vê demandas (o
  demandante também) dispara o deploy de qualquer ambiente inativo trocando o `pk` na URL.

### 2. Cadastro (admin, `AmbienteHomologacaoForm`, `forms.py:1028`)

| Campo | Origem / regra |
|---|---|
| `criador` | `AnalistaDesenvolvedor` do usuário logado (inicial). O `username_gitlab` dele vira o dono do container. |
| `branch` | Texto livre, validado fora de `DEBUG` contra `gitlab.list_branche_names(branch)`. O default do model é `'master'`. |
| `banco` | Escolha entre os nomes de `Configuracao demandas.bancos_suapdevs`, separados por espaço. O default do model é `suap_mascarado_pequeno`. |
| `data_expiracao` | Obrigatória, **sem limite máximo**. |
| `senha` | Sugerida: os 6 primeiros caracteres do `sha1(time.time())`. |

Não existe FK do ambiente para a demanda: o vínculo é feito depois, no outro sentido (passo 4).

### 3. `save()`: pipeline no GitLab (`models/ambiente.py:30`)

Na primeira gravação (`pipeline is None`), o `save()` define `data_criacao = hoje` e chama
`criar_pipeline()`, que faz `POST /projects/:id/pipeline?ref=<branch>` com o token de serviço
`Configuracao demandas.gitlab_token`. Ou seja, o pipeline sai em nome do bot, não do usuário. As
variáveis enviadas são:

```
CI_COMMIT_BRANCH=<branch>  CI_COMMIT_AUTHOR=<username_gitlab>  DATABASE_TEMPLATE=<banco>
NAME=<branch>              PASSWORD=<senha>
```

- `CI_COMMIT_BRANCH` é uma variável predefinida do GitLab, e aqui ela é **sobrescrita**. As regras
  dos jobs de produção (`.prod`, `.gitlab-ci.yml:536`) dependem de `$CI_COMMIT_BRANCH == 'master'`
  e de `$GITLAB_USER_LOGIN`. Elas só não aparecem porque quem cria o pipeline é o bot.
- O pipeline roda o `.gitlab-ci.yml` **da branch**. Com `CI_PIPELINE_SOURCE == 'api'`, as regras
  atuais só criam jobs manuais, entre eles `deploy-suapdev`, `undeploy-suapdev` e `destroy-suapdev`
  (âncora `.homologate`: stage `homologate`, runner `hom-v3`, `when: manual`). Criar o pipeline,
  portanto, não consome runner.
- Se a resposta não trouxer `id`, o `save()` levanta `Exception` com a mensagem do GitLab, e o
  `add_view` do admin a transforma em mensagem de erro.
- O registro é gravado com `ativo=False`.

### 4. Vínculo com a demanda e com a entrega

O ambiente chega à demanda por três caminhos:

1. **Mudança de etapa para Em homologação.** O formulário de `SituacaoAlterarFormFactory`
   (`forms.py:693`) lista **todos** os ambientes (`AmbienteHomologacao.objects`), com um link "crie
   um Ambiente de Homologação" que abre o admin. Escolher um ambiente apaga a URL e a senha
   externas. `Demanda.alterar_situacao` grava `demanda.ambiente_homologacao` (`models/demanda.py:1128`).
2. **Nova entrega.** `EntregaForm` lista só os ativos (`forms.py:1228`), e
   `EntregaService.criar` grava `Entrega.ambiente_homologacao` (`related_name='entregas'`).
3. **Admin da demanda**, no fieldset "Dados de homologação" (`admin.py:313`).

A aba Homologação aparece quando a demanda está em homologação **ou** quando tem um ambiente
vinculado (`demanda.html:253`). Vincular um ambiente antes da etapa, portanto, já mostra a aba ao
demandante.

### 5. Deploy: o container sobe

O deploy é disparado por `?action=deploy` na tela do ambiente ou pelo botão "Criar e Acessar
Ambiente de Homologação" da aba (`acessar_ambiente_via_demanda`). Os dois chamam a task
`criar_atualizar_container` (`tasks.py:8`), uma `@task` do djtools com barra de progresso, que:

1. chama `ambiente.criar_atualizar_container()`, que faz `gitlab.execute_job(pipeline, 'deploy-suapdev')`
   (espera até ≈10 s o job ficar `manual`, depois `play`; ou `retry`, se o job já rodou) e grava
   `ativo=True` **logo após o disparo**, antes de o job terminar;
2. sonda o log do job a cada 15 s, até 120 vezes (30 min), e converte marcos do log em percentual
   (`get_status_container`): `docker run` 5 %, `createdb` 20 %, `git pull` 50 %, `manage.py sync`
   75 %, `SENHA:` 100 %.

O job executa, **no host do runner**, `cd /opt/suap && bin/ci/deploy.sh ...`. O script é o do
checkout `/opt/suap`, não o da branch, mas a linha de comando do job vem do `.gitlab-ci.yml` da
branch. O `deploy.sh`:

- calcula o `slug` da branch (`/` e qualquer caractere fora de `[A-Za-z0-9_.-]` viram `-`);
- copia o repositório para `/var/suapdevs/<slug>` e faz `git pull origin -X ours <branch>`;
- se o banco ainda não existe, roda `pg_terminate_backend` em **todas** as conexões do banco
  template e `createdb -T <template> database-<slug>-suap`;
- sobe o container `deploy-<slug>` com `--env-file .env` **do host**, rótulos `OWNER`, `BRANCH`,
  `PASSWORD` e `DATE`, e `--restart unless-stopped`;
- roda `uv sync` e `manage.py sync` com teto de memória de 32 GiB, que volta a 1 GiB de RAM e
  2 GiB de swap ao final;
- roda `set_passwords_to "$PASSWORD" "$USERNAMES"`. Como `criar_pipeline` não envia `USERNAMES`,
  **todos os usuários** do banco mascarado ficam com a mesma senha, superusuários inclusive;
- imprime `URL: ... SENHA: ...`. Com `set -x` ativo, a senha aparece várias vezes no log do job;
- `index.sh` regenera o nginx de todos os ambientes e **reinicia o container `web`**, o proxy
  compartilhado.

A URL é `https://<branch>.<dominio_suapdevs>` (`get_url_homologacao`). Ela usa a branch crua,
enquanto o nginx usa o slug: uma branch com `/`, como `feat/x`, gera uma URL que não abre.

### 6. Status, atualização e remoção

| Ação | Onde | Efeito |
|---|---|---|
| Atualizar container | `?action=deploy` (ativo) | `retry` do `deploy-suapdev`: `git pull` + `sync` no mesmo banco |
| Atualizar pipeline | `?action=pipeline` | Cria a branch a partir de `master` se ela não existir mais (por exemplo, depois do merge), cria um pipeline novo e apaga a branch temporária |
| Remover provisoriamente | `?action=undeploy` | Novo pipeline + `undeploy-suapdev`: para o container e apaga a pasta, mas **mantém o banco**; `ativo=False` |
| Remover definitivamente | `?action=destroy`, `delete()`, exclusão em massa no admin | Novo pipeline + `destroy-suapdev`: container, pasta e `DROP DATABASE ... WITH (FORCE)`; `ativo=False` |
| Executar comando | `executar_comando_ambiente_homologacao` | Não implementado: `ExecutarComandoForm.clean_comando` sempre falha, e a view só devolveria o log do deploy |

Cada ação registra uma linha na tabela de auditoria `suapdevs` (nome do container, dono e ação).

### 7. Expiração e limpeza

O Beat roda `remover_ambientes_homolog_expirados` todo dia às 03:37 (`demandas/beat.py`). O comando:

1. notifica o criador quando `data_expiracao` é amanhã;
2. destrói os ativos com `data_expiracao < hoje` **ou** vinculados a uma demanda concluída,
   cancelada ou suspensa. O critério usa só `demanda__situacao`, a relação reversa de
   `Demanda.ambiente_homologacao`: um ambiente vinculado apenas a uma entrega nunca é limpo pela
   situação;
3. reprocessa os inativos dos últimos 30 dias cujo `destroy` ficou `manual` ou `failed`. Depois
   desse prazo, a limpeza tem de ser manual.

### 8. Custo

Por ambiente: uma cópia inteira do banco template, uma cópia do repositório, um container com
1 GiB de RAM e 2 GiB de swap em regime (até 32 GiB durante o `sync`) e o runner `hom-v3` ocupado
durante o deploy. Tudo isso roda num único host. O código **não impõe cota**: não há limite de
ambientes ativos por pessoa nem no total, e `data_expiracao` não tem teto. Dois efeitos colaterais
atingem outros ambientes: o `pg_terminate_backend` no template derruba um `createdb` concorrente,
e o restart do `web` interrompe todos os ambientes por alguns segundos. O tamanho real do template
e a capacidade do host não estão no repositório: é preciso perguntar à infraestrutura.

## Proposta

### Princípios

1. **O MCP nunca fala com o GitLab para isso.** Tudo passa pelo SUAP, que aplica as regras da
   tela, usa o token de serviço e mantém um único caminho de auditoria. As tools
   `trigger_gitlab_pipeline` e `retry_gitlab_failed_jobs` não devem servir de atalho (ver Riscos).
2. **O agente só escolhe o que a tela deixaria escolher, e menos.** A branch é a da demanda
   (`demanda.branch`), não um texto livre. O banco vem da lista configurada. A validade tem teto.
   Variáveis de pipeline, dono e senha nunca entram no payload.
3. **Criar não é implantar.** Criar o registro e o pipeline não custa runner. O custo está no
   deploy, então são duas chamadas, e cada uma pede seu próprio `confirm`.
4. **O dry-run passa pelo servidor.** Nas tools atuais, `confirm=False` devolve o eco do payload
   sem chamar o SUAP. Aqui isso não basta: a resposta útil ("criaria", "reaproveitaria o ambiente
   #N", "faltam permissão / branch / cota") depende da permissão, do GitLab e do estado do banco.
   Proposta: `confirm=False` chama o mesmo endpoint com `dry_run=true`, que valida tudo e não
   grava nada. No SUAP, `dry_run` vale `true` por padrão: o cliente precisa pedir a execução
   explicitamente.
5. **Idempotência pela demanda.** A chave é `(demanda, demanda.branch)`. Repetir uma chamada
   devolve o estado atual e não gera um segundo pipeline, deploy ou banco.

### Permissão exigida (todos os endpoints de escrita)

As regras abaixo são verificadas no SUAP, com o usuário do token (JWT/OAuth2 do usuário, como nas
demais tools):

- `demandas.add_ambientehomologacao` (grupo Analista);
- ser analista **ou** desenvolvedor da demanda (`demanda.analistas` / `demanda.desenvolvedores`).
  Hoje desenvolvedor não tem a permissão do item anterior; abrir o acesso a ele é uma decisão
  (ver Decisões);
- ter um `AnalistaDesenvolvedor` com `username_gitlab` preenchido, porque ele vira o
  `CI_COMMIT_AUTHOR`, o dono do container;
- para `implantar`, `prorrogar` e `remover`: ser o `criador` do ambiente ou analista da demanda.
  É mais estrito que a tela atual, que libera qualquer analista.

Opcional: exigir um escopo OAuth2 próprio (`require_scopes`, `djtools/ninja/auth.py:163`), para que
um token emitido para outro aplicativo não consiga subir ambientes.

### Endpoints novos no SUAP (`api/endpoints/demandas.py`)

Todos ficam em `/api/ti/demandas/{id}/ambiente-homologacao/...` e seguem o formato de erro atual
(`{error, hint, context}`). A lógica fica num serviço do módulo (`AmbienteHomologacaoService`),
para que a tela possa usá-lo depois.

| # | Método e rota | Faz | Respostas |
|---|---|---|---|
| E1 | `GET  {id}/ambiente-homologacao/` | Estado do ambiente vinculado: `id`, `branch`, `banco`, `data_criacao`, `data_expiracao`, `ativo`, `pipeline_id`, `pipeline_url`, `url` (só se ativo), `deploy` (`status` do job no GitLab, `etapa` de `get_status_container`, `job_url`), `criador`. **Sem `senha`.** | 200; 403 (`permite_visualizar`); 404 `ambiente_not_found` |
| E2 | `POST {id}/ambiente-homologacao/` body `{banco?, dias_validade?, dry_run=true}` | Cria o `AmbienteHomologacao` da `demanda.branch` (senha gerada no servidor, criador = usuário), cria o pipeline e grava `demanda.ambiente_homologacao`, **sem mudar a etapa** | 201 criado; 200 já existia (`already_exists`) ou dry-run; 403; 409 `ambiente_de_outra_branch` / `slug_em_uso`; 422 `branch_missing`, `branch_not_found`, `branch_proibida`, `banco_invalido`, `validade_excedida`, `situacao_invalida`, `gitlab_username_missing`, `pipeline_creation_failed` |
| E3 | `POST {id}/ambiente-homologacao/implantar/` body `{atualizar=false, dry_run=true}` | Dispara `deploy-suapdev` (`play`; ou `retry` com `atualizar=true`) e responde na hora, sem a task de 30 min. Se o pipeline estiver velho ou a branch tiver sido apagada, chama `atualizar_pipeline` antes | 202 disparado; 200 já em execução ou já ativo sem `atualizar` (no-op); 403; 404; 422 `cota_excedida`, `situacao_invalida`; 502 `gitlab_job_error` |
| E4 | `POST {id}/ambiente-homologacao/prorrogar/` body `{dias, dry_run=true}` | `data_expiracao = max(atual, hoje + dias)`, limitada ao teto | 200; 403; 404; 422 `validade_excedida` |
| E5 | `POST {id}/ambiente-homologacao/remover/` body `{dry_run=true}` | `destruir()`: container, pasta e banco. O registro fica, com `ativo=False` | 200 removido, ou no-op se já inativo e sem destroy pendente; 403; 404; 502 `gitlab_job_error` |

Regras de E2:

- A demanda precisa estar em desenvolvimento ou em homologação. Fora disso, a limpeza da
  madrugada destruiria o ambiente (se terminal) ou não haveria o que homologar.
- A branch precisa existir (`Demanda.branch_existe`) e não pode ser `master`, nem nenhuma branch
  protegida. O model ainda usa `master` como default.
- Idempotência:
  - se a demanda já tem um ambiente com a mesma branch, devolve 200 com ele, sem chamar o GitLab
    (mesmo que esteja inativo: subir é a vez de E3);
  - se a demanda tem um ambiente de **outra** branch, devolve 409 e não troca. A troca é decisão
    humana;
  - se já existe um ambiente ativo com o mesmo slug ligado a outra demanda, devolve 409
    `slug_em_uso`, porque os dois dividiriam container e banco;
  - se existe um ambiente da mesma branch, sem demanda, criado à mão no admin, ele é reaproveitado
    e vinculado.
- Concorrência: `select_for_update` na `Demanda` durante a criação, para que duas chamadas
  simultâneas não gerem dois pipelines. Se o GitLab criar o pipeline e o `save` falhar, sobra um
  pipeline só com jobs manuais, que é barato. Esse caso vai para o log e para o Sentry.
- Validade: o padrão e o teto vêm da `Configuracao` (proposta: 7 e 15 dias).
- A ação fica registrada na demanda (comentário ou nota interna "ambiente criado via API por X"),
  para que a origem apareça na timeline.

Regras de E3:

- O deploy é o passo caro. A cota de ambientes ativos por usuário e no total vem da `Configuracao`
  e é conferida aqui. O número depende da capacidade do host `hom-v3`.
- `ativo=True` continua sendo gravado no disparo, como hoje. Se fosse gravado só no sucesso, um
  deploy que falhasse depois do `createdb` deixaria um banco que a limpeza noturna nunca acharia,
  porque ela só olha os ativos.
- Job `pending`, `running` ou `created` resulta em 200 `already_running`, sem novo `play`.
- O agente acompanha o andamento chamando E1, não a task com barra de progresso.

### Tools novas no suap-mcp (`modules/demandas/`)

Seguem o padrão existente: input Pydantic em `models.py`, função em `client.py`, tool com
docstring "Use quando / Dry-run / Side effects" em `tools.py`, registro em `server.py` e testes
com respx.

| Tool | Endpoint | Anotações | `confirm=False` |
|---|---|---|---|
| `get_ambiente_homologacao` | E1 | `readOnlyHint`, `idempotentHint`, `openWorldHint` (consulta o GitLab via SUAP) | — |
| `criar_ambiente_homologacao` | E2 | `destructiveHint: False`, `idempotentHint: True` | chama E2 com `dry_run=true` |
| `implantar_ambiente_homologacao` | E3 | `destructiveHint: True` (com `atualizar`, sobrescreve o código do container), `idempotentHint: True` | chama E3 com `dry_run=true` |
| `prorrogar_ambiente_homologacao` | E4 | `destructiveHint: False`, `idempotentHint: True` | chama E4 com `dry_run=true` |
| `remover_ambiente_homologacao` | E5 | `destructiveHint: True`, `idempotentHint: True` | chama E5 com `dry_run=true` |

O prompt `demanda_workflow` ganha um passo: depois do MR aberto e antes de passar a demanda para
homologação, o agente oferece criar o ambiente (dry-run → confirmação do usuário → `confirm=True`),
depois implantar, e acompanha com `get_ambiente_homologacao`. Restrições do prompt: nunca remover
um ambiente que o usuário não criou e nunca implantar sem confirmação explícita.

O deploy em produção usa tags. Até uma tag com E1–E5 ser implantada, as rotas respondem 404 sem o
corpo `{error, hint}`. O client deve converter esse caso num `DemandaError`
`endpoint_indisponivel`, com hint "a versão do SUAP em produção ainda não tem este endpoint",
em vez de um `UpstreamHTTPError` genérico.

## Riscos

### Segurança

- **Senha do ambiente.** Ela dá login como **qualquer** usuário do banco mascarado, superusuários
  inclusive. Ela já vaza no log do job (`set -x` + `echo`), num rótulo do container (`docker inspect`)
  e nas variáveis do pipeline. Devolvê-la ao agente a levaria também para transcrições e logs de
  ferramenta. Proposta: E1 não a devolve. Quem precisar dela a vê no SUAP, como hoje. Se um agente
  precisar testar no ambiente (Playwright), isso vira uma decisão à parte (ver Decisões).
- **`.env` do host dentro do container.** O deploy passa `--env-file .env` do runner para o
  container. Por isso, "Executar comando" (`manage.py` arbitrário) nunca deve ser exposto: seria
  execução de código com os segredos do host de homologação. Hoje a funcionalidade nem está
  implementada.
- **A branch define o job.** O pipeline roda o `.gitlab-ci.yml` da branch, criado pelo token de
  serviço. Quem consegue fazer push numa branch já executa CI, então o risco não é novo. Mas o
  agente não pode escolher a branch: ela é sempre `demanda.branch`, que um analista definiu.
- **`CI_COMMIT_BRANCH` sobrescrito.** O endpoint E2 bloqueia `master` e branches protegidas. À
  parte disso, a tool `trigger_gitlab_pipeline` do suap-mcp aceita variáveis arbitrárias com o
  token do **usuário**. Com ela, alguém poderia montar à mão o pipeline de homologação, ou fazer
  `CI_COMMIT_BRANCH=master` liberar jobs de produção numa ref qualquer, se o usuário for um dos
  logins listados em `.prod`. Recomendação: proibir nessa tool as variáveis `CI_*`, `GITLAB_*`,
  `PASSWORD`, `DATABASE_TEMPLATE` e `NAME`.

### Permissão

- O endpoint fica **mais estrito** que a tela: exige vínculo com a demanda e confere o criador nas
  ações sobre o ambiente. Isso não corrige a tela, que segue com os dois furos descritos em
  "Quem pode": qualquer analista age sobre o ambiente de qualquer outro, e
  `acessar_ambiente_via_demanda` não confere se o ambiente pertence à demanda. Os dois ficam como
  follow-up.
- Sem escopo OAuth2, qualquer token de um analista sobe ambientes. Avaliar `require_scopes`.

### Custo de infraestrutura

- Um agente em loop pode subir ambientes em série. As defesas são a cota em E3, o teto de
  validade, a idempotência por demanda e o `confirm` em cada passo.
- Deploys simultâneos do mesmo template se atrapalham (`pg_terminate_backend` + `createdb -T`).
  Com a API, a concorrência tende a crescer. Opções: fila (um deploy por vez no `hom-v3`, por
  `resource_group` no job do GitLab) ou recusar E3 enquanto outro deploy estiver `running`.
- Cada deploy reinicia o proxy `web` de todos os ambientes.

### Ambientes órfãos

- Um ambiente sem demanda só é limpo pela data. Por isso o endpoint sempre vincula à demanda: a
  limpeza pela situação passa a valer para ele.
- A limpeza ignora `Entrega.ambiente_homologacao`. Isso não afeta a proposta, que vincula pela
  demanda, mas é um furo existente.
- Remover provisoriamente (`undeploy`) mantém o banco. Por isso não é exposto ao agente: E5 faz
  sempre `destroy`.
- O destroy que falha por mais de 30 dias sai da fila de reprocessamento. E1 deve mostrar
  `destroy_pendente` para que esse caso apareça.
- Se o pipeline for criado e o `save` falhar, sobra um pipeline só com jobs manuais. É barato e
  vai para o log.

### O que não expor a um agente

- A senha do ambiente, e qualquer campo do `.env` ou das variáveis de pipeline.
- "Executar comando" e qualquer `manage.py` dentro do container.
- Escolha livre de branch, dono, banco fora da lista, validade sem teto e variáveis de pipeline.
- `undeploy` (remoção provisória) e a exclusão do registro (`delete` do admin).
- "Atualizar pipeline" como ação solta. Ela cria e apaga uma branch no repositório; o E3 a usa
  por dentro quando precisa.
- Ações sobre ambientes de outras pessoas ou de demandas a que o usuário não está vinculado.

## Fatiamento em MRs

Cada fatia do SUAP só vale em produção depois de entrar numa tag implantada. As do MCP podem
entrar no `main` logo depois da fatia correspondente do SUAP e funcionam em homologação primeiro.

| # | Repo | Conteúdo | Testes |
|---|---|---|---|
| 1 | SUAP | Schema e **E1** (leitura), com `AmbienteHomologacao.get_situacao_deploy()` | `api/tests/views/test_demandas_ambiente_homologacao.py`, com o GitLab mockado na fronteira (`djtools.utils.gitlab`) |
| 2 | suap-mcp | `get_ambiente_homologacao` + conversão do 404 de rota ausente em `endpoint_indisponivel` | respx em `tests/modules/...` |
| 3 | SUAP | `AmbienteHomologacaoService` + **E2** (criar e vincular, dry-run, idempotência, lock, validade com teto, bloqueio de `master`) + chaves de `Configuracao` | fluxo: dry-run não grava; repetir devolve 200; outra branch dá 409; sem permissão dá 403 |
| 4 | SUAP | **E3** (implantar), cota e recusa de concorrência; E1 passa a mostrar `destroy_pendente` | fluxo: job `running` gera 200 sem novo `play`; cota excedida dá 422 |
| 5 | suap-mcp | `criar_ambiente_homologacao`, `implantar_ambiente_homologacao` e passo novo no prompt `demanda_workflow` | respx: `confirm=False` envia `dry_run=true` |
| 6 | SUAP + suap-mcp | **E4** e **E5** e as tools `prorrogar` e `remover` | — |

Follow-ups independentes, com MR próprio e fora deste desenho:

- **SUAP:** checar se o ambiente pertence à demanda e se o usuário é dono ou analista em
  `acessar_ambiente_via_demanda` e `ambientehomologacao`; usar o slug em `get_url_homologacao`;
  incluir `Entrega.ambiente_homologacao` no critério da limpeza; esconder o botão "Configurar" de
  quem não tem permissão; remover o bloco `obj.usuarios`, que não existe no model, dos templates.
- **CI:** tirar a senha do log do `deploy.sh` (`set +x` em volta e sem `echo` da senha);
  `resource_group` no `deploy-suapdev`.
- **suap-mcp:** lista de variáveis proibidas em `trigger_gitlab_pipeline`.

## Decisões para o Diego

1. **Seguir?** A recomendação é começar pelas fatias 1 e 2 (só leitura, sem custo) e decidir as
   de escrita depois de ver o E1 funcionando em homologação.
2. **Validade:** a proposta é 7 dias por padrão e teto de 15. O teto vale só para a API ou também
   para o admin?
3. **Cota:** quantos ambientes ativos por pessoa e no total? A resposta depende da capacidade do
   `hom-v3`; é preciso perguntar à infraestrutura.
4. **Desenvolvedor:** o grupo ganha `add_ambientehomologacao`, ou a criação continua só com o
   analista?
5. **Senha para o agente:** nunca devolver (proposta), ou devolver só ao criador, para testes
   automatizados no ambiente?
6. **Vínculo antes da etapa:** vincular em "Em desenvolvimento" já mostra a aba Homologação ao
   demandante. Isso é aceitável, ou E2 deve vincular só na etapa Em homologação e guardar o
   vínculo em outro lugar até lá?
