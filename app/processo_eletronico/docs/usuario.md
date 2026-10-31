# Processo Eletrônico

Use o Processo Eletrônico para abrir requerimentos, transformá-los em processos administrativos, incluir documentos, controlar o nível de acesso, registrar comentários, despachos e ciências e encaminhar processos entre setores até a sua finalização.

## Antes de começar

Algumas tarefas dependem de configurações anteriores:

1. Cadastre o tipo de processo que será usado (tarefa 1).
2. Configure o trâmite quando o tipo de processo tiver um fluxo definido entre setores (tarefa 3).
3. Defina quem pode operar a caixa de processos do setor (tarefa 4). Sem essa autorização, o Operador de Processo Eletrônico não vê o botão **Adicionar Processo Eletrônico**.
4. O setor em que o processo é criado — ou um setor acima dele — precisa ter o código SIORG cadastrado. Sem esse código, o sistema não gera o número do processo e exibe a mensagem **O setor "…" não está com o código SIORG cadastrado**.

**Como chegar à página de um processo:** acesse **Documentos/Processos › Processos Eletrônicos › Processos** (todos os processos que você pode ver) ou **Documentos/Processos › Processos Eletrônicos › Caixa de processos** (os processos do seu setor) e clique no número do processo. A partir da tarefa 7, os botões e menus citados ficam nessa página. Os botões só aparecem para quem pode executar a ação.

## Quem usa este módulo

| Perfil | O que faz aqui |
| --- | --- |
| Servidor, Prestador de Serviço ou Aposentado | Abre requerimentos e gera processos eletrônicos a partir deles |
| Gerente Sistêmico de Processo Eletrônico | Mantém os cadastros e as configurações gerais dos processos |
| Chefe de Setor | Cria, edita e tramita os processos do setor |
| Chefia do setor ou Servidores Com Poder de Chefe | Define quem pode operar a caixa de processos do setor |
| Operador de Processo Eletrônico | Cria e opera os processos do setor, depois de autorizado pela chefia |
| Tramitador de Processos Eletrônicos | Encaminha e recebe processos |
| Gestão Nível de Acesso dos Processos Documentos Eletrônicos | Altera o nível de acesso de qualquer processo |

## Tarefas

### 1. Cadastrar um tipo de processo

**Quem pode:** Gerente Sistêmico de Processo Eletrônico.

1. No menu, acesse **Documentos/Processos › Processos Eletrônicos › Cadastros › Tipos de Processos** e clique em **Adicionar Tipo de Processo**.

   ![Listagem de tipos de processo](usuario/tipo-processo-listagem-r3.webp)

2. Preencha o formulário. Os campos que merecem atenção:

   | Campo | O que informar |
   | --- | --- |
   | Níveis de Acesso Permitidos | Quais níveis (privado, restrito, público) um processo deste tipo pode ter |
   | Nível de Acesso Padrão | O nível já sugerido quando um processo deste tipo é aberto |
   | Permite Gerar Processo via Requerimento? | Marque para o tipo aparecer no formulário de requerimento (tarefa 5) |

   ![Formulário de tipo de processo preenchido](usuario/tipo-processo-formulario-r3.webp)

3. Clique em **Salvar**.

**Resultado:** a mensagem **Cadastro realizado com sucesso** é exibida e o novo tipo aparece na listagem.

![Tipo de processo cadastrado](usuario/tipo-processo-salvo-r3.webp)

### 2. Cadastrar um modelo de despacho

**Quem pode:** Gerente Sistêmico de Processo Eletrônico.

1. No menu, acesse **Documentos/Processos › Processos Eletrônicos › Cadastros › Modelos de Despacho** e clique em **Adicionar Modelo de Despacho**.
2. Preencha **Cabeçalho** e **Rodapé**.

   ![Formulário de modelo de despacho](usuario/modelo-despacho-formulario-r3.webp)

3. Clique em **Salvar**.

