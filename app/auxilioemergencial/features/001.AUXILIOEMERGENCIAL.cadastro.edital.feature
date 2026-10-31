# -*- coding: utf-8 -*-
# language: pt

Funcionalidade: Cadastro e Configuração do Edital

  Cenário: Adicionando os usuários necessários para os testes auxílio emergencial
    Dado os seguintes usuários
      | Nome               | Matrícula      | Setor | Lotação | Email                         | CPF            | Senha | Grupo                                          |
      | Coord_AE Sistemico | 103001         | CZN   | CZN     | coordaesistemico@ifrn.edu.br  | 645.433.195-40 | abcd  | Coordenador de Atividades Estudantis Sistêmico |
      | Assistente Social  | 103002         | CZN   | CZN     | assistente_social@ifrn.edu.br | 188.135.291-98 | abcd  | Assistente Social                              |
      | Aluno AE           | 20191101011031 | CZN   | CZN     | aluno_ae@ifrn.edu.br          | 101.011.031-40 | abcd  | Aluno                                          |
    E os dados básicos do auxílio emergencial
  
  @do_document
  Cenário: Cadastro do Edital
  Cadastro do edital para seleção de projetos de extensão.
  Ação executada pelo Gerente Sistêmico de Extensão ou Coordenador de Extensão.
      Dado acesso a página "/"
    Quando realizo o login com o usuário "103001" e senha "abcd"
     Então vejo o item de menu "Atividades Estudantis::Ações Emergenciais::Programas de Auxílios Emergenciais::Editais"
    Quando acesso o menu "Atividades Estudantis::Ações Emergenciais::Programas de Auxílios Emergenciais::Editais"
     Então vejo a página "Editais Emergenciais"
         E vejo o botão "Adicionar Edital Emergencial"
    Quando clico no botão "Adicionar Edital Emergencial"
     Então vejo a página "Adicionar Edital Emergencial"
         E vejo os seguintes campos no formulário
           | Campo                          | Tipo                      |
           | Descrição                      | TextArea                  |
           | Campus                         | Lista                     |
           | Tipos de Auxílio               | FilteredSelectMultiple    |
           | Link para o Edital             | Texto                     |
           | Data de Início das Inscrições  | Data                      |
           | Data de Término das Inscrições | Data                      |
           | Data de Divulgação do Resultado | Data                     |
           | Ativo                          | Checkbox                  |
         E vejo o botão "Salvar"
    Quando preencho o formulário com os dados
         | Campo                               | Tipo                    | Valor                    |
         | Descrição                           | TextArea                  | EDITAL Nº 001/2020 - ENSINO REMOTO     |
         | Campus                              | Lista                     | CZN                    |
         | Tipos de Auxílio                    | FilteredSelectMultiple    | Serviço de Internet    |
         | Link para o Edital                  | Texto                     | https://portal.ifrn.edu.br/campus/czn/edital012020.pdf|
         | Data de Início das Inscrições       | Data                      | 17/11/2020             |
         | Data de Término das Inscrições      | Data                      | 27/12/2020             |
         | Data de Divulgação do Resultado     | Data                      | 30/12/2020             |
         | Ativo                               | Checkbox                  |                        |
       E clico no botão "Salvar"
   Então vejo mensagem de sucesso "Cadastro realizado com sucesso."
  Quando acesso o menu "Sair"

#  Cenário: Adicionando os usuários necessários para os testes
#    Dado os dados básicos
