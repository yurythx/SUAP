# -*- coding: utf-8 -*-
# language: pt

Funcionalidade: Importar Notícias e Gerar Relatórios

  Cenário: Efetuar login no sistema
    Quando acesso a página "/"
    E realizo o login com o usuário "300011" e senha "abcd"

  @do_document
  Cenário: Importar Notícias
    Quando acesso o menu "Comunicação Social::Clipping::Importar notícias"
     Então vejo mensagem de sucesso "Nenhuma notícia nova foi encontrada"

  @do_document
  Cenário: Gerar Relatórios
    Quando acesso o menu "Comunicação Social::Clipping::Relatórios"
     Então vejo a página "Relatório por Período"
    Quando preencho o formulário com os dados
            | Campo                | Tipo  | Valor         |
            | Data de Início       | data | 10/05/2020     |
            | Data de Término      | data | 10/05/2020     |
         E clico no botão "Enviar"
     Então vejo a página "Clipagem do período 10/05/2020 à 11/05/2020"
