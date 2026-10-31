## -*- coding: utf-8 -*-
## language: pt
#
#Funcionalidade: Cadastro de Aditivo do Convênio
#      @do_document
#      Cenário: Cadastro de Aditivo do Convênio
#      Ação executada pelo Coordenador de Frota Sistêmico ou Coordenador de Frota.
#          Dado acesso a página "/"
#        Quando realizo o login com o usuário "190002" e senha "abcd"
#             E acesso o menu "Extensão::Convênios::Convênios"
#         Então vejo a página "Convênios"
#         Quando olho a linha "1020/2020"
#		 E clico no ícone de exibição
#         Então vejo a página "Convênio 1020/2020"
#             E vejo o botão "Adicionar Aditivo"
#        Quando clico no botão "Adicionar Aditivo"
#         Então vejo a página "Adicionar Aditivo"
#             E vejo os seguintes campos no formulário
#               | Campo                          | Tipo     |
#               | Número                         | Texto |
#               | Objeto                         | TextArea    |
#               | Data de Realização             | Data     |
#               | Data Inicial                   | Data     |
#               | Data Final                     | Data     |
#
#
#             E vejo o botão "Salvar"
#
#        Quando preencho o formulário com os dados
#            | Campo                          | Tipo     |  Valor    |
#            | Número                         | Texto    | 01/2020 |
#            | Objeto                         | TextArea    | objeto do aditivo do convênio |
#            | Data de Realização             | Data     | 31/12/2020 |
#            | Data Inicial                   | Data     | 01/01/2021 |
#            | Data Final                     | Data     | 01/06/2021 |
#
#
#             E clico no botão "Salvar"
#
#         Então vejo mensagem de sucesso "Aditivo adicionado com sucesso."
#
#      Cenário: Sai do sistema
#        Quando acesso o menu "Sair"
#
#
#
#
#
#
#
