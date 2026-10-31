# -*- coding: utf-8 -*-
# language: pt

Funcionalidade: Indicar Responsável pela Execução da Demanda

      @do_document
      Cenário: Indicar Responsável pela Execução da Demanda
      É preciso indicar o servidor responsável pela realização da demanda. Os próprios servidores do campus de atendimento também podem assumir a demanda.
      Ação executada pelo Gerente de Demandas Externas ou Coordenador de Demandas Externas.
         Dado acesso a página "/"
         Quando realizo o login com o usuário "120002" e senha "abcd"
         E acesso o menu "Extensão::Demandas Externas::Demandas"
         Então vejo a página "Demandas Externas"
         Quando clico na aba "Em Espera"
         E olho a linha "Nome do Cidadão"
         E clico no ícone de exibição
         Então vejo a página "Visualizar Demanda"
         Quando clico no botão "Atribuir Responsável"
        Então vejo a página "Atribuir Demanda"
        E vejo os seguintes campos no formulário
               | Campo                           | Tipo        |
               | Responsável                     | Autocomplete       |
               | Data Prevista de Atendimento    | Data        |

             E vejo o botão "Salvar"

        Quando preencho o formulário com os dados
               | Campo                           | Tipo              | Valor                       |
               | Responsável                     | Autocomplete             | 120003  |
               | Data Prevista de Atendimento    | Data              | 30/06/2020             |



             E clico no botão "Salvar"

         Então vejo mensagem de sucesso "Demanda atribuída com sucesso."

      Cenário: Sai do sistema
        Quando acesso o menu "Sair"
