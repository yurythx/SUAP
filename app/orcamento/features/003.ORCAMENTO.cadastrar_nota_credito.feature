# -*- coding: utf-8 -*-
# language: pt
Funcionalidade: Cadastrar Nota de Crédito

  @do_document
  Cenário: Cadastrar Nota de Crédito
    Ação executada pelo Administrador.

    Dado acesso a página "/"
    Quando realizo o login com o usuário "admin" e senha "abc"
    E acesso o menu "Administração::Orçamento::Notas::Notas de Crédito::Notas de Crédito"
    Então vejo a página "Notas de Crédito"
    E vejo o botão "Adicionar Nota de Crédito"
    Quando clico no botão "Adicionar Nota de Crédito"
    Então vejo a página "Adicionar Nota de Crédito"
    E vejo os seguintes campos no formulário
      | Campo                    | Tipo                   |
      | Número da Nota                      | Texto                  |
      | Data de Emissão                    | Data             |
      | UG Emitente                   | Autocomplete            |
      | Gestão Emitente                    | Autocomplete            |
      | UG Favorecida                    | Autocomplete            |
      | Gestão Favorecida                    | Autocomplete            |
      | Observação                    | Textarea            |
      | Evento                    | Autocomplete            |
      | Esfera                    | Lista            |
      | Ptres                    | Lista            |
      | Fonte de Recurso Completa | Texto            |
      | Natureza de Despesa | Autocomplete |
      | Valor | Texto            |

    E vejo o botão "Salvar"
    Quando preencho o formulário com os dados
      | Campo                    | Tipo                   | Valor                           |
      | Número da Nota                      | Texto                  | 	2020NC000003 |
      | Data de Emissão                    | Data             | 20/05/2020 |
      | UG Emitente                   | Autocomplete            | 11|
      | Gestão Emitente                    | Autocomplete            | 01 |
      | UG Favorecida                    | Autocomplete            | 22 |
      | Gestão Favorecida                    | Autocomplete            | 02  |
      | Observação                    | Textarea            | DEVOLUÇÃO DE SALDO NÃO UTILIZADO |
      | Evento                    | Autocomplete            | 520415 |
      | Esfera                    | Lista            | 1 - Orçamento Fiscal |
      | Ptres                    | Lista            | 01 |
      | Fonte de Recurso Completa | Texto            |0100000000 |
      | Natureza de Despesa | Autocomplete | 339030 |
      | Valor | Texto            | 5.000,00 |
    E clico no botão "Salvar"

  Cenário: Sai do sistema
    Quando acesso o menu "Sair"
