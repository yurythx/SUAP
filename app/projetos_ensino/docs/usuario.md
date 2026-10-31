# Projetos de Ensino

Gerencia os projetos de ensino da instituição de ponta a ponta — do lançamento do edital que abre as inscrições até a conclusão e a validação final do projeto. É por aqui que uma proposta vira um edital publicado, ganha uma comissão de avaliadores, é avaliada e, se aprovada, é executada com recursos acompanhados, fotos e beneficiários registrados até o encerramento.

O ciclo completo, no SUAP:

1. O edital é cadastrado e configurado (abrangência, recursos, critérios, comissão de avaliação).
2. O coordenador do projeto monta e submete a proposta.
3. O projeto passa pela pré-seleção, tem avaliadores indicados e é avaliado.
4. Aprovado, o projeto vai à execução: atividades, beneficiários atendidos, gastos e fotos são registrados.
5. O monitor valida execução e gastos, a conclusão é registrada, o projeto é finalizado e a conclusão é validada.

**Quem usa este módulo**

| Perfil | O que faz aqui |
| --- | --- |
| Gerente Sistêmico de Projetos de Ensino | Cadastra e configura o edital, forma a comissão de avaliação e indica os avaliadores dos projetos |
| Coordenador de Projetos de Ensino | Pré-seleciona os projetos enviados e monitora (valida) a execução e a conclusão |
| Servidor (coordenador do projeto) | Cadastra o projeto, monta a equipe, submete a proposta, registra a execução e conclui |
| Avaliador de Projetos de Ensino | Avalia os projetos para os quais foi indicado |

---

## Antes de começar

O cadastro de um edital consome tabelas de apoio que precisam existir: **Eixos Temáticos**, **Tipos de beneficiário**, **Origens de Recurso do Edital** e a **nomenclatura de despesas** (naturezas, elementos e modalidades). Numa instituição já em operação elas estão preenchidas. Os campos de **Origem** e **Despesa** do formulário de recurso e o campo **Eixo Temático** do projeto dependem dessas tabelas — se alguma lista aparecer vazia, é uma delas que falta. A nomenclatura de despesas fica nos cadastros transversais do módulo de gestão financeira da instituição; as demais tabelas ficam em **Ensino › Projetos › Cadastros**.

O formulário de datas do edital (inscrições, pré-seleção, seleção, divulgação) define as janelas de cada fase do ciclo — um passo não começa antes do anterior.

---

## Tarefas

### 1. Cadastrar e configurar um edital de projetos de ensino

**Quem pode:** Gerente Sistêmico de Projetos de Ensino e Coordenador de Projetos de Ensino (o Coordenador gerencia os editais do próprio campus e os campi adicionais a ele vinculados).
**Quando usar:** ao abrir uma seleção de projetos de ensino, delimitando período, recursos, critérios e avaliadores.

O edital é cadastrado no grupo **Ensino › Projetos › Editais**. Depois de salvo, a página do edital reúne as abas em que ele é configurado (oferta por campus, fontes de recurso, critérios e comissão de avaliação).

**Etapa 1 — cadastrar o edital**

1. No menu, acesse **Ensino › Projetos › Editais › Gerenciar editais** e clique em **Adicionar Edital**.

   ![Listagem de editais](usuario/edital-listagem.webp)

2. Preencha o formulário, dividido em blocos (*Dados gerais*, *Calendário*, *Configurações do Edital*, *Termos de Compromisso*). Os campos que costumam gerar dúvida:

   | Campo | O que informar |
   | --- | --- |
   | Tipo do Edital | **Ensino** para uma seleção pontual; **Ensino Contínuo** para fluxo contínuo |
   | Forma de Seleção | **Campus** quando cada campus seleciona seus próprios projetos; **Geral** para a seleção acontecer de forma centralizada |
   | Edital de Campus | Marque para que os projetos deste edital sejam avaliados por servidores do mesmo campus do projeto |
   | Início / Fim das Inscrições | A janela em que os coordenadores podem submeter projetos |
   | Início da Pré-Seleção | Quando começa a fase de pré-seleção — a seleção só avança depois dela |
   | Início / Fim da Seleção | A janela das avaliações |
   | Divulgação da Seleção | Quando o resultado pode ser divulgado — é o que libera os projetos para execução |
   | Participação de Aluno / Servidor Obrigatória | Exige que todo projeto tenha ao menos um aluno e/ou um servidor na equipe |
   | Valor Financiado por Projeto | O teto que cada projeto aprovado poderá gastar, e a base para a memória de cálculo |

   ![Formulário de cadastro do edital](usuario/edital-formulario.webp)

