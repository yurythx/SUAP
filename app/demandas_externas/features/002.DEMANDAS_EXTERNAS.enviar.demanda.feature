# -*- coding: utf-8 -*-
# language: pt

Funcionalidade: Submissão de Demanda da Comunidade

      @do_document
      Cenário: Adicionar Demanda da Comunidade
      Formulário de submissão de uma nova demanda da Comunidade.
      Ação executada por qualquer pessoa (Usuário anônimo).
          Dado acesso a página "/"
         Quando a data do sistema for "05/01/2020"
         E clico no link "Demandas da Comunidade"
         Então vejo a página "Adicionar Demanda da Comunidade"
         E vejo o botão "Adicionar Demanda"
         Quando clico no botão "Adicionar Demanda"
         Então vejo a página "Adicionar Demanda"
         E vejo os seguintes campos no formulário
               | Campo                                                                     | Tipo     |
               | Tipo da Demanda                                                           | Lista    |
               | Nome Completo / Razão Social                                              | Texto    |
               | CPF / CNPJ                                                                | Texto    |
               | Email                                                                     | Texto    |
               | Telefone(s) de Contato                                                    | Texto    |
               | Whatsapp                                                                  | Texto    |
               | Cidade                                                                    | Lista    |
               | Nome da Comunidade a ser atendida ou grupo a ser beneficiado pela demanda | Texto    |
               | Campus do IFRN que fica mais próximo da demanda                         | Lista    |
               | Descreva o problema/demanda                                               | Textarea |
               | Público-Alvo                                                              | checkbox multiplo |
               | Estimativa do número de beneficiários                             | Texto    |

             E vejo o botão "Salvar"
        Quando preencho o formulário com os dados
           | Campo                                                                     | Tipo       | Valor                   |
           | Tipo da Demanda                                                           | Lista    | Projeto                   |
           | Nome Completo / Razão Social                                              | Texto    | Nome do Cidadão           |
           | CPF / CNPJ                                                                | Texto    | 488.764.800-64            |
           | Email                                                                     | Texto    | email@teste.com           |
           | Telefone(s) de Contato                                                    | Texto    | (84) 91234-5678           |
           | Whatsapp                                                                  | Texto    | (84) 99999-1234           |
           | Cidade                                                                    | Lista    | Natal Demandas-RN         |
           | Nome da Comunidade a ser atendida ou grupo a ser beneficiado pela demanda | Texto    | Nome da Comunidade        |
           | Campus do IFRN que fica mais próximo da demanda                           | Lista    | Campus Zona Norte (Natal) |
           | Descreva o problema/demanda                                               | Textarea | Descrição do problema a ser resolvido |
           | Público-Alvo                                                              | checkbox multiplo |  Centro Comunitário, Comunidade Rural                          |
           | Estimativa do número de beneficiários                             | Texto    | 50                        |
             E clico no botão "Salvar"

        Então vejo mensagem de sucesso "Demanda cadastrada com sucesso. Mensagens sobre o andamento da demanda serão enviadas para o email informado."
