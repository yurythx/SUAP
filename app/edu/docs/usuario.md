# Ensino

Guarda a vida acadêmica da instituição de ponta a ponta: os cursos e suas matrizes curriculares, as turmas e os diários de cada período letivo, a matrícula do aluno, o lançamento de aulas, faltas e notas pelo professor, o fechamento do período, a renovação da matrícula e, no fim da linha, o diploma.

É o maior módulo do SUAP e o mais encadeado — cada etapa depende da anterior. A ordem é sempre a mesma: **diretoria acadêmica → curso e matriz → calendário → turmas e diários → aluno matriculado → período executado → período fechado → renovação → conclusão**.

**Quem usa este módulo**

| Perfil | O que faz aqui |
| --- | --- |
| Administrador Acadêmico | Configura o campus: diretoria, perfis, cursos, matrizes, componentes e as tabelas de apoio |
| Secretário Acadêmico (e Auxiliar de Secretaria Acadêmica) | Calendário, turmas e diários, matrícula, fechamento e reabertura de período, renovação de matrícula, TCC |
| Coordenador de Curso | Aprova os planos de ensino do seu curso e acompanha turmas, diários e alunos |
| Diretor Acadêmico | Homologa os planos de ensino e responde pelos procedimentos acadêmicos do campus |
| Professor | Plano de ensino, aulas, faltas, notas e entrega das etapas dos seus diários |
| Aluno | Consulta boletim, histórico e requisitos, renova a matrícula, emite declarações e mantém os próprios dados |
| Coordenador de Registros Acadêmicos | Emite e registra diplomas e certificados |
| Operador ENADE e Diretor de Avaliação e Regulação do Ensino | Convocam os alunos para o ENADE e registram a situação de cada um no exame |

---

## Antes de começar

Um campus só opera este módulo depois de três coisas existirem, nesta ordem: a **diretoria acadêmica** (tarefa 1), o **curso com matriz vinculada** (tarefa 2) e o **calendário acadêmico** do período (tarefa 3). Sem a diretoria não há a quem vincular curso, turma ou perfil; sem matriz o curso não gera turma; sem calendário o SUAP recusa aula, nota e fechamento, porque é ele que define as datas válidas.

Os formulários deste módulo consomem dezenas de tabelas de apoio (níveis de ensino, modalidades, turnos, formas de ingresso, tipos de componente, núcleos, áreas). Num campus em operação elas já existem — se uma lista aparecer vazia, é uma delas que falta. Todas ficam em **Ensino › Cadastros Gerais** (veja *Telas de apoio*, no fim).

---

## Tarefas

### 1. Configurar a diretoria acadêmica e atribuir os perfis

**Quem pode:** Administrador Acadêmico.
**Quando usar:** ao pôr um campus em operação, e sempre que alguém assume ou deixa uma função acadêmica.

**Etapa 1 — cadastrar a diretoria**

1. No menu, acesse **Ensino › Cadastros Gerais › Diretorias Acadêmicas** e clique em **Adicionar Diretoria Acadêmica**.

   ![Listagem de diretorias acadêmicas](usuario/diretoria-listagem.webp)

2. Preencha o formulário, dividido em *Dados gerais* e *Nomenclatura para Diploma*:

   | Campo | O que informar |
   | --- | --- |
   | Setor | O setor já existente no SUAP que passa a ser a diretoria — é ele que delimita o alcance de todos os perfis atribuídos aqui |
   | Tipo | **Diretoria Acadêmica** para o campus; **Sistêmica** para a diretoria que habilita os perfis com acesso a toda a rede (Diretor de Avaliação e Regulação do Ensino, Operador ENADE); há ainda *Diretoria de Ensino* e *PRONATEC* |
   | Autoridade Máxima (M) / (F) | Como o cargo é impresso no diploma (por exemplo, *Reitor* / *Reitora*) |
   | Responsável pela Diretoria (M) / (F) | Idem, para quem assina como responsável pela diretoria |
   | Ensino a Distância? | Marque se a diretoria responde por oferta EAD |

   ![Formulário da diretoria acadêmica](usuario/diretoria-formulario.webp)

3. Clique em **Salvar**.

**Resultado:** *"Cadastro realizado com sucesso."* e a diretoria passa a constar na listagem, que tem abas de conferência — **Sem Diretores**, **Sem Secretários**, **Sem Coordenadores**, **Sem Pedagogos** — para achar o que ainda falta preencher.

**Etapa 2 — atribuir os perfis**

4. Abra a diretoria. A ficha é um caderno de abas, uma por área: **Direção**, **Coordenação Acadêmica**, **Secretaria Acadêmica**, **Formatura/Diplomas**, **Atividades Extensão**, **Ensino a Distância** e **Outras Atividades**. Cada quadro mostra quantas pessoas há no perfil.

   ![Ficha da diretoria, com as abas por área](usuario/diretoria-ficha.webp)

5. Na aba da área, clique em **Adicionar &lt;perfil&gt;** (por exemplo, **Adicionar Diretor Geral**).
   ![Aba Direção da diretoria](usuario/diretoria-direcao.webp)

6. No popup, informe o **Usuário** (busque por nome ou matrícula) e clique em **Salvar**.

   ![Popup de vínculo de perfil](usuario/diretoria-vinculo.webp)

**Resultado:** *"Usuário adicionado com sucesso."* A pessoa passa a ter o perfil **com escopo no setor da diretoria** — ela enxerga os cursos, turmas e alunos daquela diretoria, não os do campus vizinho.

A ficha oferece dezoito perfis, distribuídos entre as sete abas: Diretor Geral · Diretor Acadêmico · Coordenador de Curso · Coordenador de Modalidade de Ensino · Pedagogo · Apoio Acadêmico · Secretário Acadêmico · Auxiliar de Secretaria Acadêmica · Estagiário · Coordenador de Registros Acadêmicos · Organizador de Formatura · Organizador de Minicurso · Bibliotecário · Coordenador de Laboratório · Coordenador de Desporto · Coordenador de Estágio Docente · Comissão de Horários · Assessor EAD. Cada quadro traz o botão **Adicionar &lt;perfil&gt;** e o popup é sempre o mesmo.

Na diretoria do tipo **Sistêmica** aparecem ainda os dois perfis de alcance nacional: o **Diretor de Avaliação e Regulação do Ensino**, na aba *Direção*, e o **Operador ENADE**, em *Outras Atividades* — são eles que executam a tarefa 17.

O **Coordenador de Registros Acadêmicos** (aba *Formatura/Diplomas*) é o único que pede mais que o usuário: o popup cobra também o **Número da Portaria** que o designou, e é esse cadastro que a emissão de diploma (tarefa 16) exige.

![Popup do responsável pela emissão do diploma](usuario/diretoria-portaria.webp)

---

### 2. Cadastrar um curso, da estrutura à matriz

