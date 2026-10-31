# -*- coding: utf-8 -*-
# language: pt
Funcionalidade: Cadastrar Item no Processo de Compra

  @do_document
  Cenário: Cadastrar Item no Processo de Compra
    Ação executada pelo membro do grupo Operador de Compras do campus incluído no processo de compra.

    Dado acesso a página "/"
    Quando a data do sistema for "02/03/2020"
    Quando realizo o login com o usuário "admin" e senha "abc"
    E acesso o menu "Administração::Compras::Compras"
    Então vejo a página "Processos de Compra"
    Quando clico no link "Descrição do processo de compra"
    Então vejo a página "Descrição do processo de compra"
    Quando clico no link "CZN"
    Então vejo a página "Descrição do processo de compra - CZN"
    E vejo os seguintes campos no formulário
      | Campo    | Tipo         |
      | Material | Autocomplete |
      | Qtd      | Texto        |
      | Campus   | Lista        |
    E vejo o botão "Salvar"
    Quando preencho o formulário com os dados
      | Campo    | Tipo         | Valor |
      | Material | Autocomplete |     1 |
      | Qtd      | Texto        |     5 |
      | Campus   | Lista        | CZN   |
    E clico no botão "Salvar"
    Então vejo mensagem de sucesso "Item adicionado com sucesso."

  Cenário: Sai do sistema
    Quando acesso o menu "Sair"
