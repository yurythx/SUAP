# Saúde

O módulo Saúde organiza o atendimento de saúde de alunos e servidores: permite localizar o prontuário, abrir atendimentos por especialidade — inclusive a avaliação de saúde do aluno e os atendimentos multidisciplinares —, registrar a evolução do atendimento, manter os dados de referência, planejar ações educativas, organizar horários e consultar relatórios.

## Quem usa este módulo

| Perfil | O que faz aqui |
| --- | --- |
| Coordenador de Saúde Sistêmico | Mantém os cadastros de referência, registra atividades e ações educativas, organiza horários e consulta informações de gestão. |
| Profissionais de saúde | Abrem e registram os atendimentos da própria área: Médico, Enfermeiro, Técnico em Enfermagem, Auxiliar de Enfermagem, Fisioterapeuta, Nutricionista, Psicólogo, Odontólogo e Técnico em Saúde Bucal. |
| Assistente Social | Consulta prontuários e acompanha as pessoas atendidas. |
| Aluno | Consulta horários disponíveis e reserva o próprio atendimento. |

## Antes de começar

Os cadastros usados nas telas de atendimento precisam estar disponíveis. Entre eles estão motivos, queixas, procedimentos, tipos de atividade, categorias de exame e opções de nutrição. A pessoa que mantém esses dados deve cadastrá-los antes do primeiro atendimento que dependa deles.

As tarefas clínicas começam pela tela de prontuários. É necessário que o paciente esteja ativo e que o profissional tenha o perfil correspondente ao tipo de atendimento.

Um atendimento só pode ser fechado quando as fichas exigidas estiverem preenchidas. A própria tela mostra o que falta no quadro **Regras para fechamento**, à direita: na **Avaliação de Saúde** o fechamento exige as fichas **Exame Físico** e **Sinais Vitais**; em um **Atendimento Multidisciplinar**, ao menos um procedimento.

## Tarefas

### 1. Localizar o prontuário de um aluno ou servidor

**Quem pode:** perfil autorizado a consultar prontuários. A entrada do menu exige autorização para consultar prontuários e para atuar nessa área; na rodada de navegação, o acesso foi realizado pelo Coordenador de Saúde Sistêmico.

**Quando usar:** antes de abrir um atendimento ou consultar os dados de uma pessoa.

1. No menu, acesse **Atividades Estudantis › Saúde › Prontuários**.
2. Informe no campo **Buscar por Nome, Matrícula ou CPF** o nome, a matrícula ou o CPF da pessoa.
3. Escolha **Aluno** ou **Servidor** em **Vínculo** e clique em **Buscar**.
4. No resultado, clique em **Prontuário**.

![Tela de busca de prontuários](usuario/prontuarios-busca.webp)

![Resultado da busca por aluno](usuario/prontuarios-resultado-aluno.webp)

![Prontuário do aluno](usuario/prontuario-aluno.webp)

O mesmo procedimento foi executado para um servidor; o resultado aparece na captura abaixo.

![Resultado da busca por servidor](usuario/prontuarios-resultado-servidor.webp)

**Resultado:** o prontuário é aberto com os dados do paciente, os vínculos e as abas de exames, documentos, anexos, cartão vacinal e anotações.

### 2. Abrir e registrar um atendimento médico ou de enfermagem

**Quem pode:** profissional do grupo de atendimento médico ou de enfermagem, conforme a ação: Médico, Enfermeiro, Técnico em Enfermagem ou Auxiliar de Enfermagem. O atendimento da rodada foi aberto pelo Auxiliar de Enfermagem; os registros foram feitos pelo Técnico em Enfermagem e pelo Médico.

**Pré-condição:** o prontuário precisa estar localizado (tarefa 1).

