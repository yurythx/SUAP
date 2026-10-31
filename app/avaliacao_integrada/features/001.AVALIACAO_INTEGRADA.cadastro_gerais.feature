# -*- coding: utf-8 -*-
# language: pt
Funcionalidade: Cadastro Básicos

  Cenário: Adicionando os usuários necessários para os testes avaliação integrada
    Dado os dados básicos para avaliacao integrada
    E os seguintes usuários
      | Nome                  | Matrícula     | Setor | Lotação | Email                            | CPF            | Senha | Grupo                                |
      | Adm AvalInt           | 8181001       | CZN   | CZN     | adm_avalint@ifrn.edu.br       | 050.063.460-27 | abcd  | Administrador de Avaliação Institucional               |
      | Aplicador AvalInt     | 8181002       | CZN   | CZN     | aplic_avalint@ifrn.edu.br | 442.409.050-79 | abcd  | Aplicador de Avaliação Institucional |
      | Respondente AvalInt   | 2020100104778 | CZN   | CZN     | respondente_avalint@ifrn.edu.br     | 840.322.080-42 | abcd  | Aluno                |
    Dado acesso a página "/"
    Quando realizo o login com o usuário "8181001" e senha "abcd"
  @do_document
  Cenário: Cadastrar Eixos
    Ação executada por um membro do grupo Administrador de Avaliação Institucional.

    Quando acesso o menu "Des. Institucional::Avaliação Integrada::Cadastros::Eixos"
    Então vejo a página "Eixos"
    E vejo o botão "Adicionar Eixo"
    Quando clico no botão "Adicionar Eixo"
    Então vejo a página "Adicionar Eixo"
    Quando preencho o formulário com os dados
      | Campo           | Tipo                   | Valor                         |
      | Descrição       | Texto                  | Caracterização do respondente |
      | Ordem           | Lista                  | 1                             |
    E clico no botão "Salvar"
    Então vejo mensagem de sucesso "Cadastro realizado com sucesso."

  @do_document
  Cenário: Cadastrar Dimensões
    Ação executada por um membro do grupo Administrador de Avaliação Institucional.
    Quando acesso o menu "Des. Institucional::Avaliação Integrada::Cadastros::Dimensões"
    Então vejo a página "Dimensões"
    E vejo o botão "Adicionar Dimensão"
    Quando clico no botão "Adicionar Dimensão"
    Então vejo a página "Adicionar Dimensão"
    Quando preencho o formulário com os dados
      | Campo          | Tipo          | Valor                         |
      | Eixo           | Autocomplete  | Caracterização do respondente |
      | Descrição      | Texto         | Caracterização profissional   |
      | Ordem          | Texto         | 1                             |
    E clico no botão "Salvar"
    Então vejo mensagem de sucesso "Cadastro realizado com sucesso."

  @do_document
  Cenário: Cadastrar Macroprocessos
    Ação executada por um membro do grupo Administrador de Avaliação Institucional.
    Quando acesso o menu "Des. Institucional::Avaliação Integrada::Cadastros::Macroprocessos"
    Então vejo a página "Macroprocessos"
    E vejo o botão "Adicionar Macroprocesso"
    Quando clico no botão "Adicionar Macroprocesso"
    Então vejo a página "Adicionar Macroprocesso"
    Quando preencho o formulário com os dados
      | Campo           | Tipo           | Valor                       |
      | Dimensão        | Autocomplete   | Caracterização profissional |
      | Descrição       | Texto          | Caracterização profissional |
    E clico no botão "Salvar"
    Então vejo mensagem de sucesso "Cadastro realizado com sucesso."

  @do_document
  Cenário: Cadastrar Tipos de Avaliação
    Ação executada por um membro do grupo Administrador de Avaliação Institucional.
    Quando acesso o menu "Des. Institucional::Avaliação Integrada::Cadastros::Tipos de Avaliação"
    Então vejo a página "Tipos de Avaliação"
    E vejo o botão "Adicionar Tipo de Avaliação"
    Quando clico no botão "Adicionar Tipo de Avaliação"
    Então vejo a página "Adicionar Tipo de Avaliação"
    Quando preencho o formulário com os dados
      | Campo                    | Tipo                   | Valor                           |
      | Descrição                | Texto                  | Autoavaliação Institucional |
    E clico no botão "Salvar"
    Então vejo mensagem de sucesso "Cadastro realizado com sucesso."

  @do_document
  Cenário: Cadastrar Indicador
    Ação executada por um membro do grupo Administrador de Avaliação Institucional.
    Quando acesso o menu "Des. Institucional::Avaliação Integrada::Indicadores"
    Então vejo a página "Indicadores"
    E vejo o botão "Adicionar Indicador"
    Quando clico no botão "Adicionar Indicador"
    Então vejo a página "Adicionar Indicador"
    Quando preencho o formulário com os dados
      | Campo                     | Tipo                   | Valor                                    |
      | Anos de Referência        | checkbox multiplo      | 2020                                     |
      | Macroprocesso             | Autocomplete           | Caracterização profissional              |
      | Denominação do Indicador  | Texto                  | Indicador de Caracterização profissional |
      | Critério de Análise       | Texto                  | Descrição do critério                    |
      | Subsídio p/ Avaliações    | checkbox multiplo      | Autoavaliação Institucional              |
      | Segmentos                 | FilteredSelectMultiple | DOCENTE                                  |
      | Escala Likert             | Lista                  | Escala Padrão                            |

    E clico no botão "Salvar"
    Então vejo mensagem de sucesso "Cadastro realizado com sucesso."
