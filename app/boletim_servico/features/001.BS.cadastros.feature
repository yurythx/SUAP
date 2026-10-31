# -*- coding: utf-8 -*-
# language: pt
Funcionalidade: Cadastros

  Cenário: Adicionando os usuários necessários para os testes
    Dado os seguintes usuários
      | Nome              | Matrícula | Setor | Lotação | Email                | CPF            | Senha | Grupo                                    |
      | Gerente Sistemico | 100051    | RAIZ  | RAIZ    | gerente1@ifrn.edu.br | 000.100.051-96 | abcd  | Gerente Sistêmico de Boletins de Serviço |
      | Gerente Campus    | 100052    | CZN   | CZN     | gerente2@ifrn.edu.br | 000.100.052-77 | abcd  | Gerente de Boletins de Serviço           |
      | Servidor          | 100053    | CZN   | CZN     | servidor@ifrn.edu.br | 921.158.970-30 | abcd  | Servidor                                 |

  @do_document
  Cenário: Cadastro de Boletins de Serviço Programados por um Gerente Sistêmico de Boletins de Serviço.

    Dado acesso a página "/"
    Quando a data do sistema for "01/11/2019"
    Quando realizo o login com o usuário "100051" e senha "abcd"
    E acesso o menu "Administração::Boletins de Serviço::Gerenciar Boletins"
    Então vejo a página "Boletins de Serviço Programados"
    E vejo o botão "Adicionar Boletim de Serviço Programado"
    Quando clico no botão "Adicionar Boletim de Serviço Programado"
    Então vejo a página "Adicionar Boletim de Serviço Programado"
    Quando preencho o formulário com os dados
      | Campo                         | Tipo                   | Valor                        |
      | Título                        | Texto                  | Boletim de Serviço - RAIZ/IF |
      | Tipos de documentos           | FilteredSelectMultiple | Portaria, Ofício             |
      | Nível de Acesso de Documentos | checkbox multiplo      | Restrito, Público            |
      | Gerar boletim diário?         | checkbox               |                              |
      | Gerar boletim semanal?        | checkbox               |                              |
      | Gerar boletim mensal?         | checkbox               | marcar                       |
    E preencho o formulário inline "Configurações de Setor no Boletim" com os dados
      | Campo                     | Tipo  | Valor |
      | Nome do Setor no Boletim  | Texto | RAIZ  |
      | Ordem do Setor no Boletim | Texto | 1     |
      | Setor do Documento        | lista | RAIZ  |
    E clico no botão "Salvar"
    Então vejo mensagem de sucesso "Cadastro realizado com sucesso."
    Quando acesso o menu "Administração::Boletins de Serviço::Gerenciar Boletins"
    E olho para a tabela
    Então vejo a linha "Boletim de Serviço - RAIZ/IF"
    Quando acesso o menu "Sair"


  Cenário: Listagem de Boletins Programados
    Testando se o Gerente de Boletins de Serviço pode ver o cadastrado pelo Sistêmico em outro campus

    Dado acesso a página "/"
    Quando realizo o login com o usuário "100052" e senha "abcd"
    E acesso o menu "Administração::Boletins de Serviço::Gerenciar Boletins"
    Então vejo a página "Boletins de Serviço Programados"
    Então vejo mensagem de alerta "Nenhum Boletim de Serviço Programado encontrado."


  Cenário: Cadastro de Boletins de Serviço Programados por um Gerente de Boletins de Serviço.

    Então vejo o botão "Adicionar Boletim de Serviço Programado"
    Quando clico no botão "Adicionar Boletim de Serviço Programado"
    Então vejo a página "Adicionar Boletim de Serviço Programado"
    Quando preencho o formulário com os dados
      | Campo                         | Tipo                   | Valor                        |
      | Título                        | Texto                  | Boletim de Serviço - CZN/IF  |
      | Tipos de documentos           | FilteredSelectMultiple | Portaria, Ofício             |
      | Nível de Acesso de Documentos | checkbox multiplo      | Sigiloso, Restrito           |
      | Gerar boletim diário?         | checkbox               |                              |
      | Gerar boletim semanal?        | checkbox               |                              |
      | Gerar boletim mensal?         | checkbox               | marcar                       |
    E preencho o formulário inline "Configurações de Setor no Boletim" com os dados
      | Campo                     | Tipo  | Valor |
      | Nome do Setor no Boletim  | Texto | CZN   |
      | Ordem do Setor no Boletim | Texto | 1     |
      | Setor do Documento        | lista | CZN   |
    E clico no botão "Salvar"
    Então vejo mensagem de sucesso "Cadastro realizado com sucesso."
    Quando acesso o menu "Administração::Boletins de Serviço::Gerenciar Boletins"
    E olho para a tabela
    Então vejo a linha "Boletim de Serviço - CZN/IF"
    Quando acesso o menu "Sair"