1. No prontuário, clique em **Adicionar Atendimento Médico/Enfermagem**.
2. Na aba **Motivo do Atendimento**, clique em **Adicionar Motivo**, descreva o motivo e salve.
3. Na aba **Intervenção de Enfermagem**, clique em **Adicionar Intervenção**.
4. Selecione um ou mais procedimentos e informe a **Descrição** da intervenção. Clique em **Enviar**.
5. Com o perfil Médico, abra a aba **Anamnese**, clique em **Adicionar Anamnese**, preencha **HDA** e salve.
6. Na aba **Hipótese Diagnóstica**, use **Adicionar** no quadro **Conduta Médica**, informe a conduta e salve.
7. Clique em **Fechar**, informe a **Observação de Fechamento** e salve.

![Atendimento médico e de enfermagem](usuario/atendimento-medico-enfermagem.webp)

![Motivo do atendimento](usuario/atendimento-enfermagem-motivo.webp)

![Formulário de intervenção de enfermagem](usuario/intervencao-enfermagem-formulario.webp)

![Anamnese médica](usuario/atendimento-medico-anamnese.webp)

![Conduta médica](usuario/atendimento-medico-conduta.webp)

![Observação para fechar o atendimento](usuario/medico-enfermagem-fechamento.webp)

**Resultado:** o SUAP exibe, respectivamente, **“Atendimento registrado com sucesso.”**, **“Intervenção de enfermagem registrada com sucesso.”**, **“Anamnese registrada com sucesso.”**, **“Conduta Médica registrada com sucesso.”** e **“Atendimento fechado com sucesso.”**. O atendimento passa a aparecer como fechado.

### 3. Abrir e registrar um atendimento de fisioterapia

**Quem pode:** Fisioterapeuta.

**Pré-condição:** o prontuário precisa estar localizado (tarefa 1).

1. No prontuário, clique em **Adicionar Atendimento de Fisioterapia**.
2. Na aba **Anamnese**, clique em **Adicionar**.
3. Preencha **Anamnese** e clique em **Salvar**.
4. Clique em **Fechar**, informe a **Observação de Fechamento** e salve.

![Atendimento de fisioterapia](usuario/atendimento-fisioterapia.webp)

![Anamnese de fisioterapia](usuario/fisioterapia-anamnese.webp)

![Observação para fechar o atendimento de fisioterapia](usuario/fisioterapia-fechamento.webp)

**Resultado:** o atendimento mostra **“Anamnese registrada com sucesso.”** e, depois do fechamento, **“Atendimento fechado com sucesso.”**.

### 4. Abrir e registrar um atendimento nutricional

**Quem pode:** Nutricionista.

**Pré-condição:** o prontuário precisa estar localizado (tarefa 1).

1. No prontuário, clique em **Adicionar Atendimento Nutricional**.
2. Na aba **Motivo do atendimento**, clique em **Adicionar**.
3. Selecione o motivo e preencha **Observações**. Clique em **Salvar**.
4. Na aba **Conduta Nutricional**, use **Adicionar** no quadro **Conduta**.
5. Registre a conduta no editor de texto e clique em **Salvar**.
6. Clique em **Fechar**, informe a **Observação de Fechamento** e salve.

![Atendimento nutricional](usuario/atendimento-nutricao.webp)

![Motivo do atendimento nutricional](usuario/nutricao-motivo.webp)

![Conduta nutricional](usuario/nutricao-conduta.webp)

![Observação para fechar o atendimento nutricional](usuario/nutricao-fechamento.webp)

**Resultado:** cada registro exibe **“Atendimento registrado com sucesso.”** e o fechamento exibe **“Atendimento fechado com sucesso.”**.

### 5. Abrir e registrar um atendimento psicológico

**Quem pode:** Psicólogo responsável pelo atendimento. O acesso é específico para esse perfil e o registro deve ser feito pelo usuário responsável pelo atendimento.

**Pré-condição:** o prontuário precisa estar localizado (tarefa 1).

