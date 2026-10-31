# -*- coding: utf-8 -*-
# language: pt
Funcionalidade: Cadastrar Cotação do Item

  @do_document
  Cenário: Cadastrar Cotação do Item
    Ação executada pelo membro do grupo Gerenciador do Catálogo de Materiais.

    Dado acesso a página "/"
    Quando realizo o login com o usuário "907002" e senha "abcd"
    E acesso o menu "Administração::Materiais::Materiais"
    Então vejo a página "Materiais"
    Quando olho para a listagem
    E olho a linha "Informática"
    Então vejo o botão "Adicionar Cotação"
    Quando clico no botão "Adicionar Cotação"
    Então vejo os seguintes campos no formulário
      | Campo      | Tipo  |
      | Modalidade | Lista |
      | Valor      | texto |
      | Data       | Data  |
    E vejo o botão "Salvar Material"
    Quando preencho o formulário com os dados
      | Campo      | Tipo         | Valor                            |
      | Modalidade | Lista        | Internet                         |
      | Valor      | texto        |                            15,50 |
      | Fornecedor | Autocomplete | Pessoa                           |
      | Site       | TextArea     | http://www.sitefornecedor.com.br |
    E clico no botão "Salvar Material"
    Então vejo mensagem de sucesso "Cotação adicionada com sucesso."

  Cenário: Sai do sistema
    Quando acesso o menu "Sair"
