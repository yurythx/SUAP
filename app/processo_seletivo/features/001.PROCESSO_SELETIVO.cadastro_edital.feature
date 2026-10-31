# -*- coding: utf-8 -*-
# language: pt
Funcionalidade: Cadastro Básicos

  Cenário: Adicionando os usuários necessários para os testes PROCESSO SELETIVO
    Dado os dados básicos do processo seletivo
    E os seguintes usuários
      | Nome                | Matrícula | Setor | Lotação | Email                           | CPF            | Senha | Grupo                                      |
      | Adm Acad            |   1221471 | CZN   | CZN     | adm_acad@ifrn.edu.br            | 365.645.240-72 | abcd  | Administrador Acadêmico                    |
      | Coord Edital Adesao |   1221472 | CZN   | CZN     | coord_edital_adesao@ifrn.edu.br | 398.720.660-86 | abcd  | Coordenador de Editais de Adesão Sistêmico |
      | Servidor Fiscal     |   1221473 | CZN   | CZN     | servidor_fiscal@ifrn.edu.br     | 250.462.190-69 | abcd  | Servidor                                   |
    Dado acesso a página "/"
    Quando a data do sistema for "10/06/2020"
    Quando realizo o login com o usuário "1221471" e senha "abcd"

  @do_document
  Cenário: Cadastrar Edital
    Ação executada por um membro do grupo Administrador Acadêmico.

    Quando acesso o menu "Ensino::Processos Seletivos::Editais"
    Então vejo a página "Editais"
    E vejo o botão "Adicionar Edital"
    Quando clico no botão "Adicionar Edital"
    Então vejo a página "Adicionar Edital"
    Quando preencho o formulário com os dados
      | Campo     | Tipo         | Valor               |
      | Ano       | Autocomplete |                2020 |
      | Semestre  | Texto        |                   1 |
      | Código    | Texto        |              102030 |
      | Descrição | Texto        | descrição do edital |
    E clico no botão "Salvar"
    Então vejo mensagem de sucesso "Cadastro realizado com sucesso."
