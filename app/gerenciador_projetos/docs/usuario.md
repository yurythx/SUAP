# Gerenciador de Projetos

Organiza o trabalho em projetos da instituição — do cadastro do projeto e da equipe até a conclusão das tarefas. É por aqui que um projeto ganha suas **listas** (as colunas do Dashboard), suas **tarefas** e **subtarefas** com prazos, prioridades, responsáveis e tags, e o **acompanhamento** do andamento em várias visões: Dashboard, calendário, gráfico de Gantt, tarefas por situação e histórico de evolução.

Cada projeto tem uma equipe com três papéis: quem **gerencia** (cria e organiza o projeto), quem **executa** (cria, atualiza e conclui tarefas) e quem apenas **acompanha**.

**Quem usa este módulo**

| Perfil | O que faz aqui |
| --- | --- |
| Gerente de Projeto | Cria o projeto, monta a equipe, muda a situação do projeto, organiza listas e tags, clona projetos |
| Membro de Projeto | Cria tarefas e subtarefas, atualiza situação e progresso, registra a evolução até a conclusão |
| Interessado do Projeto | Acompanha o projeto e as tarefas, sem criar nem alterar tarefas, listas ou tags |

---

## Antes de começar

Os formulários deste módulo consomem duas tabelas de apoio que precisam estar preenchidas. Numa instituição já em operação elas existem; se um desses campos aparecer vazio, é a tabela correspondente que falta:

- **Áreas de Atuação** — obrigatória no cadastro do projeto. Fica em **Administração › Cadastros › Áreas de Atuação**, fora deste módulo: quem gerencia projetos não tem acesso a essa tela e precisa pedir o cadastro a quem administra a Central de Serviços.
- **Tipos de Atividades** — obrigatória no cadastro da tarefa. Fica em **Gerenciador de Projetos › Cadastros › Tipos de Atividades**, e quem gerencia projetos pode cadastrar por conta própria.

Quem é incluído na equipe de um projeto entra automaticamente no grupo correspondente — **Gerente de Projeto**, **Membro de Projeto** ou **Interessado do Projeto** — e passa a enxergar o módulo sem precisar pedir acesso.

---

## Tarefas

### 1. Criar um projeto e colocá-lo em andamento

**Quem pode:** Gerente de Projeto.
**Quando usar:** ao começar um trabalho que precisa de equipe, tarefas e acompanhamento.

**Etapa 1 — cadastrar o projeto**

1. No menu, acesse **Gerenciador de Projetos › Projetos** e clique em **Adicionar Projeto**.

   ![Listagem de projetos](usuario/projeto-listagem.webp)

2. Preencha o formulário. Os campos que costumam gerar dúvida:

   | Campo | O que informar |
   | --- | --- |
   | Áreas de Atuação | As áreas da instituição relacionadas ao projeto (pode marcar mais de uma) |
   | Campus | A unidade a que o projeto pertence |
   | Gerentes | Obrigatório — quem vai gerenciar o projeto; busque pelo nome |
   | Membros | Quem vai executar as tarefas. Só membros e gerentes podem receber tarefas |
   | Interessados | Quem deve acompanhar o projeto sem executar tarefas |
   | Visibilidade | Em projeto **Privado**, o campo *Observadores* das tarefas só oferece os membros do projeto |

   ![Formulário de cadastro do projeto](usuario/projeto-formulario.webp)

3. Clique em **Salvar**.

**Resultado:** você é levado à página do projeto, que nasce com a situação **Aberto**. A coluna lateral mostra a equipe (Gerentes, Membros e Interessados), e a página tem as abas **Tarefas**, **Comentários**, **Listas** e **Tags**.

![Página do projeto recém-criado](usuario/projeto-criado.webp)

**Etapa 2 — colocar o projeto em andamento**

Enquanto o projeto estiver **Aberto**, cada tarefa criada nele mostra o aviso *"Este projeto ainda está com situação Aberto, favor editar o projeto e corrigir a situação."* Quando o trabalho começar:

4. Na página do projeto, clique em **Editar**.
5. Em **Situação**, marque **Em andamento** (as outras opções são *Aberto*, *Concluído*, *Suspenso* e *Cancelado*) e clique em **Salvar**.

   ![Edição do projeto, com a Situação](usuario/projeto-edicao.webp)

**Resultado:** você volta à página do projeto, agora com a tarja **Em andamento**.

