# -*- coding: utf-8 -*-
# language: pt
Funcionalidade: Cadastrar Avaliação do ENCCEJA

  @do_document
  Cenário: Cadastrar Avaliação do ENCCEJA
    Ação executada pelo membro do grupo Administrador ENCCEJA.

    Dado acesso a página "/"
    Quando realizo o login com o usuário "907008" e senha "abcd"
    E acesso o menu "Ensino::Certificados ENCCEJA::Avaliações"
    Então vejo a página "Avaliação"
    E vejo o botão "Adicionar Avaliações"
    Quando clico no botão "Adicionar Avaliações"
    Então vejo a página "Adicionar Avaliações"
    E vejo os seguintes campos no formulário
      | Campo                    | Tipo                   |
      | Ano                      | Autocomplete                  |
      | Tipo                | Lista                  |
      | Descrição do Edital                    | Textarea               |
      | Área de Conhecimento               | Texto               |
      | Redação              | Texto               |
    E vejo o botão "Salvar"
    Quando preencho o formulário com os dados
      | Campo                    | Tipo                   | Valor                           |
      | Ano                      | Autocomplete                  | 2020 |
      | Tipo                | Lista                  | Encceja Nacional |
      | Descrição do Edital                    | Textarea               | descrição da avaliação |
      | Área de Conhecimento               | Texto               | 5.00 |
      | Redação              | Texto               | 5.00 |
    E clico no botão "Salvar"
    Então vejo mensagem de sucesso "Cadastro realizado com sucesso."

  Cenário: Sai do sistema
    Quando acesso o menu "Sair"
