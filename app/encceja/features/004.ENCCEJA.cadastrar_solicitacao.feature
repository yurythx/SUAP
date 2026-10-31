# -*- coding: utf-8 -*-
# language: pt
Funcionalidade: Cadastrar Solicitação do ENCCEJA

  @do_document
  Cenário: Cadastrar Solicitação do ENCCEJA
    Ação executada pelo membro do grupo Certificador ENCCEJA.

    Dado acesso a página "/"
    Quando realizo o login com o usuário "907009" e senha "abcd"
    E acesso o menu "Ensino::Certificados ENCCEJA::Solicitações"
    Então vejo a página "Solicitações"
    E vejo o botão "Adicionar Solicitação"
    Quando clico no botão "Adicionar Solicitação"
    Então vejo a página "Adicionar Solicitação"
    E vejo os seguintes campos no formulário
      | Campo                    | Tipo                   |
      | Configuração                      | Autocomplete                  |
      | Campus                      | Autocomplete                  |
      | Nome             | Texto               |
      | CPF             | Texto               |
      | Data de Nascimento             | Data                |
      | Avaliação da Redação                     | Autocomplete                  |
      | Pontuação da Redação                      | Texto                  |
      | Área do Conhecimento                      | Autocomplete                  |
      | Avaliação                      | Autocomplete                  |
      | Pontuação                      | Texto                  |
    E vejo o botão "Salvar"
    Quando preencho o formulário com os dados
    | Campo                    | Tipo                   | Valor                           |
    | Configuração                      | Autocomplete                  | ENCCEJA 2020 |
  | Campus                      | Autocomplete                  | CZN |
  | Nome             | Texto               | Nome do candidato |
  | CPF             | Texto               |  685.937.210-95 |
  | Data de Nascimento             | Data                | 01/06/2000 |
  | Avaliação da Redação                     | Autocomplete                  | Encceja |
  | Pontuação da Redação                      | Texto                  | 7.00 |
  | Área do Conhecimento                      | Autocomplete                  | Linguagens, Códigos e suas Tecnologias |
  | Avaliação                      | Autocomplete                  | Encceja |
  | Pontuação                      | Texto                  | 8.00 |


    E clico no botão "Salvar"
    Então vejo mensagem de sucesso "Cadastro realizado com sucesso."

  Cenário: Sai do sistema
    Quando acesso o menu "Sair"

