# -*- coding: utf-8 -*-
# language: pt

Funcionalidade: Cadastros Básicos

  Cenário: Configuração inicial para execução dos cenários cnpq
    Dado os seguintes usuários
      | Nome                    | Matrícula | Setor    | Lotação  | Email                                 | CPF            | Senha | Grupo                     |
      | Gestor CNPQ             | 300021    | CEN      | CEN      | gestor_cnpq@ifrn.edu.br               | 915.539.900-21 | abcd  | Gestor CNPQ               |
      | Coordenador de Pesquisa | 300022    | CEN      | CEN      | coordenador_pesquisa_cnpq@ifrn.edu.br | 415.592.930-98 | abcd  | Coordenador de Pesquisa   |
      | Auditor                 | 300023    | CEN      | CEN      | auditor_cnpq@ifrn.edu.br              | 173.256.640-28 | abcd  | Auditor                   |
    Quando a data do sistema for "10/05/2020"

  Cenário: Efetuar login no sistema
    Dado os cadastros básicos do cnpq
    Quando acesso a página "/"
    E realizo o login com o usuário "300021" e senha "abcd"


  @do_document
  Cenário: Importar Lista Completa - Periódico Qualis
    O módulo CNPq permite a geração de relatórios e indicadores com base nas informações dos currículos lattes dos servidores da Instituição. Estes currículos são importados através de uma API do CNPq e as informações são salvas na base de dados do SUAP.
    O cadastro de periódicos com suas respectivas classificações por área de avaliação permitem pontuar os currículos dos pesquisadores que submetem projetos em editais de Pesquisa.
    A pontuação de cada currículo é calculada com base nos critérios de classificação de cada edital e na classificação de cada periódico no qual o pesquisador realizou publicação.
    A planilha com a classificação dos periódicos pode ser obtida na Plataforma Sucupira da CAPES, acessível pelo endereço: https://sucupira.capes.gov.br/sucupira/public/consultas/coleta/veiculoPublicacaoQualis/listaConsultaGeralPeriodicos.jsf
    Quando acesso o menu "Pesquisa::CNPQ::Cadastros::Importar Planilha Periódico Qualis"
     Então vejo a página "Importar Lista Completa - Periódico Qualis"
    Quando preencho o formulário com os dados
            | Campo   | Tipo         | Valor        |
            | Arquivo | Arquivo Real | qualis.xlsx  |
         E clico no botão "Enviar"
     Então vejo mensagem de sucesso "Importação realizada com sucesso."

  Cenário: Sai do sistema
    Quando acesso o menu "Sair"

  @do_document
  Cenário: Cadastrar Periódico
    É possível cadastrar manualmente um periódico que não conste na planilha Qualis.
    Dado acesso a página "/"
    Quando realizo o login com o usuário "300021" e senha "abcd"
    E acesso o menu "Pesquisa::CNPQ::Cadastros::Periódicos"
     Então vejo a página "Cadastrar Periódico"
    Quando preencho o formulário com os dados
            | Campo      | Tipo  | Valor                                                          |
            | ISSN       | Texto | 12345678                                                       |
            | Nome       | Texto | Título de exemplo de um periódico |
         E clico no botão "Salvar"
     Então vejo mensagem de sucesso "Periódico cadastrado com sucesso."

   Cenário: Sai do sistema
    Quando acesso o menu "Sair"

  @do_document
  Cenário: Cadastrar Classificação de um Periódico
    É possível cadastrar ou alterar a classificação da área de avaliação de um determinado periódico.
    Dado acesso a página "/"
    Quando realizo o login com o usuário "300021" e senha "abcd"
    E acesso o menu "Pesquisa::CNPQ::Cadastros::Classificação dos Periódicos"
    Então vejo a página "Classificações de Periódicos"
    E vejo o botão "Adicionar Classificação de Periódico"
    Quando clico no botão "Adicionar Classificação de Periódico"
    Então vejo a página "Adicionar Classificação de Periódico"
    Quando preencho o formulário com os dados
            | Campo             | Tipo         | Valor     |
            | Periódico         | Autocomplete | 12345678  |
            | Classificação     | Lista        | A1        |
            | Área de Avaliação | Autocomplete | MATERIAIS |
         E clico no botão "Salvar"
     Então vejo mensagem de sucesso "Cadastro realizado com sucesso."
