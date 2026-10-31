# -*- coding: utf-8 -*-
# language: pt
Funcionalidade: Cadastrar Tipo de Edital Regularizador

  @do_document
  Cenário: Cadastrar Tipo de Edital Regularizador
    Ação executada pelo membro do grupo Coordenador de Editais de Adesão Sistêmico.

    Dado acesso a página "/"
    Quando a data do sistema for "10/06/2020"
    Quando realizo o login com o usuário "1221472" e senha "abcd"
    E acesso o menu "Ensino::Processos Seletivos::Tipos de Editais Regularizadores"
    Então vejo a página "Tipos de Edital de Adesão"
    E vejo o botão "Adicionar Tipo do Edital de Adesão"
    Quando clico no botão "Adicionar Tipo do Edital de Adesão"
    Então vejo a página "Adicionar Tipo do Edital de Adesão"
    Quando preencho o formulário com os dados
      | Campo | Tipo  | Valor                        |
      | Nome  | Texto | Edital de Seleção de Fiscais |
    E clico no botão "Salvar"
    Então vejo mensagem de sucesso "Cadastro realizado com sucesso."
