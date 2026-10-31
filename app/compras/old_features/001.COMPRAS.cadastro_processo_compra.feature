# -*- coding: utf-8 -*-
# language: pt
Funcionalidade: Cadastro de Processo de Compra

  Cenário: Adicionando os usuários necessários para os testes compras
    Dado os dados básicos para compras
    E os seguintes usuários
      | Nome                 | Matrícula | Setor | Lotação | Email                            | CPF            | Senha | Grupo                                |
      | Gerenciador Catalogo |    907002 | CZN   | CZN     | gerenciador_catalogo@ifrn.edu.br | 188.135.291-98 | abcd  | Gerenciador do Catálogo de Materiais |
      | Validador Compra     |    907003 | CZN   | CZN     | validador_compra@ifrn.edu.br     | 568.288.693-38 | abcd  | Validador de Compras                 |

  @do_document
  Cenário: Cadastro de Processo de Compra
    Cadastro de Processo de Compra.
    Ação executada por um membro do grupo Gerenciador de Compras.

    Dado acesso a página "/"
    Quando a data do sistema for "01/03/2020"
    Quando realizo o login com o usuário "admin" e senha "abc"
    E acesso o menu "Administração::Compras::Compras"
    Então vejo a página "Processos de Compra"
    E vejo o botão "Adicionar Processo de Compra"
    Quando clico no botão "Adicionar Processo de Compra"
    Então vejo a página "Adicionar Processo de Compra"
    E vejo os seguintes campos no formulário
      | Campo                    | Tipo                   |
      | Descrição                | Texto                  |
      | Observação               | TextArea               |
      | Data de Início           | Data                   |
      | Data de Fim              | Data                   |
      | Tags                     | FilteredSelectMultiple |
      | Aplicar a todos os campi | checkbox               |
    E vejo o botão "Salvar"
    Quando preencho o formulário com os dados
      | Campo                    | Tipo                   | Valor                           |
      | Descrição                | Texto                  | Descrição do processo de compra |
      | Observação               | TextArea               | descrição das observações       |
      | Data de Início           | Data                   | 01/03/2020                      |
      | Data de Fim              | Data                   | 31/03/2020                      |
      | Tags                     | FilteredSelectMultiple | Permanente, Informática         |
      | Aplicar a todos os campi | checkbox               | Marcar                          |
    E clico no botão "Salvar"
    Então vejo mensagem de sucesso "Cadastro realizado com sucesso."

  Cenário: Sai do sistema
    Quando acesso o menu "Sair"
