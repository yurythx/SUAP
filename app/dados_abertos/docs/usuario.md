# Dados Abertos

Conduz o **Plano de Dados Abertos (PDA)** da instituição do começo ao fim: define o grupo de trabalho, cataloga os conjuntos de dados que serão abertos, prioriza-os segundo os critérios da Resolução nº 3/2017, submete cada um à análise do Responsável LAI e, por fim, publica os dados no **CKAN** — o catálogo público onde o cidadão os encontra. O mesmo módulo gera o documento oficial do plano, versionado, e mantém a área pública em que ele é divulgado.

O trabalho acontece em **cinco etapas na ordem** — Grupo de Trabalho, Conjuntos de Dados, Consulta Pública, Priorização, Abertura e Publicação. O sistema só avança para a etapa seguinte quando as ações obrigatórias da atual estão resolvidas, e a maior parte delas é marcada **automaticamente**, a partir do que existe de fato no plano: não há o que marcar à mão.

- **Ponto de partida:** integração com o CKAN ativa e organização publicadora cadastrada.
- **Ponto de chegada:** bases visíveis no CKAN, com identificador remoto preenchido, e o documento do plano publicado na área pública.
- **Tela de trabalho:** **Dados Abertos › Dashboard**.

**Quem usa este módulo**

| Perfil | O que faz aqui |
| --- | --- |
| Gestor de Dados Abertos Sistêmico | Conduz o plano de ponta a ponta: organizações, bases, recursos, matriz de priorização, dispensa de etapa e sincronização com o CKAN |
| Membros do Grupo de Trabalho | Prioriza as bases na matriz, com acesso completo a ela; consulta organizações, bases e recursos sem alterá-los. Entra no grupo automaticamente quem é responsável ativo no grupo de trabalho de um plano vigente |
| Servidor | Consulta os planos, sem nenhuma opção de alteração |
| Responsável LAI | Analisa o conteúdo de cada base antes da publicação e decide: libera ou devolve para ajustes |
| Equipe de TI | Cadastra e ativa as credenciais do CKAN. Uma única vez, na implantação |
| Cidadão | Consulta os planos, os documentos e os dados publicados, sem ter conta no SUAP |

---

## Antes de começar

**1. Confirme suas permissões.** Os três grupos acima cobrem organizações, bases, recursos, a dispensa de etapa, a matriz de priorização e a deliberação do LAI — mas **não** incluem criar o plano, vincular bases a ele, cadastrar o grupo de trabalho, editar tópicos nem gerar versões. Essas telas exigem permissões que nenhum perfil padrão do SUAP concede e que precisam ser atribuídas individualmente: **hoje o roteiro completo pressupõe um usuário com perfil administrativo**. Alinhe isso com a TI antes de começar.

**2. Ative a integração com o CKAN.** É tarefa da TI, feita uma vez, em **Tec. da Informação › Cadastros › APIs Externas**, no registro **CKAN** — que já vem cadastrado e **inativo**. Complete e ligue:

| Campo | O que informar |
| --- | --- |
| URL Base da API | Endereço do servidor CKAN, sem barra no final |
| Secret or API KEY | A chave da API, enviada a cada chamada ao CKAN |
| Ativo | O interruptor da integração |

Enquanto **Ativo** estiver desmarcado, toda tentativa de sincronização responde *"API CKAN não configurada ou inativa."*, e a aba **CKAN** do dashboard mostra *API inativa* ao lado do título, com um aviso de que nenhuma base pode ser sincronizada.

**3. Aplique a estrutura de etapas do plano.** Também uma vez, pela linha de comando, com o comando `configurar_etapas_padrao` — peça à TI. Ele cria as **5 etapas e as 11 ações** do fluxo. É um passo **manual e deliberado**: não roda no deploy, porque **substitui a estrutura vigente** e, com ela, **zera o progresso do checklist dos planos já existentes**. As dispensas de etapa já registradas são preservadas. Numa instalação nova, sem esse passo o dashboard exibe um checklist vazio.

**4. Confira os cadastros de apoio.** Licenças, Temas, Palavras-chave e Áreas alimentam o cadastro das bases. Os **Critérios da Matriz** já vêm carregados, transcritos da **Resolução nº 3/2017 do CGINDA** — desmarque **Ativo** nos que a instituição não usar, porque **só os ativos viram coluna** na matriz de priorização.

---

