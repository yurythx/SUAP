# Runbook: deduplicação de pessoas físicas

Para a equipe de TI de cada instituição que roda o SUAP (cada uma com o seu banco). O comando `deduplicar_pessoas` une as `PessoaFisica` que têm o mesmo documento (CPF, ou passaporte + ISO 3166-1 alfa-3 do país, `comum.Pais.iso_alfa3`, na forma `ARG-AB123456`), reaponta todas as referências para a sobrevivente e apaga as duplicatas. Ele tem três subcomandos: `planejar` (não altera nenhuma pessoa), `relatorio` (somente leitura) e `aplicar` (altera).

Os números do IFRN citados abaixo são só ordem de grandeza, medidos numa cópia de produção em 10/2026 (≈547 mil pessoas físicas antes, ≈206 mil duplicatas em ≈103 mil grupos, ≈341 mil depois). Meça na sua base com o ensaio da seção "Preparação".

## Visão geral: duas versões, nesta ordem

A deduplicação chega em **duas versões do SUAP**, que devem ser instaladas **nesta ordem**, com o comando rodando **entre** as duas:

- **Release 1 = SUAP 3.21.0** (minor): deploy normal, mas **faça backup antes**.
- **Release 2 = SUAP 4.0.0** (major): **pré-requisito**: estar na 3.21.x com o `deduplicar_pessoas` aplicado e o `relatorio` mostrando `trava da 4.0.0: liberada` (ver "Portão da 4.0.0"). É major justamente porque o `migrate` dela para sem esse passo.

No resto deste documento, "Release 1" e "Release 2" são essas duas versões. As versões 3.21.x seguintes (correções) continuam valendo como Release 1.

| | Release 1 — SUAP 3.21.0 | Release 2 — SUAP 4.0.0 |
|---|---|---|
| O que traz | Remove as colunas fantasmas de FK para pessoa (**irreversível**); cria `rh.DeduplicacaoPessoa` (plano e auditoria) e o índice que falta em `rh_pessoaexterna.pessoa_fisica_id` (rh/0108, rh/0109); traz o comando `deduplicar_pessoas`; fecha a entrada de dados (quase nenhuma duplicata nova nasce); o estrangeiro sem CPF cadastrado a partir dela entra com o login `ARG-AB123456` (ISO do país + passaporte; o login antigo, só com o número, continua valendo) | Constraints no banco: CPF único, par país + passaporte único, documento identificador obrigatório e único, e "sem CPF ⇒ país obrigatório" (rh/0111) |
| `migrate` | Sempre passa | **Para** com `Deduplicação de pessoas pendente (...)` enquanto houver duplicata ou linha pendente/`erro` do comando |
| Pode ficar parado nela? | Sim, por quanto tempo precisar: o sistema funciona normalmente; a entrada de dados impede quase todas as duplicatas novas, e o `relatorio` mostra o que sobrou | É o estado final |

Regras:

1. **Não pule a 3.21.** Instale a 3.21.x e deduplique. Antes de instalar a 4.0.0, rode `planejar` + `relatorio` e exija `trava da 4.0.0: liberada` (ver "Portão da 4.0.0"). Se a sua instituição receber as duas de uma vez, ver "Instalou a Release 2 sem ter deduplicado".
2. **Backup antes da Release 1**: ela apaga colunas e o `aplicar` apaga as pessoas duplicadas. Não há "desfazer" além do backup (ver "Preparação").
3. O `aplicar` exige **janela de manutenção** (ver "Na janela").

### Portão da 4.0.0

Imediatamente antes de instalar a 4.0.0, rode `python manage.py deduplicar_pessoas planejar` e depois `python manage.py deduplicar_pessoas relatorio`. Depois do resumo, o `relatorio` imprime uma linha por contador da trava da rh/0111 (`trava da 4.0.0 — <contador>: <total>`) e, por último, `trava da 4.0.0: liberada` ou `trava da 4.0.0: bloqueada`. Só instale a 4.0.0 com `liberada`: são os mesmos contadores que fazem o `migrate` dela parar.

