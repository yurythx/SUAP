# -*- coding: utf-8 -*-
# language: pt

Funcionalidade: Atividades ligadas a inclusão de unidades administrativas no PDI

     Cenário: Monta os dados básicos para rodar os testes dessa feature
         Dada os dados básicos para o planejamento
            E os usuários do planejamento
            E um PDI cadastrado
       Quando acesso a página "/"
            E a data do sistema for "01/01/2018"
            E realizo o login com o usuário "109001" e senha "abcd"


      Cenario: Acessa o PDI 2018 - 2022
          Dada a atual página
        Quando acesso o menu "Des. Institucional::Planejamento Institucional::PDI"
             E olho para a listagem
             E olho a linha "2018"
             E clico no botão "Detalhar"


       Cenário: Verifica a existência da aba e adição de Unidades Administrativas
          Dada a atual página
         Então vejo a página "PDI - 2018 a 2022"
             E vejo a aba "Unidades Administrativas"
        Quando clico na aba "Unidades Administrativas"
             E olho para a aba "Unidades Administrativas"

         Então vejo o botão "Incluir Unidade Administrativa"
         Quando clico no botão "Incluir Unidade Administrativa"
         E olho para o popup
         Então vejo os seguintes campos no formulário
               | Campo                 | Tipo         |
               | Tipo                  | Lista        |
               | Setor                 | Autocomplete |
               | Setores Participantes | Lista        |
             E vejo o botão "Salvar"
        Quando clico no botão "Salvar"
             E olho para o popup
         Então vejo os seguintes erros no formulário
               | Campo   | Tipo         | Mensagem                 |
               | Tipo    | Lista        | Este campo é obrigatório |
               | Setor   | Autocomplete | Este campo é obrigatório |
        Quando fecho o popup
         Então vejo a página "PDI - 2018 a 2022"

      @do_document
      Cenário: Adiciona a unidade administrativa A1
          Dada a atual página
        Quando clico no botão "Incluir Unidade Administrativa"
             E olho para o popup
             E preencho o formulário com os dados
               | Campo | Tipo         | Valor    |
               | Tipo  | Lista        | Pró-Reitoria |
               | Setor | Autocomplete | A1       |

             E clico no botão "Salvar"
         Então vejo mensagem de sucesso "Unidade administrativa salva."


   Esquema do Cenário: Adiciona a unidade administrativa <Setor>
          Dada a atual página
        Quando clico no botão "Incluir Unidade Administrativa"
             E olho para o popup
             E preencho o formulário com os dados
               | Campo | Tipo         | Valor   |
               | Setor | Autocomplete | <Setor> |
               | Tipo  | Lista        | <Tipo>  |
             E clico no botão "Salvar"
         Então vejo mensagem de sucesso "Unidade administrativa salva."
        Exemplos:
           | Tipo          | Setor |
           | Pró-Reitoria  | A2    |
           | Campus        | B1    |
           | Campus        | B2    |
           | Campus        | C1    |
           | Campus        | C2    |


      Cenário: Verifica a possibilidade de adicionar uma unidade administrativa já cadastrada
          Dada a atual página
        Quando clico no botão "Incluir Unidade Administrativa"
             E olho para o popup
             E preencho o formulário com os dados
               | Campo | Tipo         | Valor        |
               | Setor | Autocomplete | A1           |
               | Tipo  | Lista        | Pró-Reitoria |
             E clico no botão "Salvar"
             E olho para o popup
         Então vejo os seguintes erros no formulário
               | Campo   | Tipo         | Mensagem                                                     |
               | Setor   | Autocomplete | Unidade Administrativa com este Setor Equivalente já existe para este PDI. |
        Quando fecho o popup


   Esquema do Cenário: Verifica se o setor <Setor> foi cadastrado corretamente
          Dada a atual página
        Quando olho para a aba "Unidades Administrativas"
             E olho para a tabela
         Então vejo a linha "<Setor>"
        Exemplos:
          | Setor |
          | A1    |
          | A2    |
          | B1    |
          | B2    |
          | C1    |
          | C2    |
