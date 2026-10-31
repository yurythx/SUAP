# PNP

Mantém no SUAP os dados exportados da Plataforma Nilo Peçanha (PNP): a estrutura das unidades, as áreas temáticas e os eixos, os servidores e as matrículas dos alunos. A PNP usa códigos e nomes próprios; a importação cruza esses dados com os cadastros do SUAP e deixa para revisão manual apenas o que não conseguiu identificar.

## Antes de começar

Os arquivos são exportados da PNP no formato `.parquet` e têm colunas específicas por tela — a própria tela de importação informa quais são. Cada arquivo pode ter até 10 MB.

O acesso fica em **Tec. da Informação › PNP**. A ordem das importações importa: comece pelas **Estruturas**; **Áreas Temáticas** e **Eixos** são independentes. **Servidores** e **Matrículas** usam o código da estrutura para preencher esse vínculo.

Para que os vínculos sejam encontrados automaticamente, o SUAP precisa ter as unidades organizacionais, as áreas do conhecimento, os eixos tecnológicos, os servidores e os alunos com seus cursos já cadastrados.

## Tarefas

### 1. Importar as tabelas de referência da PNP

**Quem pode:** Coletor de Dados
**Quando usar:** ao receber da PNP os arquivos de estruturas, áreas temáticas e eixos de um novo período.

1. No menu, acesse **Tec. da Informação › PNP › Estruturas**.
2. Confira a listagem. As abas **Sem unidade organizacional** e **Com unidade organizacional** separam o que ainda precisa de revisão do que já foi vinculado.
3. Clique em **Importar Estruturas**.
4. Selecione o **Arquivo Parquet** exportado da PNP e clique em **Importar**.
5. Leia o relatório da tarefa: ele informa quantas estruturas foram cadastradas, quantas foram vinculadas a uma unidade organizacional e lista as que ficaram sem vínculo.
6. Repita o procedimento para as outras duas tabelas de referência.

   | Tela | Botão | Colunas do arquivo | O que a importação vincula |
   | --- | --- | --- | --- |
   | Estruturas PNP | Importar Estruturas | `codigo`, `nome` | Unidade organizacional de mesmo nome |
   | Áreas Temáticas PNP | Importar Áreas Temáticas | `codigo`, `nome` | Área do conhecimento de mesmo código CNPq |
   | Eixos PNP | Importar Eixos | `codigo`, `nome` | Eixo tecnológico de mesmo nome |

   Os subeixos não têm correspondente no SUAP e ficam sem vínculo; o relatório de eixos os lista para revisão.

**Resultado:** as três tabelas ficam disponíveis para as importações seguintes. O relatório mostra o que foi vinculado e o que precisa ser informado à mão.

![Listagem das estruturas, com as abas de vínculo](usuario/estruturas-listagem.webp)
![Tela de importação das estruturas](usuario/estruturas-importar.webp)
![Relatório da importação de estruturas](usuario/estruturas-resultado.webp)

Os relatórios de áreas temáticas e de eixos seguem o mesmo formato:

![Relatório da importação de áreas temáticas](usuario/areas-resultado.webp)
![Relatório da importação de eixos](usuario/eixos-resultado.webp)

### 2. Importar os servidores

**Quem pode:** Coletor de Dados
**Pré-condição:** estruturas da PNP importadas (tarefa 1).

1. No menu, acesse **Tec. da Informação › PNP › Servidores**.
2. Clique em **Importar Servidores**.
3. Selecione o arquivo `.parquet` com as colunas `matricula`, `nome`, `cpf`, `unidade` e `codigo_estrutura`.
4. Clique em **Importar** e leia o relatório: ele informa quantos servidores foram cadastrados, quantos foram vinculados a um servidor do SUAP e quais ficaram sem vínculo ou sem estrutura.
5. Use as abas **Sem servidor** e **Sem estrutura** para localizar o que precisa de revisão.

