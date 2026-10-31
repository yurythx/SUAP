# -*- coding: utf-8 -*-
# language: pt

Funcionalidade: Registro da Conclusão do Projeto de Ensino

      @do_document
      Cenário: Registro da Conclusão do Projeto
      Após o preenchimento de todos os dados sobre a execução do projeto, o coordenador do projeto pode registrar a conclusão do mesmo.
      Ação executada pelo Servidor (coordenador do projeto).
          Dado acesso a página "/"

        Quando realizo o login com o usuário "130003" e senha "abcd"
             E a data do sistema for "20/01/2018"
             E acesso o menu "Ensino::Projetos::Meus projetos"
         Então vejo a página "Meus projetos"
             E vejo o botão "Visualizar"
        Quando clico no botão "Visualizar"
         Então vejo a página "Projeto de Ensino"
         Quando clico na aba "Conclusão"
         Então vejo o botão "Registrar Conclusão"
         Quando clico no botão "Registrar Conclusão"
            E olho para o popup
            Então vejo os seguintes campos no formulário
               | Campo                                                      | Tipo     |
               | Resultados Alcançados                                      | TextArea |
               | Disseminação dos Resultados                                | TextArea |
               | Observação                                                 | TextArea |

             E vejo o botão "Salvar"
         Quando preencho o formulário com os dados
               | Campo                                                      | Tipo     | Valor                               |
               | Resultados Alcançados                                      | TextArea | descricao dos resultados alcancados |
               | Disseminação dos Resultados                                | TextArea | descricao da disseminacao           |
               | Observação                                                 | TextArea | Obs sobre a conclusão               |


             E clico no botão "Salvar"

         Então vejo mensagem de sucesso "Conclusão do projeto registrada com sucesso."

      Cenário: Sai do sistema
        Quando acesso o menu "Sair"