Rode o portão mesmo que a deduplicação já tenha terminado limpa. Entre a 3.21 e a 4.0.0 a base pode voltar a ter pendência: a corrida rara de dois cadastros simultâneos da mesma pessoa no `obter_ou_criar`, ou uma PF editada à mão no banco. Se a trava estiver `bloqueada`, rode `planejar` → `aplicar` (na janela) e repita o portão.

| Contador da trava | O que é | O que resolve |
|---|---|---|
| `cpf_repetido` | O mesmo CPF em mais de uma PF | `planejar` → `aplicar` (mescla, ou separa quando o nascimento diverge) |
| `passaporte_repetido` | O mesmo par país + passaporte em mais de uma PF | `planejar` → `aplicar` (mescla, ou `passaporte_anulado` com sintético `CONFLITO-…`) |
| `sem_cpf_sem_pais` | PF sem CPF e sem país de origem, sem documento sintético | `planejar` → `aplicar` (`pais_preenchido` pelo aluno; sem aluno, o `aplicar` dá o sintético) |
| `documento_repetido` | O mesmo `documento_identificador` em mais de uma PF | `planejar` → `aplicar` (mescla ou separa) |
| `cpf_ou_passaporte_vazio` | CPF ou passaporte gravado como texto vazio em vez de nulo | `aplicar`, mesmo sem linhas no plano: a higiene normaliza os documentos de todas as PFs |
| `sem_documento` | PF com `documento_identificador` nulo ou vazio | `aplicar`, mesmo sem linhas no plano: a higiene recalcula o documento (CPF, `<ISO 3166-1 alfa-3 do país>-<passaporte>` ou sintético) |
| `info_complementar_repetida` | Mais de uma consulta guardada por pessoa e API externa | `aplicar`, mesmo sem linhas no plano: mantém só a consulta mais recente |
| `deduplicacao_pendente` | Linha do plano ainda pendente, inclusive `erro` | `planejar` de novo (descarta as pendentes e recalcula) → `aplicar`. Havendo `erro`, ver "Recuperar de `erro`" |

## Roteiros

Escolha um. Os dois executam os mesmos passos; mudam só os intervalos entre eles.

### Roteiro A — em etapas (recomendado para quem não ensaiou)

1. **Dia D**: backup → instalar a Release 1 → `migrate`. Sem janela especial: o `migrate` da Release 1 leva cerca de 1 minuto no IFRN.
2. **Dias seguintes**, com o sistema no ar: `planejar` → `relatorio --csv` → revisar o CSV. Nada é alterado; repita quantas vezes quiser.
3. **Janela**: os passos de "Na janela".
4. **Portão** (ver "Portão da 4.0.0"): `planejar` + `relatorio` com `trava da 4.0.0: liberada`. Então instalar a Release 2 → `migrate`. Janela curta (≈1,5 min no IFRN): o `migrate` da 4.0.0 roda com a aplicação parada, ou logo antes do reinício. A trava lê sem lock: uma gravação concorrente entre a verificação e o ALTER faz o `migrate` falhar com erro cru do Postgres, e a atomicidade desfaz tudo. Reinicie a aplicação e o Celery **logo depois** do `migrate` da 4.0.0: código 3.21 ainda no ar pode gravar `documento_identificador` nulo e dar 500.

### Roteiro B — janela única (dois deploys na mesma janela)

Para quem ensaiou numa cópia e revisou o plano antes (seção "Preparação"). No IFRN, a janela fica em cerca de 20–35 minutos (o `aplicar` varia de 11 a 25 minutos conforme a carga do servidor), sem contar o backup:

