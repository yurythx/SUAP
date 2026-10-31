# -*- coding: utf-8 -*-
# language: pt

Funcionalidade: Atividades ligadas a operações com macroprocesso no PDI

     Cenário: Monta os dados básicos para rodar os testes dessa feature
         Dada os dados básicos para o planejamento
            E os usuários do planejamento
            E um PDI cadastrado
            E as unidades administrativas
       Quando acesso a página "/"
            E a data do sistema for "01/01/2018"
            E realizo o login com o usuário "109001" e senha "abcd"


      Cenario: Acessa o PDI 2018 - 2022
          Dada a atual página
        Quando acesso o menu "Des. Institucional::Planejamento Institucional::PDI"
             E olho para a listagem
             E olho a linha "2018"
             E clico no botão "Detalhar"


      Cenário: Verifica a existência da aba Macroprocesso
          Dada a atual página
         Então vejo a aba "Macroprocessos"
        Quando clico na aba "Macroprocessos"
             E olho para a aba "Macroprocessos"
         Então vejo o botão "Associar Macroprocessos ao PDI"
        Quando clico no botão "Associar Macroprocessos ao PDI"
             E olho para o popup
         Então vejo a página "PDI - 2018 a 2022"
             E vejo o botão "Adicionar apenas selecionados"


      Cenário: Avalia a associação de macroprocessos
          Dada a atual página
        Quando olho para o popup
             E olho para a tabela
         Então vejo a linha "Macroprocesso 1"
             E vejo a linha "Macroprocesso 2"
        Quando olho a linha "Macroprocesso 1"
             E clico no checkbox
             E olho para a página
             E clico no botão "Adicionar apenas selecionados"
         Então vejo mensagem de sucesso "Operação realizada."
        Quando olho para a aba "Macroprocessos"
             E olho para a tabela
         Então vejo a linha "Macroprocesso 1"
        Quando olho para a página
             E olho para a aba "Macroprocessos"
             E clico no botão "Associar Macroprocessos ao PDI"
             E olho para o popup
             E olho para a tabela
             E olho a linha "Macroprocesso 1"
             E clico no checkbox
             E olho para a página
             E clico no botão "Adicionar apenas selecionados"
         Então vejo mensagem de sucesso "Operação realizada."
        Quando clico na aba "Macroprocessos"
             E olho para a aba "Macroprocessos"
         Então vejo o texto "Não existem macroprocessos associadas a este PDI."

      @do_document
      Cenario: Realiza a associação dos macroprocessos
          Dada a atual página
        Quando olho para a aba "Macroprocessos"
             E clico no botão "Associar Macroprocessos ao PDI"
             E olho para o popup
         Então vejo a página "PDI - 2018 a 2022"
        Quando olho para a tabela
             E olho a linha "Macroprocesso 1"
             E clico no checkbox
             E olho para a página
             E olho para a tabela
             E olho a linha "Macroprocesso 2"
             E clico no checkbox
             E olho para a página
             E clico no botão "Adicionar apenas selecionados"
         Então vejo mensagem de sucesso "Operação realizada."
        Quando olho para a aba "Macroprocessos"
             E olho para a tabela
         Então vejo a linha "Macroprocesso 1"
             E vejo a linha "Macroprocesso 2"

