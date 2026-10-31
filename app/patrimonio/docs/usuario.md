# Patrimônio

Mantém o inventário dos bens permanentes da instituição: cada bem tem um número de tombo, um responsável pela carga, uma sala e um valor contábil. É por aqui que o bem nasce (pela entrada do almoxarifado), passa de mãos entre servidores, é conferido nas salas, entra em cautela e, quando deixa de servir, é baixado.

**Quem usa este módulo**

| Perfil | O que faz aqui |
| --- | --- |
| Coordenador de Patrimônio (do campus e Sistêmico) | Opera o inventário do campus: carga, transferências, baixas, conferências, reavaliações e relatórios |
| Operador de Patrimônio | Dá carga, faz baixas e cautelas e confere salas |
| Contador de Patrimônio | Acompanha as PAs das transferências entre campi e os relatórios contábeis |
| Servidor | Consulta a própria carga, requisita transferência e pede equipamentos |
| Auditor | Acompanha inventário, baixas, cautelas e relatórios, sem alterar nada |

---

## Antes de começar

O bem permanente nasce pela **entrada de material permanente** no Almoxarifado — é a entrada de compra ou de doação (guias do Almoxarifado) que gera um tombamento por unidade recebida, já pendente de carga. O tipo do material da entrada precisa ser **Permanente**.

Para esse cadastro, o módulo se apoia em **Elementos de Despesa de Mat. Permanente** (com plano de contas, vida útil e percentual residual) e no **Plano de Contas**. Numa instituição em operação eles já existem.

---

## Tarefas

### 1. Consultar e atualizar um bem do inventário

**Quem pode:** qualquer servidor vê a própria carga; os perfis do Patrimônio veem todo o campus.
**Quando usar:** para localizar um bem pelo tombo, conferir os dados e atualizar a descrição, a sala ou o estado de conservação.

1. No menu, acesse **Administração › Patrimônio › Inventários**. Filtre por **Número**, descrição ou campus e clique em **Filtrar**.

   ![Busca de inventários](usuario/inventario-busca.webp)

2. Clique no número do tombo para abrir a ficha do bem, com a situação, a carga atual, a sala e o valor.

   ![Ficha do inventário](usuario/inventario-ficha.webp)

3. Clique em **Editar** para corrigir a **Descrição**, a **Sala**, o **Estado de conservação**, os rótulos, o número de série ou a categoria de despesa; salve.

   ![Editar inventário](usuario/inventario-editar.webp)

   **Resultado:** *"Inventário salvo com sucesso."* — e a alteração fica registrada no histórico do bem.

4. O **Histórico de Movimentações** (na própria ficha) mostra as pendências, transferências e baixas do bem, com data, origem e destino.

   ![Histórico de movimentações](usuario/inventario-historico.webp)

---

### 2. Dar carga nos bens pendentes

**Quem pode:** Coordenadores de Patrimônio (do campus e sistêmico) e Operador de Patrimônio.
**Quando usar:** após a entrada de material permanente, quando os tombamentos estão sem responsável e é preciso entregá-los a um servidor.

1. No menu, acesse **Administração › Patrimônio › Movimentação › Carga**. Os bens **sem carga** do campus aparecem na tabela; os filtros do topo restringem por descrição, número ou campus.

   ![Inventários pendentes](usuario/carga-pendentes.webp)

2. Marque os bens que serão entregues e preencha o **Destino da Carga** (o servidor responsável), o **Estado de Conservação** e a **Sala** onde ficarão; os rótulos e a descrição são opcionais.

   ![Requisição de carga](usuario/carga-formulario.webp)

3. Clique em **Criar requisição de carga para os inventários selecionados**.

   **Resultado:** *"Requisição criada com sucesso."* A requisição fica aguardando a aprovação do servidor escolhido (tarefa 4) — a carga só passa a constar na ficha do bem depois do deferimento.

---

### 3. Requisitar a transferência de um bem

**Quem pode:** o servidor responsável pela carga (uma requisição por vez dos próprios bens) e os perfis do Patrimônio, que podem requisitar a carga de qualquer servidor do campus.
**Quando usar:** quando o bem vai passar para a responsabilidade de outro servidor.

