# -*- coding: utf-8 -*-
# language: pt
Funcionalidade: Cadastros Básicos

  Cenário: Adicionando os usuários necessários para os testes convenios
    Dado os dados básicos para convênios
    E os seguintes usuários
      | Nome                   | Matrícula | Setor | Lotação | Email                            | CPF            | Senha | Grupo                           |
      | Op_Convenios Sistêmico |    190001 | CZN   | CZN     | opconveniossistemico@ifrn.edu.br | 000.190.001-38 | abcd  | Operador de Convênios Sistêmico |
      | Op_Convenios Campus    |    190002 | CZN   | CZN     | opconvenioscampuso@ifrn.edu.br   | 000.190.002-19 | abcd  | Operador de Convênios           |

  @do_document
  Cenário: Convênio
    Cadastro de um convênio firmado pela Pró-reitoria de Extensão com uma instituição.
    Ação executada pelo Operador de Convênios Sistêmico ou Operador de Convênios.

    Dado acesso a página "/"
    Quando realizo o login com o usuário "190001" e senha "abcd"
    E acesso o menu "Extensão::Convênios::Convênios"
    Então vejo a página "Convênios"
    E vejo o botão "Adicionar Convênio"
    Quando clico no botão "Adicionar Convênio"
    Então vejo a página "Adicionar Convênio"
    E vejo os seguintes campos no formulário
      | Campo                  | Tipo                  |
      | Número                 | Texto                 |
      | Tipo                   | Lista                 |
      | Situação               | Lista                 |
      | Conveniadas            | Autocomplete Multiplo |
      | Campus                 | Lista                 |
      | Interveniente          | Autocomplete          |
      | Data de Início         | Data                 |
      | Data de Término        | Data                 |
      | Objeto                 | TextArea              |
      | Continuado             | checkbox              |
      | Usa Recurso Financeiro | checkbox              |
    E vejo o botão "Salvar"
    Quando preencho o formulário com os dados
      | Campo                  | Tipo                  | Valor                                   |
      | Número                 | Texto                 | 1020/2020                               |
      | Tipo                   | Lista                 | Aprendizagem                            |
      | Situação               | Lista                 | Vigente                                 |
      | Conveniadas            | Autocomplete Multiplo | Pessoa J                                |
      | Campus                 | Lista                 | CZN                                     |
      | Data de Início         | Data                 | 01/01/2020                              |
      | Data de Término        | Data                 | 31/12/2020                              |
      | Objeto                 | TextArea              | descrição do objeto do convênio firmado |
      | Continuado             | checkbox              | sim                                     |
      | Usa Recurso Financeiro | checkbox              | sim                                     |
    E clico no botão "Salvar"
    Então vejo mensagem de sucesso "Convênio cadastrado com sucesso."
    Quando acesso o menu "Sair"

  @do_document
  Cenário: Aditivo do Convênio
    Cadastro de um aditivo de convênio firmado pela Pró-reitoria de Extensão com uma instituição.
    Ação executada pelo Operador de Convênios Sistêmico ou Operador de Convênios.

    Dado acesso a página "/"
    Quando realizo o login com o usuário "190002" e senha "abcd"
    E acesso o menu "Extensão::Convênios::Convênios"
    Então vejo a página "Convênios"
    Quando olho a linha "1020/2020"
    E clico no ícone de exibição
    Então vejo a página "Convênio 1020/2020"
    E vejo o botão "Adicionar Aditivo"
    Quando clico no botão "Adicionar Aditivo"
    Então vejo a página "Adicionar Aditivo"
    E vejo os seguintes campos no formulário
      | Campo              | Tipo     |
      | Número             | Texto    |
      | Objeto             | TextArea |
      | Data de Realização | Data     |
      | Data Inicial       | Data     |
      | Data Final         | Data     |
    E vejo o botão "Salvar"
    Quando preencho o formulário com os dados
      | Campo              | Tipo     | Valor                         |
      | Número             | Texto    | 01/2020                       |
      | Objeto             | TextArea | objeto do aditivo do convênio |
      | Data de Realização | Data     | 31/12/2020                    |
      | Data Inicial       | Data     | 01/01/2021                    |
      | Data Final         | Data     | 01/06/2021                    |
    E clico no botão "Salvar"
    Então vejo mensagem de sucesso "Aditivo adicionado com sucesso."

  @do_document
  Cenário: Anexo do Convênio
    Cadastro de um anexo de convênio firmado pela Pró-reitoria de Extensão com uma instituição.
    Ação executada pelo Operador de Convênios Sistêmico ou Operador de Convênios.

    Dado acesso a página "/"
    Quando acesso o menu "Extensão::Convênios::Convênios"
    Então vejo a página "Convênios"
    Quando olho a linha "1020/2020"
    E clico no ícone de exibição
    Então vejo a página "Convênio 1020/2020"
    E vejo o botão "Adicionar Anexo"
    Quando clico no botão "Adicionar Anexo"
    Então vejo a página "Adicionar Anexo"
    E vejo os seguintes campos no formulário
      | Campo     | Tipo         |
      | Tipo      | Autocomplete |
      | Descrição | Texto        |
    E vejo o botão "Salvar"
    Quando preencho o formulário com os dados
      | Campo     | Tipo         | Valor                                              |
      | Tipo      | Autocomplete | Arquivo Digitalizado/Convênio                      |
      | Descrição | Texto        | descrição sobre o anexo com informações do aditivo |
    E clico no botão "Salvar"
    Então vejo mensagem de sucesso "Anexo adicionado com sucesso. Submeta o arquivo digitalizado."
    E vejo os seguintes campos no formulário
      | Campo   | Tipo    |
      | Arquivo | Arquivo |
    E vejo o botão "Enviar"
    Quando preencho o formulário com os dados
      | Campo   | Tipo    | Valor     |
      | Arquivo | Arquivo | anexo.png |
    E clico no botão "Enviar"
    Então vejo mensagem de sucesso "Anexo enviado com sucesso."
