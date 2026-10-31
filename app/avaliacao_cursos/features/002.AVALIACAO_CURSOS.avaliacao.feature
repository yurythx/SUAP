# -*- coding: utf-8 -*-
# language: pt
Funcionalidade: Cadastro de Avaliação

  @do_document
  Cenário: Cadastro de Avaliação
    Ação executada pelo Avaliador de Curso.

    Dado acesso a página "/"
    Quando realizo o login com o usuário "103111" e senha "abcd"
    E acesso o menu "Ensino::Pedagogia::Avaliação de Cursos::Avaliações"
    Então vejo a página "Avaliações"
    E vejo o botão "Adicionar Avaliação"
    Quando clico no botão "Adicionar Avaliação"
    Então vejo a página "Adicionar Avaliação"
    E vejo os seguintes campos no formulário
      | Campo     | Tipo     |
      | Ano    | Autocomplete    |
      | Descrição | Texto |

    E vejo o botão "Salvar"
    Quando preencho o formulário com os dados
      | Campo     | Tipo     | Valor                          |
      | Ano    | Autocomplete    | 2020 |
      | Descrição | Texto | avaliação dos cursos em 2020 |
    E clico no botão "Salvar"
    Então vejo mensagem de sucesso "Cadastro realizado com sucesso."

  Cenário: Sai do sistema
    Quando acesso o menu "Sair"

