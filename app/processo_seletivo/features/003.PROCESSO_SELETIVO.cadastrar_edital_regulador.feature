# -*- coding: utf-8 -*-
# language: pt
Funcionalidade: Cadastrar Edital Regularizador

  @do_document
  Cenário: Cadastrar Edital Regularizador
    Ação executada pelo membro do grupo Coordenador de Editais de Adesão Sistêmico.

    Dado acesso a página "/"
    Quando a data do sistema for "10/06/2020"
    Quando realizo o login com o usuário "1221472" e senha "abcd"
    E acesso o menu "Ensino::Processos Seletivos::Editais Regularizadores"
    Então vejo a página "Editais de Adesão"
    E vejo o botão "Adicionar Edital de Adesão"
    Quando clico no botão "Adicionar Edital de Adesão"
    Então vejo a página "Adicionar Edital de Adesão"
    Quando preencho o formulário com os dados
      | Campo                    | Tipo         | Valor                        |
      | Nome                     | Texto        | Nome do edital regularizador |
      | Tipo                     | Autocomplete | Edital de Seleção de Fiscais |
      | Número do Edital         | Texto        |                            2 |
      | Ano do Edital            | Texto        |                         2020 |
      | Data de início da adesão | Data     | 01/07/2020                   |
      | Data limite para adesão  | Data     | 01/08/2020                   |
    E clico no botão "Salvar"
    Então vejo mensagem de sucesso "Cadastro realizado com sucesso."
