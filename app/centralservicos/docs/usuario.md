# Central de Serviços

Registra e acompanha os chamados de serviço da instituição — o pedido de um servidor, aluno ou prestador de serviço e o trabalho de quem atende. Reúne o **catálogo de serviços** (o que pode ser solicitado, para quem e por quem é atendido), a **Central de Serviços** propriamente dita (abertura, atendimento, encaminhamento e conclusão dos chamados) e a **Base de Conhecimento** (artigos que respondem às dúvidas recorrentes).

**Quem usa este módulo**

| Perfil | O que faz aqui |
| --- | --- |
| Servidor, Aluno e Prestador de Serviço | Abre chamados, acompanha os seus, comenta, anexa, cancela, reabre, fecha e avalia o atendimento |
| Atendente da Central de Serviços | Atende os chamados do seu grupo: assume, inicia o atendimento, resolve, suspende, encaminha e abre tarefas |
| Responsável pelo grupo de atendimento | Atribui e encaminha o chamado a um atendente ou a outro nível de atendimento |
| Gestor da Central de Serviços | Mantém o catálogo de serviços e a estrutura de atendimento, e cadastra as tarefas |
| Contribuinte e Supervisor da Base de Conhecimento | Escrevem, revisam, aprovam e publicam os artigos |
| Administrador da Central de Serviços | Cria as áreas de serviço, nomeia os gestores e tem acesso amplo aos cadastros |

---

## Antes de começar

Para um chamado existir, é preciso que exista, nesta ordem:

1. uma **Área de Serviço** (tarefa 1) — é o recorte maior do catálogo (por exemplo, Tecnologia da Informação);
2. pelo menos um **Centro de Atendimento** e um **Grupo de Atendimento** com atendentes na área (tarefa 2) — sem grupo de primeiro nível para o campus de quem abre, a abertura do chamado é recusada;
3. um **Serviço** publicado no catálogo (tarefa 3) — é o que o solicitante escolhe ao abrir o chamado.

Toda a manutenção fica em **Central de Serviços › Cadastros**, exceto as áreas de serviço, que ficam em **Administração › Cadastros › Áreas de Atuação**.

---

## Tarefas

### 1. Definir a área de serviço e o gestor que responde por ela

**Quem pode:** Administrador da Central de Serviços.
**Quando usar:** ao criar uma nova área de serviço — antes de qualquer cadastro de centro, grupo ou serviço dela.

1. No menu, acesse **Administração › Cadastros › Áreas de Atuação** e clique em **Adicionar Área de Atuação**.

   ![Listagem de áreas de atuação](usuario/01-area-listagem.webp)

2. Informe **Nome** e **Ícone** (o nome de um ícone) e mantenha **Ativo?** marcado. Clique em **Salvar**.

   ![Formulário da área de atuação](usuario/01-area-formulario.webp)

3. Agora acesse **Central de Serviços › Cadastros › Gestores das Áreas de Serviços** e clique em **Adicionar Gestor da Área do Serviço**.

   ![Listagem de gestores das áreas](usuario/01-gestor-listagem.webp)

4. Informe o **Gestor** (busque pela matrícula ou pelo nome) e a **Área do Serviço** e clique em **Salvar**.

   ![Formulário do gestor da área](usuario/01-gestor-formulario.webp)

**Resultado:** em cada tela aparece *"Cadastro realizado com sucesso."*. O gestor nomeado é quem mantém o catálogo e a estrutura da área daqui em diante.

---

### 2. Montar a estrutura de atendimento

**Quem pode:** Gestor da Central de Serviços e Administrador da Central de Serviços.
**Pré-condição:** a área de serviço já existe (tarefa 1).

**Etapa 1 — cadastrar o centro de atendimento**

1. No menu, acesse **Central de Serviços › Cadastros › Atendimento › Centros de Atendimento** e clique em **Adicionar Centro de Atendimento**.

   ![Listagem de centros de atendimento](usuario/02-centro-listagem.webp)