**Quem pode:** Administrador Acadêmico.
**Quando usar:** ao criar um curso novo no campus. São cinco etapas, e o SUAP avisa a cada salvamento qual é a próxima.

**Etapa 1 — a estrutura de curso (o regulamento)**

1. Em **Ensino › Cursos, Matrizes e Componentes › Estruturas de Curso**, clique em **Adicionar Estrutura de Curso**.
2. Preencha o formulário — é o mais longo do módulo, com blocos de *critérios* (apuração de resultados, avaliação por disciplina, frequência, jubilamento, trancamento, cancelamento, matrícula), *IRA*, *fechamento de período*, *configurações de diário*, *aproveitamento*, *plano de estudo*, *plano de ensino* e *representações conceituais*. Os campos que decidem o comportamento do curso inteiro:

   | Campo | O que informar |
   | --- | --- |
   | Tipo de Avaliação | **Seriado**, **Crédito**, **FIC** ou **Modular** — define se o aluno anda por períodos fechados ou por disciplinas isoladas, e é o que habilita pré e co-requisitos |
   | Critério de Avaliação | **Nota** ou **Conceito** — no conceito, o professor lança letras em vez de números, e a faixa de cada letra é definida em *Representações Conceituais*, no fim deste mesmo formulário |
   | Média para passar sem prova final / não reprovar direto / aprovação após avaliação final | As três notas de corte que o SUAP usa para decidir a situação do aluno em cada disciplina |
   | Percentual Mínimo de Frequência | Abaixo dele o aluno reprova por falta |
   | Forma de Cálculo | Como as notas dos componentes viram a média do período |
   | Número Máximo de Matrículas em Períodos / de Reprovações | Os limites de jubilamento |
   | Requer submissão de plano de ensino | Liga o ciclo da tarefa 6 para os diários deste curso |
   | Permitir fechamento com pendência | Autoriza a entrega da etapa final com aluno sem nota (ver tarefa 7) |

   ![Formulário da estrutura de curso](usuario/estrutura-formulario.webp)

3. Clique em **Salvar**.

**Etapa 2 — os componentes (as disciplinas)**

4. Em **Ensino › Cursos, Matrizes e Componentes › Componentes**, clique em **Adicionar Componente**.

   ![Listagem de componentes](usuario/componente-listagem.webp)

5. Informe **Descrição**, **Descrição no Diploma e Histórico**, **Abreviatura**, **Tipo do Componente**, **Diretoria**, **Nível de ensino** e a carga horária (**Hora/relógio**, **Hora/aula**, **Qtd. de créditos**). Clique em **Salvar**.

   ![Formulário do componente](usuario/componente-formulario.webp)

**Resultado:** o componente ganha uma **sigla** gerada pelo SUAP (por exemplo `POS.0001`) — é por ela que ele aparece em todas as outras telas.

**Etapa 3 — a matriz curricular**

6. Em **Ensino › Cursos, Matrizes e Componentes › Matrizes Curriculares**, clique em **Adicionar Matriz Curricular**.
7. Preencha:

   | Campo | O que informar |
   | --- | --- |
   | Estrutura de curso | A estrutura da etapa 1 — é ela que traz todas as regras de aprovação para esta matriz |
   | Quantidade de Períodos Letivos | Quantos semestres/anos o aluno cursa |
   | PPP | O projeto pedagógico, em PDF — obrigatório |
   | Carga horária por tipo (obrigatórios, optativos, eletivos, extensão, seminários, prática profissional, TCC, atividades complementares, ATPA…) | Todas são obrigatórias, mesmo zeradas: a soma é a carga horária total exigida do aluno |
   | Configuração de AACC / ATPA / Créditos Especiais | Os tetos de aproveitamento de atividades — o que o aluno declara na tarefa 14 só é aceito dentro deles |
   | Exige TCC / Exige Estágio e Afins | Acrescentam requisitos de conclusão, cobrados na formatura (tarefa 16) |

   ![Formulário da matriz curricular](usuario/matriz-formulario.webp)

8. Clique em **Salvar**.

**Resultado:** *"Matriz cadastrada com sucesso."* A ficha da matriz abre com as abas **Criação e Carga Horária**, **Componentes curriculares**, **Pré/Co-Requisitos**, **Matriz Curricular**, **Projeto Integrador** e **Cursos e Alunos**.

![Ficha da matriz recém-criada](usuario/matriz-ficha.webp)

**Etapa 4 — vincular os componentes à matriz**

9. Na ficha da matriz, abra **Componentes curriculares** e clique em **Vincular Componente** (há também **Importar componentes**, para trazer a lista de uma vez).

   ![Aba de componentes curriculares da matriz](usuario/matriz-componentes.webp)

10. Informe:

    | Campo | O que informar |
    | --- | --- |
    | Componente | Busque pela sigla; a lista só oferece componentes do mesmo nível de ensino da matriz |
    | Periodo letivo | Em que período da matriz a disciplina é ofertada — em regime de crédito ele é apenas *sugerido* |
    | Tipo | **Regular**, **Seminário**, **Prática Profissional**, **Trabalho de Conclusão de Curso**, **Atividade de Extensão** ou **Prática como Componente Curricular** |
    | Qtd. Avaliações | Quantas etapas de nota o diário terá (**Uma** a **Quatro**) — precisa combinar com o calendário escolhido ao gerar turmas |
    | Avaliação por Conceito | Marque nos cursos avaliados por conceito |
    | Ementa | Obrigatória quando o curso exige plano de ensino |
    | Pode Fechar com Pendência | Autoriza a entrega da etapa final desta disciplina com aluno sem nota |

    ![Tela de vínculo de componente à matriz](usuario/matriz-vincular-componente.webp)

11. Clique em **Vincular Componente** (ou **Vincular Componente e continuar vinculando**, para emendar o próximo).

**Resultado:** *"Componente de matriz adicionado com sucesso."* O par componente + matriz é o que vira **diário** quando as turmas forem geradas.

Na aba **Pré/Co-Requisitos** da matriz define-se o que o aluno precisa ter cursado antes (pré-requisito) ou junto (co-requisito) — regra usada pelos cursos em **regime de crédito**, que a validam no pedido de matrícula.

**Etapa 5 — o curso**

12. Em **Ensino › Cursos, Matrizes e Componentes › Cursos**, clique em **Adicionar Curso**.

    ![Listagem de cursos](usuario/curso-listagem.webp)

