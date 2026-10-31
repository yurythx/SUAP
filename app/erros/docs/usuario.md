# Erros

É por aqui que qualquer pessoa que usa o SUAP avisa a equipe de desenvolvimento de que alguma tela do sistema não está funcionando — e acompanha o problema até ele ser corrigido. Cada erro reportado vira um registro com linha do tempo própria: quem reportou e quem atende conversam ali, anexam prints, e a situação vai andando de **Reportado** até **Resolvido**.

Quem atende também usa este módulo do outro lado do balcão: para organizar a fila (atribuir, juntar duplicatas, descartar o que não é defeito) e para publicar, ao resolver, a nota de atualização que o SUAP mostra a todos os usuários.

## Quem usa este módulo

| Perfil | O que faz aqui |
| --- | --- |
| Qualquer pessoa com acesso ao SUAP (servidor, aluno, prestador de serviço) | Reporta o erro que encontrou e acompanha a resolução |
| Analista | Atende o erro: assume, analisa, registra a correção e resolve |
| Recebedor de Demandas | Tria a fila que chega: atribui o erro a um analista, unifica duplicatas e descarta o que não é erro |
| Quem atende na Central de Serviços | Reclassifica em erro o chamado que, na verdade, é defeito do sistema |

---

## Antes de começar

O canal de erros é **só para defeito de funcionalidade do SUAP**, e a própria tela de abertura avisa disso. Ele **não** serve para:

1. solicitar alterações em dados cadastrados no SUAP;
2. informar problemas com dados presentes no SUAP;
3. tirar dúvidas sobre as regras de cada módulo;
4. sugerir melhorias.

Nos quatro casos o erro reportado será **cancelado** — procure o setor responsável pelo módulo. O atendimento é feito exclusivamente pelo setor de Tecnologia da Informação.

**As situações de um erro**

| Situação | O que significa |
| --- | --- |
| Reportado | O erro foi reportado para a equipe de desenvolvimento e ainda não tem ninguém atendendo |
| Em análise | A equipe de desenvolvimento já começou a analisar |
| Em correção | A solução já foi encontrada e o SUAP será atualizado em breve com a correção |
| Aguardando feedback | Quem atende devolveu o erro pedindo mais informação a quem reportou |
| Resolvido | O SUAP foi atualizado com a correção |
| Reaberto | Quem reportou avisou que o problema voltou (ou nunca deixou de acontecer) |
| Cancelado | O que foi relatado não é defeito do sistema |
| Unificado | Era duplicata; o registro foi absorvido por outro erro |

**Reportado**, **Em análise**, **Em correção** e **Resolvido** formam a régua que aparece no topo da página do erro, com a situação atual em destaque. Nas outras quatro, no lugar da régua aparece só uma tarja com o nome da situação.

---

## Tarefas

### 1. Reportar um erro

**Quem pode:** qualquer pessoa com acesso ao SUAP.
**Quando usar:** assim que uma tela do SUAP apresentar defeito — de preferência **sem sair dela**, porque o endereço da página é registrado automaticamente e é ele que direciona o erro para o módulo certo.

1. Na própria página em que o problema aconteceu, clique em **Reportar erro**, na barra de botões do rodapé.
2. **Passo 1 de 2** — leia as *Instruções para Abertura de Erro*, marque **Li as instruções** e **Concordo em compartilhar meus dados** e clique em **Continuar**.

   ![Passo 1: instruções e confirmação de ciência](usuario/reportar-instrucoes.webp)

3. **Passo 2 de 2** — o campo **URL com Erro** já vem preenchido com a página de origem. Em **Descreva a operação que você estava realizando...**, conte o que você estava fazendo e qual mensagem o sistema mostrou. Clique em **Finalizar**.

   ![Passo 2: descrição do erro](usuario/reportar-descricao.webp)

**Resultado:** aparece *"Erro reportado com sucesso."* e você é levado à página do erro, na situação **Reportado**. Você entra automaticamente como interessado, e passa a receber as novidades dele.

![Página do erro recém-reportado](usuario/erro-reportado.webp)

A partir daí o erro também aparece no quadro **Erros** da sua tela inicial, com o contador *Aguardando resolução*.

![Quadro Erros na tela inicial](usuario/inicio-quadro-erros.webp)

**Se esse erro já tiver sido reportado:** em vez do formulário, a tela mostra os erros já abertos para aquela mesma página, com o aviso *"Verifique abaixo se este erro foi reportado por outros usuários e se torne interessado para acompanhar sua resolução."*. Clique em **Tornar-se Interessado** no cartão do erro — é o que evita a duplicata e ainda assim mantém você informado. Só use **Não encontrei erro similar. Desejo reportar um novo erro.** se o seu problema for mesmo outro.

![Erros similares oferecidos antes do formulário](usuario/reportar-similares.webp)

---

### 2. Encontrar os erros já reportados

**Quem pode:** Aluno, Prestador de Serviço e Servidor.
**Quando usar:** para saber se o problema que você viu já é conhecido, ou para acompanhar como está a fila de um módulo.

1. No menu, acesse **Tec. da Informação › Desenvolvimento › Erros**.
2. Escolha a **área** do SUAP.

   ![Escolher área](usuario/areas.webp)

