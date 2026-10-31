# -*- coding: utf-8 -*-
# language: pt
Funcionalidade: Cadastrar Avaliação do ENCCEJA

  @do_document
  Cenário: Cadastrar Avaliação do ENCCEJA
    Ação executada pelo membro do grupo Administrador ENCCEJA.

    Dado acesso a página "/"
    Quando realizo o login com o usuário "907008" e senha "abcd"
    E acesso o menu "Ensino::Certificados ENCCEJA::Areas de Conhecimento"
    Então vejo a página "Área de Conhecimento"
    E vejo o botão "Adicionar Áreas de Conhecimento"
    Quando clico no botão "Adicionar Áreas de Conhecimento"
    Então vejo a página "Adicionar Áreas de Conhecimento"
    E vejo os seguintes campos no formulário
      | Campo                    | Tipo                   |
      | Nome                      | Texto                  |
      | Descrição                    | Textarea               |
    E vejo o botão "Salvar"
    Quando preencho o formulário com os dados
      | Campo                    | Tipo                   | Valor                           |
      | Nome                      | Texto                  | Linguagens, Códigos e suas Tecnologias |
      | Descrição                    | Textarea               | Linguagens, Códigos e suas Tecnologias (componentes curriculares/disciplinas: Língua Portuguesa, Língua Estrangeira Moderna, Artes e Educação Física) |
    E clico no botão "Salvar"
    Então vejo mensagem de sucesso "Cadastro realizado com sucesso."

  Cenário: Sai do sistema
    Quando acesso o menu "Sair"
