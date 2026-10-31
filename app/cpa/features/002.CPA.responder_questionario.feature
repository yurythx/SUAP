# -*- coding: utf-8 -*-
# language: pt
Funcionalidade: Responder Questionário

  @do_document
  Cenário: Responder Questionário CPA
    Ação executada por servidores e alunos.
    Quando a data do sistema for "10/01/2020"
    Dado acesso a página "/"
    Quando realizo o login com o usuário "802023" e senha "abcd"
    E clico no link "Realize sua avaliação institucional (0%)."
    Então vejo a página "Novo Questionário"
    E vejo os seguintes campos no formulário
      | Campo                              | Tipo     |
      | 1 - Descrição da primeira pergunta | Textarea |
    E vejo o botão "Enviar"
    Quando preencho o formulário com os dados
      | Campo                              | Tipo     | Valor                             |
      | 1 - Descrição da primeira pergunta | Textarea | resposta para a primeira pergunta |
    E clico no botão "Enviar"
    Então vejo mensagem de sucesso "Respostas salvas com sucesso."