3. Clique em **Salvar**.

**Resultado:** aparece *"Edital cadastrado com sucesso."* e você é levado à página do edital, que reúne as abas de configuração.

![Página do edital](usuario/edital-pagina.webp)

**Etapa 2 — definir o plano de oferta por campus**

O plano de oferta delimita quais campi participam e quantos projetos cada um pode pré-selecionar e selecionar. Só servidores dos campi incluídos aqui poderão submeter projetos.

4. Na página do edital, abra a aba **Plano de Oferta por Campus** e clique em **Adicionar Oferta**.
5. Informe o **Campus**, quantos projetos poderão ser **Pré-Selecionados** e quantos serão **Selecionados**, e clique em **Salvar**.

   ![Plano de oferta por campus](usuario/edital-oferta-popup.webp)

**Resultado:** *"Oferta adicionada com sucesso."* e o campus passa a constar no plano de oferta.

**Etapa 3 — cadastrar as fontes de recurso**

6. Abra a aba **Fonte de Recursos** e clique em **Adicionar Recurso**.
7. Informe a **Origem** do recurso, o **Valor disponível por projeto (R$)** e a **Despesa** (a rubrica), e clique em **Salvar**.

   ![Fonte de recurso do edital](usuario/edital-recurso-popup.webp)

**Resultado:** *"Recurso adicionado com sucesso."* O valor informado é o máximo que cada projeto aprovado poderá gastar naquela despesa — é a base para o coordenador do projeto definir a memória de cálculo e o plano de desembolso.

**Etapa 4 — definir os critérios de avaliação**

8. Abra a aba **Critérios de Avaliação da Qualificação do Projeto** e clique em **Adicionar Critério de Avaliação**.
9. Informe a **Descrição**, a **Pontuação Máxima** e a **Ordem para Desempate**, e clique em **Salvar**.

   ![Critério de avaliação](usuario/edital-criterio-popup.webp)

**Resultado:** *"Critério de avaliação adicionado com sucesso."* Os critérios são a ficha que os avaliadores usam na tarefa 5.

**Etapa 5 — formar a comissão de avaliação**

A comissão reúne todos os possíveis avaliadores dos projetos submetidos. É dela que a fase de **Indicação de Avaliadores** (tarefa 4) tira os avaliadores de cada projeto.

10. No menu, acesse **Ensino › Projetos › Editais › Comissão de Avaliação** e clique em **Adicionar Comissão de Avaliação**.
11. Em **Filtrar por Edital**, escolha o edital, informe os **Membros** (servidores e/ou avaliadores externos) e clique em **Salvar**.

    ![Formulário de comissão de avaliação](usuario/comissao-formulario.webp)

**Resultado:** *"Cadastro realizado com sucesso."* A comissão passa a constar na listagem.

![Comissões de avaliação cadastradas](usuario/comissao-listagem.webp)

**Saiba também:** para incluir mais um avaliador na comissão depois, use o ícone de edição da linha na listagem — os membros da comissão formada continuam valendo para a indicação (tarefa 4).

---

### 2. Submeter um projeto de ensino

**Quem pode:** Servidor (coordenador do projeto) e Aluno de graduação — quando o edital habilita a submissão por aluno.
**Quando usar:** assim que um edital está com inscrições abertas e o seu campus está no plano de oferta.
**Pré-condição:** o edital está publicado com inscrições abertas (tarefa 1).

O projeto nasce como **rascunho** (situação *Em edição*) e só é submetido na última etapa, quando todas as informações obrigatórias estiverem preenchidas.

**Etapa 1 — cadastrar o projeto**

1. No menu, acesse **Ensino › Projetos › Adicionar projeto** e, no cartão do edital com inscrições abertas, clique em **Adicionar projeto**.

   ![Editais com inscrições abertas](usuario/projeto-editais-abertos.webp)

