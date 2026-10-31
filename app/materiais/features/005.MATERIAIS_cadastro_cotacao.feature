# -*- coding: utf-8 -*-
# language: pt
Funcionalidade: Cadastrar de Cotação do Material

  @do_document
  Cenário: Cadastrar Cotação do Material
    Ação executada por um membro do grupo Gerenciador do Catálogo de Materiais.

    Dado acesso a página "/"
    Quando realizo o login com o usuário "907002" e senha "abcd"
    E acesso o menu "Administração::Materiais::Materiais"
    Então vejo a página "Materiais"
    Quando clico no link "Adicionar Cotação"
    Então vejo a página "Adicionar Cotação"
    E vejo os seguintes campos no formulário
      | Campo    | Tipo         |
      | Modalidade      | Lista        |
      | Valor      | Texto        |
      | Data      | Data         |
    E vejo o botão "Salvar Material"
    Quando preencho o formulário com os dados
      | Campo    | Tipo         | Valor |
      | Modalidade      | Lista        | Internet |
      | Valor      | Texto        | 500,00 |
      | Data      | Data         | 01/02/2020 |
      | Fornecedor | Autocomplete | Pessoa                           |
      | Site       | TextArea     | http://www.sitefornecedor.com.br |
    E clico no botão "Salvar Material"
    Então vejo mensagem de sucesso "Cotação adicionada com sucesso."

  Cenário: Sai do sistema
    Quando acesso o menu "Sair"