---

### 2. Organizar o projeto: listas e tags

**Quem pode:** gerente do projeto. Os membros não veem os botões *Adicionar Lista* e *Adicionar Tag*.
**Quando usar:** para dar estrutura ao trabalho — cada lista vira uma coluna do Dashboard (tarefa 6), e as tags identificam as tarefas.

**Etapa 1 — criar as listas**

1. Na página do projeto, abra a aba **Listas** e clique em **Adicionar Lista**.

   ![Aba Listas do projeto](usuario/projeto-listas.webp)

2. No popup, deixe a **Ação** em **Adicionar**, informe o **Nome** da lista e a **Posição** que ela deve ocupar no Dashboard, e clique em **Enviar**. A outra ação, **Vincular**, reaproveita uma lista já existente, escolhida em *Listas Disponíveis*.

   ![Popup de criação de lista](usuario/lista-popup.webp)

3. Repita para cada etapa do fluxo de trabalho — por exemplo, *A Fazer*, *Em Execução* e *Concluído*.

**Resultado:** *"Operação realizada com sucesso."* e a lista passa a constar na aba, na posição escolhida.

**Etapa 2 — criar as tags**

4. Na aba **Tags**, clique em **Adicionar Tag**, informe **Nome** e **Cor**, e clique em **Salvar**.

   ![Popup de criação de tag](usuario/tag-popup.webp)

**Resultado:** *"Tag adicionada com sucesso."* A tag fica disponível para marcar as tarefas deste projeto.

---

### 3. Criar tarefas e subtarefas

**Quem pode:** membro ou gerente do projeto.
**Pré-condição:** o projeto existe (tarefa 1) e, se a tarefa deve nascer dentro de uma lista, a lista existe (tarefa 2).

**Etapa 1 — criar a tarefa**

Há duas portas para o mesmo formulário:

- **Pelo Dashboard**, quando a tarefa já tem lugar no fluxo: na página do projeto, abra o botão do olho (**Visualização**), escolha **Dashboard** e clique no **+** ao lado do nome da coluna em que a tarefa deve entrar. O formulário abre num popup, já ligado àquela lista.
- **Pela página do projeto**: na aba **Tarefas**, clique em **+ Tarefa**. O formulário abre em página inteira, e a lista é escolhida no campo **Lista**.

1. Preencha o formulário. Os campos que costumam gerar dúvida:

   | Campo | O que informar |
   | --- | --- |
   | Tipo de Atividade | Obrigatório — a categoria da tarefa (ex.: Planejamento) |
   | Situação | **Aberta** ao criar; muda conforme o andamento (tarefa 5) |
   | Prioridade | **Alta**, **Média** ou **Baixa** |
   | Lista | A coluna do Dashboard em que a tarefa fica |
   | Atribuído a | Quem vai executar — só são oferecidos membros e gerentes do projeto |
   | Observadores | Quem deve acompanhar a tarefa sem ser responsável por ela |
   | Data de Início / Data de Conclusão Estimada | Alimentam o calendário e o gráfico de Gantt (tarefa 7) |
   | Tarefa Pai | Deixe em branco; para criar uma subtarefa, use a etapa 2 |
   | Tags | As tags do projeto (tarefa 2) |

   ![Formulário de criação de tarefa, aberto pelo Dashboard](usuario/tarefa-formulario.webp)

2. Clique em **Salvar**.

**Resultado:** *"Operação realizada com sucesso."* e a página da tarefa — dentro do próprio popup, quando você veio pelo Dashboard. A tarefa entra na lista escolhida; sem lista, aparece no quadro **Tarefas sem lista** do Dashboard.

![Página da tarefa recém-criada](usuario/tarefa-criada.webp)

**Etapa 2 — criar uma subtarefa**

3. Na página da tarefa que vai ser a "mãe", abra a aba **Subtarefas** e clique em **Adicionar subtarefa**.
4. Preencha o mesmo formulário da etapa 1. O campo **Tarefa Pai** já vem preenchido e travado com a tarefa de origem. Clique em **Salvar**.

   ![Formulário de subtarefa, com a Tarefa Pai preenchida](usuario/subtarefa-formulario.webp)

**Resultado:** *"Operação realizada com sucesso."* e a página da subtarefa, que avisa *"Esta tarefa é filha da tarefa #…"*. A subtarefa nasce sem lista. Na tarefa-mãe, ela passa a constar na aba **Subtarefas**, e a coluna lateral mostra o **Progresso das subtarefas** e quantas estão concluídas.