1. No prontuário, clique em **Adicionar Atendimento Psicológico**.
2. Na aba **Informações sobre o atendimento**, clique em **Registrar Data/Hora do Atendimento**.
3. Informe **Data/hora do atendimento** e clique em **Salvar**.
4. Na mesma aba, clique em **Adicionar**.
5. Preencha o formulário. Os campos de consequência não-óbvia são:

   | Campo | O que informar |
   | --- | --- |
   | Motivo da Chegada | A razão pela qual a pessoa procurou o atendimento. |
   | Queixa principal | Uma ou mais queixas apresentadas pela pessoa. |
   | Queixa identificada | Uma ou mais queixas identificadas durante o atendimento. |
   | Intervenção / Encaminhamento | O acolhimento, a orientação ou o encaminhamento realizado. |
   | Tipo de atendimento | A modalidade do atendimento, como **Atendimento individual**. |

6. Clique em **Salvar**.
7. Clique em **Fechar**, informe a **Observação de Fechamento** e salve.

![Atendimento psicológico](usuario/atendimento-psicologia.webp)

![Registro do motivo e das queixas psicológicas](usuario/psicologia-registro-formulario.webp)

![Registro da data e hora do atendimento](usuario/psicologia-data-hora.webp)

![Observação para fechar o atendimento psicológico](usuario/psicologia-fechamento.webp)

**Resultado:** o SUAP exibe **“Data/hora do atendimento registrada com sucesso.”**, depois **“Atendimento registrado com sucesso.”** e, ao concluir, **“Atendimento fechado com sucesso.”**.

### 6. Abrir e registrar um atendimento odontológico

**Quem pode:** Odontólogo para o registro odontológico; o Técnico em Saúde Bucal também pode abrir o atendimento odontológico quando essa ação estiver autorizada para o seu perfil. O roteiro foi executado pelo Odontólogo.

**Pré-condição:** o prontuário precisa estar localizado (tarefa 1). O odontograma é a área inicial da situação clínica; os exames e o plano são registros do atendimento.

1. No prontuário, clique em **Adicionar Atendimento Odontológico**.
2. Na aba **Situação Clínica**, no quadro **Exame Periodontal**, clique em **Adicionar**.
3. Informe a **Ocorrência**, selecione os **sextantes** correspondentes e clique em **Salvar**.
4. No quadro **Exame Estomatológico**, clique em **Adicionar**.
5. Preencha as alterações observadas e clique em **Salvar**. A tela reúne os campos abaixo:

   | Campo | O que registrar |
   | --- | --- |
   | Alteração nos lábios | Observação sobre os lábios. |
   | Alteração na língua | Observação sobre a língua. |
   | Alteração na gengiva | Observação sobre a gengiva. |
   | Alteração no assoalho | Observação sobre o assoalho bucal. |
   | Alteração na mucosa jugal | Observação sobre a mucosa jugal. |
   | Alteração no palato duro | Observação sobre o palato duro. |
   | Alteração no palato mole | Observação sobre o palato mole. |
   | Alteração no rebordo | Observação sobre o rebordo. |
   | Alteração na cadeia ganglionar | Observação sobre a cadeia ganglionar. |
   | Alteração nas tonsilas palatinas | Observação sobre as tonsilas palatinas. |
   | Alteração na ATM | Observação sobre a articulação temporomandibular. |
   | Alteração na Oclusão | Observação sobre a oclusão. |

6. Na aba **Plano de Tratamento**, clique em **Gerar Plano de Tratamento Automático**.
7. Clique em **Fechar**, informe a **Observação de Fechamento** e salve.

![Atendimento odontológico e odontograma](usuario/atendimento-odontologia.webp)

![Exame periodontal](usuario/odontologia-exame-periodontal.webp)

![Formulário do exame estomatológico](usuario/odontologia-exame-estomatologico.webp)

![Observação para fechar o atendimento odontológico](usuario/odontologia-fechamento.webp)

