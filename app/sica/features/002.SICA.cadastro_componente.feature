# -*- coding: utf-8 -*-
# language: pt
Funcionalidade: Cadastro de Componente

  @do_document
  Cenário: Cadastro de Componente
    Ação executada pelo membro do grupo Coordenador de Registro Acadêmico - SICA.

    Dado acesso a página "/"
    Quando realizo o login com o usuário "802021" e senha "abcd"
    E acesso o menu "Ensino::Sica::Componentes"
    Então vejo a página "Componentes"
    E vejo o botão "Adicionar Componente"
    Quando clico no botão "Adicionar Componente"
    Então vejo a página "Adicionar Componente"
    E vejo os seguintes campos no formulário
      | Campo                    | Tipo                   |
      | Código | Texto |
      | Nome      | Texto        |
      | Sigla | Texto        |
    E vejo o botão "Salvar"
    Quando preencho o formulário com os dados
      | Campo                    | Tipo                   | Valor                           |
      | Código | Texto | 125 |
      | Nome      | Texto        | Geologia de Minas |
      | Sigla | Texto        | GEO.MIN |
    E clico no botão "Salvar"
    Então vejo mensagem de sucesso "Cadastro realizado com sucesso."

  Cenário: Sai do sistema
    Quando acesso o menu "Sair"