3. A tela seguinte lista os módulos daquela área. Cada cartão traz o que o módulo faz, os contadores das situações que têm erro (*Reportados*, *Em análise*, *Em correção*, *Aguardando feedback*, *Resolvidos*) e o botão **Reportar erro do módulo**, que abre a tela da tarefa 1 já apontada para aquele módulo.

   ![Escolher módulo](usuario/modulos.webp)

4. Clique no nome do módulo para ver a lista de erros dele.

**Resultado:** a listagem de erros, com uma aba por situação (**Reportados**, **Em análise**, **Em correção**, **Aguardando feedback**, **Resolvidos**, **Cancelados**, **Todos**) e os filtros *Texto*, *Módulo Afetado*, *Sou Interessado*, *Possui URL do GitLab* e *Atendente Atual*. O ícone de exibição abre a página do erro.

![Listagem de erros do módulo](usuario/listagem.webp)

Esta listagem é só de consulta — não há *Adicionar* nem *Editar*. Tudo o que se faz com um erro acontece dentro da página dele.

---

### 3. Acompanhar um erro

**Quem pode:** os interessados no erro — quem o reportou (entra automaticamente) e quem clicou em **Tornar-se interessado**. Quem atende também participa da conversa.
**Quando usar:** enquanto o erro não estiver resolvido.

**Conversar com quem atende**

1. Abra o erro e, na aba **Linha do tempo**, escreva em **Adicionar interação** e clique no botão de mesmo nome.

![Página do erro, do ponto de vista de quem reportou](usuario/erro-interessado.webp)

**Resultado:** *"Comentário cadastrado com sucesso."* e o texto passa a constar na linha do tempo, junto com o registro automático de cada mudança de situação.

![Linha do tempo com o comentário publicado](usuario/linha-do-tempo.webp)

**Anexar um print ou arquivo**

2. Vá à aba **Anexos** e clique em **Adicionar anexo**.
3. Informe a **Descrição**, escolha o **Arquivo** e clique em **Enviar**.

   ![Formulário de anexo](usuario/anexo-formulario.webp)

**Resultado:** *"Anexo adicionado com sucesso."* e o anexo passa a listar na aba, com quem o enviou e quando.

**Responder quando o erro estiver aguardando feedback**

4. Se a situação for **Aguardando feedback**, a caixa de interação ganha o bloco **Enviar feedback**, com duas respostas: **O erro ainda não foi resolvido** e **O erro foi resolvido**. Escreva a interação, escolha uma das duas e clique em **Adicionar interação**.

   ![Pedido de feedback, como quem reportou o vê](usuario/feedback.webp)

**Resultado:** *"Situação alterada com sucesso."* — a resposta tira o erro da espera e o devolve à equipe.

**Reabrir um erro que voltou a acontecer**

5. Num erro **Resolvido**, quem o reportou vê o botão **O erro persiste?**. Clique nele, confirme, informe o **Motivo** e clique em **Enviar**.

   ![Erro resolvido, com o botão O erro persiste?](usuario/erro-resolvido.webp)

   ![Motivo da reabertura](usuario/reabrir-motivo.webp)

**Resultado:** *"Situação alterada com sucesso."* e o erro volta para a situação **Reaberto**, de novo na fila.

**Deixar de acompanhar:** quem se tornou interessado por conta própria pode sair pelo botão **Remover interesse**. Quem reportou o erro não tem essa opção — continua interessado no próprio erro.

---

### 4. Atender um erro

**Quem pode:** quem pertence ao grupo **Analista**.
**Quando usar:** ao pegar para si um erro da fila, até fechá-lo.

**Etapa 1 — assumir**

1. Abra o erro e clique em **Assumir**.

   ![Erro na fila, como o analista o vê](usuario/erro-atendente.webp)

**Resultado:** *"Você agora é o Atendente Principal deste erro."* O erro passa sozinho de **Reportado** para **Em análise**, seu nome aparece como *Atendente principal* e a página ganha o botão **Devolver**, para o caso de o erro não ser da sua alçada.

Quem atende vê mais coisas que os demais na página do erro: em *Dados gerais*, o **Módulo**, a **View**, o **User Agent**, o **Endereço IP** e os temas usados por quem reportou; e duas abas a mais, **Notas Internas** e **Atualização**.

![Erro assumido, com as abas de quem atende](usuario/erro-em-analise.webp)

**Etapa 2 — conversar e registrar notas**

2. Responda a quem reportou pela aba **Linha do tempo**, em **Adicionar interação**. Se você tiver textos prontos cadastrados (ver *Telas de apoio*), eles aparecem em **Resposta padrão** logo acima da caixa e preenchem a interação com um clique.
3. Para o que é da equipe e não deve ser lido por quem reportou, use a aba **Notas Internas** › **Adicionar Nota interna**.

   ![Nota interna, visível apenas para quem atende](usuario/nota-interna.webp)

**Etapa 3 — mover a situação**