1. No menu, acesse **Administração › Patrimônio › Requisições de Transferência** e clique em **Adicionar Nova Requisição**.

2. O **Servidor de Origem da Carga** já vem preenchido com você. Informe o **Servidor de Destino da Carga** e uma **Descrição**.

3. Em **Tipo de Seleção de Itens**, escolha **Inventários** e informe quais bens serão transferidos (uma requisição pode levar vários). Há outras seleções prontas: **Toda a carga do servidor de origem**, **Rótulos** ou **Salas**.

   ![Requisitar transferência](usuario/transferencia-formulario.webp)

4. Clique em **Enviar**.

   **Resultado:** *"Requisição de transferência de patrimônio efetuada com sucesso."* O pedido fica aguardando a aprovação do servidor de destino (tarefa 4).

---

### 4. Aprovar e deferir uma requisição de movimentação

**Quem pode:** o servidor de destino (é ele que aprova os itens e defere) — vale para a transferência e para a carga.
**Quando usar:** quando chega uma requisição de transferência ou de carga para você aceitar ou recusar.

1. Abra a requisição e marque, na tabela **Selecionar inventários**, cada bem que aceita; os itens não marcados saem como **Rejeitado**.

   ![Requisição de transferência](usuario/requisicao-detalhe.webp)

2. Clique em **Aprovar apenas selecionados**.

   **Resultado:** *"Inventários avaliados com sucesso..."* — e o aviso lembra que ainda falta deferir ou indeferir a requisição.

3. Clique em **Deferir** e informe a **Sala** de destino (deixe em branco para manter o bem na sala de origem).

   ![Deferir requisição](usuario/requisicao-deferir.webp)

4. Clique em **Salvar**.

   **Resultado:** a requisição fica **Deferida**, o bem passa para a carga do destino e o **Termo de Transferência** fica disponível na requisição para impressão.

   ![Requisição deferida](usuario/requisicao-deferida.webp)

---

### 5. Efetuar a baixa de um bem

**Quem pode:** Coordenadores de Patrimônio (do campus e sistêmico) e Operador de Patrimônio.
**Quando usar:** quando um bem sai do patrimônio — doação, descarte, sinistro —, sempre com a portaria ou o processo que autoriza.

1. No menu, acesse **Administração › Patrimônio › Baixas** e clique em **Adicionar Baixa**. Informe o **Tipo**, a **Data**, o **Nº da Portaria**, o **Campus** e a **Observação**; salve.

   ![Adicionar baixa](usuario/baixa-formulario.webp)

   **Resultado:** *"Baixa adicionada com sucesso."* — e você é levado à tela da baixa.

2. Na tela da baixa, clique em **Baixar Novo Inventário**, marque **Inventário** e informe o bem; clique em **Enviar**.

   ![Baixar novo inventário](usuario/baixa-tela.webp)

   **Resultado:** *"Baixa efetuada com sucesso."* O bem vai para a lista **Itens Baixados** e sai do inventário ativo.

3. O botão **Gerar PDF** emite o relatório da baixa.

---

### 6. Emitir uma cautela

**Quem pode:** Coordenadores de Patrimônio (do campus e sistêmico) e Operador de Patrimônio.
**Quando usar:** para entregar bens sob responsabilidade de alguém por um período determinado, com termo assinado.

1. No menu, acesse **Administração › Patrimônio › Cautelas** e clique em **Adicionar Cautela**. Informe o **Responsável**, a **Data de Início** e a **Data Final** (a início não pode ser maior que a final) e, se quiser, a descrição; salve.

   ![Adicionar cautela](usuario/cautela-formulario.webp)

   **Resultado:** *"Cautela adicionada com sucesso"* — e você é levado à tela da cautela.

2. Na tela da cautela, clique em **Adicionar Novo Item** e informe o **Inventário**; clique em **Salvar**.

   ![Itens sob cautela](usuario/cautela-detalhe.webp)

   **Resultado:** *"Item da Cautela cadastrado com sucesso."* Bens em cautela em andamento não podem entrar em outra cautela no mesmo período. O botão **Gerar PDF** emite o termo.

---

### 7. Conferir uma sala

