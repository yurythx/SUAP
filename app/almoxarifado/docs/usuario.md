# Almoxarifado

Administra o estoque de materiais de consumo da instituição: registra os empenhos de compra e as notas de entrada, entrega material aos setores por requisição, transfere material entre campi e avisa o que está em falta. É por aqui que o material comprado vira saldo no estoque do campus e sai dele para quem pediu.

**Quem usa este módulo**

| Perfil | O que faz aqui |
| --- | --- |
| Coordenador de Almoxarifado | Opera o estoque do campus: empenhos, entradas, requisições, estoque crítico e relatórios |
| Coordenador de Almoxarifado Sistêmico | O mesmo, para toda a instituição; vê os empenhos e relatórios de todos os campi |
| Operador de Almoxarifado | Registra empenhos, entradas e requisições do campus, e consulta os relatórios |
| Gerenciador de Materiais do Almoxarifado | Cadastra e edita os materiais de consumo |
| Contador | Mantém o plano de contas e os elementos de despesa do material de consumo |
| Auditor | Acompanha estoque, empenhos, entradas e relatórios, sem alterar nada |

---

## Antes de começar

O módulo inteiro se apoia num catálogo que precisa existir: **unidades de medida**, **materiais de consumo**, **elementos de despesa** e **plano de contas** (tarefas 1 e 2). Numa instituição já em operação ele está preenchido — se alguma lista aparecer vazia num cadastro, é uma dessas que falta.

O **CATMAT** é opcional: é o código do material no catálogo do governo federal. Preencha quando o material já o tiver.

---

## Tarefas

### 1. Cadastrar uma unidade de medida e um material de consumo

**Quem pode:** Coordenadores de Almoxarifado (do campus e sistêmico), Operador de Almoxarifado e Gerenciador de Materiais do Almoxarifado.
**Quando usar:** ao catalogar material novo para o campus comprar e entregar.

1. No menu, acesse **Administração › Almoxarifado › Cadastros › Unidades de Medida** e clique em **Adicionar Unidade de Medida**.

   ![Unidades de medida](usuario/unidade-medida-listagem.webp)

2. Informe o **Nome** da unidade (por exemplo, `Pacote`, `Caixa`, `Resma`) e salve.

   ![Formulário da unidade de medida](usuario/unidade-medida-formulario.webp)

   **Resultado:** *"Cadastro realizado com sucesso"*.

3. No menu, acesse **Administração › Almoxarifado › Materiais de Consumo** e clique em **Adicionar Material de Consumo**.

   ![Materiais de consumo](usuario/material-listagem.webp)

4. Preencha o formulário:

   | Campo | O que informar |
   | --- | --- |
   | Categoria | O **elemento de despesa** do material (tarefa 2) — é o que liga o material ao balancete |
   | Unidade | A unidade de medida do passo 2 |
   | Nome | A descrição do material, como ele deve aparecer nas requisições |

   ![Formulário do material](usuario/material-formulario.webp)

5. Clique em **Salvar**.

   **Resultado:** *"Cadastro realizado com sucesso"* e o material passa a poder ser empenhado.

---

### 2. Cadastrar o plano de contas e os elementos de despesa

**Quem pode:** Contador, Contador Administrador e Contador Sistêmico — o cadastro de elementos de despesa é exclusivo do Contador Administrador.
**Quando usar:** ao criar uma rubrica contábil nova para o material de consumo. São cadastros raros: numa instituição em operação já vêm preenchidos.

1. No menu, acesse **Administração › Almoxarifado › Plano de Contas** e clique em **Adicionar Plano de Contas**.

   ![Planos de contas](usuario/plano-contas-listagem.webp)

2. Informe o **Código**, a **Descrição** e salve.

   ![Formulário do plano de contas](usuario/plano-contas-formulario.webp)

   **Resultado:** *"Cadastro realizado com sucesso"*.

3. Volte ao menu e acesse **Administração › Almoxarifado › Cadastros › Elementos de Despesa de Mat. de Consumo**; clique em **Adicionar Elemento de Despesa de Mat. de Consumo**.

4. Informe o **Código**, o **Nome** e escolha o **Plano de contas** ao qual o elemento pertence; salve.

   ![Formulário do elemento de despesa](usuario/elemento-despesa-formulario.webp)

   **Resultado:** *"Cadastro realizado com sucesso"*. O elemento passa a aparecer no campo **Categoria** dos materiais (tarefa 1) e nas tabelas dos relatórios.

---

### 3. Registrar um empenho e empenhar itens

**Quem pode:** Coordenadores de Almoxarifado (do campus e sistêmico) e Operador de Almoxarifado.
**Quando usar:** quando uma compra é empenhada e o material ainda vai chegar. O empenho é o que a entrada (tarefa 4) vai "baixar" ao receber a nota.

1. No menu, acesse **Administração › Almoxarifado › Empenhos** e clique em **Adicionar Empenho**.

   ![Empenhos](usuario/empenho-listagem.webp)