2. Preencha o formulário, dividido em blocos (*Dados gerais*, *Dados do Projeto*, *Descrição do Projeto*). Os campos que geram dúvida:

   | Campo | O que informar |
   | --- | --- |
   | Campus / Setor | O campus e o setor do plano de oferta onde o projeto será executado |
   | Eixo Temático | O eixo a que o projeto se vincula |
   | Há parceiros externos? | Marque se houver instituições parceiras e descreva-as no campo **Parceiros Externos** |
   | Carga Horária Semanal do Coordenador | A dedicação semanal, em horas |
   | Carga horária total para desenvolvimento do projeto | O total de horas do projeto |

   Os campos de texto do bloco *Descrição do Projeto* (Resumo, Introdução, Justificativa, Objetivo Geral, Metodologia, Acompanhamento, Resultados, Referências) são editores de texto — use-os com liberdade.

   ![Formulário de cadastro do projeto](usuario/projeto-formulario.webp)

3. Clique em **Salvar**.

**Resultado:** *"Projeto cadastrado com sucesso."* e você é levado à página do projeto, ainda com situação **Em edição**, pronta para receber equipe, metas e planejamento.

![Página do projeto recém-criado](usuario/projeto-pagina.webp)

**Etapa 2 — montar a equipe**

4. Abra a aba **Equipe** e, para cada servidor, clique em **Adicionar Servidor**; para cada aluno, em **Adicionar Aluno**.
5. No popup, informe **Bolsista** (Sim/Não), **Carga Horária**, o **Participante** (busque pelo nome) e a **Data de Entrada**, e clique em **Salvar**.

   ![Inclusão de servidor na equipe](usuario/projeto-equipe-servidor.webp)

**Resultado:** *"Participante adicionado com sucesso."* O membro passa a constar na equipe do projeto.

**Etapa 3 — caracterizar os beneficiários**

6. Abra a aba **Caracterização dos Beneficiários** e clique em **Adicionar Caracterização dos Beneficiários**.
7. Informe o **Tipo de beneficiário** e a **Quantidade Prevista de Pessoas a Atender**, e clique em **Salvar**.

   ![Caracterização dos beneficiários do projeto](usuario/projeto-beneficiarios.webp)

**Resultado:** *"Caracterização do beneficiário adicionada com sucesso."* É essa previsão que, na execução (tarefa 6), será confrontada com a quantidade efetivamente atendida.

**Etapa 4 — cadastrar metas e atividades**

8. Abra a aba **Metas/Atividades** e, para cada meta, clique em **Adicionar Meta**.
9. Informe a **Ordem** e a **Descrição** da meta e clique em **Salvar**. Depois, para cada atividade dentro da meta, clique em **Adicionar Atividade** e informe **Ordem**, **Descrição**, o **Indicador Quantitativo** (unidade de medida) com sua **Quantidade**, os **Indicador(es) Qualitativo(s)**, o **Responsável** e o período (**Início** e **Fim da Execução**).

   ![Cadastro de atividade da meta](usuario/projeto-atividade.webp)

**Resultado:** *"Meta adicionada com sucesso."* e *"Atividade adicionada com sucesso."* — cada atividade é a unidade que terá a execução registrada e validada nas tarefas 6 e 7.

**Etapa 5 — planejar o orçamento (memória de cálculo e desembolso)**

10. Abra a aba **Plano de Aplicação** — nela está o *Demonstrativo do Plano de Aplicação/Memória de Cálculo e Desembolso*, que resume, por fonte e rubrica, o valor reservado, o planejado, o distribuído e o disponível.

    ![Plano de Aplicação vazio](usuario/projeto-plano-vazio.webp)

    Clique em **Adicionar Memória de Cálculo** e informe o **Recurso** (a fonte e a rubrica do edital), a **Descrição**, a **Unidade de Medida**, a **Quantidade** e o **Valor Unitário (R$)**. Clique em **Salvar**.

    ![Memória de cálculo do projeto](usuario/projeto-memoria-calculo.webp)

11. Abra a aba **Plano de Desembolso**, clique em **Adicionar Item** e informe a **Mémoria de Cálculo**, o **Ano**, o **Mês**, o **Valor (R$)** e, se quiser repetir, até que mês em **Repetir Desembolso até o mês**. Clique em **Salvar**.

    ![Plano de desembolso do projeto](usuario/projeto-desembolso.webp)

