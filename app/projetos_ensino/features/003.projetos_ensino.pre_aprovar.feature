# -*- coding: utf-8 -*-
# language: pt

Funcionalidade: Pré-Avaliação do Projeto de Ensino

      @do_document
      Cenário: Pré-Avaliação do Projeto
      A pré-avaliação consiste em uma verificação inicial do projeto em questão, analisando se o proposto está de acordo com o previsto no edital e se as informações obrigatórias foram devidamente prestadas,
      como descrição de metas e atividades, planejamento de gastos e anexos obrigatórios.
      Ação executada pelo Coordenador de Projetos de Ensino.
          Dado acesso a página "/"
        Quando realizo o login com o usuário "130002" e senha "abcd"
             E a data do sistema for "12/01/2018"
             E acesso o menu "Ensino::Projetos::Pré-avaliar"
         Então vejo a página "Editais"
         Quando olho a linha "Nome do edital"
         E clico no ícone de exibição
         Então vejo a página "Pré-Seleção de Projetos - Nome do edital"
        Quando olho a linha "Título do projeto"
         Então vejo o botão "Pré-selecionar"
        Quando clico no botão "Pré-selecionar"
        Então vejo mensagem de sucesso "Projeto pré-avaliado com sucesso."

      Cenário: Sai do sistema
        Quando acesso o menu "Sair"
