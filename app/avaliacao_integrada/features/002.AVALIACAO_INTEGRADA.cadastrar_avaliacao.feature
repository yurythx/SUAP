# -*- coding: utf-8 -*-
# language: pt
Funcionalidade: Avaliação

  @do_document
  Cenário: Adicionar Avaliação
    Ação executada pelo membro do grupo Aplicador de Avaliação Institucional.

    Dado acesso a página "/"
    Quando realizo o login com o usuário "8181002" e senha "abcd"
    E acesso o menu "Des. Institucional::Avaliação Integrada::Avaliações"
    Então vejo a página "Avaliações"
    E vejo o botão "Adicionar Avaliação"
    Quando clico no botão "Adicionar Avaliação"
    Então vejo a página "Adicionar Avaliação"
    Quando preencho o formulário com os dados
      | Campo                    | Tipo                   | Valor                             |
      | Tipos                    | checkbox multiplo      | Autoavaliação Institucional       |
      | Ano de Referência        | Autocomplete           | 2020                              |
      | Nome                     | Texto                  | Avaliação Integrada CIPE-CPA 2020 |
      | Descrição                | TextArea               | Descrição sobre a avaliação       |
      | Data de Início           | Data                   | 01/01/2020                        |
      | Data de Término          | Data                   | 20/10/2020                        |
      | Segmentos                | FilteredSelectMultiple | DOCENTE                           |
    E clico no botão "Salvar"
    Então vejo mensagem de sucesso "Cadastro realizado com sucesso."

  @do_document
  Cenário: Gerar Público-alvo da Avaliação
    Ação executada pelo membro do grupo Aplicador de Avaliação Institucional.

    Quando a data do sistema for "08/01/2020"
    E acesso o menu "Des. Institucional::Avaliação Integrada::Avaliações"
    Então vejo a página "Avaliações"
    Quando clico no ícone de exibição
    Então vejo a página "Avaliação Integrada CIPE-CPA 2020"
    Quando clico no botão "Reprocessar Público-Alvo"
    Então vejo mensagem de sucesso "Público-Alvo reprocessado com sucesso."
    Quando acesso o menu "Sair"


  #@do_document
  #Cenário: Responder Avaliação Integrada
  #  Ação executada pelo membro de um dos segmentos respondentes.

  #  Dado acesso a página "/"
  #  Quando a data do sistema for "08/01/2020"
  #  E realizo o login com o usuário "2020100104778" e senha "abcd"
  #  E clico no link "Você precisa responder a Avaliação Integrada CIPE-CPA 2020"
  #  Então vejo a página "Avaliação Integrada CIPE-CPA 2020"