| # | Passo | IFRN |
|---|---|---|
| 1 | Backup (ou confirmação do backup físico, ver "Preparação") | — |
| 2 | Tirar o SUAP do ar (aplicação e Celery) | — |
| 3 | Deploy da **Release 1** → `python manage.py migrate` | ≈1 min |
| 4 | `python manage.py deduplicar_pessoas planejar` | ≈1 min |
| 5 | `python manage.py deduplicar_pessoas relatorio`: confira se os totais batem com os do ensaio (diferença pequena é normal) | segundos |
| 6 | `python manage.py deduplicar_pessoas aplicar` | 11–25 min conforme a carga |
| 7 | Portão: `python manage.py deduplicar_pessoas planejar` e depois `python manage.py deduplicar_pessoas relatorio`, que deve terminar com `trava da 4.0.0: liberada` (ver "Portão da 4.0.0") | ≈1 min |
| 8 | Se o passo 7 mostrar `trava da 4.0.0: liberada`: deploy da **Release 2** → `python manage.py migrate`. Se mostrar `bloqueada`: **pare aqui** (ver "Se algo der errado") | ≈1,5 min (cria 3 índices únicos, NOT NULL e a CHECK em ≈341 mil PFs, já mescladas) |
| 9 | Subir aplicação e Celery (reinício obrigatório, ver "Na janela") | — |

Com o SUAP fora do ar durante a janela, os passos 4–6 não concorrem com usuários: é o cenário mais seguro.

Passos 8 e 9: o `migrate` da 4.0.0 roda com a aplicação parada, ou logo antes do reinício. A trava lê sem lock: uma gravação concorrente entre a verificação e o ALTER faz o `migrate` falhar com erro cru do Postgres, e a atomicidade desfaz tudo. Reinicie a aplicação e o Celery **logo depois** do `migrate` da 4.0.0: código 3.21 ainda no ar pode gravar `documento_identificador` nulo e dar 500.

## Preparação (antes da janela)

1. **Ensaio numa cópia de produção**, num servidor que não seja o de produção: restaure a cópia, instale a Release 1 nela e rode `migrate` → `planejar` → `relatorio --csv` → `aplicar` → `relatorio`, cronometrando cada um. Isso dá o tempo real da sua janela e revela, sem risco, os problemas da seção "Problemas comuns" (principalmente FKs desconhecidas).
2. **Revisão do plano**: no CSV do ensaio, revise principalmente `mesclada` (quem sobrevive), `separada` (pessoas que **não** foram unidas por terem nascimento diferente) e `campo_descartado`. O CSV tem CPF: guarde com acesso restrito e apague depois.
3. **FKs desconhecidas**: se o `planejar` do ensaio abortou com `FKs para pessoa que o ORM não conhece`, decida com o DBA o que fazer com cada tabela listada **antes** da janela (ver "Problemas comuns").
4. **Backup**: o caminho de volta é restaurar o banco inteiro. Escolha um:
   - `pg_dump -Fc -f suap-antes-dedup.dump <banco>` imediatamente antes de instalar a Release 1 (simples, mas em bancos grandes leva tempo e alonga a janela); ou
   - backup físico recente com arquivamento de WAL (recuperação para o instante anterior à janela), **testado**.
5. **Conexão e servidor**: rode o comando no servidor que roda o `migrate`. Pode ser pelo pgbouncer, inclusive em modo `transaction`: toda leitura em lote do comando acontece dentro de uma transação, e o lock por documento é travado e solto na mesma transação. Duas conferências no pgbouncer: `query_timeout` e `idle_transaction_timeout` precisam estar zerados (o padrão) ou acima da duração do `aplicar`, porque a higiene é uma transação só de alguns minutos. O comando roda com o histórico (`USE_HISTORY`) desligado, mesmo que o servidor o tenha ligado: a auditoria da operação é a `DeduplicacaoPessoa`.

## Os comandos

- **`planejar`**: `python manage.py deduplicar_pessoas planejar`. Imprime o total de linhas planejadas por ação. Não altera `PessoaFisica`: só recria, em `DeduplicacaoPessoa`, as linhas ainda não aplicadas (as aplicadas são mantidas). Pode ser repetido à vontade.
  - Se abortar com `FKs para pessoa que o ORM não conhece (remova ou trate antes de deduplicar): tabela.coluna, ...`, ver "Problemas comuns".