## Tarefas

### 1. Cadastrar e sincronizar a organização publicadora

**Quem pode:** Gestor de Dados Abertos Sistêmico.
**Quando usar:** na implantação, antes de qualquer base. A organização é quem **publica** os dados no CKAN, e todo conjunto enviado precisa apontar para ela.

1. No menu, acesse **Dados Abertos › Organizações**.

   ![Listagem de organizações](usuario/organizacao-listagem.webp)

2. Clique em **Adicionar Organização** e preencha:

   | Campo | O que informar |
   | --- | --- |
   | Título | Nome de exibição da unidade publicadora |
   | Identificador | **Preenchido sozinho** a partir do título, e não editável — é a chave do registro no CKAN |
   | Descrição | Texto que aparece no catálogo público |
   | Imagem / URL da imagem | Logotipo exibido no CKAN. O **arquivo enviado tem precedência** sobre a URL |
   | Estado | *Ativa* ou *Excluída*, refletindo o estado no CKAN |

   ![Formulário da organização](usuario/organizacao-formulario.webp)

3. Clique em **Salvar**.
4. De volta à listagem, clique no **ícone de sincronizar** (as setas em círculo) na linha da organização.

**Resultado:** *"Organização sincronizada com sucesso."* e a coluna **ID remoto** deixa de estar em branco — é a prova de que a organização existe no CKAN.

![Organização já sincronizada, com ID remoto preenchido](usuario/organizacao-sincronizada.webp)

> **Se o campo *URL da imagem* trouxer algo que não é um endereço**, como `2026-08-26-125357.123456logo.png`, é resíduo de uma versão anterior que gravava ali o nome do arquivo devolvido pelo CKAN. O valor é ignorado no envio e não causa dano; para limpar, basta apagar o campo e salvar.

> **A imagem sobe junto, ou a sincronização acusa erro.** Se o arquivo anexado não puder ser lido, ou se o CKAN aceitar a atualização sem registrar a imagem, a tela informa o problema em vez de dizer que deu certo. Uma organização marcada como sincronizada é uma organização com o logotipo no lugar — se aparecer *"o CKAN aceitou a atualização … mas não registrou a imagem enviada"*, o caminho é a TI conferir o `ckan.storage_path` e o limite de upload do servidor.

> **Sincronize a organização antes de qualquer base.** O conjunto de dados é enviado ao CKAN com o dono preenchido a partir do **ID remoto da organização**; se ele estiver vazio, o conjunto chega ao catálogo **sem dono**.

> **Depois de sincronizado, não altere o identificador.** Ele é a chave do registro no CKAN — alterá-lo faz o SUAP criar um registro novo lá e deixa o antigo órfão. Mude o título à vontade; o identificador, não.

---

### 2. Abrir o Plano de Dados Abertos e acompanhar pelo dashboard

**Quem pode:** exige as permissões de cadastrar e alterar Plano de Dados Abertos, que **nenhum perfil padrão do SUAP concede** — o acesso é atribuído individualmente. O item **Dashboard** aparece no menu para quem pode consultar o plano — todo servidor pode. Quem só consulta vê o checklist, mas não marca ações nem dispensa etapas.

1. No menu, acesse **Dados Abertos › Plano de Dados Abertos** e clique em **Adicionar Plano de Dados Abertos (PDA)**.
2. Preencha:

   | Campo | O que informar |
   | --- | --- |
   | Título do PDA | Nome do plano, como sairá no documento |
   | Situação | Comece em *Rascunho*. **Ela é sempre manual** — o sistema nunca a muda |
   | Vigência - início / fim | Período de vigência do plano; **as duas datas são obrigatórias** |
   | Data de publicação | Deixe em branco; preencha quando o plano for de fato publicado |

   ![Formulário do plano](usuario/pda-formulario.webp)

   Na mesma tela ficam os blocos de **Capa**, **Tópicos do documento**, **Bases de Dados no PDA** e os cronogramas de **Elaboração e Sustentação** e de **Promoção, Fomento, Uso e Reúso** — todos podem ser preenchidos depois.

3. Clique em **Salvar**. O plano nasce na versão **1.0.0**.
4. No menu, acesse **Dados Abertos › Dashboard**.

**Resultado:** o checklist é montado **na primeira visita ao dashboard** — o sistema cria as onze ações deste plano e posiciona o plano na **Etapa 1**.

