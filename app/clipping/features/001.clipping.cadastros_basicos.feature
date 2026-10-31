# -*- coding: utf-8 -*-
# language: pt

Funcionalidade: Cadastros Básicos

  Cenário: Configuração inicial para execução dos cenários clipping
    Dado os seguintes usuários
      | Nome                       | Matrícula | Setor    | Lotação  | Email                             | CPF            | Senha | Grupo                     |
      | Gerente de Clipping        | 300011    | CEN      | CEN      | gerente_clipping@ifrn.edu.br      | 000.300.011-70 | abcd  | Gerente de Clipping       |
    Quando a data do sistema for "10/05/2020"

  Cenário: Efetuar login no sistema
    Quando acesso a página "/"
    E realizo o login com o usuário "300011" e senha "abcd"

  @do_document
  Cenário: Cadastrar Veículo de Comunicação
    Quando acesso o menu "Comunicação Social::Clipping::Cadastros::Veículos"
     Então vejo o botão "Adicionar Veículo"
    Quando clico no botão "Adicionar Veículo"
     Então vejo a página "Adicionar Veículo"
    Quando preencho o formulário com os dados
            | Campo      | Tipo  | Valor         |
            | Nome       | Texto | 94 FM ZYX4962 |
         E clico no botão "Salvar"
     Então vejo mensagem de sucesso "Cadastro realizado com sucesso."

  @do_document
  Cenário: Cadastrar Fonte
    Quando acesso o menu "Comunicação Social::Clipping::Fontes"
     Então vejo o botão "Adicionar Fonte"
    Quando clico no botão "Adicionar Fonte"
     Então vejo a página "Adicionar Fonte"
    Quando preencho o formulário com os dados
            | Campo      | Tipo  | Valor                                                                           |
            | Descrição  | Texto | Agência Brasil                                                                  |
            | Editorial  | Texto | Educação                                                                        |
            | Link       | Texto | https://www.gov.br/pt-br/noticias/ultimas-noticias/ultimas-noticias/RSS         |
            | Ativo      | checkbox | marcar                                                                       |
         E clico no botão "Salvar"
     Então vejo mensagem de sucesso "Cadastro realizado com sucesso."

  @do_document
  Cenário: Cadastrar Palavra Chave
    Quando acesso o menu "Comunicação Social::Clipping::Cadastros::Palavras-chave"
     Então vejo o botão "Adicionar Palavra-Chave"
    Quando clico no botão "Adicionar Palavra-Chave"
     Então vejo a página "Adicionar Palavra-Chave"
    Quando preencho o formulário com os dados
            | Campo      | Tipo  | Valor                                                         |
            | Descrição  | Texto | IFRN                                                          |
         E clico no botão "Salvar"
     Então vejo mensagem de sucesso "Cadastro realizado com sucesso."

  @do_document
  Cenário: Cadastrar Classificação
    Quando acesso o menu "Comunicação Social::Clipping::Cadastros::Classificações"
     Então vejo o botão "Adicionar Classificação"
    Quando clico no botão "Adicionar Classificação"
     Então vejo a página "Adicionar Classificação"
    Quando preencho o formulário com os dados
            | Campo      | Tipo  | Valor  |
            | Descrição  | Texto | Positivo  |
            | Visível    | checkbox | marcar     |
         E clico no botão "Salvar"
     Então vejo mensagem de sucesso "Cadastro realizado com sucesso."

  @do_document
  Cenário: Cadastrar Editorial
    Quando acesso o menu "Comunicação Social::Clipping::Cadastros::Editoriais"
     Então vejo o botão "Adicionar Editorial"
    Quando clico no botão "Adicionar Editorial"
     Então vejo a página "Adicionar Editorial"
    Quando preencho o formulário com os dados
            | Campo      | Tipo  | Valor  |
            | Nome  | Texto | Ambiente  |
         E clico no botão "Salvar"
     Então vejo mensagem de sucesso "Cadastro realizado com sucesso."
