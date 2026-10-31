# -*- coding: utf-8 -*-
# language: pt

Funcionalidade: Ponto.

      @do_document
      Cenário: Ponto
          Dado acesso a página "/"
        Quando realizo o login com o usuário "1111111" e senha "abc"
           E acesso a página "/ponto/frequencia_funcionario/"
           E preencho o formulário com os dados
              | Campo      | Tipo     | Valor                  |
              | Início     | Data     | 13/04/2020             |
              | Término    | Data     | 13/04/2020             |
        Quando clico no botão "Enviar"
             E clico no link "Anexar"
             E olho para o popup
         Então vejo a página "Anexar Documento"
             E vejo os seguintes campos no formulário com as obrigatoriedades atendidas e preencho com
               | Campo     | Tipo     | Obrigatório | Valor     |
               | Descrição | Textarea | Sim         | Edital 1  |
               | Anexo     | Arquivo  | Sim         | image.png |
        Quando clico no botão "Salvar"
         Então vejo mensagem de sucesso "Documento anexado."

      Cenário: Sai do sistema
        Quando acesso o menu "Sair"
