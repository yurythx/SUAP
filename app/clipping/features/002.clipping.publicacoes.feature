# -*- coding: utf-8 -*-
# language: pt

Funcionalidade: Cadastros Básicos

  Cenário: Efetuar login no sistema
    Quando acesso a página "/"
    E realizo o login com o usuário "300011" e senha "abcd"

  @do_document
  Cenário: Cadastrar Publicação Impressa
    Quando acesso o menu "Comunicação Social::Clipping::Publicações::Impressas"
     Então vejo o botão "Adicionar Publicação Impressa"
    Quando clico no botão "Adicionar Publicação Impressa"
     Então vejo a página "Adicionar Publicação Impressa"
    Quando preencho o formulário com os dados
            | Campo      | Tipo  | Valor         |
            | Data       | data | 10/05/2020     |
            | Veículo    | autocomplete | 94 FM ZYX4962 |
            | Editorial  | autocomplete | Ambiente          |
            | Título     | Texto        | Universidades ganham prêmio de inovação |
            | Palavras chaves | autocomplete multiplo | IFRN                           |
            | Classificação   | autocomplete | Positivo                       |
            | Página          | Texto        | 1                              |
         E clico no botão "Salvar"
     Então vejo mensagem de sucesso "Cadastro realizado com sucesso."

  @do_document
  Cenário: Cadastrar Publicação Eletrônica
    Quando acesso o menu "Comunicação Social::Clipping::Publicações::Eletrônicas"
     Então vejo o botão "Adicionar Publicação Eletrônica"
    Quando clico no botão "Adicionar Publicação Eletrônica"
     Então vejo a página "Adicionar Publicação Eletrônica"
    Quando preencho o formulário com os dados
            | Campo      | Tipo  | Valor         |
            | Data       | data | 10/05/2020     |
            | Veículo    | autocomplete | 94 FM ZYX4962 |
            | Editorial  | autocomplete | Ambiente          |
            | Título     | Texto        | Institutos Federais receberão mais verbas |
            | Palavras chaves | autocomplete multiplo | IFRN                           |
            | Classificação   | autocomplete | Positivo                       |
            | Link          | Texto        | http://www.ifrn.edu.br           |
         E clico no botão "Salvar"
     Então vejo mensagem de sucesso "Cadastro realizado com sucesso."

  @do_document
  Cenário: Cadastrar Publicação Digital
    Quando acesso o menu "Comunicação Social::Clipping::Publicações::Digitais"
     Então vejo o botão "Adicionar Publicação Digital"
    Quando clico no botão "Adicionar Publicação Digital"
     Então vejo a página "Adicionar Publicação Digital"
    Quando preencho o formulário com os dados
            | Campo      | Tipo  | Valor         |
            | Data       | data | 10/05/2020     |
            | Veículo    | autocomplete | 94 FM ZYX4962 |
            | Editorial  | autocomplete | Ambiente          |
            | Título     | Texto        | IFRN abre processo seletivo com 220 vagas para cursos de pós-graduação na área de educação |
            | Palavras chaves | autocomplete multiplo | IFRN                           |
            | Classificação   | autocomplete | Positivo                       |
            | Link          | Texto        | http://www.ifrn.edu.br           |
            | Texto         | Textarea        | O IFRN abriu inscrições para processo seletivo de cursos superiores de pós-graduação lato sensu em nível de especialização na área de educação. Ao todo, são 220 vagas. |
         E clico no botão "Salvar"
     Então vejo mensagem de sucesso "Cadastro realizado com sucesso."
