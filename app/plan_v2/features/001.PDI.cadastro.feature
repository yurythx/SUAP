# -*- coding: utf-8 -*-
# language: pt
Funcionalidade: Atividades ligadas ao cadastro do PDI
    Essa funcionalidade verifica as atividades ligadas ao PDI.

      Cenário: Adicionando os usuários necessários para os testes PLAN_V2
          Dado os dados básicos para o planejamento
             E os seguintes usuários
                 | Nome           | Matrícula | Setor | Lotação | Email             | CPF            | Senha | Grupo                                               |
                 | Administrador do PDI | 109001    | A0    | A0      | pla01@ifrn.edu.br | 000.109.001-10 | abcd  | Administrador de Planejamento Institucional         |
                 | Proreitor_1    | 109002    | A1    | A1      | pla02@ifrn.edu.br | 000.109.002-09 | abcd  | Coordenador de Planejamento Institucional Sistêmico |
                 | Proreitor_2    | 109003    | A2    | A2      | pla03@ifrn.edu.br | 000.109.003-81 | abcd  | Coordenador de Planejamento Institucional Sistêmico |
                 | Coord_campus_1 | 109004    | B1    | B1      | pla04@ifrn.edu.br | 653.710.071-21 | abcd  | Coordenador de Planejamento Institucional           |
                 | Coord_campus_2 | 109005    | B2    | B2      | pla05@ifrn.edu.br | 840.617.325-44 | abcd  | Coordenador de Planejamento Institucional           |
                 | Coord_campus_3 | 109006    | C1    | C1      | pla06@ifrn.edu.br | 222.490.685-42 | abcd  | Coordenador de Planejamento Institucional           |
                 | Coord_campus_4 | 109007    | C2    | C2      | pla07@ifrn.edu.br | 976.731.873-96 | abcd  | Coordenador de Planejamento Institucional           |

   Esquema do Cenário: Verifica se a visibilidade do PDI e da adição do PDI pelo <Papel>
          Dado acesso a página "/"
        Quando realizo o login com o usuário "<Papel>" e senha "abcd"
        Quando acesso a página "/admin/plan_v2/pdi/"
         Então vejo a página "Você não tem permissão para acessar essa página"
        Quando acesso o menu "Sair"
        Exemplos:
            | Papel  |
            | 109002 |
            | 109004 |

      @do_document
      Cenário: Cria um novo PDI
        Cria um PDI conforme solicitado. O PDI é o planejamento intitucional de 4 anos.
        Durante o período do PDI será possível ajustes em seu cadastro.
          Dado acesso a página "/"
        Quando a data do sistema for "01/01/2018"
             E realizo o login com o usuário "109001" e senha "abcd"
             E acesso o menu "Des. Institucional::Planejamento Institucional::PDI"
         Então vejo a página "PDIs"
             E vejo o botão "Adicionar PDI"
        Quando clico no botão "Adicionar PDI"
         Então vejo a página "Adicionar PDI"
             E vejo os seguintes campos no formulário
               | Campo       | Tipo  |
               | Ano Inicial | Lista |
               | Ano Final   | Lista |
             E vejo o botão "Salvar"
        Quando clico no botão "Salvar"
         Então vejo os seguintes erros no formulário
               | Campo       | Tipo  | Mensagem                 |
               | Ano Inicial | Lista | Este campo é obrigatório |
               | Ano Final   | Lista | Este campo é obrigatório |
        Quando preencho o formulário com os dados
               | Campo       | Tipo  | Valor |
               | Ano Inicial | Lista | 2020  |
               | Ano Final   | Lista | 2018  |
             E clico no botão "Salvar"
         Então vejo os seguintes erros no formulário
               | Campo       | Tipo  | Mensagem                                  |
               | Ano Final   | Lista | O ano final deve ser maior que o inicial. |
        Quando preencho o formulário com os dados
               | Campo       | Tipo  | Valor |
               | Ano Inicial | Lista | 2018  |
               | Ano Final   | Lista | 2020  |
             E clico no botão "Salvar"
         Então vejo os seguintes erros no formulário
               | Campo       | Tipo  | Mensagem                                  |
               | Ano Final   | Lista | O ano final deve ter 4 anos de diferença. |
        Quando preencho o formulário com os dados
               | Campo       | Tipo  | Valor |
               | Ano Inicial | Lista | 2018  |
               | Ano Final   | Lista | 2022  |
             E clico no botão "Salvar"
         Então vejo mensagem de sucesso "Cadastro realizado com sucesso."