2. Preencha **Nome**, **Área do Serviço** e **Ativo?**, e decida sobre **Centro de Atendimento Local?** — marque quando o atendimento é feito no campus de quem abre o chamado; deixe desmarcado para um centro que atende toda a rede. Clique em **Salvar**.

   ![Formulário do centro de atendimento](usuario/02-centro-formulario.webp)

**Etapa 2 — cadastrar os grupos de atendimento**

3. Acesse **Central de Serviços › Cadastros › Atendimento › Grupos de Atendimento** e cadastre primeiro o grupo de **nível superior**: informe **Campus**, **Centro de Atendimento**, **Nome**, os **Responsáveis** e os **Atendentes Vinculados ao Grupo**, e deixe **Grupo de Atendimento Superior** vazio. Clique em **Salvar**.
4. Cadastre agora o grupo de **primeiro nível** — é ele que recebe os chamados. O formulário é o mesmo; a diferença é apontar, em **Grupo de Atendimento Superior**, o grupo do passo 3.

   ![Formulário do grupo de atendimento](usuario/02-grupo-formulario.webp)

**Resultado:** *"Cadastro realizado com sucesso."* Um chamado aberto para o centro e o campus informados passa a cair no grupo de primeiro nível; o vínculo com o grupo superior é o que habilita as ações **Escalar** e **Retornar** no chamado (tarefa 10).

**Campos que mudam o comportamento**

| Campo | O que ele decide |
| --- | --- |
| Centro de Atendimento Local? | Se marcado, o grupo só atende chamados do próprio campus; se desmarcado, atende a rede toda |
| Grupo de Atendimento Superior | Para onde o chamado vai quando é escalado; também é o que faz o botão aparecer |
| Responsáveis | Quem pode **atribuir** o chamado a um atendente e encaminhá-lo entre níveis |
| Atendentes Vinculados ao Grupo | Quem enxerga e assume os chamados do grupo |

---

### 3. Cadastrar um serviço no catálogo

**Quem pode:** Gestor da Central de Serviços.
**Pré-condição:** a área de serviço e o centro de atendimento já existem (tarefas 1 e 2).

1. Acesse **Central de Serviços › Cadastros › Serviços › Categorias de Serviço** e clique em **Adicionar Categoria de Serviço**. Informe **Nome** e **Área do Serviço** e clique em **Salvar**.

   ![Listagem de categorias de serviço](usuario/03-categoria-listagem.webp)

2. Acesse **Central de Serviços › Cadastros › Serviços › Grupos de Serviço** e clique em **Adicionar Grupo de Serviço**. Informe **Nome**, **Detalhamento**, **Categorias** e **Ícone**, e clique em **Salvar**.

   ![Formulário do grupo de serviço](usuario/03-grupo-servico-formulario.webp)

3. Acesse **Central de Serviços › Cadastros › Serviços › Serviços** e clique em **Adicionar Serviço**. Preencha o formulário — dividido em *Dados gerais*, *Atendimento*, *Instruções para Abertura de Chamado*, *Configurações* e *Visibilidade* — e clique em **Salvar**.

   ![Formulário do serviço](usuario/03-servico-formulario.webp)

**Resultado:** *"Cadastro realizado com sucesso."* O serviço passa a aparecer para quem abre chamado, na área e nos centros de atendimento escolhidos.

**Campos que mudam o comportamento**

| Campo | O que ele decide |
| --- | --- |
| Tipo | **Incidente** para problemas (algo parou de funcionar) ou **Requisição** para pedidos — a distinção aparece no painel e nos relatórios |
| Centros de Atendimento | Em quais centros o serviço é oferecido; é por eles que o chamado é roteado até um grupo |
| SLA utilizado / SLA manual (em horas) | O prazo de atendimento. Em **SLA manual**, é o número de horas informado; no automático, é calculado pelas estatísticas do próprio serviço |
| Informações para preenchimento do chamado | O texto que orienta quem abre o chamado, exibido junto ao formulário |
| Permite anexos? | Se o formulário de abertura aceita anexos |
| Deve solicitar local de atendimento? | Se quem abre precisa informar a sala/local |
| Interno? | Se o serviço é oferecido apenas aos atendentes (não aparece para o público) |
| Ativo? | Desmarcado, o serviço deixa de ser oferecido |