**Resultado:** a mensagem **Cadastro realizado com sucesso** é exibida e o modelo aparece na listagem.

![Modelo de despacho cadastrado](usuario/modelo-despacho-salvo-r3.webp)

### 3. Configurar o trâmite do processo

**Quem pode:** Gerente Sistêmico de Processo Eletrônico.
**Quando usar:** quando um tipo de processo precisar seguir um fluxo definido entre setores.

1. No menu, acesse **Documentos/Processos › Processos Eletrônicos › Cadastros › Configurações do Trâmite do Requerimento** e clique em **Adicionar Configuração do Trâmite do Processo**.
2. Em **Tipo de Processo**, clique em **Buscar**, selecione o tipo e clique em **Confirmar**.
3. Informe a **Origem do interessado**. Em **Destino do primeiro trâmite**, selecione **Buscar usando o Autocompletar** e informe o **Setor de Destino**.

   ![Configuração do trâmite preenchida](usuario/configuracao-tramite-formulario-r3.webp)

4. Clique em **Salvar**.

**Resultado:** a mensagem **Cadastro realizado com sucesso** é exibida.

![Configuração do trâmite cadastrada](usuario/configuracao-tramite-salvo-r3.webp)

### 4. Definir quem opera a caixa de processos do setor

**Quem pode:** a chefia do setor ou um membro do grupo **Servidores Com Poder de Chefe**.

1. No menu, acesse **Documentos/Processos › Permissões** e abra a aba **Processos Eletrônicos**.

   ![Permissões da caixa de processos](usuario/permissoes-formulario-r3.webp)

2. No campo **Servidores/Prestadores de Serviço que podem adicionar e operar processos eletrônicos** do seu setor, selecione a pessoa.

   ![Permissão preenchida](usuario/permissoes-preenchido-r3.webp)

3. Clique em **Enviar**.

**Resultado:** a mensagem **Operação realizada com sucesso** é exibida e a pessoa passa a ver o botão **Adicionar Processo Eletrônico**.

![Permissões salvas](usuario/permissoes-salvo-r3.webp)

### 5. Abrir um requerimento e gerar um processo eletrônico

**Quem pode:** Servidor, Prestador de Serviço ou Aposentado.
**Quando usar:** quando a solicitação deve dar origem a um processo eletrônico com os dados do requerimento.
**Pré-condição:** o tipo de processo precisa permitir a geração via requerimento (tarefa 1), e o seu setor precisa ter o código SIORG (veja **Antes de começar**).

1. No menu, acesse **Documentos/Processos › Processos Eletrônicos › Requerimentos** e clique em **Adicionar Requerimento**.

   ![Listagem de requerimentos](usuario/requerimento-listagem-r3.webp)

2. Em **Tipo de Processo**, clique em **Buscar**, selecione o tipo e clique em **Confirmar**. O **Nível de Acesso Padrão** é preenchido a partir do tipo escolhido e não pode ser alterado aqui.

   ![Formulário de requerimento](usuario/requerimento-formulario-r3.webp)

3. Informe o **Assunto** e a **Descrição**. A descrição será usada no requerimento que dará origem ao processo.

   ![Requerimento preenchido](usuario/requerimento-preenchido-r3.webp)

4. Clique em **Salvar**.

   **Resultado:** o requerimento é cadastrado e sua página de gerenciamento é aberta, com a situação **Iniciado**.

   ![Requerimento cadastrado](usuario/requerimento-gerenciado-r3.webp)

   **Opcional:** antes de gerar o processo, use **Adicionar Documento Interno** ou **Upload de Documento Externo** para incluir documentos no requerimento.

5. Clique em **Gerar Processo Eletrônico**.
6. Em **Destino do primeiro trâmite**, escolha como buscar o setor, informe o **Setor de Destino**, selecione o **Perfil** e informe sua **Senha**.

   ![Formulário de finalização do requerimento](usuario/requerimento-finalizacao-formulario-r3.webp)

   ![Finalização do requerimento preenchida](usuario/requerimento-finalizacao-preenchido-r3.webp)

