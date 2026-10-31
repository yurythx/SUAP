# -*- coding: utf-8 -*-
# language: pt
Funcionalidade: Cadastro gerais do módulo CPA

  Cenário: Adicionando os usuários necessários para os testes CPA
    Dado os seguintes usuários
      | Nome            | Matrícula | Setor | Lotação | Email                            | CPF            | Senha | Grupo            |
      | Gerente CPA     |    802021 | CZN   | CZN     | gerente_cpa@ifrn.edu.br          | 000.802.021-36 | abcd  | cpa_gerente      |
      | Visualizar CPA  |    802022 | CZN   | CZN     | visualizador_cpa@ifrn.edu.br     | 975.215.430-17 | abcd  | cpa_visualizador |
      | Respondente CPA |    802023 | CZN   | CZN     | servidor_respondente@ifrn.edu.br | 950.147.300-78 | abcd  | Servidor         |

  @do_document
  Cenário: Cadastro de Categoria de Questionário
    Cadastro de Categoria de Questionário.
    Ação executada por um membro do grupo cpa_gerente.

    Dado acesso a página "/"
    Quando realizo o login com o usuário "802021" e senha "abcd"
    E acesso o menu "Des. Institucional::Autoavaliação::Categorias"
    Então vejo a página "Categorias"
    E vejo o botão "Adicionar Categoria"
    Quando clico no botão "Adicionar Categoria"
    Então vejo a página "Adicionar Categoria"
    E vejo os seguintes campos no formulário
      | Campo | Tipo  |
      | Nome  | Texto |
    E vejo o botão "Salvar"
    Quando preencho o formulário com os dados
      | Campo | Tipo  | Valor                                                       |
      | Nome  | Texto | ORGANIZAÇÃO, GESTÃO, PLANEJAMENTO E AVALIAÇÃO INSTITUCIONAL |
    E clico no botão "Salvar"
    Então vejo mensagem de sucesso "Cadastro realizado com sucesso."

    @do_document
    Cenário: Cadastrar Questionário CPA
    Ação executada pelo membro do grupo cpa_gerente.

    Quando acesso o menu "Des. Institucional::Autoavaliação::Questionários"
    Então vejo a página "Questionários"
    E vejo o botão "Adicionar Questionário"
    Quando clico no botão "Adicionar Questionário"
    Então vejo a página "Adicionar Questionário"
    E vejo os seguintes campos no formulário
      | Campo           | Tipo                   |
      | Descrição       | Texto                  |
      | Público         | Lista                  |
      | Ano             | Texto                  |
      | Data de Início  | Data                  |
      | Data de Término | Data                  |
      | Dicionário      | Textarea               |
      | Campi           | FilteredSelectMultiple |
      | Categoria       | Autocomplete           |
      | Ordem           | Texto                  |
    E vejo o botão "Salvar"
    Quando preencho o formulário com os dados
      | Campo           | Tipo                   | Valor                                                       |
      | Descrição       | Texto                  | Novo Questionário                                           |
      | Público         | Lista                  | Técnicos                                                    |
      | Ano             | Texto                  |                                                        2020 |
      | Data de Início  | Data                  | 01/01/2020                                                   |
      | Data de Término | Data                  | 01/06/2020                                                   |
      | Dicionário      | Textarea               | descrição sobre o questionário                              |
      | Campi           | FilteredSelectMultiple | CZN                                                         |
    
    E preencho o formulário inline "Categoria do questionário" com os dados
      | Campo           | Tipo                   | Valor                                                       |
      | Categoria       | Autocomplete           | ORGANIZAÇÃO, GESTÃO, PLANEJAMENTO E AVALIAÇÃO INSTITUCIONAL |
      | Ordem           | Texto                  |                                                           1 |
    E clico no botão "Salvar"
    Então vejo mensagem de sucesso "Questionário cadastrado com sucesso."

  @do_document
  Cenário: Cadastrar Perguntas do Questionário CPA
    Ação executada pelo membro do grupo cpa_gerente.

    Quando acesso o menu "Des. Institucional::Autoavaliação::Questionários"
    Então vejo a página "Questionários"
    Quando clico no ícone de exibição
    Então vejo a página "Avaliação Institucional"
    E vejo o botão "Adicionar Pergunta"
    Quando clico no botão "Adicionar Pergunta"
    E olho para o popup
    Então vejo a página "Adicionar Pergunta"
    E vejo os seguintes campos no formulário
      | Campo         | Tipo     |
      | Identificador | Texto    |
      | Texto         | Textarea |
      | Objetiva      | checkbox |
      | Ordem         | Texto    |
    E vejo o botão "Salvar"
    Quando preencho o formulário com os dados
      | Campo         | Tipo     | Valor                          |
      | Identificador | Texto    | Pergunta 1                     |
      | Texto         | Textarea | Descrição da primeira pergunta |
      | Objetiva      | checkbox | desmarcar                      |
      | Ordem         | Texto    |                              1 |
    E clico no botão "Salvar"
    Então vejo mensagem de sucesso "Pergunta adicionada com sucesso."
