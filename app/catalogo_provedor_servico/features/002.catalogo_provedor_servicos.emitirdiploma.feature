# -*- coding: utf-8 -*-
# language: pt

Funcionalidade: Solicitação de Segunda Via de Diploma
  Essa funcionalidade realiza o processo de solicitar segunda via de diploma

  Cenário: Configuração inicial para execução dos cenários do catalogo
    Dado acesso a página "/"
    Quando a data do sistema for "10/05/2020"
    E realizo o login com o usuário "300002" e senha "abcd"

  @do_document
  Cenário: Assumindo Atendimento da Solicitação de Segunda Via de Diploma
    Dado acesso a página "/"
    Quando acesso o menu "Balcão Digital::Solicitações"
    Então vejo a página "Solicitações"
    Quando olho para a listagem
    E olho a linha "Emissão de 2a Via de Diploma"
    E clico no ícone de exibição
    Então vejo a página "Solicitação: Emissão de 2a Via de Diploma"
    Quando clico no botão "Assumir atendimento"
    Então vejo mensagem de sucesso "O responsável foi associado a Avaliador do Catálogo Digital"

  @do_document
  Cenário: Confirmando Dados da Solicitação de Segunda Via de Diploma
    Quando clico na aba "Etapa 1"
    Quando clico no label "OK" da etapa "1"
    E clico no botão "Salvar"
    Então vejo mensagem de sucesso "Avaliação salva com sucesso."
    Quando olho para a página
    Então vejo o texto "Pronto Para Execução"

  @do_document
  Cenário: Executando a Solicitação de Segunda Via de Diploma
    Quando clico no botão "Executar"
    Então vejo a página "Solicitação de Emissão de Segunda via de Diploma"
    Quando preencho o formulário com os dados
      | Campo            | Tipo         | Valor                         |
      | Senha            | senha        | abcd                          |
      | Perfil           | lista        | Avaliador do Catálogo Digital |
      | Destino do primeiro trâmite | radio | Buscar usando o Autocompletar |
      | Setor de Destino | autocomplete | CEN                           |
    E clico no botão "Enviar"
    Então vejo mensagem de sucesso "A solicitação foi atendida através da criação do processo de número"
    Quando olho para a listagem
    E olho a linha "Emissão de 2a Via de Diploma"
    E clico no ícone de exibição
    Então vejo a página "Solicitação: Emissão de 2a Via de Diploma"
    E vejo o texto "Atendido"

  Cenário: Verificando a criação da Solicitação de Segunda Via de Diploma
    Quando acesso a página "/admin/processo_eletronico/processo/"
    Então vejo a página "Processos Eletrônicos"
    Quando olho para a listagem
    E olho a linha "Segunda Via de Diploma"
    E clico no ícone de exibição
    E olho para o quadro "Dados gerais"
    Então vejo o texto "Segunda Via de Diploma"
