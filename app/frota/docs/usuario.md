# Frota

Administra a frota da instituição: o cadastro de viaturas e máquinas, a solicitação e a avaliação das viagens, o registro da saída e da chegada, os abastecimentos, os serviços e revisões, e os relatórios de consumo e deslocamento.

O ciclo que organiza o módulo é o da viagem: alguém da unidade **solicita** a viagem, a coordenação da frota **avalia e defere** escolhendo a viatura e os motoristas, e o registro de **saída e chegada** encerra o percurso. É essa cadeia que alimenta os relatórios de quilometragem, consumo e viagens por campus — e é ela que as tarefas deste guia percorrem, na ordem em que acontece.

**Quem usa este módulo**

| Perfil | O que faz aqui |
| --- | --- |
| Coordenador de Frota Sistêmico | Administra a frota de toda a instituição: cadastros, avaliação dos agendamentos, viagens, abastecimentos e serviços |
| Coordenador de Frota | O mesmo, restrito às viaturas e aos agendamentos do seu campus |
| Agendador de Frota | Solicita as viagens da sua unidade |
| Operador de Frota | Cadastra viaturas e lança a rotina operacional — viagens, abastecimentos e serviços |
| Motorista | Aparece na lista de motoristas disponíveis da avaliação e registra a saída e a chegada quando tem a permissão |
| Servidor | Aparece como passageiro dos agendamentos e das viagens |

---

## Antes de começar

Os formulários deste módulo consomem cadastros de apoio que precisam existir: **Modelos de Viaturas** (marca, modelo, tipo e espécie do veículo), **Grupo** da viatura, **Situação**, os **Combustíveis** e o número do **Patrimônio** no inventário. Numa instituição já em operação eles estão preenchidos — se um campo aparecer vazio no formulário, é um desses que falta.

Duas regras que valem para o módulo inteiro:

- **A viatura pertence a um campus.** Ao avaliar um agendamento, só são oferecidas as viaturas **do campus do solicitante** e que não estejam escaladas em outra viagem no mesmo período — o mesmo vale para os motoristas. Se a viatura que você esperava não aparece na lista, é uma dessas duas razões.
- **A Lotação é a capacidade máxima de ocupantes incluindo o motorista.** O sistema recusa o deferimento quando o número de passageiros passa da lotação da viatura escolhida.

---

## Tarefas

### 1. Cadastrar uma viatura

**Quem pode:** Coordenador de Frota, Coordenador de Frota Sistêmico e Operador de Frota.

**Quando usar:** quando a instituição incorpora um veículo à frota. É o primeiro elo da cadeia: sem viatura cadastrada não há o que agendar.

1. No menu, acesse **Administração › Frota › Cadastros › Viaturas**.

   ![Listagem de viaturas](usuario/viaturas-listagem.webp)

2. Clique em **Adicionar Viatura**.
3. Preencha o formulário. Os campos que mudam o comportamento do módulo:

   | Campo | O que informar |
   | --- | --- |
   | Patrimônio | O número do bem no inventário; é o que liga a viatura ao patrimônio |
   | Grupo | A categoria da viatura (por exemplo, Carro de Passeio) |
   | Combustíveis | Um ou mais — o abastecimento só aceita os combustíveis marcados aqui |
   | Lotação | O máximo de ocupantes **incluindo o motorista** |
   | Tanque | A capacidade do tanque em litros; limita a quantidade de cada abastecimento |
   | Rendimento Estimado | O consumo em km/l, usado nos relatórios de consumo |
   | Prazo (em meses) e Quantidade de quilômetros (km) para a próxima revisão | Os parâmetros da revisão programada, usados em **Revisão/Serviço de Viatura › Controle das Revisões** |
   | Situação | A situação atual da viatura (por exemplo, Ativa) |

   ![Formulário de cadastro da viatura](usuario/viatura-formulario.webp)

4. Clique em **Salvar**.

**Resultado:** aparece *"Cadastro realizado com sucesso."* e a viatura passa a constar na listagem e a ser oferecida na avaliação dos agendamentos do seu campus.

![Detalhe da viatura cadastrada](usuario/viatura-detalhe.webp)

---

### 2. Cadastrar um motorista temporário

**Quem pode:** Coordenador de Frota e Coordenador de Frota Sistêmico.

**Quando usar:** para habilitar alguém que não pertence ao quadro de motoristas a dirigir uma viagem. Sem esse cadastro, a pessoa não aparece em **Motoristas Disponíveis** na avaliação.

1. No menu, acesse **Administração › Frota › Motoristas Temporários**.

   ![Listagem de motoristas temporários](usuario/motoristas-listagem.webp)

2. Clique em **Adicionar Motorista**.
3. Informe a **Pessoa**, a **Portaria** e o **Ano da Portaria** que autoriza a condução, e a **Data Inicial** da validade. Deixe a **Data Final** em branco quando a portaria não tiver prazo de validade.

   ![Formulário do motorista temporário](usuario/motorista-formulario.webp)

4. Clique em **Salvar**.