7. Clique em **Enviar**.

**Resultado:** a mensagem **Requerimento finalizado com sucesso** é exibida, um processo eletrônico é criado com os dados do requerimento e o primeiro trâmite é encaminhado ao setor escolhido.

![Processo criado a partir do requerimento](usuario/requerimento-processo-criado-r3.webp)

### 6. Criar um processo

**Quem pode:** Chefe de Setor, Gerente Sistêmico de Processo Eletrônico ou Operador de Processo Eletrônico autorizado pela chefia (tarefa 4).

1. No menu, acesse **Documentos/Processos › Processos Eletrônicos › Processos** e clique em **Adicionar Processo Eletrônico**.

   ![Listagem de processos](usuario/processo-listagem-r3.webp)

2. Em **Tipo de Processo**, clique em **Buscar**, selecione o tipo e clique em **Confirmar**.
3. Informe os **Interessados**, o **Assunto**, o **Nível de Acesso** e o **Setor de Criação**.

   ![Formulário de processo preenchido](usuario/processo-formulario-r3.webp)

4. Clique em **Salvar**.

**Resultado:** a mensagem **Cadastro realizado com sucesso** é exibida e o processo é criado.

![Processo criado](usuario/processo-criado-r3.webp)

### 7. Receber um processo

**Quem pode:** quem opera a caixa do setor de destino — Chefe de Setor, Operador de Processo Eletrônico ou Tramitador de Processos Eletrônicos.

1. Acesse **Documentos/Processos › Processos Eletrônicos › Caixa de processos** e abra o processo encaminhado ao seu setor.
2. Clique em **Receber** e confirme.

**Resultado:** a mensagem **Processo recebido com sucesso.** é exibida.

![Processo recebido](usuario/receber-salvo-r3.webp)

### 8. Encaminhar um processo sem despacho

**Quem pode:** quem opera a caixa do setor em que o processo está — Chefe de Setor, Gerente Sistêmico de Processo Eletrônico, Operador de Processo Eletrônico ou Tramitador de Processos Eletrônicos.

1. Na página do processo, clique em **Encaminhar › Sem despacho**.

   ![Formulário de encaminhamento sem despacho](usuario/encaminhar-sem-formulario-r3.webp)

2. Em **Buscar setor de destino por**, selecione **Autocompletar** e informe o **Setor de Destino**.

   ![Encaminhamento sem despacho preenchido](usuario/encaminhar-sem-preenchido-r3.webp)

3. Clique em **Salvar**.

**Resultado:** a mensagem **Processo encaminhado com sucesso.** é exibida.

![Processo encaminhado sem despacho](usuario/encaminhar-sem-salvo-r3.webp)

### 9. Encaminhar um processo com despacho

**Quem pode:** os mesmos perfis da tarefa 8.

1. Na página do processo, clique em **Encaminhar › Com despacho**.

   ![Formulário para encaminhar com despacho](usuario/encaminhar-com-formulario-r3.webp)

2. Escreva o **Despacho**. Em **Buscar setor de destino por**, selecione **Autocompletar**, informe o **Setor de Destino** e selecione o **Perfil** com que vai assinar.

   ![Encaminhamento com despacho preenchido](usuario/encaminhar-com-preenchido-r3.webp)

3. Informe a senha e clique em **Salvar**.

**Resultado:** a mensagem **Processo encaminhado com sucesso.** é exibida.

![Processo encaminhado com despacho](usuario/encaminhar-com-salvo-r3.webp)

### 10. Remover o último trâmite

**Quem pode:** quem opera a caixa do setor que encaminhou o processo, enquanto ele estiver na caixa de saída desse setor.
**Quando usar:** para desfazer um encaminhamento feito por engano.

