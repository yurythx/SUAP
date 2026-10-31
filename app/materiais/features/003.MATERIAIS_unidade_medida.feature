# -*- coding: utf-8 -*-
# language: pt
Funcionalidade: Cadastrar Unidade de Medida

  @do_document
  Cenário: Cadastrar Unidade de Medida
    Ação executada por um membro do grupo Gerenciador do Catálogo de Materiais.

    Dado acesso a página "/"
    Quando realizo o login com o usuário "907002" e senha "abcd"
    E acesso o menu "Administração::Materiais::Unidade de Medida"
    Então vejo a página "Unidades de Medida"
    Quando clico no link "Adicionar Unidade de Medida"
    Então vejo a página "Adicionar Unidade de Medida"
    E vejo os seguintes campos no formulário
      | Campo    | Tipo         |
      | Descricao      | Texto        |
    E vejo o botão "Salvar"
    Quando preencho o formulário com os dados
      | Campo    | Tipo         | Valor |
      | Descricao      | Texto        |     Unidade |
    E clico no botão "Salvar"
    Então vejo mensagem de sucesso "Cadastro realizado com sucesso."

  Cenário: Sai do sistema
    Quando acesso o menu "Sair"
