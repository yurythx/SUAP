# Eventos

Registra os eventos institucionais da instituição — palestras, seminários, cursos, mostras — do cadastro pelo servidor organizador até o certificado de quem participou. É por aqui que um evento passa pela avaliação das dimensões, ganha um endereço público de inscrição, tem seus participantes confirmados e sua presença registrada.

O mesmo módulo guarda mais duas coisas da Comunicação Social: o **registro dos atendimentos ao público** feitos no campus e os **banners** publicados na página inicial do SUAP.

**Quem usa este módulo**

| Perfil | O que faz aqui |
| --- | --- |
| Servidor | Cadastra o evento que vai organizar |
| Coordenador ou organizador do evento | Gerencia os participantes: inclui, confirma inscrição e presença, finaliza o evento e emite os certificados |
| Avaliador de dimensão | Defere, indefere ou devolve os eventos da dimensão que avalia |
| Coordenador de Comunicação (e Coordenador de Comunicação Sistêmico) | Gerencia qualquer evento do seu campus (ou de toda a rede) e emite os relatórios |
| Comunicador Social | Registra os atendimentos ao público do campus |
| Público externo | Inscreve-se pela página pública do evento, sem ter conta no SUAP |

---

## Antes de começar

O formulário do evento consome tabelas de apoio que precisam estar preenchidas: **Dimensões**, **Portes**, **Tipos** e **Subtipos**, **Classificações**, **Espacialidades**, **Áreas temáticas**, **Naturezas**. Num campus já em operação elas existem — se alguma lista aparecer vazia no cadastro, é uma dessas que falta. Todas ficam em **Comunicação Social › Cadastros › Eventos**.

---

## Tarefas

### 1. Cadastrar um evento e abrir as inscrições

**Quem pode:** Servidor, Coordenador de Comunicação e Coordenador de Comunicação Sistêmico.
**Quando usar:** ao organizar um evento institucional que precise de divulgação, inscrição ou certificado.

**Etapa 1 — cadastrar**

1. No menu, acesse **Comunicação Social › Eventos** e clique em **Adicionar Evento**.

   ![Listagem de eventos](usuario/evento-listagem.webp)

2. Preencha o formulário, dividido em blocos (*Dados gerais*, *Coordenação e Organização*, *Realização*, *Inscrição*, *Configurações*, *Carga Horária*, *Classificação*). Os campos que costumam gerar dúvida:

   | Campo | O que informar |
   | --- | --- |
   | Dimensões | Uma ou mais entre Ensino, Pesquisa, Extensão, Gestão e Recursos Humanos — **define quem vai avaliar o evento** |
   | Organizadores | Servidores que poderão gerenciar o evento junto com você; busque pelo nome |
   | Inscrição Online | Marque para o evento ganhar um endereço público de inscrição |
   | Gera Certificado? | Marque para habilitar a emissão de certificados no fim do evento |
   | Carga Horária do Evento | No formato `HH:MM` — é o que sai impresso no certificado, e o envio só ocorre se for maior que zero |
   | Localização | **Local** para evento de um campus, **Regional**, **Nacional** ou **Internacional** conforme o alcance |

   ![Formulário de cadastro do evento](usuario/evento-formulario.webp)

3. Clique em **Salvar**.

**Resultado:** aparece a mensagem *"Ação realizada com sucesso."* e você é levado à página do evento, ainda com a tarja **Inativo** — ele só passa a valer depois de avaliado (tarefa 2). A página já mostra a **URL pública do evento**, que é o endereço a divulgar.

![Página do evento recém-criado](usuario/evento-criado.webp)

**Etapa 2 — definir o período de inscrições**

4. Na página do evento, abra a aba **Detalhamento** e, no quadro **Tipos de participantes**, clique no ícone de edição da linha **Participante**.
5. No popup, informe **Limite de Inscrições**, **Início** e **Fim das Inscrições** (com as horas), marque **Permite Inscrição Direta** se a inscrição não depender de convite e clique em **Salvar**.

   ![Popup do tipo de participante](usuario/evento-inscricoes.webp)

**Resultado:** *"Tipo de participante alterado com sucesso."* O evento passa a aceitar inscrições pela página pública dentro do período informado.

---

### 2. Avaliar um evento

**Quem pode:** quem pertence a um grupo avaliador da dimensão do evento — o avaliador **local** só enxerga os eventos do seu próprio campus; o **sistêmico**, os de toda a rede. Os grupos avaliadores são definidos em cada dimensão, em **Comunicação Social › Cadastros › Eventos › Dimensões**.
**Quando usar:** enquanto o evento estiver aguardando aprovação. Sem esta etapa ele não aceita participantes nem aparece na área pública.

