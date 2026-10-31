# -*- coding: utf-8 -*-
# language: pt
Funcionalidade: Cadastrar Evento

  @do_document
  Cenário: Cadastrar Evento
    Ação executada pelo Administrador.

    Dado acesso a página "/"
    Quando realizo o login com o usuário "admin" e senha "abc"
    E acesso o menu "Administração::Orçamento::Cadastros::Eventos::Eventos"
    Então vejo a página "Eventos"
    E vejo o botão "Adicionar Evento"
    Quando clico no botão "Adicionar Evento"
    Então vejo a página "Adicionar Evento"
    E vejo os seguintes campos no formulário
      | Campo                    | Tipo                   |
      | Código                      | Texto                  |
      | Nome                      | Texto                  |
      | Descrição                      | Textarea                 |
    E vejo o botão "Salvar"
    Quando preencho o formulário com os dados
      | Campo                    | Tipo                   | Valor                           |
      | Código                      | Texto                  | 520415 |
      | Nome                      | Texto                  | REG.DA CONTA CORRENTE-21142000 |
      | Descrição                      | Textarea                 | REGULARIZACAO DE C/C DA CONTA 21142.00.00 |
    E clico no botão "Salvar"
    Então vejo mensagem de sucesso "Cadastro realizado com sucesso."

  Cenário: Sai do sistema
    Quando acesso o menu "Sair"