![Aba Subtarefas da tarefa-mãe](usuario/tarefa-subtarefas.webp)

---

### 4. Registrar o andamento e concluir uma tarefa

**Quem pode:** membro ou gerente do projeto.
**Pré-condição:** a tarefa existe (tarefa 3).

A página da tarefa organiza o trabalho em quatro abas: **Evolução** (com o *Checklist* e o *Histórico*), **Anexos**, **Links** e **Subtarefas**. Comentários e evoluções entram no Histórico, com quem registrou e quando.

**Checklist**

1. Na aba **Evolução**, no quadro **Checklist**, digite o item no campo *Novo item para Checklist* e pressione Enter.
2. Marque o item quando ele estiver feito. O quadro mostra quantos itens já foram concluídos.

   ![Checklist da tarefa com um item marcado](usuario/tarefa-checklist.webp)

**Comentário rápido**

3. No quadro **Histórico**, escreva em *Novo comentário* e clique em **Comentar**.

**Resultado:** *"Comentário adicionado com sucesso."*

**Link**

4. Na aba **Links**, clique em **Adicionar link**, informe **Título** e **URL** e clique em **Salvar**.

**Resultado:** *"Link salvo com sucesso."*

**Anexar um arquivo**

5. Na aba **Anexos**, clique em **Adicionar anexo**, selecione o arquivo e clique em **Salvar**. Também é possível anexar um arquivo ao registrar uma evolução.

**Resultado:** o arquivo passa a constar na aba **Anexos**.

**Registrar evolução**

6. No quadro **Histórico**, clique em **Registrar evolução**, informe o **Comentário**, arraste o **Percentual executado** até o valor desejado (de 5 em 5%, com o número ao lado) e clique em **Salvar**. O popup também tem os campos **Anexo**, **Data de Conclusão** e **Título do link** / **URL do link**. Se a tarefa estiver **Aberta** e o percentual passar de 0%, ela muda sozinha para **Em andamento** (vale também para o botão **Progresso**).

   ![Popup de registro de evolução](usuario/tarefa-evolucao.webp)

**Resultado:** *"Evolução registrada com sucesso."* O percentual informado passa a ser o progresso da tarefa.

Quando alguém adiciona um comentário, anexo ou link, o SUAP envia uma notificação por e-mail aos atribuídos, observadores e interessados da tarefa. Quem fez a alteração não recebe a própria notificação.

**Concluir a tarefa**

7. Clique em **Registrar evolução** de novo, informe o **Comentário** final, arraste o **Percentual executado** até **100%**, informe a **Data de Conclusão** e clique em **Salvar**.

**Resultado:** a tarefa fica **Concluída**, com 100%, e passa a ser **somente leitura**: somem *Editar*, *Registrar evolução*, *Comentar*, *Situação*, *Progresso*, *Adicionar subtarefa*, anexos, links, checklist, atribuições, recorrência e *Atribuir a campus*. Continuam disponíveis *Observar*, *Clonar tarefa*, *Excluir tarefa* e *Reabrir tarefa*.

> **Tarefas somente leitura:** a mesma regra vale para a tarefa **Cancelada** (que também pode ser reaberta) e para a **Suspensa**, que mantém apenas o botão *Situação* para ser retomada. Em projeto **Concluído** ou **Cancelado**, todas as tarefas ficam somente leitura, sem reabrir, clonar ou excluir: para mexer nelas, reabra o projeto.

![Tarefa concluída](usuario/tarefa-concluida.webp)

Basta o **Percentual executado** **100** para concluir a tarefa, mesmo sem a data de conclusão: ela recebe a data do dia. Outro caminho para concluir é o botão **Progresso › 100%** (tarefa 5). Para reabrir uma tarefa concluída ou cancelada, use o botão da engrenagem (**Ações**) › **Reabrir tarefa** e, na janela que se abre, clique em **Reabrir tarefa** para confirmar: aparece *"A tarefa foi reaberta."* e ela volta à situação **Aberta**.

---

### 5. Ajustar situação, progresso e responsáveis de uma tarefa

**Quem pode:** membro ou gerente do projeto.
**Quando usar:** para atualizar a tarefa sem registrar uma evolução completa. Cada mudança entra sozinha no Histórico.

**Situação**