![Dashboard, aba Etapas, com o checklist recém-criado](usuario/dashboard-etapas.webp)

O dashboard tem três abas — **Etapas** (checklist e progresso), **Plano de Ação** (pendências por base) e **CKAN** (situação de sincronização) — e um seletor no topo para trocar de plano quando houver mais de um.

Quem tem pendência recebe um resumo semanal por notificação, toda segunda-feira: cada responsável vê só o que é seu, e o Gestor de Dados Abertos Sistêmico e o grupo de trabalho recebem o agregado do plano. As pendências são as mesmas da aba **Plano de Ação**.

Cada ação do checklist é marcada **Automática** ou fica com a caixa liberada para marcação manual. As automáticas são reavaliadas **a cada abertura do dashboard**, a partir do estado real do plano: se você fez algo em outra tela e o checklist parece parado, **recarregue o dashboard** — é ali que a reavaliação acontece.

---

### 3. Definir o grupo de trabalho (Etapa 1)

**Quem pode:** exige as permissões de cadastrar Grupo de Trabalho e Responsável do Grupo de Trabalho, que nenhum perfil padrão do SUAP concede — o acesso é atribuído individualmente.

**Primeiro, o grupo**

1. No menu, acesse **Dados Abertos › Grupo de Trabalho › Grupo de Trabalho** e clique em **Adicionar Grupo de Trabalho**.
2. Escolha o **PDA**, escreva a **Descrição** e mantenha a **Situação** em **Ativo** — grupos *Finalizado* ou *Cancelado* não contam para o fluxo. Clique em **Salvar**.

   ![Formulário do grupo de trabalho](usuario/grupo-trabalho-formulario.webp)

**Depois, os responsáveis**

3. No menu, acesse **Dados Abertos › Grupo de Trabalho › Responsável do Grupo de Trabalho** e clique em **Adicionar Responsável**.
4. Escolha o **Grupo de Trabalho**, informe o **Responsável** e mantenha **Ativo?** marcado. Clique em **Salvar**. Repita para cada integrante.

   ![Formulário do responsável](usuario/responsavel-formulario.webp)

**Resultado:** a ação *Definir grupo de trabalho e responsáveis* fecha sozinha e a Etapa 1 fica concluída — mas **só quando existe um grupo ativo com pelo menos um responsável ativo**. Grupo sem gente não fecha a etapa. Cada responsável ativo passa também a integrar o perfil **Membros do Grupo de Trabalho** no próximo acesso, o que lhe dá a matriz de priorização (tarefa 6); ao sair do grupo, ou ao fim da vigência do plano, perde o perfil.

![Etapa 1 concluída no checklist](usuario/dashboard-etapa-1-concluida.webp)

A outra ação da etapa, *Registrar portaria de designação*, é **manual e opcional**: serve de registro documental e não bloqueia o avanço.

---

### 4. Cadastrar os conjuntos de dados e vinculá-los ao plano (Etapa 2)

**Quem pode:** cadastrar a base é do Gestor de Dados Abertos Sistêmico; **vincular a base ao plano** exige uma permissão que nenhum perfil padrão concede, atribuída individualmente.

**Primeiro, a base de dados**

1. No menu, acesse **Dados Abertos › Conjuntos da Dados › Base de Dados** e clique em **Adicionar Base de Dados**.

   ![Listagem de bases de dados](usuario/base-listagem.webp)

2. Preencha:

   | Campo | O que informar |
   | --- | --- |
   | Título | Nome do conjunto no catálogo público |
   | Identificador | Preenchido sozinho a partir do título e não editável — **é a chave no CKAN**, e vale para ele o mesmo aviso da tarefa 1 |
   | Notas | A descrição que o cidadão lê no catálogo |
   | Organização | **Obrigatória** — é o dono do conjunto no CKAN (tarefa 1) |
   | Licença / Tema / Tags | Metadados de catalogação; alimentados pelas tabelas de apoio |
   | Estado | Mantenha *Ativa* |

   ![Formulário da base de dados](usuario/base-formulario.webp)

3. Clique em **Salvar**.

Na listagem, a coluna **Situação** funciona como termômetro do conjunto ao longo de todo o roteiro:

`Não vinculada a PDA` → `Sem recurso` → `Aguardando envio ao LAI` → `Em análise do LAI` → `Devolvida para ajustes` → `Liberada (aguardando sincronização)` → `Sincronizada com o CKAN`

