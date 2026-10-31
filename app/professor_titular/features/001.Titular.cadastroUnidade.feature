# -*- coding: utf-8 -*-
# language: pt

Funcionalidade: Atividades ligadas ao cadastro de unidade da diretriz

      Cenário: Adicionando os usuários necessários para os testes
          Dado os seguintes usuários
               | Nome           | Matrícula      | Setor | Lotação | Email             | CPF            | Senha | Grupo           |
               | Membro         | Membro         | A0    | A0      | pla01@ifrn.edu.br | 645.433.197-02 | abcd  | Membro CPPD     |
               | Presidente     | Presidente     | A0    | A0      | pla01@ifrn.edu.br | 645.433.196-21 | abcd  | Presidente CPPD |

      @do_document
      Cenário: Criar uma unidade da diretriz do Titular
          Dado acesso a página "/"
        Quando realizo o login com o usuário "Membro" e senha "abcd"
             E acesso o menu "Gestão de Pessoas::Desenvolvimento de Pessoal::Docentes::Professor Titular::Cadastros::Unidades"
         Então vejo a página "Unidades"
             E vejo o botão "Adicionar Unidade"
        Quando clico no botão "Adicionar Unidade"
         Então vejo a página "Adicionar Unidade"
             E vejo os seguintes campos no formulário
               | Campo       | Tipo  |
               | Nome        | Texto |
               | Sigla       | Texto |
             E vejo o botão "Salvar"
        Quando clico no botão "Salvar"
         Então vejo os seguintes erros no formulário
               | Campo       | Tipo  | Mensagem           |
               | Nome | Texto | Este campo é obrigatório  |
               | Sigla | Texto | Este campo é obrigatório |
        Quando preencho o formulário com os dados
               | Campo       | Tipo  | Valor  |
               | Nome        | Texto |  Prova |
               | Sigla       | Texto |  Prova |
             E clico no botão "Salvar"
         Então vejo mensagem de sucesso "Cadastro realizado com sucesso."


      Cenário: Sai do sistema
        Quando acesso o menu "Sair"
