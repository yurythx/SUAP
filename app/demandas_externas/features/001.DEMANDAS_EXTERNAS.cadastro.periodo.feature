# -*- coding: utf-8 -*-
# language: pt

Funcionalidade: Cadastro e Configuração do Período de Recebimento

      Cenário: Adicionando os usuários necessários para os testes demandas externas
          Dado os dados básicos para a demanda externa
          E os seguintes usuários
                | Nome          | Matrícula      | Setor    | Lotação  | Email                      | CPF            | Senha | Grupo                         |
                | Gerente de Demandas | 120001         | CZN      | CZN      | gerente@ifrn.edu.br        | 000.120.001-16 | abcd  | Gerente de Demandas Externas |
                | CoordExtensao | 120002         | DIAC/CZN | DIAC/CZN | coord_extensao@ifrn.edu.br | 000.120.002-05 | abcd  | Coordenador de Demandas Externas       |
                | Responsavel do Demandas Externas | 120003         | DIAC/CZN | DIAC/CZN | coord_proj@ifrn.edu.br   | 921.728.444-03 | abcd  | Servidor                      |
                | Participante1     | 120004         | DIAC/CZN | DIAC/CZN | coord_proj@ifrn.edu.br | 861.297.280-93 | abcd  | Servidor                      |
                | Participante2     | 120005         | DIAC/CZN | DIAC/CZN | coord_proj@ifrn.edu.br | 066.395.620-06 | abcd  | Servidor                      |

   Esquema do Cenário: Verifica a visibilidade do menu de Demandas Externas e da adição do Período pelo <Papel>
        Dado acesso a página "/"
        Quando realizo o login com o usuário "<Papel>" e senha "abcd"
        Então vejo o item de menu "Extensão::Demandas Externas::Períodos para Recebimento"
        Quando acesso a página "/admin/demandas_externas/periodo/"
        Então vejo a página "Períodos de Recebimento de Demandas"
        E vejo o botão "Adicionar Período de Recebimento de Demandas"
        Quando acesso o menu "Sair"
          Exemplos:
              | Papel  |
              | 120001 |

      @do_document
      Cenário: Cadastro do Período de Recebimento
      Cadastro do período de recebimento de demandas da comunidade.
      Ação executada pelo Gerente de Demandas Externas.
          Dado acesso a página "/"
        Quando realizo o login com o usuário "120001" e senha "abcd"
             E acesso o menu "Extensão::Demandas Externas::Períodos para Recebimento"
         Então vejo a página "Períodos de Recebimento de Demandas"
             E vejo o botão "Adicionar Período de Recebimento de Demandas"
        Quando clico no botão "Adicionar Período de Recebimento de Demandas"
         Então vejo a página "Adicionar Período de Recebimento de Demandas"
             E vejo os seguintes campos no formulário
               | Campo                      | Tipo                   |
               | Título                     | Texto                  |
               | Início do Período          | Data                  |
               | Término do Período         | Data                  |
               | Descrição                  | Texto Rico             |
               | Campi                      | FilteredSelectMultiple |
             E vejo o botão "Salvar"

        Quando preencho o formulário com os dados
               | Campo                      | Tipo                   | Valor                       |
               | Título                     | Texto                  | Novo período de Recebimento |
               | Início do Período          | Data                  | 01/01/2020                  |
               | Término do Período         | Data                  | 31/01/2020                  |
               | Descrição                  | Texto Rico             | Texto que será apresentado na tela de envio das demandas |
               | Campi                      | FilteredSelectMultiple | CZN                         |



             E clico no botão "Salvar"

         Então vejo mensagem de sucesso "Cadastro realizado com sucesso."

      Cenário: Sai do sistema
        Quando acesso o menu "Sair"
