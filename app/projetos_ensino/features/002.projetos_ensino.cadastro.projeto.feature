# -*- coding: utf-8 -*-
# language: pt

Funcionalidade: Submissão de Projeto de Ensino

      @do_document
      Cenário: Cadastro do Projeto
      Formulário de submissão com as informações básicas do projeto. Após o envio dos dados, o projeto estará cadastrado mas ainda não terá sido submetido,
      ou seja, a situação do projeto será 'em edição' (rascunho). Só após o cadastro das demais informações obrigatórias, descritas nos próximos passos, é que o projeto poderá ser efetivamente submetido.
      Ação executada pelo Servidor (coordenador do projeto).
          Dado acesso a página "/"
        Quando realizo o login com o usuário "130003" e senha "abcd"
             E a data do sistema for "08/01/2018"
             E acesso o menu "Ensino::Projetos::Adicionar projeto"
         Então vejo a página "Editais de Ensino e de Fluxo Contínuo com Inscrições Abertas"
        Quando clico no botão "Adicionar projeto"
         Então vejo a página "Adicionar projeto"
             E vejo os seguintes campos no formulário
               | Campo                                                      | Tipo     |
               | Campus                                                     | Lista    |
               | Setor                                                      | Lista    |
               | Título do projeto                                          | Texto    |
               | Carga Horária Semanal do Coordenador                       | Texto    |
               | Início da Execução                                         | Data     |
               | Término da Execução                                        | Data     |
               | Carga horária total para desenvolvimento do projeto        | Texto    |
               | Eixo Temático                                              | Autocomplete    |
               | Há parceiros externos                                      | Checkbox |
               | Resumo                                                     | Textarea |
               | Introdução                                                 | Textarea |
               | Justificativa e Relevância                                 | Textarea |
               | Objetivo Geral                                             | Textarea |
               | Metodologia da execução do projeto                         | Textarea |
               | Acompanhamento e avaliação do projeto durante a execução   | Textarea |
               | Resultados Esperados e Disseminação dos Resultados         | Textarea |
               | Referências                                                | Textarea |
             E vejo o botão "Salvar"
        Quando preencho o formulário com os dados
            | Campo                                                    | Tipo       | Valor                                  |
            | Campus                                                   | Lista      | CZN                                    |
            | Setor                                                    | Lista      | DIAC/CZN                               |
            | Título do projeto                                        | Texto      | Título do projeto                      |
            | Carga Horária Semanal do Coordenador                     | Texto      | 5                                      |
            | Início da Execução                                       | Data       | 01/03/2018                             |
            | Término da Execução                                      | Data       | 12/12/2018                             |
            | Carga horária total para desenvolvimento do projeto      | Texto      | 50                                     |
            | Há parceiros externos                                    | Checkbox | marcar |
            | Parceiros Externos                                       | Texto      | Instituição parceira                   |
            | Eixo Temático                                            | Autocomplete    | Educação                               |
            | Resumo                                                   | Texto Rico | Texto do Resumo                        |
            | Introdução                                               | Texto Rico | Texto da Introdução                 |
            | Justificativa e Relevância                               | Texto Rico | Texto da Justificativa e Relevância         |
            | Objetivo Geral                                           | Texto Rico | Texto do objetivo Geral                |
            | Metodologia da execução do projeto                       | Texto Rico | Texto da metodologia                   |
            | Acompanhamento e avaliação do projeto durante a execução | Texto Rico | Texto do acompanhamento                |
            | Resultados Esperados e Disseminação dos Resultados       | Texto Rico | Texto dos resultados                   |
            | Referências                                | Texto Rico | Texto das referências                  |
             E clico no botão "Salvar"

        Então vejo mensagem de sucesso "Projeto cadastrado com sucesso."

      @do_document
      Cenário: Inclusão de Servidor na Equipe
      Cadastro do servidor membro do projeto de ensino.
      Ação executada pelo Servidor (coordenador do projeto).
        Quando acesso o menu "Ensino::Projetos::Meus projetos"
         Então vejo a página "Meus projetos"
             E vejo o botão "Visualizar"
        Quando clico no botão "Visualizar"
         Então vejo a página "Projeto de Ensino"
         Quando clico na aba "Equipe"
         Então vejo o botão "Adicionar Servidor"
         Quando clico no botão "Adicionar Servidor"
             E olho para o popup
             Então vejo os seguintes campos no formulário
               | Campo                                                      | Tipo     |
               | Bolsista                                                   | Lista    |
               | Carga Horária                                              | Texto    |
               | Participante                                               | Autocomplete    |
               | Data de Entrada                                            | Data     |

             E vejo o botão "Salvar"

        Quando preencho o formulário com os dados
               | Campo                                                      | Tipo     | Valor                                       |
               | Bolsista                                                   | Lista    | Não                                         |
               | Carga Horária                                              | Texto    | 6                                           |
               | Participante                                               | Autocomplete    | Servidor 1                                  |
               | Data de Entrada                                            | Data     | 05/05/2018                                  |

             E clico no botão "Salvar"

         Então vejo mensagem de sucesso "Participante adicionado com sucesso."


      @do_document
      Cenário: Inclusão de Aluno na Equipe
      Cadastro do aluno membro do projeto de ensino.
      Ação executada pelo Servidor (coordenador do projeto).
        Quando acesso o menu "Ensino::Projetos::Meus projetos"
         Então vejo a página "Meus projetos"
             E vejo o botão "Visualizar"
        Quando clico no botão "Visualizar"
         Então vejo a página "Projeto de Ensino"
         Quando clico na aba "Equipe"
         Então vejo o botão "Adicionar Aluno"
         Quando clico no botão "Adicionar Aluno"
             E olho para o popup
             Então vejo os seguintes campos no formulário
               | Campo                                                      | Tipo     |
               | Bolsista                                                   | Lista    |
               | Carga Horária                                              | Texto    |
               | Participante                                               | Autocomplete    |
               | Data de Entrada                                            | Data     |

             E vejo o botão "Salvar"

        Quando preencho o formulário com os dados
               | Campo                                                      | Tipo     | Valor                                       |
               | Bolsista                                                   | Lista    | Não                                         |
               | Carga Horária                                              | Texto    | 6                                           |
               | Participante                                               | Autocomplete    | Aluno           |
               | Data de Entrada                                            | Data     | 05/05/2018                                  |

             E clico no botão "Salvar"

         Então vejo mensagem de sucesso "Participante adicionado com sucesso."

      @do_document
      Cenário: Cadastro e Caracterização dos Beneficiários
      Cadastro das pessoas e das instituições que poderão ser beneficiadas com a execução do projeto.
      Ação executada pelo Servidor (coordenador do projeto).
        Quando acesso o menu "Ensino::Projetos::Meus projetos"
         Então vejo a página "Meus projetos"
             E vejo o botão "Visualizar"
        Quando clico no botão "Visualizar"
         Então vejo a página "Projeto de Ensino"
         Quando clico na aba "Caracterização dos Beneficiários"
             Então vejo o botão "Adicionar Caracterização dos Beneficiários"
         Quando clico no botão "Adicionar Caracterização dos Beneficiários"
             E olho para o popup
             Então vejo os seguintes campos no formulário
               | Campo                                                      | Tipo     |
               | Tipo de beneficiário                                       | Autocomplete    |
               | Quantidade Prevista de Pessoas a Atender                   | Texto    |

             E vejo o botão "Salvar"


        Quando preencho o formulário com os dados
               | Campo                                                      | Tipo     | Valor              |
               | Tipo de beneficiário                                       | Autocomplete    | Movimentos Sociais |
               | Quantidade Prevista de Pessoas a Atender                   | Texto    | 12                 |

             E clico no botão "Salvar"

         Então vejo mensagem de sucesso "Caracterização do beneficiário adicionada com sucesso."

      @do_document
      Cenário: Cadastro das Metas
      Cadastro das metas do projeto.
      Ação executada pelo Servidor (coordenador do projeto).
        Quando acesso o menu "Ensino::Projetos::Meus projetos"
         Então vejo a página "Meus projetos"
             E vejo o botão "Visualizar"
        Quando clico no botão "Visualizar"
         Então vejo a página "Projeto de Ensino"
         Quando clico na aba "Metas/Atividades"
             Então vejo o botão "Adicionar Meta"
         Quando clico no botão "Adicionar Meta"
             E olho para o popup
             Então vejo os seguintes campos no formulário
               | Campo                                                      | Tipo     |
               | Ordem                                                      | Texto    |
               | Descrição                                                  | TextArea |


             E vejo o botão "Salvar"


        Quando preencho o formulário com os dados
               | Campo                                                      | Tipo     | Valor                                       |
               | Ordem                                                      | Texto    | 1                                           |
               | Descrição                                                  | TextArea | Descrição da Meta 1                         |

             E clico no botão "Salvar"

         Então vejo mensagem de sucesso "Meta adicionada com sucesso."

      @do_document
      Cenário: Cadastro das Atividades
      Cadastro das atividades que serão realizadas dentro de cada meta do projeto.
      Ação executada pelo Servidor (coordenador do projeto).
        Quando acesso o menu "Ensino::Projetos::Meus projetos"
         Então vejo a página "Meus projetos"
             E vejo o botão "Visualizar"
        Quando clico no botão "Visualizar"
         Então vejo a página "Projeto de Ensino"
         Quando clico na aba "Metas/Atividades"
         Então vejo o botão "Adicionar Atividade"
         Quando clico no botão "Adicionar Atividade"
             E olho para o popup
             Então vejo os seguintes campos no formulário
               | Campo                                                      | Tipo     |
               | Ordem                                                      | Texto    |
               | Descrição                                                  | TextArea |
               | Indicador Quantitativo                                     | Texto    |
               | Quantidade                                                 | Texto    |
               | Indicador(es) Qualitativo(s)                               | TextArea |
               | Responsável                                                | Lista    |
               | Início da Execução                                         | Data    |
               | Fim da Execução                                            | Data    |


             E vejo o botão "Salvar"

        Quando preencho o formulário com os dados
               | Campo                                                      | Tipo     | Valor                    |
               | Ordem                                                      | Texto    | 1                        |
               | Descrição                                                  | TextArea | Descrição da Atividade 1 |
               | Indicador Quantitativo                                     | Texto    | Unidade                  |
               | Quantidade                                                 | Texto    | 4                        |
               | Indicador(es) Qualitativo(s)                               | TextArea | Verificação de qualidade |
               | Responsável                                                | Lista    | Servidor 1               |
               | Início da Execução                                         | Data    | 01/04/2018               |
               | Fim da Execução                                            | Data    | 30/04/2018               |

             E clico no botão "Salvar"

         Então vejo mensagem de sucesso "Atividade adicionada com sucesso."

      @do_document
      Cenário: Cadastro das Memórias de Cálculo
      A memória de cálculo serve para descrever em detalhes os gastos que serão realizados no projeto. Nesta aba do projeto existe o Demonstrativo do Plano de Aplicação/Memória de Cálculo e Desembolso,
      onde, na coluna 'Valor Reservado' consta o valor total disponível para o projeto na rubrica em específico, conforme cadastrado na fonte de recurso do edital. Na seção 'Planejado', a coluna 'Valor Planejado' exibe a soma de todas as memórias de cálculo cadastradas pelo coordenador do projeto.
      Já na coluna 'Valor Distribuído' consta a soma de todos os desembolsos que foram cadastrados pelo coordenador e na coluna 'Valor Disponível' consta a diferença entre a soma das memórias de cálculo e a soma dos desembolsos.
      Na seção 'Execução', a coluna 'Valor Executado' é a soma de todos os registros de gastos cadastrados pelo coordenador do projeto e a coluna 'Valor Disponível' é a diferença entre o total de desembolsos e o total de gastos.
      Ação executada pelo Servidor (coordenador do projeto).
        Quando acesso o menu "Ensino::Projetos::Meus projetos"
         Então vejo a página "Meus projetos"
             E vejo o botão "Visualizar"
        Quando clico no botão "Visualizar"
         Então vejo a página "Projeto de Ensino"
        Quando clico na aba "Plano de Aplicação"
         Então vejo o botão "Adicionar Memória de Cálculo"
        Quando clico no botão "Adicionar Memória de Cálculo"
             E olho para o popup
             Então vejo os seguintes campos no formulário
               | Campo                                                      | Tipo     |
               | Recurso                                                    | Lista    |
               | Descrição                                                  | TextArea |
               | Unidade de Medida                                          | Texto    |
               | Quantidade                                                 | Texto    |
               | Valor Unitário (R$)                                        | Texto    |


             E vejo o botão "Salvar"

        Quando preencho o formulário com os dados
               | Campo                                                      | Tipo     | Valor                                             |
               | Recurso                                                    | Lista    | 339018 - Auxílio Financeiro a Estudantes / CAMPUS  |
               | Descrição                                                  | TextArea | Pagamento das bolsas de dois alunos, no valor de R$ 500,00 cada |
               | Unidade de Medida                                          | Texto    | Unidade                                           |
               | Quantidade                                                 | Texto    | 1                                                 |
               | Valor Unitário (R$)                                        | Texto    | 10.000,00                                         |

             E clico no botão "Salvar"

         Então vejo mensagem de sucesso "Item adicionado com sucesso."

      @do_document
      Cenário: Cadastro dos Desembolsos
      Com base na memória de cálculo, neste passo o coordenador do projeto informa quando pretende realizar os gastos(desembolsos) dos recursos.
      Por exemplo, uma memória de cálculo no valor de R$ 10.000,00 prevista para pagamento de alunos bolsistas pode ter 10 desembolsos, no valor de R$1.000,00 cada,
      que serão executados ao longo de 10 meses.
      Ação executada pelo Servidor (coordenador do projeto).
        Quando acesso o menu "Ensino::Projetos::Meus projetos"
         Então vejo a página "Meus projetos"
             E vejo o botão "Visualizar"
        Quando clico no botão "Visualizar"
         Então vejo a página "Projeto de Ensino"
         Quando clico na aba "Plano de Desembolso"
         Então vejo o botão "Adicionar Item"
         Quando clico no botão "Adicionar Item"
             E olho para o popup
             Então vejo os seguintes campos no formulário
               | Campo                                                      | Tipo     |
               | Mémoria de Cálculo                                         | Lista    |
               | Ano                                                        | Autocomplete    |
               | Mês                                                        | Lista    |
               | Valor (R$)                                                 | Texto    |
               | Repetir Desembolso até o mês                               | Texto    |


             E vejo o botão "Salvar"

        Quando preencho o formulário com os dados
               | Campo                                                      | Tipo     | Valor                                                                             |
               | Mémoria de Cálculo                                         | Lista    | 339018 - Auxílio Financeiro a Estudantes / CAMPUS - Pagamento das bolsas de dois alunos, no valor de R$ 500,00 cada  |
               | Ano                                                        | Autocomplete    | 2018                                                                       |
               | Mês                                                        | Lista    | 1                                                                                 |
               | Valor (R$)                                                 | Texto    | 10.000,00                                                                            |


             E clico no botão "Salvar"

         Então vejo mensagem de sucesso "Desembolso adicionado com sucesso."


  @do_document
      Cenário: Submissão do Projeto
      Após o cadastro de todas as informações obrigatórias, o coordenador do projeto está apto a realizar a submissão do projeto.
      Ação executada pelo Servidor (coordenador do projeto).
        Quando acesso o menu "Ensino::Projetos::Meus projetos"
         Então vejo a página "Meus projetos"
             E vejo o botão "Visualizar"
        Quando clico no botão "Visualizar"
         Então vejo a página "Projeto de Ensino"
             E vejo o botão "Enviar Projeto"
         Quando clico no botão "Enviar Projeto"
         Então vejo mensagem de sucesso "Projeto enviado com sucesso."
