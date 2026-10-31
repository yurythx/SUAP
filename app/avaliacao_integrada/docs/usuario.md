# Avaliação Integrada

É por aqui que a instituição faz a **autoavaliação institucional**: a instituição monta um questionário, define quem deve respondê-lo — servidores, estudantes e também gente de fora, como pais, egressos e empresas prestadoras de serviço —, abre um prazo, acompanha quem já respondeu e lê o resultado em gráficos e medidas.

O questionário é montado em camadas: **eixos** agrupam **dimensões**, que agrupam **macroprocessos**, que reúnem os **indicadores** — as perguntas propriamente ditas. Uma **avaliação** é a aplicação desse questionário num período, para um público. Quem responde vê apenas as perguntas do seu perfil.

**Quem usa este módulo**

| Perfil | O que faz aqui |
| --- | --- |
| Administrador de Avaliação Institucional | Monta o questionário (eixos, dimensões, macroprocessos, indicadores), mantém as comissões CPA e cuida das tabelas de apoio |
| Aplicador de Avaliação Institucional | Cria a avaliação, identifica o público-alvo, acompanha o preenchimento e lê os relatórios |
| Visualizador de Avaliação Institucional | Só consulta: vê as avaliações e os relatórios, sem alterar nada |
| Quem foi identificado no público-alvo | Responde o questionário do seu perfil, dentro do prazo |
| Público externo | Responde pelo link público, sem ter conta no SUAP |

---

## Antes de começar

Todo o módulo fica em **Des. Institucional › Avaliação Integrada**, exceto as duas telas de áreas de vinculação, que ficam em **Gestão de Pessoas** (tarefa 1) — elas são deste módulo na prática: a permissão que as libera é a de Avaliação Integrada.

A ordem importa, e cada etapa é pré-requisito da seguinte:

1. **áreas de vinculação dos setores** (tarefa 1) — sem elas a avaliação se recusa a identificar o público-alvo;
2. **estrutura** — eixos, dimensões e macroprocessos (tarefa 2);
3. **indicadores** — as perguntas (tarefa 3);
4. **avaliação** — o prazo e o público (tarefa 4).

---

## Tarefas

### 1. Associar as áreas de vinculação aos setores

**Quem pode:** Administrador de Avaliação Institucional.
**Quando usar:** antes da primeira avaliação, e sempre que a instituição criar setores novos.

A **área de vinculação** diz a que campo de atuação um setor pertence (Ensino, Pesquisa, Extensão, Atividades Estudantis…). É por ela que o SUAP decide quais perguntas cada servidor técnico-administrativo recebe — e enquanto **um único** setor com servidor ativo estiver sem área, a tela da avaliação esconde os botões de identificar o público-alvo e mostra o aviso *"Existem N servidores de M setores sem áreas de vinculação associada"*.

1. No menu, acesse **Gestão de Pessoas › Cadastros › Associar Áreas de Vinculação aos Setores**.
2. **Passo 1 de 2** — informe uma **Palavra-chave** com parte da sigla dos setores que você quer alcançar e clique em **Continuar**. (A **Árvore de Setores**, ao lado, serve para conferir a hierarquia.)

   ![Passo 1: filtro por palavra-chave](usuario/areas-vinculacao-filtro.webp)

3. **Passo 2 de 2** — marque os **Setores** e as **Áreas de Vinculação** que valem para eles. Marque **Definir Recursivamente** para aplicar a mesma escolha a todos os setores abaixo na hierarquia — é o caminho usual para cobrir a instituição inteira de uma vez, começando pelo setor raiz. Clique em **Finalizar**.

   ![Passo 2: setores, áreas e a opção recursiva](usuario/areas-vinculacao-selecao.webp)

**Resultado:** aparece *"Áreas vinculadas com sucesso."*

Para conferir o que ficou valendo, use **Gestão de Pessoas › Relatórios › Áreas de Vinculação dos Setores**, que mostra a árvore inteira com as áreas de cada setor. É uma tela só de leitura.

