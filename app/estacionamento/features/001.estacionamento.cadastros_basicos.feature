# -*- coding: utf-8 -*-
# language: pt

Funcionalidade: Cadastros Básicos
    Cadastros básicos do módulo de estacionamento

  Cenário: Configuração inicial para execução dos cenários do estacionamento
    Dado os dados básicos do estacionamento
    Dado acesso a página "/"
    Quando realizo o login com o usuário "admin" e senha "abc"


  @do_document
  Cenário: Cadastrar Marcas de Veículo
    Quando acesso o menu "Administração::Estacionamento::Marca de Veículos"
     Então vejo o botão "Adicionar Marca de Veículo"
    Quando clico no botão "Adicionar Marca de Veículo"
     Então vejo a página "Adicionar Marca de Veículo"
    Quando preencho o formulário com os dados
            | Campo              | Tipo            | Valor  |
            | Nome               | Texto           | Randon |
         E clico no botão "Salvar"
     Então vejo mensagem de sucesso "Cadastro realizado com sucesso."

  @do_document
  Cenário: Cadastrar Modelo de Veículo
    Quando acesso o menu "Administração::Estacionamento::Modelos de Veículos"
     Então vejo o botão "Adicionar Modelo de Veículo"
    Quando clico no botão "Adicionar Modelo de Veículo"
     Então vejo a página "Adicionar Modelo de Veículo"
    Quando preencho o formulário com os dados
            | Campo              | Tipo            | Valor                |
            | Nome               | Texto           | Carga Seca           |
            | Marca              | Autocomplete    | Randon               |
            | Tipo e Espécie     | Autocomplete    | Semi-reboque - Carga |
         E clico no botão "Salvar"
     Então vejo mensagem de sucesso "Cadastro realizado com sucesso."


  @do_document
  Cenário: Cadastrar Veículo
    Quando acesso o menu "Administração::Estacionamento::Veículos"
     Então vejo o botão "Adicionar Veículo"
    Quando clico no botão "Adicionar Veículo"
     Então vejo a página "Adicionar Veículo"
#      Dado Curso no campo Modelo
    Quando preencho o formulário com os dados
            | Campo                | Tipo                   | Valor             |
            | Modelo               | Autocomplete           | Carga Seca        |
            | Cor                  | Autocomplete           | Branca            |
            | Ano                  | Texto                  | 1996              |
            | Placa                | Texto                  | MOV-6111          |
            | Condutores           | Autocomplete Multiplo  | 1111111           |


         E clico no botão "Salvar"
     Então vejo mensagem de sucesso "Cadastro realizado com sucesso."
