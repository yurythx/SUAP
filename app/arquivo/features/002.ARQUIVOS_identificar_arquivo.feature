# -*- coding: utf-8 -*-
# language: pt
Funcionalidade: Identificar Arquivo

  @do_document
  Cenário: Identificar Arquivo
    Ação executada pelo membro do grupo Identificador de Arquivos.

    Dado acesso a página "/"
    Quando realizo o login com o usuário "101011" e senha "abcd"
    E acesso o menu "Gestão de Pessoas::Administração de Pessoal::Assentamento Funcional::Arquivos Pendentes"
    Então vejo a página "Arquivos Pendentes"
    Quando clico no ícone de exibição
    Então vejo a página "Arquivos Pendentes do Servidor: Servidor do Assentamento Funcional (101013)"
    Quando clico no ícone de exibição
    Então vejo a página "Identificar Arquivo: Servidor do Assentamento Funcional (101013)"
    E vejo os seguintes campos no formulário
      | Campo    | Tipo         |
      | Tipo de Arquivo | Autocomplete |
      | Ação      | radio        |
    E vejo o botão "Salvar"
    Quando preencho o formulário com os dados
      | Campo    | Tipo         | Valor |
      | Tipo de Arquivo | Autocomplete | Alteração de férias |
      | Ação      | radio        | Identificar |
    E clico no botão "Salvar"
    Então vejo mensagem de sucesso "Arquivo Identificado com sucesso!"

  Cenário: Sai do sistema
    Quando acesso o menu "Sair"
