# -*- coding: utf-8 -*-
# language: pt

Funcionalidade: Atividades ligadas ao cadastro de indicadores

      Cenário: Adicionando os usuários necessários para os testes
        Dado os dados básicos para professor titular
          E os seguintes usuários
               | Nome           | Matrícula      | Setor | Lotação | Email             | CPF            | Senha | Grupo           |
               | Membro         | Membro         | A0    | A0      | pla01@ifrn.edu.br | 645.433.197-02 | abcd  | Membro CPPD     |
               | Presidente     | Presidente     | A0    | A0      | pla01@ifrn.edu.br | 645.433.196-21 | abcd  | Presidente CPPD |

      @do_document
      Cenário: Criar indicadores
          Dado acesso a página "/"
        Quando realizo o login com o usuário "Membro" e senha "abcd"
             E acesso o menu "Gestão de Pessoas::Desenvolvimento de Pessoal::Docentes::Professor Titular::Cadastros::Indicadores"
         Então vejo a página "Indicadores"
             E vejo o botão "Adicionar Indicador"
        Quando clico no botão "Adicionar Indicador"
         Então vejo a página "Adicionar Indicador"

        Quando preencho o formulário com os dados
               | Campo        | Tipo               | Valor  |
               | Grupo        | Autocomplete       |  A     |
               | Nome         | Texto              |  Prova |
               | Descricao    | Textarea           |  Prova |


             E clico no botão "Salvar"
         Então vejo mensagem de sucesso "Cadastro realizado com sucesso."

      Cenário: Sai do sistema
        Quando acesso o menu "Sair"