**Resultado:** aparece *"Cadastro realizado com sucesso."*. A tela de motoristas permite filtrar por **Campus**, **Categoria** e **Disponibilidade** para conferir quem está habilitado:

![Motorista localizado no filtro](usuario/motoristas-resultado.webp)

---

### 3. Solicitar um agendamento de viagem

**Quem pode:** Agendador de Frota, Coordenador de Frota, Coordenador de Frota Sistêmico e Operador de Frota.

**Quando usar:** ao planejar uma viagem da sua unidade. A solicitação nasce pendente e depende da avaliação da coordenação (tarefa 4).

1. No menu, acesse **Administração › Frota › Agendamentos**.

   ![Listagem de agendamentos](usuario/agendamentos-listagem.webp)

2. Clique em **Adicionar Agendamento de Viagem**.
3. Preencha o formulário. O essencial:

   | Campo | O que informar |
   | --- | --- |
   | Objetivo e Itinerário | Para que é a viagem e qual o trajeto previsto |
   | Saída e Chegada | Data e hora previstas de saída e de chegada |
   | Nome e Telefone do Responsável | Quem responde pela viagem |
   | Passageiros | Os servidores e alunos que viajarão |
   | Local de Saída | De onde a viatura sai |
   | Turma, Diário e Alunos | Atalhos para incluir uma turma inteira como passageiros |
   | Termo de Responsabilidade | O texto do termo e a marcação de aceite, quando a instituição exigir |

   ![Formulário do agendamento de viagem](usuario/agendamento-formulario.webp)

4. Clique em **Salvar**.

**Resultado:** aparece *"Cadastro realizado com sucesso."* e o agendamento fica na fila de avaliação da coordenação da frota.

---

### 4. Avaliar o agendamento da viagem

**Quem pode:** Coordenador de Frota e Coordenador de Frota Sistêmico.

**Quando usar:** depois de recebida a solicitação. É aqui que a viagem ganha viatura e motorista — sem o deferimento não existe viagem para registrar.

**Pré-condição:** a viatura e o motorista precisam estar cadastrados (tarefas 1 e 2).

1. No menu, acesse **Administração › Frota › Agendamentos** e abra a aba **Agendamentos Futuros**.
2. Na linha do agendamento, clique em **Avaliar**.

   ![Agendamentos futuros na fila de avaliação](usuario/agendamentos-futuros.webp)

3. Confira os **Dados do Agendamento** e a **Disponibilidade de Viaturas** (o gráfico marca em vermelho o que já está comprometido no período).
4. No **Formulário de Avaliação**, escolha a **Situação** — **Deferida** para autorizar, ou **Indeferida** para recusar —, a **Viatura** e os **Motoristas Disponíveis**. Use **Local de Saída** e **Observações** para complementar.

   ![Formulário de avaliação do agendamento](usuario/agendamento-avaliacao.webp)

5. Clique em **Salvar**.

**Resultado:** aparece *"Agendamento avaliado com sucesso."* e o agendamento deferido passa a aparecer na fila de registro de saída.

---

### 5. Registrar a saída e a chegada da viagem

**Quem pode:** Coordenador de Frota, Coordenador de Frota Sistêmico e Operador de Frota; a tela também é liberada pela permissão específica de registrar saída e chegada, concedida por padrão aos perfis **Servidor**, **Prestador de Serviço** e **Usuário Externo** — é por ela que o próprio motorista registra o percurso.

**Pré-condição:** o agendamento precisa estar deferido (tarefa 4).

**Etapa 1 — registrar a saída**

1. No menu, acesse **Administração › Frota › Viagens › Registrar Saída**. Use o link **Todas as Viaturas** para enxergar a fila do campus inteiro e não só as suas viagens.

   ![Viagens agendadas aguardando saída](usuario/viagens-agendadas.webp)

2. Na linha da viagem, clique em **Registrar Saída**.
3. Informe a **Data e Hora** da saída, confirme a **Viatura** e o **Odômetro** (a quilometragem no momento da saída). Os **Motoristas Disponíveis**, os **Passageiros**, a **Turma**, o **Diário** e os **Alunos** já vêm do agendamento.

   ![Formulário de registro da saída](usuario/viagem-saida-formulario.webp)

4. Clique em **Salvar**.

**Resultado:** aparece *"Viagem iniciada com sucesso."* e a viagem sai da fila de agendadas e entra em **Viagens Iniciadas**.

**Etapa 2 — registrar a chegada**

5. Acesse **Administração › Frota › Viagens › Registrar Chegada**.

   ![Viagens iniciadas aguardando chegada](usuario/viagens-iniciadas.webp)

6. Na linha da viagem, clique em **Registrar Chegada**, informe a **Data e Hora** e o **Odômetro** final e clique em **Salvar**.

   ![Formulário de registro da chegada](usuario/viagem-chegada-formulario.webp)

**Resultado:** aparece *"Viagem finalizada com sucesso."* e a viagem fica disponível na tela **Viagens**, com os dados gerais e o botão **Editar Viagem**:

![Viagem finalizada](usuario/viagem-detalhe.webp)

---

### 6. Registrar o abastecimento de uma viatura