![Áreas de vinculação por setor](usuario/areas-vinculacao-arvore.webp)

> **Atenção:** *Definir Recursivamente* **substitui** as áreas dos setores abaixo, em vez de acrescentar. Use com cuidado em setores que já tenham áreas diferentes das do pai.

---

### 2. Montar a estrutura da avaliação

**Quem pode:** Administrador de Avaliação Institucional.
**Quando usar:** ao criar um instrumento de avaliação novo, ou ao acrescentar um tema aos que já existem.

As perguntas não ficam soltas: cada indicador pertence a um macroprocesso, que pertence a uma dimensão, que pertence a um eixo. Essa árvore é o que organiza o questionário na tela de quem responde (os títulos numerados *1.*, *1.1.*, *1.1.1.*) e o agrupamento dos relatórios.

**Etapa 1 — o tipo de avaliação**

1. Acesse **Cadastros › Tipos de Avaliação**, clique em **Adicionar Tipo de Avaliação**, informe a **Descrição** (por exemplo, *Autoavaliação Institucional*) e clique em **Salvar**.

O tipo é o que liga a avaliação aos indicadores: cada indicador declara para quais tipos ele serve, e cada avaliação declara de que tipos ela é.

**Etapa 2 — o eixo**

2. Acesse **Cadastros › Eixos** e clique em **Adicionar Eixo**.

   ![Listagem de eixos](usuario/eixos-listagem.webp)

3. Informe a **Descrição** e, se quiser, o **Texto de Ajuda** — ele vira uma dica (ícone de informação) ao lado do título do eixo no questionário. A **Ordem** é uma lista com as posições disponíveis e define em que lugar este eixo entra na sequência; escolher uma posição já ocupada empurra os demais. Clique em **Salvar**.

   ![Formulário de eixo](usuario/eixo-formulario.webp)

**Etapa 3 — a dimensão**

4. Acesse **Cadastros › Dimensões**, clique em **Adicionar Dimensão**, escolha o **Eixo**, informe a **Descrição** e clique em **Salvar**.

   ![Formulário de dimensão](usuario/dimensao-formulario.webp)

**Etapa 4 — o macroprocesso**

5. Acesse **Cadastros › Macroprocessos**, clique em **Adicionar Macroprocesso**, escolha a **Dimensão**, informe a **Descrição** e clique em **Salvar**.

   ![Formulário de macroprocesso](usuario/macroprocesso-formulario.webp)

**Resultado:** a cada cadastro aparece *"Cadastro realizado com sucesso."*, e a árvore fica pronta para receber indicadores.

---

### 3. Cadastrar um indicador

**Quem pode:** Administrador de Avaliação Institucional.
**Quando usar:** para acrescentar uma pergunta ao questionário.

1. No menu, acesse **Des. Institucional › Avaliação Integrada › Indicadores** e clique em **Adicionar Indicador**.

   ![Listagem de indicadores](usuario/indicadores-listagem.webp)

2. Preencha o formulário — são **27 campos em 7 blocos**, mais o quadro **Iteradores** no fim da página, e a maioria já vem preenchida com o valor usual. Os que costumam gerar dúvida:

   | Campo | O que informar |
   | --- | --- |
   | Anos de Referência | Os anos em que esta pergunta vale; a avaliação só puxa indicadores do seu ano |
   | Macroprocesso | Onde a pergunta entra na árvore — define em que aba e sob que título ela aparece |
   | Denominação do Indicador | O nome interno, usado nas listagens de gestão |
   | Critério de Análise | **O texto que o respondente lê como pergunta.** É este, e não a denominação, que aparece no questionário e no relatório |
   | Subsídio p/ Avaliações | Os tipos de avaliação a que este indicador serve |
   | Segmentos | Um bloco por público (Servidores, Alunos, Sociedade Civil): quem **não** for de um segmento marcado não recebe a pergunta |
   | Áreas | Restringe a pergunta a servidores de setores daquelas áreas de vinculação; em branco, vale para todos |
   | Tipo | O formato da resposta: *Escala Likert* (o padrão), texto, número, escolha única ou múltipla, conjunto de variáveis |
   | Escala Likert | Obrigatória quando o tipo é *Escala Likert* — é a régua de opções que o respondente vê |
   | Autocalculado | Para os poucos indicadores que o SUAP preenche sozinho a partir do cadastro da pessoa (cargo, curso, ano de ingresso…). Só funciona com as denominações que o sistema reconhece — com qualquer outra, o formulário recusa salvar |
   | Em uso | Desmarque para aposentar a pergunta sem apagá-la: ela deixa de entrar nos questionários novos e os dados antigos continuam nos relatórios |

   ![Formulário de indicador](usuario/indicador-formulario.webp)

