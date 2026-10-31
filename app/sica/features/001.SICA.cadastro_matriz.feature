# -*- coding: utf-8 -*-
# language: pt
Funcionalidade: Cadastro de Matriz

  Cenário: Adicionando os usuários necessários para os testes sica
    Dado os seguintes usuários
      | Nome                 | Matrícula | Setor | Lotação | Email                            | CPF            | Senha | Grupo                                |
      | Coordenador Registro | 802021     | CZN   | CZN     | coordenador_ra@ifrn.edu.br       | 000.802.021-36 | abcd  | Coordenador de Registro Acadêmico - SICA               |
      | Aluno SICA           | 20101101011031 | CZN   | CZN     | aluno_sica@ifrn.edu.br          | 411.610.130-32 | abcd  | Aluno                                          |
  @do_document
  Cenário: Cadastrar Matriz
    Ação executada pelo membro do grupo Coordenador de Registro Acadêmico - SICA.

    Dado acesso a página "/"
    Quando realizo o login com o usuário "802021" e senha "abcd"
    E acesso o menu "Ensino::Sica::Matrizes"
    Então vejo a página "Matrizes"
    E vejo o botão "Adicionar Matriz"
    Quando clico no botão "Adicionar Matriz"
    Então vejo a página "Adicionar Matriz"
    E vejo os seguintes campos no formulário
      | Campo    | Tipo         |
      | Código | Texto |
      | Nome      | Texto        |
      | Carga-Horária Obrigatória | Texto        |
      | Carga-Horária de Estágio   | Texto        |
      | Reconhecimento | Textarea        |
    E vejo o botão "Salvar"
    Quando preencho o formulário com os dados
      | Campo    | Tipo         | Valor |
      | Código | Texto | 32 |
      | Nome      | Texto        | Técnico em Geologia |
      | Carga-Horária Obrigatória | Texto        | 3465 |
      | Reconhecimento | Textarea        | Curso aprovado através da portaria nº 50, de 07 de julho de 1981 – Ministério da Educação e Cultura/Secretaria de Ensino de 1º e 2º graus, publicada no D.O.U., de 10 de julho de 1981, Seção I.|
    E clico no botão "Salvar"

  Cenário: Sai do sistema
    Quando acesso o menu "Sair"