13. Preencha os blocos *Identificação*, *Dados de funcionamento*, *Coordenação*, *Dados gerais*, *ENADE* e *Título do certificado de conclusão*:

    | Campo | O que informar |
    | --- | --- |
    | Código | O código do curso no campus — é ele que identifica o curso nas buscas |
    | Modalidade de Ensino | Integrado, Subsequente, Licenciatura, Especialização… |
    | Diretoria | A diretoria da tarefa 1 — define quem administra o curso |
    | Coordenador / Coordenador substituto e Nº Portaria | Quem responde pelo curso; o coordenador é quem aprova plano de ensino (tarefa 6) |
    | Periodicidade | **Anual**, **Semestral** ou **Livre** |
    | Exige Plano de Ensino | Liga o ciclo da tarefa 6 |
    | Exige ENADE e Área do curso de formação superior (código CINE) | Só para graduação: é o par que faz o curso ser alcançado pela convocação do ENADE (tarefa 17) |
    | Exige colação de grau | Acrescenta a colação aos requisitos de conclusão |
    | Códigos CENSUP / EDUCACENSO / SISTEC / e-MEC | Os identificadores do curso nos sistemas do MEC, usados nas exportações dos censos |
    | Masculino / Feminino (título) | Como o título sai impresso no diploma |

    ![Formulário do curso](usuario/curso-formulario.webp)

14. Clique em **Salvar**.

**Resultado:** *"Curso cadastrado com sucesso."* — e o SUAP já avisa que falta vincular a matriz.

15. Na ficha do curso, abra a aba **Matrizes**, clique em **Vincular Matriz**, escolha a matriz e salve.

    ![Aba Matrizes do curso](usuario/curso-ficha.webp)

    ![Popup de vínculo da matriz ao curso](usuario/curso-vincular-matriz.webp)

**Resultado:** *"Matriz adicionada com sucesso."* Só agora o curso pode gerar turmas e receber alunos.

**Para replicar em vez de cadastrar:** as fichas de matriz e de curso têm o botão **Replicar**, que copia a matriz com todos os seus componentes (ou o curso com sua configuração). É o caminho usual para criar a variante de uma matriz já em uso — por exemplo, a versão avaliada por conceito.

---

### 3. Cadastrar o calendário acadêmico do período

**Quem pode:** Administrador Acadêmico, Auxiliar de Secretaria Acadêmica, Secretário Acadêmico.
**Quando usar:** antes de gerar as turmas de cada período letivo. É o calendário que autoriza — ou barra — o lançamento de aula, nota e o fechamento do período nas datas certas.

1. No menu, acesse **Ensino › Procedimentos de Apoio › Calendários Acadêmicos** e clique em **Adicionar Calendário Acadêmico**.

   ![Listagem de calendários acadêmicos](usuario/calendario-listagem.webp)

2. Preencha:

   | Campo | O que informar |
   | --- | --- |
   | Campus e Diretoria | A quem o calendário se aplica — um campus pode ter mais de um calendário no mesmo período |
   | Tipo | **Anual**, **Semestral** ou **Livre** |
   | Ano letivo e Período letivo | O período que este calendário rege |
   | Início / Fim | O intervalo do período letivo |
   | Data de Fechamento do Período | A partir dela o SUAP fecha o período automaticamente, se não houver pendência |
   | Qtd etapas | **Etapa Única** a **Quatro Etapas** — precisa ser compatível com a *Qtd. Avaliações* dos componentes da matriz, senão o assistente de turmas recusa a combinação |
   | Início/Término de cada etapa | Delimitam quando o professor pode lançar e entregar cada etapa |
   | Início / Encerramento da Prova Final, do Trancamento e da Cert. e Aproveitamento | As janelas dos procedimentos do período |
   | Calendário de Referência? | Marque no calendário que serve de modelo para os demais |

   ![Formulário do calendário acadêmico](usuario/calendario-formulario.webp)

3. Clique em **Salvar**.

**Resultado:** *"Cadastro realizado com sucesso."*

---

### 4. Gerar as turmas e configurar os diários

**Quem pode:** Administrador Acadêmico, Secretário Acadêmico, Coordenador de Curso, Coordenador de Modalidade Acadêmica, Diretor Acadêmico e os perfis sistêmicos correspondentes. *Medido: um professor recebe "acesso negado" nesta tela.*
**Pré-condição:** curso com matriz vinculada (tarefa 2) e calendário do período (tarefa 3).

**Etapa 1 — o assistente de geração**

1. Abra o assistente **Gerar Turmas** (em **Ensino › Turmas e Diários**). Ele tem quatro passos, e cada um só monta suas opções depois do anterior.
2. **Passo 1 — dados do curso:** escolha **Ano Letivo**, **Período Letivo**, **Tipo dos Componentes** (*Obrigatório* ou *Optativo*) e **Matriz/Curso**. Clique em **Continuar**.

   ![Passo 1 do assistente de turmas](usuario/turma-assistente-1.webp)

3. **Passo 2 — turmas por período:** para cada período da matriz, informe **Nº de Turmas**, **Turno** e **Nº de Vagas**. Períodos que não terão turma ficam com zero. Clique em **Continuar**.

   ![Passo 2 do assistente de turmas](usuario/turma-assistente-2.webp)

4. **Passo 3 — horário, calendário e componentes:** escolha o **Horário do Campus**, o **Calendário Acadêmico** e marque os componentes que virarão diário. Clique em **Continuar**.

   ![Passo 3 do assistente de turmas](usuario/turma-assistente-3.webp)

5. **Passo 4 — confirmação:** o SUAP lista as turmas e os diários que serão criados ou atualizados. Marque **Confirmação** e clique em **Finalizar**.

   ![Passo 4 do assistente de turmas](usuario/turma-assistente-4.webp)

**Resultado:** *"Turmas geradas com sucesso."* Cada turma nasce com um diário por componente selecionado.

![Listagem de turmas](usuario/turma-listagem.webp)

**Etapa 2 — configurar cada diário**

6. Abra o diário em **Ensino › Turmas e Diários › Diários**. A ficha traz *Dados do diário*, *Dados complementares*, *Observações Gerais*, *Aulas* e *Professores*.

   ![Ficha do diário recém-gerado](usuario/diario-ficha.webp)

7. Clique em **Definir Local** e escolha a sala.

   ![Popup de definição de local](usuario/diario-local.webp)

8. Clique em **Definir Horário** e marque, na grade de dias × faixas de aula, os horários da disciplina.

   ![Popup de definição de horário](usuario/diario-horario.webp)

9. Clique em **Adicionar Professor**, informe o servidor, o **Tipo** (Principal, Colaborador…) e o **percentual de carga horária** dele no diário.

   ![Popup de vínculo do professor](usuario/diario-professor.webp)

**Resultado:** *"Local definido com sucesso."*, *"Horário definido com sucesso."* e *"Professor adicionado/atualizado com sucesso."* Só com professor vinculado o diário aparece em **Meus Diários** e passa a aceitar lançamentos (tarefa 7).

---

### 5. Matricular um aluno