4. Use o botão **Alterar situação** no topo da página e escolha o destino. As opções disponíveis mudam conforme a situação atual — de *Em análise*, por exemplo, é possível ir para **Em correção**, **Resolvido**, **Aguardando feedback** ou **Cancelado**.

A mesma mudança pode ser feita junto com um comentário: na caixa **Adicionar interação** há o bloco **Alterar situação**, com as mesmas opções. Assim a mudança já vai acompanhada da explicação.

**Se o erro foi reportado da página errada:** em **Opções** › **Editar URL do Erro**, informe o endereço em que o problema realmente acontece e clique em **Enviar**. Vale a pena corrigir: é a URL que define o módulo afetado e a busca por duplicatas. O mesmo menu traz **Editar URL do Sentry** e **Editar URL do Gitlab**.

![Menu Opções de quem atende](usuario/opcoes-atendente.webp)

**Etapa 4 — registrar a atualização e resolver**

5. Na aba **Atualização**, clique em **Editar** e preencha **Título** (o texto que os usuários vão ler), **Tipo** (*Bug*, *Funcionalidade* ou *Manutenção*) e **Grupos Envolvidos**. Clique em **Salvar**.

   ![Formulário da atualização](usuario/atualizacao-formulario.webp)

6. Clique em **Alterar situação** › **Resolvido**. O formulário da atualização é oferecido de novo — é a última chance de descrever a correção. Clique em **Salvar** (ou **Pular**).

**Resultado:** *"Situação alterada com sucesso."*, a régua marca **Resolvido** e a atualização é publicada como nota de versão do SUAP, etiquetada com o módulo afetado. Quem reportou passa a ver o botão **O erro persiste?** (tarefa 3).

![Erro resolvido](usuario/erro-resolvido-atendente.webp)

**Se você era atendente auxiliar:** no bloco *Outros atendentes*, à direita, o próprio nome traz o botão **Me remover do atendimento**. Ele não afeta o atendente principal.

---

### 5. Triar os erros que chegam

**Quem pode:** quem pertence ao grupo **Recebedor de Demandas**.
**Quando usar:** na varredura dos erros recém-reportados, antes de eles ficarem parados na fila.

Quem só tria vê a página do erro reduzida: a descrição, a URL e o menu **Opções**. A linha do tempo, os anexos e as notas internas ficam visíveis apenas para quem é interessado ou atende.

![Menu Opções de quem tria a fila](usuario/opcoes-gerente.webp)

**Entregar o erro a um analista**

1. Em **Opções** › **Atribuir atendente**, escolha o **Atendente** (a busca aceita nome ou matrícula) e clique em **Enviar**.

   ![Formulário de atribuição](usuario/atribuir-formulario.webp)

**Resultado:** *"Usuário atribuído com sucesso."* O erro sai de **Reportado** para **Em análise** em nome de quem foi atribuído — quem atribui não vira atendente.

**Juntar duplicatas**

2. Abra o erro que ficará como principal e vá em **Opções** › **Unificar erros**. No campo **Erros**, escolha os que devem ser absorvidos e clique em **Enviar**. A lista só oferece erros da mesma tela; a busca aceita o número ou a URL do erro.

   ![Formulário de unificação](usuario/unificar-formulario.webp)

**Resultado:** *"Erros unificados com sucesso."* Os absorvidos passam à situação **Unificado**, seus interessados migram para o erro principal e a descrição de cada um vira um comentário na linha do tempo dele.

**Descartar o que não é erro**

**Quem pode:** quem é Recebedor de Demandas **e** Analista.

3. Num erro ainda **Reportado**, use **Opções** › **Cancelar por erro de abertura** e confirme.

**Resultado:** *"Cancelado por não atender às instruções exibidas na tela de abertura deste Erro."* e o erro fica **Cancelado**.

---

### 6. Reportar um erro a partir de um chamado

**Quem pode:** quem pode reclassificar o chamado na Central de Serviços — na prática, quem o atende ou responde pelo grupo de atendimento.
**Quando usar:** quando o chamado aberto por alguém não é dúvida nem solicitação, e sim defeito do sistema.

1. No chamado, use a ação **Reportar erro do sistema**.
2. Na tela **Reportar erro a partir do chamado #N**, informe a **URL com Erro** (o endereço completo da página em que o defeito ocorre) e **Descreva a operação que você estava realizando antes de ocorrer o erro**. Clique em **Enviar**.

   ![Formulário de reclassificação do chamado](usuario/chamado-formulario.webp)

**Resultado:** *"Erro reportado com sucesso."* O erro nasce em seu nome, a linha do tempo dele registra de qual chamado veio, **os interessados do chamado passam a ser interessados do erro** e o chamado recebe um comentário com o link. Como a descrição fica visível para todos os usuários, ela não deve conter dados pessoais — a própria tela avisa isso.

---

## Telas de apoio

**Respostas Frequentes** (**Tec. da Informação › Desenvolvimento › Cadastros › Respostas Frequentes**) é a única tela de apoio do módulo, e está disponível para o grupo **Analista**. Cada resposta cadastrada é um texto pronto que aparece na lista **Resposta padrão**, acima da caixa de interação da página do erro, e preenche a resposta com um clique. Cada pessoa vê e usa apenas as suas.
