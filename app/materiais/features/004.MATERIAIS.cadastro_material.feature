# -*- coding: utf-8 -*-
# language: pt
Funcionalidade: Cadastrar de Material

  @do_document
  Cenário: Cadastrar Material
    Ação executada por um membro do grupo Gerenciador do Catálogo de Materiais.

    Dado acesso a página "/"
    Quando realizo o login com o usuário "907002" e senha "abcd"
    E acesso o menu "Administração::Materiais::Materiais"
    Então vejo a página "Materiais"
    Quando clico no link "Adicionar Material"
    Então vejo a página "Adicionar Material"
    E vejo os seguintes campos no formulário
      | Campo    | Tipo         |
      | Subelemento      | Lista        |
      | Categoria      | Lista        |
      | Código CATMAT      | Texto        |
      | Descrição      | Texto        |
      | Especificação      | Textarea        |
      | Unidade de Medida      | Autocomplete        |
      | Tags      | FilteredSelectMultiple        |
    E vejo o botão "Salvar Material"
    Quando preencho o formulário com os dados
      | Campo    | Tipo         | Valor |
      | Subelemento      | Lista        | 339030.20 - Nome do Subelemento |
      | Código CATMAT      | Texto        | 123456 |
      | Descrição      | Texto        | descrição do material |
      | Especificação      | Textarea        | especificação do material |
      | Unidade de Medida      | Autocomplete        | Unidade |
      | Tags      | FilteredSelectMultiple        | tag dos materiais |
    E clico no botão "Salvar Material"
    Então vejo mensagem de sucesso "Material adicionado com sucesso."

  Cenário: Sai do sistema
    Quando acesso o menu "Sair"