**Resultado:** *"Item adicionado com sucesso."* e *"Desembolso adicionado com sucesso."* O desembolso diz quando o recurso da memória de cálculo será executado (ex.: R$ 10.000,00 de bolsas distribuídos em 10 parcelas mensais). O **Plano de Desembolso** deve cobrir cada memória de cálculo antes do envio.

**Etapa 6 — enviar o projeto**

12. De volta à página do projeto, clique em **Enviar Projeto**.

![Projeto enviado](usuario/projeto-enviado.webp)

**Resultado:** *"Projeto enviado com sucesso."* e a situação do projeto passa de *Em edição* a **Enviado**, liberando-o para a pré-seleção (tarefa 3). Se faltar informação obrigatória (uma meta sem atividade, um desembolso pendente), o SUAP aponta qual cadastrar antes de concluir o envio.

---

### 3. Pré-selecionar os projetos enviados

**Quem pode:** Coordenador de Projetos de Ensino (pré-seleciona os projetos do próprio campus) e Gerente Sistêmico de Projetos de Ensino.
**Quando usar:** no período de pré-seleção, para verificar se cada projeto enviado está de acordo com o edital e tem as informações obrigatórias.
**Pré-condição:** o projeto foi enviado (tarefa 2) e o edital está no período de pré-seleção.

1. No menu, acesse **Ensino › Projetos › Pré-avaliar** e, na listagem de editais, clique no ícone de exibição do edital.

   ![Editais em pré-seleção](usuario/preselecao-editais.webp)

2. Na tela **Pré-Seleção de Projetos**, localize o projeto enviado e clique em **Pré-selecionar**.

   ![Pré-seleção de projetos](usuario/preselecao-projetos.webp)

**Resultado:** *"Projeto pré-avaliado com sucesso."* O projeto é marcado como **Pré-selecionado** e o coordenador de projetos que fez a pré-seleção passa a ser o **monitor** por padrão (pode ser alterado em **Ensino › Projetos › Gerenciar Monitores**). A partir daqui o projeto pode receber avaliadores (tarefa 4).

---

### 4. Indicar os avaliadores de um projeto

**Quem pode:** Gerente Sistêmico de Projetos de Ensino e Coordenador de Projetos de Ensino.
**Quando usar:** na fase de seleção, para dizer, entre os membros da comissão de avaliação (tarefa 1), quem avalia cada projeto pré-selecionado (tarefa 3).
**Pré-condição:** o projeto foi pré-selecionado e a comissão de avaliação do edital foi formada.

1. No menu, acesse **Ensino › Projetos › Indicar Avaliador** e, na listagem de editais em avaliação, clique no ícone de exibição do edital.

   ![Editais com projetos a avaliar](usuario/indicar-avaliador-editais.webp)

2. Na tela **Selecionar avaliadores dos Projetos**, localize o projeto pré-selecionado e clique em **Selecionar avaliadores**.

   ![Projetos pré-selecionados aguardando avaliadores](usuario/indicar-avaliador-projetos.webp)

3. No popup, marque os **Avaliadores** e clique em **Enviar**.

   ![Indicação dos avaliadores do projeto](usuario/indicar-avaliador-popup.webp)

**Resultado:** *"Avaliadores cadastrados com sucesso."* Os indicados recebem o acesso à tarefa 5 e passam a constar na coluna **Avaliadores** do projeto, identificando quem já avaliou e quem ainda não.

---

### 5. Avaliar um projeto

**Quem pode:** Avaliador de Projetos de Ensino — mas apenas os projetos para os quais foi indicado (tarefa 4), e durante o período de seleção.
**Pré-condição:** o projeto foi indicado ao avaliador e o edital está no período de seleção.

1. No menu, acesse **Ensino › Projetos › Avaliar** e, na listagem de editais em avaliação, localize o edital e clique no campus (**CZN** na listagem).

   ![Editais em avaliação](usuario/avaliacao-editais.webp)

2. Na tela **Seleção de Projetos**, localize o projeto a avaliar e clique em **Avaliar**.

   ![Projetos a avaliar](usuario/avaliacao-projetos.webp)

3. Preencha o formulário de avaliação: para cada **critério** da ficha, escolha a **pontuação**; preencha o **Parecer** e clique em **Enviar**.

   ![Formulário de avaliação do projeto](usuario/avaliacao-formulario.webp)

**Resultado:** *"Projeto avaliado com sucesso."* A média das avaliações compõe a pontuação do projeto. Em uma seleção por campus, os avaliados de cada avaliador somam até o projeto atingir a nota de corte definida pelos critérios.

