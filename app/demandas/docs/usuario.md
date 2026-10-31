# Demandas

Registra e acompanha os pedidos de melhoria e de novas funcionalidades nos sistemas da instituição, do pedido do demandante até a entrega concluída. Cada demanda percorre uma sequência de etapas — **Solicitada**, **Em negociação**, **Em análise**, **Aprovada**, **Em desenvolvimento**, **Em homologação**, **Homologada**, **Em implantação** e **Concluída** —, com papéis diferentes em cada uma: o demandante descreve e valida, o analista especifica e conduz, o desenvolvedor implementa. O módulo também recebe **sugestões de melhorias** abertas por qualquer pessoa com acesso e as transforma em demandas.

## Quem usa este módulo

| Perfil | O que faz aqui |
| --- | --- |
| Demandante | Abre a demanda da sua área de atuação, acompanha o andamento, aprova ou reprova a consolidação e as entregas (homologação). |
| Analista | Assume a demanda, registra a consolidação, conduz a demanda pelas etapas e mantém os cadastros de apoio. |
| Desenvolvedor | Atende a demanda e altera a etapa conforme o andamento do desenvolvimento. |
| Recebedor de Demandas | Conduz demandas e consulta relatórios e o painel de força-trabalho. |
| Coordenador de TI sistêmico | Mantém as áreas de atuação e os módulos e acompanha indicadores e força-trabalho. |
| Servidor e Prestador de Serviço | Abrem e votam em sugestões de melhorias. |
| Público externo | Consulta as atualizações do sistema, sem login. |

## Antes de começar

Toda demanda pertence a uma **Área de Atuação** e a pelo menos um **Módulo**. As áreas de atuação e os módulos ficam em **Tec. da Informação › Desenvolvimento › Cadastros**, e cada área tem um **Demandante Responsável** e os demandantes vinculados — é essa lista que responde pelas demandas da área. Numa instituição em operação esses cadastros já existem; se a lista de módulos aparecer vazia no formulário de cadastro, é porque a área escolhida não tem módulos vinculados.

Duas coisas valem para todas as tarefas:

- **A consolidação é obrigatória antes da análise.** A demanda não avança para **Em análise** enquanto não tiver uma consolidação registrada.
- **Cada área de atuação prioriza um número limitado de demandas** para desenvolvimento. A prioridade aparece na própria página da demanda e não impede que as demais andem — apenas ordena a fila.

## Tarefas

### 1. Abrir uma demanda

**Quem pode:** perfis com permissão de cadastrar demandas — Demandante, Analista, Desenvolvedor e Recebedor de Demandas. Na rodada de navegação, o acesso foi feito pelo Demandante.
**Quando usar:** ao identificar uma melhoria ou uma funcionalidade nova que precise ser desenvolvida.

1. No menu, acesse **Tec. da Informação › Desenvolvimento › Demandas**.
2. Clique em **Adicionar demanda**.

   ![Dashboard de demandas](usuario/dashboard-demandas.webp)

3. Preencha o formulário. Os campos que costumam gerar dúvida:

   | Campo | O que informar |
   | --- | --- |
   | Área de Atuação | A área responsável por avaliar e desenvolver a demanda. |
   | Módulos | Um ou mais módulos do sistema afetados. A lista é carregada depois que a área de atuação é escolhida. |
   | Tipo | **Melhoria**, para ajuste no que já existe, ou **Funcionalidade**, para algo novo. |
   | Demandantes | Quem acompanha e responde pela demanda. |
   | Descrição da Demanda | Evite informações sensíveis: a descrição é pública. |
   | Privada? | Marque para restringir os detalhes a quem participa da demanda. |
   | Demanda Pré-requisito | Indica que o desenvolvimento desta demanda depende da conclusão de outra demanda. |

   ![Formulário de cadastro da demanda](usuario/formulario-nova-demanda.webp)

4. Clique em **Salvar**.