1. Na página da tarefa, clique em **Situação** e escolha a nova situação. O menu lista todas as situações, exceto a atual.
2. No popup, confira a *Situação atual* e a *Nova situação* e clique em **Alterar para …**.

   ![Popup de confirmação da mudança de situação](usuario/tarefa-situacao.webp)

**Resultado:** *"Situação da tarefa alterada com sucesso."*

**Progresso**

3. Clique em **Progresso** e escolha **0%**, **25%**, **50%**, **75%** ou **100%**.

**Resultado:** *"Progresso atualizado com sucesso."* Escolher **100%** conclui a tarefa. Para outro valor, ou para registrar o motivo da mudança, use o **Registrar evolução** (tarefa 4).

**Responsáveis**

4. Clique no botão da engrenagem (**Ações**) › **Alterar atribuições**, inclua ou retire pessoas em **Atribuído a** e clique em **Salvar**.

   ![Popup de atribuições](usuario/tarefa-atribuicoes.webp)

**Resultado:** *"Atribuições atualizadas com sucesso."*, e a mudança fica registrada no Histórico.

**Observar a tarefa**

5. Para acompanhar uma tarefa sem ser responsável por ela, clique no botão do olho (**Observar**).

**Resultado:** *"Você foi adicionado como observador desta tarefa."* Seu nome passa a constar no quadro **Observadores** da coluna lateral, e no lugar do olho aparece o olho cortado (**Deixar de observar**).

6. Para parar de acompanhar, clique no olho cortado (**Deixar de observar**). Aparece *"Você deixou de observar esta tarefa."* e seu nome sai do quadro **Observadores**; os demais observadores continuam.

![Tarefa em andamento, com progresso, dois responsáveis e um observador](usuario/tarefa-acoes.webp)

Numa tarefa concluída ou cancelada, os botões *Situação* e *Progresso* não aparecem; numa suspensa, só *Situação* continua, para retomá-la.

---

### 6. Usar o Dashboard

**Quem pode:** membro ou gerente do projeto. O interessado não tem o Dashboard no menu *Visualização*.
**Quando usar:** para enxergar o fluxo de trabalho como um quadro, com uma coluna por lista, e mover as tarefas entre as etapas.

1. Na página do projeto, abra o botão do olho (**Visualização**) e escolha **Dashboard**. Cada lista do projeto é uma coluna; tarefas sem lista ficam na coluna **Tarefas sem lista**.
2. Para mudar uma tarefa de lista, arraste o cartão até a coluna de destino e **solte-o abaixo de um cartão que já esteja lá**.

   > **Atenção:** ao soltar o cartão numa coluna vazia, a mudança **não é gravada** — o cartão aparece na coluna nova, mas volta à de origem quando a página é recarregada. Para levar uma tarefa a uma coluna vazia, abra a tarefa, clique no lápis (**Editar**), escolha a lista no campo **Lista** e clique em **Salvar**.

3. Para ver só parte das tarefas, use os filtros **Atribuído a**, **Situação** e **Prioridade** no topo e clique em **Enviar**.
4. Cada cartão tem o seu próprio menu de atalhos: o lápis (**Alterar**) oferece *Situação > …* e *Progresso > …%*. Ao escolher um percentual, você é levado à página da tarefa com a mensagem *"Progresso atualizado com sucesso."*

![Dashboard com as colunas das listas e o menu Alterar de um cartão aberto](usuario/dashboard-board.webp)

---

### 7. Acompanhar o andamento do projeto

**Quem pode:** qualquer pessoa da equipe do projeto — gerente, membro ou interessado.

Na página do projeto, o botão do olho (**Visualização**) reúne as visões de acompanhamento: **Padrão** (a própria página do projeto), **Dashboard**, **Tarefas por situação**, **Gantt**, **Calendário** e **Evolução das tarefas**. O interessado recebe só *Padrão*, *Gantt*, *Calendário* e *Evolução das tarefas*, e vê a página do projeto sem os botões *+ Tarefa*, *Editar*, *Clonar projeto*, *Adicionar Lista* e *Adicionar Tag*.

![Página do projeto vista por um interessado](usuario/projeto-interessado.webp)

**Gantt** — o gráfico de barras das tarefas do projeto, de acordo com a Data de Início e a Data de Conclusão Estimada de cada uma.

![Gráfico de Gantt do projeto](usuario/gantt.webp)