- **`relatorio`**: `python manage.py deduplicar_pessoas relatorio [--csv /caminho/fora/do/media/plano.csv]`. Imprime o resumo `ação (pendente|aplicada): total` e, com `--csv`, grava o plano completo (colunas `id, pf_id, sobrevivente_id, documento, acao, campo, valor_original, motivo, criado_em, aplicado_em`). O CSV é criado com permissão 0600 e o comando recusa caminho dentro do `MEDIA_ROOT`.
- **`aplicar`**: `python manage.py deduplicar_pessoas aplicar [--lote N]`. Aplica a higiene (anular documentos inválidos, sintéticos, separações) e depois mescla os grupos, `N` grupos por transação (padrão 1000). Imprime `higiene`, `mescladas`, `erros`, `apagadas` (pessoas sem relacionamento apagadas; ver a ação `apagada`), `busca` (pessoas com passaporte cuja busca passou a incluir `ARG-AB123456`) e `contatos` (telefones e endereços repetidos apagados: a mescla junta os de todas as cópias da pessoa; só os idênticos saem). Se for interrompido, rode de novo: só o que está pendente é refeito.

## Na janela

O `aplicar` só roda em janela de manutenção: a higiene é **uma transação só** sobre a tabela inteira e ignora o `--lote`; enquanto ela roda, todo `save()` de pessoa física fica bloqueado, inclusive o login pelo gov.br.

1. **Rode `planejar` de novo**, imediatamente antes do `aplicar`, mesmo que já tenha planejado antes. A entrada de dados ficou aberta desde a revisão, e o `aplicar` confere a premissa de cada linha: o que mudou depois do `planejar` (CPF corrigido, PF apagada, nascimento alterado) não é aplicado e vira `erro` com `plano desatualizado (<ação>); rode planejar de novo`.
2. **`aplicar`**. Ordem de grandeza no IFRN: 11–25 minutos conforme a carga, para ≈206 mil duplicatas em ≈103 mil grupos.
3. **Segunda rodada.** Rode `planejar` de novo. Ele costuma achar trabalho que só aparece depois das mesclas: o passaporte de um aluno que veio da duplicata apagada, o país de uma PF separada, uma separação nova. Se o `planejar` gerar linhas, rode `aplicar` outra vez. Repita até o `planejar` não gerar nada (no ensaio do IFRN, a 2ª rodada teve ≈1 mil linhas e levou segundos).
4. **Conferir** com o portão: `planejar` → `relatorio`, que deve terminar com `trava da 4.0.0: liberada` (resumo só com linhas `(aplicada)`, zero `erro`). Havendo `erro`, ver "Recuperar de `erro`"; com outro contador acima de zero, ver "Portão da 4.0.0". No Roteiro A, repita o portão antes de instalar a 4.0.0.
5. **Reinicie os servidores de aplicação e os workers do Celery** logo depois do `aplicar`. Cada processo guarda em memória o vínculo e a pessoa de cada usuário (`User.VINCULOS`/`PESSOAS_FISICAS`), e essas entradas ainda apontam para as PFs apagadas na mescla. O `aplicar` não limpa esse cache: ele só existe dentro de cada processo.

## Se algo der errado

