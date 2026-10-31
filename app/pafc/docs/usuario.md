# PAFC — Projeto de Autorização de Funcionamento de Curso

É por aqui que a instituição conduz o processo de **autorização de um curso**: da proposta de criação (ou adequação de um curso existente) até a aprovação pelos conselhos. O **PAFC** descreve o curso — vagas, primeira oferta, equipe, docentes, instalações, laboratórios, bibliografia e matriz — e percorre as etapas de elaboração, revisão técnica, validação, análise da Pró-Reitoria e dos conselhos (Câmara, CONSEPEX e CONSUP), com a emissão dos documentos de cada etapa. O módulo também guarda os **modelos** que padronizam o documento.

**Quem usa este módulo**

| Perfil | O que faz aqui |
| --- | --- |
| Servidor | Consulta os PAFCs e, quando designado, participa da elaboração, revisão ou validação |
| Administrador de PAFC | Mantém os modelos de PAFC e acompanha as solicitações de tramitação |
| Gestão acadêmica (Administrador Acadêmico, Reitor) | Conduz a tramitação e decide as solicitações ad referendum |

---

## Tarefas

### 1. Acompanhar um PAFC

**Quem pode:** Servidor (a permissão de ver PAFCs pertence aos perfis acima — o Servidor a recebe para as propostas em que atua).
**Quando usar:** o acompanhamento do processo de autorização do curso.

1. No menu, acesse **Ensino › PAFC › PAFCs**. A listagem traz a busca por texto e filtros de **Tipo de tramitação** (Criação/Adequação), **Situação**, **Campus**, **Modelo**, **PPC**, **Vinculados a mim** (como pró-reitor, diretor, elaborador, revisor, validador, integrante da Câmara) e **Pendência de cadastro**.

   ![Listagem de PAFCs](usuario/pafc-listagem.webp)

2. Abra o PAFC pelo ícone de exibição.

   ![Página do PAFC](usuario/pafc-tela.webp)

**Resultado:** a página do PAFC mostra, no topo, a **régua de situação** (Em solicitação → Emissão da Portaria → Em elaboração → Análise preliminar → Revisão técnica → Validação → Pró-Reitoria → Câmara → CONSEPEX → CONSUP → Aprovado) e, abaixo, os quadros e abas que se completam ao longo do processo: **Dados do Curso** (vagas, primeira oferta, justificativas), **Equipe** (comissão de elaboração, revisores técnicos, validadores, colaboradores), **Servidores** (coordenador do curso, técnicos administrativos, docentes por disciplina), **Instalações e Equipamentos** (laboratórios), **Conteúdo**, **Bibliografia**, **Matrizes**, **Documentos** (com a **Ficha de Revisão Técnica** e o **Relatório da Análise Preliminar**) e o **Histórico de movimentações**. As pendências de cada etapa ficam sinalizadas nos quadros próprios.

---

### 2. Solicitar a tramitação ad referendum

**Quem pode:** o secretário dos conselhos (a tela só libera o botão para quem é) — e quem acompanha a solicitação vê na listagem **Solicitações de Tramitação Ad Referendum** (menu **Ensino › PAFC › Solicitações de Tramitação Ad Referendum**), restrita aos perfis de gestão (Reitor, Administrador Acadêmico e Administrador de PAFC).
**Quando usar:** quando o PAFC está **aguardando aprovação do CONSEPEX** (ou do CONSUP) e a reunião ainda não ocorreu — para que a aprovação siga sem depender da reunião.

1. Na página do PAFC em conselho, clique em **Solicitar tramitação Ad Referendum**.

   ![PAFC nos conselhos, com a solicitação disponível](usuario/pafc-conselho.webp)

2. No popup, informe a **Justificativa** da necessidade e salve.

**Resultado:** *"Solicitação registrada com sucesso."* — o popup fecha e a solicitação passa a constar na listagem de **Solicitações de Tramitação Ad Referendum** (PAFC, situação do PAFC na solicitação, solicitante, data e a decisão, quando houver).

![Listagem de solicitações ad referendum](usuario/ad-referendum-listagem.webp)

3. Abra a solicitação pelo ícone de exibição para acompanhar os **Dados da solicitação**.

   ![Solicitação ad referendum](usuario/ad-referendum-visualizar.webp)

---

### 3. Manter o modelo de PAFC

**Quem pode:** Administrador de PAFC (o menu **Ensino › PAFC › Configuração › Modelos de PAFC** exige ver o modelo; criar exige o perfil de administrador).
**Quando usar:** o modelo de PAFC é o gabarito que define as seções (e o texto de orientação de cada uma) dos PAFCs novos.

1. No menu, acesse **Ensino › PAFC › Configuração › Modelos de PAFC**.

   ![Listagem de modelos de PAFC](usuario/modelos-pafc-listagem.webp)

2. Abra o modelo pelo ícone de exibição (ou **Adicionar Modelo de PAFC**, para criar).

   ![Página do modelo de PAFC](usuario/modelo-pafc-tela.webp)

**Resultado:** a página do modelo mostra os **Dados gerais** (descrição, tipo de oferta, versão do modelo, ativo/inativo) e as abas **Seções** e **Conteúdos**, onde o administrador adiciona as seções do documento e o texto de orientação de cada conteúdo. **Pré-visualizar**, **Gerar minuta** e **Replicar** (criar um novo modelo a partir deste) completam as ações.

---

## Telas de apoio

Seguem o padrão do SUAP — listar, adicionar, editar, remover — e não têm passo a passo próprio.

**Ensino › PAFC › Configuração:** Mapeamentos de modalidades de ensino · Modelos de PAFC (tarefa 3).

> **Mapeamentos de modalidades de ensino** vincula as versões do modelo de PAFC às modalidades de ensino — é a tabela que o formulário do modelo consulta.
