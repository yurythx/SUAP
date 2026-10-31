# Contratos

Acompanhe os contratos da instituição: registre o instrumento, organize as parcelas, designe fiscais, vincule empenhos e registre a execução. O módulo também oferece consultas internas, relatórios e consulta pública.

## Quem usa este módulo

| Perfil | O que faz aqui |
| --- | --- |
| Gerente de Contrato ou Operador de Contrato | Cadastra contratos, organiza cronogramas, designa fiscais e vincula empenhos. |
| Fiscal de Contrato | Registra a medição das parcelas dos contratos para os quais foi designado. |
| Perfil com permissão de consultar contratos | Acompanha os contratos e seus documentos. |
| Público externo | Consulta contratos sem entrar no SUAP. |

## Antes de começar

Para cadastrar um contrato, tenha o processo, os dados da contratada e o documento do contrato. Confira também se estão disponíveis o tipo, o subtipo, a base legal e os campi envolvidos. Para vincular um empenho, a nota precisa estar disponível na pesquisa de notas de empenho.

As imagens usam pessoas, empresas e documentos fictícios. Os dados do exemplo ilustram o preenchimento; informe os dados do seu contrato.

## Tarefas

### 1. Cadastrar um contrato

**Quem pode:** Gerente de Contrato ou Operador de Contrato.

1. Abra a listagem **Contratos** e clique em **Adicionar Contrato**.

   ![Listagem de contratos com acesso ao cadastro](usuario/contratos-listagem.webp)

2. Preencha o formulário com os dados do contrato. No exemplo, foi registrado um contrato de despesa, contínuo, sem dedicação exclusiva de mão de obra.

   | Campo | Atenção no preenchimento |
   | --- | --- |
   | Número | A tela orienta o formato `99999/9999`. |
   | Processo | Pesquise pelo número e selecione o processo correspondente. |
   | Campus Gerenciador e Campi Atendidos | Informe a unidade gerenciadora e mova os campi atendidos para a lista de escolhidos. |
   | Contratada | Pesquise por nome, CPF ou CNPJ e selecione o resultado. No exemplo, a busca foi feita por CNPJ. |
   | Quantidade de Parcelas | No exemplo, duas parcelas foram previstas para organizar o cronograma depois do cadastro. |
   | Arquivo do Contrato | Envie o PDF; a tela informa limite de 10 MB. |
   | Licitação/Ano/UASG da Licitação | Use o formato `XXXXX/YYYY (AAAAAA)`, com cinco dígitos para a licitação, quatro para o ano e seis para a UASG. |

   ![Formulário de contrato preenchido](usuario/contrato-cadastro.webp)

3. Clique em **Salvar** e confira o número, as datas, a contratada e o valor na página do contrato.

**Resultado:** aparece **Cadastro realizado com sucesso.** O contrato passa a ter uma página com seus dados gerais, demonstrativo de valores e abas de acompanhamento.

![Detalhamento do contrato cadastrado](usuario/contrato-detalhamento.webp)

### 2. Organizar o cronograma e as parcelas

**Quem pode:** Gerente de Contrato ou Operador de Contrato com acesso à gestão do contrato.

**Pré-condição:** contrato cadastrado com quantidade de parcelas informada.

1. Abra o contrato e selecione a aba **Cronograma**.
2. Clique em **Criar Cronograma**, informe o **Número do Cronograma** e clique em **Salvar**.

   ![Definição do número do cronograma](usuario/cronograma-numero.webp)

3. Após a mensagem **Número de cronograma definido com sucesso. As parcelas necessitam ser geradas.**, abra novamente **Cronograma** e clique em **Gerar Várias Parcelas**.
4. Confira as datas previstas e os valores de cada parcela e clique em **Gerar Parcelas**.

   ![Conferência das parcelas antes de gerar](usuario/cronograma-gerar-parcelas.webp)

**Resultado:** aparece **Parcelas geradas com sucesso.** As parcelas ficam visíveis no cronograma. No exemplo, o contrato de R$ 12.000,00 foi dividido em duas parcelas de R$ 6.000,00, inicialmente aguardando medição.

![Cronograma com as parcelas geradas](usuario/cronograma-parcelas.webp)

### 3. Designar um fiscal

**Quem pode:** Gerente de Contrato ou Operador de Contrato com acesso à gestão do contrato.

1. Abra o contrato, selecione **Fiscais** e clique em **Adicionar Fiscal**.
2. Informe o tipo de fiscal, a portaria, a data da nomeação, o fim da vigência, o servidor e o campus. Selecione o servidor e o campus nos resultados da pesquisa.

   ![Formulário de designação de fiscal](usuario/fiscal-cadastro.webp)