**Resultado:** a mensagem *"Cadastro realizado com sucesso."* aparece e a demanda é aberta na etapa **Solicitada**, já com a régua de etapas no topo da página.

![Demanda recém-aberta](usuario/demanda-aberta.webp)

### 2. Registrar a consolidação e encaminhar a demanda para análise

**Quem pode:** Analista. A mudança de etapa também está disponível a Desenvolvedor e Recebedor de Demandas.
**Pré-condição:** a demanda existe (tarefa 1).
**Quando usar:** depois de conversar com o demandante sobre o que será feito.

1. No menu, acesse **Tec. da Informação › Desenvolvimento › Demandas** e clique em **Visualizar todas** para abrir a listagem de demandas.
2. Localize a demanda pelo campo **Texto** e clique em **Filtrar**. Na linha da demanda, clique no ícone de edição.
3. No quadro **Atendimento**, vincule em **Analistas** quem vai atender a demanda e clique em **Salvar**.

   ![Vínculo dos analistas na edição da demanda](usuario/demanda-editar-analistas.webp)

4. Abra a demanda e, em **Alterar etapa**, escolha **Negociar** para registrar o início do levantamento de requisitos. Clique em **Enviar**.
5. Na aba **Consolidação**, clique em **Adicionar especificação**. Informe o **Nome** da especificação e as **Atividade(s)** previstas.

   ![Formulário da especificação](usuario/demanda-especificacao.webp)

6. Clique em **Salvar**. Uma demanda pode ter mais de uma especificação; repita os passos 5 e 6 para cada uma.
7. Clique em **Editar** no quadro da consolidação e descreva o resultado do levantamento em **Descrição**, complementando com o **Detalhamento** e os **Novos Grupos de Usuários** que serão envolvidos. Clique em **Salvar**.

   ![Consolidação da demanda](usuario/demanda-consolidacao.webp)

8. Em **Alterar etapa**, escolha **Analisar**, informe o **Comentário** e a **Previsão** e clique em **Enviar**.

   ![Encaminhamento para análise](usuario/demanda-analisar.webp)

**Resultado:** a mensagem *"A etapa da demanda foi alterada."* aparece e a demanda passa para **Em análise**, ficando com o demandante para validação.

> **Sem consolidação não há análise.** Se você escolher **Analisar** antes de registrar a consolidação, o sistema responde com o aviso *"Não é possível alterar uma demanda para Em Análise caso ela não tenha Consolidação"* e a demanda permanece **Em negociação**.

### 3. Aprovar ou reprovar a consolidação

**Quem pode:** Demandante.
**Pré-condição:** a demanda está em **Em análise** (tarefa 2).

1. Abra a demanda e, na aba **Consolidação**, leia a descrição e as especificações. O quadro **O que analisar?** lista o que precisa ser conferido: se a consolidação atende às necessidades, se os grupos de usuários envolvidos estão contemplados, se todas as funcionalidades necessárias estão nas especificações e se o texto está em linguagem comum, sem termos técnicos.

   ![Consolidação aguardando aprovação](usuario/demanda-em-analise.webp)

2. Clique em **Aprovar** ou em **Reprovar**.
3. Na tela de confirmação, informe a **Senha para confirmação** e marque **Confirma a operação**. Clique em **Enviar**.

   ![Confirmação da reprovação](usuario/demanda-reprovar.webp)

**Resultado:** a mensagem *"A consolidação da demanda foi aprovada."* aparece e a demanda passa para **Aprovada**. Se você reprovar, a mensagem é *"A consolidação da demanda foi reprovada."* e a demanda volta para **Em negociação**, para o analista ajustar a consolidação e reencaminhar.

### 4. Conduzir a demanda pelas etapas de desenvolvimento, homologação e implantação

**Quem pode:** perfis que atendem demandas — Analista, Desenvolvedor e Recebedor de Demandas.
**Pré-condição:** a consolidação foi aprovada (tarefa 3).

