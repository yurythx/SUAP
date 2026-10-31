# -*- coding: utf-8 -*-
# language: pt

Funcionalidade: Finalização do Projeto de Ensino

      @do_document
      Cenário: Finalização do Projeto
      Caso o projeto não possua mais pendências, o mesmo pode ser finalizado pelo coordenador do projeto.
      Ação executada pelo Servidor (coordenador do projeto).
          Dado acesso a página "/"
        Quando realizo o login com o usuário "130003" e senha "abcd"
             E a data do sistema for "20/01/2018"
             E acesso o menu "Ensino::Projetos::Meus projetos"
         Então vejo a página "Meus projetos"
             E vejo o botão "Visualizar"
        Quando clico no botão "Visualizar"
         Então vejo a página "Projeto de Ensino"
         E vejo o botão "Finalizar Projeto"
         Quando clico no botão "Finalizar Projeto"
             Então vejo mensagem de sucesso "Conclusão finalizada com sucesso."

      Cenário: Sai do sistema
        Quando acesso o menu "Sair"