**Quem pode:** Coordenadores de Patrimônio (do campus e sistêmico) e Operador de Patrimônio.
**Quando usar:** para conferir, bem a bem, o que está lotado numa sala — a leitura é feita pelo aplicativo de coletor, lendo o QRCode.

1. No menu, acesse **Administração › Patrimônio › Conferências de Salas** e clique em **Adicionar Conferência de Sala**. Escolha a **Sala** e o **Responsável** (a lista traz apenas o campus do usuário logado) e salve.

   ![Adicionar conferência](usuario/conferencia-formulario.webp)

   **Resultado:** a conferência é criada e aparece na lista de conferências, pronta para o coletor.

2. Na tela da conferência, a aba **Inventários Lotados na Sala e Não Coletados** lista o que o coletor ainda não leu, com a carga atual e a última requisição de cada bem.

   ![Conferência de sala](usuario/conferencia-sala.webp)

3. O **Autorizar Coletor** (na listagem de conferências) abre o **QRCode** que o aplicativo do coletor lê para começar a conferência.

   ![QRCode do coletor](usuario/conferencia-coletor.webp)

   **Resultado:** conforme os bens são lidos, saem da lista de não coletados e o total conferido sobe no contador da conferência.

---

### 8. Reavaliar e ajustar o valor de um bem

**Quem pode:** Coordenadores de Patrimônio (do campus e sistêmico).
**Quando usar:** quando o valor contábil do bem muda: para mais (reavaliação) ou para menos (ajuste do valor recuperável).

Essas duas telas são abertas pelo endereço do bem, com o número do inventário no fim do endereço — não têm item de menu.

1. Abra a tela de reavaliação, informe o **Valor Reavaliado** e o **Motivo**; clique em **Enviar**.

   ![Reavaliar inventário](usuario/reavaliar-formulario.webp)

   **Resultado:** *"Inventário reavaliado com sucesso."* O valor do bem sobe pelo valor informado.

2. Na tela de ajuste, informe o **Valor do Ajuste** e o **Motivo**; clique em **Enviar**.

   ![Ajustar valor recuperável](usuario/ajustar-valor-formulario.webp)

   **Resultado:** *"Ajuste do valor recuperável realizado com sucesso."* O valor do bem cai pelo valor informado. As duas operações ficam registradas no histórico do bem.

---

### 9. Consultar os relatórios

**Quem pode:** os perfis do Patrimônio — operadores e coordenadores veem o campus; Coordenador Sistêmico e Auditor veem a instituição.

- **Depreciação de Inventários** — a depreciação de um item num mês/ano, ou por plano contábil.
- **Servidores com Carga** — quem responde por bens no campus, com o **Termo de Responsabilidade** de cada servidor.

  ![Servidores com carga](usuario/relatorio-servidores-carga.webp)

- **Termos** — emite o termo de responsabilidade de um servidor.

  ![Termos](usuario/relatorio-termos.webp)

- **Inventários não Conferidos** — o que ainda não foi conferido no período, por campus.

  ![Inventários não conferidos](usuario/relatorio-nao-conferidos.webp)

- **Totalizações**, **Totalização por Campus** e **Plano de Contas** — os totais por elemento de despesa, campus e período.

No **Relatório de Depreciação por Itens**, escolha o **Mês**, o **Ano** e o bem; só há resultado se a depreciação daquele período já tiver sido processada.

![Depreciação por itens](usuario/relatorio-depreciacao.webp)

![Totalização por elemento de despesa](usuario/relatorio-totalizacao-ed.webp)

---

## Telas de apoio

Tabelas e procedimentos que o módulo usa sem passo a passo próprio:

- **Elementos de Despesa de Mat. Permanente** e **Plano de Contas** — o catálogo contábil dos bens (vida útil, percentual residual).
- **Rótulos** — agrupamentos de bens para carga, transferência e baixa em conjunto.
- **Migração de Inventários** — importação do acervo por planilha, procedimento de implantação (uma vez por instituição).
- **Requisições de Equipamentos** — lista as requisições de uso pessoal feitas pelo servidor.
- **Movimentação › Doação** e **Entradas** — são as telas de entrada de material permanente, documentadas no guia do Almoxarifado.
- **Carga Contábil** e **Alterações do Período de Execução** — telas de conferência contábil do inventário.