3. Clique em **Salvar**.

**Resultado:** *"Cadastro realizado com sucesso."* e o indicador passa a integrar o questionário de todas as avaliações que casem com o ano, o tipo e os segmentos escolhidos.

**Reaproveitar uma pergunta:** na listagem, cada indicador tem o botão **Replicar Indicador**, na coluna *Opções*. Ele cria uma cópia com o sufixo **[Replicado]** no nome, já com os mesmos segmentos, áreas, modalidades e opções de resposta, e abre a edição para você ajustar o que mudou (o ano de referência, em geral). É mais rápido que recadastrar, e evita esquecer um detalhe.

![Indicador replicado](usuario/indicador-replicado.webp)

---

### 4. Criar e aplicar uma avaliação

**Quem pode:** Administrador ou Aplicador de Avaliação Institucional.
**Quando usar:** para abrir um período de coleta de respostas.

**Etapa 1 — cadastrar a avaliação**

1. No menu, acesse **Des. Institucional › Avaliação Integrada › Avaliações** e clique em **Adicionar Avaliação**.

   ![Listagem de avaliações](usuario/avaliacoes-listagem.webp)

2. Preencha o formulário — **21 campos em 6 blocos**. Os que costumam gerar dúvida:

   | Campo | O que informar |
   | --- | --- |
   | Tipos | Quais tipos de avaliação esta aplicação cobre; é o que seleciona os indicadores |
   | Ano de Referência | Só entram indicadores que tenham este ano entre os seus anos de referência |
   | Data de Início / Data de Término | O prazo. Fora dele o questionário não abre — e é a data de término que aparece nos e-mails de lembrete |
   | Áreas de Vinculação | Quais áreas participam. **Deixar em branco impede o público interno de abrir o questionário**; marque ao menos uma |
   | Campi | Restringe a avaliação a alguns campi; em branco, vale para todos |
   | Segmentos | Um bloco por público (Servidores, Alunos, Sociedade Civil). Marcar um segmento de **Sociedade Civil** é o que faz a avaliação ganhar link público |
   | Texto com instruções | Um por público: é o cabeçalho que o respondente lê antes das perguntas. Aceita formatação |
   | Modalidades dos cursos participantes da pesquisa | Só para o segmento *Pais e/ou Responsável*: define de quais cursos vêm os alunos cujos responsáveis serão consultados |

   ![Formulário de avaliação](usuario/avaliacao-formulario.webp)

3. Clique em **Salvar**.

**Resultado:** *"Cadastro realizado com sucesso."* A avaliação passa a existir, ainda sem público-alvo.

**Etapa 2 — identificar o público-alvo**

4. Abra a avaliação (ícone de exibição na listagem). Em *Dados gerais* você encontra o **Link de Compartilhamento** — o endereço público, com botão **Copiar**, que só aparece quando há segmento de sociedade civil.
5. Na aba **Público-Alvo**, clique em **Reprocessar Público-Alvo** e confirme. O SUAP percorre servidores, estudantes e público externo aplicando os filtros da avaliação e monta um respondente para cada pessoa apta, com o questionário já ajustado ao perfil dela.