**Calendário** — as tarefas marcadas no dia da sua data de conclusão estimada, com cor por situação (veja a legenda). Apenas tarefas com data de conclusão estimada aparecem — a própria tela avisa. Ajuste **Data de Início**, **Data de Término** e **Situação** e clique em **Enviar** para mudar o período.

![Calendário do projeto](usuario/calendario.webp)

**Tarefas por situação** — uma coluna para cada situação que tenha tarefas (*Aberta*, *Em andamento*, *Concluída* …), com a barra de progresso do projeto no topo. Os botões das tags, acima das colunas, mostram só as tarefas marcadas com aquela tag; **Todas as tags** volta a mostrar tudo.

![Tarefas por situação do projeto](usuario/situacao-tarefas.webp)

**Evolução das tarefas** — o histórico de evolução de todas as tarefas do projeto numa tabela só, com filtro por **Data Inicial** e **Data Final**.

![Evolução das tarefas do projeto](usuario/evolucao-tarefas.webp)

---

### 8. Ver as minhas tarefas

**Quem pode:** gerente ou membro de projeto. O interessado vê o item no menu, mas a tela recusa o acesso.

1. No menu, acesse **Gerenciador de Projetos › Minhas tarefas**.
2. Para ver só as tarefas de um projeto, escolha-o no campo **Projetos** e clique em **Enviar**.

**Resultado:** dois quadros com as tarefas atribuídas a você: **Em andamento** (todas as que não estão concluídas, inclusive as que ainda estão *Abertas*) e **Concluída**. Cada cartão mostra o nome do projeto; clique no título para abrir a tarefa.

![Minhas tarefas, filtradas por projeto](usuario/minhas-tarefas.webp)

---

### 9. Distribuir uma tarefa entre campi

**Quem pode:** membro ou gerente do projeto.
**Quando usar:** quando a mesma tarefa precisa ser executada em mais de um campus, cada um com o seu acompanhamento.

1. Na página da tarefa, clique no botão da engrenagem (**Ações**) › **Atribuir a campus**. Na aba **Tarefas** da página do projeto, os cartões das tarefas não concluídas também têm o botão **Atribuir a campus**.
2. Em **Campi**, selecione os campi em *Disponíveis* e clique em **Escolher selecionado(s)**. Marque **Manter atendentes** para que as cópias saiam com os mesmos responsáveis.

   ![Tela Atribuir tarefa a campus](usuario/tarefa-campus.webp)

3. Clique em **Enviar**.

**Resultado:** *"Vínculo realizado com sucesso."* e você volta à página do projeto. Um dos campi escolhidos fica com a própria tarefa, e cada um dos outros recebe uma cópia dela, com as subtarefas. O título de cada uma passa a vir precedido da sigla do campus (*CEN - …*, *CZN - …*). As cópias nascem sem lista.

![Projeto com a tarefa distribuída entre dois campi](usuario/tarefa-campus-resultado.webp)

---

### 10. Reaproveitar um projeto (clonar)

**Quem pode:** gerente do projeto. Os membros não veem o botão.
**Quando usar:** para começar um projeto parecido com um que já existe, aproveitando as tarefas.

1. Na página do projeto, clique em **Clonar projeto** e, na página de confirmação, clique de novo em **Clonar projeto**.

**Resultado:** *"Operação realizada com sucesso."* e você é levado ao projeto *"Cópia de …"*, com situação **Aberto**. A cópia traz a descrição, o campus, as áreas de atuação e as tarefas e subtarefas, mas:

- a equipe não é copiada — só você entra, como gerente. Use **Editar** para incluir membros e interessados;
- as tarefas vêm sem responsáveis e sem tags;
- as listas e as tags do projeto não vão para a cópia — recrie-as como na tarefa 2.

![Projeto clonado](usuario/projeto-clonado.webp)

---

## Telas de apoio

Tabelas consultadas pelos formulários deste módulo. Seguem o mesmo padrão do SUAP — listar, adicionar, editar, remover — e ficam em **Gerenciador de Projetos › Cadastros**:

- **Listas** — as listas usadas como colunas do Dashboard (tarefa 2);
- **Tipos de Atividades** — alimenta o campo *Tipo de Atividade* do formulário de tarefa (tarefa 3).

Fora do módulo, o cadastro de projeto consome as **Áreas de Atuação**, em **Administração › Cadastros › Áreas de Atuação** (veja *Antes de começar*).
