## -*- coding: utf-8 -*-
## language: pt
#Funcionalidade: Cadastro de Convênio
#
#  Cenário: Adicionando os usuários necessários para os testes
#    Dado os dados básicos para convênios
#    E os seguintes usuários
#      | Nome                   | Matrícula | Setor | Lotação | Email                            | CPF            | Senha | Grupo                           |
#      | Op_Convenios Sistêmico |    190001 | CZN   | CZN     | opconveniossistemico@ifrn.edu.br | 645.433.195-40 | abcd  | Operador de Convênios Sistêmico |
#      | Op_Convenios Campus    |    190002 | CZN   | CZN     | opconvenioscampuso@ifrn.edu.br   | 188.135.291-98 | abcd  | Operador de Convênios           |
#
#  @do_document
#  Cenário: Cadastro de Convênio
#    Cadastro de um convênio firmado pela Pró-reitoria de Extensão com uma instituição.
#    Ação executada pelo Operador de Convênios Sistêmico ou Operador de Convênios.
#
#    Dado acesso a página "/"
#    Quando realizo o login com o usuário "190001" e senha "abcd"
#    E acesso o menu "Extensão::Convênios::Convênios"
#    Então vejo a página "Convênios"
#    E vejo o botão "Adicionar Convênio"
#    Quando clico no botão "Adicionar Convênio"
#    Então vejo a página "Adicionar Convênio"
#    E vejo os seguintes campos no formulário
#      | Campo                  | Tipo                  |
#      | Número                 | Texto                 |
#      | Tipo                   | Lista                 |
#      | Situação               | Lista                 |
#      | Conveniadas            | Autocomplete Multiplo |
#      | Campus                 | Lista                 |
#      | Interveniente          | Autocomplete          |
#      | Data de Início         | Data                 |
#      | Data de Término        | Data                 |
#      | Objeto                 | TextArea              |
#      | Continuado             | checkbox              |
#      | Usa Recurso Financeiro | checkbox              |
#    E vejo o botão "Salvar"
#    Quando preencho o formulário com os dados
#      | Campo                  | Tipo                  | Valor                                   |
#      | Número                 | Texto                 | 1020/2020                               |
#      | Tipo                   | Lista                 | Aprendizagem                            |
#      | Situação               | Lista                 | Vigente                                 |
#      | Conveniadas            | Autocomplete Multiplo | Pessoa Jurídica                         |
#      | Campus                 | Lista                 | CZN                                     |
#      | Data de Início         | Data                 | 01/01/2020                              |
#      | Data de Término        | Data                 | 31/12/2020                              |
#      | Objeto                 | TextArea              | descrição do objeto do convênio firmado |
#      | Continuado             | checkbox              | sim                                     |
#      | Usa Recurso Financeiro | checkbox              | sim                                     |
#    E clico no botão "Salvar"
#    Então vejo mensagem de sucesso "Convênio cadastrado com sucesso."
#
#  Cenário: Sai do sistema
#    Quando acesso o menu "Sair"
