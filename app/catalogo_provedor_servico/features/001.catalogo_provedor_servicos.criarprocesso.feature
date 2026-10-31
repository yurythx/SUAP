# -*- coding: utf-8 -*-
# language: pt

Funcionalidade: Solicitar Criação de Processo Eletrônico
  Essa funcionalidade permite solicitar a criação de um processo eletrônico

  Cenário: Configuração inicial para execução dos cenários do catalogo
    Dado os seguintes usuários
      | Nome                                  | Matrícula | Setor | Lotação | Email                        | CPF            | Senha | Grupo                                           |
      | Gerente Sistemico do Catalogo Digital | 300001    | CEN   | CEN     | gerente_catalogo@ifrn.edu.br | 994.034.470-87 | abcd  | Gerente Sistemico do Catalogo Digital, Servidor |
      | Avaliador do Catálogo Digital         | 300002    | CEN   | CEN     | chefe_setor@ifrn.edu.br      | 211.659.640-82 | abcd  | Avaliador do Catálogo Digital, Servidor         |
    E os cadastros básicos do catálogo digital
    E acesso a página "/"
    Quando a data do sistema for "10/05/2020"
    E realizo o login com o usuário "300002" e senha "abcd"

  @do_document
  Cenário: Assumindo Atendimento da Solicitação de Protocolo Eletrônico
    Dado acesso a página "/"
    Quando acesso o menu "Balcão Digital::Solicitações"
    Então vejo a página "Solicitações"
    Quando olho para a listagem
    E olho a linha "Protocolar Documentos"
    E clico no ícone de exibição
    Então vejo a página "Solicitação: Protocolar Documentos"
    Quando clico no botão "Assumir atendimento"
    Então vejo mensagem de sucesso "O responsável foi associado a Avaliador do Catálogo Digital"

  @do_document
  Cenário: Confirmando Dados da Solicitação de Protocolo Eletrônico
    Quando clico na aba "Etapa 1"
    Quando clico no label "OK" da etapa "1"
    Quando clico na aba "Etapa 2"
    Quando clico no label "OK" da etapa "2"
    E clico no botão "Salvar"
    Então vejo mensagem de sucesso "Avaliação salva com sucesso."
    Quando olho para a página
    Então vejo o texto "Pronto Para Execução"

  @do_document
  Cenário: Executando a Solicitação de Protocolo Eletrônico
    Quando clico no botão "Executar"
    Então vejo a página "Solicitação de Protocolo Eletrônico"
    Quando preencho o formulário com os dados
      | Campo                         | Tipo         | Valor                          |
      | Tipo do Documento             | lista        | Ofício                         |
      | Nível de Acesso               | lista        | Público                        |
      | Destino do primeiro trâmite   | radio        | Buscar usando o Autocompletar |
      | Setor de Destino (Campus CEN) | autocomplete | CEN                            |
      | Perfil                        | lista        | Avaliador do Catálogo Digital  |
      | Senha                         | senha        | abcd                           |
    E clico no botão "Enviar"
    Então vejo mensagem de sucesso "A solicitação foi atendida através da criação do processo de número"
    Quando olho para a listagem
    E olho a linha "Protocolar Documentos"
    E clico no ícone de exibição
    Então vejo a página "Solicitação: Protocolar Documentos"
    E vejo o texto "Atendido"

  Cenário: Verificando a criação da Solicitação de Protocolo Eletrônico
    Quando acesso a página "/admin/processo_eletronico/processo/"
    Então vejo a página "Processos Eletrônicos"
    Quando olho para a listagem
    E olho a linha "Protocolo Eletrônico Demanda Externa"
    E clico no ícone de exibição
    E olho para o quadro "Dados gerais"
    Então vejo o texto "Protocolo Eletrônico Demanda Externa"