![Base recém-cadastrada, ainda sem vínculo](usuario/base-listagem-nao-vinculada.webp)

**Depois, o vínculo com o plano e o cronograma de abertura**

4. No menu, acesse **Dados Abertos › Conjuntos da Dados › Bases Relacionadas** e clique em **Adicionar Base de Dados no PDA** — ou use o bloco *Bases de Dados no PDA* dentro do próprio plano.
5. Escolha o **PDA** e a **Base de Dados** e preencha o **Cronograma de Abertura de Bases**, exigido pela Resolução nº 3/2017:

   | Campo | O que informar |
   | --- | --- |
   | Unidade Responsável pela Abertura / Responsável | Quem responde pela abertura desta base |
   | Meta/Prazo de Abertura | Data prevista de publicação — é ela que gera o alerta de **prazo vencido** na aba Plano de Ação |
   | Frequência de Atualização | Governa a cobrança de **ressincronização** depois de publicada (tarefa 11) |
   | Herdada | Marque quando a base vier de um plano anterior |
   | Em revisão | Marque quando a base estiver sendo revista |

   ![Formulário do vínculo com o plano](usuario/vinculo-formulario.webp)

**Resultado:** *"Cadastro realizado com sucesso."* e a ação *Vincular os conjuntos de dados ao PDA* fecha sozinha — basta **um** vínculo. A ação *Classificar por tema e descrever os conjuntos* fica como registro **manual e opcional**.

A aba **Plano de Ação** do dashboard passa a contar o que ainda falta — prazo vencido, sem responsável, sem prazo e sem recurso de dados — e traz o cronograma com uma linha por base: responsável, meta de abertura e situação de publicação no CKAN.

![Aba Plano de Ação](usuario/dashboard-plano-de-acao.webp)

---

### 5. Dispensar (ou realizar) a consulta pública (Etapa 3)

**Quem pode:** Gestor de Dados Abertos Sistêmico — é o único grupo com a permissão de pular etapa.
**Quando usar:** quando o plano não passar por consulta pública, ou quando ela tiver ocorrido fora do sistema.

> **Ainda não há tela para cadastrar uma consulta pública.** O registro existe no sistema, mas sem interface própria; como a ação automática desta etapa só fecha quando existe uma consulta cadastrada, o caminho praticável hoje é **dispensar a etapa** — que é a única dispensável do fluxo, desenhada assim por causa disso.

1. No dashboard, aba **Etapas**, localize o cartão **3. Consulta Pública** e clique em **Pular etapa**.
2. Escreva a **Justificativa da dispensa** e clique em **Confirmar dispensa**.

   ![Formulário de dispensa da etapa](usuario/dashboard-pular-etapa.webp)

**Resultado:** o cartão passa a exibir a tarja **Etapa dispensada**, a etapa conta como resolvida e o fluxo segue para a Priorização. O sistema registra **quem dispensou, quando, o IP e o navegador** — é um ato auditável, então escreva uma justificativa que se sustente numa auditoria.

![Etapa 3 dispensada](usuario/dashboard-etapa-dispensada.webp)

Para desfazer, use **Reativar etapa** no mesmo cartão: a dispensa é removida e a etapa volta a pesar no fluxo.

---

### 6. Priorizar as bases na matriz (Etapa 4)

**Quem pode:** Membros do Grupo de Trabalho e Gestor de Dados Abertos Sistêmico — consultam, salvam e finalizam a matriz. Quem entra no grupo é decidido pela tarefa 3: todo responsável ativo no grupo de trabalho de um plano vigente passa a fazer parte dele automaticamente.

1. No menu, acesse **Dados Abertos › Matriz de Priorização › Matriz de Priorização**.
2. Havendo mais de um plano cadastrado, escolha o **Plano de Dados Abertos** no seletor do topo — a matriz opera sobre o plano selecionado, e a escolha é mantida ao salvar.
3. A tabela traz as bases do plano nas linhas (identificadas pelo **identificador**, não pelo título), a coluna **CP** com o resultado da consulta pública e uma coluna **C1, C2, …** por critério ativo. A legenda embaixo diz o que é cada uma.

   ![Matriz de priorização em branco](usuario/matriz-vazia.webp)

4. Para cada cruzamento, escolha *Não se aplica*, *Baixo*, *Médio* ou *Alto* e clique em **Salvar**. Pode salvar quantas vezes quiser.

   ![Matriz preenchida](usuario/matriz-preenchida.webp)