**Atenção:** depois de fechado um atendimento odontológico, o sistema não deixa abrir outro para a mesma pessoa nas 12 horas seguintes — a mensagem pede que se reabra o atendimento mais recente. No topo do atendimento ficam **Fechar** e **Cancelar** enquanto ele está aberto, e **Reabrir** depois de fechado (para quem tem permissão de editar a situação clínica).

**Resultado:** o SUAP exibe **“Exame periodontal registrado com sucesso.”**, **“Exame Estomatológico registrado com sucesso.”**, **“Plano de Tratamento criado com sucesso.”** e, ao concluir, **“Atendimento fechado com sucesso.”**.

### 7. Registrar a avaliação de saúde de um aluno

**Quem pode:** perfis de saúde com acesso ao prontuário. O botão **Adicionar Avaliação de Saúde** só aparece no prontuário de **aluno**, e não é oferecido ao Assistente Social.

**Quando usar:** para reunir num mesmo atendimento as fichas da avaliação do aluno — sinais vitais, antropometria, acuidade visual, exame físico, saúde bucal, nutrição e saúde mental — em vez de um atendimento de uma especialidade só.

**Pré-condição:** o prontuário precisa estar localizado (tarefa 1).

1. No prontuário do aluno, clique em **Adicionar Avaliação de Saúde**.
2. Preencha as fichas nas quais o seu perfil atua — cada aba informa os perfis que podem registrar nela (por exemplo, **Sinais Vitais** é de Médico, Enfermeiro, Técnico em Enfermagem e Auxiliar de Enfermagem).
3. Na aba **Sinais Vitais**, clique em **Adicionar**, informe **Pressão Sistólica**, **Pressão Diastólica** e **Pulsação**, e clique em **Salvar**.
4. Na aba **Exame Físico**, clique em **Adicionar**. O formulário é um checklist: responda cada pergunta de alteração com **Sim** ou **Não** e clique em **Salvar**.
5. Clique em **Fechar**, informe a **Observação de Fechamento** e salve.

![Avaliação de saúde do aluno](usuario/avaliacao-saude.webp)

![Ficha de sinais vitais](usuario/avaliacao-saude-sinais-vitais.webp)

![Observação para fechar a avaliação de saúde](usuario/avaliacao-saude-fechamento.webp)

**Resultado:** o SUAP exibe **“Avaliação biomédica gerada com sucesso.”** ao abrir o atendimento, **“Sinais Vitais registrados com sucesso.”**, **“Exame Físico registrado com sucesso.”** e **“Atendimento fechado com sucesso.”**. Os sinais vitais e o exame físico ficam vinculados a esse atendimento de avaliação de saúde.

---

### 8. Registrar um atendimento multidisciplinar

**Quem pode:** Médico, Odontólogo, Nutricionista ou Psicólogo.

**Quando usar:** quando um procedimento é realizado em conjunto por mais de uma especialidade.

**Pré-condição:** o prontuário precisa estar localizado (tarefa 1).

1. No prontuário, clique em **Adicionar Atendimento Multidisciplinar**.
2. Na aba **Procedimentos**, clique em **Adicionar**.
3. Escolha um ou mais **Procedimentos**, descreva a **Observação** se for o caso e clique em **Salvar**.
4. Clique em **Fechar**, informe a **Observação de Fechamento** e salve.

A aba **Antecedentes** reúne o histórico clínico do paciente.

![Atendimento multidisciplinar](usuario/atendimento-multidisciplinar.webp)

![Registro dos procedimentos](usuario/multidisciplinar-procedimento.webp)

![Observação para fechar o atendimento multidisciplinar](usuario/multidisciplinar-fechamento.webp)

**Resultado:** o SUAP exibe **“Atendimento Multidisciplinar gerado com sucesso.”** ao abrir, **“Atendimento multidisciplinar registrado com sucesso.”** ao salvar os procedimentos e **“Atendimento fechado com sucesso.”** ao fechar. O fechamento exige ao menos um procedimento registrado.