---

### 4. Escrever, revisar e publicar artigos da Base de Conhecimento

**Quem pode:** o **Contribuinte da Base de Conhecimento** escreve; o **Supervisor da Base de Conhecimento** revisa, aprova e publica.
**Quando usar:** ao identificar uma solução que vai se repetir, ou quando um atendimento revela que a resposta precisa ser padronizada.

**Etapa 1 — escrever o artigo**

1. No menu, acesse **Central de Serviços › Base de Conhecimentos** e clique no nome da área.

   ![Áreas de serviço da Base de Conhecimento](usuario/04-base-conhecimento-area.webp)

2. Clique em **Adicionar Artigo**. Preencha **Área do Serviço**, **Título**, **Resumo**, **Solução**, **Tags**, **Visibilidade** e, se quiser restringir, **Restringir aos Grupos de Atendimento** e **Restringir aos Serviços**. Clique em **Salvar**.

   ![Formulário do artigo](usuario/04-artigo-formulario.webp)

**Resultado:** *"Cadastro realizado com sucesso."* Como o seu perfil não aprova artigos, o artigo nasce marcado como **Supervisão pendente** e ainda não pode ser usado no atendimento.

**Etapa 2 — revisar e aprovar**

3. O supervisor abre o artigo pela mesma área (**Central de Serviços › Base de Conhecimentos**) e clica em **Aprovar alterações**.

   ![Artigo pendente de supervisão](usuario/04-artigo-supervisao-pendente.webp)

**Resultado:** *"Base de conhecimento revisada com sucesso."* O artigo fica disponível para uso no atendimento.

**Etapa 3 — publicar como artigo público (opcional)**

4. Para o artigo também aparecer para quem abre chamado e na área de Perguntas Frequentes, crie-o (ou edite-o) com **Visibilidade: Pública**. Só o Supervisor da Base de Conhecimento pode fazer isso.

   ![Formulário de artigo público](usuario/04-artigo-publico-formulario.webp)

**O que cada visibilidade significa**

| Visibilidade | Quem enxerga |
| --- | --- |
| Privada | Os atendentes da Central de Serviços |
| Pública | Os atendentes **e** quem abre chamado — é o que faz o artigo aparecer antes do formulário de abertura |
| Sigilosa | Apenas os grupos de atendimento indicados em **Restringir aos Grupos de Atendimento** |

---

### 5. Consultar a Base de Conhecimento

**Quem pode:** qualquer pessoa com acesso ao módulo. Quem não é atendente vê apenas os artigos **públicos**; os atendentes veem também os privados da área.

1. No menu, acesse **Central de Serviços › Base de Conhecimentos** e clique no nome da área.

   ![Áreas de serviço da Base de Conhecimento](usuario/05-areas-base-conhecimento.webp)

2. A tela da área reúne as categorias e os artigos. Clique no título de um artigo para lê-lo por inteiro.

   ![Base de Conhecimento de uma área](usuario/05-base-conhecimento-area.webp)

**Resultado:** o artigo completo é exibido, com resumo, solução e tags.

![Artigo aberto para leitura](usuario/05-artigo-publico.webp)

---

### 6. Abrir um chamado

**Quem pode:** Servidor, Aluno e Prestador de Serviço.
**Pré-condição:** o serviço existe no catálogo e há grupo de atendimento de primeiro nível para o seu campus (tarefas 2 e 3).

1. No menu, acesse **Central de Serviços › Abrir chamado** e clique no nome da área.

   ![Áreas de serviço](usuario/06-areas-de-servico.webp)

2. Escolha o serviço na lista da área.

   ![Serviços da área](usuario/06-servicos-da-area.webp)

3. O SUAP mostra antes as soluções já conhecidas para aquele serviço. Se nenhuma resolver, clique em **Não encontrei nenhuma solução. Desejo abrir um novo chamado mesmo assim.**

   ![Soluções sugeridas antes de abrir o chamado](usuario/06-solucoes-antes-de-abrir.webp)

