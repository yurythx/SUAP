## -*- coding: utf-8 -*-
## language: pt
#
#Funcionalidade: Cadastro de Anexo do Convênio
#      @do_document
#      Cenário: Cadastro de Anexo do Convênio
#      Ação executada pelo Coordenador de Frota Sistêmico ou Coordenador de Frota.
#          Dado acesso a página "/"
#        Quando realizo o login com o usuário "190002" e senha "abcd"
#             E acesso o menu "Extensão::Convênios::Convênios"
#         Então vejo a página "Convênios"
#         Quando olho a linha "1020/2020"
#		 E clico no ícone de exibição
#         Então vejo a página "Convênio 1020/2020"
#             E vejo o botão "Adicionar Anexo"
#        Quando clico no botão "Adicionar Anexo"
#         Então vejo a página "Adicionar Anexo"
#             E vejo os seguintes campos no formulário
#               | Campo                          | Tipo     |
#               | Tipo                         | Autocomplete |
#               | Descrição                         | Texto    |
#
#
#             E vejo o botão "Salvar"
#
#        Quando preencho o formulário com os dados
#            | Campo                          | Tipo     |  Valor    |
#            | Tipo                         | Autocomplete    | Arquivo Digitalizado/Convênio |
#            | Descrição                         | Texto    | descrição sobre o anexo com informações do aditivo |
#
#             E clico no botão "Salvar"
#
#         Então vejo mensagem de sucesso "Anexo adicionado com sucesso. Submeta o arquivo digitalizado."
#         E vejo os seguintes campos no formulário
#               | Campo                          | Tipo     |
#               | Arquivo                         | Arquivo |
#
#
#             E vejo o botão "Enviar"
#
#        Quando preencho o formulário com os dados
#            | Campo                          | Tipo     |  Valor    |
#            | Arquivo                         | Arquivo    | anexo.png |
#
#             E clico no botão "Enviar"
#
#         Então vejo mensagem de sucesso "Anexo enviado com sucesso."
#
#      Cenário: Sai do sistema
#        Quando acesso o menu "Sair"