| Onde parou | O que fazer |
|---|---|
| `migrate` da Release 1 falhou | Nada foi deduplicado. Leia o erro; se for `lock_timeout` (outra sessão segurando a tabela), tire o SUAP do ar e repita. Para desistir: restaure o backup e volte à versão anterior. |
| `planejar` abortou (FKs desconhecidas) | Nada foi alterado. Trate as tabelas listadas (ver "Problemas comuns") e repita, ou encerre a janela: a Release 1 pode ficar no ar sem deduplicar. |
| `aplicar` interrompido (queda, cancelamento) | Rode `aplicar` de novo: a higiene é atômica e cada lote de mescla também; só o que está pendente é refeito. |
| `aplicar` terminou com `erros: N` | O resto foi aplicado; os grupos com `erro` ficaram intactos. **Não instale a Release 2** nesta janela. Suba o SUAP na Release 1 (com reinício), resolva os `erro` depois (ver "Recuperar de `erro`") e instale a Release 2 numa próxima oportunidade. |
| `migrate` da Release 2 parou com `Deduplicação de pessoas pendente (...)` | A base ainda tem pendências. Os contadores da mensagem dizem quais. Volte a rodar `planejar` → `aplicar` e o portão (`planejar` + `relatorio` até `trava da 4.0.0: liberada`; o comando já está instalado) e repita o `migrate`. Não force a migration. |
| `migrate` da Release 2 falhou com `canceling statement due to lock timeout` | Outra sessão segurava `pessoa_fisica` (a rh/0111 desiste em 10 s em vez de enfileirar o sistema). A migration foi desfeita por inteiro. Confira que a aplicação e o Celery estão parados (ou sem transações longas abertas) e rode `migrate` de novo. |
| Resultado errado depois do `aplicar` (pessoas unidas indevidamente) | As mesclas não têm desfazer automático. A auditoria (`DeduplicacaoPessoa`, ações `mesclada` e `campo_descartado`) diz o que foi unido e o que foi descartado. Para voltar tudo: restaure o backup. |

## Instalou a Release 2 sem ter deduplicado

Acontece quando a instituição atualiza de uma versão anterior à 3.21 direto para a 4.0.0 (ou posterior). O `migrate` da Release 2 aplica as migrations anteriores (inclusive as da Release 1, de que a rh/0111 depende) e **para** na rh/0111 com `Deduplicação de pessoas pendente (...)`. No IFRN, esse 1º `migrate` (Release 1 + trava) leva ≈ 1 min e para na rh/0111 com os contadores. Exemplo real: `cpf_repetido=103172, passaporte_repetido=10, sem_cpf_sem_pais=1661, documento_repetido=103577, cpf_ou_passaporte_vazio=543117, sem_documento=16682`.

O sistema **não** está pronto para subir: as migrations de outros apps que vêm depois da rh/0111 na ordem podem ter ficado sem aplicar, e o código novo rodaria sobre um schema incompleto. Então, na mesma janela:

1. **Mantenha o SUAP fora do ar** (aplicação e Celery).
2. Confira o backup (a remoção das colunas fantasmas já foi aplicada pelo `migrate`).
3. Siga o Roteiro B a partir do passo 4: `planejar` → `relatorio` → `aplicar` → portão (`planejar` + `relatorio` com `trava da 4.0.0: liberada`) → `python manage.py migrate` de novo. A rh/0111 passa e as migrations que ficaram para trás são aplicadas (≈ 1,5 min no IFRN).
4. Só então suba a aplicação e o Celery (reinício obrigatório, ver "Na janela").

## Ações da auditoria

Cada linha de `DeduplicacaoPessoa` tem uma ação. `Pendente` = `aplicado_em` vazio.