**Quem pode:** Coordenador de Frota, Coordenador de Frota Sistêmico e Operador de Frota.

**Quando usar:** a cada abastecimento, para o consumo entrar nos relatórios.

1. No menu, acesse **Administração › Frota › Ordens de Abastecimento › Viaturas**.

   ![Listagem de ordens de abastecimento](usuario/abastecimentos-listagem.webp)

2. Clique em **Adicionar Ordem de Abastecimento de Viatura**.
3. Informe a **Data**, a **Viatura**, o **Combustível** (só aparecem os combustíveis marcados no cadastro da viatura), o **Odômetro**, a **Quantidade** e o **Valor Total da Nota Fiscal (R$)**, mais o **Cupom Fiscal** quando houver. Quantidade e valores usam vírgula decimal, como `40,00`.

   ![Formulário da ordem de abastecimento](usuario/abastecimento-formulario.webp)

4. Clique em **Salvar**.

**Resultado:** aparece *"Cadastro realizado com sucesso."*. A **Quantidade** não pode passar da capacidade do **Tanque** informada no cadastro da viatura — o sistema recusa e avisa *"Valor supera a capacidade do tanque da viatura."*.

---

### 7. Registrar um serviço (revisão ou manutenção) da viatura

**Quem pode:** Coordenador de Frota, Coordenador de Frota Sistêmico e Operador de Frota.

**Quando usar:** ao levar a viatura para revisão, manutenção, conserto de problema ou depois de um acidente.

1. No menu, acesse **Administração › Frota › Revisão/Serviço de Viatura › Serviços e Revisões**.

   ![Listagem de serviços e revisões](usuario/servicos-listagem.webp)

2. Clique em **Adicionar Serviço**.
3. Informe a **Data**, a **Viatura**, o **Odômetro** e o **Tipo de Serviço** — **Manutenção Periódica**, **Problema de Funcionamento**, **Acidente** ou **Outro**. Anexe a **Nota Fiscal dos Serviços**, que é obrigatória, e a **Nota Fiscal das Peças**, quando houver, com os respectivos valores.

   ![Formulário do serviço da viatura](usuario/servico-formulario.webp)

4. Clique em **Salvar**.

**Resultado:** aparece *"Cadastro realizado com sucesso."*. O serviço passa a constar na listagem — que exporta para planilha e permite baixar as notas fiscais dos serviços selecionados — e alimenta o **Controle das Revisões**, que aponta as viaturas com revisão em atraso, prevista para os próximos 30 dias ou perto da quilometragem da próxima revisão.

---

### 8. Registrar uma viagem retroativa

**Quem pode:** Coordenador de Frota, Coordenador de Frota Sistêmico e Operador de Frota.

**Quando usar:** quando a viagem aconteceu e ninguém registrou o agendamento nem a saída. É o caminho para regularizar o percurso e não deixar a quilometragem fora dos relatórios.

1. No menu, acesse **Administração › Frota › Viagens › Cadastro Retroativo**.
2. Preencha o **Solicitante**, a **Saída** e a **Chegada** ocorridas, o **Objetivo**, o **Itinerário**, a **Viatura**, a **Quilometragem Inicial**, o **Local de Saída** e a **Quilometragem Final**. Informe os **Passageiros**; o campo **Agendamento** serve para vincular a viagem a uma solicitação que já exista.

   ![Formulário da viagem retroativa](usuario/viagem-retroativa-formulario.webp)

3. Clique em **Enviar** — neste formulário o botão de gravação se chama **Enviar**, e não **Salvar**.

**Resultado:** aparece *"Viagem retroativa #N cadastrada com sucesso."*, com o número da viagem, e ela passa a constar em **Viagens**.

![Viagem retroativa cadastrada](usuario/viagem-retroativa-resultado.webp)

---

## Telas de apoio

As telas abaixo seguem o padrão do SUAP — listar, adicionar, editar e remover — ou são consultas, e por isso não têm passo a passo próprio:

- **Cadastros:** Modelos de Viaturas, Máquinas, Viaturas, Tipo de Serviço de Máquina — em **Administração › Frota › Cadastros**.
- **Máquinas:** máquinas têm cadastro e ciclo próprios, com **Ordens de Abastecimento › Máquinas** e **Revisão/Serviço de Máquina › Serviços e Revisões**, nos mesmos moldes das viaturas (tarefas 6 e 7).
- **Viagens:** **Viagens** (o histórico), **Viagens por Período e Passageiro** e **Cadastro Retroativo** (tarefa 8).
- **Revisão/Serviço de Viatura:** **Controle das Revisões** — filtra por viatura, campus e situação (revisão em atraso, prevista ou por quilometragem) e é alimentado pelo **Prazo** e pela **Quantidade de quilômetros** informados no cadastro da viatura.
- **Relatórios:** Consumo Estimado por Viatura, Consumo por Máquina, Deslocamento por Viatura, Frota Atual, Viagens por Campus/Setor, Viagens por Motorista, Viagens por Solicitante, Viagens por Viatura e Viaturas por Campus — em **Administração › Frota › Relatórios**. São relatórios em tela com exportação para planilha ou PDF.
