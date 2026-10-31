# -*- coding: utf-8 -*-
# language: pt

Funcionalidade: Atividades ligadas a operações com ações associadas

       Cenário: Monta os dados básicos para rodar os testes dessa feature
         Dada os dados básicos para o planejamento
            E os usuários do planejamento
            E um PDI cadastrado
            E as unidades administrativas
            E os macroprocessos
            E os objetivos estratégicos
       Quando acesso a página "/"
            E a data do sistema for "01/01/2018"
            E realizo o login com o usuário "109001" e senha "abcd"


      Cenario: Acessa o PDI 2018 - 2022
          Dada a atual página
        Quando acesso o menu "Des. Institucional::Planejamento Institucional::PDI"
             E olho para a listagem
             E olho a linha "2018"
             E clico no botão "Detalhar"


      Cenário: Verifica a existência da aba Ações Associadas
          Dada a atual página
         Então vejo a aba "Ações Associadas"
        Quando clico na aba "Ações Associadas"
             E olho para a aba "Ações Associadas"
         Então vejo o botão "Associar Ação"
        
        
      @do_document
      Cenário: Avalia a associação de ações ao PDI
          Dada a atual página
        Quando clico na aba "Ações Associadas"
             E olho para a aba "Ações Associadas"
             E clico no botão "Associar Ação"
             E olho para o popup
         Então vejo a página "PDI - 2018 a 2022"
             E vejo o botão "Adicionar apenas selecionados"
        Quando clico no botão "Adicionar apenas selecionados"
             E olho para a página
         Então vejo mensagem de sucesso "Ações associados com sucesso."
        Quando olho para a aba "Ações Associadas"
         Então vejo o texto "Não existem ações associadas a este PDI."
        Quando clico no botão "Associar Ação"
             E olho para o popup
             E olho para a tabela
             E olho a linha "Ação 1"
             E clico no checkbox
             E olho para a página
             E clico no botão "Adicionar apenas selecionados"
         Então vejo mensagem de sucesso "Ações associados com sucesso."
        Quando olho para a aba "Ações Associadas"
             E olho para a tabela
         Então vejo a linha "Ação 1"

