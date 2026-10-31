# -*- coding: utf-8 -*-
# language: pt

Funcionalidade: Matricular Alunos na EAD
  Essa funcionalidade realiza o processo de matricular alunos na EAD.

  Cenário: Configuração inicial para execução dos cenários do catalogo
    Dado acesso a página "/"
    Quando a data do sistema for "10/05/2020"
    E realizo o login com o usuário "300002" e senha "abcd"

  @do_document
  Cenário: Assumindo Atendimento da Matrícula EAD
    Dado acesso a página "/"
    Quando acesso o menu "Balcão Digital::Solicitações"
    Então vejo a página "Solicitações"
    Quando olho para a listagem
    E olho a linha "Matrícula EAD"
    E clico no ícone de exibição
    Então vejo a página "Solicitação: Matrícula EAD"
    Quando clico no botão "Assumir atendimento"
    Então vejo a página "Solicitação: Matrícula EAD"
    E vejo mensagem de sucesso "O responsável foi associado a Avaliador do Catálogo Digital"

  @do_document
  Cenário: Solicitando Correção de Dados da Matrícula EAD
    Quando clico na aba "Etapa 2"
    Quando clico no label "OK" da etapa "2"
    Quando clico na aba "Etapa 3"
    Quando clico no label "OK" da etapa "3"
    Quando clico na aba "Etapa 4"
    Quando clico no label "OK" da etapa "4"
    E clico no botão "Salvar"
    Então vejo mensagem de sucesso "Avaliação salva com sucesso."
    Quando clico na aba "Etapa 2"
    E olho para a tabela "table_etapa_2"
    E olho a linha "Marcos Paulo"
    E seto o status da linha de avaliação para "C.P"
    E olho para a página
    E clico no botão "Salvar"
    Então vejo mensagem de sucesso "Avaliação salva com sucesso."
    Quando olho para a página
    E clico no botão "Solicitar correção de dados"
    Entao vejo a página "Solicitação: Matrícula EAD"
    # Então vejo mensagem de sucesso "A correção de dados foi solicitada."
    # E vejo a página "Avaliação de Solicitação"
    # E vejo a linha "Aguardando Correção de Dados"

  @do_document
  Cenário: Confirmando Dados da Matrícula EAD
    Dado informações corrigidas da Matrícula EAD
    Quando acesso o menu "Balcão Digital::Solicitações"
    E olho para a listagem
    E olho a linha "Matrícula EAD"
    E clico no ícone de exibição
    Então vejo a página "Solicitação: Matrícula EAD"
    E vejo o texto "Dados Corrigidos"
    Quando clico no label "OK" da etapa "2"
    E clico no botão "Salvar"
    Então vejo mensagem de sucesso "Avaliação salva com sucesso."
    Quando olho para a página
    Então vejo a página "Solicitação: Matrícula EAD"
    E vejo o texto "Pronto Para Execução"

  @do_document
  Cenário: Executando a Matrícula EAD
    Quando clico no botão "Executar"
    Então vejo a página "Executar Solicitação"
    Quando preencho o formulário com os dados
      | Campo           | Tipo    | Valor  |
      | Possui Convênio | lista   | Não    |
      | Possui Orientador | lista   | Não    |
    E clico no botão "Enviar"
    Então vejo mensagem de sucesso "A solicitação foi atendida"
    Quando olho para a listagem
    E olho a linha "Matrícula EAD"
    E clico no ícone de exibição
    Então vejo a página "Solicitação: Matrícula EAD"
    E vejo o texto "Atendido"

  Cenário: Verificando a criação do aluno
    Quando acesso o menu "Ensino::Alunos e Professores::Alunos"
    Então vejo a página "Alunos"
    Quando olho para a listagem
    E olho a linha "Marcos Paulo de Araújo"
    E clico no ícone de exibição
    Então vejo a página "Marcos Paulo de Araújo"