---

### 6. Registrar a execução do projeto

**Quem pode:** o coordenador do projeto (Servidor).
**Quando usar:** a partir do período de execução, para prestar contas do que o projeto efetivamente realizou: beneficiários atendidos, atividades executadas, gastos e fotos.
**Pré-condição:** o projeto foi selecionado (passou pelas avaliações da tarefa 5) — situação **Em execução**.

![Página do projeto em execução](usuario/execucao-pagina.webp)

**Registrar a quantidade atendida de beneficiários**

1. Abra a aba **Caracterização dos Beneficiários** e, na linha do público-alvo previsto (tarefa 2), clique em **Registrar**.

   ![Caracterização dos beneficiários com os atendidos](usuario/execucao-beneficiarios.webp)

2. Informe a **Quantidade Atendida** e a descrição dos **Beneficiários do Público-Alvo**, e clique em **Salvar**.

   ![Registro dos beneficiários atendidos](usuario/execucao-beneficiario-atendido.webp)

**Resultado:** *"Caracterização registrada com sucesso."* É o que habilita a finalização (tarefa 9).

**Registrar a execução de uma atividade**

3. Abra a aba **Metas/Atividades** e, na linha da atividade, clique em **Registrar Execução**.
4. Informe o resultado qualitativo (**Indicadores Qualitativos**), a **Quantidade** executada, o período real (**Início** e **Fim da Execução**), a **Descrição da Atividade Realizada** e o **Arquivo** comprobatório, e clique em **Salvar**.

   ![Registro da execução de atividade](usuario/execucao-atividade.webp)

**Resultado:** *"Execução registrada com sucesso."* A atividade fica **aguardando validação** do monitor (tarefa 7).

**Registrar os gastos do desembolso**

5. Abra a aba **Plano de Desembolso** e, na linha do desembolso planejado (tarefa 2), clique em **Gerenciar Gasto**.
6. Na tela **Gastos Registrados**, informe **Ano**, **Mês**, a **Descrição**, a **Quantidade**, o **Valor Unitário (R$)**, a **Observação** e, se houver, anexe a **Nota Fiscal ou Cupom** e a **Cotação de Preços**, e clique em **Salvar**.

   ![Registro de gasto](usuario/execucao-gasto.webp)

**Resultado:** *"Gasto registrado com sucesso."* Caso o gasto não tenha ocorrido, registre-o com valor **R$ 0,00** e descreva na **Observação** o motivo. O gasto fica **aguardando validação** do monitor (tarefa 7).

**Registrar fotos do projeto**

7. Abra a aba **Fotos** e clique em **Adicionar Foto**.
8. Informe a **Legenda**, anexe a **Imagem** e clique em **Salvar**.

   ![Cadastro de foto do projeto](usuario/execucao-foto.webp)

**Resultado:** *"Foto adicionada com sucesso."* As fotos ilustram as atividades executadas e são um dos requisitos para a finalização (tarefa 9).

---

### 7. Validar as atividades e os gastos (monitoramento)

**Quem pode:** o monitor do projeto — por padrão o coordenador de projetos de ensino que fez a pré-seleção (tarefa 3), podendo ser alterado em **Ensino › Projetos › Gerenciar Monitores**.
**Quando usar:** a cada atividade executada e a cada gasto registrado pelo coordenador (tarefa 6).
**Pré-condição:** o projeto está em execução e há registros pendentes de validação.

1. No menu, acesse **Ensino › Projetos › Monitoramento**.

   ![Projetos em execução a monitorar](usuario/monitoramento-listagem.webp)

2. Na linha do projeto, clique em **Acompanhar Validação**.

   ![Tela de validação da execução](usuario/monitoramento-validacao.webp)

3. Na aba **Metas**, na linha da atividade executada, clique em **Aprovar**.

**Resultado:** *"Execução de atividade validada com sucesso."* Se algo estiver errado, em vez de **Aprovar** use **Não Aprovar** para devolver a atividade com justificativa.

4. Abra a aba **Gastos** e, na linha do gasto registrado, clique em **Aprovar**.

   ![Validação dos gastos](usuario/monitoramento-gastos.webp)

