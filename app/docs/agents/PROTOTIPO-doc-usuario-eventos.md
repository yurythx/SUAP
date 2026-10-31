<!--
PROTÓTIPO — escrito à mão para o ticket
https://gitlab.ifrn.edu.br/cosinf/suap/-/work_items/16997 (Anatomia do documento de
usuário de um módulo). NÃO é a doc oficial do `eventos` e não é gerado por nada.

Depois do grilling, deixou de ser só "algo a que reagir" e passou a ENCODAR as decisões
tomadas. É o gabarito contra o qual a revisão de dev no MR confere um documento — sem
ele, um revisor aprova qualquer coisa. A anatomia extraída está no fim do arquivo.

Ancoragem: passos, nomes de campo, caminhos de menu e mensagens de sucesso são reais,
extraídos de `eventos/features/*.feature` e `eventos/menu.yaml`. Os screenshots são
marcadores `[captura: ...]` — este protótipo não navegou o sistema.
-->

> **Superado como exemplo, mantido como gabarito.** A doc real do `eventos`, gerada pelo
> subagente navegando o sistema, está em `eventos/docs/usuario.md` — use **aquela** como
> exemplo de saída. Este arquivo continua valendo pela seção **"A anatomia, extraída"**, no
> fim, que é o contrato que a revisão confere.
>
> A prova ([#17001](https://gitlab.ifrn.edu.br/cosinf/suap/-/work_items/17001)) refutou três
> coisas do texto abaixo, todas por ele ter sido escrito sem navegar: **Atendimento ao
> Público** e **Banners** são tarefas, não telas de apoio (a ressalva deixada de propósito
> estava certa em desconfiar); as três telas de **Relatórios** existem e não foram
> mencionadas; e participante incluído à mão **já nasce confirmado** (`inscricao_validada`
> tem `default=True`) — o botão de confirmar serve às inscrições vindas da página pública.

# Eventos

Registra os eventos institucionais da instituição — palestras, seminários, cursos, mostras — desde o cadastro pelo servidor organizador até a emissão de certificado para quem participou. É por aqui que um evento ganha página pública de inscrição, tem seus participantes confirmados e passa pela avaliação das dimensões (Ensino, Pesquisa, Extensão).

**Quem usa este módulo**

| Perfil | O que faz aqui |
| --- | --- |
| Servidor | Cadastra o evento que vai organizar e acompanha suas inscrições |
| Coordenador do evento | Gerencia os participantes: inclui, confirma inscrição, emite certificado |
| Avaliador de dimensão | Avalia os eventos da sua dimensão, no campus ou de forma sistêmica |
| Público externo | Inscreve-se pela página pública, sem ter conta no SUAP |

---

## Antes de começar

O cadastro de um evento consome tabelas de apoio que precisam existir: **Dimensões**, **Portes**, **Tipos** e **Subtipos**, **Espacialidades**, **Áreas temáticas**, **Públicos**. Numa instituição já em operação elas estão preenchidas — se algum campo do formulário aparecer vazio, é uma dessas que falta, e todas ficam em `Comunicação Social › Cadastros › Eventos`.

---

## Tarefas

### 1. Cadastrar um evento

**Quem pode:** Servidor
**Quando usar:** ao organizar um evento institucional que precise de divulgação, inscrição ou certificado.

1. No menu, acesse **Comunicação Social › Eventos**.
   `[captura: listagem de eventos, com o botão Adicionar Evento em destaque]`
2. Clique em **Adicionar Evento**.
3. Preencha o formulário. Os campos que costumam gerar dúvida:

   | Campo | O que informar |
   | --- | --- |
   | Dimensões | Uma ou mais entre Ensino, Pesquisa e Extensão — define quem avaliará o evento |
   | Organizadores | Servidores que poderão gerenciar o evento; busque pelo nome |
   | Inscrição Online | Marque para o evento ganhar página pública de inscrição |
   | Gera Certificado? | Marque para habilitar a emissão ao fim do evento |
   | Carga Horária do Evento | No formato `HH:MM` — é o que sai impresso no certificado |
   | Localização | **Local** para evento de um campus; **Sistêmico** para evento de toda a rede |

   `[captura: formulário de cadastro preenchido]`
4. Clique em **Salvar**.

**Resultado:** a mensagem *"Ação realizada com sucesso."* aparece e você é levado à página do evento.
`[captura: página do evento recém-criado]`

**Se o evento terá inscrições:** abra a aba **Detalhamento**, encontre a linha **Participante** e clique no ícone de edição. É nesse popup que se define **Limite de Inscrições**, **Início** e **Fim das Inscrições** e se a inscrição é direta.

---

### 2. Inscrever alguém num evento

**Quem pode:** Coordenador do evento
**Quando usar:** para inscrever manualmente um participante — ou para confirmar quem já se inscreveu pela página pública, caso em que só a etapa 2 se aplica.

**Etapa 1 — incluir o participante**

1. No menu, acesse **Comunicação Social › Eventos** e abra o evento.
2. Vá à aba **Participantes** e clique em **Adicionar Participante**.
3. Informe a pessoa e o tipo de participação, e clique em **Salvar**.

O participante passa a constar na lista, com inscrição **pendente**.

**Etapa 2 — confirmar a inscrição**

4. Ainda na aba **Participantes**, localize a inscrição pendente e confirme-a.

**Resultado:** a inscrição fica confirmada, habilitando o participante à emissão de certificado.
`[captura: aba Participantes, com uma inscrição pendente e uma confirmada]`

---

### 3. Avaliar um evento

**Quem pode:** membro de grupo avaliador de dimensão — local (do campus) ou sistêmico
**Quando usar:** após o evento ser cadastrado, para aprová-lo na dimensão que você avalia.

1. No menu, acesse **Comunicação Social › Eventos**.
2. Abra o evento a avaliar e registre o parecer da sua dimensão.

`[captura: tela de avaliação, como o avaliador a vê]`

---

## Para o público externo

Fluxos executados por quem **não tem conta no SUAP**. Servidores que atendem inscritos também os leem, para saber o que o outro lado enxerga.

### Inscrever-se pela página pública

**Pré-condição:** o evento tem **Inscrição Online** marcada e está dentro do período de inscrições.

1. Acesse o endereço público do evento, divulgado pelos organizadores.
2. Preencha os dados solicitados e confirme a inscrição.

**Resultado:** a inscrição fica registrada como **pendente**, aguardando confirmação do coordenador (tarefa 2, etapa 2).

---

## Telas de apoio

Tabelas consultadas pelos formulários deste módulo. Todas seguem o mesmo padrão do SUAP — listar, adicionar, editar, remover — e ficam em `Comunicação Social › Cadastros › Eventos`:

Áreas temáticas · Classificações · Dimensões · Espacialidades · Naturezas · Portes · Subtipos · Tipos · Tipos de Atividade · Tipos de Modalidade · Tipos de Participação · Públicos

Fora do grupo de cadastros, o módulo ainda expõe **Atendimento ao Público** e **Banners**.

> **Ressalva deste protótipo, deliberadamente deixada em pé:** não navegei o sistema, então **Atendimento ao Público** e **Banners** podem ser tarefas de verdade classificadas aqui por engano. É exatamente o erro que a revisão de dev no MR existe para pegar — e a demonstração de que ela só funciona contra um gabarito que diga o que cada seção deve conter.

---

# A anatomia, extraída

Esta é a parte que vale além do `eventos`.

## Seções obrigatórias

1. **Abertura** — o que o módulo faz, em linguagem de usuário. Sem nome de model, sem caminho de arquivo, sem jargão de Django.
2. **Quem usa este módulo** — tabela perfil → o que faz aqui. **Omitir quando o módulo tem um papel só**: uma tabela de uma linha é ruído.
3. **Tarefas** — cada uma com **Quem pode**, passos numerados e **Resultado**.
4. **Telas de apoio** — listadas, nunca documentadas passo a passo.

## Seções opcionais

- **Antes de começar** — pré-condições que valem para o módulo inteiro.
- **Para o público externo** — só em módulo com face pública.
- **Quando usar** por tarefa — onde o nome da tarefa não se explica sozinho.
- **Pré-condição** por tarefa — só quando depende de outra tarefa.

## Como uma tarefa é cortada

**Uma tarefa por objetivo do usuário**, com etapas numeradas dentro quando o objetivo exige mais de um ato. Não herdar o recorte das `.feature`: elas separam por **arquivo de teste**, não por lógica de usuário — foi por isso que "incluir participante" e "confirmar inscrição" chegaram como duas `Funcionalidade:` e viraram uma tarefa só aqui.

O julgamento de quais ações pertencem ao mesmo objetivo é do subagente, e a semente colhida **não** o fornece. É um dos pontos que a revisão precisa conferir.

## Como um formulário longo vira passo

**Um passo único** (“Preencha o formulário”) **mais uma tabela apenas dos campos que geram dúvida** — os de consequência não-óbvia. Omitir os autoexplicativos.

No `eventos`: 21 campos no formulário, 6 na tabela. `Dimensões` entra porque define quem avaliará o evento; `Carga Horária` entra porque é o que sai impresso no certificado; `Título do Evento` fica de fora.

Descartados: tabela completa dos 21 (a maioria das linhas diria o óbvio, e tabela que se aprende a pular esconde as 6 que importavam) e um passo numerado por campo (fiel às `.feature`, mas 21 passos para uma tela, e o SUAP tem centenas de formulários assim).

## Fluxos públicos

Mesmo documento, **seção própria ao fim**. Um arquivo por módulo, como o mapa fixou — e o servidor que presta suporte precisa ver o que o inscrito enxerga.

## Fora do documento

- Nome de model, caminho de arquivo, jargão de Django.
- Passo a passo das tabelas de apoio.
- **Cenários de configuração inicial.** `Adicionando os usuários necessários para os testes EVENTOS` é setup de teste, não tarefa: **4 dos 9 cenários do `eventos`** são disso (setup e `Sai do sistema`). O subagente tem de descartá-los, e a tag `@do_document` do inventário colhido já separa — os 5 documentáveis do `eventos` são exatamente as tarefas reais.

## Legendas de captura

Podem afirmar o que um perfil **não** vê (“note que os botões de edição não aparecem para este perfil”) quando isso for informação útil, mas **não são obrigatórias** — exigi-las de toda captura obrigaria o subagente a comparar telas entre papéis, custo que nenhum ticket cobriu.
