# -*- coding: utf-8 -*-
# language: pt
Funcionalidade: Cadastro da Configuração do ENCCEJA

  Cenário: Adicionando os usuários necessários para os testes ENCCEJA
    Dado os dados básicos para encceja
    e os seguintes usuários
      | Nome                 | Matrícula | Setor | Lotação | Email                            | CPF            | Senha | Grupo                                |
      | Adm Encceja |    907008 | CZN   | CZN     | adm_encceja@ifrn.edu.br | 125.221.570-35 | abcd  | Administrador ENCCEJA |
      | Certificador Encceja     |    907009 | CZN   | CZN     | certificador_encceja@ifrn.edu.br     | 235.496.690-38 | abcd  | Certificador ENCCEJA                |

  @do_document
  Cenário: Cadastro da Configuração do ENCCEJA
    Cadastro das Configurações.
    Ação executada por um membro do grupo Administrador ENCCEJA.

    Dado acesso a página "/"
    Quando realizo o login com o usuário "907008" e senha "abcd"
    E acesso o menu "Ensino::Certificados ENCCEJA::Configurações"
    Então vejo a página "Configuração ENCCEJA"
    E vejo o botão "Adicionar Configurações ENCCEJA"
    Quando clico no botão "Adicionar Configurações ENCCEJA"
    Então vejo a página "Adicionar Configurações ENCCEJA"
    E vejo os seguintes campos no formulário
      | Campo                    | Tipo                   |
      | Ano                      | Lista                  |
      | Descrição                | Texto                  |
      | Ativa                    | checkbox               |
      | Data de realização da 1ª Prova               | Data                |
    E vejo o botão "Salvar"
    Quando preencho o formulário com os dados
      | Campo                    | Tipo                   | Valor                           |
      | Ano                      | Lista                  | 2020 |
      | Descrição                | Texto                  | ENCCEJA 2020 |
      | Data de realização da 1ª Prova               | Data                | 01/08/2020 |
      | Ativa                    | checkbox               | marcar |
    E clico no botão "Salvar"
    Então vejo mensagem de sucesso "Cadastro realizado com sucesso."

  Cenário: Sai do sistema
    Quando acesso o menu "Sair"
