# -*- coding: utf-8 -*-
# language: pt

Funcionalidade: Registrar a Conclusão da Demanda

      @do_document
      Cenário: Registrar a Conclusão da Demanda
      O responsável pela demanda precisa registrar que a mesma foi executada.
      Ação executada pelo Responsável pela Demanda.
         Dado acesso a página "/"
         Quando realizo o login com o usuário "120003" e senha "abcd"
         E acesso o menu "Extensão::Demandas Externas::Demandas"
         Então vejo a página "Demandas Externas"
         Quando clico na aba "Em Atendimento"
         E olho a linha "Nome do Cidadão"
         E clico no ícone de exibição
         Então vejo a página "Visualizar Demanda"
         Quando clico na aba "Execução"
        Então vejo o botão "Registrar Conclusão"
        Quando clico no botão "Registrar Conclusão"
        Então vejo os seguintes campos no formulário
               | Campo                                    | Tipo        |
               | Tipo de Ação                             | Autocomplete       |
               | Área Temática                            | Autocomplete       |
               | Quantidade de Beneficiários Atendidos    | Texto       |
               | Descrição sobre o Atendimento da Demanda | Textarea    |

        E vejo o botão "Salvar"

        Quando preencho o formulário com os dados
               | Campo                                    | Tipo     | Valor                       |
               | Tipo de Ação                             | Autocomplete    | Projeto |
               | Área Temática                            | Autocomplete    | Cultura |
               | Quantidade de Beneficiários Atendidos    | Texto    | 100     |
               | Descrição sobre o Atendimento da Demanda | Textarea | descrição de como a demanda foi atendida |
             E clico no botão "Salvar"
         Então vejo mensagem de sucesso "Atendimento da demanda registrado com sucesso."

      Cenário: Sai do sistema
        Quando acesso o menu "Sair"
