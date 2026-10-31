# -*- coding: utf-8 -*-
# language: pt

Funcionalidade: Cadastros Básicos
   Cadastro Variáveis e Indicadores

   Contexto: Acessa a index da aplicação
       Dado acesso a página "/"

    Cenário: Efetuar login no sistema
      Quando realizo o login com o usuário "admin" e senha "abc"


    @do_document
    Cenário: Cadastrar Variáveis
      Quando acesso o menu "Des. Institucional::Gestão::Cadastros::Variáveis"
       Então vejo o botão "Adicionar Variável"
      Quando clico no botão "Adicionar Variável"
       Então vejo a página "Adicionar Variável"
      Quando preencho o formulário com os dados
              | Campo              | Tipo            | Valor                           |
              | Sigla              | Texto           | _AE                             |
              | Nome               | Texto           | Alunos Evadidos                 |
              | Descrição          | TextArea        | Número de alunos evadidos       |
              | Fonte              | Texto           | Sistema acadêmico/Suap          |
           E clico no botão "Salvar"
       Então vejo mensagem de sucesso "Cadastro realizado com sucesso."

    @do_document
    Cenário: Cadastrar Indicadores
      Quando acesso o menu "Des. Institucional::Gestão::Cadastros::Indicadores"
       Então vejo o botão "Adicionar Indicador"
      Quando clico no botão "Adicionar Indicador"
       Então vejo a página "Adicionar Indicador"
      Quando preencho o formulário com os dados
              | Campo              | Tipo            | Valor                     |
              | Sigla              | Texto           | _PMEja (MEC)              |
              | Nome               | Texto           | Percentual de matrículas em cursos articulados com a educação de jovens e adultos (PMEja)        |
              | Objetivo           | TextArea        | Objetivo: Quantificar o percentual de vagas ofertadas para o PROEJA, de acordo com o previsto no art. 2º do Decreto nº 5.840/2006. Descrição: Alunos equivalentes em cursos Eja: número de alunos-equivalentes matriculados em cursos ordinários articulados com a educação de jovens e adultos (presenciais e EAD) ofertados pelo IFRN, registrados no sistema acadêmico institucional, incluindo-se cursos FIC e técnicos. Alunos equivalentes ordinários matriculados: número de alunos-equivalentes matriculados em cursos ordinários (presenciais e EAD) ofertados pelo IFRN, registrados no sistema acadêmico institucional. Considera-se o conceito de aluno-equivalente, regulamentado pela Portaria MEC nº 818, de 13/08/2015.           |
              | Área Responsável   | Texto           | Pró-Reitoria de Ensino    |
              | Fórmula            | Texto           | AMEJA_OR / AM_OR * 100    |
              | Tipo               | Lista           | MEC                       |
           E clico no botão "Salvar"
       Então vejo mensagem de sucesso "Cadastro realizado com sucesso."


