# -*- coding: utf-8 -*-
# language: pt
Funcionalidade: Cadastrar Edital de Adesão de Campus

  @do_document
  Cenário: Cadastrar Edital de Adesão de Campus
    Ação executada pelo membro do grupo Coordenador de Editais de Adesão Sistêmico.

    Dado acesso a página "/"
    Quando a data do sistema for "10/06/2020"
    Quando realizo o login com o usuário "1221472" e senha "abcd"
    E acesso o menu "Ensino::Processos Seletivos::Editais de Adesão por campus"
    Então vejo a página "Editais de Adesão Campus"
    E vejo o botão "Adicionar Edital de Adesão Campus"
    Quando clico no botão "Adicionar Edital de Adesão Campus"
    Então vejo a página "Adicionar Edital de Adesão Campus"
    Quando preencho o formulário com os dados
      | Campo                | Tipo         | Valor       |
      | Nome                 | Texto        | Fiscal 2020 |
      | Edital regulador     | Autocomplete | Nome        |
      | Número do Edital     | Texto        |           3 |
      | Ano do Edital        | Texto        |        2020 |
      | Campus               | Autocomplete | CZN         |
      | Data da inscrição    | Data     | 01/07/2020  |
      | Data de encerramento | Data     | 01/08/2020  |
    E clico no botão "Salvar"
    Então vejo mensagem de sucesso "Cadastro realizado com sucesso."