**Resultado:** *"Notas salvas com sucesso."*

5. Quando a avaliação estiver fechada, clique em **Finalizar**.

**Resultado:** *"Avaliações finalizadas com sucesso."*, a ação *Finalizar a matriz de priorização* fecha sozinha e a tela passa a informar que todas as bases do plano foram avaliadas.

![Matriz finalizada](usuario/matriz-finalizada.webp)

> **Finalizar não tem volta pela interface.** Os cruzamentos deixados em branco são gravados como *Não se aplica* e toda a matriz é travada; depois disso a tela ignora alterações, apenas informando quantas foram ignoradas. Revise tudo antes de clicar.

Só é possível finalizar quando **todas** as bases do plano têm ao menos uma nota; caso contrário a tela recusa com *"Não é possível finalizar. Todas as bases devem ter uma avaliação cadastrada."*. A ação opcional *Aprovar a relação final com o grupo de trabalho* fica no checklist para registro da validação colegiada.

---

### 7. Cadastrar o recurso de cada base e enviá-la ao LAI (Etapa 5)

**Quem pode:** Gestor de Dados Abertos Sistêmico.
**Pré-condição:** a base já está vinculada ao plano (tarefa 4).

O **recurso** é o arquivo que vai efetivamente ao ar — sem ele não há o que publicar nem o que o Responsável LAI avaliar.

1. No menu, acesse **Dados Abertos › Conjuntos da Dados › Recurso de Dados** e clique em **Adicionar Recurso** — ou use o bloco *Recursos* dentro da própria base.
2. Preencha:

   | Campo | O que informar |
   | --- | --- |
   | Base de Dados | O conjunto a que o arquivo pertence |
   | Nome / Descrição | Como o recurso aparece no catálogo |
   | Formato | Apenas **CSV** ou **JSON** |
   | URL **ou** Arquivo | Pelo menos um dos dois. Informando a **URL**, o SUAP baixa o conteúdo ao salvar, anexa como arquivo com nome datado (ex. `contratos_20260810_103245.json`) e detecta o tipo; se o endereço estiver fora do ar, o cadastro falha — resolva a origem e salve de novo |

   ![Formulário do recurso](usuario/recurso-formulario.webp)

3. Clique em **Salvar**.
4. Abra o **Dashboard**.

**Resultado:** a ação *Cadastrar recurso em ao menos uma base priorizada* fecha assim que **uma** base do plano tem recurso (a aba **Plano de Ação** continua listando as que ainda estão sem, para você não perder o resto de vista), o plano chega à **Etapa 5 — Abertura e Publicação** e, nesse momento, o sistema **envia à análise do LAI** todas as bases que estejam *Pendente* **e tenham ao menos um recurso**. Base sem recurso permanece pendente: sem recurso não há prévia do conteúdo para o LAI avaliar.

![Etapa 5 em curso](usuario/dashboard-etapa-5.webp)

**Para enviar fora desse momento** — uma base cadastrada depois, ou uma que foi devolvida — selecione os registros em **Bases Relacionadas** e use a ação em lote **Enviar/Reenviar ao LAI (datasets pendentes ou devolvidos)**. Os que estiverem sem recurso não são enviados, e a tela avisa quantos ficaram de fora.

---

### 8. Deliberar sobre cada base

**Quem pode:** Responsável LAI.
**Quando usar:** sempre que houver base em análise — é o passo que autoriza (ou barra) a publicação.

1. No menu, acesse **Dados Abertos › Deliberação LAI** e, se houver mais de um plano, escolha o **Plano de Dados Abertos** no seletor do topo.
2. Cada base em análise vem num quadro com a organização, a situação e, para cada recurso, uma **prévia real do conteúdo** — os cinco primeiros registros e até vinte colunas, lidos do arquivo anexado. É sobre esse conteúdo que a decisão é tomada.

   ![Tela de deliberação, com a prévia dos dados](usuario/deliberacao-lai.webp)

3. Escreva o **Parecer** e clique em **Liberar** ou em **Devolver para ajustes**.

**Resultado:** *"Deliberação registrada."* Ao liberar, a base fica apta a ir ao CKAN; ao devolver, ela volta ao gestor para correção — e nesse caso **o parecer é obrigatório**: sem texto o sistema recusa a devolução. Cada deliberação vira registro permanente, com autor, data, IP e navegador.