| Ação | Significado |
|---|---|
| `cpf_anulado` | O CPF da PF era inválido (DV errado, dígitos repetidos, tamanho): foi apagado. O valor fica em `valor_original`. A PF passa a ter documento sintético `INVALIDO-…` (ou outro documento, se tiver passaporte com país). |
| `passaporte_anulado` | Passaporte inválido (menos de 5 ou mais de 26 letras e dígitos, de um caractere repetido ou sem nenhum dígito, como "NÃO TENHO" e "SEM PASSAPORTE"), ou repetido entre duas PFs com o mesmo país (fica a de maior prioridade): apagado, valor em `valor_original`. Em repetição, a PF que perdeu recebe sintético `CONFLITO-…` (`SEMDOC-…` se o país não tem ISO 3166-1 alfa-3: ali o passaporte não é documento e nada é mesclado, mas o par repetido também é anulado). |
| `passaporte_preenchido` | A PF não tinha passaporte válido e o aluno vinculado a ela tinha: o passaporte do aluno foi copiado para a PF (`documento`); o anterior fica em `valor_original`. |
| `pais_preenchido` | PF sem CPF e sem país de origem: o país foi inferido do aluno mais recente (brasileiro vira Brasil; o país do estrangeiro é convertido pelo **nome** e, sem correspondência, pela sigla ISO 3166-1 alfa-3 do país do aluno — nunca pelo código, que no `edu` é outro esquema). `documento` guarda o id do país. Com o país, o documento da PF passa a ser `<ISO 3166-1 alfa-3>-<passaporte>` (`comum.Pais.iso_alfa3`), por exemplo `ARG-AB123456`; país sem alfa-3 não forma documento, e a PF recebe sintético `SEMDOC-…`. Sem CPF o país é obrigatório (constraint da Release 2), exceto para documento sintético. |
| `sintetico` | PF sem nenhum documento utilizável recebeu `SEMDOC-<id>`, ou `SEMPAIS-<id>-<passaporte>` se tem passaporte válido mas não tem país (ou `INVALIDO-<id>-<dígitos>` / `CONFLITO-<id>-<doc>`, conforme a origem). `INVALIDO-` e `CONFLITO-` guardam a história e nunca mudam; `SEMDOC-` e `SEMPAIS-` acompanham o passaporte atual (o `aplicar` e o salvar da pessoa os recalculam). Para tirar a PF do `SEMPAIS-`, preencha o país de origem dela: o documento vira `ARG-AB123456`. |
| `mesclada` | `pf_id` é duplicata de `sobrevivente_id`: suas referências foram reapontadas, os campos vazios da sobrevivente preenchidos e a duplicata apagada. A sobrevivente é a de maior prioridade: servidor ativo, depois aluno ativo, depois prestador ativo, depois o maior id. Também aparece entre separadas: as de mesmo documento original e mesmo nascimento viram uma `CONFLITO-` só (inclusive as gravadas por uma rodada anterior), e a `CONFLITO-` volta para a dona do documento original quando o nascimento das duas passa a ser o mesmo (ex.: alguém corrigiu o nascimento errado); a dona fica com o documento. |
| `separada` | Duas PFs com o mesmo documento que **não** são a mesma pessoa (nascimentos diferentes) ou que não podem ser unidas (colide em tabela com referência 1:1): a perdedora perde o documento e recebe sintético `CONFLITO-<id>-<doc original>`. Com nascimentos diferentes, fica com o documento o nascimento do servidor ativo (vem do SIAPE) ou, sem ele, o que aparece em mais PFs do grupo (empate: a prioridade de `mesclada`); as PFs dos outros nascimentos são separadas e as de mesmo nascimento entre si viram uma só. O documento original fica em `valor_original`; o motivo, em `motivo`. **Exceção:** se a PF separada tinha CPF e também passaporte com país válidos, ela perde só o CPF e o documento final passa a ser o do passaporte com o ISO 3166-1 alfa-3 do país (`comum.Pais.iso_alfa3`), por exemplo `ARG-AB123456`, não o `CONFLITO-…` que aparece na coluna `documento` do plano. Ver "Corrigir uma PF `CONFLITO-…`". |
| `apagada` | A PF não tinha relacionamento: nenhum vínculo, servidor, aluno, prestador ou objeto genérico (GFK) apontava para ela. Não contam endereço, telefone, contato de emergência, informação complementar, pessoa externa, biometria e solicitação de biometria, nem o vínculo da própria pessoa externa quando não tem usuário (o salvar da externa o cria): o DELETE os leva junto. Se outra tabela usa esse vínculo ou a pessoa externa (participante de evento, prontuário, viagem…), a PF fica. `documento` guarda o documento que ela tinha. Quem está num grupo de mesmo documento com alguém relacionado é mesclado, não apagado; o grupo todo sem relacionamento é apagado inteiro. Não entra a PF cujo DELETE levaria ou anularia outra coisa (ex.: pessoa externa legada com setores adicionais). No `aplicar`, a PF que ganhou relacionamento depois do `planejar` fica: a linha é marcada aplicada com `motivo` = `não apagada: …`. Na `suap_dev` (10/2026): 5.867 de 340 mil, 4.908 delas `SEMDOC-`. |
| `campo_descartado` | Na mescla, a sobrevivente já tinha valor no campo e a perdedora tinha outro: o da perdedora foi descartado. O valor fica em `valor_original`. Para biometria (`template`) e `senha_ponto` a divergência é auditada **sem o valor** (`motivo` = `valor omitido (biometria/senha)`). |
| `divergencia_entrada` | Gerada pela entrada de dados, depois do deploy (não pelo comando): uma fonte autoritativa (ex.: SIAPE) informou uma data de nascimento diferente da gravada. O dado foi atualizado e a divergência registrada, já como aplicada. |
| `erro` | Duas origens, sempre com o `motivo`. **Mescla:** o grupo de `sobrevivente_id` não pôde ser mesclado (`pf_id` = `sobrevivente_id`); nada foi alterado para esse grupo. **Higiene:** a linha de higiene de `pf_id` não foi aplicada porque o dado mudou depois do `planejar` (`sobrevivente_id` vazio; `campo` e `valor_original` são os da linha original; `motivo` = `plano desatualizado (<ação>); rode planejar de novo`, com a ação original da linha); nada foi alterado nessa PF. Fica **pendente de propósito**, para a Release 2 recusar o `migrate`. |

