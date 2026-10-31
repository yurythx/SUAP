# -*- coding: utf-8 -*-
# language: pt
Funcionalidade: Cadastros Gerais de Orçamento

  Cenário: Adicionando os usuários necessários para os testes Orçamento
    Dado os dados básicos para orçamento
    E os seguintes usuários
      | Nome                 | Matrícula | Setor | Lotação | Email                            | CPF            | Senha | Grupo                                |
      | Adm Orcamento |    917008 | CZN   | CZN     | adm_orcamento@ifrn.edu.br | 165.506.040-60 | abcd  | Administrador de Orçamento |

  @do_document
  Cenário: Cadastro Gerais de Orçamento
    Cadastro das Configurações.
    Ação executada pelo Administrador.

    Dado acesso a página "/"
    Quando realizo o login com o usuário "admin" e senha "abc"
    E acesso o menu "Administração::Orçamento::Cadastros::Unidades Gestoras"
    Então vejo a página "Unidades Gestoras"
    E vejo o botão "Adicionar Unidade Gestora"
    Quando clico no botão "Adicionar Unidade Gestora"
    Então vejo a página "Adicionar Unidade Gestora"
    E vejo os seguintes campos no formulário
      | Campo                    | Tipo                   |
      | Código                      | Texto                  |
      | Mnemônico                | Texto                  |
      | Nome                | Texto                  |
      | Função                | Lista                  |
    E vejo o botão "Salvar"
    Quando preencho o formulário com os dados
      | Campo                    | Tipo                   | Valor                           |
      | Código                      | Texto                  | 11 |
      | Mnemônico                | Texto                  | 11 |
      | Nome                | Texto                  | Campus 1 |
      | Função                | Lista                  | Executora |
    E clico no botão "Salvar"
    Então vejo mensagem de sucesso "Cadastro realizado com sucesso."

    Quando acesso o menu "Administração::Orçamento::Cadastros::Unidades Gestoras"
    Então vejo a página "Unidades Gestoras"
    E vejo o botão "Adicionar Unidade Gestora"
    Quando clico no botão "Adicionar Unidade Gestora"
    Então vejo a página "Adicionar Unidade Gestora"
    E vejo os seguintes campos no formulário
      | Campo                    | Tipo                   |
      | Código                      | Texto                  |
      | Mnemônico                | Texto                  |
      | Nome                | Texto                  |
      | Função                | Lista                  |
    E vejo o botão "Salvar"
    Quando preencho o formulário com os dados
      | Campo                    | Tipo                   | Valor                           |
      | Código                      | Texto                  | 22 |
      | Mnemônico                | Texto                  | 22 |
      | Nome                | Texto                  | Campus 2 |
      | Função                | Lista                  | Executora |
    E clico no botão "Salvar"
    Então vejo mensagem de sucesso "Cadastro realizado com sucesso."

    Quando acesso o menu "Administração::Orçamento::Cadastros::Unidades de Medida"
    Então vejo a página "Unidades de Medida"
    E vejo o botão "Adicionar Unidade de Medida"
    Quando clico no botão "Adicionar Unidade de Medida"
    Então vejo a página "Adicionar Unidade de Medida"
    E vejo os seguintes campos no formulário
      | Campo                    | Tipo                   |
      | Nome                | Texto                  |
    E vejo o botão "Salvar"
    Quando preencho o formulário com os dados
      | Campo                    | Tipo                   | Valor                           |
      | Nome                | Texto                  | Aluno assistido |
    E clico no botão "Salvar"
    Então vejo mensagem de sucesso "Cadastro realizado com sucesso."

  Cenário: Sai do sistema
    Quando acesso o menu "Sair"