**Resultado:** a aba **Público-Alvo** passa a listar os respondentes — **Nome**, **Identificação**, **Campus**, **Segmento**, **% Respondido** e **Enviado** —, com o contador ao lado do nome da aba, o campo **Buscar** e os filtros **Segmento** e **Campus**. Cada linha traz **Visualizar questionário**, que abre o formulário exatamente como aquela pessoa o vê.

![Aba Público-Alvo, como o Aplicador a vê](usuario/avaliacao-publico-alvo.webp)

Repare que, para o **Aplicador**, as colunas *Nome* e *Identificação* mostram **Anônimo** e **---**: ver quem é quem depende de uma permissão que só o **Administrador** tem. Ele também é o único que enxerga o botão **Reprocessar Público-Alvo e Respostas** — a variante que **apaga todas as respostas já dadas** antes de refazer o público — e o **Enviar lembrete por e-mail**.

![A mesma aba, como o Administrador a vê](usuario/avaliacao-publico-alvo-administrador.webp)

> Os dois botões pedem confirmação, e a diferença está no aviso: o **Reprocessar Público-Alvo** apenas pergunta se você tem certeza; o **Reprocessar Público-Alvo e Respostas** avisa que *"Esta ação é IRREVERSÍVEL, ao confirmar, TODAS as avaliações já respondidas serão APAGADAS."*. Use o segundo só quando a avaliação tiver mudado de escopo a ponto de as respostas anteriores não valerem mais.

**Etapa 3 — cobrar quem ainda não respondeu**

6. Ainda na aba **Público-Alvo**, clique em **Enviar lembrete por e-mail**. O SUAP abre um diálogo com o **Assunto** e a **Mensagem (HTML)** já escritos, lembrando o prazo e explicando como retomar o preenchimento. Ajuste o texto se quiser, marque **Confirmo o envio para todos os respondentes elegíveis desta avaliação** e clique em **Enviar e-mail**.

   ![Formulário do lembrete por e-mail](usuario/avaliacao-lembrete.webp)

   Só recebem o lembrete quem **ainda não enviou** as respostas e tem e-mail válido cadastrado.

**Acompanhar o andamento:** a aba **Resumo** consolida os quatro números que interessam à gestão — **Finalizados**, **Respondido 100% mas não enviados**, **Parciais** e **Não Respondidos** — e traz **Exportar Resumo (XLSX)**. Os blocos carregam um a um, então a tela pode levar alguns segundos para ficar completa.

![Aba Resumo](usuario/avaliacao-quadro-resumo.webp)

---

### 5. Responder a avaliação

**Quem pode:** qualquer pessoa identificada no público-alvo — nenhum perfil especial é necessário. Cada pessoa só acessa o próprio questionário.
**Quando usar:** dentro do prazo da avaliação; fora dele o SUAP avisa que *"O prazo para resposta da Avaliação foi expirado."*

1. Na tela inicial do SUAP, o quadro **Fique atento!** traz o convite — *"Sua voz é importante! Responda à autoavaliação…"*, com o campus, o segmento e o prazo. Clique nele.

   ![Convite na tela inicial](usuario/inicio-chamada.webp)

2. A página abre com o seu **Perfil** (o segmento pelo qual você foi convidado), o texto de orientações da instituição e a barra **Percentual respondido**. As perguntas ficam em abas, uma por eixo, e dentro de cada aba aparecem numeradas por dimensão e macroprocesso.
3. Responda o que quiser. Nada é obrigatório de uma vez.

   ![Questionário](usuario/questionario.webp)

4. Clique em **Salvar e Continuar** quantas vezes precisar — dá para sair e voltar depois, até o prazo acabar.

**Resultado:** *"As suas respostas foram salvas."* e a barra de percentual sobe.

![Questionário com resposta salva](usuario/questionario-respondido.webp)

