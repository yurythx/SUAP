# -*- coding: utf-8 -*-
# language: pt

Funcionalidade: Fluxos
  Fluxos do módulo de enquetes

  Cenário: Adiciona os usuarios necessarios para essa funcionalidade
    Dado os usuarios de Enquete
    Quando a data do sistema for "02/08/2019"

  @do_document
  Cenario: Adicionar pergunta à enquete
    Dado acesso a página "/"
    Quando realizo o login com o usuário "CriadorEnquete" e senha "abcd"
    E acesso a página "/admin/enquete/enquete/"
    E clico no ícone de exibição
    E clico no botão "Adicionar Pergunta"
    E olho para o popup
    E preencho o formulário com os dados
        | Campo              | Tipo                  | Valor                    |
        | Ordem              | Texto                 | 1                        |
        | Título da Pergunta | Textarea              | Exemplo de Pergunta      |
    E clico no botão "Salvar"
    Então vejo mensagem de sucesso "Pergunta adicionada com sucesso"


  @do_document
  Cenario: Publicar enquete
    Dado acesso a página "/"
    Quando acesso a página "/admin/enquete/enquete/"
    E clico no botão "Publicar"
    Então vejo mensagem de sucesso "Enquete publicada com sucesso"
    Quando acesso o menu "Sair"


  @do_document
  Cenário: Responder enquete
    Dado acesso a página "/"
    Quando realizo o login com o usuário "1111111" e senha "abc"
    Quando clico no link "Responda à Enquete"
    E preencho o formulário com os dados
        | Campo                   | Tipo           | Valor                    |
        | #1 Exemplo de Pergunta  | Textarea       | Resposta da pergunta     |
    E clico no botão "Enviar"
    Então vejo mensagem de sucesso "Enquete respondida com sucesso"
    Quando acesso o menu "Sair"

  @do_document
  Cenario: Despublicar enquete
    Dado acesso a página "/"
    Quando realizo o login com o usuário "CriadorEnquete" e senha "abcd"
    E acesso a página "/admin/enquete/enquete/"
    E clico no ícone de exibição
    E clico no botão "Despublicar"
    Então vejo mensagem de sucesso "Enquete despublicada com sucesso"

  @do_document
  Cenario: Visualizar resultados de enquete
    Dado acesso a página "/"
    Quando acesso a página "/admin/enquete/enquete/"
    E clico no botão "Ver Resultados"
    Então vejo a página "Resultados da Enquete"