2. Preencha o formulário. Os campos que costumam gerar dúvida:

   | Campo | O que informar |
   | --- | --- |
   | UG Emitente | O campus do almoxarifado que receberá o material — é o que faz o empenho aparecer na entrada desse campus |
   | Número de empenho | No formato `9999NE123456`: quatro dígitos, `NE` e seis dígitos; o sistema recusa fora dele |
   | Processo | O processo eletrônico do empenho; busque pelo número |
   | Tipo de Material | **Consumo** para materiais de uso geral; **Permanente** para bens do patrimônio |
   | Tipo de Fornecedor | **Pessoa Física** ou **Pessoa Jurídica** — o campo de fornecedor abaixo se adapta à escolha |
   | Prazo | Prazo em dias para o fornecedor entregar |

   ![Formulário do empenho](usuario/empenho-formulario.webp)

3. Clique em **Salvar**.

4. Na página do empenho, clique em **Empenhar novo item** e informe o **Material**, a **Qtd. Empenhada** e o **Valor Unitário**.

   ![Empenhar item](usuario/empenho-item.webp)

5. Clique em **Salvar**.

   **Resultado:** *"Item de Empenho cadastrada com sucesso."* O item passa a ficar pendente de entrega — é ele que a entrada de compra vai receber.

---

### 4. Efetuar a entrada de compra

**Quem pode:** os perfis operacionais do Almoxarifado; para material permanente, também os do Patrimônio.
**Pré-condição:** o empenho da compra estar registrado e com item pendente (tarefa 3).

1. No menu, acesse **Administração › Almoxarifado › Entradas** e clique em **Efetuar Entrada de Compra**.

   ![Busca de entradas](usuario/entrada-busca.webp)

2. Informe a **Data Entrada** e busque o **Empenho** pelo número — os itens pendentes aparecem numa tabela.

3. Marque o item que chegou e informe a **Qtd Recebida**; preencha o **Nº Nota Fiscal** e a **Data Nota Fiscal**. O **Fornecedor** é preenchido a partir do empenho.

   ![Entrada de compra](usuario/entrada-compra-formulario.webp)

4. Clique em **Efetuar**.

   **Resultado:** *"Entrada realizada com sucesso."* e você é levado à página da entrada, com o item e o valor recebidos — é esta operação que credita o material no estoque do campus.

   ![Entrada registrada](usuario/entrada-detalhe.webp)

---

### 5. Efetuar a entrada de doação

**Quem pode:** os perfis operacionais do Almoxarifado; para material permanente, também os do Patrimônio.
**Quando usar:** quando o material chega doado, sem empenho nem nota de compra.

1. No menu, acesse **Administração › Almoxarifado › Entradas** e clique em **Efetuar Entrada de Doação**.

2. Preencha a **Data**, o **Tipo de Material** (Consumo ou Permanente), o **Fornecedor** (o doador), o **Processo** e, se houver, o número e a data da nota; salve.

   ![Entrada de doação](usuario/entrada-doacao-formulario.webp)

   **Resultado:** *"Entrada realizada com sucesso."* e você é levado à página da entrada.

3. Na página da entrada, clique em **Adicionar Item** e informe o **Material**, a **Qtd** e o **Valor**; clique em **Enviar**.

   ![Item da doação](usuario/entrada-doacao-item.webp)

   **Resultado:** *"Item adicionado com sucesso."* Cada item adicionado credita o saldo do campus.

---

### 6. Registrar uma requisição de saída de material

**Quem pode:** Coordenadores de Almoxarifado (do campus e sistêmico) e Operador de Almoxarifado — é o almoxarifado que registra o pedido em nome do servidor.
**Quando usar:** quando um setor pede material ao almoxarifado.

1. No menu, acesse **Administração › Almoxarifado › Requisições › Saída de Material para Consumo**.

2. Informe a **Pessoa Solicitante** (busque pelo nome) e, se quiser, as **Observações**. Em **Materiais**, informe o **Material** e a **Quantidade**; use **Adicionar Material** para incluir mais de um item na mesma requisição.

   ![Requisição de material](usuario/requisicao-formulario.webp)

3. Clique em **Efetuar**.

   **Resultado:** *"Requisição efetuada com sucesso."* O pedido entra na fila do almoxarifado para atendimento (tarefa 7). Só aparecem no campo **Material** os itens que têm estoque no campus do almoxarifado que está registrando o pedido.

---

### 7. Atender as requisições pendentes

**Quem pode:** Coordenadores de Almoxarifado (do campus e sistêmico) e Operador de Almoxarifado.
**Quando usar:** quando chega um pedido de material (tarefa 6) para ser entregue.

1. No menu, acesse **Administração › Almoxarifado › Requisições › Requisições Pendentes**. A fila tem duas abas: **Saída para Servidores** e **Saída para Outros Campi**.

   ![Requisições pendentes](usuario/requisicoes-pendentes.webp)

2. Clique no ícone de exibição da requisição para abrir a tela de atendimento.

