# -*- coding: utf-8 -*-
# language: pt

Funcionalidade: Cadastros Básicos
    Cadastros básicos do módulo de chaves


  Cenário: Configuração inicial para execução dos cenários de chaves
    Dado Salas e Servidores já existentes
    Dado acesso a página "/"
    Quando realizo o login com o usuário "admin" e senha "abc"


    #    Contexto: Solicitação de vaga de leito COVID já realizada
    #      Dado Solicitações já existente

    @do_document
    Cenário: Cadastrar Chaves
      Quando acesso o menu "Administração::Chaves::Chaves"
       Então vejo o botão "Adicionar Chave"
      Quando clico no botão "Adicionar Chave"
       Então vejo a página "Adicionar Chave"
      Quando preencho o formulário com os dados
              | Campo          | Tipo                   | Valor          |
              | Identificação  | Texto                  | AU-001         |
              | Sala           | Autocomplete           | Sala A1    |
              | Ativa          | checkbox               | Marcar         |
              | Vinculos       | Autocomplete Multiplo  | Servidor 1     |
           E clico no botão "Salvar"
       Então vejo mensagem de sucesso "Cadastro realizado com sucesso."
