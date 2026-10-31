# -*- coding: utf-8 -*-
# language: pt

Funcionalidade: Validar Processo de Compra
      @do_document
      Cenário: Validar Processo de Compra
      Ação executada pelo membro do grupo Validador de Compras.
          Dado acesso a página "/"
        Quando a data do sistema for "02/03/2020"
        Quando realizo o login com o usuário "907003" e senha "abcd"
         E acesso o menu "Administração::Compras::Compras"
         Então vejo a página "Processos de Compra"
         Quando clico no link "Descrição do processo de compra"
         Então vejo a página "Descrição do processo de compra"
         Quando clico no link "CZN"
         Então vejo a página "Descrição do processo de compra - CZN"
         E vejo o botão "Validar Processo de Compra"
         Quando clico no botão "Validar Processo de Compra"
         Então vejo mensagem de sucesso "Processo validado com sucesso."

      Cenário: Sai do sistema
        Quando acesso o menu "Sair"