**Quem pode:** Secretário Acadêmico — e os demais perfis com permissão de efetuar matrícula: Administrador Acadêmico, Auxiliar de Secretaria Acadêmica, Coordenador de Curso, Diretor Acadêmico, Operador de Matrícula e os sistêmicos.
**Quando usar:** para matricular quem entrou por processo seletivo, transferência ou convênio. São duas etapas: a matrícula **no curso** e a matrícula **na turma**.

**Etapa 1 — matrícula institucional**

1. No menu, acesse **Ensino › Procedimentos de Apoio › Efetuar Matrícula Direta**. O formulário tem cinco passos, e cada um só avança quando o anterior valida.
2. **Passo 1 — Identificação:** informe a **Nacionalidade** e o **CPF** (ou o **Nº do Passaporte**, para estrangeiro). O SUAP recusa CPF já cadastrado.

   ![Passo 1 da matrícula institucional](usuario/matricula-passo-1.webp)

3. **Passo 2 — Dados pessoais, familiares e endereço:** nome, sexo, data de nascimento, estado civil, filiação, responsável (para menor de idade) e endereço completo.

   ![Passo 2 da matrícula institucional](usuario/matricula-passo-2.webp)

4. **Passo 3 — Contato, necessidades específicas, transporte e escolaridade anterior:** e-mail e telefones, deficiências e outras NEEs, transporte escolar, naturalidade, raça e os dados da escola de origem.
5. **Passo 4 — Documentos:** RG, título de eleitor, carteira de reservista e certidão civil.

   ![Passo 4 da matrícula institucional](usuario/matricula-passo-4.webp)

6. **Passo 5 — Dados da matrícula:** foto do aluno e o vínculo acadêmico:

   | Campo | O que informar |
   | --- | --- |
   | Ano Letivo e Período Letivo | Em que período o aluno ingressa |
   | Matriz/Curso | O par curso + matriz — é o que define o que ele terá de cursar |
   | Turno | O turno de oferta |
   | Forma de Ingresso | Como ele entrou (ampla concorrência, cota, transferência…) — é o dado que o SUAP exporta para CENSUP e EDUCACENSO |
   | Possui Convênio / Convênio | Para matrícula amarrada a um programa |
   | Possui Orientador / Orientador / Linha de Pesquisa | Para pós-graduação |
   | Aluno Especial? | Marque para matrícula em disciplinas isoladas |

   ![Passo 5 da matrícula institucional](usuario/matricula-passo-5.webp)

7. Clique em **Finalizar Matrícula Institucional**.

**Resultado:** *"Matrícula realizada com sucesso."* O SUAP gera o **número de matrícula** e oferece o comprovante em PDF.

![Conclusão da matrícula institucional](usuario/matricula-resultado.webp)

**Etapa 2 — matricular na turma**

8. No menu, acesse **Ensino › Turmas e Diários › Turmas**, abra a turma e vá à aba **Alunos**.

   ![Aba Alunos da turma](usuario/turma-alunos.webp)

9. Clique em **Adicionar alunos**: a tela lista os alunos do curso que ainda não estão em turma, com filtro por **Turno** e **Polo**.
10. Marque quem vai entrar e clique em **Matricular Alunos Selecionados**.

    ![Tela de adicionar alunos à turma](usuario/turma-adicionar-alunos.webp)

**Resultado:** *"Aluno(s) matriculado(s) com sucesso."* O aluno passa a constar em **todos os diários da turma** — é essa matrícula em diário que dá ao professor alguém a quem lançar nota.

---

### 6. Elaborar e homologar o plano de ensino

**Quem pode:** o **Professor** preenche e submete; o **Coordenador de Curso** aprova; o **Diretor Acadêmico** homologa.
**Quando usar:** no início do período, para os diários de curso que exige plano de ensino. As três etapas acontecem na mesma tela — **Planos de Ensino** —, cada papel na sua aba.

**Etapa 1 — preencher (professor)**

1. Abra **Planos de Ensino** e a aba **Meus planos Aguardando Submissão**; clique no plano do seu diário.

   ![Listagem de planos de ensino do professor](usuario/plano-listagem.webp)

2. Preencha **Ementa**, **Justificativa**, **Objetivo Geral**, **Objetivos Específicos**, **Conteúdo Programático**, **Metodologia** e **Informações Adicionais**, e acrescente as **Referências Bibliográficas Básica e Complementar** (uma linha por referência, com a indicação de disponibilidade na biblioteca). Clique em **Salvar**.

   ![Formulário do plano de ensino](usuario/plano-formulario.webp)

**Etapa 2 — submeter (professor)**

3. Na aba **Meus planos Aguardando Submissão**, marque o plano, escolha a ação **Submeter** e clique em **Aplicar**.

   ![Ação de submissão do plano](usuario/plano-submeter.webp)

**Resultado:** *"Submissão realizada com sucesso."* O plano sai da mão do professor e entra na fila do coordenador.

**Etapa 3 — aprovar (coordenador de curso)**

4. Na aba **Aguardando Minha Aprovação**, marque o plano e aplique a ação **Aprovar** — ou **Devolver**, para que o professor ajuste.

   ![Ação de aprovação do plano](usuario/plano-aprovar.webp)

**Etapa 4 — homologar (diretor acadêmico)**

5. Na aba **Aguardando Homologação**, marque o plano e aplique **Homologar** (também há **Devolver**).

   ![Ação de homologação do plano](usuario/plano-homologar.webp)

**Resultado:** *"Homologação realizada com sucesso."* O plano passa para a aba **Homologados** e fica visível na consulta pública (ver *Para o público externo*).

---

### 7. Executar o diário: aulas, faltas, notas e entrega da etapa

**Quem pode:** Professor — e também Administrador Acadêmico, Secretário Acadêmico, Coordenador de Curso, Diretor Acadêmico e os sistêmicos, que têm as mesmas permissões de aula e nota.
**Pré-condição:** o diário está configurado e tem professor vinculado (tarefa 4), e a etapa está **em posse do professor**.

1. No menu, acesse **Ensino › Turmas e Diários › Meus Diários** e escolha o período no filtro; clique no diário.

   ![Meus diários, filtrados por período](usuario/meus-diarios.webp)

2. O diário abre na etapa corrente, com as abas **Aulas**, **Faltas**, **Notas**, **Materiais de Aula**, **Fórum de Discussão**, **Trabalhos**, **Observações** e **Estatísticas**.

   ![Diário aberto na etapa](usuario/diario-etapa.webp)

**Definir como a etapa será avaliada**

3. Clique em **Editar Configuração de Avaliação**. Escolha a **Forma de Cálculo** (*Média Aritmética*, *Média Ponderada*, *Maior Nota*, *Soma Simples*, *Soma com Divisor Informado*) e, na lista de itens, informe para cada avaliação a **sigla**, a **descrição**, o **tipo** (Prova, Seminário, Trabalho, Teste, Atividade, Exercício, Atitudinal), a **nota máxima**, o **peso** e a **data**. Salve.

   ![Configuração da forma de avaliação](usuario/forma-avaliacao.webp)