**Resultado:** *"Gasto validado com sucesso."* Atividades e gastos aprovados são o que destrava a conclusão (tarefa 8) e a finalização (tarefa 9).

---

### 8. Registrar a conclusão do projeto

**Quem pode:** o coordenador do projeto (Servidor).
**Quando usar:** após a execução ser integralmente registrada (tarefa 6) e validada (tarefa 7).
**Pré-condição:** o projeto está em execução, sem pendências de atividades, gastos, anexos, fotos ou beneficiários.

1. Abra a página do projeto, vá à aba **Conclusão** e clique em **Registrar Conclusão**.

   ![Aba Conclusão do projeto](usuario/conclusao-tab.webp)

2. Preencha os **Resultados Alcançados**, a **Disseminação dos Resultados** e, se necessário, uma **Observação**, e clique em **Salvar**.

   ![Formulário de conclusão do projeto](usuario/conclusao-formulario.webp)

**Resultado:** *"Conclusão do projeto registrada com sucesso."* O registro de conclusão é criado e passa a aguardar o parecer do monitor (tarefa 10).

---

### 9. Finalizar o projeto

**Quem pode:** o coordenador do projeto (Servidor).
**Quando usar:** quando a conclusão foi registrada (tarefa 8) e não restam pendências.
**Pré-condição:** todas as execuções e gastos foram aprovados (tarefa 7) e a conclusão foi registrada (tarefa 8).

1. Vá à aba **Conclusão** do projeto e clique em **Finalizar Projeto**.

**Resultado:** *"Conclusão finalizada com sucesso."* O projeto passa da situação **Em execução** a **Concluído** (após a validação final da tarefa 10), e os membros da equipe são avisados por e-mail.

![Projeto finalizado](usuario/finalizacao-pagina.webp)

**Saiba também:** o botão **Finalizar Projeto** só aparece quando não há pendências. Se algo faltar (beneficiários não registrados, fotos, atividade ou gasto sem validação), o SUAP aponta na aba **Pendências** o que ainda é necessário.

---

### 10. Validar a conclusão do projeto

**Quem pode:** o monitor do projeto (Servidor).
**Quando usar:** após o coordenador registrar a conclusão (tarefa 8) e o projeto ser finalizado (tarefa 9), para emitir o parecer final.

1. No menu, acesse **Ensino › Projetos › Monitoramento** e, na linha do projeto, clique em **Acompanhar Validação**.

   ![Projetos a validar a conclusão](usuario/validar-conclusao-listagem.webp)

2. Abra a aba **Conclusão do Projeto** e clique em **Emitir Parecer**.

   ![Aba de validação da conclusão](usuario/validar-conclusao-tab.webp)

3. No popup, marque **Aprovado** (ou deixe-o desmarcado para descumprir), registre a **Observação** e clique em **Enviar**.

   ![Parecer final da conclusão](usuario/validar-conclusao-formulario.webp)

**Resultado:** *"Conclusão do projeto registrada com sucesso."* O projeto ganha a situação **Concluído**, encerrando o ciclo.

---

## Telas de apoio

Tabelas consultadas pelos formulários deste módulo. Todas seguem o mesmo padrão do SUAP — listar, adicionar, editar, remover — e não têm passo a passo próprio.

Em **Ensino › Projetos › Cadastros**: **Colaborador Externo** (pessoas de fora da instituição que participam de projetos), **Critérios de Avaliação do Aluno**, **Eixo Temático**, **Origem do Recurso do Edital** e **Tipo de beneficiário**.

Em **Ensino › Projetos › Editais**: **Comissão de Acompanhamento** (a comissão que acompanha a execução), **Editais** (a listagem e o cadastro do edital — tarefa 1) e **Resultado Final/Parcial**.

Em **Ensino › Projetos › Relatórios**: **Caracterização de Beneficiários**, **Estatísticas**, **Lista de Avaliadores de Projetos**, **Lista de Emails dos Avaliadores**, **Lista de Emails dos Coordenadores**, **Lista de Equipes dos Projetos**, **Lista de Projetos em Atraso** e **Relatórios de Lições Aprendidas**.

Fora do grupo **Cadastros**, o módulo ainda expõe **Cancelamentos**, **Declarações › Avaliador de Projetos**, **Gerenciar Monitores**, **Indicar Pré-Avaliador**, **Interposição de recursos** e **Projetos** (a listagem administrativa no painel).
