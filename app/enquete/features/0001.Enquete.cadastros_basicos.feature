# -*- coding: utf-8 -*-
# language: pt

Funcionalidade: Cadastros Básicos
    Cadastros Básicos do módulo de enquetes

  Cenário: Adiciona os usuarios necessarios para essa funcionalidade
    Dado os usuarios de Enquete
    Quando a data do sistema for "02/08/2019"


  @do_document
  Cenario: Cadastrar enquete
    Dado acesso a página "/"
    Quando realizo o login com o usuário "CriadorEnquete" e senha "abcd"
    Quando acesso a página "/admin/enquete/enquete/"
    E clico no botão "Adicionar Enquete"
    E preencho o formulário com os dados
        | Campo          | Tipo                  | Valor                    |
        | Título         | Texto                 | Enquete de Teste         |
        | Descrição      | Textarea              | Enquete de Teste         |
        | Data de Início | Data                  | 01/08/2019               |
        | Data de Término| Data                  | 05/08/2019               |
        | Responsáveis   | Autocomplete Multiplo | CriadorEnquete           |
        | Público        | Autocomplete          | Servidores               |
        | Ordem          | Texto                 | 1                        |
        | Texto          | Textarea              | Categoria de Enquete     |
    E clico no botão "Escolher todos"
    E clico no botão "Salvar"
    Então vejo mensagem de sucesso "Enquete cadastrada com sucesso"
