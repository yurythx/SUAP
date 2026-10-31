# -*- coding: utf-8 -*-
# language: pt

Funcionalidade: Avaliações do Projeto de Ensino
      @do_document
      Cenário: Primeira Avaliação do Projeto
      O avaliador indicado realiza a avaliação do projeto.
      Ação executada pelo Avaliador do Projeto (servidor ou avaliador externo à instituição).
          Dado acesso a página "/"
        Quando realizo o login com o usuário "130005" e senha "abcd"
             E a data do sistema for "16/01/2018"
             E acesso o menu "Ensino::Projetos::Avaliar"
         Então vejo a página "Editais em Avaliação"
         Quando olho a linha "Nome do edital"
         E clico no link "CZN"
         Então vejo a página "Seleção de Projetos"
        Quando olho a linha "Título do projeto"
         Então vejo o botão "Avaliar"
        Quando clico no botão "Avaliar"
        Então vejo a página "Avaliação de Projeto"
        Quando preencho o formulário com os dados
               | Campo                               | Tipo                 | Valor                  |
               | Parecer                             | TextArea             | Parecer do avaliador A |

           E clico no botão "Enviar"
           Então vejo mensagem de sucesso "Projeto avaliado com sucesso."

      Cenário: Sai do sistema
        Quando acesso o menu "Sair"

      @do_document
      Cenário: Segunda Avaliação do Projeto
      O avaliador indicado realiza a avaliação do projeto.
      Ação executada pelo Avaliador do Projeto (servidor ou avaliador externo à instituição).
          Dado acesso a página "/"
        Quando realizo o login com o usuário "130006" e senha "abcd"
             E a data do sistema for "16/01/2018"
             E acesso o menu "Ensino::Projetos::Avaliar"
         Então vejo a página "Editais em Avaliação"
         Quando olho a linha "Nome do edital"
         E clico no link "CZN"
         Então vejo a página "Seleção de Projetos"
        Quando olho a linha "Título do projeto"
         Então vejo o botão "Avaliar"
        Quando clico no botão "Avaliar"
        Então vejo a página "Avaliação de Projeto"
        Quando preencho o formulário com os dados
               | Campo                               | Tipo                 | Valor                  |
               | Parecer                             | TextArea             | Parecer do avaliador B |

           E clico no botão "Enviar"
           Então vejo mensagem de sucesso "Projeto avaliado com sucesso."

      Cenário: Sai do sistema
        Quando acesso o menu "Sair"
