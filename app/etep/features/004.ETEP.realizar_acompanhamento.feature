# -*- coding: utf-8 -*-
# language: pt
Funcionalidade: Realizar Acompanhamento

  @do_document
  Cenário: Realizar Acompanhamento
    Ação executada pelo membro do grupo Membro ETEP. 
    Esse membro irá visualizar o cadastro registros dos acompanhamentos e 
    poderá realizar encaminhamento para os alunos que estão em acompanhamento.

    Dado acesso a página "/"
    Quando realizo o login com o usuário "111124" e senha "abcd"
    E acesso o menu "Ensino::ETEP::Acompanhamentos"
    Então vejo a página "Acompanhamento"
    Quando clico no ícone de exibição
    Então vejo a página "Acompanhamento de Aluno ETEP"
    Quando clico na aba "Registros"
    E olho para a aba "Registros"
    Então vejo o botão "Adicionar Registro"
    Quando clico no botão "Adicionar Registro"
    E olho para o popup
    Então vejo os seguintes campos no formulário
      | Campo     | Tipo     |
      | Descrição | Textarea |
      | Anexo     | Arquivo  |
      | Descrição | Textarea |
    E vejo o botão "Salvar"
    Quando preencho o formulário com os dados
      | Campo     | Tipo     | Valor                                                 |
      | Descrição | Textarea | Descrição do novo registro de acompanhamento do aluno |
    E clico no botão "Salvar"
    Então vejo mensagem de sucesso "Acompanhamento adicionado com sucesso."
    Quando clico na aba "Encaminhamentos"
    E olho para a aba "Encaminhamentos"
    Então vejo o botão "Adicionar Encaminhamento"
    Quando clico no botão "Adicionar Encaminhamento"
    Então vejo os seguintes campos no formulário
      | Campo           | Tipo                   |
      | Encaminhamentos | checkbox multiplo |
    E vejo o botão "Enviar"
    Quando preencho o formulário com os dados
      | Campo           | Tipo                   | Valor                  |
      | Encaminhamentos | checkbox multiplo | Atendimento domiciliar |
    E clico no botão "Enviar"
    Então vejo mensagem de sucesso "Encaminhamentos adicionados com sucesso."
