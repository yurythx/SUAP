# -*- coding: utf-8 -*-
# language: pt
Funcionalidade: Gerenciar Exercício Externo
  Gerenciamento de Cessão, Requisição, Exercício Provisório e Cooperação técnica

  Cenário: Adicionando os usuários necessários para os testes Exercício Externo
    Dado os seguintes usuários
      | Nome               | Matrícula      | Setor | Lotação | Email                         | CPF            | Senha | Grupo                                       |
      | Coord_RH Sistemico | 9999100        | CZN   | CZN     | coordrhsistemico@ifrn.edu.br  | 619.993.140-85 | abcd  | Coordenador de Gestão de Pessoas Sistêmico  |
    E os dados basicos cadastrados


  @do_document
  Cenário: Cadastro de Exercício Externo

    Dado acesso a página "/"
    Quando realizo o login com o usuário "9999100" e senha "abcd"
    E acesso o menu "Gestão de Pessoas::Administração de Pessoal::Acompanhamento Funcional::Exercício Externo"
    Então vejo a página "Exercícios Externos"
    Quando clico no botão "Adicionar Exercício Externo"
    Então vejo a página "Adicionar Exercício Externo"
    Quando preencho o formulário com os dados
      | Campo               | Tipo            | Valor           |
      | Servidor Cedido     | Autocomplete    | 1111111         |
      | Tipo de Exercício   | lista           | Cessão          |
      | Instituição Destino | Autocomplete    | TRE/RN          |

    E clico no botão "Salvar"
    Então vejo mensagem de sucesso "Cadastro realizado com sucesso."
    Quando acesso o menu "Sair"


  @do_document
  Cenário: Registro de frequência do servidor

    Dado acesso a página "/"
    Quando realizo o login com o usuário "1111111" e senha "abc"
    E acesso o menu "Gestão de Pessoas::Administração de Pessoal::Acompanhamento Funcional::Exercício Externo"
    Então vejo a página "Exercícios Externos"
    Quando clico na aba "Meus Processos"
    E olho a linha "Servidor 1 (1111111)"
    E clico no ícone de exibição
    Então vejo a página "Detalhes de Exercício Externo"
    Quando clico no link "Adicionar Frequência"
    E olho para o popup
    E preencho o formulário com os dados
      | Campo               | Tipo            | Valor           |
      | Data Inicial        | Data            | 01/01/2020      |
      | Data Final          | Data            | 31/01/2020      |
      | Arquivo             | arquivo         | arquivo.pdf            |

    E clico no botão "Salvar"
    Então vejo mensagem de sucesso "Frequência adicionada com sucesso"
    Quando olho para a tabela
    E olho a linha "01/01/2020 a 31/01/2020"