1. Na página do processo, clique em **Ações › Remover último trâmite** e confirme.

   ![Processo com opção para remover o último trâmite](usuario/remover-tramite-criado-r3.webp)

**Resultado:** a mensagem **Último trâmite removido com sucesso.** é exibida.

![Último trâmite removido](usuario/remover-tramite-salvo-r3.webp)

### 11. Editar o assunto do processo

**Quem pode:** quem pode editar o processo, enquanto ele estiver em trâmite.

1. Na página do processo, clique em **Editar dados › Assunto**.
2. Informe o novo **Assunto** e a **Justificativa da alteração**.

   ![Formulário de edição de assunto](usuario/editar-assunto-formulario-r3.webp)

3. Clique em **Salvar**.

**Resultado:** a mensagem **O assunto do processo foi alterado com sucesso.** é exibida.

![Assunto alterado](usuario/editar-assunto-salvo-r3.webp)

### 12. Alterar os interessados do processo

**Quem pode:** quem pode editar o processo.

1. Na página do processo, clique em **Editar dados › Interessados**. O formulário abre sobre a página.

   ![Formulário de edição de interessados](usuario/interessados-formulario-r3.webp)

2. Em **Interessados**, inclua ou remova as pessoas e informe a **Justificativa**.

   ![Interessados preenchidos](usuario/interessados-preenchido-r3.webp)

3. Informe a senha e clique em **Enviar**.

**Resultado:** a mensagem **Os interessados do processo foram alterados com sucesso.** é exibida.

![Interessados alterados](usuario/interessados-salvo-r3.webp)

### 13. Alterar o nível de prioridade do processo

**Quem pode:** quem pode editar o processo.

1. Na página do processo, clique em **Editar dados › Nível de prioridade**.

   ![Formulário de prioridade](usuario/prioridade-formulario-r3.webp)

2. Em **Prioridade**, selecione o nível e informe a **Justificativa**.

   ![Prioridade preenchida](usuario/prioridade-preenchido-r3.webp)

3. Clique em **Salvar**.

**Resultado:** a mensagem **O nível de prioridade foi atualizado com sucesso.** é exibida.

![Prioridade alterada](usuario/prioridade-salvo-r3.webp)

### 14. Adicionar documentos ao processo

**Quem pode:** quem pode editar o processo.

**Etapa 1 — documento interno já finalizado**

1. Na página do processo, na aba **Documentos**, clique em **Adicionar documento**. A lista **Documentos que podem ser adicionados ao processo** mostra os documentos finalizados do setor.

   ![Documentos disponíveis](usuario/documentos-lista-r3.webp)

2. No documento desejado, clique em **Adicionar ao processo**.

   ![Documento interno adicionado](usuario/documento-interno-salvo-r3.webp)

   A mensagem **Documento adicionado com sucesso.** confirma a inclusão.

**Etapa 2 — documento externo (arquivo)**

3. Na mesma aba **Documentos**, clique em **Upload de documento externo**.

   ![Formulário de upload de documento externo](usuario/documento-externo-formulario-r3.webp)

4. Preencha **Tipo**, selecione o **Arquivo**, escolha o **Tipo de Conferência**, informe o **Assunto** e selecione o **Nível de Acesso**. Clique em **Salvar**.
5. Selecione o **Perfil**, informe a senha e clique em **Assinar Documento**.

   ![Documento externo pronto para assinatura](usuario/documento-externo-assinatura-r3.webp)

**Resultado:** a mensagem **Documento anexado com sucesso.** é exibida.

![Documento externo anexado](usuario/documento-externo-salvo-r3.webp)

### 15. Adicionar um comentário ao processo

**Quem pode:** quem pode editar o processo.

1. Na página do processo, abra a aba **Comentários** e clique em **Adicionar Comentário**.

   ![Formulário de comentário](usuario/comentario-formulario-r3.webp)

2. Escreva o **Comentário** e clique em **Salvar**.