1. Abra a demanda e, em **Alterar etapa**, escolha **Desenvolver**. Informe o **Comentário** e a **Previsão** e clique em **Enviar**. A demanda passa para **Em desenvolvimento**.
2. Quando houver algo para o demandante validar, acesse a aba **Entregas**, clique em **Nova entrega** e preencha os campos:

   | Campo | O que informar |
   | --- | --- |
   | Título da entrega e O que está sendo entregue | O pacote que o demandante vai validar. |
   | Notas para o demandante | O que testar, os fluxos principais e dados de exemplo. |
   | Prazo para o demandante responder | Obrigatório. É também a previsão da etapa **Em homologação**. |
   | Especificações entregues | As especificações da consolidação que esta entrega cumpre. Aparece quando a consolidação tem especificações. |
   | Conclui a demanda? | Só para demanda sem especificações: marque se, aprovada, a entrega encerra o escopo. |
   | Ambiente de Homologação, ou URL e Senha | Onde o demandante vai testar, quando houver ambiente de testes. |
   | Branch | Preencha se o desenvolvimento tiver uma branch própria: o merge request é criado a partir dela quando a demanda fica **Homologada**. |

   ![Formulário de nova entrega](usuario/demanda-homologar.webp)

3. Clique em **Salvar**. A demanda passa para **Em homologação** e fica com o demandante (tarefa 5). Enquanto houver uma entrega aguardando resposta, não é possível registrar outra; para substituí-la, use **Cancelar entrega**, o que devolve a demanda para **Em desenvolvimento**.
4. Depois de a demanda ficar **Homologada**, em **Alterar etapa** escolha **Implantar**, informe o **Comentário** e a **Previsão** e, se houver, o **ID Merge-request**. Clique em **Enviar**. Se o merge request tiver sido criado pela branch, a demanda já vai sozinha para **Em implantação**.
5. Quando a entrega estiver em uso, em **Alterar etapa** escolha **Concluir**, informe o **Comentário** e a **Conclusão** e clique em **Enviar**.

**Resultado:** a mensagem *"A etapa da demanda foi alterada."* aparece a cada mudança e a demanda termina a régua em **Concluída**.

![Demanda concluída](usuario/demanda-concluida.webp)

> **Suspender e cancelar.** Conforme a etapa atual, o mesmo menu **Alterar etapa** também oferece **Suspender**, que interrompe a demanda sem encerrá-la, e **Cancelar**, que a encerra.

### 5. Validar uma entrega (homologar)

**Quem pode:** os demandantes da demanda e o demandante responsável da área. Quem cadastrou a entrega nunca a valida; interessados acompanham e comentam.
**Pré-condição:** a demanda está **Em homologação**, com uma entrega aguardando resposta (tarefa 4).

1. Abra a demanda e acesse a aba **Entregas**. A entrega pendente mostra o que foi entregue, o prazo para responder e o ambiente de testes.

   ![Entrega aguardando validação](usuario/demanda-em-homologacao.webp)

2. Teste a entrega e clique em **Aprovar** ou em **Reprovar**. Para reprovar, informe o **Motivo da reprovação**: é o que o desenvolvedor vai corrigir.
3. Clique em **Enviar**.

   ![Aprovação da entrega](usuario/demanda-aprovar-homologacao.webp)

**Resultado:**

- **Aprovar** — se, com esta entrega, todas as especificações da consolidação já foram aprovadas em alguma entrega, a demanda passa para **Homologada**, liberando a implantação. Se ainda faltam especificações, a demanda volta para **Em desenvolvimento** e a aba **Entregas** lista as que faltam.
- **Reprovar** — a demanda volta para **Em desenvolvimento**, com o motivo registrado na entrega.

> **Prazo vencido.** Se o prazo para responder passar, a entrega continua aguardando e a demanda mostra o selo **Entrega vencida**. Enquanto houver alterações sem validação na consolidação, a entrega não pode ser aprovada.