---

### 9. Cadastrar e localizar um registro administrativo

**Quem pode:** perfil autorizado a cadastrar registros administrativos. A verificação de permissão indica vários perfis de saúde; na rodada, o cadastro foi executado pelo Coordenador de Saúde Sistêmico.

1. No menu, acesse **Atividades Estudantis › Saúde › Registros Administrativos**.
2. Clique em **Adicionar Registro Administrativo**.
3. Preencha **Descrição** e associe uma ou mais **Atividades**. A atividade associada define em que tipo de registro o lançamento será classificado.
4. Clique em **Salvar**.
5. Na listagem, informe parte da descrição no filtro **Texto** e clique em **Filtrar**.

![Formulário de registro administrativo](usuario/registro-administrativo-formulario.webp)

![Busca de atividades de registros administrativos](usuario/atividade-registro-busca.webp)

![Registro administrativo localizado](usuario/registro-administrativo-listagem.webp)

**Resultado:** a mensagem **“Cadastro realizado com sucesso.”** aparece e o registro pode ser localizado na tabela pelos filtros.

### 10. Cadastrar uma atividade em grupo

**Quem pode:** perfil autorizado a cadastrar atividades em grupo. O roteiro foi executado pelo Coordenador de Saúde Sistêmico.

1. No menu, acesse **Atividades Estudantis › Saúde › Atividades em Grupo**.
2. Clique em **Adicionar Atividade em Grupo**.
3. Preencha o formulário. Os campos que alteram o planejamento da atividade são:

   | Campo | O que informar |
   | --- | --- |
   | Tipo | O tipo previamente cadastrado para a atividade. |
   | Atividade Sistêmica | Marque quando a atividade não estiver limitada a um campus. |
   | Campus | A unidade onde a atividade acontecerá, quando não for sistêmica. |
   | Número de Participantes | A quantidade esperada de participantes. |
   | Data de Início e Data de Término | O período, incluindo horário, em que a atividade ocorrerá. |
   | Responsáveis | As pessoas que acompanharão a atividade. |

4. Clique em **Salvar**.

![Cadastro de atividade em grupo](usuario/atividade-grupo-formulario.webp)

![Listagem de atividades em grupo](usuario/atividade-grupo-listagem.webp)

**Resultado:** a mensagem **“Cadastro realizado com sucesso.”** aparece e a atividade fica disponível na listagem.

### 11. Planejar metas e ações educativas

**Quem pode:** Coordenador de Saúde Sistêmico. O cadastro de metas exige esse perfil; o mesmo perfil executou a ação independente nesta rodada.

**Quando usar:** para planejar uma ação vinculada a uma meta ou registrar uma ação educativa independente.

1. No menu, acesse **Atividades Estudantis › Saúde › Planejamento de Ações Educativas › Metas**.
2. Para cadastrar uma meta, clique em **Adicionar Meta da Ação Educativa**.
3. Preencha **Ano de Referência**, **Objetivos**, **Descrição**, **Tipo de Indicador** e **Quantidade**. O ano e os objetivos vinculam a meta ao planejamento; o tipo de indicador define o que será medido.
4. Clique em **Salvar**.
5. Na tela das metas, clique em **Cadastrar Ação Independente** quando a ação não estiver vinculada a uma meta.
6. Preencha o nome da ação, o recurso necessário e as datas de início e término. Os campos de motivo, detalhamento, público-alvo, turno, solicitante, turma e anexo podem complementar o planejamento.
7. Clique em **Salvar**.

![Listagem de metas](usuario/metas-listagem.webp)

![Cadastro de meta da ação educativa](usuario/meta-formulario.webp)

![Cadastro de ação educativa independente](usuario/acao-independente-formulario.webp)

**Resultado:** a meta é cadastrada com **“Cadastro realizado com sucesso.”**; a ação independente é cadastrada com **“Ação cadastrada com sucesso.”**.