3. Clique em **Salvar** e confira o servidor na aba **Fiscais**.

**Resultado:** aparece **Fiscal adicionado com sucesso.** A designação fica listada no contrato.

![Fiscal designado no contrato](usuario/fiscais.webp)

### 4. Vincular uma nota de empenho

**Quem pode:** Fiscal de Contrato, Gerente de Contrato ou Operador de Contrato com acesso à gestão dos empenhos do contrato.

1. Abra o contrato, selecione **Empenho** e clique em **Adicionar Empenho**.
2. Pesquise o número em **Nota de Empenho** e selecione o resultado. Confira os valores mostrados na pesquisa antes de continuar.

   ![Pesquisa e seleção da nota de empenho](usuario/empenho-cadastro.webp)

3. Clique em **Salvar** e confira a nota na aba **Empenho**.

**Resultado:** aparece **Empenho adicionado com sucesso.** A nota fica vinculada ao contrato e pode ser selecionada na medição.

![Nota de empenho vinculada ao contrato](usuario/empenhos.webp)

### 5. Registrar a medição de uma parcela

**Quem pode:** Fiscal de Contrato designado para o contrato, durante a vigência da designação.

**Pré-condição:** parcela gerada e empenho vinculado, como no exemplo deste guia.

1. Abra o contrato e selecione **Cronograma**.
2. Na parcela correspondente, clique em **Efetuar Medição**.
3. Confira as **Datas Efetivas de Início e Término**, informe o **Nº do Documento**, envie o **Arquivo da Medição** e selecione o **Processo** e o **Campus**. Selecione também a **Nota de Empenho** e informe o **Valor** utilizado nessa medição. No exemplo, foram mantidas as datas previstas da primeira parcela e informado R$ 6.000,00.

   ![Medição preenchida pelo fiscal](usuario/medicao-formulario.webp)

4. Clique em **Salvar** e confira a medição no cronograma.

**Resultado:** aparece **Medição realizada com sucesso.** O número do documento fiscal e o valor ficam registrados na parcela. No exemplo, o demonstrativo do contrato passou a mostrar R$ 6.000,00 executados e saldo de R$ 6.000,00.

![Medição registrada e valores atualizados](usuario/medicao-registrada.webp)

### 6. Localizar o fiscal de um contrato

**Quem pode:** Servidor.

1. Abra **Fiscais de Contrato**.
2. Selecione o **Campus**, informe a **Matrícula do Servidor** e clique em **Buscar**.
3. Confira o nome, o tipo de fiscal, a existência de contrato ativo e a quantidade de contratos.

**Resultado:** a listagem mostra os fiscais que correspondem aos filtros. No exemplo, a pesquisa retornou o fiscal designado na tarefa 3, com um contrato ativo.

![Consulta de fiscais filtrada por campus e matrícula](usuario/consulta-fiscais.webp)

### 7. Consultar pendências de documentação

**Quem pode:** Servidor.

1. Abra **Relatório de Pendências**.
2. Selecione **Filtrar por Campus** e clique em **Enviar**.
3. Confira a pendência, o contrato e os fiscais apresentados.

**Resultado:** o relatório apresenta os contratos com pendências no campus escolhido. No exemplo, indicou **Publicações do contrato não informadas**.

![Relatório de pendências do campus](usuario/relatorio-pendencias.webp)

### 8. Acompanhar os indicadores de contratos

**Quem pode:** Servidor.

1. Abra **Indicadores**.
2. Selecione **Filtrar por Campus** e **Filtrar por Ano**, e clique em **Buscar**.
3. Consulte os gráficos de despesas e de crescimento apresentados para os grupos de contratos.

**Resultado:** a tela apresenta os indicadores do campus e do ano escolhidos. No exemplo, o gráfico de despesas gerais passou a mostrar os R$ 6.000,00 registrados na medição.

![Indicadores filtrados por campus e ano](usuario/indicadores.webp)

### 9. Consultar os relatórios de acompanhamento

**Quem pode:** os perfis indicados para cada relatório abaixo.

1. Abra o relatório correspondente ao que deseja acompanhar.
2. Em **Consumo de Energia**, informe campus e ano; em **Terceirizados**, informe o campus; em **Situação dos Contratos**, informe campus e período. Nessas três telas, clique em **Enviar**. Nos relatórios de contratos a aditivar ou licitar, consulte diretamente a listagem. Em **Empenhos**, confira os filtros disponíveis na tela.
3. Confira o resultado. Uma listagem vazia indica que a consulta não retornou registros para os critérios informados.