![Depois de liberar: a base sai da lista e nada mais fica em análise](usuario/deliberacao-lai-liberada.webp)

A ação *Liberação de ao menos uma base pelo Responsável LAI* fecha assim que **uma** base do plano é liberada — a abertura é incremental, e uma base devolvida não segura o checklist do plano inteiro. A fila de análise e a aba **Plano de Ação** seguem mostrando o que falta.

> **A liberação é anulada por edição.** Alterar título, notas, tags, tema, licença ou organização de uma base já liberada — ou alterar o conteúdo de um recurso dela (nome, descrição, formato, URL, arquivo), ou acrescentar um recurso novo — devolve a base para *Em análise do LAI*, com o motivo *"Reaberto por edição do conteúdo"* visível nesta tela. Feche a revisão de conteúdo **antes** de acionar o LAI; depois de qualquer edição, conte com um novo ciclo de deliberação.
>
> Sincronizar com o CKAN **não** conta como edição: gravar o resultado do envio (`ID remoto` e data da última sincronização) é registro da publicação, não alteração do dado publicado.

![Base reaberta por edição do conteúdo](usuario/deliberacao-lai-reaberta.webp)

---

### 9. Sincronizar as bases com o CKAN

**Quem pode:** Gestor de Dados Abertos Sistêmico.
**Pré-condição:** organização sincronizada (tarefa 1), base com recurso (tarefa 7) e liberação do LAI (tarefa 8).

1. No **Dashboard**, abra a aba **CKAN**. O título indica se a integração está ativa, os contadores resumem o plano (bases sincronizadas, com periodicidade atrasada e sem configuração mínima) e a tabela mostra, por base, o estado da sincronização e a aderência à periodicidade.

   ![Aba CKAN antes do primeiro envio](usuario/dashboard-ckan-antes.webp)

2. Clique em **Sincronizar** na linha da base. É o caminho recomendado: envia de uma vez o conjunto **e** todos os seus recursos.

**Resultado:** *"Sincronização com o CKAN concluída. Dataset: 1 sucesso(s). Recursos: 1 sucesso(s)."* e a coluna **Sincronização** passa a exibir *Dataset e recursos sincronizados*, com quantos recursos subiram e a data do envio.

![Base sincronizada — logo após o envio, com o progresso ainda em 86% pelo motivo do aviso abaixo](usuario/dashboard-ckan-sincronizado.webp)

Se algo falhar, a mensagem informa quantos tiveram sucesso e quantos deram erro, e a coluna mostra o estado intermediário — *Sincronização parcial* ou *Dataset sincronizado, recursos pendentes* — indicando que parte dos recursos não subiu. Repita e confira a mensagem.

**Quando o botão não aparece, ou a sincronização é recusada:**

| Situação | O que a tela diz | Onde resolver |
| --- | --- | --- |
| Integração CKAN inativa | *API inativa* no título da aba, com o aviso *a API externa do CKAN não está configurada ou está inativa* / *API CKAN não configurada ou inativa* | Antes de começar, passo 2 |
| Base não liberada pelo LAI | *A base possui datasets pendentes, em análise ou devolvidos pelo Responsável LAI…* | Tarefa 8 |
| Base sem recurso com fonte | *Nenhum recurso cadastrado.* ou *Recursos sem URL ou arquivo configurado.* na coluna **Sincronização** | Tarefa 7 |
| Usuário sem permissão | *você pode acompanhar a situação das bases, mas não tem permissão para sincronizá-las* | Antes de começar, passo 1 |

> **Sincronizar não reabre a análise do LAI.** Gravar o resultado do envio (`ID remoto` e data da sincronização) é registro da publicação, não alteração do conteúdo: a base sincronizada continua *Liberada* e o checklist fecha em **100%** sem uma nova deliberação.
>
> O que reabre a análise é mudar o dado publicado — trocar a URL de um recurso, substituir o arquivo, renomear, ou acrescentar um recurso novo (tarefa 11). Aí sim a base volta para *Em análise do LAI* e precisa de nova liberação antes de ir ao ar.

**Resultado final:** com a última ação obrigatória fechada, o progresso geral chega a **100%** e a faixa de etapas passa a marcar **Concluído**. As bases estão publicadas no CKAN.

![Plano concluído, 100%](usuario/dashboard-concluido.webp)