### 12. Manter os cadastros de referência usados nos atendimentos

**Quem pode:** Coordenador de Saúde Sistêmico — é o único perfil que recebe a permissão de cadastrar estas tabelas.

**Quando usar:** antes de disponibilizar uma opção nova nos formulários clínicos ou de nutrição.

1. No menu, acesse a categoria correspondente em **Atividades Estudantis › Saúde › Cadastros**.
2. Escolha o cadastro que será mantido e clique em **Adicionar**.
3. Informe os campos solicitados. Os campos que exigem atenção são:

   | Cadastro | Campos que merecem atenção |
   | --- | --- |
   | Vacinas | **Número de Doses**, **É de COVID-19?** e, quando houver integração, **Nome no RN+Vacina**. |
   | Tipo de Exame Laboratorial | **Categoria**, **Unidade de Medida** e **Valores de Referência**. |
   | Alimento/Bebida para Frequência de Prática Alimentar | **Valor Recomendado**, além da descrição. |
   | Pergunta de Marcador Alimentar | **Tipo de Resposta**. |
   | Opção de Resposta de Marcador Alimentar | A **Pergunta** à qual a opção ficará vinculada. |
   | Orientação Nutricional e Receita | O **Título** e a **Descrição** no editor de texto. |
   | Demais cadastros | A descrição, denominação, nome ou código apresentado no próprio formulário. |

4. Clique em **Salvar**.

![Listagem dos cadastros de apoio](usuario/cadastros-apoio-listagem.webp)

![Cadastro de vacina](usuario/cadastro-vacina.webp)

![Cadastro de tipo de exame laboratorial](usuario/cadastro-tipo-exame-laboratorial.webp)

![Cadastro de orientação nutricional](usuario/cadastro-orientacao-nutricional.webp)

Foram exercitados também os cadastros de doença, droga, método contraceptivo, dificuldade oral, procedimento de enfermagem, CID, motivo da chegada, queixa psicológica, tipo de atividade em grupo, categoria de exame laboratorial, procedimento multidisciplinar, ano de referência, objetivo da ação educativa, avaliação gastrointestinal, restrição alimentar, diagnóstico nutricional, alimento ou bebida, pergunta de marcador alimentar, motivo do atendimento nutricional, receita nutricional e opção de resposta de marcador alimentar.

**Resultado:** a mensagem **“Cadastro realizado com sucesso.”** aparece e a nova opção passa a estar disponível para os formulários que a utilizam.

### 13. Criar horários e reservar um atendimento

**Quem pode:**

- **Criar horários:** perfis de saúde e de atendimento autorizados a gerenciar a agenda — a permissão é concedida individualmente pela instituição, e não vem em nenhum perfil padrão. A rodada foi executada pelo Coordenador de Saúde Sistêmico.
- **Consultar horários:** perfil com acesso à agenda.
- **Reservar:** Aluno, para si próprio, enquanto houver horário disponível e até **12 horas** antes do atendimento.

1. Para criar horários, no menu, acesse **Atividades Estudantis › Saúde › Agenda de Atendimentos**.

![Agenda de Atendimentos](usuario/agenda-listagem.webp)

2. Clique em **Adicionar Data de Atendimento**.
3. Informe **Campus do Atendimento**, **Especialidade**, **Data Inicial**, a modalidade (**Presencial** ou **Online**), **Horário de Início**, **Horário de Término** e a **Duração de cada atendimento (em minutos)**. Informe **Data Final** somente quando quiser repetir a geração por um período.
4. Clique em **Gerar Horários**.
5. Confira os intervalos apresentados e clique em **Salvar**.

![Formulário para criar horários](usuario/agenda-formulario.webp)

![Confirmação dos horários gerados](usuario/agenda-confirmacao-horarios.webp)

6. Para consultar, selecione a especialidade e o intervalo de datas nos filtros da **Agenda de Atendimentos** e clique em **Enviar**.