4. Preencha o formulário. Os campos que costumam gerar dúvida:

   | Campo | O que informar |
   | --- | --- |
   | Descrição | O problema ou o pedido, com o detalhe que o atendente precisa para trabalhar |
   | Campus | O campus de quem precisa do atendimento |
   | Centro de Atendimento | Qual equipe deve atender; aparece apenas quando o serviço é oferecido em mais de um centro |
   | Sala/local de atendimento | Aparece só nos serviços que pedem essa informação |
   | Outros Interessados | Outras pessoas que devem acompanhar o chamado |
   | Enviar cópia de abertura deste chamado para os interessados? | Marque para avisar os interessados por e-mail |

   ![Formulário de abertura do chamado](usuario/06-formulario-abrir-chamado.webp)

5. Clique em **Abrir chamado**.

**Resultado:** aparece *"Chamado aberto com sucesso."* e você é levado à página do chamado, já com a previsão de atendimento calculada pelo SLA do serviço.

---

### 7. Atender um chamado

**Quem pode:** Atendente da Central de Serviços.

1. No menu, acesse **Central de Serviços › Dashboard**. Os números mostram a situação dos chamados dos seus grupos de atendimento.

   ![Dashboard do atendente](usuario/07-dashboard.webp)

2. Clique no indicador **Não Atribuídos** para ver a fila de chamados que ainda não têm atendente.

   ![Fila de chamados](usuario/07-fila-de-chamados.webp)

3. Abra o chamado e clique em **Assumir**.

   ![Chamado aberto](usuario/07-chamado-aberto.webp)

   **Resultado:** *"Atribuição realizada com sucesso."* A partir daí o chamado é seu: só você resolve, suspende ou abre notas internas nele.

4. Clique em **Alterar para Em Atendimento** — é o estado em que o chamado passa a contar prazo de atendimento e libera o comentário para quem abriu.

   **Resultado:** *"Alteração de situação realizada com sucesso."*

5. Para registrar o andamento sem que o interessado veja, use a aba **Notas Internas**, escreva o texto e clique em **Adicionar Nota interna**.

   ![Nota interna](usuario/07-nota-interna.webp)

   **Resultado:** *"Nota Interna adicionada com sucesso."*

---

### 8. Acompanhar o próprio chamado

**Quem pode:** quem abriu o chamado e as pessoas marcadas como interessadas.

1. No menu, acesse **Central de Serviços › Meus chamados**. A tela tem uma aba por situação (Ativos, Abertos, Em atendimento, Reabertos, Suspensos, Resolvidos, Fechados, Cancelados e A Fechar) e filtros por ID, área, período e relação com o chamado.

   ![Meus chamados](usuario/08-meus-chamados.webp)

2. Abra o chamado e escreva no campo de comentário da **Linha do tempo**; clique em **Adicionar Comentário**.

   ![Comentário no chamado](usuario/08-comentario.webp)

   **Resultado:** *"Comentário adicionado com sucesso."* Só é possível comentar enquanto o chamado está **Em atendimento** ou **Suspenso**.

3. Para enviar um arquivo, abra a aba **Anexos**, clique em **Adicionar Anexo**, informe **Descrição** e **Anexo** e clique em **Salvar**.

   **Resultado:** *"Anexo adicionado com sucesso."*

4. Para envolver outra pessoa, abra **Ações › Adicionar outros interessados**, informe os nomes em **Outros Interessados** e clique em **Enviar**.

   ![Adicionar outros interessados](usuario/08-outros-interessados.webp)

   **Resultado:** *"Adição de outros interessados realizada com sucesso."*

**Outros dois desfechos do acompanhamento**

- **Cancelar:** enquanto o chamado não foi fechado, **Cancelar** (na barra de ações) pede o motivo e encerra o chamado.

  ![Cancelar chamado](usuario/08-cancelar-chamado.webp)

  **Resultado:** *"Situação alterada com sucesso."*

- **Reabrir:** se o problema voltar depois de resolvido, abra o chamado e clique em **Reabrir chamado**, informando o motivo.

  ![Reabrir chamado](usuario/08-reabrir-chamado.webp)

  **Resultado:** *"Situação alterada com sucesso."* O chamado volta para o atendimento com o mesmo atendente.

---

