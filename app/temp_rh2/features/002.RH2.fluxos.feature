# -*- coding: utf-8 -*-
# language: pt
Funcionalidade: Fluxos

  @do_document
  Cenário: Inscrição em Competição Desportiva
  Ação executada pelo Servidor.

    Dado acesso a página "/"
    Quando a data do sistema for "10/08/2020"
    E realizo o login com o usuário "337003" e senha "abcd"
    E clico no link "Inscrição nos"
    Então vejo os seguintes campos no formulário
      | Campo                                        | Tipo              |
      | Confirme seu Campus                          | Lista             |
      | Escolha as modalidades que deseja participar | checkbox multiplo |
    E vejo o botão "Salvar"

    Quando preencho o formulário com os dados
      | Campo                                              | Tipo              | Valor                          |
      | Confirme seu Campus                                | Lista             | CZN                            |
      | Escolha as modalidades que deseja participar       | checkbox multiplo | Futebol - Masculino - Coletivo |
      | Termo de aceitação para entrega do atestado médico | Checkbox          | marcar                         |
      | Atestado Médico                                    | Arquivo           | arquivo.pdf                    |
    E clico no botão "Salvar"
    Então vejo mensagem de sucesso "Inscrição na competição realizada com sucesso!"