![Horários de atendimento encontrados](usuario/agenda-resultado.webp)

O quadro **Atenção** no topo da agenda avisa que a solicitação do agendamento deve ser feita até 12 horas antes da data do atendimento e que o agendamento pode ser cancelado até 12 horas antes.

7. Com o usuário Aluno, marque **Somente Disponíveis**, localize um horário e clique em **Agendar**.

![Agenda com horários disponíveis](usuario/agenda-aluno-disponivel.webp)

![Agenda após reservar um horário](usuario/agenda-aluno-reservado.webp)

**Resultado:** a criação exibe **“Horário(s) de atendimento(s) registrado(s) com sucesso.”**; depois da reserva, aparece **“Horário de atendimento agendado com sucesso.”**. O horário reservado deixa de aparecer como disponível para novas reservas.

### 14. Consultar pacientes bloqueados

**Quem pode:** perfil com autorização para consultar pacientes bloqueados. A permissão é concedida a vários perfis de saúde; na rodada, a tela foi consultada pelo Coordenador de Saúde Sistêmico.

1. No menu, acesse **Atividades Estudantis › Saúde › Relatórios › Listagem de Pacientes Bloqueados**.
2. Use os filtros **Texto**, **Campus**, **Ano** e **Profissional**, conforme necessário.
3. Clique em **Filtrar**.

![Listagem de pacientes bloqueados](usuario/pacientes-bloqueados.webp)

**Resultado:** a tabela apresenta o campus, o paciente, a data até a qual o bloqueio vale e o profissional relacionado.

## Telas de apoio

Os cadastros de referência ficam em **Atividades Estudantis › Saúde › Cadastros** e seguem todos o mesmo padrão — listar, adicionar, editar e remover —, que a tarefa 12 mostra uma vez:

- **CID**, **Categorias de Exame Laboratorial**, **Tipo de Exame Laboratorial**, **Atividades de Registros Administrativos**, **Tipo de Atividade em Grupo** e **Vacinas**;
- **Doenças**, **Drogas**, **Métodos Contraceptivos**, **Dificuldades Orais**, **Sintoma**, **Procedimentos de Enfermagem**, **Procedimentos de Fisioterapia**, **Procedimentos Odontológicos** e **Procedimentos Multidisciplinares**;
- **Nutrição:** Alimento/Bebida para Frequência de Prática Alimentar, Avaliação Gastrointestinal, Diagnóstico Nutricional, Motivo do Atendimento, Orientação Nutricional, Perguntas de Marcador Alimentar, Receitas, Respostas de Perguntas de Marcador Alimentar e Restrições Alimentares;
- **Psicologia:** Motivo da Chegada, Queixa e Tipo de Atendimento;
- **Planejamento de Ações Educativas:** Ano de Referência, Metas e Objetivos;
- **Avaliação de Saúde:** em Nutrição e Alimentação (Grupo de Alimento, Tipo de Intolerância Alimentar, Tipo de Refeição), em Processo Saúde-Doença (Grupo de Medicamento, Tipo de Transtorno de Neurodesenvolvimento) e em Saúde Mental (Grupo de Atividade da Saúde Excitantes e Relaxantes).

As consultas de **Relatórios** ficam em **Atividades Estudantis › Saúde › Relatórios**: Alergias, Avaliação de Saúde, Estatísticas de Atendimentos por Curso, Indicadores de Saúde, Listagem de Atendimentos, Listagem de Atendimentos Odontológicos, Listagem de Pacientes Bloqueados (tarefa 14), Vacinas e Relatório de Atendimentos — este último com Médico/Enfermagem, Odontologia, Psicologia e Registros Administrativos.

Dentro do prontuário ainda há cartão vacinal, exames laboratoriais e de imagem, anotações interdisciplinares, documentos, anexos e encaminhamentos; na agenda, o botão **Ver Calendário** mostra os horários em calendário.