| Relatório | Quem pode | Consulta realizada neste guia |
| --- | --- | --- |
| Contratos a serem Aditivados | Gerente de Contrato, Operador de Contrato ou Auditor | Listagem de número, contratada, vigência e termos aditivos. |
| Contratos a serem Licitados | Gerente de Contrato, Operador de Contrato ou Auditor | Listagem de contratos para acompanhamento de licitação. |
| Consumo de Energia | Fiscal de Contrato, Gerente de Contrato ou Auditor | Filtros de campus e ano. |
| Terceirizados | Fiscal de Contrato, Gerente de Contrato ou Auditor | Filtro de campus. |
| Empenhos | Fiscal de Contrato, Gerente de Contrato ou Auditor | Abertura da tela de consulta de empenhos. |
| Situação dos Contratos | Servidor | Campus e período de datas. |

**Resultado:** a consulta abre a listagem ou o relatório correspondente. No exemplo, não havia registros de consumo de energia, terceirizados ou contratos nas consultas de renovação, licitação e situação.

![Consulta de contratos a aditivar](usuario/relatorio-aditivos.webp)

![Consulta de contratos a licitar](usuario/relatorio-licitacoes.webp)

![Consulta de consumo de energia por campus e ano](usuario/relatorio-energia.webp)

![Consulta de terceirizados por campus](usuario/relatorio-terceirizados.webp)

![Tela de relatório de empenhos](usuario/relatorio-empenhos.webp)

![Consulta da situação dos contratos por campus e período](usuario/situacao-contratos.webp)

### 10. Consultar pendências de renovação e medição

**Quem pode:** Gerente de Contrato ou Operador de Contrato.

1. Abra **Notificar Pendências**.
2. Selecione o campus em **Filtrar por Campus** e clique em **Enviar**.
3. Confira as categorias **Contratos aguardando Renovação** e **Parcelas aguardando Medição** que a página apresenta.

**Resultado:** a tela apresenta as categorias de pendências do campus escolhido. Na consulta do exemplo, a página informou **Nenhum contrato encontrado**.

![Consulta de pendências de renovação e medição](usuario/notificar-pendencias.webp)

### 11. Exportar os dados dos contratos

**Quem pode:** Servidor.

1. Abra **Exportação de dados de contrato**.
2. Selecione o **Tipo do Contrato** e mova os **Campi** desejados para a lista de escolhidos. No exemplo, foram selecionados o tipo Contrato e o campus de demonstração.

   ![Filtros da exportação de contratos](usuario/exportacao.webp)

3. Clique em **Enviar** e aguarde a conclusão da tarefa.
4. Quando aparecer **Arquivo gerado com sucesso.**, clique em **Continuar** para baixar a planilha.

**Resultado:** o navegador baixa o arquivo XLS dos contratos selecionados.

![Exportação concluída com acesso ao arquivo](usuario/exportacao-resultado.webp)

### 12. Consultar o detalhamento de um contrato

**Quem pode:** perfil com permissão de consultar contratos.

1. Abra a listagem **Contratos** e localize o número desejado.
2. Na linha do contrato, clique no ícone de visualização, representado pela lupa.
3. Confira o objeto, a vigência, os valores e as abas de acompanhamento.

**Resultado:** o detalhamento do contrato selecionado é aberto.

![Consulta interna do contrato](usuario/contrato-consulta.webp)

## Para o público externo

### Consultar um contrato sem entrar no SUAP

**Quem pode:** qualquer pessoa, sem autenticação.

1. Abra a **Consulta pública de Contratos**.
2. Localize o contrato na listagem e clique no seu número.

   ![Listagem pública dos contratos](usuario/contratos-publicos.webp)

3. Confira os dados gerais, os valores executados e o saldo. A página também apresenta o acesso ao **Arquivo do contrato** e as abas de acompanhamento disponíveis.

**Resultado:** a página pública mostra o contrato selecionado sem exigir login. No exemplo, exibiu R$ 6.000,00 executados e saldo de R$ 6.000,00.

![Detalhamento do contrato na consulta pública](usuario/contrato-publico.webp)

## Telas de apoio

Os cadastros de apoio incluem **Motivos de Conclusão de Contratos**, **Subtipos de Contratos**, **Tipos de Anexos**, **Tipos de Ocorrências**, **Tipos de Verbas Salariais**, **Tipos de Contratos**, **Tipos de Documentos Comprobatórios**, **Tipos de Fiscais**, **Base Legal** e **Pré-configuração de agenda**. Sua disponibilidade depende do perfil. A tela **Rol de Responsabilidades** reúne orientações para os fiscais e acessos aos manuais do fiscal e do gestor.