1. No menu, acesse **Comunicação Social › Eventos** e clique na aba **Aguardando minha aprovação**.

   ![Aba Aguardando minha aprovação](usuario/avaliacao-aguardando.webp)

2. Na linha do evento, clique no ícone de exibição para abri-lo e conferir os dados.
3. Clique em **Avaliar** e escolha **Deferir** ou **Indeferir**.

   ![Botões Avaliar e Devolver na página do evento](usuario/avaliacao-parecer.webp)

**Resultado:** ao deferir, aparece *"O evento foi deferido."*, o evento fica ativo e passa a aceitar participantes.

**Se faltar informação:** ao lado de *Avaliar* fica o botão **Devolver**, que encerra a avaliação sem deferir nem indeferir.

---

### 3. Gerenciar os participantes de um evento

**Quem pode:** o coordenador ou um dos organizadores do evento; também o Coordenador de Comunicação do campus e o Coordenador de Comunicação Sistêmico. Evento indeferido não é gerenciável.
**Pré-condição:** o evento já foi deferido (tarefa 2).

![Página de um evento deferido](usuario/evento-pagina.webp)

Na página do evento, clique em **Participantes** para chegar à tela de gestão. Ela tem uma aba por tipo de participação (Participante, Palestrante, Convidado, Organizador), e as ações valem para os participantes **marcados** na aba aberta.

![Tela de participantes](usuario/participantes-lista.webp)

**Incluir alguém manualmente**

1. Na aba do tipo de participação desejado, clique em **Adicionar**.
2. No popup, informe **Nome**, **CPF**, **E-mail** e **Perfil** (e, para estrangeiro, **Nacionalidade**, **Nº do Passaporte** e **País de Origem**), e clique em **Salvar**.

   ![Popup de inclusão de participante](usuario/participante-formulario.webp)

**Resultado:** *"<Tipo> adicionado com sucesso."* Quem é incluído por aqui **já entra com a inscrição confirmada** — não é preciso confirmar depois. O cartão de cada participante mostra o que falta nele (*Inscrição não confirmada*, *Presença não confirmada*, *Certificado não enviado*), a carga horária total e uma **chave de acesso**.

**Confirmar inscrições vindas da página pública**

3. Marque os inscritos com a tarja **Inscrição não confirmada** e clique em **Confirmar inscrição**.

   ![Inscrição pendente vinda da página pública](usuario/inscricao-pendente.webp)

**Resultado:** *"N inscrição(ões) confirmada(s) com sucesso."* Se nenhum dos marcados estava pendente, o SUAP responde *"Nenhuma inscrição confirmada."* e nada muda.

**Registrar presença e emitir os certificados**

4. Depois de o evento acontecer, marque quem compareceu e clique em **Confirmar presença**.

   ![Participante marcado, com as ações em lote](usuario/participante-selecionado.webp)

5. Volte à página do evento e clique em **Finalizar**.
6. De volta à tela de participantes, marque quem tem direito e clique em **Enviar certificado**.

**Resultado:** *"N E-mail(s) enviado(s) com sucesso."* O certificado só vai para quem tem **presença confirmada** e **carga horária cumprida maior que zero** — a própria tela avisa isso no topo.

![Certificados enviados](usuario/certificado-enviado.webp)

**Outras ações da mesma tela:** **Importar**, **Exportar**, **Importar Lista de Presença**, **Enviar Mensagem**, **Reenviar credenciais de acesso**, **Gerar etiqueta em lote**, **Cancelar presença**, **Remover participante** e **Migrar Participantes**.

---

### 4. Emitir os relatórios de eventos e de participantes

**Quem pode:** os perfis que enxergam eventos — Servidor, Coordenador de Comunicação, Coordenador de Comunicação Sistêmico, Prestador de Serviço e Aluno.
**Quando usar:** para prestar contas dos eventos de um período, campus ou dimensão.

1. No menu, acesse **Comunicação Social › Relatórios › Relatório de Eventos**.
2. Ajuste os filtros — **Ano**, **Campus**, **Dimensão**, **Setor**, *Apenas eventos de capacitação*, *Apenas eventos com cunho social* — e clique em **Enviar**.

**Resultado:** o quadro **Detalhes** aparece abaixo dos filtros, com os eventos deferidos que atendem ao recorte.

![Relatório de eventos](usuario/relatorio-eventos-resultado.webp)

Para a lista de pessoas em vez da lista de eventos, use **Comunicação Social › Relatórios › Relatório Participantes**: os filtros são **Título**, **Dimensão**, **Ano** e **Campus**, o resultado sai no quadro **Resultados**, e ali há os botões **Gerar CSV** e **Gerar XLS**.

![Relatório de participantes](usuario/relatorio-participantes-resultado.webp)

---

### 5. Consultar o calendário de eventos do campus