**Resultado:** o servidor da PNP fica ligado ao servidor do SUAP pela matrícula SIAPE — os zeros à esquerda são ignorados — e à estrutura pelo código importado. O relatório lista os servidores cuja matrícula não foi encontrada no SUAP.

![Tela de importação dos servidores](usuario/servidores-importar.webp)
![Listagem dos servidores da PNP](usuario/servidores-listagem.webp)
![Aba dos servidores sem vínculo](usuario/servidores-pendentes.webp)
![Relatório da importação de servidores](usuario/servidores-resultado.webp)

### 3. Importar as matrículas

**Quem pode:** Coletor de Dados
**Pré-condição:** estruturas da PNP importadas (tarefa 1) e alunos com seus cursos cadastrados no SUAP.

1. No menu, acesse **Tec. da Informação › PNP › Matrículas**.
2. Clique em **Importar Matrículas**.
3. Selecione o arquivo `.parquet` com as colunas `matricula`, `cpf`, `nome`, `curso`, `unidade` e `codigo_estrutura`.
4. Clique em **Importar** e leia o relatório: ele informa quantas matrículas foram importadas, quantas foram vinculadas a um aluno do SUAP e quais ficaram sem vínculo.
5. Use a aba **Sem aluno** para localizar as matrículas que precisam de revisão.

**Resultado:** a matrícula da PNP fica registrada e, quando possível, ligada ao aluno do SUAP. A matrícula da PNP não é a mesma do SUAP: a ligação é feita pelo CPF e, quando ele não basta, pelo curso e pela unidade. Quando o CPF aparece em mais de um curso, o SUAP usa a unidade e o nome do curso para decidir qual é o aluno; se ainda houver dúvida, a matrícula fica sem vínculo para revisão manual.

![Tela de importação das matrículas](usuario/matriculas-importar.webp)
![Listagem das matrículas da PNP](usuario/matriculas-listagem.webp)
![Aba das matrículas sem aluno](usuario/matriculas-pendentes.webp)
![Relatório da importação de matrículas](usuario/matriculas-resultado.webp)

### 4. Revisar e corrigir os vínculos pendentes

**Quem pode:** Coletor de Dados
**Quando usar:** depois de qualquer importação, para resolver o que o relatório deixou pendente.

1. Abra a listagem correspondente: **Estruturas PNP**, **Servidores PNP** ou **Matrículas PNP**.
2. Clique na aba da pendência.

   | Tela | Aba |
   | --- | --- |
   | Estruturas PNP | Sem unidade organizacional |
   | Servidores PNP | Sem servidor |
   | Servidores PNP | Sem estrutura |
   | Matrículas PNP | Sem aluno |

3. Localize o registro e clique no ícone de edição (lápis).
4. Informe o vínculo no campo correspondente: **Unidade Organizacional** na estrutura, **Servidor** no servidor ou **Aluno** na matrícula. No formulário do servidor, o campo **Estrutura PNP** permite completar a estrutura.
5. Clique em **Salvar**.

**Resultado:** o registro sai da aba de pendências e passa a constar na aba **Com...**. O vínculo informado à mão é preservado nas importações seguintes: uma nova importação não o desfaz nem o transfere para outro registro.

![Correção da unidade organizacional de uma estrutura](usuario/estrutura-vinculo.webp)
![Formulário de edição de um servidor sem vínculo](usuario/servidor-editar.webp)
![Servidor com o vínculo informado, antes de salvar](usuario/servidor-vinculando.webp)
![Correção do aluno de uma matrícula](usuario/matricula-vinculo.webp)

## Telas de apoio

As cinco listagens do módulo — **Estruturas PNP**, **Áreas Temáticas PNP**, **Eixos PNP**, **Servidores PNP** e **Matrículas PNP** — também permitem incluir, editar e excluir registros individualmente e exportar a listagem para XLS. Essas telas seguem o padrão do SUAP e não são detalhadas aqui. Os arquivos de importação são preparados fora do SUAP.
