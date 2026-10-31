# -*- coding: utf-8 -*-
# language: pt
Funcionalidade: Cadastro do Período de Preenchimento do Questionário

  Cenário: Adicionando os usuários necessários para os testes Acumulo de Cargo
    Dado os seguintes usuários
      | Nome                | Matrícula | Setor | Lotação | Email                        | CPF            | Senha | Grupo                                      |
      | Coord RH            |    100147 | CZN   | CZN     | coord_rh@ifrn.edu.br         | 988.868.680-14 | abcd  | Coordenador de Gestão de Pessoas Sistêmico |
      | Servidor do Acumulo |    100148 | CZN   | CZN     | servidor_acumulo@ifrn.edu.br | 056.941.450-46 | abcd  | Servidor                                   |
    Quando a data do sistema for "02/07/2020"

  @do_document
  Cenário: Cadastro do Período de Preenchimento do Questionário
    Cadastro do Período de Preenchimento do Questionário
    Ação executada por um membro do grupo Coordenador de Gestão de Pessoas Sistêmico.

    Dado acesso a página "/"
    Quando realizo o login com o usuário "100147" e senha "abcd"
    E acesso o menu "Gestão de Pessoas::Administração de Pessoal::Acúmulo de Cargo::Questionário de Acúmulo de Cargo"
    Então vejo a página "Questionários de Acúmulo de Cargos"
    E vejo o botão "Adicionar Questionário de Acúmulo de Cargos"
    Quando clico no botão "Adicionar Questionário de Acúmulo de Cargos"
    Então vejo a página "Adicionar Questionário de Acúmulo de Cargos"
    E vejo os seguintes campos no formulário
      | Campo           | Tipo                   |
      | Descrição       | Texto                  |
      | Público         | Lista                  |
      | Ano             | Texto                  |
      | Data de Início  | Data                   |
      | Data de Término | Data                   |
      | Campi           | FilteredSelectMultiple |
    E vejo o botão "Salvar"
    Quando preencho o formulário com os dados
      | Campo           | Tipo                   | Valor             |
      | Descrição       | Texto                  | Questionário 2020 |
      | Público         | Lista                  | Geral             |
      | Ano             | Texto                  |              2020 |
      | Data de Início  | Data                   | 10/07/2020        |
      | Data de Término | Data                   | 31/07/2020        |
      | Campi           | FilteredSelectMultiple | CZN               |
    E clico no botão "Salvar"
    Então vejo mensagem de sucesso "Cadastro realizado com sucesso."

  Cenário: Sai do sistema
    Quando acesso o menu "Sair"
