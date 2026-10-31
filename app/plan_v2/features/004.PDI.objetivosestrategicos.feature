# -*- coding: utf-8 -*-
# language: pt

Funcionalidade: Atividades ligadas a operações com objetivos estratégicos no PDI

       Cenário: Monta os dados básicos para rodar os testes dessa feature
         Dada os dados básicos para o planejamento
            E os usuários do planejamento
            E um PDI cadastrado
            E as unidades administrativas
            E os macroprocessos
       Quando acesso a página "/"
            E a data do sistema for "01/01/2018"
            E realizo o login com o usuário "109001" e senha "abcd"


      Cenario: Acessa o PDI 2018 - 2022
          Dada a atual página
        Quando acesso o menu "Des. Institucional::Planejamento Institucional::PDI"
             E olho para a listagem
             E olho a linha "2018"
             E clico no botão "Detalhar"


      Cenário: Verifica a existência da aba Objetivos Estratégicos
          Dada a atual página
         Então vejo a aba "Objetivos Estratégicos"
        Quando clico na aba "Objetivos Estratégicos"
             E olho para a aba "Objetivos Estratégicos"
         Então vejo o botão "Todas as dimensões"
             E vejo o quadro "1. Dimensão 1 - Macroprocesso 1"
        Quando olho para o quadro "1. Dimensão 1 - Macroprocesso 1"
             E clico no botão "Adicionar Objetivo Estratégico"
             E olho para o popup
         Então vejo a página "Adicionar objetivo estratégico"
             E vejo os seguintes campos no formulário
               | Campo         | Tipo     |
               | Macroprocesso | Lista    |
               | Descrição     | Textarea |


      @do_document
      Cenário: Realiza o cadastro do objetivo estratégico
          Dada a atual página
        Quando olho para o popup
             E clico no botão "Salvar"
             E olho para o popup
         Então vejo os seguintes erros no formulário
               | Campo         | Tipo     | Mensagem                 |
               | Macroprocesso | Autocomplete    | Este campo é obrigatório |
               | Descrição     | Textarea | Este campo é obrigatório |
        Quando preencho o formulário com os dados
               | Campo         | Tipo     | Valor                    |
               | Macroprocesso | Autocomplete    | Macroprocesso 1          |
               | Descrição     | Textarea | Objetivo 1 - Macro 1     |
             E clico no botão "Salvar"
         Então vejo mensagem de sucesso "Objetivo estratégico salvo."


      @do_document
      Cenário: Realiza o cadastro da Meta
          Dada a atual página
        Quando olho para o objetivo estratégico do planejamento "Objetivo 1 - Macro 1"
         Então vejo o botão "Adicionar Meta"
             E vejo o botão "Editar"
        Quando clico no botão "Adicionar Meta"
             E olho para o popup
         Então vejo a página "Adicionar meta"
             E vejo os seguintes campos no formulário
               | Campo  | Tipo         |
               | Título | Textarea     |
               | Setor  | Autocomplete |
        Quando clico no botão "Salvar"
             E olho para a página
             E olho para o popup
         Então vejo os seguintes erros no formulário
               | Campo  | Tipo         | Mensagem                 |
               | Título | Textarea     | Este campo é obrigatório |
               | Setor  | Autocomplete | Este campo é obrigatório |
        Quando preencho o formulário com os dados
               | Campo  | Tipo         | Valor               |
               | Título | Textarea     | Objetivo 1 - Meta 1 |
               | Setor  | Autocomplete | A1                  |
             E clico no botão "Salvar"
         Então vejo mensagem de sucesso "Meta salva."
        Quando olho para a aba "Objetivos Estratégicos"
             E olho para o objetivo estratégico do planejamento "Objetivo 1 - Macro 1"
             E olho para a tabela
         Então vejo a linha "Objetivo 1 - Meta 1"
             E vejo o botão "Indicadores"


      @do_document
      Cenário: Realiza o cadastro de indicador
          Dada a atual página
        Quando olho para a aba "Objetivos Estratégicos"
             E olho para o objetivo estratégico do planejamento "Objetivo 1 - Macro 1"
             E olho para a tabela
             E olho a linha "Objetivo 1 - Meta 1"
         Então vejo o botão "Indicadores"
        Quando clico no botão "Indicadores"
         Então vejo a página "PDI - 2018 a 2022"
             E vejo o quadro "Indicadores"
             E vejo o botão "Incluir Indicador"
        Quando clico no botão "Incluir Indicador"
             E olho para o popup
         Então vejo a página "Adicionar Indicador"
             E vejo os seguintes campos no formulário
               | Campo                | Tipo     |
               | Denominação          | Texto    |
               | Críterio de Análise  | Texto    |
               | Forma de Cálculo     | Textarea |
               | Valor Físico Inicial | Texto    |
               | Valor Físico Final   | Texto    |
               | Método de Incremento | Lista    |
        Quando clico no botão "Salvar"
             E olho para a página
             E olho para o popup
         Então vejo os seguintes erros no formulário
               | Campo                | Tipo     | Mensagem                 |
               | Denominação          | Texto    | Este campo é obrigatório |
               | Críterio de Análise  | Texto    | Este campo é obrigatório |
               | Forma de Cálculo     | Textarea | Este campo é obrigatório |
               | Método de Incremento | Lista    | Este campo é obrigatório |
        Quando preencho o formulário com os dados
               | Campo                | Tipo     | Valor                        |
               | Denominação          | Texto    | Indicador 1 - Obj 1 - Meta 1 |
               | Críterio de Análise  | Texto    | Indicador 1 - Obj 1 - Meta 1 |
               | Forma de Cálculo     | Textarea | Forma de cálculo             |
               | Valor Físico Inicial | Texto    | 0,00                         |
               | Valor Físico Final   | Texto    | 100,00                       |
               | Método de Incremento | Lista    | Soma                         |
             E clico no botão "Salvar"
         Então vejo mensagem de sucesso "Indicador salvo."
        Quando olho para o quadro "Indicadores"
             E olho para a tabela
         Então vejo a linha "Indicador 1 - Obj 1 - Meta 1"
        Quando olho para a página
             E clico no botão "Voltar para o PDI"
         Então vejo a página "PDI - 2018 a 2022"
             E vejo a aba "Objetivos Estratégicos"
