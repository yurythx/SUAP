# -*- coding: utf-8 -*-
# language: pt
Funcionalidade: Cadastro de Materiais

  Cenário: Adicionando os usuários necessários para os testes Materiais
    Dado os dados básicos para materiais
    E os seguintes usuários
      | Nome                 | Matrícula | Setor | Lotação | Email                            | CPF            | Senha | Grupo                                |
      | Gerenciador Catalogo |    907002 | CZN   | CZN     | gerenciador_catalogo@ifrn.edu.br | 000.907.002-87 | abcd  | Gerenciador do Catálogo de Materiais |

  @do_document
  Cenário: Cadastro de Categorias
    Cadastro de Categorias de Materiais.
    Ação executada por um membro do grupo Gerenciador do Catálogo de Materiais.

    Dado acesso a página "/"
    Quando realizo o login com o usuário "907002" e senha "abcd"
    E acesso o menu "Administração::Materiais::Categorias"
    Então vejo a página "Categorias"
    E vejo o botão "Adicionar Categoria"
    Quando clico no botão "Adicionar Categoria"
    Então vejo a página "Adicionar Categoria"
    E vejo os seguintes campos no formulário
      | Campo                    | Tipo                   |
      | Subelemento                 | Autocomplete                  |
      | Descrição               | Texto               |
      | Código           | Texto                  |
      | Validade              | Texto                  |

    E vejo o botão "Salvar"
    Quando preencho o formulário com os dados
      | Campo                    | Tipo                   | Valor                           |
      | Subelemento                | Autocomplete                  |339030 |
      | Descrição               | Texto               | descricao da categoria |
      | Código           | Texto                  | 1234 |
      | Validade              | Texto                  | 30 |
    E clico no botão "Salvar"
    Então vejo mensagem de sucesso "Cadastro realizado com sucesso."

  Cenário: Sai do sistema
    Quando acesso o menu "Sair"
