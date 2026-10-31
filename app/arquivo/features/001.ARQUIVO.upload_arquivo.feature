# -*- coding: utf-8 -*-
# language: pt
Funcionalidade: Cadastro de Arquivo do Servidor

  Cenário: Adicionando os usuários necessários para os testes Arquivo

    Dado os seguintes usuários
      | Nome                 | Matrícula | Setor | Lotação | Email                            | CPF            | Senha | Grupo                          |
      | Cadastrador de Arquivo | 101010     | CZN   | CZN     | cadastrador_arquivo@ifrn.edu.br       | 994.148.300-06 | abcd  | Uploader de Arquivos   |
      | Identificador de Arquivo |    101011 | CZN   | CZN     | identificador_arquivo@ifrn.edu.br | 814.245.450-56 | abcd  | Identificador de Arquivos |
      | Validador de Arquivo     |    101012 | CZN   | CZN     | validador_arquivo@ifrn.edu.br     | 851.797.020-97 | abcd  | Validador de Arquivos     |
      | Servidor do Assentamento Funcional     |    101013 | CZN   | CZN     | servidor_arquivo@ifrn.edu.br     | 410.445.380-31 | abcd  | Servidor                               |
    E os dados básicos para arquivos


  @do_document
  Cenário: Cadastro de Arquivo do Servidor
    Cadastro de Arquivo.
    Ação executada por um membro do grupo Uploader de Arquivos.

    Dado acesso a página "/"
    Quando realizo o login com o usuário "101010" e senha "abcd"
    E acesso o menu "Gestão de Pessoas::Administração de Pessoal::Assentamento Funcional::Upload de Arquivos"
    Então vejo a página "Upload de Arquivos"
    E vejo os seguintes campos no formulário
      | Campo                    | Tipo                   |
      | Selecione o Servidor     | Autocomplete           |
    E vejo o botão "Enviar"
    Quando preencho o formulário com os dados
      | Campo                    | Tipo                   | Valor                           |
      | Selecione o Servidor     | Autocomplete           | Servidor do Assentamento Funcional |
    E clico no botão "Enviar"
    Então vejo a página "Upload de Arquivos"

  Cenário: Sai do sistema
    Quando acesso o menu "Sair"
