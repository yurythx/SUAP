# -*- coding: utf-8 -*-
# language: pt

Funcionalidade: Atividades ligadas ao Plano de Ação e Cadastros Sistemicos

    Cenário: Monta os dados básicos para rodar os testes dessa feature
        Dada os dados básicos para o planejamento
           E os usuários do planejamento
           E um PDI cadastrado
           E as unidades administrativas
           E os macroprocessos
           E os objetivos estratégicos
           E as ações no PDI
      Quando a data do sistema for "01/01/2018"


    Esquema do Cenário: Verifica a visibilidade do menu do plano de ação do <Papel>
        Dada acesso a página "/"
      Quando realizo o login com o usuário "<Papel>" e senha "abcd"
           E acesso o menu "Des. Institucional::Planejamento Institucional::Plano de Ação"
       Então vejo a página "Planos de Ação"
      Quando acesso o menu "Sair"
      Exemplos:
          | Papel  |
          | 109002 |
          | 109004 |


    @do_document
    Cenário: Realiza o cadastro de um plano de ação
        Dada acesso a página "/"
      Quando realizo o login com o usuário "109001" e senha "abcd"
           E acesso o menu "Des. Institucional::Planejamento Institucional::Plano de Ação"
       Então vejo a página "Planos de Ação"
           E vejo o botão "Adicionar Plano de Ação"
      Quando clico no botão "Adicionar Plano de Ação"
       Então vejo a página "Adicionar Plano de Ação"
           E vejo os seguintes campos no formulário
             | Campo                              | Tipo   |
             | Pdi                                | Lista  |
             | Ano Base                           | Lista  |
             | Início da Vigência                 | Data   |
             | Fim da Vigência                    | Data   |
             | Início do Cadastro de Sistêmico    | Data   |
             | Fim do Cadastro de Sistêmico       | Data   |
             | Início do Cadastro do Campus       | Data   |
             | Fim do Cadastro do Campus          | Data   |
             | Início da Validação                | Data   |
             | Fim da Validação                   | Data   |

            E vejo o botão "Salvar"
        Quando clico no botão "Salvar"
         Então vejo os seguintes erros no formulário
             | Campo                              | Tipo   | Mensagem                 |
             | Pdi                                | Lista  | Este campo é obrigatório |
             | Ano Base                           | Lista  | Este campo é obrigatório |
             | Início da Vigência                 | Data   | Este campo é obrigatório |
             | Fim da Vigência                    | Data   | Este campo é obrigatório |
             | Início do Cadastro de Sistêmico    | Data   | Este campo é obrigatório |
             | Fim do Cadastro de Sistêmico       | Data   | Este campo é obrigatório |
             | Início do Cadastro do Campus       | Data   | Este campo é obrigatório |
             | Fim do Cadastro do Campus          | Data   | Este campo é obrigatório |
             | Início da Validação                | Data   | Este campo é obrigatório |
             | Fim da Validação                   | Data   | Este campo é obrigatório |
        Quando preencho o formulário com os dados
             | Campo                              | Tipo   | Valor       |
             | Pdi                                | Lista  | De 2018 até 2022          |
             | Ano Base                           | Lista  | 2018        |
             | Início da Vigência                 | Data   | 01/01/2018  |
             | Fim da Vigência                    | Data   | 31/12/2018  |
             | Início do Cadastro de Sistêmico    | Data   | 01/12/2017  |
             | Fim do Cadastro de Sistêmico       | Data   | 04/11/2018  |
             | Início do Cadastro do Campus       | Data   | 27/12/2017  |
             | Fim do Cadastro do Campus          | Data   | 16/11/2018  |
             | Início da Validação                | Data   | 17/01/2018  |
             | Fim da Validação                   | Data   | 31/01/2018  |
      
        E clico no botão "Salvar"

      Então vejo mensagem de sucesso "Cadastro realizado com sucesso."
    Cenário: Sai do sistema
      Quando acesso o menu "Sair"


    @do_document
    Cenário: Realiza o cadastro de uma origem de recurso
        Dada acesso a página "/"
      Quando realizo o login com o usuário "109001" e senha "abcd"
           E acesso o menu "Des. Institucional::Planejamento Institucional::Plano de Ação"
       Então vejo a página "Planos de Ação"
      Quando olho para a listagem
           E olho a linha "De 2018 até 2022"
       Então vejo o botão "Detalhar Sistêmico"
      Quando clico no botão "Detalhar Sistêmico"
           E olho para a aba "Origens de Recurso"
       Entao vejo o botão "Adicionar Origem de Recurso"
      Quando clico no botão "Adicionar Origem de Recurso"
           E olho para o popup
       Então vejo a página "Adicionar Origem de Recurso"
           E vejo os seguintes campos no formulário
             | Campo                                 | Tipo     |
             | Dimensão                              | Autocomplete   |
             | Ação Orçamentária                     | Autocomplete   |
             | Valor de Custeio                      | Texto    |
             | Valor de Capital                      | Texto    |
             | Código                                | Numero   |
          E vejo o botão "Salvar"
          Quando clico no botão "Salvar"
          E olho para o popup
          Então vejo os seguintes erros no formulário
             | Campo                                 | Tipo            | Mensagem                  |
             | Dimensão                              | Autocomplete    | Este campo é obrigatório  |
             | Ação Orçamentária                     | Autocomplete    | Este campo é obrigatório  |
             | Valor de Custeio                      | Texto           | Este campo é obrigatório  |
             | Valor de Capital                      | Texto           | Este campo é obrigatório  |
             | Código                                | Numero          | Este campo é obrigatório  |
          Quando preencho o formulário com os dados
             | Campo                                 | Tipo            | Valor                     |
             | Dimensão                              | Autocomplete    | Dimensão 1                |
             | Ação Orçamentária                     | Autocomplete    | 002                       |
             | Valor de Custeio                      | texto           | 10,00                     |
             | Valor de Capital                      | Texto           | 10,00                     |
             | Código                                | Texto           | 01                        |
        E clico no botão "Salvar"
        Então vejo mensagem de sucesso "Origem de recurso salva."
        Cenário: Sai do sistema
        Quando acesso o menu "Sair"


      @do_document
      Cenário: Vincula a Natureza de Despesa
        Dada acesso a página "/"
      Quando realizo o login com o usuário "109001" e senha "abcd"
           E acesso o menu "Des. Institucional::Planejamento Institucional::Plano de Ação"
       Então vejo a página "Planos de Ação"
      Quando olho para a listagem
           E olho a linha "De 2018 até 2022"
       Então vejo o botão "Detalhar Sistêmico"
      Quando clico no botão "Detalhar Sistêmico"
           E clico na aba "Naturezas de Despesa"
       Entao vejo o botão "Vincular Natureza de Despesa"
      Quando clico no botão "Vincular Natureza de Despesa"
           E olho para o popup
       Então vejo a página "Vincular Natureza de Despesa"
           E vejo os seguintes campos no formulário
             | Campo                                 | Tipo           |
             | Natureza de Despesa                   | Autocomplete   |

          E vejo o botão "Salvar"
          Quando clico no botão "Salvar"
          E olho para o popup
          Então vejo os seguintes erros no formulário
             | Campo                                 | Tipo            | Mensagem                  |
             | Natureza de Despesa                   | Autocomplete    | Este campo é obrigatório  |
          Quando preencho o formulário com os dados
             | Campo                                 | Tipo            | Valor                        |
             | Natureza de Despesa                   | Autocomplete    | 001                          |
        E clico no botão "Salvar"
        Então vejo mensagem de sucesso "A Natureza de Despesa foi vinculada."
        Cenário: Sai do sistema
        Quando acesso o menu "Sair"


     @do_document
     Cenário: Importar Objetivo Estratégico
        Dada acesso a página "/"
      Quando realizo o login com o usuário "109001" e senha "abcd"
           E acesso o menu "Des. Institucional::Planejamento Institucional::Plano de Ação"
       Então vejo a página "Planos de Ação"
      Quando olho para a listagem
           E olho a linha "De 2018 até 2022"
       Então vejo o botão "Detalhar Sistêmico"
      Quando clico no botão "Detalhar Sistêmico"
           E clico na aba "Objetivos Estratégicos/Meta"
       Entao vejo o botão "Importar Objetivos Estratégicos"
      Quando clico no botão "Importar Objetivos Estratégicos"
           E olho para o popup
           E seleciono o item "Objetivo 1 - Macro 1" da lista
           E clico no botão "Adicionar apenas selecionados"
       Então vejo mensagem de sucesso "Ações associadas com sucesso."