**Pela administração de bases** existe o caminho em duas partes — os ícones **Sincronizar Dataset** e **Sincronizar Recursos** na listagem de *Base de Dados*, também disponíveis como ações em lote. Nesse caminho a **ordem importa**: recursos de um conjunto que ainda não foi sincronizado são ignorados sem erro visível. O botão único da aba CKAN evita esse problema.

> **Identificador que já foi usado e "excluído" no CKAN continua ocupado.** O CKAN não apaga um conjunto de fato: marca-o como excluído, e o identificador segue reservado. Se a sincronização de uma base nova esbarrar nisso, reative o registro no CKAN ou dê outro título à base no SUAP, para que ela nasça com outro identificador.

---

### 10. Montar e publicar o documento do plano

**Quem pode:** exige as permissões de cadastrar tópicos e gerar versões do plano, que nenhum perfil padrão do SUAP concede — o acesso é atribuído individualmente.

**Primeiro, os tópicos**

1. No menu, acesse **Dados Abertos › Cadastros › Tópicos** e clique em **Adicionar Tópico do documento do PDA** — ou use o bloco *Tópicos do documento do PDA* dentro do plano.
2. Escolha o **PDA**, dê um **Título do tópico** (Resumo, Objetivos, Metodologia…), escreva o **Conteúdo** no editor de texto e informe a **Ordem no documento**.

   ![Formulário do tópico](usuario/topico-formulario.webp)

No texto podem ser inseridas **marcações** que o sistema substitui, ao gerar o documento, por conteúdo vivo do plano: a matriz de priorização, o grupo de trabalho e o plano de ação. Cada marcação é um registro em **Marcações do PDA**, com o texto exato a digitar e o modelo que ela renderiza — escreva-a exatamente como cadastrada, porque um erro de digitação faz o texto sair literal no documento.

![Cadastro de uma marcação](usuario/marcacao-formulario.webp)

**Depois, a versão**

3. No menu, acesse **Dados Abertos › Plano de Dados Abertos**. Na linha do plano ficam os quatro ícones de ação — **Visualizar**, **Nova versão**, **Gerar documento** e **Editar**. Clique em **Nova versão**.

   ![Listagem de planos, com os ícones de ação](usuario/pda-listagem.webp)

4. Escolha o **Tipo de versão** e escreva a **Justificativa da versão**; clique em **Enviar**.

   | Tipo | Quando usar | Efeito na numeração |
   | --- | --- | --- |
   | Major | Alteração estrutural | 1.0.0 → 2.0.0 |
   | Minor | Adição ou remoção relevante | 1.0.0 → 1.1.0 |
   | Patch | Correção pontual | 1.0.0 → 1.0.1 |

   ![Criação de uma nova versão](usuario/pda-nova-versao.webp)

**Resultado:** *"Versão do PDA criada com sucesso."* O sistema guarda um retrato do plano naquele momento e produz o documento em **HTML e PDF**, que passam a ser oferecidos na área pública.

O ícone **Gerar documento** apenas **regera os arquivos da versão atual**, sem criar versão nova — use quando o conteúdo mudou sem justificar uma versão, ou quando os arquivos se perderam.

**Por fim, a área pública**

5. Abra a área pública em `/dados_abertos/publico/` — **sem necessidade de login**. Ela também é alcançável pelo bloco de serviços da tela inicial do SUAP, em *Transparência › Dados Abertos*.
6. Confira que a versão recém-gerada aparece e que o PDF abre.

![Área pública do plano](usuario/area-publica.webp)

> **A situação do plano é manual.** Concluir o checklist não muda a **Situação** nem preenche a **Data de publicação**: volte ao registro do plano e ajuste os dois você mesmo (tarefa 2).

---

### 11. Manter os dados atualizados

**Quem pode:** Gestor de Dados Abertos Sistêmico para o conteúdo e o envio; Responsável LAI para a nova liberação.
**Quando usar:** para publicar **conteúdo novo** (nova URL ou arquivo) ou fazer a primeira publicação de uma base. A rotina roda todo dia e **recoleta** as bases já publicadas cuja frequência — a mais estrita entre os PDAs da base — venceu, **republicando** as que mudaram, sem passar por esta tarefa.

