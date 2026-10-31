# -*- coding: utf-8 -*-
# language: pt

Funcionalidade: Avaliar Demanda Recebida

      @do_document
      Cenário: Avaliar Demanda da Comunidade
      É preciso fazer uma triagem nas demandas recebidas para só depois disponibilizar a visualização para a comunidade acadêmica.
      Ação executada pelo Gerente de Demandas Externas ou Coordenador de Demandas Externas.
         Dado acesso a página "/"
         Quando realizo o login com o usuário "120002" e senha "abcd"
         E acesso o menu "Extensão::Demandas Externas::Demandas"
         Então vejo a página "Demandas Externas"
         Quando clico na aba "Submetidas"
         E olho a linha "Nome do Cidadão"
         E clico no ícone de exibição
         Então vejo a página "Visualizar Demanda"
         Quando clico no botão "Aceitar"
        Então vejo mensagem de sucesso "Demanda aceita com sucesso."