5. Quando o percentual chegar a **100%**, o aviso muda para *"Você completou 100% da avaliação. Para finalizar o processo e registrar suas respostas, lembre-se de clicar no botão **Enviar respostas**."* e o botão aparece ao lado de *Salvar e Continuar*. Clique nele. O SUAP pergunta *"Tem certeza que deseja enviar suas respostas? Você não poderá mais editar o questionário."* — confirme.

**Resultado:** *"Avaliação concluída com sucesso! Agradecemos a sua participação."*, e a página passa a exibir o agradecimento em destaque.

![Questionário enviado](usuario/questionario-finalizado.webp)

**Se você quiser recomeçar:** o botão **Cancelar avaliação**, no fim da página, avisa que *"Todas as suas respostas serão apagadas e você precisará recomeçar."* e devolve o questionário em branco.

---

### 6. Acompanhar os resultados

**Quem pode:** Administrador, Aplicador ou Visualizador de Avaliação Institucional.
**Quando usar:** durante a coleta, para ver como está indo, e depois dela, para analisar.

1. No menu, acesse **Des. Institucional › Avaliação Integrada › Relatórios**.
2. Escolha a **Avaliação** e, se quiser restringir, os **Tipos de Avaliação**. Clique em **Enviar**.

   ![Filtro do relatório](usuario/relatorio-filtro.webp)

3. A tela lista os indicadores **que já receberam ao menos uma resposta**, agrupados por eixo, dimensão e macroprocesso. Indicador sem nenhuma resposta não aparece.

   ![Indicadores com resposta](usuario/relatorio-indicadores.webp)

4. Clique em **Visualizar** na linha do indicador.

**Resultado:** o detalhamento do indicador, com:

- **Dados gerais** — *Universo* (quantas pessoas foram convidadas) e *Respondentes* (quantas responderam, e o percentual);
- **Filtros** — recorte por **Segmentos**, **Áreas**, **Campi**, **Modalidades** e **Cursos**, aplicados com **Filtrar**;
- **Distribuição de Frequência das Respostas** — a tabela valor × frequência × %;
- **Ranking de Frequência das Respostas** — os mesmos números em gráfico;
- **Medidas Resumo** — média, mediana, moda, desvio-padrão, variância e coeficiente de variação.

![Detalhamento do indicador](usuario/relatorio-indicador.webp)

**Levar as respostas para uma planilha:** o botão **Exportar respostas para Excel**, na tela de Relatórios, abre um formulário com filtros mais finos — **Avaliação**, **Eixo**, **Dimensão**, **Macroprocesso**, **Segmentos**, **Áreas**, **Campi**, **Modalidades**, **Cursos** e **Tipos**. Clique em **Enviar** e o SUAP gera o arquivo em segundo plano, uma resposta por linha.

![Exportação das respostas](usuario/relatorio-xlsx.webp)

---

### 7. Manter as comissões CPA

**Quem pode:** Administrador de Avaliação Institucional.
**Quando usar:** ao publicar a portaria que designa a Comissão Própria de Avaliação, central ou de campus.

1. No menu, acesse **Des. Institucional › Avaliação Integrada › Comissões CPA** e clique em **Adicionar Comissão CPA**.

   ![Listagem de comissões](usuario/comissoes-listagem.webp)

2. Preencha:

   | Campo | O que informar |
   | --- | --- |
   | Tipo | **CPA Central** (uma só na instituição) ou **CPA Local** (uma por campus) |
   | Setor Associado | O setor da comissão; é ele que define o campus |
   | Data da Portaria | A data do ato de designação |
   | Documento da portaria | O documento eletrônico da portaria, se já estiver no SUAP |
   | Membro | Os integrantes; a busca aceita nome ou matrícula |
   | Ativo | Desmarque para encerrar a comissão sem apagá-la |

   ![Formulário da comissão](usuario/comissao-formulario.webp)

3. Clique em **Salvar**.

**Resultado:** *"Cadastro realizado com sucesso."* Os membros entram automaticamente no grupo de acesso da CPA correspondente — e, com isso, passam a ser público-alvo das avaliações dirigidas aos segmentos *CPA Central* e *CPA Campus*. Retirar alguém da comissão, ou desativá-la, desfaz esse acesso pelo mesmo caminho.