**Quem pode:** os mesmos perfis da tarefa 4.
**Quando usar:** para ver, mês a mês, o que já está marcado antes de agendar mais um evento.

1. No menu, acesse **Comunicação Social › Relatórios › Calendário de Eventos**.
2. Escolha **Ano** e **Unidade Organizacional** e clique em **Enviar**.

**Resultado:** o calendário do ano inteiro, com os eventos ativos e deferidos do campus marcados nos seus dias.

![Calendário de eventos por campus](usuario/calendario-resultado.webp)

---

### 6. Registrar um atendimento ao público

**Quem pode:** Comunicador Social e Coordenador de Comunicação Sistêmico.
**Quando usar:** a cada atendimento prestado ao público no campus, para que ele entre na estatística da Comunicação Social.

1. No menu, acesse **Comunicação Social › Atendimentos ao Público** e clique em **Adicionar Atendimento ao Público**.
2. Informe **Campus**, **Tipo**, **Motivo**, **Assunto**, **Público** e **Situação**, e clique em **Salvar**. A data e a hora são registradas automaticamente.

   ![Formulário de atendimento ao público](usuario/atendimento-formulario.webp)

**Resultado:** *"Cadastro realizado com sucesso."* e o atendimento passa a constar na listagem, que pode ser filtrada por tipo, motivo, assunto, público e situação.

![Listagem de atendimentos ao público](usuario/atendimento-listagem.webp)

---

### 7. Publicar um banner

**Quem pode:** Coordenador de Comunicação Sistêmico.
**Quando usar:** para divulgar uma campanha ou um evento na página inicial do SUAP, por um período determinado.

1. No menu, acesse **Comunicação Social › Banners** e clique em **Adicionar Banner**.
2. Preencha:

   | Campo | O que informar |
   | --- | --- |
   | Título | Texto que identifica o banner |
   | Imagem | A arte a ser exibida |
   | Tipo | Onde o banner aparece — hoje há uma opção só, **Início** |
   | Link | Endereço aberto ao clicar no banner (opcional) |
   | Início / Término da Publicação | Data e hora em que o banner entra e sai do ar |

   ![Formulário de banner](usuario/banner-formulario.webp)

3. Clique em **Salvar**.

**Resultado:** *"Cadastro realizado com sucesso."* e o banner passa a constar na listagem.

![Listagem de banners](usuario/banner-listagem.webp)

---

## Para o público externo

Fluxo executado por quem **não tem conta no SUAP**. Quem organiza o evento também deve conhecê-lo, para saber o que o inscrito enxerga e para prestar suporte.

### Inscrever-se pela página pública do evento

**Pré-condição:** o evento está deferido, tem **Inscrição Online** marcada e está dentro do período de inscrições definido na tarefa 1, etapa 2.

1. Acesse a lista pública de eventos do SUAP (endereço `/eventos/`) e clique no nome do evento — ou vá direto à **URL pública do evento**, divulgada pelos organizadores.

   ![Lista pública de eventos](usuario/publico-listagem.webp)

2. **Identificação:** informe a **Nacionalidade** e o **CPF** (ou o **Nº do Passaporte** e o **País de Origem**, se estrangeiro) e clique em **Continuar**. A página também oferece **Entrar** e **Entrar com Gov.BR**, para quem já tem conta.

   ![Passo 1 da inscrição pública](usuario/publico-identificacao.webp)

3. **Dados pessoais:** informe **Nome**, **E-mail** e **Telefone** e clique em **Continuar**.

   ![Passo 2 da inscrição pública](usuario/publico-dados.webp)

4. **Participação:** escolha o **Tipo de participação** e clique em **Confirmar inscrição**.

**Resultado:** aparece *"Inscrição realizada com sucesso."*. A inscrição fica **pendente** até o coordenador confirmá-la (tarefa 3). O acompanhamento é feito em **Área do participante**, com a chave de acesso enviada por e-mail.

![Confirmação da inscrição pública](usuario/publico-confirmacao.webp)

---

## Telas de apoio

Tabelas consultadas pelos formulários deste módulo. Todas seguem o mesmo padrão do SUAP — listar, adicionar, editar, remover — e não têm passo a passo próprio.

Em **Comunicação Social › Cadastros › Eventos**: Áreas temáticas · Classificações · Dimensões · Espacialidades · Naturezas · Portes · Subtipos · Tipos · Tipos de Atividade · Tipos de modalidades · Tipos de Participação.

Em **Comunicação Social › Cadastros › Atendimentos** (as tabelas que alimentam a tarefa 6): Assuntos · Motivos · Públicos · Situações · Tipos.

> **Dimensões** é a única com efeito além de preencher uma lista: é nela que se define quais grupos avaliam cada dimensão, e portanto quem executa a tarefa 2.
