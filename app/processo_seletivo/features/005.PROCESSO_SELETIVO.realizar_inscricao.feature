# -*- coding: utf-8 -*-
# language: pt
Funcionalidade: Inscrição no Edital de Fiscais

  @do_document
  Cenário: Inscrição no Edital de Fiscais
    Ação executada pelo Servidor.

    Dado acesso a página "/"
    Quando a data do sistema for "10/07/2020"
    Quando realizo o login com o usuário "1221473" e senha "abcd"
    E clico no link "Inscrição para Fiscal de Concurso para Edital: Fiscal 2020 3/2020-CZN"
    Então vejo a página "Formulário de Inscrição para o edital Fiscal 2020 3/2020-CZN"
    Quando preencho o formulário com os dados
      | Campo                | Tipo     | Valor          |
      | Telefones            | Texto    | 84 1234-5678   |
      | Banco                | Texto    | BB             |
      | Número da Agência    | Texto    |            001 |
      | Tipo da Conta        | Lista    | Conta Corrente |
      | Número da Conta      | Texto    | 1234-5         |
      | Termo de Compromisso | checkbox | marcar         |
    E clico no botão "Salvar"
    Então vejo mensagem de sucesso "Inscrição realizada com sucesso."

  Cenário: Sai do sistema
    Quando acesso o menu "Sair"