### 6. Sugerir uma melhoria

**Quem pode:** Servidor, Prestador de Serviço e Demandante. A área de atuação define quais desses públicos podem abrir sugestões (tarefa 9).
**Quando usar:** para propor uma melhoria em um módulo do sistema sem abrir uma demanda.

1. No menu, acesse **Tec. da Informação › Desenvolvimento › Sugestões de melhorias**.
2. Na área de atuação desejada, clique no módulo ao qual a sugestão se refere. Também é possível buscar o módulo pelo campo **Busque um módulo**.

   ![Áreas e módulos para sugestões](usuario/sugestoes-areas.webp)

3. Clique em **Adicionar Sugestão**.
4. Preencha **Título** e **Descrição** e, se quiser, vincule **Interessados**.

   ![Formulário da sugestão de melhoria](usuario/sugestao-formulario.webp)

5. Clique em **Salvar**.

**Resultado:** a mensagem *"Sugestão de Melhoria salva com sucesso."* aparece e a sugestão é aberta, já com os botões de voto e o quadro com os demandantes da área.

![Sugestão registrada](usuario/sugestao-detalhe.webp)

### 7. Concordar ou discordar de uma sugestão

**Quem pode:** os perfis que acessam o módulo de sugestões — Servidor, Prestador de Serviço e Demandante.
**Pré-condição:** a sugestão ainda aceita votos — os botões **Concordar** e **Discordar** aparecem no cartão dela.

1. Acesse **Tec. da Informação › Desenvolvimento › Sugestões de melhorias** e abra o módulo da sugestão.
2. No cartão da sugestão, clique em **Concordar com a sugestão** (polegar para cima) ou em **Discordar da sugestão** (polegar para baixo). No detalhe da sugestão os mesmos botões ficam no quadro **Sugestão**.

**Resultado:** a mensagem *"Voto cadastrado com sucesso."* aparece e o seu nome é somado ao quadro **Concordaram**, no detalhe da sugestão.

![Voto registrado na sugestão](usuario/sugestao-concordar.webp)

### 8. Transformar uma sugestão em demanda

**Quem pode:** o responsável pela sugestão ou o demandante da área de atuação, com permissão para cadastrar demandas.

1. No menu, acesse **Tec. da Informação › Desenvolvimento › Sugestões de melhorias** e clique em **Visualizar todas**.
2. Localize a sugestão pelo campo **Texto**, clique em **Filtrar** e abra-a pelo ícone de exibição.
3. Clique em **Atribuir-se como Responsável**. Se a sugestão ainda estiver **Pendente**, ela passa para **Em análise** — o detalhe do fluxo fica no quadro **Sugestão**.
4. Clique em **Editar**, altere **Situação** para **Deferida** e clique em **Salvar**.

   ![Sugestão deferida](usuario/sugestao-deferir.webp)

5. Clique em **Gerar Demanda**. Revise os dados que vieram da sugestão — **Área de Atuação**, **Título da Demanda**, **Descrição da Demanda**, **Demandantes**, **Interessados** e **Tags** — e clique em **Salvar**.

   ![Cadastro da demanda gerada](usuario/sugestao-gerar-demanda.webp)

**Resultado:** a mensagem *"Demanda gerada com sucesso."* aparece e a demanda é aberta na etapa **Solicitada**, ligada à sugestão de origem. A partir daí ela segue o fluxo das tarefas 2 a 5.

![Demanda gerada a partir da sugestão](usuario/demanda-gerada-da-sugestao.webp)

### 9. Definir quem pode sugerir melhorias numa área de atuação

**Quem pode:** Coordenador de TI sistêmico.
**Quando usar:** para restringir ou liberar o recebimento de sugestões por público, em cada área.

1. No menu, acesse **Tec. da Informação › Desenvolvimento › Cadastros › Áreas de atuação**.

   ![Listagem de áreas de atuação](usuario/areas-de-atuacao.webp)

