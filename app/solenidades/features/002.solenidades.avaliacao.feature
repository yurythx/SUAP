# -*- coding: utf-8 -*-
# language: pt

Funcionalidade: Atividades ligadas a avaliação de um agendamento de solenidade
    Essa funcionalidade verifica a avaliação de um agendamento de solenidade.

      Cenário: Avaliação de um Agendamento de Solenidade pelo usuário Operador de Gabinete Sistêmico
          Dado acesso a página "/"
        Quando realizo o login com o usuário "116006" e senha "abcd"
             E a data do sistema for "01/10/2018"
             E acesso o menu "Administração::Agendamento de solenidades"
         Então vejo a página "Agendamento de Solenidades"
             E vejo o texto "Mostrando 4 Agendamento de Solenidade"
        Quando olho para a tabela
         Então vejo a linha "Data"
             E vejo a linha "10 de Outubro de 2018"

             E vejo a linha "Hora de Início"
             E vejo a linha "08:00:00"

             E vejo a linha "Local"
             E vejo a linha "Local 1"
             E vejo a linha "Local 2"
             E vejo a linha "Local 3"
             E vejo a linha "Local 4"

             E vejo a linha "Descrição"

             E vejo a linha "Reitor/Representante"

             E vejo a linha "Solicitante"
             E vejo a linha "Operador Gabinete"
             E vejo a linha "Coordenador Comunicação"
             E vejo a linha "Coordenador Sistêmico"
             E vejo a linha "Pró-Reitor"

             E vejo a linha "Opções"
             E vejo o botão "Deferir"
             E vejo o botão "Indeferir"

      Cenário: Sai do sistema
        Quando acesso o menu "Sair"
