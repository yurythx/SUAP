# -*- coding: utf-8 -*-
# language: pt

Funcionalidade: Atividades ligadas a criação de um agendamento de solenidade
    Essa funcionalidade verifica a criação de um agendamento de solenidade.

      Cenário: Monta os dados básicos e adiciona os usuários necessários para os testes
          Dado os seguintes usuários
              | Nome                                 | Matrícula | Setor    | Lotação  | Email           | CPF            | Senha | Grupo                                |
              | Operador de Gabinete                 | 116001    | DIAC/CEN | DIAC/CEN | d01@ifrn.edu.br | 000.116.001-01 | abcd  | Operador de Gabinete                 |
              | Coordenador de Comunicação           | 116002    | DIAC/CEN | DIAC/CEN | d02@ifrn.edu.br | 000.116.002-84 | abcd  | Coordenador de Comunicação           |
              | Coordenador de Comunicação Sistêmico | 116003    | DIAC/CZN | DIAC/CZN | d03@ifrn.edu.br | 000.116.003-65 | abcd  | Coordenador de Comunicação Sistêmico |
              | Pró-Reitor                           | 116004    | DIAC/CZN | DIAC/CZN | d04@ifrn.edu.br | 000.116.004-46 | abcd  | Pró-Reitor                           |
              | Servidor                             | 116005    | CZN      | CZN      | d05@ifrn.edu.br | 000.116.005-27 | abcd  | Servidor                             |
              | Operador de Gabinete Sistêmico       | 116006    | RAIZ     | RAIZ     | d06@ifrn.edu.br | 611.896.200-65 | abcd  | Operador de Gabinete Sistêmico       |
      @do_document
      Cenário: Criação de um Agendamento de Solenidade pelo usuário Operador de Gabinete
          Dado acesso a página "/"
        Quando realizo o login com o usuário "116001" e senha "abcd"
             E a data do sistema for "01/10/2018"
             E acesso o menu "Administração::Agendamento de solenidades"
         Então vejo a página "Agendamento de Solenidades"
             E vejo mensagem de alerta "Nenhum Agendamento de Solenidade encontrado."
        Quando clico no botão "Adicionar Agendamento de Solenidade"
         Então vejo a página "Adicionar Agendamento de Solenidade"
             E vejo os seguintes campos no formulário com as obrigatoriedades atendidas e preencho com
                 | Campo          | Tipo     | Obrigatório | Valor      |
                 | Data           | Data     | Sim         | 10/10/2018 |
                 | Hora de Início | Texto    | Sim         | 08:00      |
                 | Local          | Texto    | Sim         | Local 1    |
                 | Descrição      | Textarea | Sim         | Descrição  |
        Quando clico no botão "Salvar"
         Então vejo mensagem de sucesso "Agendamento de Solenidade cadastrado com sucesso."
             E vejo o texto "Solicitação Agendamento Solenidade 1"

      Cenário: Sai do sistema
        Quando acesso o menu "Sair"


      Cenário: Criação de um Agendamento de Solenidade
          Dado acesso a página "/"
        Quando realizo o login com o usuário "116002" e senha "abcd"
             E a data do sistema for "01/10/2018"
             E acesso o menu "Administração::Agendamento de solenidades"
         Então vejo a página "Agendamento de Solenidades"

      Cenário: Sai do sistema
        Quando acesso o menu "Sair"


      Cenário: Criação de um Agendamento de Solenidade pelo usuário Coordenador de Comunicação
          Dado acesso a página "/"
        Quando realizo o login com o usuário "116002" e senha "abcd"
             E a data do sistema for "01/10/2018"
             E acesso o menu "Administração::Agendamento de solenidades"
         Então vejo a página "Agendamento de Solenidades"
             E vejo o texto "Mostrando 1 Agendamento de Solenidade"
        Quando clico no botão "Adicionar Agendamento de Solenidade"
         Então vejo a página "Adicionar Agendamento de Solenidade"
             E vejo os seguintes campos no formulário com as obrigatoriedades atendidas e preencho com
                 | Campo          | Tipo     | Obrigatório | Valor      |
                 | Data           | Data     | Sim         | 10/10/2018 |
                 | Hora de Início | Texto    | Sim         | 08:00      |
                 | Local          | Texto    | Sim         | Local 2    |
                 | Descrição      | Textarea | Sim         | Descrição  |
        Quando clico no botão "Salvar"
         Então vejo mensagem de sucesso "Agendamento de Solenidade cadastrado com sucesso."
             E vejo o texto "Solicitação Agendamento Solenidade 2"

      Cenário: Sai do sistema
        Quando acesso o menu "Sair"


      @do_document
      Cenário: Criação de um Agendamento de Solenidade
          Dado acesso a página "/"
        Quando realizo o login com o usuário "116002" e senha "abcd"
             E a data do sistema for "01/10/2018"
             E acesso o menu "Administração::Agendamento de solenidades"
         Então vejo a página "Agendamento de Solenidades"
             E vejo o texto "Mostrando 2 Agendamento de Solenidade"
             E vejo o botão "Cancelar"

      Cenário: Sai do sistema
        Quando acesso o menu "Sair"


      Cenário: Criação de um Agendamento de Solenidade pelo usuário Coordenador de Comunicação Sistêmico
          Dado acesso a página "/"
        Quando realizo o login com o usuário "116003" e senha "abcd"
             E a data do sistema for "01/10/2018"
             E acesso o menu "Administração::Agendamento de solenidades"
         Então vejo a página "Agendamento de Solenidades"
             E vejo mensagem de alerta "Nenhum Agendamento de Solenidade encontrado."
        Quando clico no botão "Adicionar Agendamento de Solenidade"
         Então vejo a página "Adicionar Agendamento de Solenidade"
             E vejo os seguintes campos no formulário com as obrigatoriedades atendidas e preencho com
                 | Campo          | Tipo     | Obrigatório | Valor      |
                 | Data           | Data     | Sim         | 10/10/2018 |
                 | Hora de Início | Texto    | Sim         | 08:00      |
                 | Local          | Texto    | Sim         | Local 3    |
                 | Descrição      | Textarea | Sim         | Descrição  |
        Quando clico no botão "Salvar"
         Então vejo mensagem de sucesso "Agendamento de Solenidade cadastrado com sucesso."
             E vejo o texto "Solicitação Agendamento Solenidade 3"

      Cenário: Sai do sistema
        Quando acesso o menu "Sair"


      Cenário: Criação de um Agendamento de Solenidade pelo usuário Pró-Reitor
          Dado acesso a página "/"
        Quando realizo o login com o usuário "116004" e senha "abcd"
             E a data do sistema for "01/10/2018"
             E acesso o menu "Administração::Agendamento de solenidades"
         Então vejo a página "Agendamento de Solenidades"
             E vejo o texto "Mostrando 1 Agendamento de Solenidade"
        Quando clico no botão "Adicionar Agendamento de Solenidade"
         Então vejo a página "Adicionar Agendamento de Solenidade"
             E vejo os seguintes campos no formulário com as obrigatoriedades atendidas e preencho com
                 | Campo          | Tipo     | Obrigatório | Valor      |
                 | Data           | Data     | Sim         | 10/10/2018 |
                 | Hora de Início | Texto    | Sim         | 08:00      |
                 | Local          | Texto    | Sim         | Local 4    |
                 | Descrição      | Textarea | Sim         | Descrição  |
        Quando clico no botão "Salvar"
         Então vejo mensagem de sucesso "Agendamento de Solenidade cadastrado com sucesso."
             E vejo o texto "Solicitação Agendamento Solenidade 4"

      Cenário: Sai do sistema
        Quando acesso o menu "Sair"