### 9. Resolver e concluir o chamado

**Quem pode:** o atendente do chamado resolve; quem abriu o chamado fecha e avalia.
**Pré-condição:** o chamado está Em Atendimento e não há tarefa pendente vinculada a ele.

**Etapa 1 — resolver (atendente)**

1. Abra o chamado, vá à aba **Artigos relacionados**, marque o artigo que documenta a solução e escreva o **Comentário** com o que foi feito.

   ![Resolver o chamado com o artigo](usuario/09-resolver-chamado.webp)

2. Clique em **Alterar para Resolvido**.

   **Resultado:** *"Alteração de situação realizada com sucesso. Os seguintes chamados foram resolvidos: …"* O artigo marcado fica ligado ao histórico do chamado.

**Etapa 2 — fechar e avaliar (quem abriu)**

3. Abra o chamado resolvido e clique em **Fechar Chamado**.
4. Dê a nota no atendimento (de 1 a 5 estrelas) e, se quiser, escreva um **Comentário**; confirme no botão ao fim do formulário.

   ![Fechar e avaliar o chamado](usuario/09-fechar-chamado.webp)

   **Resultado:** *"Alteração de situação realizada com sucesso."* O chamado é encerrado e a avaliação entra nos indicadores.

---

### 10. Encaminhar o chamado

**Quem pode:** o responsável pelo grupo de atendimento (atribuir e encaminhar entre níveis) e o atendente do chamado (reclassificar, sinalizar e suspender).

1. Abra o chamado e use o menu **Ações** para escolher a operação.

   ![Chamado a encaminhar](usuario/10-chamado-a-encaminhar.webp)

2. **Atribuir** — passa o chamado a um atendente do grupo. Escolha o nome em **Atribuido para** e clique em **Salvar**.

   ![Atribuir o chamado](usuario/10-atribuir.webp)

   **Resultado:** *"Atribuição realizada com sucesso para …"*

3. **Escalar** — sobe o atendimento para o grupo de nível superior. Escreva o **Texto** (vira uma nota interna) e clique em **Salvar**.

   ![Escalar o atendimento](usuario/10-escalar.webp)

   **Resultado:** *"Operação realizada com sucesso."* O chamado passa ao grupo superior e volta a ficar sem atendente.

4. **Retornar** — devolve o chamado ao grupo de nível anterior, pelo mesmo formulário.

   ![Retornar o atendimento](usuario/10-retornar.webp)

   **Resultado:** *"Operação realizada com sucesso."*

5. **Reclassificar** — troca o serviço, o campus ou o centro de atendimento do chamado. Informe **Novo Serviço**, **Campus**, **Centro de Atendimento** e a **Justificativa**, e clique em **Salvar**.

   ![Reclassificar o chamado](usuario/10-reclassificar.webp)

   **Resultado:** *"Reclassificação de chamado realizada com sucesso."* O chamado é reencaminhado para o grupo de primeiro nível do novo centro e volta para **Aberto**.

6. **Adicionar tags** — marca o chamado para facilitar a busca depois. Marque as tags e clique em **Enviar**.

   ![Adicionar tags ao chamado](usuario/10-adicionar-tags.webp)

   **Resultado:** *"Adição de tags realizada com sucesso."*

7. **Suspender** — quando o atendimento depende de outra pessoa. Escreva o motivo em **Comentário** e clique em **Salvar**.

   ![Suspender o chamado](usuario/10-suspender.webp)

   **Resultado:** *"Situação alterada com sucesso."*

**Se o botão não aparecer:** **Escalar** só existe quando o grupo atual tem um grupo de atendimento superior e **Retornar**, quando existe um grupo inferior — os dois vínculos são feitos na tarefa 2.

---

### 11. Registrar e acompanhar tarefas

**Quem pode:** o **Gestor da Central de Serviços** cadastra as tarefas; o **atendente do chamado** abre a tarefa no chamado; o **responsável pela tarefa** (ou o atendente do chamado) altera a situação dela.
**Quando usar:** quando o atendimento depende de uma providência que precisa ser acompanhada à parte (uma visita técnica, uma compra, um agendamento).