A aba **CKAN** do dashboard acompanha esse compromisso a partir da frequência cadastrada e da data da última sincronização, e classifica cada base em *Periodicidade em dia*, *Próxima do vencimento (N dia(s))* ou *Atrasada em N dia(s)*, informando a **próxima sincronização esperada**. Bases com frequência *Eventual* ou sem frequência definida não são cobradas.

Para publicar dados novos:

1. no recurso, **altere a URL** (o SUAP baixa o conteúdo do novo endereço ao salvar) ou **substitua o arquivo**. A base volta para *Em análise do LAI*;
2. peça a liberação (tarefa 8);
3. sincronize (tarefa 9);
4. peça a liberação **de novo** — o envio reabriu a análise, como avisa a tarefa 9, e é essa última liberação que devolve o plano a 100%.

A atualização automática só reenvia o conteúdo quando a **estrutura** (as colunas) continua a mesma. Se a origem mudou de estrutura, o conteúdo novo fica gravado no SUAP, a base volta para *Em análise do LAI* e o ciclo manual acima é obrigatório para publicá-lo.

Quando **você publica conteúdo novo pelo SUAP** — URL nova, arquivo novo ou estrutura alterada —, o ciclo manual é sempre o mesmo: **novo conteúdo → liberação → sincronizar → liberação**. Só se encerra numa liberação; se terminar num envio, a base fica em análise e o checklist não fecha.

---

## Para o público externo

Fluxo executado por quem **não tem conta no SUAP**. Quem conduz o plano também deve conhecê-lo, para saber o que o cidadão enxerga.

### Consultar o Plano de Dados Abertos e os dados publicados

**Pré-condição:** o plano tem ao menos uma versão gerada (tarefa 10).

1. Acesse `/dados_abertos/publico/`, ou o serviço **Transparência › Dados Abertos** na tela inicial do SUAP.
2. A página explica o que é o Plano de Dados Abertos, mostra os contadores de **planos publicados**, **datasets cadastrados** e **recursos disponíveis** e, no bloco **Documentos**, traz cada plano com todas as suas versões — cada uma com a data e a justificativa.
3. Use **LER** para abrir o documento no navegador ou **PDF** para baixá-lo.

**Resultado:** o documento oficial do plano, na versão escolhida. Os dados em si ficam no catálogo CKAN da instituição, para onde os conjuntos foram enviados na tarefa 9.

O texto institucional, o endereço e o contato exibidos nessa página **não são editáveis pelo módulo**: vêm fixos no sistema. O que muda com o seu trabalho são os contadores e a lista de planos e versões.

---

## Telas de apoio

Tabelas que alimentam os formulários deste módulo. Todas seguem o mesmo padrão do SUAP — listar, adicionar, editar, remover — e não têm passo a passo próprio.

Em **Dados Abertos › Conjuntos da Dados › Cadastros**: Temas · Palavra Chave. Em **Dados Abertos › Cadastros**: Capa · Tópicos · Áreas · Licença. Em **Dados Abertos › Matriz de Priorização › Avaliação da Base de Dados** ficam as notas da matriz, uma a uma — a tela da tarefa 6 é a forma prática de preenchê-las.

Fora do menu, alcançáveis pela administração do módulo, existem ainda os **Critérios da Matriz**, as **Marcações do PDA**, as **Etapas** e as **Ações** do fluxo, e a auditoria das **etapas dispensadas** — esta somente de leitura, com justificativa, autor, data, IP e navegador de cada dispensa.

Quatro delas têm efeito além de preencher uma lista:

- **Critérios da Matriz** — cada critério ativo vira uma coluna da matriz de priorização (tarefa 6). Vêm carregados da Resolução nº 3/2017 do CGINDA; desativar um critério o tira da matriz.
- **Marcações do PDA** — definem quais trechos vivos podem ser inseridos nos tópicos do documento (tarefa 10).
- **Etapas** e **Ações** — são a estrutura do checklist. Não edite por aqui: quem as define é o passo 3 de *Antes de começar*, e cada execução do comando substitui o que estiver cadastrado.
- **Licença**, **Tema** e **Palavra Chave** — são os metadados de catalogação que acompanham o conjunto até o CKAN.

---

## Base legal

- **Lei nº 12.527/2011** — Lei de Acesso à Informação
- **Decreto nº 8.777/2016** — Política de Dados Abertos do Poder Executivo Federal
- **Resolução nº 3/2017 do CGINDA** — critérios de priorização e cronograma de abertura de bases
