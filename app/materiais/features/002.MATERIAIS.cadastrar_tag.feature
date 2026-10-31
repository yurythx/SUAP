# -*- coding: utf-8 -*-
# language: pt
Funcionalidade: Cadastrar Tag

  @do_document
  Cenário: Cadastrar Tag de Materiais
    Ação executada por um membro do grupo Gerenciador do Catálogo de Materiais.

    Dado acesso a página "/"
    Quando realizo o login com o usuário "907002" e senha "abcd"
    E acesso o menu "Administração::Materiais::Tag de Materiais"
    Então vejo a página "Tags de Materiais"
    Quando clico no link "Adicionar Tag"
    Então vejo a página "Adicionar Tag"
    E vejo os seguintes campos no formulário
      | Campo    | Tipo         |
      | Descrição      | Texto        |
    E vejo o botão "Salvar"
    Quando preencho o formulário com os dados
      | Campo    | Tipo         | Valor |
      | Descrição      | Texto        |     tag dos materiais |
    E clico no botão "Salvar"
    Então vejo mensagem de sucesso "Cadastro realizado com sucesso."

  Cenário: Sai do sistema
    Quando acesso o menu "Sair"