**Resultado:** *"Atualização realizada com sucesso."* Cada item vira uma coluna na planilha de notas — e a etapa só será entregue quando todas estiverem preenchidas.

**Registrar as aulas**

4. Clique em **Adicionar aula**, informe **Quantidade** (de aulas do dia), **Etapa**, **Data** e **Conteúdo**, e salve.

   ![Formulário de registro de aula](usuario/aula-formulario.webp)

**Resultado:** *"Aula cadastrada/atualizada com sucesso."* A quantidade de aulas registradas é o que conta como carga horária cumprida do diário — e é o que habilita o lançamento de falta.

**Lançar as faltas**

5. Abra a aba **Faltas**: a tela é uma grade de alunos × aulas. Digite a quantidade de faltas do aluno naquela aula e **saia do campo** — a gravação é imediata, sem botão. O SUAP recusa quantidade maior que o número de aulas do dia.

   ![Aba de faltas do diário](usuario/diario-faltas.webp)

**Lançar as notas**

6. Abra a aba **Notas**: uma coluna por avaliação configurada. Digite a nota e **saia do campo**; aparece *"Nota salva!"* e a média do aluno é recalculada na hora.

   ![Aba de notas do diário](usuario/diario-notas.webp)

**Entregar a etapa**

7. Clique em **Entregar Etapa &lt;n&gt;** e confirme.

   ![Confirmação de entrega da etapa](usuario/etapa-entrega.webp)

**Resultado:** *"Etapa entregue com sucesso."* A posse da etapa passa para o **registro escolar** e o professor não altera mais nada — para reabrir, é preciso pedir o relançamento (tarefa 8).

**Se faltar nota:** a entrega é recusada com *"A etapa só pode ser entregue quando todas as notas forem lançadas."* Depois do fim da etapa final, e apenas nas disciplinas marcadas com *Pode Fechar com Pendência*, a tela passa a oferecer **Confirmar entrega sem nota**.

**Nos cursos avaliados por conceito** a aba de notas vira **Registro de Conceitos** e aceita as letras definidas na estrutura do curso, em vez de números; o boletim do aluno mostra a mesma letra.

---

### 8. Pedir e autorizar o relançamento de uma etapa

**Quem pode:** o **Professor** pede; **Secretário Acadêmico** e **Administrador Acadêmico** deferem.
**Quando usar:** quando é preciso corrigir aula, falta ou nota de uma etapa **já entregue**.

1. No diário com a etapa já entregue, abra a solicitação de relançamento, descreva o **Motivo** e clique em **Salvar**.

   ![Formulário de solicitação de relançamento](usuario/relancamento-formulario.webp)

**Resultado:** *"Solicitação enviada com sucesso."*