## Recuperar de `erro`

1. Gere o CSV (`relatorio --csv`) e leia o `motivo` das linhas `erro`. Com `sobrevivente_id` preenchido, é um grupo de mescla (`pf_id` = `sobrevivente_id` = a sobrevivente do grupo); sem ele, é uma linha de higiene da PF `pf_id`.
2. Causas típicas:
   - `PF do plano não existe mais: …; rode planejar de novo`: alguém apagou uma PF depois do `planejar`. Plano desatualizado, não é defeito.
   - `… mudou depois do planejar; rode planejar de novo` (mescla) ou `plano desatualizado (<ação>); rode planejar de novo` (higiene): o documento ou o nascimento de uma PF mudou entre o `planejar` e o `aplicar`. Nada foi alterado nela; replaneje.
   - `O DELETE apagaria: <app.Model>, …`: a perdedora ainda tem dependentes que o reapontamento não cobre. Trate o model citado (ou avise a equipe do SUAP) antes de repetir.
   - Erro de banco (violação de unicidade, FK etc.): o texto do banco está no `motivo`. Uma colisão de índice único fica como `erro` em vez de apagar dado.
3. Corrija a causa e **refaça o plano**: `planejar` descarta as linhas pendentes (inclusive os `erro`) e recalcula tudo a partir do estado atual; as já aplicadas são mantidas. Depois `relatorio`, `aplicar` e `relatorio` de novo.
4. Rodar só `aplicar` de novo também retenta o grupo, mas não limpa os `erro` antigos; prefira `planejar` antes.

## Corrigir uma PF `CONFLITO-…`

A pessoa continua existindo com documento sintético até alguém informar o documento correto.

1. Localize a PF pelo `pf_id` do relatório (ação `separada`) e confira em `valor_original` o documento que ela tinha.
2. Abra a tela da pessoa e informe o **CPF certo** (ou passaporte e país). O `save()` troca o documento sintético pelo real.
3. Se o formulário recusar com "Já existe uma pessoa física com este CPF", o CPF certo já é de outra PF. Então são a mesma pessoa, separada porque uma das duas tinha a data de nascimento errada:
   1. Corrija a data de nascimento errada para que as duas fiquem iguais (na PF que tem o CPF ou na `CONFLITO-…`).
   2. Rode `planejar` → `relatorio` → `aplicar`. O `planejar` devolve a `CONFLITO-…` para a dona do documento original (linha `mesclada`), e a dona fica com o CPF.

   Funciona antes e depois da Release 2 (4.0.0): a PF separada não tem CPF, então a mescla não esbarra na unicidade.

   Sem janela e sem rodar o comando na base inteira: use a tela "Unificar duas PFs à mão" (abaixo), com a dona do CPF como a pessoa que fica.