**Resultado:** a mensagem **Comentário adicionado com sucesso.** é exibida e o comentário aparece na aba.

![Comentário adicionado](usuario/comentario-salvo-r3.webp)

### 16. Alterar o nível de acesso do processo

**Quem pode:** membros do grupo **Gestão Nível de Acesso dos Processos Documentos Eletrônicos**, em qualquer processo; quem pode editar o processo, enquanto ele não estiver finalizado; e os interessados de um processo finalizado.

1. Na página do processo, clique em **Nível de acesso › Editar nível de acesso**.

   ![Formulário para alterar nível de acesso](usuario/alterar-nivel-formulario-r3.webp)

2. Em **Para**, selecione o novo nível. Para **Restrito**, selecione também a **Hipótese Legal** que justifica a restrição.

   ![Nível de acesso preenchido](usuario/alterar-nivel-preenchido-r3.webp)

3. Informe a senha e clique em **Enviar**.

**Resultado:** a mensagem **Nível de Acesso alterado com sucesso.** é exibida.

![Nível de acesso alterado](usuario/alterar-nivel-salvo-r3.webp)

### 17. Solicitar a alteração do nível de acesso

**Quem pode:** quem vê o processo mas não pode alterar o nível diretamente (veja a tarefa 16).

1. Na página do processo, clique em **Nível de acesso › Solicitar alteração de nível de acesso**.

   ![Formulário de solicitação de alteração de nível](usuario/solicitar-nivel-formulario-r3.webp)

2. Em **Novo Nível de Acesso**, selecione o nível desejado em **Para** e, se for **Restrito**, a **Hipótese Legal**. Escreva a **Justificativa**.

   ![Solicitação de alteração de nível preenchida](usuario/solicitar-nivel-preenchido-r3.webp)

3. Informe a senha em **Senha para confirmação** e clique em **Enviar**.

**Resultado:** uma mensagem confirma a solicitação. Quem pode alterar o nível passa a ver, no mesmo menu, **Analisar/Visualizar solicitações de alteração de nível de acesso**.

![Solicitação de alteração de nível registrada](usuario/solicitar-nivel-salvo-r3.webp)

### 18. Solicitar um despacho

**Quem pode:** quem opera o processo.
**Quando usar:** quando o despacho precisa ser assinado por outra pessoa antes do encaminhamento.

1. Na página do processo, clique em **Solicitar › Despacho**.

   ![Formulário de solicitação de despacho](usuario/solicitar-despacho-formulario-r3.webp)

2. Escreva o **Corpo** do despacho e, em **Solicitar Assinatura a**, selecione quem vai assinar. Em **Setor de Destino do Trâmite (Buscar por)**, selecione **Autocompletar** e informe o setor em **Especificar Setor**.

   ![Solicitação de despacho preenchida](usuario/solicitar-despacho-preenchido-r3.webp)

3. Informe a senha e clique em **Salvar**.

**Resultado:** a mensagem **A solicitação de despacho foi efetuada com sucesso.** é exibida.

![Despacho solicitado](usuario/solicitar-despacho-salvo-r3.webp)

### 19. Deferir um despacho

**Quem pode:** a pessoa indicada em **Solicitar Assinatura a** (tarefa 18).
**Pré-condição:** há uma solicitação de despacho pendente para você no processo.

1. A página do processo avisa **Processo possui solicitação de despacho pendente**. Abra a aba **Solicitações** e, na solicitação de despacho, clique em **Analisar**.

   ![Solicitação de despacho pendente](usuario/despacho-pendente-r3.webp)

   ![Formulário para deferir despacho](usuario/deferir-despacho-formulario-r3.webp)

2. Selecione o **Perfil**, informe a senha e clique em **Deferir e Encaminhar**.

**Resultado:** a mensagem **Processo encaminhado com sucesso.** é exibida e o processo segue para o setor indicado na solicitação.