2. A secretaria acompanha em **Ensino › Procedimentos de Apoio › Solicitações de Usuários**, aba **Pendentes** (a listagem também aceita **Deferir**/**Indeferir** em lote).

   ![Solicitações de usuários pendentes](usuario/solicitacoes-pendentes.webp)

3. Abra a solicitação e clique em **Deferir** (ou **Rejeitar**).

   ![Detalhe da solicitação de relançamento](usuario/solicitacao-detalhe.webp)

**Resultado:** *"Solicitação deferida com sucesso."* A posse da etapa volta para o professor, que pode lançar de novo e entregar outra vez.

---

### 9. Fechar e reabrir o período letivo

**Quem pode:** Administrador Acadêmico, Diretor Acadêmico e Secretário Acadêmico.
**Quando usar:** ao fim do período, depois que os diários foram entregues. O SUAP fecha sozinho os períodos sem pendência a partir da *Data de Fechamento do Período* do calendário; esta tarefa é para o que sobra.

1. No menu, acesse **Ensino › Procedimentos de Apoio › Fechar Período**.
2. **Passo 1:** escolha **Ano Letivo**, **Período Letivo** e o recorte — **Por Curso**, **Por Turma**, **Por Diário** ou **Por Matrícula** — e o alvo correspondente. Clique em **Continuar**.

   ![Passo 1 do fechamento de período](usuario/fechar-passo-1.webp)

3. **Passo 2:** confira a **Relação de Alunos** que o SUAP montou, marque **Confirmado** e clique em **Finalizar**. Marque também **Forçar fechamento?** para encerrar mesmo com pendência nos diários — os alunos afetados ficam com a situação em **dependência**.

   ![Passo 2 do fechamento de período](usuario/fechar-passo-2.webp)

**Resultado:** o processamento roda em segundo plano e a tela mostra o andamento da tarefa. Ao terminar, as matrículas do período saem de *matriculado* para a situação apurada, e nasce a matrícula do período seguinte — que é o que habilita a renovação (tarefa 11).

![Acompanhamento da tarefa de fechamento](usuario/fechar-resultado.webp)

**Para desfazer:** **Ensino › Procedimentos de Apoio › Reabrir Período** tem os mesmos dois passos e o mesmo recorte, e devolve as matrículas à situação *matriculado*, liberando ajuste de nota e falta.

![Reabertura de período: seleção](usuario/reabrir-passo-1.webp)

![Reabertura de período: confirmação](usuario/reabrir-passo-2.webp)

---

### 10. Corrigir um lançamento depois da etapa entregue

**Quem pode:** Secretário Acadêmico, Administrador Acadêmico, Auxiliar de Secretaria Acadêmica, Coordenador de Curso, Diretor Acadêmico e os sistêmicos.
**Quando usar:** quando a correção é da própria secretaria e não vale a pena devolver o diário ao professor. Quem escreve no diário é quem está **de posse** da etapa, não quem tem o cargo mais alto.

1. Abra o diário em **Ensino › Turmas e Diários › Diários** e clique em **Transferir para o Registro**.

   ![Diário visto pela secretaria](usuario/diario-secretaria.webp)

**Resultado:** *"Posse transferida com sucesso"*. A etapa passa para o registro escolar.

2. Para aula e falta, use **Registro de aula/falta** — mesma grade da tarefa 7, com **Adicionar aula** e a chamada por aluno.

   ![Registro de aula e falta pela secretaria](usuario/registro-chamada.webp)

3. Para nota, abra a aba **Registro de Notas** do diário e digite na planilha, saindo do campo para gravar.

   ![Registro de notas pela secretaria](usuario/nota-registro.webp)

4. Terminada a correção, clique em **Transferir para o Professor** para devolver a etapa.

**Resultado:** *"Posse transferida com sucesso"*. Sem esta devolução o professor continua sem poder lançar nada.

---

### 11. Renovar a matrícula para o período seguinte

**Quem pode:** a janela é aberta e processada por Secretário Acadêmico, Administrador Acadêmico, Coordenador de Curso, Diretor Acadêmico e os sistêmicos; o pedido é feito pelo **Aluno**.
**Pré-condição:** o período anterior está fechado (tarefa 9) e as turmas do próximo período já foram geradas (tarefa 4).

**Etapa 1 — abrir a janela (secretaria)**

1. No menu, acesse **Ensino › Procedimentos de Apoio › Renovação de Matrícula** e clique em **Adicionar Renovação de Matrícula**. A listagem separa as renovações por situação: **Agendadas**, **Em Andamento**, **Aguardando Processamento**, **Processadas** e **Canceladas**.

   ![Listagem de renovações de matrícula](usuario/renovacao-listagem.webp)

2. Preencha:

   | Campo | O que informar |
   | --- | --- |
   | Ano Letivo e Período Letivo | O período **para o qual** o aluno vai se matricular |
   | Data de Início e Data de Fim | A janela em que o aluno pode pedir — fora dela a tela do aluno não abre |
   | Diretorias | Quais diretorias participam desta renovação |
   | Restringir por curso | Marque para escolher os cursos um a um (etapa seguinte) |
   | Requerer atualização do cadastro / da caracterização social | Obriga o aluno a revisar os dados antes de pedir |
   | Impedir troca de turma | Prende o aluno à turma em que já está |
   | Permitir a "solicitação"/"requerimento" de matrículas em diário extracurriculares | Autoriza o aluno a pedir disciplinas fora da sua periodização |

   ![Formulário da renovação de matrícula](usuario/renovacao-formulario.webp)

3. Clique em **Salvar**, abra a aba **Cursos** e clique em **Informar Cursos** para incluir os cursos que participam.

   ![Aba Cursos da renovação](usuario/renovacao-ficha.webp)

   ![Popup de inclusão dos cursos na renovação](usuario/renovacao-cursos.webp)

**Etapa 2 — o pedido (aluno)**

4. Dentro da janela, a tela inicial do aluno mostra o aviso **Faça sua matrícula online**.

   ![Tela inicial do aluno com o aviso de matrícula](usuario/aluno-inicio-renovacao.webp)

5. Na tela **Matrícula Online**, o aluno escolhe a **turma** oferecida e marca as **disciplinas** — as obrigatórias do período já vêm listadas — e clica em **Salvar**.

   ![Tela de matrícula online do aluno](usuario/pedido-matricula.webp)

**Resultado:** *"Pedido de matrícula salvo com sucesso."* O pedido fica **aguardando processamento**: ainda não é matrícula.

![Pedido de matrícula registrado](usuario/pedido-matricula-resultado.webp)

**Etapa 3 — processar (secretaria)**

6. Na ficha da renovação, acompanhe as abas **Cursos**, **Pendências** e **Monitoramento** e clique em **Processar Pedidos de Matrícula**.

   ![Ficha da renovação com os pedidos](usuario/renovacao-pedidos.webp)

**Resultado:** o processamento roda em segundo plano; ao terminar, cada pedido deferido vira matrícula no período e nos diários escolhidos, e o aluno passa a ver as disciplinas em **Minhas disciplinas**.

![Acompanhamento do processamento dos pedidos](usuario/processar-pedidos.webp)

---

### 12. (Aluno) Acompanhar a vida acadêmica

**Quem pode:** Aluno — cada um enxerga apenas o próprio prontuário.

1. A tela inicial reúne os atalhos do quadro **Ensino**: *Minhas disciplinas*, *Meus dados*, *Agenda de avaliações*, *Locais e horários de aula*, *Minhas justificativas de falta*, além das pendências e avisos do campus.

   ![Tela inicial do aluno](usuario/aluno-inicio.webp)

2. **Ensino › Dados do Aluno** abre o prontuário completo, com o resumo do curso, o I.R.A. e as abas **Dados acadêmicos**, **Dados pessoais**, **Pasta documental**, **Requisitos de conclusão**, **Pedidos de renovação de matrícula**, **TCC/Relatórios**, **Boletins**, **Histórico**, **Caracterização socioeconômica**, **Atividades estudantis**, **Dados bancários**, **Requerimentos**, **Justificativas de faltas**, **Nada consta**, **Documentos e processos** e **Matriz curricular**.

   ![Prontuário do aluno](usuario/aluno-dados-academicos.webp)

3. Em **Dados acadêmicos** ficam as **Matrículas em períodos** — um bloco por período cursado, com a situação apurada.

   ![Matrículas em períodos](usuario/aluno-periodos.webp)

4. Em **Histórico**, os **Componentes Curriculares** já cursados, com nota, carga horária e situação.

   ![Histórico do aluno](usuario/aluno-historico.webp)

5. Em **Requisitos de conclusão**, o que ainda falta para se formar — carga horária por tipo de componente, TCC, estágio, ENADE e colação de grau, conforme a matriz.

   ![Requisitos de conclusão](usuario/aluno-requisitos.webp)

6. **Ensino › Minhas disciplinas** mostra as disciplinas do período escolhido no filtro, com acesso ao diário de cada uma (materiais, notas e faltas lançadas).

   ![Minhas disciplinas](usuario/aluno-disciplinas.webp)

---

### 13. (Aluno) Emitir declarações e comprovantes

**Quem pode:** Aluno.

1. Em **Ensino › Dados do Aluno**, clique em **Documentos**.
2. Escolha o documento na lista — **Histórico Parcial**, **Comprovante de Dados Acadêmicos**, declaração de matrícula e demais comprovantes disponíveis para o seu vínculo.

   ![Menu de documentos do aluno](usuario/aluno-documentos.webp)

**Resultado:** o documento escolhido é gerado em PDF.

---

### 14. (Aluno) Registrar uma atividade complementar

**Quem pode:** Aluno, nos cursos cuja matriz tem configuração de AACC.
**Quando usar:** para aproveitar horas de curso, evento, monitoria ou estágio como atividade complementar.

1. Abra o formulário de **solicitação de atividade complementar** — ele fica na área do aluno, junto da aba **Atividades estudantis** do seu prontuário.
2. Informe **Ano Letivo**, **Período Letivo**, **Tipo** (a lista só traz os tipos que a configuração da sua matriz aceita), **Atividade**, **Data de Início** e **Data da Conclusão**, **Carga Horária** e anexe o comprovante.

   ![Formulário de atividade complementar](usuario/aluno-atividade-complementar.webp)

3. Clique em **Salvar**.

**Resultado:** *"Atividade complementar adicionada com sucesso."* O registro entra como **solicitação**: a carga horária só é aproveitada depois de a secretaria validar o comprovante.

![Atividade complementar registrada](usuario/aluno-atividade-resultado.webp)

---

### 15. (Aluno) Manter os próprios dados

**Quem pode:** Aluno.

**Dados pessoais e de contato**

1. Em **Ensino › Dados do Aluno**, use **Editar** para abrir a *Atualização de Dados Pessoais*: nome usual, endereço, identificadores acadêmicos (Lattes, ORCID), transporte escolar e programas sociais (NIS).
2. Clique em **Enviar**.

   ![Atualização de dados pessoais](usuario/aluno-dados-pessoais.webp)

**Resultado:** *"Dados Pessoais atualizados com sucesso."*

**Dados bancários**

3. Na aba **Dados bancários** do prontuário, escolha adicionar uma conta. Por ser informação sensível, o SUAP pede antes um **código enviado por e-mail** — informe-o e clique em **Autenticar**.

   ![Autenticação em duas etapas](usuario/aluno-dado-bancario-autenticacao.webp)

4. Informe **Banco**, **Número da Agência**, **Tipo da Conta**, **Número da Conta** e, se houver, a **Operação**. Clique em **Salvar**.

   ![Formulário de dados bancários](usuario/aluno-dado-bancario.webp)

**Resultado:** *"Dados bancários adicionado com sucesso."* É essa conta que a assistência estudantil usa para pagar auxílio.

---

### 16. Formar o aluno e emitir o diploma

**Quem pode:** o **TCC** é registrado por Secretário Acadêmico, Administrador Acadêmico ou Professor; o **modelo de documento** e o **livro de registros** são do Administrador Acadêmico; a **emissão do diploma** é do Coordenador de Registros Acadêmicos (e do Administrador Acadêmico).
**Pré-condição:** o aluno cumpriu os requisitos da matriz e teve o último período fechado.

**Etapa 1 — registrar o TCC**

1. Abra a ficha do aluno em **Ensino › Alunos e Professores › Alunos**.

   ![Ficha do aluno vista pela secretaria](usuario/aluno-ficha-secretaria.webp)

2. Na aba **TCC/Relatórios**, adicione o trabalho: **Ano/Período Letivo**, **Título**, **Resumo**, **Tipo de Trabalho** (Monografia, Dissertação, Tese, Artigo Científico, Portfólio…), **Orientador** e **Coorientadores**, os dados da **defesa** (data prevista, local, se é online) e a **banca** (Presidente, examinadores e suplentes).

   ![Formulário de TCC](usuario/tcc-formulario.webp)

**Resultado:** *"TCC / Relatório adicionado com sucesso."* Nas matrizes que exigem TCC, sem esse registro o aluno não integraliza o curso.

**Etapa 2 — preparar a emissão**

3. Em **Ensino › Diplomas e Certificados › Modelos de Documentos**, clique em **Adicionar Modelo de Documento** e informe **Descrição**, **Tipo** (*DIPLOMA/CERTIFICADO* ou *DECLARAÇÃO DE MATRÍCULA*), a **Modalidade de Ensino** a que ele se aplica e o arquivo **Template** — um `.docx` com as marcações que o SUAP substitui pelos dados do aluno.

   ![Formulário de modelo de documento](usuario/modelo-formulario.webp)

4. Em **Ensino › Diplomas e Certificados › Configurar Livros**, cadastre o livro de registros: **Campus**, **Modalidades de Ensino** abrangidas, **Nº do Livro Atual**, **Folhas por Livro**, **Nº da Folha Atual** e **Nº do Registro Atual**. O SUAP incrementa esses contadores a cada diploma emitido.

   ![Formulário do livro de registros](usuario/livro-formulario.webp)

**Etapa 3 — emitir**

5. Em **Ensino › Diplomas e Certificados › Emitir diploma**, informe o **Aluno** e clique em **Continuar**. Para uma turma inteira, use **Emitir diploma em lote**.

   ![Tela de emissão de diploma](usuario/diploma-emitir.webp)

**Onde acompanhar:** **Ensino › Diplomas e Certificados › Registros de Emissão** lista os diplomas já emitidos, com a situação do trâmite de cada um (*Aguardando registro*, *Aguardando geração ou impressão*, *Aguardando assinatura…*) e abas por forma de assinatura — manual, eletrônica para FIC/Técnicos/Pós e eletrônica para Graduação.

![Registros de emissão de diploma](usuario/diploma-registros.webp)

> A emissão só é aceita para aluno com **todos** os requisitos cumpridos, inclusive colação de grau quando o curso a exige. Se algum requisito faltar, o SUAP recusa a seleção do aluno.

---

### 17. Convocar para o ENADE e lançar a situação dos alunos

**Quem pode:** **Operador ENADE** e **Diretor de Avaliação e Regulação do Ensino** (e o Administrador Acadêmico). São perfis **sistêmicos**, atribuídos na diretoria do tipo Sistêmica (tarefa 1).
**Pré-condição:** cursos de graduação com **Exige ENADE** marcado e **Área do curso de formação superior** (código CINE) preenchida (tarefa 2).

**Etapa 1 — o catálogo de dispensas**

1. Em **Ensino › Cadastros Gerais › Justificativas de Dispensa do ENADE**, clique em **Adicionar Justif. de Dispensa do ENADE**, informe a **Descrição** e marque **Ativo**.

   ![Cadastro de justificativa de dispensa](usuario/enade-justificativa.webp)

**Etapa 2 — criar a convocação**

2. Em **Ensino › Procedimentos de Apoio › Convocações do ENADE**, clique em **Adicionar Convocação do ENADE**.

   ![Listagem de convocações do ENADE](usuario/enade-listagem.webp)

3. Preencha o recorte — é ele que decide quem participa:

   | Campo | O que informar |
   | --- | --- |
   | Tipo de convocação | **Avaliação teórica** ou **Avaliação prática** |
   | Ano letivo | O ano do exame |
   | Situações convocadas | Em que situação de matrícula o aluno precisa estar (*Matriculado*, *Matrícula Vínculo Institucional*) |
   | Modalidades convocadas | As modalidades de ensino alcançadas |
   | Áreas de cursos de formação superior | As áreas CINE convocadas pela portaria — junto com a modalidade, é o que seleciona os cursos |
   | Data limite para inscrição de ingressantes / de concluintes | Os prazos da portaria |
   | Edital e Portaria | Os documentos que embasam a convocação |

   ![Formulário da convocação do ENADE](usuario/enade-formulario.webp)

4. Clique em **Salvar**.

**Resultado:** *"Cadastro realizado com sucesso."* O SUAP monta a lista de cursos alcançados e cria um bloco de critérios **por modalidade**. A ficha da convocação traz as abas **Quadro de convocados**, **Possíveis integralizados**, **Possíveis concluintes**, **Quadro de não convocados** e **Documentos**.

![Ficha da convocação](usuario/enade-ficha.webp)

5. Ainda na ficha, edite os critérios da modalidade para informar a **Data de realização da prova** (e, na avaliação prática, as faixas de percentual de curso integralizado que separam ingressante de concluinte). Sem a data, o lançamento de situação é recusado.

   ![Critérios de convocação da modalidade](usuario/enade-modalidade.webp)

**Etapa 3 — processar a lista de convocados**

6. Use **Atualizar Lista de Convocados**, opcionalmente filtrando por **Curso** — em branco, processa todos os cursos da convocação.

   ![Atualização da lista de convocados](usuario/enade-processar.webp)

**Resultado:** o processamento roda em segundo plano e cria um registro de convocação por aluno apto, separado em **Ingressante** e **Concluinte**.

**Etapa 4 — lançar a situação de cada aluno**

7. Abra a lista de convocados do curso. Ali estão as ações de conferência: **Adicionar aluno avulso**, **Excluir registros selecionados**, **Reprocessar convocações**, **Enviar mensagem** e **Exportar**.

   ![Convocados de um curso](usuario/enade-convocados.webp)

8. No registro do aluno, lance a **Situação**: **Regular**, **Irregular** ou **Dispensado**. A dispensa exige a **Justificativa de Dispensa** da etapa 1 — e justificativa sem dispensa também é recusada.

   ![Lançamento da situação no ENADE](usuario/enade-situacao.webp)

**Resultado:** *"Lançamento do ENADE realizado com sucesso."* Para desfazer, use a remoção da situação (*"Situação do ENADE removida com sucesso."*), que devolve o aluno para *convocado, sem resultado*.

Toda mudança fica registrada: o log do registro de convocação mostra o que mudou, quando e por quem.

![Log do registro de convocação](usuario/enade-log.webp)

---

## Para o público externo

Fluxo aberto, sem login no SUAP.

### Consultar os planos de ensino homologados

1. Acesse a consulta pública de planos de ensino (endereço `/edu/planoensino_public/`), nos **Serviços de Acesso Público** do SUAP.
2. Filtre por **Ano Letivo**, **Período Letivo**, **Campus**, **Curso** e **Componente**, e clique em **Filtrar**.

**Resultado:** a lista traz apenas os planos **homologados** (tarefa 6), com o PDF de cada um.

![Consulta pública de planos de ensino](usuario/plano-publico.webp)

---

## Telas de apoio

Tabelas consultadas pelos formulários deste módulo. Todas seguem o mesmo padrão do SUAP — listar, adicionar, editar, remover — e não têm passo a passo próprio.

Em **Ensino › Cadastros Gerais** (50 telas): Atividade Extra · Cartórios · Catálogo de cursos técnicos · Cidades · Classificações Complementares de Componente Curricular · Convênios · Cursos de formação superior · Diretorias Acadêmicas · Disciplinas do Professor · Eixos Tecnológicos · Escolas · Formas de Ingresso · Grupos de Arquivos Obrigatórios · Grupos de Atuação · Habilitações · Instituições de Ensino Superior · Justificativas de Dispensa do ENADE · Laboratórios · Linhas de Pesquisa · Modalidades de Ensino · Modalidades de prática profissional · Motivos de Afatamento de Sala de Aula · Motivos para Ausência Escolar · NEEs (Deficiências, Outras NEEs) · Naturezas de Participação · Níveis de Ensino · Núcleo Central Estruturante · Núcleos · Parecer de Aproveitamento de Estudo · Programas · Situações de Matrícula · Situações de Matrícula no Período · Tipos de Arquivos da Pasta Documental · Tipos de Componente · Tipos de Instituições Estrangeiras · Tipos de Medidas Disciplinares · Tipos de Nada Consta · Tipos de Polo · Tipos de Premiações · Tipos de Professor em Diário · Tipos de atividades complementares · Tipos de atividades curriculares de extensão · Tipos de atividades docente · Tipos de atividades teórico-práticas de aprofundamento · Turnos · Vínculos dos Professores EAD · Áreas Capes · Áreas de Concentração · Áreas de Cursos · Áreas de Cursos de formação superior · Órgão Emissor RG.

Em **Ensino › Cursos, Matrizes e Componentes**, além do que a tarefa 2 usa: Configurações AACCs · Configurações ATPAs · Configurações de Créditos Especiais · Cursos FIC < 160h · Equivalência de Componentes · Equivalência Q-Acadêmico.

Em **Ensino › Procedimentos de Apoio**, os procedimentos pontuais que reaproveitam telas já descritas: Alterar Matriz em Lote · Atividades complementares · Atividades Curriculares de Extensão · Atividades de prática profissional · Atividades Teórico-Prática de Aprofundamento · Atualizar Fotos em Lote · Colação de Grau · Configuração de Nada Consta · Efetuar Matrícula por Processo Seletivo · Evasão em Lote · Horário do Campus · Importação Q-Acadêmico · Justificar Faltas · Matrícula de Ingressantes em Turma · Mensagens para Responsável de Aluno · Nada Consta · Pedidos de Matrícula · Planos de Estudo · Pré-Matricula Internacional · Requerimentos.

Em **Ensino › Relatórios** (20 telas), todas com o mesmo desenho — escolha os filtros, clique em enviar, leia o quadro de resultados ou exporte: Boletins · Carteira de Estudante (Relatório STTU) · Coordenação de Cursos · Disciplinas EAD · Exportar Dados de Aluno e Caracterização Social · Histórico Escolar · Listagem de Alunos · Listagem de Alunos com Conflitos de Horários · Listagem de Dependências/Reprovados · Listagem de Diários · Listagem de Horários · Listagem de Horários (Atividades Específicas) · Listagem de Professores · Migração do Q-Acadêmico · Relatório EAD · Relatório ISF · Relatório de Alunos Menores de Idade sem CPF do Responsável · Relatório de Faltas · Relatório de Períodos Não-Fechados · Relatório de Requerimentos · Relatório de TCCs.

> **Horário do Campus** merece nota: é ele que define as faixas de aula (número, turno, início e término) oferecidas ao configurar o diário na tarefa 4. Sem um horário cadastrado, o assistente de turmas não avança.

---

## O que este guia ainda não cobre

O menu do Ensino tem 205 entradas, e as tarefas acima descrevem a espinha dorsal do módulo. Os subsistemas abaixo têm telas próprias e ficaram de fora — cada um merece um guia seu:

**EAD** (Polos, Ofertas EAD, Rateios, Atividades dos Polos, Horários de Atendimento) · **Censos e dados do MEC** (CENSUP, EDUCACENSO, SISTEC, PNP, Auditorias) · **Certificados ENEM** (configurações, solicitações e registros de emissão) · **NAPNE** (acolhimentos, apoios especializados, sugestões de recursos) · **Programa Pé de Meia** · **Seguro de Aula de Campo** · **Requerimentos e Nada Consta** · **Atas Eletrônicas de projeto final** · **Migração de dados do Q-Acadêmico** · **Plano de Oferta (Cenários)** · **Regulação/Credenciamento** · **Projetos Integradores** · **Estágios Docentes** · **Comunicador** (mensagens para alunos) · **Painel de Controle** e **Indicadores/Quantitativo de Alunos**.
