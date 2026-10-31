# -*- coding: utf-8 -*-
# language: pt
Funcionalidade: Cadastro de Segmentos Respondentes

  Cenário: Adicionando os usuários necessários para os testes avaliação de cursos
    Dado os seguintes usuários
      | Nome               | Matrícula      | Setor | Lotação | Email                         | CPF            | Senha | Grupo                                          |
      | Avaliador de Curso |         103111 | CZN   | CZN     | avaliadorcurso@ifrn.edu.br  | 000.103.111-22 | abcd  | Avaliador de Cursos|
    E os dados basicos cadastrados da avaliacao de cursos
  @do_document
  Cenário: Cadastro de Segmentos Respondentes
    Ação executada pelo Avaliador de Curso.

    Dado acesso a página "/"
    Quando realizo o login com o usuário "103111" e senha "abcd"
    E acesso o menu "Ensino::Pedagogia::Avaliação de Cursos::Segmentos Respondentes"
    Então vejo a página "Segmentos Respondentes"
    E vejo o botão "Adicionar Segmento Respondente"
    Quando clico no botão "Adicionar Segmento Respondente"
    Então vejo a página "Adicionar Segmento Respondente"
    E vejo os seguintes campos no formulário
      | Campo     | Tipo     |
      | Descrição    | Texto    |
      | Forma de Identificação | TextArea |
    E vejo o botão "Salvar"
    Quando preencho o formulário com os dados
      | Campo     | Tipo     | Valor                          |
      | Descrição    | Texto    | Aluno         |
      | Forma de Identificação | TextArea | Alunos com matriz (matriculado no SUAP ou migrados do Q-Acadêmico) com situação "Matriculado " em cursos das modalidades selecionadas no cadastro do questionário. |
    E clico no botão "Salvar"
    Então vejo mensagem de sucesso "Cadastro realizado com sucesso."

  Cenário: Sai do sistema
    Quando acesso o menu "Sair"
