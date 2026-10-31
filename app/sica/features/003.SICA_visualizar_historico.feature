# -*- coding: utf-8 -*-
# language: pt
Funcionalidade: Cadastro de Histórico

  @do_document
  Cenário: Cadastro de Histórico
    Ação executada pelo membro do grupo Coordenador de Registro Acadêmico - SICA.

    Dado acesso a página "/"
    E os dados básicos do sica
    Quando realizo o login com o usuário "802021" e senha "abcd"
    E acesso o menu "Ensino::Sica::Históricos"
    Então vejo a página "Históricos"
    Quando clico no ícone de exibição
    Então vejo a página "Aluno Sica (20101101011031)"