1. No menu, acesse **Central de Serviços › Cadastros › Serviços › Tarefas** e clique em **Adicionar Tarefa**.

   ![Tarefas cadastradas](usuario/11-tarefa-listagem.webp)

2. Informe o **Serviço** a que a tarefa pertence, o **Título** e a **Descrição**, e clique em **Salvar**.

   ![Formulário da tarefa](usuario/11-tarefa-formulario.webp)

   **Resultado:** *"Cadastro realizado com sucesso."*

3. No chamado, abra a aba **Tarefas** e clique em **Adicionar tarefa**. Escolha a **Tarefa** e o **Responsável** e clique em **Salvar**.

   ![Vincular tarefa ao chamado](usuario/11-vincular-tarefa.webp)

   **Resultado:** a tarefa passa a constar na aba, com a situação **Aberta**.

   ![Tarefa vinculada ao chamado](usuario/11-tarefa-vinculada.webp)

4. O responsável pela tarefa clica em **Alterar** na linha dela, muda a **Situação** e clica em **Salvar**.

   ![Alterar a situação da tarefa](usuario/11-alterar-tarefa.webp)

5. Para acompanhar todas as tarefas dos seus grupos, acesse **Central de Serviços › Tarefas** — a aba **Ativas** mostra as que ainda estão em aberto.

   ![Tarefas vinculadas em andamento](usuario/11-tarefas-vinculadas.webp)

> Enquanto houver tarefa não finalizada (nem cancelada) vinculada ao chamado, o atendente **não consegue resolvê-lo** — a pendência precisa ser concluída antes. Finalizar a última tarefa **não** resolve nem fecha o chamado sozinho: libera o atendente para resolvê-lo.
>
> Chamado resolvido, fechado ou cancelado não recebe tarefa nova, e a tarefa dele só pode ser finalizada ou cancelada. Ao cancelar o chamado, as tarefas pendentes são canceladas junto.

---

### 12. Acompanhar os indicadores e relatórios

**Quem pode:** Atendente da Central de Serviços (e o Auditor).

1. No menu, acesse **Central de Serviços › Relatórios › Indicadores**. A tela tem filtros de período, unidade organizacional e grupo de atendimento; ajuste o que precisar e clique em **Enviar**.

   ![Filtros dos indicadores](usuario/12-indicadores-filtros.webp)

   **Resultado:** a tela passa a mostrar os gráficos de chamados abertos, reabertos, fechados, escalados/retornados, reclassificados, avaliações e tempos médios.

   ![Indicadores](usuario/12-indicadores.webp)

2. Acesse **Central de Serviços › Relatórios › Atendimentos por Ano**, confira o **Ano de Início** e o **Ano de Término** e clique em **Enviar**.

   ![Atendimentos por ano](usuario/12-atendimentos-por-ano.webp)

3. Acesse **Central de Serviços › Relatórios › Situação dos Atendentes** para ver quantos chamados cada atendente tem atribuídos, filtrando por unidade, grupo e setor.

   ![Situação dos atendentes](usuario/12-situacao-dos-atendentes.webp)

---

## Telas de apoio

Cadastros consultados pelos formulários deste módulo. Todos seguem o mesmo padrão do SUAP — listar, adicionar, editar, remover — e não têm passo a passo próprio. Ficam em **Central de Serviços › Cadastros**, exceto a última:

Categorias de Serviço · Centros de Atendimento · Grupos de Atendimento · Grupos de Serviço · Grupo de Interessados · Monitoramento · Perguntas das Avaliações · Resposta Padrão · Serviços · Tags · Tarefas

- **Tags** são por área de serviço e só aparecem no chamado quando existem tags cadastradas para a área dele.
- **Grupo de Interessados** é um conjunto de pessoas que pode ser vinculado de uma vez a um chamado (a opção aparece no menu **Ações**).
- **Resposta Padrão** é por atendente e alimenta o campo de resposta rápida do formulário de resolução.
- **Perguntas das Avaliações** são as perguntas que o atendente responde ao usar um artigo da Base de Conhecimento.
- **Monitoramento** gera um painel dos chamados de um grupo, acessível por um link com token.