![Despacho deferido](usuario/deferir-despacho-salvo-r3.webp)

### 20. Indeferir um despacho

**Quem pode:** a pessoa indicada em **Solicitar Assinatura a** (tarefa 18).
**Pré-condição:** há uma solicitação de despacho pendente para você no processo.

1. Na página do processo, abra a aba **Solicitações** e, na solicitação de despacho, clique em **Indeferir**.

   ![Formulário para indeferir despacho](usuario/indeferir-despacho-formulario-r3.webp)

2. Escreva a **Justificativa da Rejeição** e clique em **Salvar**.

**Resultado:** a mensagem **Despacho indeferido com sucesso.** é exibida e o processo não é encaminhado.

![Despacho indeferido](usuario/indeferir-despacho-salvo-r3.webp)

### 21. Solicitar ciência em um processo

**Quem pode:** quem opera o processo.

1. Na página do processo, clique em **Solicitar › Ciência**.

   ![Formulário para solicitar ciência](usuario/solicitar-ciencia-formulario-r3.webp)

2. Clique no campo **Interessados**, marque as pessoas na janela que se abre e clique em **Confirmar**. Só aparecem interessados que têm acesso ao SUAP.
3. Informe a **Data Limite da Ciência**, a **Justificativa da Solicitação** e o **Tipo da Ciência**.

   ![Solicitação de ciência preenchida](usuario/solicitar-ciencia-preenchido-r3.webp)

4. Clique em **Enviar**.

**Resultado:** a mensagem **Solicitações de ciência adicionadas com sucesso.** é exibida.

![Solicitação de ciência registrada](usuario/solicitar-ciencia-salvo-r3.webp)

### 22. Dar ciência em um processo

**Quem pode:** a pessoa de quem a ciência foi solicitada.
**Pré-condição:** há uma solicitação de ciência para você (tarefa 21).

1. Na página do processo, clique em **Dar ciência**.

   ![Formulário para dar ciência](usuario/dar-ciencia-formulario-r3.webp)

2. Selecione o **Perfil**, marque **Declaro-me ciente** e informe a senha.

   ![Ciência preenchida](usuario/dar-ciencia-preenchido-r3.webp)

3. Clique em **Assinar**.

**Resultado:** a mensagem **Ciência do processo … dada com sucesso.** é exibida, com o número do processo.

![Ciência registrada](usuario/dar-ciencia-salvo-r3.webp)

### 23. Solicitar documentos aos interessados

**Quem pode:** quem opera o processo.
**Quando usar:** quando um interessado precisa anexar documentos ao processo.

1. Na página do processo, clique em **Solicitar › Documento**.

   ![Formulário de solicitação de documentos](usuario/juntada-formulario-r3.webp)

2. Clique no campo **Solicitados**, marque as pessoas na janela que se abre e clique em **Confirmar**. Só aparecem interessados do processo que têm acesso ao SUAP.
3. Escreva a **Motivação** e informe a **Data Limite**.

   ![Solicitação de documentos preenchida](usuario/juntada-preenchido-r3.webp)

4. Clique em **Enviar**.

**Resultado:** a mensagem **Solicitações de Juntada de Documentos adicionadas com sucesso.** é exibida.

![Solicitação de documentos registrada](usuario/juntada-salvo-r3.webp)

### 24. Apensar processos

**Quem pode:** quem pode editar os processos envolvidos.
**Quando usar:** para que processos do mesmo setor tramitem juntos, sem perder a numeração própria.

1. Na página do processo principal, abra a aba **Processos Apensados, Anexados e Relacionados** e clique em **Apensar Processo**.

   ![Formulário de apensamento](usuario/apensar-formulario-r3.webp)

2. Em **Processos a Apensar**, informe os processos. Só aparecem processos ativos que estão no mesmo setor. Escreva a **Justificativa**.

   ![Apensamento preenchido](usuario/apensar-preenchido-r3.webp)