> **Só existe uma comissão ativa de cada tipo por campus.** Ao cadastrar uma segunda sem desativar a anterior, o SUAP recusa e mostra *"Comissão CPA Local para o campus … já existe. Para adicionar uma nova, deve-se antes desativar a anterior"*.

**Reunir os e-mails dos membros:** na listagem, o botão **Lista de Emails dos Membros** abre um diálogo com os endereços já formatados para colar num campo de destinatários.

![Lista de e-mails dos membros](usuario/comissao-emails.webp)

---

## Para o público externo

Fluxo de quem **não tem conta no SUAP** — pais e responsáveis, egressos, empresas e profissionais prestadores de serviço, supervisores de estágio. Servidores que atendem essas pessoas também precisam conhecê-lo, para saber o que o outro lado enxerga.

### Responder pelo link público

**Pré-condição:** a avaliação tem ao menos um segmento de **Sociedade Civil** e está dentro do prazo.

1. Abra o endereço divulgado pela instituição. Ele também aparece sozinho no rodapé público do SUAP, em **Serviços de Acesso Público › Avaliações**, com o nome da avaliação.
2. A página traz o texto de orientações e explica por que o e-mail é pedido: é ele que permite **voltar depois** e **rever ou editar** o que você já respondeu.
3. Informe o **E-mail**, escolha o **Tipo do Respondente** (Pais e/ou Responsável, Aluno Egresso, Empresa Prestadora de Serviço, Profissional Prestador de Serviço, Supervisor de Estágio ou Demais segmentos da sociedade civil), resolva o **reCAPTCHA** e clique em **Acessar**. Conforme o tipo escolhido, a página pede também **Matrícula do aluno**, **CPF** ou **CNPJ**.

   ![Identificação do público externo](usuario/externa-identificacao.webp)

4. Responda as perguntas e clique em **Salvar e Continuar**. Voltar ao mesmo endereço e informar o **mesmo e-mail** reabre o questionário de onde você parou.

   ![Questionário do público externo](usuario/externa-questionario.webp)

**Resultado:** *"As suas respostas foram salvas."* — e o questionário fica guardado sob o seu e-mail: voltar ao mesmo endereço e informá-lo de novo reabre exatamente de onde você parou.

![Respostas registradas](usuario/externa-respondido.webp)

> **Se a primeira tentativa apresentar a tela "Erro no Sistema":** informe o mesmo e-mail de novo, na mesma página. O questionário abre normalmente na segunda vez, e nada do que você fizer se perde — o cadastro já foi criado na primeira. É uma falha conhecida do primeiro acesso.

---

## Telas de apoio

Cadastros consultados pelos formulários deste módulo. Ficam todos em **Des. Institucional › Avaliação Integrada › Cadastros** e seguem o padrão do SUAP — listar, adicionar, editar:

**Segmentos Respondentes** · **Escala Likert** · **Tipos de Avaliação**

Duas observações valem por eles:

- **Segmentos Respondentes** lista os catorze segmentos que o módulo conhece (CPA Central, CPA Campus, Gestor, Técnico, ETEP, Docente, Estudante, Desligado, Aluno Egresso, Pais, Empresa e Profissional Prestador de Serviço, Supervisor de Estágio e Demais da sociedade civil). Na prática ela é de consulta: as regras que decidem quem responde o quê estão amarradas a esses catorze, então acrescentar ou renomear itens aqui não cria público novo.
- **Escala Likert** define as réguas de resposta. Cada escala tem seus **níveis**, cadastrados na mesma tela, com nível, descrição, emoji e o critério usado para padronizar os gráficos — é o que o respondente vê como *Discordo*, *Concordo parcialmente* e assim por diante. Vale criar uma escala nova em vez de editar a que já está em uso: mudar os níveis de uma escala já respondida altera a leitura dos relatórios anteriores.