3. Marque **Aceitar?** no item que será entregue e informe a **Qtd. Aceita** — ela pode ser menor que a solicitada (atendimento parcial é comum). Clique em **Responder**.

   ![Responder requisição](usuario/requisicao-atendimento.webp)

   **Resultado:** *"Saída de Material Realizada"*, com links para a nota de fornecimento em HTML e PDF. O estoque do campus baixa na hora; a quantidade aceita não pode ser maior que a disponível em estoque.

---

### 8. Transferir material entre campi

**Quem pode:** Coordenadores de Almoxarifado (do campus e sistêmico) e Operador de Almoxarifado.
**Quando usar:** quando um campus precisa de material que só existe no estoque de outro.

1. No menu, acesse **Administração › Almoxarifado › Requisições › Transferência de Material Intercampi**.

2. Escolha o **Almoxarifado Fornecedor** (o campus que tem o material), informe o **Material** e a **Quantidade**; clique em **Efetuar**.

   ![Transferência intercampi](usuario/transferencia-formulario.webp)

   **Resultado:** *"Requisição efetuada com sucesso."* O pedido fica pendente para o campus fornecedor.

3. Como o **campus de destino**, acesse **Requisições Pendentes**, aba **Saída para Outros Campi**, abra o pedido e responda com a quantidade que vai sair.

   ![Pedido de outro campus](usuario/transferencia-pendente.webp)

   ![Responder transferência](usuario/transferencia-atendimento.webp)

   **Resultado:** *"Saída de Material Realizada."* O saldo sai do campus fornecedor e entra no solicitante.

---

### 9. Controlar o estoque crítico

**Quem pode:** Coordenadores de Almoxarifado (do campus e sistêmico) e Auditor (somente leitura).
**Quando usar:** para o sistema avisar quando um material está perto de acabar e sugerir quanto comprar.

1. No menu, acesse **Administração › Almoxarifado › Controle de Estoque Crítico** e clique em **Adicionar Material Controlado**.

2. Informe o **Material** a controlar (ou a **Categoria**, para controlar de uma vez todos os materiais do elemento), o **Tempo de Aquisição** e o **Intervalo de Aquisição**, em meses; clique em **Enviar**.

   ![Configuração do estoque](usuario/configuracao-estoque.webp)

   **Resultado:** o material entra na lista **Materiais Sob Controle**, na tela de configuração.

   ![Materiais sob controle](usuario/materiais-sob-controle.webp)

3. A tela de **Situação do Estoque** do campus mostra cada material sob controle com a **Situação** (Estoque Normal, Ponto Crítico, Estado de Compra, Estoque Máximo), a **Qtd Em Estoque** e a **Qtd À Ressumprimir**.

   ![Situação do estoque](usuario/estoque-critico.webp)

4. Marque os materiais que serão comprados e use **Gerar Lista de Compra em HTML** ou **em PDF**.

   **Resultado:** a lista de compras sai com as quantidades sugeridas, que podem ser ajustadas antes de gerar.

---

### 10. Consultar os relatórios

**Quem pode:** os perfis do Almoxarifado — Operador e Coordenador veem o próprio campus; Coordenador Sistêmico e Auditor veem a instituição.

**Balancetes e saldo** — em **Administração › Almoxarifado › Relatórios**, os balancetes do **Elemento de Despesa**, do **Elemento de Despesa Detalhado** e do **Material de Consumo**, o **Saldo Atual por ED**, as **Saídas por Setor**, os **Materiais Transferidos** e o **Total por ED Permanente**. Preencha o período (e o elemento de despesa ou o solicitante, conforme o relatório) e clique em **Enviar**.

![Balancete detalhado](usuario/relatorio-balancete.webp)

O **Balancete do Elemento de Despesa Detalhado** roda como tarefa em segundo plano: a tela acompanha o processamento e libera o resultado ao terminar.

![Processamento do relatório](usuario/relatorio-processamento.webp)

**Materiais Transferidos** mostra o que saiu de um campus para outro, filtrado por solicitante e período — não informe uma data final no futuro.

![Materiais Transferidos](usuario/relatorio-materiais-transferidos.webp)

**Saldo Atual por ED** e **Saídas por Setor** consolidam o saldo e o consumo por elemento de despesa e por setor.

![Saldo por elemento de despesa](usuario/relatorio-saldo-ed.webp)

![Saídas por setor](usuario/relatorio-saidas-por-setor.webp)

---

## Telas de apoio

Tabelas e consultas que o módulo usa sem passo a passo próprio:

- **CATMAT** — códigos de material do catálogo federal, consultados no cadastro do material.
- **Importar Estoque por CSV** — carga em massa de saldo, restrita ao perfil de migração.
- **Buscar Requisições** — consulta das requisições já atendidas por tipo, período e material.
- **Histórico de Movimentação** — entradas e saídas de um material, acessível pela listagem de materiais.
- **Devolução de item** — devolução de material entregue, a partir da requisição atendida.
- **Remover Requisição / Remover Itens** — cancelamentos de pedidos e de itens de entrada, disponíveis nas telas correspondentes.
