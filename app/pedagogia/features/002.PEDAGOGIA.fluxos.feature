# -*- coding: utf-8 -*-
# language: pt
Funcionalidade: Fluxos

  Cenário: Adicionando os usuários necessários para os testes PEDAGOGIA
    Dado os seguintes usuários
      | Nome                 | Matrícula      | Setor | Lotação | Email                            | CPF            | Senha | Grupo                   |
      | Estagiario Pedagogia |         103112 | CZN   | CZN     | estagiario_pedagogia@ifrn.edu.br | 315.103.000-90 | abcd  | Estagiária de Pedagoria |
      | Aluno AvaliacaoCurso | 20191101011031 | CZN   | CZN     | aluno_ae@ifrn.edu.br             | 101.011.031-40 | abcd  | Aluno                   |
    E os dados basicos cadastrados da pedagogia

  @do_document
  Cenário: Responder Avaliação de curso
    Ação executada pelo próprio aluno.

    Dado acesso a página "/"
    Quando a data do sistema for "10/01/2019"
    Quando realizo o login com o usuário "20191101011031" e senha "abcd"
    E clico no link "Responda ao questionário de Avaliação do Curso."
    Então vejo a página "Avaliação Processual dos Cursos"
    E vejo o botão "Continuar"
    Quando clico no botão "Continuar"
    Então vejo a página "Avaliação Processual dos Cursos"
    E vejo o botão "Salvar"
    Quando clico no botão "Salvar"
    Então vejo mensagem de sucesso "Questionário salvo com sucesso."

  Cenário: Sai do sistema
    Quando acesso o menu "Sair"
