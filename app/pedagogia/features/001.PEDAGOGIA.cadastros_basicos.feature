# -*- coding: utf-8 -*-
# language: pt
Funcionalidade: Cadastros Básicos

  Cenário: Adicionando os usuários necessários para os testes PEDAGOGIA
    Dado os seguintes usuários
      | Nome                 | Matrícula      | Setor | Lotação | Email                            | CPF            | Senha | Grupo                   |
      | Estagiario Pedagogia |         103112 | CZN   | CZN     | estagiario_pedagogia@ifrn.edu.br | 315.103.000-90 | abcd  | Estagiária de Pedagoria |
      | Aluno AvaliacaoCurso | 20191101011031 | CZN   | CZN     | aluno_ae@ifrn.edu.br             | 101.011.031-40 | abcd  | Aluno                   |
    E os dados basicos cadastrados da pedagogia

  @do_document
  Cenário: Questionários de Matriz
    Ação executada por membro do grupo Estagiária de Pedagogia.

    Dado acesso a página "/"
    Quando a data do sistema for "01/01/2019"
    Quando realizo o login com o usuário "103112" e senha "abcd"
    E acesso o menu "Ensino::Pedagogia::Avaliação de Cursos::Questionários"
    Então vejo a página "Questionários de Matrizes"
    E vejo o botão "Adicionar Questionário de Matriz"
    Quando clico no botão "Adicionar Questionário de Matriz"
    Então vejo a página "Adicionar Questionário de Matriz"
    E vejo os seguintes campos no formulário
      | Campo     | Tipo                  |
      | Descrição | Texto                 |
      | Cursos    | Autocomplete multiplo |
      | Período   | Texto                 |
    E vejo o botão "Salvar"
    Quando preencho o formulário com os dados
      | Campo     | Tipo                  | Valor             |
      | Descrição | Texto                 | Novo questionário |
      | Cursos    | Autocomplete multiplo | TECINF            |
      | Período   | Texto                 |                 1 |
    E clico no botão "Salvar"
    Então vejo mensagem de sucesso "Cadastro realizado com sucesso."

  @do_document
  Cenário: Períodos de Resposta
    Ação executada por membro do grupo Estagiária de Pedagogia.

    Dado acesso a página "/"
    Quando acesso o menu "Ensino::Pedagogia::Avaliação de Cursos::Período de Resposta"
    Então vejo a página "Períodos de Resposta"
    E vejo o botão "Adicionar Período de Resposta"
    Quando clico no botão "Adicionar Período de Resposta"
    Então vejo a página "Adicionar Período de Resposta"
    E vejo os seguintes campos no formulário
      | Campo           | Tipo         |
      | Ano             | Autocomplete |
      | Data de Início  | Data        |
      | Data de Término | Data        |
    E vejo o botão "Salvar"
    Quando preencho o formulário com os dados
      | Campo           | Tipo         | Valor      |
      | Ano             | Autocomplete |       2019 |
      | Data de Início  | Data        | 02/01/2019 |
      | Data de Término | Data        | 30/04/2019 |
    E clico no botão "Salvar"
    Então vejo mensagem de sucesso "Cadastro realizado com sucesso."
