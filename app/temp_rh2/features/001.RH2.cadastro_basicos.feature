# -*- coding: utf-8 -*-
# language: pt
Funcionalidade: Cadastros

  Cenário: Adicionando os usuários necessários para os testes TEMP_RH2
    Dado os dados básicos para competição desportiva
    E os seguintes usuários
      | Nome                | Matrícula | Setor | Lotação | Email                           | CPF            | Senha | Grupo                                            |
      | Coord Competicao    | 337002    | CZN   | CZN     | coord_competicao@ifrn.edu.br    | 347.666.110-55 | abcd  | Coordenador de Competições Desportivas Sistêmico |
      | Servidor Competicao | 337003    | CZN   | CZN     | servidor_competicao@ifrn.edu.br | 352.629.450-07 | abcd  | Servidor                                         |
    E os dados de sexo do servidor está populado

  @do_document
  Cenário: Modalidades Desportivas
  Ação executada por um membro do grupo Coordenador de Competições Desportivas Sistêmico.

    Dado acesso a página "/"
    Quando realizo o login com o usuário "337002" e senha "abcd"
    E acesso o menu "Gestão de Pessoas::Atenção a Saúde do Servidor::Competições Desportivas::Cadastros::Modalidades"
    Então vejo a página "Modalidades Desportivas"
    E vejo o botão "Adicionar Modalidade Desportiva"
    Quando clico no botão "Adicionar Modalidade Desportiva"
    Então vejo a página "Adicionar Modalidade Desportiva"
    E vejo os seguintes campos no formulário
      | Campo | Tipo  |
      | Nome  | Texto |
      | Sexo  | Lista |
      | Tipo  | Lista |
    E vejo o botão "Salvar"
    Quando preencho o formulário com os dados
      | Campo | Tipo  | Valor     |
      | Nome  | Texto | Futebol   |
      | Sexo  | Lista | Masculino |
      | Tipo  | Lista | Coletivo  |
    E clico no botão "Salvar"
    Então vejo mensagem de sucesso "Cadastro realizado com sucesso."

  @do_document
  Cenário: Categorias
  Ação executada por um membro do grupo Coordenador de Competições Desportivas Sistêmico.

    Dado acesso a página "/"
    Quando acesso o menu "Gestão de Pessoas::Atenção a Saúde do Servidor::Competições Desportivas::Cadastros::Categorias"
    Então vejo a página "Categorias"
    E vejo o botão "Adicionar Categoria"
    Quando clico no botão "Adicionar Categoria"
    Então vejo a página "Adicionar Categoria"
    E vejo os seguintes campos no formulário
      | Campo                    | Tipo  |
      | Nome                     | Texto |
      | Limite de idade inferior | Texto |
      | Limite de idade superior | Texto |
    E vejo o botão "Salvar"
    Quando preencho o formulário com os dados
      | Campo                    | Tipo  | Valor |
      | Nome                     | Texto | B     |
      | Limite de idade inferior | Texto | 31    |
      | Limite de idade superior | Texto | 40    |
    E clico no botão "Salvar"
    Então vejo mensagem de sucesso "Cadastro realizado com sucesso."

  @do_document
  Cenário: Competição Desportiva
  Ação executada pelo membro do grupo Coordenador de Competições Desportivas Sistêmico.

    Dado acesso a página "/"
    Quando acesso o menu "Gestão de Pessoas::Atenção a Saúde do Servidor::Competições Desportivas::Competição Desportiva"
    Então vejo a página "Competições Desportivas"
    E vejo o botão "Adicionar Competição Desportiva"
    Quando clico no botão "Adicionar Competição Desportiva"
    Então vejo a página "Adicionar Competição Desportiva"
    E vejo os seguintes campos no formulário
      | Campo                                                                | Tipo              |
      | Nome                                                                 | Texto             |
      | Descrição                                                            | Textarea          |
      | Ano                                                                  | Autocomplete      |
      | Modalidades                                                          | checkbox multiplo |
      | Quantidade Máxima de modalidades coletivas                           | Texto             |
      | Quantidade Máxima modalidades Independente se individual ou coletiva | Texto             |
      | Quantidade Máxima modalidades individuais                            | Texto             |
      | Provas                                                               | checkbox multiplo |
      | Categorias                                                           | checkbox multiplo |
      | Data inicial do período de inscrições                                | Data              |
      | Data final do período de inscrições                                  | Data              |
      | Data inicial do período de validação                                 | Data              |
      | Data final do período de validação                                   | Data              |
      | Data inicial do período de confirmação dos inscritos                 | Data              |
      | Data final do período de confirmação dos inscritos                   | Data              |
      | Data inicial do período de reajustes (pelo representante do campus)  | Data              |
      | Data final do período de reajustes (pelo representante do campus)    | Data              |
      | Data de homologação e consolidação das inscrições                    | Data              |
      | Data inicial do período 1 de jogos                                   | Data              |
      | Data final do período 1 de jogos                                     | Data              |

    E vejo o botão "Salvar"
    Quando preencho o formulário com os dados
      | Campo                                                                | Tipo              | Valor                                    |
      | Nome                                                                 | Texto             | JICS                                     |
      | Descrição                                                            | Textarea          | Campeonato do servidores 2020            |
      | Ano                                                                  | Autocomplete      | 2020                                     |
      | Modalidades                                                          | checkbox multiplo | Futebol - Masculino - Coletivo           |
      | Quantidade Máxima de modalidades coletivas                           | Texto             | 2                                        |
      | Quantidade Máxima modalidades Independente se individual ou coletiva | Texto             | 3                                        |
      | Quantidade Máxima modalidades individuais                            | Texto             | 3                                        |
      | Provas                                                               | checkbox multiplo | 25m Livre - Natação - Individual, 200m Rasos - Atletismo - Individual, Fifa 18 - Jogos Eletrônicos - Individual |
      | Categorias                                                           | checkbox multiplo | Categoria B de 31 à 40 anos              |
      | Data inicial do período de inscrições                                | Data              | 01/07/2020                               |
      | Data final do período de inscrições                                  | Data              | 15/08/2020                               |
      | Data inicial do período de validação                                 | Data              | 16/08/2020                               |
      | Data final do período de validação                                   | Data              | 20/08/2020                               |
      | Data inicial do período de confirmação dos inscritos                 | Data              | 21/08/2020                               |
      | Data final do período de confirmação dos inscritos                   | Data              | 25/08/2020                               |
      | Data inicial do período de reajustes (pelo representante do campus)  | Data              | 26/08/2020                               |
      | Data final do período de reajustes (pelo representante do campus)    | Data              | 30/08/2020                               |
      | Data de homologação e consolidação das inscrições                    | Data              | 31/08/2020                               |
      | Data inicial do período 1 de jogos                                   | Data              | 01/09/2020                               |
      | Data final do período 1 de jogos                                     | Data              | 30/09/2020                               |
    E clico no botão "Salvar"
    Então vejo mensagem de sucesso "Cadastro realizado com sucesso."
