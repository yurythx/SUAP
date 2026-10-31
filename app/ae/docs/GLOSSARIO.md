# Atividades Estudantis — Glossário

## Termos de domínio

| Termo | Definição no contexto do módulo |
|---|---|
| Caracterização socioeconômica | Conjunto vigente de dados sociais, familiares, educacionais, de trabalho, renda, saúde e acesso usado pelos programas. |
| Grupo familiar | Pessoas e rendimentos informados na inscrição caracterizada para compor a renda familiar. |
| Programa | Benefício ou iniciativa de atividades estudantis, identificado por um tipo operacional e por regras próprias. |
| Tipo de programa | Classificação operacional usada para selecionar o subtipo de inscrição/participação: alimentação, passe, trabalho, idioma ou genérico. |
| Edital | Instrumento que reúne tipos de programa e regras de uma seleção. |
| Período de inscrição | Janela temporal, por unidade e/ou programa, em que uma inscrição pode ser apresentada. |
| Inscrição | Candidatura do aluno a um programa, com documentos, parecer, respostas e eventual análise. |
| Análise de inscrição | Snapshot da situação do aluno e dos critérios aplicados para apoiar a seleção. |
| Pontuação | Soma dos pontos dos critérios e da especificidade registrados na análise. |
| Parecer | Decisão ou estado administrativo da inscrição: deferido, indeferido, pendente ou equivalente. |
| Pendência de documentação | Estado em que a inscrição ou documento requer correção, validação ou entrega adicional. |
| Participação | Concretização de uma inscrição deferida, com vigência e dados específicos do benefício. |
| Demanda do aluno | Tipo de atendimento que pode ser solicitado ou efetivamente atendido. |
| Atendimento setorial | Registro de atendimento realizado por setor, podendo envolver vários alunos e valores. |
| Oferta | Capacidade ou valor disponível para um campus em determinado período. |
| Agendamento de refeição | Reserva de uma refeição para aluno/programa, com data e tipo (café, almoço ou jantar). |
| Solicitação de refeição | Pedido do aluno para receber uma refeição em dia e modalidade permitidos. |
| Falta de alimentação | Não comparecimento ou não consumo identificado no controle de refeições, sujeito a justificativa e suspensão. |
| Auxílio eventual | Auxílio pontual solicitado e concedido fora da participação recorrente de um programa. |
| Comprovante de participação | Evidência mensal exigida por alguns programas para comprovar participação/pagamento. |
| Termo de compromisso | Instrumento associado à inscrição/participação, podendo ter assinatura e validação eletrônicas quando disponível. |
| CadÚnico | Cadastro externo utilizado como fonte de informação socioeconômica na importação configurada. |
| Renda per capita | Renda familiar dividida conforme a composição familiar registrada, usada em faixas, critérios e ordenações. |
| Bolsa interna/externa | Tipo de bolsa informado na inscrição ou associado a critérios e benefícios. |
| Critério de seleção | Regra parametrizada que gera pontos a partir de renda, perfil, documentos ou condições sociais. |
| Parâmetro de seleção | Configuração adicional de sugestão, limite ou especificidade usada na análise. |

## Acrônimos e abreviações

| Acrônimo | Expansão/uso |
|---|---|
| AE | Atividades Estudantis, nome do módulo e da área funcional. |
| CPF | Cadastro de Pessoas Físicas, usado para localizar aluno/pessoa no CadÚnico. |
| RG | Registro Geral, um dos tipos de documento de inscrição. |
| FK | Foreign Key, relação de chave estrangeira no modelo. |
| M2M | Many-to-many, relação muitos-para-muitos. |
| PNAES | Sigla usada pelo módulo nos relatórios de atendimento; expansão não registrada no código consultado. |
| SISPNAES | Identificador usado no nome do relatório de exportação; contrato externo não documentado no módulo. |
| EAD | Modalidade de ensino usada em regras/perfis acadêmicos quando fornecida por `edu`. |
| NAPNE | Sigla preservada em regras/opções de público quando aplicável; significado deve ser confirmado no domínio institucional. |

> ⚠️ REVISAR: confirmar as expansões institucionais de PNAES, SISPNAES e NAPNE junto à área responsável; o código fornece os rótulos, mas não uma definição normativa.

## Entidades e significado de negócio

| Entidade | Significado |
|---|---|
| `Caracterizacao` | Estado socioeconômico corrente do aluno. |
| `HistoricoCaracterizacao` | Versão histórica dos campos alterados da caracterização. |
| `InscricaoCaracterizacao` | Dados socioeconômicos capturados no contexto de uma inscrição. |
| `Inscricao` | Candidatura a um `Programa`. |
| `AnaliseInscricao` | Registro congelado de avaliação e pontuação da candidatura. |
| `Participacao` | Benefício efetivamente iniciado após a inscrição. |
| `ParticipacaoAlimentacao` | Especialização da participação com refeições. |
| `ParticipacaoTrabalho` | Especialização com alocação em oferta de bolsa/trabalho. |
| `ParticipacaoPasseEstudantil` | Especialização com valor/condição de passe. |
| `ParticipacaoIdioma` | Especialização com turma de idioma. |
| `DemandaAlunoAtendida` | Registro de consumo/atendimento efetivo. |
| `AgendamentoRefeicao` | Reserva operacional de refeição. |
| `DocumentoInscricaoAluno` | Evidência documental da candidatura ou grupo familiar. |
| `ComprovanteParticipacao` | Evidência periódica da participação. |
| `DadosFincanceiros` | Dados financeiros históricos; a grafia do nome é legada. |

_Gerado/atualizado via subagent `documentador` em 2026-09-09._