## Unificar duas PFs à mão (tela)

`/rh/unificar_pessoas/`, só para superusuário. Para o caso pontual depois da deduplicação: uma `CONFLITO-…` que é a mesma pessoa que a dona do CPF, ou duas PFs com documentos diferentes que são a mesma pessoa (ex.: cadastro com CPF errado).

1. Escolha no autocomplete (busca por nome, CPF ou usuário) a pessoa que **fica** e a que **sai** e envie: a tela mostra as duas, os vínculos de cada uma e os campos que a que sai preenche ou que serão descartados. Nada é alterado.
2. Marque "Confirmo a unificação" e envie de novo. A unificação usa o mesmo motor do `aplicar` (reaponta as referências, preenche os campos vazios da que fica e apaga a que sai), numa transação só: qualquer falha não altera nada e a mensagem diz o motivo.

Diferenças em relação ao `aplicar`: não confere documento nem nascimento (quem escolhe responde pela escolha; o nascimento divergente da que sai fica como `campo_descartado`) e não depende do `planejar`. A tela recusa a pessoa que fica com documento sintético quando a que sai tem documento: inverta as duas. A auditoria fica em `DeduplicacaoPessoa` (`mesclada` com `motivo` = `unificação manual por <usuário>` e `documento` = o documento da que sai, mais os `campo_descartado`). Não há desfazer. Os servidores de aplicação não são reiniciados: o usuário da pessoa que sai pode ver erro até o próximo reinício.

## Problemas comuns

| Sintoma | Causa e solução |
|---|---|
| `planejar` aborta com `FKs para pessoa que o ORM não conhece` | Há tabelas com FK para `pessoa`/`pessoa_fisica` que nenhuma migration do SUAP cria (criadas à mão ou por sistemas legados). A mensagem já traz, com os nomes da sua base, os dois caminhos: arquivar (`pg_dump`) e apagar a tabela, ou manter a tabela e tirar só a FK (`ALTER TABLE … DROP CONSTRAINT …`). O DBA escolhe por tabela e repete o `planejar`. No IFRN: `financeiro_empenho`, `temp_rh_resposta` e `temp_enquete_cnat_resposta`. Confira o que a tabela contém antes de apagar: ela entra no backup (ver "Preparação"). |
| `erro` com `rode planejar de novo` | Plano desatualizado: rode `planejar` e `aplicar`. |
| `País sem código ISO 3166-1 alfa-3` | Preencha o campo ISO 3166-1 alfa-3 do país no admin de Países. Estrangeiros desse país, sem CPF, já gravados com sintético ganham a chave no próximo `planejar`/`aplicar`. Preencheu o ISO de um país? Rode `planejar` antes do `aplicar`. |
| `relatorio --csv` falha com `grave fora do MEDIA_ROOT` | Escolha um caminho fora do `MEDIA_ROOT` (por exemplo `/var/tmp`). O CSV tem CPF e o `MEDIA_ROOT` é servido pelo web. |
| `--lote` recusado | Aceita só inteiro ≥ 1. |
| `aplicar` lento ou travando outras sessões | A higiene é uma transação única e bloqueia gravações de pessoa até terminar: só rode na janela. Na mescla, reduza o `--lote`; cada lote é uma transação e o comando retoma de onde parou. |
| `aplicar` cai com `query_timeout`/conexão encerrada pelo pgbouncer | Timeout do pgbouncer menor que a transação da higiene. Aumente (ou zere) `query_timeout`/`idle_transaction_timeout` durante a janela, ou conecte direto no Postgres, e rode `aplicar` de novo (retoma). |
