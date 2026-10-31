# -*- coding: utf-8 -*-
# language: pt

Funcionalidade: Atividades ligadas ao cadastro de pontuacao minima

      Cenário: Adicionando os usuários necessários para os testes
          Dado os seguintes usuários
               | Nome           | Matrícula      | Setor | Lotação | Email             | CPF            | Senha | Grupo           |
               | Membro         | Membro         | A0    | A0      | pla01@ifrn.edu.br | 645.433.197-02 | abcd  | Membro CPPD     |
               | Presidente     | Presidente     | A0    | A0      | pla02@ifrn.edu.br | 645.433.196-21 | abcd  | Presidente CPPD |

      @do_document
      Cenário: Criar uma pontuacao minima
          Dado acesso a página "/"
        Quando realizo o login com o usuário "Membro" e senha "abcd"
             E acesso o menu "Gestão de Pessoas::Desenvolvimento de Pessoal::Docentes::Professor Titular::Cadastros::Pontuação Mínima"
         Então vejo a página "Pontuações mínimas"
             E vejo o botão "Adicionar Pontuação mínima"
        Quando clico no botão "Adicionar Pontuação mínima"
         Então vejo a página "Adicionar Pontuação mínima"


        Quando preencho o formulário com os dados
               | Campo                                  | Tipo              | Valor  |
               | Qtd minima grupos                      | Texto             |  2     |
               | Ano                                    | Texto             |  2020  |
               | Pontuacao exigida                      | Texto             |  10    |
               | Grupo associado à pontuação mínima     | Autocomplete      |  A     |


             E clico no botão "Salvar"
         Então vejo mensagem de sucesso "Cadastro realizado com sucesso."


      Cenário: Sai do sistema
        Quando acesso o menu "Sair"