2. Clique no ícone de edição da área.
3. Marque ou desmarque **Recebe sugestões de melhorias de Alunos?**, **de Servidores?** e **de Prestadores de Serviço?**. Os **Módulos** vinculados à área definem para quais módulos as sugestões podem ser abertas.

   ![Públicos da área de atuação](usuario/area-publicos.webp)

4. Clique em **Salvar**.

**Resultado:** a mensagem *"Atualização realizada com sucesso."* aparece. O público desmarcado deixa de ver a área na tela de sugestões: com **Servidores** desmarcado, um servidor não encontra a área, mesmo que ela tenha módulos vinculados.

![Área indisponível para o público desmarcado](usuario/sugestoes-sem-area.webp)

### 10. Acompanhar demandas e indicadores

**Quem pode:** os relatórios exigem permissão de relatório — Demandante, Analista, Coordenador de TI sistêmico e Recebedor de Demandas. O painel de força-trabalho é de Analista, Coordenador de TI sistêmico e Recebedor de Demandas.
**Quando usar:** para consultar volume, prazos e carga de trabalho por área e por analista.

1. Para o acompanhamento por área e período, acesse **Tec. da Informação › Desenvolvimento › Relatórios › Acompanhamento de demandas**, informe **Data Inicial**, **Data Final** e, se quiser, a **Área de atuação**, e clique em **Enviar**.

   ![Acompanhamento de demandas](usuario/acompanhamento-demandas.webp)

2. Para os indicadores, acesse **Tec. da Informação › Desenvolvimento › Relatórios › Indicadores** e navegue pelas abas **Demandas**, **Analistas/Desenvolvedores** e **Atualizações**, filtrando por **Data Inicial**, **Data Final** e **Tag**.

   ![Indicadores de demandas](usuario/demandas-indicadores.webp)

3. Para a distribuição de trabalho, acesse **Tec. da Informação › Desenvolvimento › Painel de Força-trabalho** e use as abas **Força-trabalho** e **Desenvolvedores por atualizações**.

   ![Painel de força-trabalho](usuario/painel-forca-trabalho.webp)

4. Para a relação de demandas por módulo, acesse **Relatórios › Demandas por tags**, informe o período e clique em **Enviar**.

   ![Relatório de demandas por tags](usuario/relatorio-demandas-por-tags.webp)

**Resultado:** cada relatório exibe as demandas e os indicadores do período escolhido, e a página de indicadores permite alternar entre as visões de demandas, de analistas/desenvolvedores e de atualizações.

## Para o público externo

### Consultar as atualizações do sistema

Não exige login. O módulo publica a lista de atualizações implantadas, com o tipo (Funcionalidade, Manutenção ou Bug), a data de implantação, os módulos afetados e, quando houver, o detalhamento da mudança.

1. Na página de serviços de acesso público, em **Sobre o Suap**, clique em **Atualizações do sistema**.

**Resultado:** a lista das atualizações publicadas é exibida, da mais recente para a mais antiga.

![Atualizações do sistema](usuario/atualizacoes-do-sistema.webp)

## Telas de apoio

Telas de consulta e de cadastro que dão suporte às tarefas acima e seguem o padrão do SUAP — listar, filtrar, adicionar, editar e remover. Todas ficam em **Tec. da Informação › Desenvolvimento**:

- **Demandas** (dashboard) e **Listagem**, com filtros por área, situação, tipo e módulo.
- **Cadastros**: Áreas de atuação, Módulos, Analistas/Desenvolvedores e Projetos do Gitlab.
- **Atualizações** e **Ambientes de homologação**.
- **Demandantes**, que mantém os demandantes de cada área de atuação.
- **Glossário**, com os termos usados no módulo.

A página da demanda ainda oferece **Comentários**, **Anexos**, **Nova entrega**, **Nova sub-demanda** e, para os perfis de atendimento, **Adicionar Nota Interna**.