3. Clique em **Enviar**.

**Resultado:** a mensagem **Processo(s) apensado(s) com sucesso.** é exibida e os processos passam a constar na aba **Processos Apensados, Anexados e Relacionados** do processo principal.

![Processos apensados](usuario/apensar-salvo-r3.webp)

### 25. Relacionar processos

**Quem pode:** quem pode editar o processo.
**Quando usar:** para registrar que dois processos tratam de assuntos ligados, sem que tramitem juntos.

1. Na página do processo, abra a aba **Processos Apensados, Anexados e Relacionados** e clique em **Relacionar Processo**.
2. Use os filtros para localizar o outro processo — por número, campus dono, setor dono, tipo de processo ou data de criação — e clique em **Enviar**.

   ![Processos que podem ser relacionados](usuario/relacionar-lista-r3.webp)

3. Na linha do processo, clique em **Relacionar ao Processo**.

**Resultado:** a mensagem **Relacionamento criado com sucesso.** é exibida.

![Processos relacionados](usuario/relacionar-salvo-r3.webp)

### 26. Adicionar um processo à sua lista de interesses

**Quem pode:** quem vê o processo.
**Quando usar:** para acompanhar um processo que não está no seu setor.

1. Na página do processo, clique em **Adicionar interesse** e confirme.

   ![Detalhe do processo antes de adicionar interesse](usuario/interesse-detalhe-r3.webp)

**Resultado:** a mensagem **Processo adicionado na lista de interesses.** é exibida.

![Interesse adicionado](usuario/interesse-adicionado-r3.webp)

### 27. Remover um processo da sua lista de interesses

**Quem pode:** quem adicionou o processo à própria lista de interesses.

1. Na página do processo, clique em **Ações › Remover interesse**.

   ![Detalhe do processo com interesse](usuario/interesse-remover-detalhe-r3.webp)

**Resultado:** a mensagem **Processo removido da lista de interesses.** é exibida.

![Interesse removido](usuario/interesse-removido-r3.webp)

### 28. Finalizar e reabrir um processo

**Quem pode:** quem pode editar o processo e todos os seus apensados.
**Pré-condição:** o processo está ativo e não tem pendências de documentos.

**Etapa 1 — finalizar**

1. Na página do processo, clique em **Finalizar** e confirme.
2. Selecione o **Perfil**, escreva a **Justificativa** e escolha o **Nível de acesso** do termo de finalização (a **Hipótese Legal** só é obrigatória se o termo não for público).

   ![Formulário de finalização](usuario/finalizar-formulario-r3.webp)

3. Informe a senha em **Senha para confirmação** e clique em **Assinar**.

A mensagem **Processo finalizado com sucesso.** é exibida. Se o processo tiver apensados, eles são desapensados e finalizados junto.

![Processo finalizado](usuario/finalizar-salvo-r3.webp)

**Etapa 2 — reabrir, se necessário**

Pode reabrir o servidor que opera a caixa do setor em que o processo finalizado está.

4. Na página do processo finalizado, clique em **Ações › Remover finalização** e confirme.
5. Preencha **Perfil**, **Justificativa** e **Nível de acesso** do termo de reabertura.

   ![Formulário de reabertura](usuario/reabrir-formulario-r3.webp)

6. Informe a senha e clique em **Assinar**.

**Resultado:** a mensagem **Processo reaberto com sucesso.** é exibida e o processo volta a tramitar.

![Processo reaberto](usuario/reabrir-salvo-r3.webp)

## Telas de apoio

As telas abaixo apoiam a consulta e a administração do módulo, mas não têm passo a passo próprio neste manual:

- **Minhas Permissões**
- **Distribuição de Trâmites**
- **Configurações**
- **Rótulos**
- **Orientações de Nível de Acesso**
- **Solicitações de Alteração de Nível de Acesso** (no menu, aparece como **Solitações de Alteração de Nível de Acesso**)
